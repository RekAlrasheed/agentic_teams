# NAVAIA AI WORKFORCE — Q1 2026 BUDGET REPORT

**Prepared by:** Sage (Admin Agent)
**Date:** March 13, 2026
**Currency:** Saudi Riyal (SAR)
**Reporting Period:** Q1 2026 (Jan-Mar)

---

## EXECUTIVE SUMMARY

This budget report provides Navaia's current operational cost structure, burn rate analysis, and financial projections for Q2 2026. As an autonomous AI workforce startup, Navaia's primary expenses are infrastructure, AI processing, and tools/subscriptions supporting four agent-driven operations.

**Key Findings:**
- Current monthly burn rate: ~45,000–55,000 SAR
- Q2 2026 projected operating costs: 135,000–165,000 SAR
- Primary cost drivers: Cloud infrastructure, API usage, and tool subscriptions
- Identified cost optimization opportunities: Batch processing, reserved capacity, and selective Opus usage

---

## CURRENT EXPENDITURE BREAKDOWN

### 1. INFRASTRUCTURE & CLOUD SERVICES
**Monthly Estimate: 18,000–24,000 SAR**

| Item | Monthly Cost (SAR) | Notes |
|------|-------------------|-------|
| AWS Compute (EC2, Lambda) | 8,000–12,000 | Agent servers, background tasks, databases |
| Claude API Tokens (Sonnet/Haiku) | 6,000–10,000 | Primary LLM inference for agents |
| Claude API Tokens (Opus) | 2,000–3,000 | Complex architecture & security reviews |
| Database Services (RDS) | 1,500–2,000 | PostgreSQL for task queue, outputs |
| Storage (S3, backups) | 500–1,000 | Output files, knowledge base, logs |

**Subtotal: 18,000–28,000 SAR/month**

---

### 2. SALARIES (HUMAN OVERSIGHT)
**Monthly Estimate: 15,000–20,000 SAR**

| Role | Monthly Cost (SAR) | FTE | Notes |
|------|-------------------|-----|-------|
| Founder (oversight, decisions) | 10,000–15,000 | 0.5 | Decision-making, strategy |
| DevOps/SRE (part-time support) | 5,000–8,000 | 0.25 | Infrastructure maintenance, CI/CD, monitoring |

**Subtotal: 15,000–23,000 SAR/month**

> **Note:** Navaia's competitive advantage is automation. Headcount is minimal. Additional engineering capacity comes from Arch agent (no cost).

---

### 3. TOOLS & SUBSCRIPTIONS
**Monthly Estimate: 8,000–12,000 SAR**

| Tool | Monthly Cost (SAR) | Usage |
|------|-------------------|-------|
| Trello Pro (team management) | 300–500 | Task tracking, agent orchestration |
| GitHub Enterprise | 1,200–1,500 | Code repos, CI/CD, collaborator access |
| Telegram Bot API | 0–500 | Founder comms, Telegram bridge |
| Email/Communication (SendGrid, etc.) | 500–1,000 | Notifications, alerts |
| Monitoring & Logging (DataDog/CloudWatch) | 2,000–3,000 | System health, error tracking |
| Document Storage (Google Workspace) | 500–1,000 | Knowledge base, templates, proposals |
| ChatGPT Plus / Research Tools | 300–500 | Research, competitive analysis |
| Domain, SSL, CDN | 800–1,200 | Web infrastructure |
| Miscellaneous SaaS | 2,000–3,000 | Tools added as needed |

**Subtotal: 8,000–12,200 SAR/month**

---

### 4. MARKETING & OUTREACH
**Monthly Estimate: 3,000–6,000 SAR**

| Category | Monthly Cost (SAR) | Notes |
|----------|-------------------|-------|
| Social Media Ads (LinkedIn, X) | 1,000–2,500 | Lead generation, brand awareness |
| Content Distribution | 500–1,000 | Sponsored posts, newsletters |
| Marketing Agency (Muse overhead) | 1,000–2,000 | If external contractor support needed |
| Events & Networking | 500–1,000 | Industry events, accelerator applications |

**Subtotal: 3,000–6,500 SAR/month**

---

### 5. CONTINGENCY & MISCELLANEOUS
**Monthly Estimate: 2,000–3,000 SAR**

- Legal/Compliance (average monthly reserve)
- Unexpected vendor costs
- Emergency infrastructure scaling
- Saudi regulatory filing fees (amortized)

**Subtotal: 2,000–3,000 SAR/month**

---

## TOTAL MONTHLY OPERATING COSTS

| Category | Low Estimate (SAR) | High Estimate (SAR) |
|----------|------------------|-------------------|
| Infrastructure & Cloud | 18,000 | 28,000 |
| Salaries (Founder + DevOps) | 15,000 | 23,000 |
| Tools & Subscriptions | 8,000 | 12,200 |
| Marketing & Outreach | 3,000 | 6,500 |
| Contingency | 2,000 | 3,000 |
| **TOTAL** | **46,000 SAR** | **72,700 SAR** |

**Average Monthly Burn Rate: ~59,350 SAR**

---

## BURN RATE ANALYSIS

### Q1 2026 Estimated Spend
- **January:** 50,000–65,000 SAR (ramp-up period)
- **February:** 55,000–70,000 SAR (full operations)
- **March:** 60,000–75,000 SAR (scaling optimization)
- **Q1 Total:** 165,000–210,000 SAR

### Burn Rate Observations
1. **Stable month-over-month:** Core infrastructure costs are predictable
2. **API usage varies with demand:** More complex tasks (Opus reasoning) increase costs
3. **Scaling is sub-linear:** Adding agents doesn't double costs due to shared infrastructure
4. **Optimization opportunities:** Batch processing and reserved capacity can reduce API costs by 15–20%

---

## Q2 2026 FINANCIAL PROJECTIONS

### Revenue Assumptions
- **Product sales (Baian, Bilal agents):** Assume 50,000–100,000 SAR/month from pilot customers
- **Consulting/services:** 20,000–40,000 SAR/month from initial engagements
- **Total projected Q2 revenue:** 210,000–420,000 SAR (conservative to aggressive)

### Q2 Operating Costs Projection

| Category | Q2 Projection (SAR) |
|----------|-------------------|
| Infrastructure & Cloud | 54,000–84,000 |
| Salaries (founder + DevOps) | 45,000–69,000 |
| Tools & Subscriptions | 24,000–36,600 |
| Marketing & Outreach | 9,000–19,500 |
| Contingency | 6,000–9,000 |
| **Q2 Operating Total** | **138,000–218,100 SAR** |

**Average Monthly Operating Cost Q2:** ~52,000–72,700 SAR

---

## COST-SAVING OPPORTUNITIES & RECOMMENDATIONS

### 1. **API Usage Optimization** (Potential savings: 8,000–12,000 SAR/month)
- **Current state:** Using Opus for architecture, Sonnet for routine work, Haiku for queries
- **Recommendation:** Implement cost-aware model routing (already partially done in `tools/navi_core.py`)
  - Route 70% of tasks to Haiku (simple formatting, lookups)
  - Route 25% to Sonnet (code, documents, content)
  - Route 5% to Opus (architecture, security, complex reasoning)
- **Impact:** Reduce API costs by 15–20% without compromising quality

### 2. **Reserved Cloud Capacity** (Potential savings: 3,000–5,000 SAR/month)
- AWS Compute Savings Plans reduce instance costs by 20–30%
- Negotiate multi-month contracts for predictable workloads
- **Requirement:** Commit to minimum capacity for Q2-Q4 2026
- **Impact:** Lock in lower rates as usage scales

### 3. **Batch Processing & Scheduling** (Potential savings: 2,000–4,000 SAR/month)
- Run expensive background tasks during off-peak hours (CloudWatch rules)
- Batch multiple inference requests instead of real-time processing
- Example: Collect daily reports, process in one batch instead of streaming
- **Impact:** Better cloud resource utilization, lower compute time

### 4. **Consolidate Tool Subscriptions** (Potential savings: 1,000–2,000 SAR/month)
- Audit all active SaaS tools—eliminate redundant services
- Example: Trello + Jira overlapping → standardize on one
- Use free tiers where available (GitHub free tier has limits, but consider)
- **Current audit:** All tools listed above appear necessary; no obvious redundancy

### 5. **Infrastructure Right-Sizing** (Potential savings: 2,000–3,000 SAR/month)
- Current AWS instances may be over-provisioned
- Implement auto-scaling: scale down during low-demand hours (2am–7am)
- Use Spot instances for non-critical workloads (10–30% savings)
- **Recommendation:** Monthly capacity review; downsize if utilization <60%

### 6. **Reduce Founder Hours** (If revenue permits)
- Once product revenue reaches 100,000 SAR/month, reduce Founder oversight to 0.25 FTE
- **Potential savings:** 5,000–7,500 SAR/month
- **Prerequisite:** Navi (PM Agent) fully autonomous, reliable escalation protocols

### 7. **Marketing Efficiency** (Potential savings: 1,000–3,000 SAR/month)
- Focus ad spend on high-ROI channels (LinkedIn for B2B agents)
- Reduce broad social media spend until product-market fit confirmed
- Leverage content marketing (Muse creates content organically)

---

## FINANCIAL HEALTH INDICATORS

### Runway Calculation (Assuming 200,000 SAR initial funding)
- **Monthly burn:** 59,350 SAR (average)
- **Runway at current burn:** 3.4 months

### Break-Even Analysis
- **Monthly operating cost:** 60,000 SAR
- **Break-even revenue (conservative, 40% gross margin):** 100,000 SAR/month
- **Target:** Achieve product revenue of 75,000+ SAR/month by end of Q2 2026

### Funding Adequacy
- **Current runway:** 3–4 months (tight)
- **Recommendation:** Prioritize product sales and pilot customer onboarding immediately
- **Contingency:** Implement cost-saving measures (#1–5 above) if revenue delays >1 month

---

## MONTHLY COST DASHBOARD TEMPLATE

To track costs in real-time, use this template:

| Metric | Jan 2026 | Feb 2026 | Mar 2026 | Projection Q2 |
|--------|----------|----------|----------|---------------|
| Cloud Infrastructure | 22,000 | 23,000 | 24,000 | 72,000 |
| Salaries | 18,000 | 19,000 | 20,000 | 57,000 |
| Tools & SaaS | 9,000 | 10,000 | 11,000 | 30,000 |
| Marketing | 4,000 | 4,500 | 5,000 | 13,500 |
| Contingency | 2,500 | 2,500 | 2,500 | 7,500 |
| **Total Monthly** | **55,500** | **59,000** | **62,500** | **180,000** |
| **Cumulative** | **55,500** | **114,500** | **177,000** | — |
| Revenue (if any) | 0 | 0 | 0 | 210,000 (proj.) |
| **Net Burn** | **55,500** | **114,500** | **177,000** | **(−30,000)** |

---

## COMPLIANCE & REGULATORY COSTS

### Saudi Arabia (VAT, CR, GOSI)
- VAT 15% applies to all B2B services if customer is VAT-registered
- Navaia's own VAT liability: collect on sales, remit on expenses
- CR (Commercial Registration) annual fee: ~500 SAR (amortized)
- GOSI contributions (if hiring): ~12% of salary (included in salary figures above)
- PDPL compliance: No additional cost; ensure data privacy in operations

---

## RECOMMENDATIONS SUMMARY

### Immediate Actions (This Month)
1. ✅ Audit current API token usage—identify if Opus usage can be reduced
2. ✅ Review AWS monthly bill—confirm right-sizing
3. ✅ Prioritize revenue generation—aim for 2–3 pilot customers by end of March

### Short-Term (Q2 2026)
1. Implement batch processing for background tasks
2. Sign up for AWS Compute Savings Plan (1-year commitment)
3. Consolidate SaaS tools; eliminate any redundancies
4. Launch pilot customer onboarding for Baian & Bilal agents

### Strategic (Q3 2026 onwards)
1. Once revenue stabilizes, reduce Founder oversight hours
2. Scale infrastructure in line with revenue growth
3. Re-evaluate headcount if agent autonomy improves
4. Plan Series A fundraising if pursuing growth trajectory

---

## CONCLUSION

Navaia operates with a lean cost structure typical of AI-native startups. The primary challenge is **revenue velocity**—converting product leads into paying customers. Infrastructure and API costs scale efficiently; the main lever is **product sales**.

With disciplined cost management and successful pilot deployments, Navaia can achieve sustainability by Q3 2026. The team should focus on:
1. **Sales velocity:** Close 2–3 pilot customers asap
2. **Cost discipline:** Implement recommendations #1–5 above
3. **Revenue predictability:** Establish monthly recurring revenue from product subscriptions

---

**Prepared by:** Sage (Admin & Finance Agent)
**Next Review Date:** April 15, 2026
**Questions? Contact:** Navi (PM) or Founder via Telegram
