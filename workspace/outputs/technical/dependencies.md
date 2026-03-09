# Navaia AI Workforce — Python Dependencies

**File:** `tools/requirements.txt`
**Date:** 2026-03-08

---

## Runtime Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `python-telegram-bot` | >=21.0 | Telegram Bot SDK — powers the Founder's Telegram interface for sending/receiving messages and task creation via `tools/telegram_bridge.py` |
| `watchdog` | >=4.0.0 | File system event monitoring — watches `workspace/tasks/inbox/` and `workspace/comms/` directories for new files in real-time, triggering agent loops |
| `python-dotenv` | >=1.0.0 | Environment variable loader — reads `.env` file for secrets (Telegram Bot token, Trello API key/token, board IDs) so credentials stay out of source code |

---

## Tool Scripts

| File | Language | Description |
|------|----------|-------------|
| `tools/telegram_bridge.py` | Python | Main bot process: receives Founder messages via Telegram, routes them to `workspace/tasks/inbox/`, watches `workspace/comms/to-founder/` for agent replies and forwards them to Telegram |
| `tools/catalog.py` | Python | Knowledge base cataloger: scans `knowledge/` directory and auto-generates `knowledge/INDEX.md` with structured file catalog organized by category and agent relevance |
| `tools/trello_api.sh` | Bash | Trello API wrapper: shell functions agents source to create/update/move Trello cards without raw curl calls |

---

## Standard Library Modules Used

`asyncio`, `json`, `logging`, `os`, `signal`, `subprocess`, `sys`, `time`, `urllib`, `datetime`, `pathlib` — all built into Python 3, no additional install required.
