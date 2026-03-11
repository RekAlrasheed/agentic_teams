# Navaia Microservices Architecture Design

**Date:** 2026-03-11
**Author:** Arch (Technical Agent)
**Status:** Draft — Pending Founder Review

---

## 1. Overview

This document outlines the migration from Navaia's current monolithic architecture to a microservices-based system. The design covers the two core products — **Baian** (WhatsApp AI platform) and **Bilal** (voice AI agent) — plus shared infrastructure.

---

## 2. Current State (Monolith)

Assumed monolith characteristics:
- Single deployable unit handling all concerns (API, auth, messaging, billing, AI orchestration)
- Shared database for all features
- Scaling requires scaling the entire application
- Deployments require full downtime or blue-green of the entire app

**Pain points:**
- Cannot scale AI processing independently of web serving
- WhatsApp webhook handling competes with user-facing API for resources
- Any crash brings down all features
- Long build/deploy cycles

---

## 3. Target Architecture

### 3.1 Service Map

```
┌─────────────────────────────────────────────────────────┐
│                    API Gateway (Kong / AWS API GW)       │
│            Rate limiting · Auth · Routing · SSL          │
└────────────┬────────────┬───────────────┬───────────────┘
             │            │               │
     ┌───────▼──┐  ┌──────▼──┐   ┌───────▼──────┐
     │  Auth    │  │  Users  │   │  Billing     │
     │ Service  │  │ Service │   │  Service     │
     │ (JWT)    │  │         │   │ (Stripe/etc) │
     └──────────┘  └─────────┘   └──────────────┘

     ┌───────────────────────────────────────────┐
     │            Message Broker (SQS / Redis)    │
     └──────┬──────────────────────┬─────────────┘
            │                      │
   ┌─────────▼────────┐   ┌────────▼──────────┐
   │  Baian Service   │   │  Bilal Service    │
   │  (WhatsApp AI)   │   │  (Voice AI Agent) │
   │                  │   │                   │
   │  - Webhook recv  │   │  - Inbound calls  │
   │  - Flow engine   │   │  - TTS/STT        │
   │  - Template mgmt │   │  - Call routing   │
   └────────┬─────────┘   └────────┬──────────┘
            │                      │
   ┌─────────▼──────────────────────▼─────────┐
   │          AI Orchestration Service         │
   │    Claude API · LLM routing · caching     │
   └───────────────────────────────────────────┘

   ┌────────────────────────────────────────────┐
   │           Notification Service             │
   │       (Telegram · Email · Webhooks)        │
   └────────────────────────────────────────────┘

   ┌────────────────────────────────────────────┐
   │           Analytics Service                │
   │       (Usage · Metrics · Billing data)     │
   └────────────────────────────────────────────┘
```

### 3.2 Services Breakdown

| Service | Responsibility | Tech Stack | Scaling Strategy |
|---------|----------------|------------|-----------------|
| API Gateway | Routing, auth, rate limiting | AWS API Gateway or Kong | Auto-scales |
| Auth Service | JWT issuance, token refresh, session | FastAPI + Redis | Horizontal |
| Users Service | Account management, tenant config | FastAPI + PostgreSQL | Horizontal |
| Billing Service | Subscriptions, usage metering, invoices | FastAPI + Stripe | Horizontal |
| Baian Service | WhatsApp webhook handling, flows, templates | FastAPI + SQS | Horizontal (high throughput) |
| Bilal Service | Voice calls, TTS/STT orchestration | FastAPI + Twilio/WebSocket | Horizontal |
| AI Orchestration | LLM calls, model routing, caching | FastAPI + Redis cache | Horizontal (GPU-aware) |
| Notification Service | Outbound alerts (Telegram, email, webhooks) | FastAPI + SQS | Horizontal |
| Analytics Service | Aggregated metrics, usage reports | FastAPI + TimescaleDB | Read replicas |

---

## 4. Data Architecture

### 4.1 Database Per Service (No Shared DB)

Each service owns its data. Cross-service data access goes through APIs, not direct DB queries.

```
Auth Service        → PostgreSQL (users, tokens)
Users Service       → PostgreSQL (accounts, tenants, settings)
Billing Service     → PostgreSQL (subscriptions, invoices) + Stripe as source of truth
Baian Service       → PostgreSQL (flows, templates, message history) + S3 (media)
Bilal Service       → PostgreSQL (call logs, scripts) + S3 (recordings)
AI Orchestration    → Redis (prompt cache) + PostgreSQL (usage logs)
Analytics Service   → TimescaleDB (time-series metrics)
```

### 4.2 Event Streaming

Services communicate asynchronously via **AWS SQS** (simple, cost-effective) or **Redis Pub/Sub** for low-latency events.

Key event flows:
- `user.created` → Billing Service provisions free tier
- `message.received` (WhatsApp) → Baian Service → AI Orchestration → Baian Service → WhatsApp reply
- `call.started` → Bilal Service → AI Orchestration → Bilal Service → Voice response
- `usage.tracked` → Analytics Service aggregates

---

## 5. Infrastructure

### 5.1 AWS Stack

```
Route53 → CloudFront → ALB
                           ├── ECS Fargate (Auth, Users, Billing, Notification, Analytics)
                           ├── ECS Fargate (Baian Service) — scales on SQS depth
                           ├── ECS Fargate (Bilal Service) — scales on active calls
                           └── ECS Fargate (AI Orchestration) — scales on queue depth

RDS PostgreSQL (Multi-AZ)  — per service, separate instances or schemas
ElastiCache Redis           — shared, logical DBs per service
S3                          — media storage
SQS                         — async messaging between services
CloudWatch + X-Ray          — observability
Secrets Manager             — all secrets (no env-file secrets in code)
```

### 5.2 Container Strategy

- All services containerized with Docker
- Deployed to ECS Fargate (no EC2 management overhead)
- Each service has its own ECR repository
- Health checks on `/health` endpoint per service

### 5.3 CI/CD Per Service

```
GitHub monorepo with service-scoped paths
  services/auth/     → GitHub Actions → ECR → ECS (auth-service)
  services/baian/    → GitHub Actions → ECR → ECS (baian-service)
  ...
```

Each service deploys independently. No cross-service deployment coupling.

---

## 6. Migration Plan (Phased)

### Phase 1 — Strangler Fig (Weeks 1-4)
1. Stand up API Gateway in front of the monolith
2. Extract **Auth Service** first (lowest blast radius, well-defined boundary)
3. Extract **Notification Service** (fire-and-forget, easy to decouple)
4. Route auth + notification traffic through new services; monolith stays running

**Deliverable:** Auth and notifications running as microservices; everything else in monolith.

### Phase 2 — Core Products (Weeks 5-10)
1. Extract **Users Service** (depends on Auth being stable)
2. Extract **Baian Service** (WhatsApp webhook handling isolated)
3. Extract **Bilal Service** (voice call handling isolated)
4. Set up SQS event bus between services
5. Run services in parallel with monolith (shadow mode) for validation

**Deliverable:** Baian and Bilal fully decoupled; monolith only handles legacy billing + admin.

### Phase 3 — Billing & Analytics (Weeks 11-14)
1. Extract **Billing Service** (most complex — validate thoroughly in shadow mode)
2. Extract **Analytics Service** (read-heavy; migrate in parallel)
3. Decommission monolith

**Deliverable:** Monolith retired. Full microservices.

### Phase 4 — Hardening (Weeks 15-16)
1. Tune auto-scaling policies
2. Load test each service independently
3. Set up distributed tracing (X-Ray)
4. Chaos testing (kill individual services, verify graceful degradation)

---

## 7. Service Communication Patterns

| Pattern | When to Use |
|---------|-------------|
| Sync REST (via API GW) | User-facing requests requiring immediate response |
| Async SQS | Background jobs, cross-service events, high-volume messaging |
| Redis Pub/Sub | Real-time low-latency events (e.g., live call status) |
| Direct DB read | Never — all cross-service data through APIs |

---

## 8. Observability Stack

- **Metrics:** CloudWatch + custom dashboards per service
- **Logs:** CloudWatch Logs with structured JSON logging
- **Tracing:** AWS X-Ray for distributed request tracing
- **Alerting:** CloudWatch Alarms → SNS → Telegram (our Notification Service)
- **Uptime:** Health checks per ECS task; ALB removes unhealthy instances automatically

---

## 9. Security Considerations

- All inter-service communication inside VPC (private subnets)
- Services authenticate to each other using internal JWT (service-to-service tokens)
- No service exposes direct DB access outside its VPC subnet
- Secrets via AWS Secrets Manager only — no hardcoded credentials anywhere
- WAF on CloudFront for public endpoints
- Network ACLs isolate each service subnet

---

## 10. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Data consistency across services | Use event sourcing + eventual consistency; use distributed sagas for transactions |
| Network latency between services | Co-locate services in same AZ; use Redis caching |
| Debugging complexity | Distributed tracing from day 1 (X-Ray) |
| Migration data loss | Shadow mode validation before cutting over |
| Team learning curve | Start with lowest-risk services (Auth, Notifications) |

---

## 11. Open Questions (Need Founder Input)

1. **Monolith location:** What is the current monolith repo and tech stack?
2. **Timeline:** Is the 16-week phased migration acceptable or is there urgency?
3. **Team:** Will external engineers be brought in, or is this internal + AI agents?
4. **Budget:** AWS cost increase during migration period (running both monolith + new services) — approximately 40-60% higher temporarily.
5. **Multi-tenancy:** Are Baian/Bilal customers fully isolated at the DB level already?

---

## Next Steps

1. Founder reviews and approves this architecture
2. Arch maps current monolith boundaries to service candidates
3. Phase 1 begins: API Gateway + Auth Service extraction
4. Weekly architecture review meetings to adjust as we learn

---

*Prepared by Arch (Technical Agent) — 2026-03-11*
