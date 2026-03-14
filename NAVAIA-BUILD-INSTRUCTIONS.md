# NAVAIA AI WORKFORCE — BUILD INSTRUCTIONS

You are setting up an AI Workforce Operating System for Navaia, a Saudi Arabia-based startup. This document tells you EVERYTHING you need to build. Read it fully before writing any code.

---

## WHAT YOU'RE BUILDING

A system where 4 AI agents (PM, Creative, Technical, Admin) run as a coordinated team using Claude Code Agent Teams. The agents work autonomously 24/7 on the Manager's machine using a Claude Max subscription. The Manager controls everything via Telegram and monitors tasks on Trello.

### The Agents

1. **PM Agent — "Navi"** (Team Lead, runs on Opus)
   - Receives tasks from the Manager via Telegram
   - Breaks down complex tasks into subtasks
   - Assigns work to the right teammate
   - Reviews all output before marking complete
   - Updates Trello with every status change
   - Reports back to the Manager on Telegram
   - For simple tasks: handles them directly or routes to a cheaper model (Sonnet/Haiku)

2. **Creative & Marketing Agent — "Muse"** (Teammate, runs on Sonnet)
   - Marketing content: blog posts, social media, newsletters
   - Email campaigns: cold outreach templates, follow-up sequences
   - Pitch decks and one-pagers
   - Brand voice enforcement
   - LinkedIn content
   - Design briefs
   - Bilingual content (English + Arabic for Saudi market)

3. **Technical Agent — "Arch"** (Teammate, runs on Opus)
   - Code: features, bug fixes, refactors across all Navaia repos
   - Deployments to staging and production
   - Infrastructure management on AWS (EC2, S3, RDS)
   - API integrations (WhatsApp Business API, Telegram, SendGrid, etc.)
   - Site updates on production websites
   - GitHub management: branches, PRs, code review
   - Has access to all Navaia GitHub repos and AWS

4. **Admin & Finance Agent — "Sage"** (Teammate, runs on Sonnet)
   - Documents: proposals, contracts, MOUs, NDAs, invoices
   - Financial tracking: expenses, revenue, budgets
   - Research: market research, competitor analysis, stakeholder profiling
   - Data analysis: Excel/CSV work, reports
   - Saudi compliance: CR, GOSI, VAT, PDPL
   - HR: job descriptions, offer letters

---

## REPO STRUCTURE TO CREATE

Create this exact structure in the repo. This is a monorepo — everything lives here.

```
navaia/
│
├── CLAUDE.md                    ← YOU ARE HERE — master config the PM reads on startup
├── VISION.md                    ← Full architecture roadmap (create from Section 11 below)
├── README.md                    ← Setup guide
├── .env.example                 ← Template for API keys
├── .gitignore
│
├── agents/                      ← Each agent's identity and instructions
│   ├── pm/
│   │   └── CLAUDE.md            ← Navi's full instructions
│   ├── creative/
│   │   └── CLAUDE.md            ← Muse's full instructions
│   ├── technical/
│   │   └── CLAUDE.md            ← Arch's full instructions
│   └── admin/
│       └── CLAUDE.md            ← Sage's full instructions
│
├── knowledge/                   ← THE COMPANY BRAIN — all Navaia files
│   ├── INDEX.md                 ← Auto-generated catalog of every file (see Section 6)
│   ├── company/                 ← About Navaia: pitch deck, brand guide, team
│   ├── sales/                   ← Proposals, pricing, case studies
│   │   ├── proposals/
│   │   ├── pricing/
│   │   └── case-studies/
│   ├── products/                ← Product docs
│   │   ├── baian/               ← WhatsApp bot documentation
│   │   └── ai-workforce/       ← The AI Workforce OS product
│   ├── finance/                 ← Budgets, invoices, expense tracking
│   ├── legal/                   ← Contracts, NDAs, CR docs
│   ├── marketing/               ← Campaigns, content calendar, assets
│   ├── technical/               ← Architecture docs, API docs
│   ├── hr/                      ← Job descriptions, policies
│   └── templates/               ← Reusable document templates
│       ├── proposal-template.docx
│       ├── email-templates/
│       └── contract-template.docx
│
├── workspace/                   ← Active work area (agents read/write here)
│   ├── tasks/
│   │   ├── inbox/               ← New tasks from Manager (via Telegram)
│   │   ├── active/              ← Currently being worked on
│   │   ├── done/                ← Completed tasks
│   │   └── rejected/           ← Rejected tasks
│   ├── outputs/                 ← Final deliverables
│   │   ├── creative/
│   │   ├── technical/
│   │   └── admin/
│   └── comms/
│       ├── to-manager/          ← Messages TO Manager (sent via Telegram)
│       ├── from-manager/        ← Messages FROM Manager (received via Telegram)
│       └── inter-agent/         ← Agent-to-agent file handoffs
│
├── tools/                       ← Integration scripts
│   ├── telegram_bridge.py       ← Telegram ↔ filesystem bridge (see Section 4)
│   ├── trello_api.sh            ← Trello helper functions (see Section 5)
│   ├── catalog.py               ← Auto-cataloger for knowledge/ files (see Section 6)
│   └── requirements.txt
│
└── scripts/                     ← Startup and management
    ├── start.sh                 ← Single session launcher
    ├── loop.sh                  ← 24/7 auto-restart loop
    └── setup.sh                 ← First-time setup script
```

---

## SECTION 1: CLAUDE.md (MASTER CONFIG)

This is the most important file. The PM agent reads this on every startup. Write it with these rules:

### Agent Behavior Rules

1. **NEVER ask anything in the terminal.** All questions go to Telegram via `workspace/comms/to-manager/` files. The system runs with `--dangerously-skip-permissions` so the terminal is non-interactive.

2. **ALWAYS propose a plan before executing complex tasks.**
   - When the Manager sends a new task, the PM breaks it down into subtasks
   - PM writes the plan to `workspace/comms/to-manager/plan-{timestamp}.md`
   - PM waits for the Manager's approval in `workspace/comms/from-manager/` before proceeding
   - For simple tasks (under 5 minutes of work), just execute immediately

3. **If you can't do something as requested — STOP and ASK.**
   - Do NOT substitute a different approach without permission
   - Do NOT skip steps because they're hard
   - Do NOT do a "simplified version" unless the Manager explicitly says so
   - Write to Telegram: "I can't do X because Y. Options: A, B, or C?"

4. **Update Trello for EVERY task state change.** The Manager monitors Trello. It must always reflect the real status of all work.

5. **Agents work in PARALLEL.** When the PM assigns tasks to multiple teammates, they should all work simultaneously. Don't serialize work that can be parallelized.

### Token Cost Management Rules

This is critical — the system runs on a Max subscription with rolling usage limits.

1. **PM routes simple tasks to itself using cheaper models when possible.** Simple lookups, formatting, quick answers — don't spawn a teammate for these. The PM handles them directly.

2. **Teammates use the minimum model needed:**
   - Creative (Muse): Sonnet 4.5 for content writing. Only escalate to Opus if doing complex strategy work.
   - Technical (Arch): Opus 4.6 for architecture decisions and complex code. Sonnet for routine code changes, simple bug fixes.
   - Admin (Sage): Sonnet 4.5 for documents and research. Haiku for simple lookups and formatting.

3. **Avoid unnecessary context.** Don't dump the entire knowledge base into every prompt. Load only the files relevant to the current task.

4. **Be concise in inter-agent messages.** Short status updates, not essays. Save tokens for actual work.

5. **If rate-limited:** The PM should notify the Manager on Telegram ("⏸️ Rate limited. Resuming in ~X minutes."), pause non-urgent work, and prioritize the most important active task when usage resets.

### Task Routing Table

The PM uses this to decide where tasks go:

| Task Type | Route To | Model Priority |
|-----------|----------|---------------|
| Content, copy, social media, campaigns | Creative (Muse) | Sonnet first |
| Code, deploy, debug, infrastructure, APIs | Technical (Arch) | Opus for complex, Sonnet for routine |
| Documents, proposals, research, finance, Excel | Admin (Sage) | Sonnet first |
| Multi-step projects spanning agents | Multiple teammates in parallel | Mixed |
| Simple lookups, quick formatting, Q&A | PM handles directly | Haiku/Sonnet |
| Strategic planning, architecture decisions | PM + relevant teammate | Opus |

### Trello Integration

Board name: **Navaia Crew**

Lists (in order):
- **Inbox** — New tasks just received
- **Planning** — PM is breaking down the task
- **To Do** — Ready to be picked up by an agent
- **In Progress** — Agent actively working
- **Review** — PM reviewing the output
- **Done** — Completed and approved
- **Blocked** — Waiting for Manager input
- **Rejected** — Manager rejected, needs rework

Labels (one per agent): PM (blue), Creative (orange), Technical (purple), Admin (green)

Every card has: title, description, agent label, checklist of subtasks if applicable.

Agents update cards by calling the Trello API via bash (using helpers in `tools/trello_api.sh`).

### Telegram Communication Protocol

**Receiving tasks from Manager:**
- New tasks appear as files in `workspace/tasks/inbox/` (created by the Telegram bridge)
- PM checks this folder on startup and periodically
- Each file contains the task text, timestamp, and source

**Sending messages to Manager:**
- Write a markdown file to `workspace/comms/to-manager/`
- Filename format: `{YYYYMMDD-HHMMSS}-{topic}.md`
- The Telegram bridge watches this folder and sends new files to the Manager
- Keep messages concise — the Manager reads on mobile

**Message format:**
```markdown
## [STATUS UPDATE | QUESTION | PLAN APPROVAL | BLOCKER | COMPLETED]

{Your message}

**Task:** {task name}
**Agent:** {who's working on it}
**Trello:** {card ID or link}
```

**Receiving Manager replies:**
- Replies appear in `workspace/comms/from-manager/`
- Check this folder when waiting for approval

### Team Spawn Instructions

On startup, the PM spawns teammates with these instructions:

```
Create an agent team. You are the lead (Navi, PM Agent).

Spawn 3 teammates:

1. Name: "Muse" (Creative & Marketing)
   Instructions: Read agents/creative/CLAUDE.md for your full role and skills.
   You handle all content, marketing, campaigns, pitch materials, and outreach copy.
   Save outputs to workspace/outputs/creative/.
   Report progress to the lead.
   Use Sonnet-tier reasoning — save Opus for complex strategy only.

2. Name: "Arch" (Technical)
   Instructions: Read agents/technical/CLAUDE.md for your full role and skills.
   You handle all code, deployments, infrastructure, and API integrations.
   You have access to GitHub repos and AWS.
   Save outputs to workspace/outputs/technical/.
   Report progress to the lead.

3. Name: "Sage" (Admin & Finance)
   Instructions: Read agents/admin/CLAUDE.md for your full role and skills.
   You handle documents, proposals, research, finance tracking, and compliance.
   Save outputs to workspace/outputs/admin/.
   Report progress to the lead.
   Use Sonnet-tier reasoning — save Opus for complex analysis only.

All teammates:
- Read knowledge/INDEX.md to understand what company files are available
- Check workspace/tasks/ for assigned work
- Communicate through the shared task list and teammate messaging
- NEVER ask questions in the terminal — route all Manager questions through the lead
- Update Trello via tools/trello_api.sh when you start/finish tasks
```

---

## SECTION 2: AGENT CLAUDE.md FILES

Create a dedicated CLAUDE.md for each agent in their respective `agents/{name}/` folder. Each file should include:

1. **Identity** — Name, role, model preference
2. **Core responsibilities** — Detailed list of what they do
3. **Skills & expertise** — What they're good at
4. **Tools they can use** — Git, curl, Python, npm, etc.
5. **Working standards** — Quality expectations, file naming, output format
6. **File organization** — Where they save outputs
7. **Access & permissions** — What repos, services, APIs they can touch

Key details per agent:

**Creative (Muse):**
- Copywriting, SEO, email marketing, social media strategy
- Brand voice: professional but approachable, tech-forward, solution-focused
- Target audience: startup founders and SMBs in Saudi Arabia / MENA
- Always provide 2-3 variations for key copy (subject lines, headlines, CTAs)
- No generic AI-sounding copy — write like a human
- Can create markdown, HTML, slides, content calendars
- Bilingual: English and Arabic

**Technical (Arch):**
- Full-stack: React/Next.js, Python/FastAPI, Node.js
- AWS: EC2, ECS, Lambda, RDS, S3, CloudFront
- Docker, CI/CD (GitHub Actions), database design
- Git workflow: always branch, never commit to main directly
- Write tests for critical paths
- For first-time production changes: get PM approval
- If deployment fails: rollback immediately, notify PM
- Has access to all Navaia GitHub repos (list them in the file) and AWS console via CLI

**Admin (Sage):**
- Business documents: proposals, contracts, MOUs, NDAs, invoices
- Financial: expense tracking, budgets, revenue forecasting in SAR
- Research: market analysis, competitor profiling, stakeholder mapping
- Excel mastery: formulas, pivot tables, charts
- Saudi compliance: CR, GOSI, VAT (15%), PDPL data privacy
- Flags legal issues but doesn't give legal advice
- All financial tracking in SAR

---

## SECTION 3: STARTUP SCRIPTS

### scripts/setup.sh (First-time setup)

This script runs once when the Manager first clones the repo. It should:

1. Check prerequisites: Claude Code CLI installed, Python 3.10+, tmux, pip
2. Install Python dependencies from `tools/requirements.txt`
3. Copy `.env.example` to `.env` if it doesn't exist, prompt to fill in keys
4. Create all workspace directories
5. Set up the Trello board (create lists and labels via API) using `tools/trello_api.sh`
6. Verify Telegram bot connectivity (send a test message)
7. Run `tools/catalog.py` to generate initial `knowledge/INDEX.md`
8. Print success message with next steps

### scripts/start.sh (Single session)

1. Source `.env`
2. Preflight: check all required env vars are set, Claude Code available, tmux available
3. Start Telegram bridge (`tools/telegram_bridge.py`) in background
4. Set `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`
5. Launch Claude Code with `--dangerously-skip-permissions` and an initial prompt that tells the PM to:
   - Read CLAUDE.md
   - Check inbox for pending tasks
   - Spawn teammates
   - Send status update to Manager on Telegram
6. On exit: kill the Telegram bridge process

### scripts/loop.sh (24/7 mode)

1. Start Telegram bridge once
2. In a while loop:
   - Check for STOP signal file (`workspace/comms/STOP`) — if found, halt
   - Launch Claude Code with `--dangerously-skip-permissions` and a resume prompt
   - When session ends (rate limit, completion, error): wait 30 seconds, restart
   - Increment session counter
   - Safety: stop after 200 restarts (configurable)
3. On Ctrl+C or STOP signal: clean up Telegram bridge, exit gracefully

The resume prompt should tell the PM:
- "A previous session ended. This is normal — sessions are ephemeral."
- "Check inbox for new tasks, check active for in-progress work"
- "Spawn teammates if needed, send status update, keep working"
- Include the session number so the PM can reference it

---

## SECTION 4: TELEGRAM BRIDGE

Create `tools/telegram_bridge.py` — a Python script that runs alongside Claude Code and bridges Telegram messages to the filesystem.

### How it works:

**Telegram → Filesystem (Manager sends a message):**
1. Manager sends a message to the Telegram bot
2. Script saves it as a markdown file in `workspace/tasks/inbox/` (for new tasks) or `workspace/comms/from-manager/` (for replies)
3. File format:
```markdown
## NEW TASK FROM FOUNDER
**Time:** 2026-03-06T14:30:00Z
**Source:** Telegram

{the message text}
```

**Filesystem → Telegram (Agent sends a message to Manager):**
1. Uses `watchdog` library to monitor `workspace/comms/to-manager/` for new files
2. When a new .md file appears, read its content
3. Send it to the Manager's Telegram chat
4. Truncate if over 4000 chars (Telegram limit) with a note that full message is in the file

### Commands the Manager can use:
- Any text message → saved as a new task
- `/status` → returns count of tasks in each state (inbox, active, done, blocked)
- `/stop` → creates a STOP signal file that the loop script checks

### Requirements:
- `python-telegram-bot` for Telegram API
- `watchdog` for filesystem monitoring
- `python-dotenv` for .env loading

### Security:
- Only respond to messages from `TELEGRAM_FOUNDER_CHAT_ID`
- Reject all other chat IDs with "Unauthorized"

---

## SECTION 5: TRELLO INTEGRATION

Create `tools/trello_api.sh` — a bash script with helper functions that agents source and call.

### Functions needed:

```
trello_setup_board      — Create all lists and labels on the board (run once)
trello_get_list_id      — Get a list's ID by name
trello_get_label_id     — Get a label's ID by name
trello_create_card      — Create a card in a specific list with optional label
trello_move_card        — Move a card to a different list
trello_comment          — Add a comment to a card
trello_add_checklist    — Add a checklist with items to a card
trello_list_cards       — List all cards in a specific list
trello_status           — Print a summary of card counts per list
```

All functions use curl to call the Trello REST API with key/token from `.env`.

### How agents use it:

```bash
# PM creates a task card
source tools/trello_api.sh
CARD_ID=$(trello_create_card "To Do" "Write outreach emails" "Create 3 email templates for SaaS founders" "Creative")

# Creative agent picks it up
trello_move_card "$CARD_ID" "In Progress"
trello_comment "$CARD_ID" "Starting work on email templates"

# Creative finishes
trello_move_card "$CARD_ID" "Review"
trello_comment "$CARD_ID" "3 templates ready in workspace/outputs/creative/emails/"

# PM reviews and approves
trello_move_card "$CARD_ID" "Done"
```

---

## SECTION 6: KNOWLEDGE BASE AUTO-CATALOGER

Create `tools/catalog.py` — a Python script that scans `knowledge/` and generates `knowledge/INDEX.md`.

### What it does:

1. Walks through every file in `knowledge/` recursively
2. For each file, records:
   - **Path**: relative path from repo root
   - **Category**: derived from folder name (company, sales, products, etc.)
   - **Type**: file extension and size
   - **Summary**: a brief description. For text files (.md, .txt, .csv), read the first ~500 chars and summarize. For binary files (.pdf, .xlsx, .pptx, .docx), note the file type and size.
   - **Use when**: which agents would typically need this file and for what purpose
   - **Language**: English, Arabic, or Bilingual (detect from content if text)
   - **Last modified**: file modification timestamp
3. Outputs `knowledge/INDEX.md` with all entries sorted by category

### INDEX.md format:

```markdown
# NAVAIA KNOWLEDGE BASE INDEX

> Auto-generated by tools/catalog.py
> Last updated: 2026-03-06T14:30:00Z
> Total files: 47

## Quick Reference by Agent

### For Creative Agent (Muse)
- knowledge/company/brand-guidelines.md — Brand voice and visual identity
- knowledge/marketing/content-calendar.xlsx — Current content schedule
- knowledge/templates/email-templates/ — Outreach email templates

### For Technical Agent (Arch)
- knowledge/technical/architecture.md — System architecture docs
- knowledge/products/baian/api-docs.md — WhatsApp bot API reference

### For Admin Agent (Sage)
- knowledge/finance/budget-2026.xlsx — Current year budget
- knowledge/legal/nda-template.docx — Standard NDA template
- knowledge/templates/proposal-template.docx — Client proposal template

---

## Full Catalog

### company/

#### knowledge/company/pitch-deck.pptx
- **Category:** Company
- **Type:** PowerPoint (2.4 MB, 15 slides)
- **Summary:** Navaia investor pitch deck. Covers problem, solution, market size, business model, team, and ask.
- **Use when:** Creative agent preparing investor materials. Admin agent referencing company positioning. Sales outreach requiring company overview.
- **Language:** English
- **Last modified:** 2026-02-15

(... more entries ...)
```

### When to run:
- First time during `scripts/setup.sh`
- Whenever the Manager adds new files to `knowledge/`
- The PM can trigger it by running `python tools/catalog.py`

---

## SECTION 7: .env.example

```
# ── Telegram Bridge ──────────────────────
TELEGRAM_BOT_TOKEN=           # From @BotFather
TELEGRAM_FOUNDER_CHAT_ID=     # From @userinfobot

# ── Trello ───────────────────────────────
TRELLO_KEY=                   # From https://trello.com/app-key
TRELLO_TOKEN=                 # Authorize at the link on that page
TRELLO_BOARD_ID=              # From the board URL

# ── GitHub ───────────────────────────────
GITHUB_TOKEN=                 # Personal access token with repo scope

# ── AWS (for Technical Agent) ────────────
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=me-south-1  # Bahrain region (closest to Saudi)

# ── Navaia Services ──────────────────────
WHATSAPP_API_TOKEN=           # WhatsApp Business API token (Baian)
SENDGRID_API_KEY=             # For email outreach
```

---

## SECTION 8: .gitignore

```
.env
__pycache__/
*.pyc
node_modules/
.DS_Store
*.log

# Don't commit active workspace files (they're ephemeral)
workspace/tasks/inbox/*
workspace/tasks/active/*
workspace/comms/to-manager/*
workspace/comms/from-manager/*
workspace/comms/inter-agent/*
workspace/comms/STOP

# Keep the directory structure
!workspace/**/.gitkeep

# Don't commit large binary outputs (commit to separate branch or S3 if needed)
workspace/outputs/**/*.xlsx
workspace/outputs/**/*.pptx
workspace/outputs/**/*.pdf
```

---

## SECTION 9: README.md

Write a clear README with:

1. **What this is** — one paragraph explaining the AI Workforce concept
2. **Quick Start** — numbered steps to get running in 15 minutes:
   - Prerequisites (Claude Max, Claude Code CLI, Python, tmux)
   - Clone repo
   - Copy .env.example → .env, fill in keys
   - Run `scripts/setup.sh`
   - Add company files to `knowledge/`
   - Run `scripts/loop.sh` in tmux
3. **How it works** — simple diagram showing Manager → Telegram → PM → Teammates
4. **Controlling via Telegram** — what commands work, how to send tasks, how to approve plans
5. **Monitoring on Trello** — what the board looks like, what each list means
6. **Repo structure** — quick reference of what's where
7. **Adding knowledge files** — how to add new files and regenerate the index
8. **Full roadmap** — link to VISION.md

---

## SECTION 10: IMPORTANT IMPLEMENTATION DETAILS

### Parallel Agent Execution
Agent Teams teammates work in parallel by default. When the PM assigns 3 tasks to 3 different agents, they all start simultaneously. Use the shared task list for coordination — each teammate claims a task, works on it, and marks it complete. The PM monitors progress.

### Avoiding Waste
- Don't load knowledge/INDEX.md into every agent's context on every task. The PM reads the index, identifies which files are relevant, and only tells the teammate which specific files to read.
- Agents should NOT re-read CLAUDE.md on every message. They read it once on spawn.
- Status updates to Telegram should be batched — don't send 10 messages for 10 small updates. Batch into one summary every 10-15 minutes during active work.

### Error Recovery
- If a teammate crashes or gets stuck, the PM should note the failure on Trello, attempt to re-assign the task, and notify the Manager only if it fails twice.
- If the Trello API fails (rate limit, bad auth), log the error and continue. Don't block real work because of a tracking tool failure.
- If the Telegram bridge is down, write messages to `workspace/comms/to-manager/` anyway. They'll be sent when the bridge comes back up.

### File Handoffs Between Agents
When one agent produces output that another agent needs:
1. Save the file to `workspace/comms/inter-agent/{from}-to-{to}-{topic}.md`
2. Message the receiving agent via Agent Teams messaging
3. The receiving agent reads the file and proceeds

Example: Creative writes email templates → saves to inter-agent → messages Arch → Arch integrates into SendGrid.

### Access to Navaia Repos and Services
- Technical agent (Arch) has full access to GitHub repos via `GITHUB_TOKEN`
- Arch can SSH into EC2 instances, run AWS CLI commands, push deployments
- All agents can read knowledge/ files for company context
- Baian (WhatsApp bot) is accessible via `WHATSAPP_API_TOKEN`
- Email sending is via SendGrid API
- The PM should explicitly grant or deny access when assigning sensitive tasks

---

## SECTION 11: VISION.md

Create VISION.md as a roadmap document containing the full architecture we're eventually building toward. Include:

### Phase 0 (Current) — Claude Max on Local Machine
- 4 agents via Agent Teams on Manager's machine
- Telegram bridge for communication
- Trello for task management
- Max subscription, no extra infrastructure cost

### Phase 1 — Cloud Deployment
- Move to EC2 (single t3.xlarge or m6i.xlarge instance, ~$85-140/month)
- Claude agents run via API keys (pay-per-token) instead of Max subscription
- Add OpenClaw for always-on channel agents (Telegram bot, WhatsApp, Outreach)
- FastAPI orchestrator connects both engines
- Redis Streams for inter-agent messaging
- Weaviate vector DB for semantic search and RAG
- PostgreSQL for structured data and audit trail
- Docker Compose for container management

### Phase 2 — Multi-Engine Scaled Architecture
- Split into 3 EC2 instances (core, OpenClaw isolated, optional GPU)
- Customer-facing products: WhatsApp (Baian), Call Center (Vapi/Twilio), HR Recruiter
- Multi-tenant isolation for customer data
- SaaS pricing: 1,000 SAR basic, 2,500 SAR pro, 5,000 SAR premium per month
- Next.js monitoring dashboard

### Model Routing Strategy
| Agent | Phase 0 Model | Phase 1+ Model | Est. Daily Cost (Phase 1) |
|-------|--------------|----------------|--------------------------|
| PM (Navi) | Opus 4.6 (Max) | Opus 4.6 (API) | ~$8 |
| Technical (Arch) | Opus 4.6 (Max) | Opus 4.6 (API) | ~$10 |
| Creative (Muse) | Sonnet 4.5 (Max) | Sonnet 4.5 (API) | ~$4 |
| Admin (Sage) | Sonnet 4.5 (Max) | Sonnet 4.5 (API) | ~$3 |
| Telegram Bot | N/A | GPT-4o (OpenClaw) | ~$2 |
| Outreach | N/A | Llama 3.3 70B self-hosted | ~$0 |
| WhatsApp (Baian) | N/A | GPT-4o (OpenClaw) | ~$3 |
| Call Center | N/A | Configurable | Varies |
| HR Recruiter | N/A | Sonnet/GPT-4o | ~$4 |

### Full Tech Stack (Phase 1+)
- Engines: Claude Agent SDK + OpenClaw
- Backend: FastAPI + Python
- Vector DB: Weaviate
- Structured DB: PostgreSQL (AWS RDS)
- Message Bus: Redis Streams
- Task Management: Trello (Phase 0), Linear (Phase 1+)
- Infrastructure: AWS ECS Fargate, Lambda, S3
- Dashboard: Next.js
- Channels: Telegram, WhatsApp Business API, Vapi/Twilio, SendGrid
- Model Gateway: LiteLLM or OpenRouter

### 12-Week Implementation Roadmap
Include the week-by-week plan from Phase 0 through Phase 2 product launch.

---

## SECTION 12: AFTER BUILDING

Once you've created all files:

1. Initialize the git repo: `git init && git add . && git commit -m "Initial commit: Navaia AI Workforce OS"`
2. Run `tools/catalog.py` to generate the initial (empty) knowledge index
3. Run `scripts/setup.sh` to verify everything works
4. Print a summary of what was created and what the Manager needs to do next:
   - Fill in .env with actual API keys
   - Add company files to knowledge/
   - Create the Telegram bot via @BotFather
   - Create the Trello board
   - Run `scripts/loop.sh` to start the crew

---

## IMPORTANT: BUILD ALL OF THIS AS WORKING CODE

Do not create placeholder files. Do not write "TODO" comments. Every script should be functional. The Telegram bridge should actually connect to Telegram. The Trello helpers should actually call the Trello API. The catalog script should actually scan and index files. The startup scripts should actually launch Claude Code with the right flags.

Test each script after writing it (where possible without actual API keys). Handle errors gracefully. Log clearly.

The Manager should be able to clone this repo, fill in .env, run setup.sh, and have a working AI workforce within 15 minutes.
