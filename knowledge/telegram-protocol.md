# Telegram Communication Protocol

## Receiving tasks from Manager
- New tasks appear as files in `workspace/tasks/inbox/` (created by Telegram bridge)
- Check this folder on startup and periodically
- Each file contains the task text, timestamp, and source

## Sending messages to Manager
- Write a markdown file to `workspace/comms/to-manager/`
- Filename format: `{YYYYMMDD-HHMMSS}-{topic}.md`
- The Telegram bridge watches this folder and sends new files to the Manager
- Keep messages concise — the Manager reads on mobile

## Message format
```markdown
## [STATUS UPDATE | QUESTION | PLAN APPROVAL | BLOCKER | COMPLETED]

{Your message}

**Task:** {task name}
**Agent:** {who's working on it}
**Trello:** {card ID or link}
```

## Receiving Manager replies
- Replies appear in `workspace/comms/from-manager/`
- Check this folder when waiting for approval
