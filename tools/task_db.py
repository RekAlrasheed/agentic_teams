#!/usr/bin/env python3
"""
TaskDB — SQLite-backed task management for Navaia AI Workforce.

Replaces file-scanning with atomic database operations. No race conditions,
full history, queryable status. File-based dispatch is kept as a compatibility
layer — when a task file is created, it's also recorded in the database.

Usage:
    from tools.task_db import TaskDB

    db = TaskDB()
    task_id = db.create_task("Write blog post", "About AI in real estate", "creative")
    db.update_status(task_id, "in_progress")
    db.update_status(task_id, "done", result="Blog post written. See workspace/outputs/creative/blog.md")
    db.fail_task(task_id, "Rate limited after 3 retries")

    # Query
    pending = db.get_tasks(status="pending", agent="creative")
    history = db.get_task_history(limit=50)
    stats = db.get_agent_stats()
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


class TaskDB:
    """Thread-safe SQLite task database."""

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = str(db_path or DB_PATH)
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self):
        """Create tables if they don't exist."""
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                agent TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                priority TEXT DEFAULT 'standard',
                source TEXT DEFAULT 'dashboard',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                result TEXT,
                error TEXT,
                retry_count INTEGER DEFAULT 0,
                trello_card_id TEXT,
                task_file TEXT,
                metadata TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_agent TEXT NOT NULL,
                to_agent TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                read_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_agent ON tasks(agent);
            CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);
            CREATE INDEX IF NOT EXISTS idx_messages_to ON messages(to_agent, read_at);
        """)
        conn.commit()

    def create_task(
        self,
        title: str,
        description: str,
        agent: str,
        source: str = "dashboard",
        priority: str = "standard",
        trello_card_id: str = "",
        task_file: str = "",
    ) -> int:
        """Create a new task. Returns the task ID."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        cursor = conn.execute(
            """INSERT INTO tasks (title, description, agent, source, priority,
               trello_card_id, task_file, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, description, agent.lower(), source, priority,
             trello_card_id, task_file, now, now),
        )
        conn.commit()
        return cursor.lastrowid

    def update_status(
        self,
        task_id: int,
        status: str,
        result: Optional[str] = None,
        error: Optional[str] = None,
    ):
        """Update task status. Valid: pending, in_progress, done, failed, blocked."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()

        updates = ["status = ?", "updated_at = ?"]
        params = [status, now]

        if status == "in_progress":
            updates.append("started_at = ?")
            params.append(now)
        elif status in ("done", "failed"):
            updates.append("completed_at = ?")
            params.append(now)

        if result is not None:
            updates.append("result = ?")
            params.append(result)
        if error is not None:
            updates.append("error = ?")
            params.append(error)

        params.append(task_id)
        conn.execute(
            f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()

    def fail_task(self, task_id: int, error: str):
        """Mark a task as failed, increment retry count."""
        conn = self._get_conn()
        conn.execute(
            """UPDATE tasks SET status = 'failed', error = ?,
               retry_count = retry_count + 1,
               updated_at = ?, completed_at = ?
               WHERE id = ?""",
            (error, datetime.now(timezone.utc).isoformat(),
             datetime.now(timezone.utc).isoformat(), task_id),
        )
        conn.commit()

    def retry_task(self, task_id: int) -> bool:
        """Reset a failed task to pending for retry. Returns False if max retries exceeded."""
        conn = self._get_conn()
        row = conn.execute("SELECT retry_count FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row or row["retry_count"] >= 3:
            return False
        conn.execute(
            """UPDATE tasks SET status = 'pending', error = NULL,
               updated_at = ? WHERE id = ?""",
            (datetime.now(timezone.utc).isoformat(), task_id),
        )
        conn.commit()
        return True

    def get_task(self, task_id: int) -> Optional[dict]:
        """Get a single task by ID."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def get_tasks(
        self,
        status: Optional[str] = None,
        agent: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Query tasks with optional filters."""
        conn = self._get_conn()
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if agent:
            query += " AND agent = ?"
            params.append(agent.lower())

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_task_history(self, limit: int = 50) -> list[dict]:
        """Get recent task history across all agents."""
        return self.get_tasks(limit=limit)

    def get_agent_stats(self) -> dict:
        """Get per-agent task statistics."""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT agent,
                   COUNT(*) as total,
                   SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                   SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                   SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as done,
                   SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
            FROM tasks GROUP BY agent
        """).fetchall()
        return {r["agent"]: dict(r) for r in rows}

    def get_summary(self) -> str:
        """Get a human-readable task summary."""
        stats = self.get_agent_stats()
        if not stats:
            return "No tasks in database."

        lines = []
        for agent, s in stats.items():
            parts = []
            if s["pending"]:
                parts.append(f"{s['pending']} pending")
            if s["in_progress"]:
                parts.append(f"{s['in_progress']} active")
            if s["done"]:
                parts.append(f"{s['done']} done")
            if s["failed"]:
                parts.append(f"{s['failed']} failed")
            lines.append(f"  {agent}: {', '.join(parts)}")
        return "Task DB:\n" + "\n".join(lines)

    # ── Inter-agent messaging ─────────────────────────────────────────

    def send_message(self, from_agent: str, to_agent: str, content: str) -> int:
        """Send a message between agents. Returns message ID."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO messages (from_agent, to_agent, content, created_at) VALUES (?, ?, ?, ?)",
            (from_agent.lower(), to_agent.lower(), content, now),
        )
        conn.commit()
        return cursor.lastrowid

    def get_unread_messages(self, agent: str) -> list[dict]:
        """Get unread messages for an agent."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM messages WHERE to_agent = ? AND read_at IS NULL ORDER BY created_at",
            (agent.lower(),),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_read(self, message_id: int):
        """Mark a message as read."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE messages SET read_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), message_id),
        )
        conn.commit()

    def close(self):
        """Close the database connection."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
