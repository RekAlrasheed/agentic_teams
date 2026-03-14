# Trello Integration Guide

**Board name:** Navaia Crew

## Lists (in order)
- **Inbox** — New tasks just received
- **Planning** — PM is breaking down the task
- **To Do** — Ready to be picked up by an agent
- **In Progress** — Agent actively working
- **Review** — PM reviewing the output
- **Done** — Completed and approved
- **Blocked** — Waiting for Manager input
- **Rejected** — Manager rejected, needs rework

## Labels (one per agent)
PM (blue), Creative (orange), Technical (purple), Admin (green)

## Card Requirements
Every card has: title, description, agent label, checklist of subtasks if applicable.

## API Access
Agents update cards by calling the Trello API via bash:
```bash
source tools/trello_api.sh
```
