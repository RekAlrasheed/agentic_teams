# NAVAIA AI Workforce — Project Folder Structure
> Generated: 2026-03-08 | Agent: Arch (Technical)

```
agentic_teams/
├── .claude/
│   └── settings.local.json
├── .env
├── .env.example
├── .gitignore
├── .vscode/
│   └── tasks.json
├── CLAUDE.md                          # PM (Navi) master config
├── NAVAIA-BUILD-INSTRUCTIONS.md
├── README.md
├── VISION.md
│
├── agents/                            # Per-agent role instructions
│   ├── admin/
│   │   └── CLAUDE.md                  # Sage (Admin) role config
│   ├── creative/
│   │   └── CLAUDE.md                  # Muse (Creative) role config
│   ├── pm/
│   │   └── CLAUDE.md                  # Navi (PM) role config
│   └── technical/
│       └── CLAUDE.md                  # Arch (Technical) role config
│
├── knowledge/                         # Company knowledge base
│   ├── INDEX.md                       # Auto-generated file catalog
│   ├── company/
│   │   ├── introductory-flyer.pdf
│   │   ├── navaia-company-profile-ar.pdf
│   │   └── task-guide.xlsx
│   ├── finance/
│   │   └── navaia-roi-summary-ar.docx
│   ├── hr/                            # (empty)
│   ├── legal/                         # (empty)
│   ├── marketing/
│   │   ├── agencies/
│   │   │   ├── above-limits-portfolio.pdf
│   │   │   ├── above-web-sample.pdf
│   │   │   ├── arabi-company-profile-ar.pdf
│   │   │   ├── bab-agency-profile.pdf
│   │   │   ├── bab-packages-pricing-ar.pdf
│   │   │   ├── dunesberry-portfolio-2025.pdf
│   │   │   ├── marketing-companies.xlsx
│   │   │   ├── upgro-digital-pm.pdf
│   │   │   ├── upgro-profile-ar.pdf
│   │   │   └── upgro-profile-en.pdf
│   │   ├── exhibitions-and-visits.xlsx
│   │   └── linkedin-posts/
│   │       ├── post-1-aqaraium-flyer.docx
│   │       ├── post-2-voice-agent-flyer.docx
│   │       ├── post-3-baian-profile.docx
│   │       ├── post-4-bilal-profile.docx
│   │       ├── post-5-engagement.docx
│   │       └── post-6-combined-products.docx
│   ├── products/
│   │   ├── ai-workforce/              # (empty)
│   │   ├── baian/
│   │   │   ├── baian-product-evaluation-ar.docx
│   │   │   └── navaia-whatsapp-platform-ar.pdf
│   │   └── bilal/
│   │       ├── bilal-agent-packages-and-roi.pdf
│   │       └── bilal-product-evaluation-ar.docx
│   ├── sales/
│   │   ├── accelerators-and-incubators.xlsx
│   │   ├── competitors/
│   │   │   ├── competing-companies-b.xlsx
│   │   │   └── competing-companies.xlsx
│   │   ├── case-studies/              # (empty)
│   │   ├── crm-product-management.xlsx
│   │   ├── navaia-growth-plan-baian-ar.pdf
│   │   ├── navaia-growth-plan-bilal-ar.pdf
│   │   ├── pricing/                   # (empty)
│   │   └── proposals/
│   │       ├── baian-proposal.pptx
│   │       └── voice-agent-proposal.pptx
│   └── technical/                     # (empty)
│
├── scripts/                           # Automation scripts
│   ├── agent-loop.sh                  # Agent session loop
│   ├── loop.sh                        # Main orchestration loop
│   ├── setup.sh                       # Initial setup
│   └── start.sh                       # Startup script
│
├── tools/                             # Shared tools & integrations
│   ├── catalog.py                     # Knowledge base auto-cataloger
│   ├── requirements.txt
│   ├── telegram_bridge.py             # Telegram ↔ workspace bridge
│   └── trello_api.sh                  # Trello API helpers
│
└── workspace/                         # Runtime workspace
    ├── bot.log
    ├── crew.log
    ├── comms/
    │   ├── from-founder/              # Founder replies (inbound)
    │   │   └── 20260307-221211-task-created.md
    │   ├── inter-agent/               # Agent-to-agent handoffs
    │   └── to-founder/                # Outbound messages to Founder
    │       └── [multiple status/update files]
    ├── outputs/
    │   ├── admin/                     # Sage outputs
    │   │   ├── board-agenda.md
    │   │   ├── competitor-analysis.md
    │   │   ├── executive-summary.md
    │   │   ├── fact-sheet.md
    │   │   ├── kpis.md
    │   │   ├── pricing-comparison.md
    │   │   └── unlimited-coffee-budget.md
    │   ├── creative/                  # Muse outputs
    │   │   ├── ai-startup-logo-concepts.md
    │   │   ├── baian-bilal-product-summaries.md
    │   │   ├── instagram-captions.md
    │   │   ├── linkedin-post.md
    │   │   ├── slogans.md
    │   │   ├── taglines.md
    │   │   └── tweet-ideas.md
    │   ├── pm/                        # Navi outputs
    │   │   ├── deep-critical-analysis-20260307.md
    │   │   └── navaia-state-analysis-20260307.md
    │   └── technical/                 # Arch outputs
    │       ├── architecture-overview.md
    │       ├── dependencies.md
    │       ├── emoji-chatbot-readme.md
    │       ├── emoji-chatbot.py
    │       ├── file-inventory.md
    │       ├── folder-tree.md         ← this file
    │       ├── git-summary.md
    │       └── health-check.md
    └── tasks/
        ├── active/                    # In-progress tasks
        ├── admin/                     # Sage task queue
        │   └── 20260307-225859-task.md
        ├── blocked/                   # Awaiting Founder input
        │   ├── 20260306-214605-task.md
        │   ├── 20260306-224231-task.md
        │   └── 20260307-144541-task.md
        ├── creative/                  # Muse task queue
        │   └── 20260307-225859-task.md
        ├── done/                      # Completed tasks (14 files)
        ├── inbox/                     # New tasks from Telegram
        │   └── 20260307-225859-task.md
        ├── rejected/                  # Rejected tasks
        └── technical/                 # Arch task queue
            └── 20260307-225859-task.md
```

## Summary
- **Total items:** 212 (files + directories)
- **Knowledge files:** 33 (PDFs, Word docs, Excel, PowerPoint)
- **Scripts:** 4 (loop, agent-loop, setup, start)
- **Agent configs:** 4 (pm, creative, technical, admin)
- **Tools:** 4 (catalog.py, telegram_bridge.py, trello_api.sh, requirements.txt)
- **Completed tasks:** 14 in `workspace/tasks/done/`
