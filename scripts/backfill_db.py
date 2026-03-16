#!/usr/bin/env python3
"""
Backfill TaskDB — One-time migration from file-based history to SQLite.

Scans workspace/tasks/done/, workspace/outputs/, and workspace/comms/to-manager/
and inserts records into the TaskDB so history is preserved before cleanup
deletes old files.

Usage:
    python3 scripts/backfill_db.py          # run backfill
    python3 scripts/backfill_db.py --dry-run # preview without writing
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from task_db import TaskDB


def parse_task_file(filepath: Path) -> dict:
    """Extract title, description, agent, and source from a task MD file."""
    text = filepath.read_text(encoding="utf-8", errors="replace")
    title = ""
    agent = ""
    source = "file-backfill"

    for line in text.split("\n"):
        if line.startswith("## TASK:"):
            title = line.replace("## TASK:", "").strip()
        elif line.startswith("**Assigned Agent:**"):
            agent = line.replace("**Assigned Agent:**", "").strip().lower()
        elif line.startswith("**Source:**"):
            source = line.replace("**Source:**", "").strip()

    if not title:
        title = filepath.stem

    # Infer agent from filename prefix if not found in content
    if not agent:
        name = filepath.name.lower()
        for a in ("creative", "technical", "admin", "pm", "ceo"):
            if a in name or a in str(filepath.parent):
                agent = a
                break
        if not agent:
            agent = "unknown"

    description = text[:500]
    return {"title": title, "description": description, "agent": agent, "source": source}


def detect_agent_from_path(filepath: Path) -> str:
    """Infer agent from the file's parent directory."""
    parts = filepath.parts
    for a in ("creative", "technical", "admin", "pm", "ceo"):
        if a in parts:
            return a
    return "unknown"


def backfill_tasks(db: TaskDB, dry_run: bool) -> int:
    """Scan workspace/tasks/done/ and insert into tasks table."""
    done_dir = REPO_ROOT / "workspace" / "tasks" / "done"
    if not done_dir.exists():
        print("  No done/ directory found.")
        return 0

    count = 0
    for f in sorted(done_dir.iterdir()):
        if not f.is_file() or f.name == ".gitkeep":
            continue
        parsed = parse_task_file(f)
        if dry_run:
            print(f"  [DRY] task: {parsed['title'][:60]} | agent={parsed['agent']}")
        else:
            task_id = db.create_task(
                title=parsed["title"],
                description=parsed["description"],
                agent=parsed["agent"],
                source=parsed["source"],
                task_file=str(f),
            )
            db.update_status(task_id, "done")
        count += 1
    return count


def backfill_outputs(db: TaskDB, dry_run: bool) -> int:
    """Scan workspace/outputs/ and insert into outputs table."""
    outputs_dir = REPO_ROOT / "workspace" / "outputs"
    if not outputs_dir.exists():
        print("  No outputs/ directory found.")
        return 0

    count = 0
    for f in sorted(outputs_dir.rglob("*")):
        if not f.is_file() or f.name == ".gitkeep":
            continue
        agent = detect_agent_from_path(f)
        size = f.stat().st_size
        if dry_run:
            print(f"  [DRY] output: {f.name} | agent={agent} | {size}B")
        else:
            db.record_output(
                agent=agent,
                filename=f.name,
                filepath=str(f.relative_to(REPO_ROOT)),
                size_bytes=size,
            )
        count += 1
    return count


def backfill_messages(db: TaskDB, dry_run: bool) -> int:
    """Scan workspace/comms/to-manager/ and insert into messages table."""
    comms_dir = REPO_ROOT / "workspace" / "comms" / "to-manager"
    if not comms_dir.exists():
        print("  No to-manager/ directory found.")
        return 0

    count = 0
    for f in sorted(comms_dir.iterdir()):
        if not f.is_file() or f.name == ".gitkeep":
            continue
        text = f.read_text(encoding="utf-8", errors="replace")

        # Try to detect which agent sent it
        from_agent = "unknown"
        for line in text.split("\n"):
            if "**Agent:**" in line:
                val = line.split("**Agent:**")[-1].strip().lower()
                for a in ("navi", "muse", "arch", "sage", "rex"):
                    if a in val:
                        from_agent = {"navi": "pm", "muse": "creative", "arch": "technical", "sage": "admin", "rex": "ceo"}[a]
                        break
                break

        # Also detect from filename
        if from_agent == "unknown":
            name = f.name.lower()
            for a_name, a_id in [("muse", "creative"), ("arch", "technical"), ("sage", "admin"), ("navi", "pm"), ("rex", "ceo")]:
                if a_name in name or a_id in name:
                    from_agent = a_id
                    break

        if dry_run:
            print(f"  [DRY] msg: {f.name} | from={from_agent}")
        else:
            db.send_message(from_agent=from_agent, to_agent="manager", content=text[:2000])
        count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="Backfill TaskDB from workspace files")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    args = parser.parse_args()

    db = TaskDB()

    print("=== TaskDB Backfill ===")
    if args.dry_run:
        print("(DRY RUN — no writes)\n")

    print("1. Backfilling tasks from workspace/tasks/done/...")
    task_count = backfill_tasks(db, args.dry_run)
    print(f"   → {task_count} tasks\n")

    print("2. Backfilling outputs from workspace/outputs/...")
    output_count = backfill_outputs(db, args.dry_run)
    print(f"   → {output_count} outputs\n")

    print("3. Backfilling messages from workspace/comms/to-manager/...")
    msg_count = backfill_messages(db, args.dry_run)
    print(f"   → {msg_count} messages\n")

    total = task_count + output_count + msg_count
    print(f"=== Done: {total} records {'previewed' if args.dry_run else 'inserted'} ===")

    if not args.dry_run:
        print(f"\nDB summary:\n{db.get_summary()}")

    db.close()


if __name__ == "__main__":
    main()
