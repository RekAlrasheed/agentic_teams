## Task: Smart result delivery in Telegram

**Assigned by:** Navi (PM)
**Priority:** High

### Problem

When agents finish tasks, the results are sent to the Founder on Telegram. Right now it always sends raw text which gets truncated for long outputs. The Founder can't easily read results.

### What we need

Make the Telegram bot smart about HOW it delivers results:

1. **Short results** (fits in a message) → send the content directly as a Telegram message
2. **Document-sized results** (single file, like a report or summary) → send as a Telegram file attachment using `send_document` so the Founder can open/download it
3. **Large results or multiple files** → send a short summary message + tell the Founder where the files are saved

The decision should be automatic based on the output size and type.

### Where to look

- `tools/telegram_bridge.py` — the `OutputWatcher._notify()` method (around line 366) is where output notifications happen
- Also check `OutboxWatcher._send()` (around line 328) for the to-founder messages
- Telegram bot API supports `send_document` for file attachments

### When done

Save any changes and move this task to `workspace/tasks/done/`.
