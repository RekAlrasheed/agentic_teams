#!/usr/bin/env python3
"""
PerformanceDB — RL Feedback & KPI Tracking for Navaia AI Workforce.

Lightweight reinforcement learning via SQLite. CEO agent (Rex) evaluates
agent batches every 20 completed tasks, assigns quality scores, and the
system derives routing recommendations from cumulative scores.

Also tracks quarterly KPIs per department.

Usage:
    from tools.performance_db import PerformanceDB

    db = PerformanceDB()

    # Record an RL evaluation
    db.record_evaluation(
        agent="creative",
        batch=1,
        score_delta=3.0,
        quality_rating=4,
        token_efficiency=0.85,
        failure_count=0,
        success_count=5,
        evaluation_summary="Strong output quality, efficient token use.",
        tasks_evaluated=["task1.md", "task2.md"],
    )

    # Get score summary
    summary = db.get_score_summary()
    # {"creative": {"score": 3.0, "trend": "up", "last_eval": "2026-...", "last_rating": 4}}

    # Record a KPI snapshot
    db.record_kpi(
        agent="creative",
        period="Q1-2026",
        kpi_name="Output volume",
        target_value=15.0,
        actual_value=18.0,
        unit="count",
        category="department",
    )

    # Get routing recommendations
    recs = db.get_routing_recommendations()
    # {"creative": {"level": "high performer", "note": "assign complex tasks"}}
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "workspace" / "tasks.db"


class PerformanceDB:
    """Thread-safe RL + KPI database using the shared tasks.db."""

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
            CREATE TABLE IF NOT EXISTS rl_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent TEXT NOT NULL,
                evaluation_batch INTEGER NOT NULL,
                score_delta REAL NOT NULL,
                cumulative_score REAL NOT NULL,
                quality_rating INTEGER NOT NULL,
                token_efficiency REAL DEFAULT 0.0,
                failure_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                evaluation_summary TEXT DEFAULT '',
                evaluated_at TEXT NOT NULL,
                tasks_evaluated TEXT DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS kpi_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent TEXT NOT NULL,
                period TEXT NOT NULL,
                kpi_name TEXT NOT NULL,
                target_value REAL NOT NULL,
                actual_value REAL,
                unit TEXT DEFAULT '%',
                category TEXT DEFAULT 'shared',
                measured_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_rl_agent ON rl_scores(agent);
            CREATE INDEX IF NOT EXISTS idx_rl_evaluated ON rl_scores(evaluated_at);
            CREATE INDEX IF NOT EXISTS idx_kpi_agent ON kpi_snapshots(agent);
            CREATE INDEX IF NOT EXISTS idx_kpi_period ON kpi_snapshots(period);
        """)

    # ── RL Evaluations ──────────────────────────────────────────────────────

    def record_evaluation(
        self,
        agent: str,
        batch: int,
        score_delta: float,
        quality_rating: int,
        token_efficiency: float = 0.0,
        failure_count: int = 0,
        success_count: int = 0,
        evaluation_summary: str = "",
        tasks_evaluated: Optional[list] = None,
    ) -> int:
        """Store an RL evaluation and return the row id."""
        conn = self._get_conn()

        # Calculate cumulative score
        row = conn.execute(
            "SELECT cumulative_score FROM rl_scores WHERE agent = ? ORDER BY id DESC LIMIT 1",
            (agent,),
        ).fetchone()
        prev_score = row["cumulative_score"] if row else 0.0
        cumulative = prev_score + score_delta

        now = datetime.now(timezone.utc).isoformat()
        tasks_json = json.dumps(tasks_evaluated or [])

        cur = conn.execute(
            """INSERT INTO rl_scores
               (agent, evaluation_batch, score_delta, cumulative_score,
                quality_rating, token_efficiency, failure_count, success_count,
                evaluation_summary, evaluated_at, tasks_evaluated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                agent, batch, score_delta, cumulative,
                quality_rating, token_efficiency, failure_count, success_count,
                evaluation_summary, now, tasks_json,
            ),
        )
        conn.commit()
        return cur.lastrowid

    def get_score_summary(self) -> dict:
        """Return {agent: {score, trend, last_eval, last_rating}} for all agents."""
        conn = self._get_conn()
        agents = [r["agent"] for r in conn.execute(
            "SELECT DISTINCT agent FROM rl_scores"
        ).fetchall()]

        result = {}
        for agent in agents:
            rows = conn.execute(
                "SELECT cumulative_score, score_delta, evaluated_at, quality_rating "
                "FROM rl_scores WHERE agent = ? ORDER BY id DESC LIMIT 2",
                (agent,),
            ).fetchall()

            if not rows:
                continue

            latest = rows[0]
            trend = "stable"
            if len(rows) >= 2:
                if latest["score_delta"] > 0:
                    trend = "up"
                elif latest["score_delta"] < 0:
                    trend = "down"

            result[agent] = {
                "score": latest["cumulative_score"],
                "trend": trend,
                "last_eval": latest["evaluated_at"],
                "last_rating": latest["quality_rating"],
            }

        return result

    def get_all_scores(self, limit: int = 50) -> list:
        """Return evaluation history list."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM rl_scores ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_agent_scores(self, agent: str, limit: int = 20) -> list:
        """Return evaluation history for a specific agent."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM rl_scores WHERE agent = ? ORDER BY id DESC LIMIT ?",
            (agent, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── KPI Snapshots ───────────────────────────────────────────────────────

    def record_kpi(
        self,
        agent: str,
        period: str,
        kpi_name: str,
        target_value: float,
        actual_value: Optional[float] = None,
        unit: str = "%",
        category: str = "shared",
    ) -> int:
        """Store a KPI snapshot and return the row id."""
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()

        cur = conn.execute(
            """INSERT INTO kpi_snapshots
               (agent, period, kpi_name, target_value, actual_value, unit, category, measured_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (agent, period, kpi_name, target_value, actual_value, unit, category, now),
        )
        conn.commit()
        return cur.lastrowid

    def get_latest_kpis(self) -> dict:
        """Return {agent: [{kpi_name, target, actual, status, unit, category}]}."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT agent, kpi_name, target_value, actual_value, unit, category, measured_at
               FROM kpi_snapshots
               WHERE id IN (
                   SELECT MAX(id) FROM kpi_snapshots GROUP BY agent, kpi_name
               )
               ORDER BY agent, kpi_name""",
        ).fetchall()

        result = {}
        for r in rows:
            agent = r["agent"]
            if agent not in result:
                result[agent] = []

            actual = r["actual_value"]
            target = r["target_value"]
            if actual is None:
                status = "pending"
            elif target > 0 and actual >= target:
                status = "met"
            elif target > 0 and actual < target:
                status = "missed"
            else:
                status = "met" if actual <= abs(target) else "missed"

            result[agent].append({
                "kpi_name": r["kpi_name"],
                "target": target,
                "actual": actual,
                "status": status,
                "unit": r["unit"],
                "category": r["category"],
                "measured_at": r["measured_at"],
            })

        return result

    def get_kpis_by_period(self, period: str) -> dict:
        """Return KPIs filtered by period."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM kpi_snapshots WHERE period = ? ORDER BY agent, kpi_name",
            (period,),
        ).fetchall()

        result = {}
        for r in rows:
            agent = r["agent"]
            if agent not in result:
                result[agent] = []
            result[agent].append(dict(r))
        return result

    # ── Routing Recommendations ─────────────────────────────────────────────

    def get_routing_recommendations(self) -> dict:
        """Return {agent: {level, note}} based on cumulative RL scores."""
        summary = self.get_score_summary()
        result = {}

        for agent, data in summary.items():
            score = data["score"]
            if score > 10:
                level = "high performer"
                note = "assign complex tasks"
            elif score >= 0:
                level = "adequate"
                note = "maintain workload"
            else:
                level = "struggling"
                note = "assign simpler tasks or escalate model"

            result[agent] = {"level": level, "note": note}

        return result

    # ── Dashboard Aggregation ───────────────────────────────────────────────

    def get_dashboard_data(self, days: int = 30) -> dict:
        """Return combined data for the performance dashboard page."""
        conn = self._get_conn()

        # Task metrics from tasks table (if it exists)
        task_metrics = {}
        try:
            rows = conn.execute(
                """SELECT agent,
                          COUNT(CASE WHEN status = 'done' THEN 1 END) as done,
                          COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
                          COUNT(*) as total
                   FROM tasks
                   GROUP BY agent"""
            ).fetchall()
            for r in rows:
                agent = r["agent"]
                done = r["done"]
                failed = r["failed"]
                total = r["total"]
                pct = round(done / total * 100, 1) if total > 0 else 0
                task_metrics[agent] = {
                    "done": done,
                    "failed": failed,
                    "total": total,
                    "completion_pct": pct,
                }
        except Exception:
            pass

        # Token usage from token_usage table (if it exists)
        token_usage = {}
        try:
            token_db_path = REPO_ROOT / "workspace" / "token_usage.db"
            if token_db_path.exists():
                tconn = sqlite3.connect(str(token_db_path), timeout=5)
                tconn.row_factory = sqlite3.Row
                rows = tconn.execute(
                    """SELECT agent,
                              SUM(input_tokens + output_tokens) as total_tokens,
                              SUM(weighted_cost) as total_cost
                       FROM token_usage
                       WHERE recorded_at >= datetime('now', ?)
                       GROUP BY agent""",
                    (f"-{days} days",),
                ).fetchall()
                for r in rows:
                    token_usage[r["agent"]] = {
                        "total_tokens": r["total_tokens"] or 0,
                        "total_cost": round(r["total_cost"] or 0, 4),
                    }
                tconn.close()
        except Exception:
            pass

        return {
            "scores": self.get_score_summary(),
            "task_metrics": task_metrics,
            "token_usage": token_usage,
            "kpis": self.get_latest_kpis(),
            "recent_evaluations": self.get_all_scores(limit=20),
            "routing": self.get_routing_recommendations(),
        }
