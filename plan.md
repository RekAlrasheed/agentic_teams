# Plan: Integrate Everything Claude Code (ECC) on Top of Navaia

## Goal
Add ECC's skills, commands, agents, hooks, and rules as a **capability layer** on top of our existing Navaia AI Workforce. Keep all existing Navaia infrastructure intact (CLAUDE.md, agent configs, tools/, scripts/, workspace/, knowledge/).

## How It Works (No Conflicts)
- **ECC installs globally** to `~/.claude/` (agents, commands, skills, rules)
- **Our stuff is project-level** in `agentic_teams/` (CLAUDE.md, agents/, tools/, workspace/)
- Project-level configs **always override** global ones — natural separation
- ECC adds capabilities our agents can USE, it doesn't replace them

---

## Step 1: Clone ECC Repository
```bash
git clone https://github.com/affaan-m/everything-claude-code.git /tmp/ecc
```

## Step 2: Install Rules (Python + Common)
Run the ECC installer for our tech stack:
```bash
cd /tmp/ecc && ./install.sh python
```
This copies to `~/.claude/rules/`:
- `common/` — 9 shared rules (agents, coding-style, development-workflow, git-workflow, hooks, patterns, performance, security, testing)
- `python/` — Python-specific best practices

**Why these are safe:** Rules are global coding guidelines. They complement (not conflict with) our CLAUDE.md business rules.

## Step 3: Install ECC Agents (Selective — 8 of 17)
Copy only the agents that complement our existing team:
- `planner.md` — Breaks down complex features into phases (helps Navi)
- `architect.md` — System design decisions (helps Arch)
- `tdd-guide.md` — Test-driven development (helps Arch)
- `code-reviewer.md` — Code quality assessment (helps Arch)
- `security-reviewer.md` — Security vulnerability scanning (helps Arch)
- `build-error-resolver.md` — Resolves build failures (helps Arch)
- `python-reviewer.md` — Python-specific code review (helps Arch)
- `doc-updater.md` — Keeps docs in sync (helps all)

**Skip:** go-reviewer, go-build-resolver, database-reviewer (not our stack), chief-of-staff (overlaps Navi), harness-optimizer, loop-operator, e2e-runner, refactor-cleaner (nice-to-have later)

## Step 4: Install ECC Commands (Selective — 15 of 49)
Copy the most valuable slash commands:
- `/plan` — Implementation design and task breakdown
- `/tdd` — Test-driven development workflow
- `/orchestrate` — Chain agents for complex tasks
- `/code-review` — Quality gate assessment
- `/security-scan` — Security audit
- `/verify` — Verification workflow
- `/quality-gate` — Post-edit quality checks
- `/learn` — Extract patterns from session
- `/evolve` — Evolve learnings into skills
- `/eval` — Run evaluation framework
- `/instinct-status` — Check learning status
- `/instinct-export` — Export learned patterns
- `/instinct-import` — Import learned patterns
- `/model-route` — Smart model routing (aligns with our cost rules)
- `/checkpoint` — Session state preservation

**Skip:** Go-specific, multi-* (we have our own multi-agent system), pm2, loop-start, sessions, frontend-slides, claw, etc.

## Step 5: Install ECC Skills (Selective — 20 of 91)
Copy most relevant skills for our stack:

**Must-have:**
- `api-design` — API best practices
- `backend-patterns` — Backend architecture
- `python-patterns` — Python coding standards
- `python-testing` — Python test strategies
- `security-review` — Security review workflow
- `security-scan` — Security scanning
- `tdd-workflow` — TDD methodology
- `deployment-patterns` — Deployment best practices
- `coding-standards` — General coding standards
- `continuous-learning` — The instinct/learning system
- `verification-loop` — Verify changes work

**Nice-to-have:**
- `agent-harness-construction` — Building better agent systems
- `agentic-engineering` — Agentic patterns
- `autonomous-loops` — Autonomous operation patterns
- `cost-aware-llm-pipeline` — Token cost optimization
- `content-engine` — Content generation (helps Muse)
- `article-writing` — Article writing (helps Muse)
- `investor-materials` — Investor materials (helps Sage)
- `market-research` — Market research (helps Sage)
- `docker-patterns` — Docker best practices

## Step 6: Install Hooks (Selective — Learning System Only)
From ECC's hooks.json, add ONLY:
- **observe** hooks (PreToolUse + PostToolUse) — Powers the learning/instinct system
- **quality-gate** (PostToolUse) — Auto quality checks after edits

**Skip for now:** auto-tmux, git-push-reminder, format, typecheck, console-warn, doc-file-warning (may interfere with our `--dangerously-skip-permissions` autonomous mode)

## Step 7: Merge Settings
Update `~/.claude/settings.json` to preserve our existing setting + add ECC hooks:
```json
{
  "skipDangerousModePermissionPrompt": true,
  "hooks": { ... selected ECC hooks ... }
}
```

## Step 8: Update Our CLAUDE.md (Add ECC Reference)
Add a small section to our existing CLAUDE.md:
```markdown
## ECC CAPABILITIES (Everything Claude Code)

ECC is installed globally. You have access to:
- `/plan`, `/tdd`, `/orchestrate`, `/code-review`, `/security-scan` slash commands
- Specialized subagents: planner, architect, tdd-guide, code-reviewer, security-reviewer
- 20 domain skills (run /instinct-status to check learning)
- Continuous learning system that captures patterns across sessions

Use these to enhance your work — they complement (not replace) your existing agent behavior rules.
```

## Step 9: Test
1. Verify Claude Code starts without errors
2. Run `/instinct-status` to confirm learning system is active
3. Run `/plan "test task"` to confirm commands work
4. Verify our existing loop.sh still works
5. Verify Telegram bridge still works
6. Verify Trello integration still works

## Step 10: Rollback Plan
If anything breaks:
```bash
rm -rf ~/.claude/agents/ ~/.claude/skills/ ~/.claude/rules/
# Restore original settings.json:
echo '{"skipDangerousModePermissionPrompt": true}' > ~/.claude/settings.json
```
Our project-level files are never touched, so they need no rollback.

---

## What We're NOT Doing
- NOT replacing our CLAUDE.md — only adding a small reference section
- NOT replacing our agent configs (agents/pm/, agents/creative/, agents/technical/, agents/admin/)
- NOT touching our tools/ (trello_api.sh, telegram_bridge.py, navi_core.py)
- NOT touching our scripts/ (loop.sh, agent-loop.sh)
- NOT touching workspace/, knowledge/, or dashboard/
- NOT installing ALL 91 skills — only 20 relevant ones
- NOT installing ALL 49 commands — only 15 useful ones
- NOT installing ALL 17 agents — only 8 complementary ones
- NOT installing MCP configs (we'd need API keys we don't have yet)
