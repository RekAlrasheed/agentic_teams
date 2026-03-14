#!/usr/bin/env python3
"""
Token Tracker — Monitors token consumption across all agents.

Tracks every Claude call: agent, model, input/output tokens (estimated),
prompt size, duration. Stores in SQLite for querying and optimization.

Token estimation: ~4 characters = 1 token (conservative estimate).

Usage:
    from tools.token_tracker import TokenTracker

    tracker = TokenTracker()

    # Log a call
    tracker.log_call(
        agent="creative",
        model="sonnet",
        input_text="system prompt + user message",
        output_text="claude's response",
        duration_ms=2500,
        source="telegram",
    )

    # Analyze usage
    print(tracker.get_summary())           # Overall breakdown
    print(tracker.get_agent_breakdown())    # Per-agent usage
    print(tracker.get_top_consumers())      # What's eating tokens
    print(tracker.get_daily_usage())        # Daily trend
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "workspace" / "token_usage.db"

# Token weight multipliers — models consume quota at different rates
# on Max plan. Opus uses ~5x the quota of Haiku for the same tokens.
MODEL_WEIGHTS = {
    "haiku": 1.0,
    "sonnet": 3.0,
    "opus": 15.0,
}


def estimate_tokens(text: str) -> int:
    """Estimate token count from text. ~4 chars per token (conservative)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


class TokenTracker:
    """SQLite-backed token usage tracker."""

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = str(db_path or DB_PATH)
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                total_tokens INTEGER NOT NULL,
                weighted_tokens INTEGER NOT NULL,
                prompt_tokens INTEGER DEFAULT 0,
                duration_ms INTEGER DEFAULT 0,
                source TEXT DEFAULT 'unknown',
                task_type TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                date_key TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_usage_agent ON token_usage(agent);
            CREATE INDEX IF NOT EXISTS idx_usage_date ON token_usage(date_key);
            CREATE INDEX IF NOT EXISTS idx_usage_model ON token_usage(model);
        """)
        conn.commit()

    def log_call(
        self,
        agent: str,
        model: str,
        input_text: str = "",
        output_text: str = "",
        prompt_text: str = "",
        duration_ms: int = 0,
        source: str = "unknown",
        task_type: str = "",
    ):
        """Log a Claude call with estimated token counts."""
        input_tokens = estimate_tokens(input_text)
        output_tokens = estimate_tokens(output_text)
        prompt_tokens = estimate_tokens(prompt_text)
        total_tokens = input_tokens + output_tokens
        weight = MODEL_WEIGHTS.get(model.lower(), 3.0)
        weighted_tokens = int(total_tokens * weight)

        now = datetime.now(timezone.utc)
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO token_usage
               (agent, model, input_tokens, output_tokens, total_tokens,
                weighted_tokens, prompt_tokens, duration_ms, source,
                task_type, created_at, date_key)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (agent.lower(), model.lower(), input_tokens, output_tokens,
             total_tokens, weighted_tokens, prompt_tokens, duration_ms,
             source, task_type, now.isoformat(), now.strftime("%Y-%m-%d")),
        )
        conn.commit()

    def get_summary(self, days: int = 7) -> str:
        """Get a human-readable usage summary."""
        conn = self._get_conn()
        row = conn.execute("""
            SELECT COUNT(*) as calls,
                   COALESCE(SUM(total_tokens), 0) as total,
                   COALESCE(SUM(weighted_tokens), 0) as weighted,
                   COALESCE(SUM(input_tokens), 0) as input_t,
                   COALESCE(SUM(output_tokens), 0) as output_t,
                   COALESCE(SUM(prompt_tokens), 0) as prompt_t,
                   COALESCE(AVG(duration_ms), 0) as avg_ms
            FROM token_usage
            WHERE date_key >= date('now', ?)
        """, (f"-{days} days",)).fetchone()

        if not row or row["calls"] == 0:
            return "No token usage data yet."

        total_input = row['input_t'] + row['prompt_t']
        lines = [
            f"Token Usage (last {days} days):",
            f"  Calls: {row['calls']}",
            f"  Total input: {total_input:,} (message: {row['input_t']:,} + prompt: {row['prompt_t']:,})",
            f"  Total output: {row['output_t']:,}",
            f"  Prompt overhead: {self._pct(row['prompt_t'], total_input)} of input is system prompt",
            f"  Weighted tokens: {row['weighted']:,} (accounts for model cost)",
            f"  Avg response time: {row['avg_ms']:.0f}ms",
        ]
        return "\n".join(lines)

    def get_agent_breakdown(self, days: int = 7) -> str:
        """Show token usage per agent — find who's consuming the most."""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT agent,
                   COUNT(*) as calls,
                   SUM(total_tokens) as total,
                   SUM(weighted_tokens) as weighted,
                   SUM(prompt_tokens) as prompt_t,
                   GROUP_CONCAT(DISTINCT model) as models
            FROM token_usage
            WHERE date_key >= date('now', ?)
            GROUP BY agent
            ORDER BY weighted DESC
        """, (f"-{days} days",)).fetchall()

        if not rows:
            return "No usage data."

        lines = [f"Token usage by agent (last {days} days):"]
        for r in rows:
            lines.append(
                f"  {r['agent']}: {r['weighted']:,} weighted tokens "
                f"({r['calls']} calls, models: {r['models']}, "
                f"prompt overhead: {r['prompt_t']:,})"
            )
        return "\n".join(lines)

    def get_top_consumers(self, days: int = 7) -> str:
        """Identify what's eating the most tokens."""
        conn = self._get_conn()
        findings = []

        # 1. Model usage breakdown
        models = conn.execute("""
            SELECT model, COUNT(*) as calls,
                   SUM(total_tokens) as total,
                   SUM(weighted_tokens) as weighted
            FROM token_usage
            WHERE date_key >= date('now', ?)
            GROUP BY model ORDER BY weighted DESC
        """, (f"-{days} days",)).fetchall()

        if models:
            findings.append("Model usage:")
            for m in models:
                findings.append(
                    f"  {m['model']}: {m['calls']} calls, "
                    f"{m['total']:,} raw / {m['weighted']:,} weighted tokens"
                )

        # 2. System prompt overhead
        prompt_row = conn.execute("""
            SELECT SUM(prompt_tokens) as prompt_total,
                   SUM(input_tokens) as input_total
            FROM token_usage
            WHERE date_key >= date('now', ?)
        """, (f"-{days} days",)).fetchone()

        if prompt_row and prompt_row["input_total"]:
            total_input = prompt_row["prompt_total"] + prompt_row["input_total"]
            pct = self._pct(prompt_row["prompt_total"], total_input)
            findings.append(f"\nSystem prompt overhead: {pct} of all input tokens")
            if total_input > 0:
                ratio = prompt_row["prompt_total"] / total_input * 100
                if ratio > 50:
                    findings.append("  WARNING: prompts are over 50% of input — consider trimming")

        # 3. Biggest single calls
        big = conn.execute("""
            SELECT agent, model, total_tokens, weighted_tokens, task_type,
                   created_at
            FROM token_usage
            WHERE date_key >= date('now', ?)
            ORDER BY weighted_tokens DESC LIMIT 5
        """, (f"-{days} days",)).fetchall()

        if big:
            findings.append("\nTop 5 most expensive calls:")
            for b in big:
                findings.append(
                    f"  {b['agent']}/{b['model']}: {b['weighted_tokens']:,} weighted "
                    f"({b['task_type'] or 'unknown'} @ {b['created_at'][:16]})"
                )

        return "\n".join(findings) if findings else "No usage data."

    def get_daily_usage(self, days: int = 14) -> str:
        """Show daily usage trend."""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT date_key, COUNT(*) as calls,
                   SUM(total_tokens) as total,
                   SUM(weighted_tokens) as weighted
            FROM token_usage
            WHERE date_key >= date('now', ?)
            GROUP BY date_key ORDER BY date_key
        """, (f"-{days} days",)).fetchall()

        if not rows:
            return "No daily usage data."

        lines = ["Daily usage:"]
        for r in rows:
            bar = "#" * min(50, r["weighted"] // 1000)
            lines.append(f"  {r['date_key']}: {r['weighted']:>8,} weighted ({r['calls']} calls) {bar}")
        return "\n".join(lines)

    def get_optimization_tips(self, days: int = 7) -> list[str]:
        """Analyze usage patterns and return actionable tips."""
        conn = self._get_conn()
        tips = []

        # Check if opus is being used for simple tasks
        opus_calls = conn.execute("""
            SELECT COUNT(*) as c FROM token_usage
            WHERE model = 'opus' AND date_key >= date('now', ?)
        """, (f"-{days} days",)).fetchone()
        total_calls = conn.execute("""
            SELECT COUNT(*) as c FROM token_usage
            WHERE date_key >= date('now', ?)
        """, (f"-{days} days",)).fetchone()

        if opus_calls and total_calls and total_calls["c"] > 0:
            pct = opus_calls["c"] / total_calls["c"] * 100
            if pct > 20:
                tips.append(
                    f"Opus is used for {pct:.0f}% of calls. "
                    f"Downgrade to Sonnet where possible — Opus uses 5x the quota."
                )

        # Check prompt overhead
        prompt_check = conn.execute("""
            SELECT AVG(prompt_tokens) as avg_prompt,
                   AVG(input_tokens) as avg_input
            FROM token_usage
            WHERE date_key >= date('now', ?)
        """, (f"-{days} days",)).fetchone()

        if prompt_check and prompt_check["avg_input"] and prompt_check["avg_prompt"]:
            total_avg = prompt_check["avg_prompt"] + prompt_check["avg_input"]
            if total_avg > 0:
                ratio = prompt_check["avg_prompt"] / total_avg * 100
                if ratio > 60:
                    tips.append(
                        f"System prompts are {ratio:.0f}% of input tokens. "
                        f"Trim the system prompt or load context lazily."
                    )

        # Check agent imbalance
        agents = conn.execute("""
            SELECT agent, SUM(weighted_tokens) as w
            FROM token_usage
            WHERE date_key >= date('now', ?)
            GROUP BY agent ORDER BY w DESC
        """, (f"-{days} days",)).fetchall()

        if len(agents) >= 2:
            top = agents[0]
            bottom = agents[-1]
            if bottom["w"] > 0 and top["w"] / bottom["w"] > 5:
                tips.append(
                    f"{top['agent']} uses {top['w'] // bottom['w']}x more tokens than "
                    f"{bottom['agent']}. Review if {top['agent']}'s tasks need that much."
                )

        if not tips:
            tips.append("No optimization issues detected. Usage looks healthy.")

        return tips

    @staticmethod
    def _pct(part: int, total: int) -> str:
        if not total:
            return "0%"
        return f"{part / total * 100:.0f}%"

    # ── Budget alerts ──────────────────────────────────────────────────

    def check_budget(self, daily_limit: int = 500_000) -> Optional[str]:
        """Check if today's weighted token usage exceeds the daily budget.

        Returns a warning message if over budget, None otherwise.
        Default limit: 500K weighted tokens/day (~reasonable for Max plan).
        """
        conn = self._get_conn()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        row = conn.execute(
            "SELECT COALESCE(SUM(weighted_tokens), 0) as total FROM token_usage WHERE date_key = ?",
            (today,),
        ).fetchone()

        used = row["total"] if row else 0
        pct = (used / daily_limit * 100) if daily_limit > 0 else 0

        if pct >= 100:
            return (
                f"BUDGET EXCEEDED: {used:,} / {daily_limit:,} weighted tokens today ({pct:.0f}%). "
                f"Consider pausing non-urgent tasks."
            )
        elif pct >= 80:
            return (
                f"Budget warning: {used:,} / {daily_limit:,} weighted tokens today ({pct:.0f}%). "
                f"Approaching daily limit."
            )
        return None

    def get_today_usage(self) -> dict:
        """Get today's usage summary as a dict."""
        conn = self._get_conn()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        row = conn.execute("""
            SELECT COUNT(*) as calls,
                   COALESCE(SUM(total_tokens), 0) as total,
                   COALESCE(SUM(weighted_tokens), 0) as weighted,
                   COALESCE(SUM(prompt_tokens), 0) as prompt
            FROM token_usage WHERE date_key = ?
        """, (today,)).fetchone()
        return dict(row) if row else {"calls": 0, "total": 0, "weighted": 0, "prompt": 0}

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
