## Task: Summarize both Zoho Mail inboxes

**Agent:** Sage
**Model:** haiku
**Priority:** medium
**Source:** Founder (via PM)

### Instructions

Read both email accounts and provide a **brief** summary of what's in each inbox.

**Tool to use:**
```bash
# info@navaia.sa
python tools/zoho_mail.py list --limit 20

# ralrasheed@navaia.sa
python tools/zoho_mail.py --account rakan list --limit 20
```

To read a specific email's full content:
```bash
python tools/zoho_mail.py read <message_id>
python tools/zoho_mail.py --account rakan read <message_id>
```

### What to deliver

A short summary (half a page max) covering:
- **info@navaia.sa:** What types of emails are there? Any patterns? Anything needing a reply?
- **ralrasheed@navaia.sa:** Same questions.
- **Action items:** Flag any emails that look important or time-sensitive.

### What NOT to do
- No long reports or analysis documents
- No charts or spreadsheets
- Don't reply to any emails — just read and summarize
- Keep it brief — the Founder reads on mobile

### Output
Save to: `workspace/outputs/admin/20260314-email-inbox-summary.md`
