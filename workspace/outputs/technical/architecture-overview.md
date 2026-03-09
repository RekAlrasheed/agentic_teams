# Navaia AI Workforce — Technical Architecture Overview

**Author:** Arch (Technical Agent)
**Date:** 2026-03-08
**Status:** Internal reference document

---

## 1. System Overview

The Navaia AI Workforce is a four-agent autonomous system built on top of Claude Code (Anthropic). The Founder interacts exclusively via Telegram. Agents operate headlessly using the `--dangerously-skip-permissions` flag in ephemeral Claude Code sessions that auto-restart via a shell loop. The system is designed to run 24/7 in a tmux session on a local or cloud machine.

---

## 2. Folder Structure

```
agentic_teams/
├── CLAUDE.md                     # Master config — PM agent startup guide
├── VISION.md                     # Company vision and product context
├── NAVAIA-BUILD-INSTRUCTIONS.md  # Setup instructions for the system
├── README.md                     # Developer-facing README
├── .env                          # Secrets (never committed) — API keys
├── .env.example                  # Template for required environment variables
│
├── agents/                       # Per-agent role definitions
│   ├── pm/CLAUDE.md              # Navi — PM Agent instructions
│   ├── creative/CLAUDE.md        # Muse — Creative Agent instructions
│   ├── technical/CLAUDE.md       # Arch — Technical Agent instructions
│   └── admin/CLAUDE.md           # Sage — Admin Agent instructions
│
├── knowledge/                    # Read-only company knowledge base
│   ├── INDEX.md                  # Auto-generated catalog (via tools/catalog.py)
│   ├── company/                  # Company profiles, introductory materials
│   ├── finance/                  # ROI summaries, financial documents
│   ├── marketing/                # Agency portfolios, LinkedIn posts, campaigns
│   ├── products/                 # Baian (chat) and Bilal (voice) product docs
│   ├── sales/                    # CRM data, proposals, competitor analysis
│   ├── hr/                       # HR templates (currently empty)
│   ├── legal/                    # Legal templates (currently empty)
│   ├── technical/                # Technical references (currently empty)
│   └── templates/                # Document templates
│
├── tools/                        # Shared tooling used by agents and bridge
│   ├── telegram_bridge.py        # Telegram bot + filesystem watcher (Python)
│   ├── trello_api.sh             # Trello REST API helpers (Bash)
│   ├── catalog.py                # Generates knowledge/INDEX.md
│   └── requirements.txt          # Python dependencies
│
├── scripts/                      # Orchestration scripts
│   ├── loop.sh                   # Main 24/7 auto-restart loop
│   ├── start.sh                  # One-time startup helper
│   └── setup.sh                  # Initial environment setup
│
└── workspace/                    # Runtime state — all agent I/O
    ├── bot.log                   # Telegram bridge log
    ├── crew.log                  # Claude Code session log
    ├── comms/
    │   ├── to-founder/           # Agent-written messages → sent to Founder via Telegram
    │   ├── from-founder/         # Founder replies → read by PM agent
    │   ├── inter-agent/          # File handoffs between agents
    │   └── STOP                  # Sentinel file — triggers graceful shutdown
    ├── tasks/
    │   ├── inbox/                # New tasks from Founder (created by Telegram bridge)
    │   ├── active/               # Tasks currently being worked on
    │   ├── done/                 # Completed task records
    │   ├── blocked/              # Tasks awaiting Founder input
    │   └── rejected/             # Tasks rejected by Founder
    └── outputs/
        ├── creative/             # Muse's deliverables (blog posts, emails, etc.)
        ├── technical/            # Arch's deliverables (code, docs, patches)
        ├── admin/                # Sage's deliverables (proposals, budgets, research)
        └── pm/                   # Navi's deliverables (plans, analyses)
```

---

## 3. Agent Architecture

### Agent Roster

| Agent | Name | Model | Role |
|-------|------|-------|------|
| PM | Navi | Sonnet (Opus for complex coordination) | Team lead, task routing, QA, Founder comms |
| Creative | Muse | Sonnet (never Opus) | Content, marketing, campaigns, brand |
| Technical | Arch | Sonnet (Opus for architecture only) | Code, deployments, infra, APIs |
| Admin | Sage | Haiku/Sonnet (never Opus) | Docs, proposals, research, finance |

### Agent Instantiation

Agents are spawned by Navi using the Claude Code Agent Teams SDK (enabled via `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` env var). Each agent is a separate Claude Code subprocess with its own CLAUDE.md instructions. All agents run within the same session as Navi — they are not separate OS processes.

Each agent:
- Reads its own `agents/{role}/CLAUDE.md` on startup
- Reads `knowledge/INDEX.md` to understand available company files
- Writes outputs to `workspace/outputs/{role}/`
- Reports progress to Navi via the Agent Teams messaging system
- Updates Trello by sourcing `tools/trello_api.sh`

---

## 4. How Agents Communicate

### 4.1 Agent Teams Messaging (In-Session)

The primary inter-agent communication mechanism is the Claude Code Agent Teams SDK. Navi (PM) spawns teammates and exchanges messages with them directly through the SDK's SendMessage/TaskUpdate tools. This is real-time, in-process communication within a single Claude Code session.

- Navi assigns tasks to teammates via TaskUpdate (with `owner` field)
- Teammates report completion by messaging Navi
- Navi can broadcast to all teammates simultaneously
- Teammates go idle between turns — this is normal, they wake on message receipt

### 4.2 Filesystem File Handoffs (Cross-Agent, Async)

For structured data transfer between agents (e.g., Muse handing copy to Arch for deployment), the filesystem is used:

```
1. Sender writes:  workspace/comms/inter-agent/{from}-to-{to}-{topic}.md
2. Sender notifies recipient via Agent Teams messaging
3. Recipient reads the file and proceeds
```

This pattern is used when the handoff contains more data than fits cleanly in a message, or when the output needs to be a file artifact.

### 4.3 Founder Communication (Filesystem + Telegram)

Outbound (agent to Founder):
- Agent writes a `.md` file to `workspace/comms/to-founder/`
- Filename format: `{YYYYMMDD-HHMMSS}-{topic}.md`
- The `OutboxWatcher` in `telegram_bridge.py` detects the new file via `watchdog` and immediately sends its content to the Founder's Telegram chat

Inbound (Founder to agent):
- Founder sends a Telegram message
- The bridge processes it through Claude (Haiku model), which decides: `reply`, `create_task`, or `ask_clarification`
- If `create_task`: a task file is written to `workspace/tasks/inbox/` and the loop wakes up Claude Code
- Founder replies to agent questions are written to `workspace/comms/from-founder/`
- Navi checks `from-founder/` on each session start and when waiting for approval

---

## 5. How the Session Loop Works

The `scripts/loop.sh` is the runtime engine. It runs indefinitely (up to `MAX_RESTARTS=200`) in a tmux session.

### Loop Logic

```
1. Start Telegram bridge as a background process (once, not per loop)
2. Every iteration:
   a. Check workspace/comms/STOP — if present, halt
   b. Count files in: inbox/, active/, from-founder/
   c. If ALL counts are zero — sleep 60s and loop (no tokens burned)
   d. If work exists — launch Claude Code with a startup prompt
   e. Claude Code runs, completes work, exits
   f. Wait RESTART_DELAY (30s default) then loop
```

This design is token-cost-optimized: Claude Code is only launched when there is actual work to do. Idle periods cost nothing.

### Session Prompt

On session 1, Navi receives a STARTUP prompt. On subsequent sessions, it receives a RESUME prompt. Both instruct Navi to check for work and exit immediately if none is found.

The key env var is `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, which enables the Agent Teams SDK for spawning teammates.

---

## 6. Telegram Integration

**File:** `tools/telegram_bridge.py`
**Runtime:** Persistent Python process (started once by `loop.sh`)
**Libraries:** `python-telegram-bot`, `watchdog`, `asyncio`

### Architecture

The bridge has two main concerns running concurrently:

#### 6.1 Inbound: Founder -> System

```
Founder sends Telegram message
    → handle_message() receives it
    → ConversationMemory stores last 20 messages for context
    → ask_claude() is called:
        - Builds a system prompt with live state (task counts, Trello board, recent outputs)
        - Calls `claude -p <message> --model haiku --max-turns 1`
        - Parses JSON response: { action, message, task_title, ... }
    → If action = "create_task":
        - create_task_file() writes to workspace/tasks/inbox/{timestamp}-task.md
        - Trello card created in "Inbox" list
        - Confirmation written to workspace/comms/from-founder/
    → If action = "ask_clarification":
        - Pending task stored in ConversationMemory
        - Clarifying question sent back to Founder
    → If action = "reply":
        - Direct response sent back (no file created)
```

**Model used for bot responses:** Claude Haiku (`--model haiku`, `--max-turns 1`) — intentionally cheap, fast responses.

#### 6.2 Outbound: System -> Founder (File Watchers)

Three `watchdog` FileSystemEventHandlers run concurrently:

| Watcher | Watches | Action |
|---------|---------|--------|
| `OutboxWatcher` | `workspace/comms/to-founder/` | Sends new `.md` files as Telegram messages to Founder |
| `OutputWatcher` | `workspace/outputs/` (recursive) | Notifies Founder of new deliverable files with filename, size, and 3-line preview |
| `TaskDoneWatcher` | `workspace/tasks/done/` | Notifies Founder of task completion; attempts to auto-move matching Trello card to Done |

All watchers use a `_sent`/`_notified` set to prevent duplicate deliveries on re-events.

#### 6.3 Commands

| Command | Handler | Purpose |
|---------|---------|---------|
| `/status` | `handle_status` | Agent online/offline, task counts |
| `/board` | `handle_board` | Trello board summary |
| `/outputs` | `handle_outputs` | Recent deliverable files |
| `/clear` | `handle_clear` | Delete all inbox task files |
| `/stop` | `handle_stop` | Write STOP sentinel file to halt loop |
| `/help` | `handle_help` | Command reference |

#### 6.4 Authorization

All handlers check `is_authorized(chat_id)` against `TELEGRAM_FOUNDER_CHAT_ID` from `.env`. Any other chat ID is rejected immediately.

---

## 7. Trello Integration

**File:** `tools/trello_api.sh`
**Also implemented in:** `tools/telegram_bridge.py` (Python mirror of the same API)
**API:** Trello REST API v1 (`https://api.trello.com/1`)
**Auth:** Key + Token from `.env` — passed as query params on every request

### Board Structure

**Board name:** Navaia Crew

| List | Purpose |
|------|---------|
| Inbox | New tasks just received from Founder |
| Planning | PM breaking down the task |
| To Do | Ready for agent pickup |
| In Progress | Agent actively working |
| Review | PM reviewing output |
| Done | Completed and approved |
| Blocked | Waiting for Founder input |
| Rejected | Founder rejected, needs rework |

**Labels:** PM (blue), Creative (orange), Technical (purple), Admin (green)

### Shell API Functions (trello_api.sh)

Sourced by agents via `source tools/trello_api.sh`. Requires `.env` with `TRELLO_KEY`, `TRELLO_TOKEN`, `TRELLO_BOARD_ID`.

| Function | Signature | Purpose |
|----------|-----------|---------|
| `trello_setup_board` | `()` | One-time: creates all lists and labels |
| `trello_get_list_id` | `"List Name"` | Returns list ID by name |
| `trello_get_label_id` | `"Label Name"` | Returns label ID by name |
| `trello_create_card` | `"List" "Title" "Desc" "Label"` | Creates card, returns card ID |
| `trello_move_card` | `"card_id" "List Name"` | Moves card to target list |
| `trello_comment` | `"card_id" "comment"` | Adds comment to card |
| `trello_add_checklist` | `"card_id" "name" "item1"...` | Adds checklist with items |
| `trello_list_cards` | `"List Name"` | Prints cards in a list |
| `trello_status` | `()` | Prints card count per list |

All functions use `curl` for HTTP requests. List/label lookups are done with inline Python3 (`json.load(sys.stdin)`) to parse the JSON responses.

### Python Mirror (telegram_bridge.py)

`telegram_bridge.py` contains a parallel Python implementation of the Trello API for use by the bridge process:
- `trello_create_card()` — creates task cards when Founder triggers `create_task`
- `trello_move_card()` — used by `TaskDoneWatcher` to auto-move cards to Done
- `trello_comment()` — adds completion comments
- `trello_get_board_summary()` — returns compact board state string for the Claude system prompt

---

## 8. Cost Management Architecture

Token cost is treated as a first-class architectural concern:

- **Session gating:** The loop checks for work before launching Claude. Zero work = zero tokens.
- **Model tiers:** Haiku for simple bot responses and admin lookups, Sonnet for content/routine code, Opus only for complex architecture or multi-step coordination.
- **Exit-when-idle rule:** If Navi finds no tasks on startup, it exits immediately. The loop sleeps 60s and checks again.
- **Batching:** Telegram status updates are batched (max one per 10-15 minutes) rather than sent for every small update.
- **Minimal context loading:** Agents load only relevant knowledge files for their specific task, not the entire knowledge base.

---

## 9. Environment Variables

All secrets are stored in `.env` at the repo root. The `.env.example` file documents required variables.

| Variable | Used By | Purpose |
|----------|---------|---------|
| `TELEGRAM_BOT_TOKEN` | telegram_bridge.py | Telegram Bot API authentication |
| `TELEGRAM_FOUNDER_CHAT_ID` | telegram_bridge.py | Authorized user gate |
| `TRELLO_KEY` | trello_api.sh, telegram_bridge.py | Trello API key |
| `TRELLO_TOKEN` | trello_api.sh, telegram_bridge.py | Trello API token |
| `TRELLO_BOARD_ID` | trello_api.sh, telegram_bridge.py | Target Trello board |
| `GITHUB_TOKEN` | Arch agent (via bash) | GitHub repo access |
| `AWS_ACCESS_KEY_ID` | Arch agent (via bash) | AWS CLI access |
| `AWS_SECRET_ACCESS_KEY` | Arch agent (via bash) | AWS CLI access |
| `WHATSAPP_API_TOKEN` | Arch agent (via bash) | WhatsApp Business API |
| `SENDGRID_API_KEY` | Arch agent (via bash) | Email delivery |
| `MAX_RESTARTS` | loop.sh | Max Claude sessions (default: 200) |
| `RESTART_DELAY` | loop.sh | Seconds between sessions (default: 30) |

---

## 10. Known Limitations and Design Notes

- **Sessions are ephemeral:** Each Claude Code session has no persistent memory beyond what is written to the filesystem. State must be reconstructed from workspace files on every restart.
- **No agent persistence:** The Agent Teams SDK runs within a single Claude Code session. If Navi's session ends, all spawned teammates are also terminated. They are re-spawned fresh on the next session.
- **Inter-agent file handoffs are manual:** The `workspace/comms/inter-agent/` pattern requires agents to explicitly write and message each other. There is no automatic routing.
- **Trello API has no caching:** Every board operation makes a live HTTP call. List/label IDs are fetched on each operation rather than cached. This is acceptable at current task volume but would be inefficient at scale.
- **Telegram message length cap:** `TELEGRAM_MAX_LENGTH = 4000` characters. Long outputs are truncated with a notice. Large deliverables should be referenced by filename rather than pasted inline.
- **Single-founder authorization:** The system is designed for exactly one Founder. The chat ID check is a simple equality comparison.
