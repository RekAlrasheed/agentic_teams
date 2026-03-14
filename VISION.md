# NAVAIA AI WORKFORCE — ARCHITECTURE ROADMAP

> This document outlines the full architecture we're building toward, from local execution to cloud-scale SaaS.

---

## Phase 0 (Current) — Claude Max on Local Machine

The immediate system: 4 AI agents running as a coordinated team on the Manager's machine.

### Architecture
- **Engine:** Claude Code Agent Teams (experimental)
- **Execution:** Local machine with Claude Max subscription
- **Agents:** PM (Navi), Creative (Muse), Technical (Arch), Admin (Sage)
- **Communication:** Telegram bot ↔ filesystem bridge
- **Task Management:** Trello board via REST API
- **Knowledge Base:** Local files in `knowledge/` with auto-cataloger
- **Runtime:** 24/7 via tmux + auto-restart loop

### Cost
- Claude Max subscription: fixed monthly cost
- No additional infrastructure
- All compute runs locally

### Limitations
- Tied to Manager's machine (must stay on)
- Max subscription rate limits
- No persistent memory between sessions (ephemeral sessions)
- Single point of failure

---

## Phase 1 — Cloud Deployment

Move to cloud for reliability, add always-on channel agents, and introduce proper infrastructure.

### Architecture
```
┌─────────────────────────────────────────────────────────┐
│                    AWS EC2 Instance                       │
│                 (t3.xlarge or m6i.xlarge)                 │
│                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  FastAPI      │  │  Claude Agent │  │  OpenClaw     │  │
│  │  Orchestrator │──│  SDK (Core)   │  │  (Channels)   │  │
│  └──────┬───────┘  └──────────────┘  └───────────────┘  │
│         │                                                 │
│  ┌──────┴───────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Redis        │  │  Weaviate    │  │  PostgreSQL   │  │
│  │  Streams      │  │  Vector DB   │  │  (via RDS)    │  │
│  └──────────────┘  └──────────────┘  └───────────────┘  │
│                                                           │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  Docker Compose                                       │ │
│  └──────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
         │              │              │
    ┌────┴────┐   ┌────┴────┐   ┌────┴────┐
    │Telegram │   │WhatsApp │   │SendGrid │
    │  Bot    │   │Business │   │  Email  │
    └─────────┘   └─────────┘   └─────────┘
```

### Components
- **FastAPI Orchestrator:** Central API connecting both engines, routing tasks
- **Claude Agent SDK:** Core agents (Navi, Muse, Arch, Sage) via API keys
- **OpenClaw:** Always-on channel agents (Telegram bot, WhatsApp, Outreach)
- **Redis Streams:** Inter-agent messaging and event bus
- **Weaviate:** Vector DB for semantic search and RAG over knowledge base
- **PostgreSQL (RDS):** Structured data, audit trail, task history
- **Docker Compose:** Container orchestration

### Cost Estimate
- EC2 (t3.xlarge): ~$85-140/month
- RDS (db.t3.micro): ~$15/month
- Claude API: ~$25-30/day (see model routing below)
- OpenClaw models: ~$5-10/day
- **Total: ~$1,200-1,500/month**

---

## Phase 2 — Multi-Engine Scaled Architecture

Full production system with customer-facing products and multi-tenant isolation.

### Architecture
- **3 EC2 Instances:**
  - Core: FastAPI + Claude Agent SDK agents
  - OpenClaw: Isolated channel agents
  - GPU (optional): Self-hosted models (Llama 3.3 70B for outreach)
- **Customer-Facing Products:**
  - Baian: WhatsApp AI assistant for businesses
  - AI Call Center: Voice AI via Vapi/Twilio
  - HR Recruiter: Automated candidate screening
- **Multi-Tenant Isolation:** Separate data, models, and access per customer
- **Monitoring Dashboard:** Next.js app for real-time oversight

### SaaS Pricing
| Tier | Price (SAR/month) | Included |
|------|-------------------|----------|
| Basic | 1,000 | 1 channel, 500 messages/day |
| Pro | 2,500 | 3 channels, 2,000 messages/day, analytics |
| Premium | 5,000 | All channels, unlimited, custom models, priority |

---

## Model Routing Strategy

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

---

## Full Tech Stack (Phase 1+)

| Layer | Technology |
|-------|-----------|
| AI Engines | Claude Agent SDK + OpenClaw |
| Backend | FastAPI + Python |
| Vector DB | Weaviate |
| Structured DB | PostgreSQL (AWS RDS) |
| Message Bus | Redis Streams |
| Task Management | Trello (Phase 0), Linear (Phase 1+) |
| Infrastructure | AWS ECS Fargate, Lambda, S3 |
| Dashboard | Next.js |
| Channels | Telegram, WhatsApp Business API, Vapi/Twilio, SendGrid |
| Model Gateway | LiteLLM or OpenRouter |
| Containers | Docker Compose (Phase 0-1), ECS (Phase 2) |
| CI/CD | GitHub Actions |
| Monitoring | CloudWatch + custom dashboard |

---

## 12-Week Implementation Roadmap

### Weeks 1-2: Phase 0 Foundation
- [x] Set up repo structure and agent configs
- [ ] Configure Telegram bot and Trello board
- [ ] Add initial company knowledge files
- [ ] Test single-session operation
- [ ] Validate 24/7 loop stability

### Weeks 3-4: Phase 0 Hardening
- [ ] Stress-test rate limit handling
- [ ] Refine agent prompts based on output quality
- [ ] Build knowledge base with all company docs
- [ ] Establish Manager workflow patterns
- [ ] Document common tasks and expected outputs

### Weeks 5-6: Phase 1 Infrastructure
- [ ] Provision AWS EC2 instance
- [ ] Set up Docker Compose stack
- [ ] Deploy PostgreSQL on RDS
- [ ] Set up Redis Streams
- [ ] Deploy Weaviate vector DB

### Weeks 7-8: Phase 1 Migration
- [ ] Build FastAPI orchestrator
- [ ] Migrate agents from Claude Code to Claude Agent SDK
- [ ] Implement API-based model routing
- [ ] Connect Redis Streams for inter-agent messaging
- [ ] Migrate knowledge base to Weaviate (RAG)

### Weeks 9-10: Phase 1 Channels
- [ ] Deploy OpenClaw for channel agents
- [ ] Build always-on Telegram bot (replace filesystem bridge)
- [ ] Integrate WhatsApp Business API (Baian)
- [ ] Set up SendGrid for outreach campaigns
- [ ] Build Next.js monitoring dashboard (v1)

### Weeks 11-12: Phase 2 Prep
- [ ] Design multi-tenant data model
- [ ] Build customer onboarding flow
- [ ] Set up Vapi/Twilio for call center prototype
- [ ] Implement SaaS billing (Stripe/Moyasar)
- [ ] Launch beta with 2-3 pilot customers

---

## Key Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Phase 0 engine | Claude Code Agent Teams | Zero infra cost, uses Max subscription |
| Cloud region | me-south-1 (Bahrain) | Closest to Saudi Arabia |
| Vector DB | Weaviate | Open-source, good Arabic support, self-hostable |
| Structured DB | PostgreSQL | Industry standard, RDS managed, ACID compliant |
| Message bus | Redis Streams | Low latency, simple, battle-tested |
| Channel engine | OpenClaw | Multi-model, always-on, good for conversational AI |
| Model gateway | LiteLLM | Open-source, supports all providers, easy routing |
| Task management | Trello → Linear | Trello for simplicity now, Linear for API power later |
