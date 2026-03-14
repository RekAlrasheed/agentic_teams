# Navaia AI Workforce OS

An autonomous AI workforce system where 4 specialized agents (PM, Creative, Technical, Admin) operate as a coordinated team using Claude Code Agent Teams. The agents work 24/7 on tasks received via Telegram, track everything on Trello, and leverage a shared company knowledge base — all running on a Claude Max subscription with zero infrastructure cost.

---

## Quick Start

### Prerequisites
- **Claude Max subscription** (for Claude Code access)
- **Claude Code CLI** (`npm install -g @anthropic-ai/claude-code`)
- **Python 3.10+**
- **tmux** (`brew install tmux`)

### Setup (15 minutes)

```bash
# 1. Clone the repo
git clone https://github.com/RekAlrasheed/agentic_teams.git
cd agentic_teams

# 2. Copy environment template and fill in your API keys
cp .env.example .env
# Edit .env with your keys (Telegram, Trello, GitHub, AWS)

# 3. Run first-time setup
bash scripts/setup.sh

# 4. Add your company files to knowledge/
# (pitch deck, brand guide, contracts, financials, etc.)

# 5. Start the crew
# Single session:
bash scripts/start.sh

# 24/7 mode (recommended — run in tmux):
tmux new -s navaia
bash scripts/loop.sh
```

---

## How It Works

```
┌──────────┐    Telegram    ┌──────────────┐
│          │ ──────────────→ │   Telegram   │
│ Manager  │                 │   Bridge     │
│ (Mobile) │ ←────────────── │  (Python)    │
└──────────┘                 └──────┬───────┘
                                    │ filesystem
                             ┌──────┴───────┐
                             │  Navi (PM)   │
                             │  Team Lead   │
                             └──┬───┬───┬───┘
                                │   │   │
                    ┌───────────┘   │   └───────────┐
                    │               │               │
              ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐
              │   Muse    │  │   Arch    │  │   Sage    │
              │ Creative  │  │ Technical │  │   Admin   │
              └───────────┘  └───────────┘  └───────────┘
                    │               │               │
              ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐
              │  Content  │  │   Code    │  │   Docs    │
              │  Emails   │  │  Deploy   │  │  Finance  │
              │  Social   │  │   Infra   │  │ Research  │
              └───────────┘  └───────────┘  └───────────┘
```

1. **Manager** sends a task via Telegram
2. **Telegram Bridge** saves the message as a file in `workspace/tasks/inbox/`
3. **Navi (PM)** picks up the task, breaks it down, and assigns to the right agent(s)
4. **Agents** work in parallel, saving outputs to `workspace/outputs/`
5. **Navi** reviews output, updates Trello, and reports back via Telegram

---

## Controlling via Telegram

### Sending Tasks
Just send a text message to your bot. Examples:
- "Write 3 cold outreach emails for SaaS founders in Saudi"
- "Deploy the new landing page to production"
- "Create a budget forecast for Q2 2026"
- "Research competitors in the AI workforce space in MENA"

### Commands
- `/status` — Get task counts (inbox, active, done, blocked)
- `/stop` — Gracefully stop the workforce

### Approving Plans
For complex tasks, Navi will send a plan for approval. Reply with:
- "Approved" or "Go ahead" — proceed with the plan
- "Change X to Y" — modify the plan
- "Cancel" — cancel the task

---

## Monitoring on Trello

Board: **Navaia Crew**

| List | Meaning |
|------|---------|
| Inbox | New tasks just received |
| Planning | PM is breaking down the task |
| To Do | Ready to be picked up |
| In Progress | Agent actively working |
| Review | PM reviewing output |
| Done | Completed and approved |
| Blocked | Waiting for Manager input |
| Rejected | Needs rework |

**Labels:** PM (blue), Creative (orange), Technical (purple), Admin (green)

---

## Repo Structure

```
navaia/
├── CLAUDE.md                ← Master config (PM reads on startup)
├── VISION.md                ← Full architecture roadmap
├── README.md                ← This file
├── .env.example             ← API key template
├── agents/                  ← Agent identity files
│   ├── pm/CLAUDE.md         ← Navi (PM)
│   ├── creative/CLAUDE.md   ← Muse (Creative)
│   ├── technical/CLAUDE.md  ← Arch (Technical)
│   └── admin/CLAUDE.md      ← Sage (Admin)
├── knowledge/               ← Company brain (your files go here)
│   ├── INDEX.md             ← Auto-generated catalog
│   ├── company/             ← Pitch deck, brand guide, team
│   ├── sales/               ← Proposals, pricing, case studies
│   ├── products/            ← Product documentation
│   ├── finance/             ← Budgets, invoices
│   ├── legal/               ← Contracts, NDAs
│   ├── marketing/           ← Campaigns, content calendar
│   ├── technical/           ← Architecture, API docs
│   ├── hr/                  ← Job descriptions, policies
│   └── templates/           ← Reusable document templates
├── workspace/               ← Active work area
│   ├── tasks/               ← inbox/, active/, done/, rejected/
│   ├── outputs/             ← creative/, technical/, admin/
│   └── comms/               ← to-manager/, from-manager/, inter-agent/
├── tools/                   ← Integration scripts
│   ├── telegram_bridge.py   ← Telegram ↔ filesystem bridge
│   ├── trello_api.sh        ← Trello helper functions
│   ├── catalog.py           ← Knowledge base auto-cataloger
│   └── requirements.txt     ← Python dependencies
└── scripts/                 ← Startup and management
    ├── setup.sh             ← First-time setup
    ├── start.sh             ← Single session launcher
    └── loop.sh              ← 24/7 auto-restart loop
```

---

## Adding Knowledge Files

1. Add files to the appropriate folder in `knowledge/`:
   - Company docs → `knowledge/company/`
   - Sales materials → `knowledge/sales/`
   - Product docs → `knowledge/products/`
   - Financial data → `knowledge/finance/`
   - Legal docs → `knowledge/legal/`
   - Marketing assets → `knowledge/marketing/`
   - Tech docs → `knowledge/technical/`
   - HR files → `knowledge/hr/`
   - Templates → `knowledge/templates/`

2. Regenerate the index:
   ```bash
   python3 tools/catalog.py
   ```

The agents will automatically discover new files via `knowledge/INDEX.md`.

---

## Full Roadmap

See [VISION.md](VISION.md) for the complete architecture roadmap, including:
- Phase 0: Local machine (current)
- Phase 1: Cloud deployment on AWS
- Phase 2: Multi-engine SaaS platform
- 12-week implementation timeline
