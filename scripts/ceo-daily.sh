#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# CEO Daily Task Generator
#
# Creates the CEO agent's daily research & performance review task.
# Designed to run via cron once per day (e.g., 08:00 local time).
#
# Usage:
#   bash scripts/ceo-daily.sh
#
# Cron example (daily at 8 AM):
#   0 8 * * * cd /path/to/agentic_teams && bash scripts/ceo-daily.sh
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

TODAY=$(date '+%Y-%m-%d')
TIMESTAMP=$(date '+%Y%m%d-%H%M%S')
TASK_DIR="workspace/tasks/ceo"
TASK_FILE="${TASK_DIR}/${TIMESTAMP}-daily-research.md"

# Ensure task directory exists
mkdir -p "$TASK_DIR"

# Check if today's daily task already exists (avoid duplicates)
if find "$TASK_DIR" -name "*-daily-research.md" -newer "$TASK_DIR/.gitkeep" 2>/dev/null | head -1 | grep -q "$(date '+%Y%m%d')"; then
    echo "[ceo-daily] Today's task already exists. Skipping."
    exit 0
fi

# Also check done folder for today's completed daily task
DONE_DIR="workspace/tasks/done"
if find "$DONE_DIR" -name "*-daily-research.md" 2>/dev/null | xargs grep -l "$TODAY" 2>/dev/null | head -1 | grep -q .; then
    echo "[ceo-daily] Today's daily task already completed. Skipping."
    exit 0
fi

cat > "$TASK_FILE" <<EOF
## TASK: Daily CEO Briefing — ${TODAY}
**Time:** $(date -u '+%Y-%m-%dT%H:%M:%SZ')
**Source:** Automated (ceo-daily.sh)
**Assigned Agent:** CEO
**Priority:** Standard
**Model:** sonnet

### Description

Run the full daily CEO research and performance review pipeline for ${TODAY}.

#### Step 1: Agent Performance Review
- Read \`workspace/tasks/done/\` — count completed tasks per agent since last review
- Read \`workspace/tasks/failed/\` — count failures per agent
- Query \`workspace/token_usage.db\` — get token costs per agent
- Count output files in \`workspace/outputs/{agent}/\`
- Write review to \`workspace/outputs/ceo/performance/review-${TODAY}.md\`

#### Step 2: Tech & Tools Research
- Search for latest AI agent news, real estate tech, voice/chat AI developments
- Focus on tools and frameworks that could improve our agent workflow
- Write findings to \`workspace/outputs/ceo/research/tech-${TODAY}.md\`

#### Step 3: Cost Analysis
- Review token_usage.db for spending trends
- Compare costs across agents and models
- Identify optimization opportunities
- Write analysis to \`workspace/outputs/ceo/cost-analysis/cost-${TODAY}.md\`

#### Step 4: Business Development Ideas
- Research client acquisition strategies for AI-powered real estate
- Identify partnership or market opportunities
- Write ideas to \`workspace/outputs/ceo/business-dev/biz-${TODAY}.md\`

#### Step 5: Daily Briefing
- Compile executive summary from all steps above
- Write daily briefing to \`workspace/outputs/ceo/daily-briefing-${TODAY}.md\`

#### Step 6: Notify PM
- Send summary to \`workspace/comms/inter-agent/ceo-to-pm-daily-briefing.md\`
- Include key metrics, top findings, and action items for the Manager
EOF

echo "[ceo-daily] Task created: $TASK_FILE"
