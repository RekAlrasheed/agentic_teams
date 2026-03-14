## Task: Detailed Email Analysis — info@navaia.sa

**Assigned by:** Navi (PM)
**Priority:** High
**Model hint:** sonnet (this requires careful reading and analysis)

### Instructions

Read ALL emails in the info@navaia.sa inbox and provide a **detailed per-email summary** with actionable call-to-actions.

**Step 1 — List all emails:**
```bash
python tools/zoho_mail.py list --limit 20
```

**Step 2 — Read each email one by one:**
```bash
python tools/zoho_mail.py read <message_id>
```

If you hit rate limits, wait 30 seconds between reads. Do NOT skip emails — read every single one.

**Step 3 — For EACH email, document:**
- **From:** sender name and email
- **Date:** when received
- **Subject:** email subject line
- **Summary:** 2-3 sentence summary of the email content
- **Call to Action:** what should the Founder do about this email (reply, archive, forward, schedule meeting, etc.)
- **Priority:** High / Medium / Low with brief justification

**Step 4 — After all emails are read, provide:**
- **Email Pattern Analysis:** group by category (applications, partnerships, admin, spam)
- **Top 5 Actions Ranked by Urgency:** what needs attention first
- **Inbox Health Notes:** volume, quality, any concerns

### What NOT to do
- Do NOT reply to any emails — read only
- Do NOT skip emails due to rate limits — wait and retry
- Do NOT give one-line summaries — the Founder wants DETAIL

### Output
Save to: `workspace/outputs/admin/20260314-info-inbox-detailed-v2.md`

### When done
1. Move this task file to `workspace/tasks/done/`
2. Write a completion report to `workspace/comms/to-founder/` that includes:
   - Summary of what you found
   - The top 3 most urgent emails
   - Path to the full output file
