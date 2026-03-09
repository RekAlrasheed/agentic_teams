# Navaia AI Workforce — System Health Check

**Date:** 2026-03-08
**Agent:** Arch (Technical)

---

## Scripts & Their Purpose

| Script | Language | Purpose |
|--------|----------|---------|
| `scripts/loop.sh` | Bash | **24/7 PM loop** — auto-restarts Claude as Navi (PM Agent) every 30s after session ends. Starts Telegram bridge once. Stops on STOP signal or Ctrl+C. |
| `scripts/agent-loop.sh <agent>` | Bash | **Per-agent loop** — runs a single agent (pm/creative/technical/admin) in its own terminal, polls for tasks every 15-30s, and restarts Claude when work is found. Used for multi-terminal mode. |
| `scripts/start.sh` | Bash | **Single-session launcher** — starts Telegram bridge + launches Claude once. Used for one-off runs instead of persistent loops. |
| `scripts/setup.sh` | Bash | **Environment setup** — scaffolds directory structure, creates .env template, installs Python deps. Run once on fresh clone. |
| `tools/telegram_bridge.py` | Python | **Telegram ↔ filesystem bridge** — receives Founder messages, writes task files to `workspace/tasks/inbox/`. Watches `workspace/comms/to-founder/` and forwards agent messages to Founder on Telegram. |
| `tools/catalog.py` | Python | **Knowledge cataloger** — scans `knowledge/` directory and auto-generates `knowledge/INDEX.md`. Run manually when knowledge base changes. |
| `tools/trello_api.sh` | Bash | **Trello wrapper** — shell functions (`create_card`, `move_card`, `update_card`) that agents `source` to update the Navaia Crew board without raw curl calls. |

---

## Workspace Directory Map

```
workspace/
├── tasks/
│   ├── inbox/      ← New tasks from Founder (via Telegram)
│   ├── active/     ← Tasks being worked on
│   ├── creative/   ← Tasks queued for Muse
│   ├── technical/  ← Tasks queued for Arch
│   ├── admin/      ← Tasks queued for Sage
│   ├── blocked/    ← Waiting for Founder input
│   └── done/       ← Completed tasks (archived)
├── outputs/
│   ├── creative/   ← Muse's deliverables
│   ├── technical/  ← Arch's deliverables
│   ├── pm/         ← Navi's deliverables
│   └── admin/      ← Sage's deliverables
└── comms/
    ├── to-founder/     ← Agent → Founder (watched by Telegram bridge)
    ├── from-founder/   ← Founder → Agents (replies via Telegram)
    ├── inter-agent/    ← Agent-to-agent file handoffs
    └── STOP            ← Drop this file to halt all loops
```
