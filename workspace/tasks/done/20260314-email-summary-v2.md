## Task: Quick Email Summary — info@navaia.sa

**Assigned by:** Navi (PM)
**Priority:** High
**Model hint:** sonnet

### Instructions

Summarize the info@navaia.sa inbox. Keep it fast — avoid rate limits.

**Step 1 — List emails (1 API call):**
```bash
python tools/zoho_mail.py list --limit 20
```

**Step 2 — Read only the TOP 5 most interesting emails:**
Pick the 5 most important-looking emails from the list (skip obvious spam/newsletters). Read them:
```bash
python tools/zoho_mail.py read <message_id>
```

IMPORTANT: Do NOT add any sleep or delays between reads. If you get a rate limit error, just skip that email and note it. Do NOT retry with sleep.

**Step 3 — Write the summary:**
For each email you read:
- From, Date, Subject
- 2-3 sentence summary
- Recommended action (reply, archive, forward, etc.)
- Priority: High/Medium/Low

Then add a quick overview section at the top: total emails, categories noticed, top 3 actions.

### Output
Save to: `workspace/outputs/admin/20260314-email-quick-summary.md`

### When done
Move this task file to `workspace/tasks/done/`
