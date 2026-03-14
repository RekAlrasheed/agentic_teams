# Marketing Capabilities — Setup Guide

## What Was Installed

### MCP Servers
1. **mcp-image** (Nano Banana 2) — AI image generation via Google Gemini
2. **Zoho Mail MCP** (Composio) — Email read/send/reply (requires setup below)

### New Skills (Claude Code)
- `ad-copywriting` — Google Ads, Meta Ads, LinkedIn Ads, TikTok Ads copy
- `seo-content` — SEO-optimized blog posts, landing pages, keyword targeting
- `email-marketing` — drip sequences, newsletters, cold outreach, replies

### Updated Configs
- `agents/creative/CLAUDE.md` — Muse now has image gen + email + skill references
- `CLAUDE.md` — Task routing table updated with marketing-specific routes

---

## Setup Steps (Manager Action Required)

### Step 1: Get a Gemini API Key (for image generation)

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Sign in with your Google account
3. Click **"Create API key"**
4. Copy the key

Then add it to your shell environment:

```bash
echo 'export GEMINI_API_KEY="your-key-here"' >> ~/.zshenv
source ~/.zshenv
```

**Cost:** ~$0.04-$0.05 per image at standard resolution. Free tier available.

### Step 2: Set Up Zoho Mail MCP (for email read/send/reply)

#### Option A: Via Composio (Recommended — handles OAuth automatically)

1. Create a free account at [app.composio.dev](https://app.composio.dev)
2. Get your API key from Settings > API Keys
3. Install Composio:
   ```bash
   pip install composio-core
   ```
4. Run this to get the MCP URL:
   ```bash
   composio mcp --app zoho_mail
   ```
5. Add the MCP server to Claude Code:
   ```bash
   claude mcp add --transport http zoho_mail-composio "YOUR_MCP_URL" --scope user
   ```
6. First use will prompt you to authorize your Zoho account in the browser

#### Option B: Direct Zoho API (More control, more setup)

1. Go to [Zoho API Console](https://api-console.zoho.com/)
2. Create a **Self Client** application
3. Note your Client ID and Client Secret
4. Generate an auth code with scopes:
   ```
   ZohoMail.messages.ALL,ZohoMail.folders.ALL,ZohoMail.accounts.READ,ZohoMail.search.READ
   ```
5. Exchange for refresh token:
   ```bash
   curl -X POST "https://accounts.zoho.com/oauth/v2/token" \
     -d "client_id=YOUR_CLIENT_ID" \
     -d "client_secret=YOUR_CLIENT_SECRET" \
     -d "grant_type=authorization_code" \
     -d "code=YOUR_AUTH_CODE"
   ```
6. Store the refresh token securely in env vars

---

## Verification Checklist

After setup, test each capability:

- [ ] **Image generation:** Ask Muse to "generate a social media banner for Navaia"
- [ ] **Email read:** Ask to "list recent emails from info@navaia.sa"
- [ ] **Email send:** Ask to "draft and send a test email to yourself"
- [ ] **Email reply:** Ask to "reply to the latest email"
- [ ] **Ad copy:** Run `/ad-copywriting` skill
- [ ] **SEO content:** Run `/seo-content` skill
- [ ] **Email marketing:** Run `/email-marketing` skill

---

## Cost Summary

| Service | Cost | Notes |
|---------|------|-------|
| Nano Banana 2 (images) | ~$0.04-$0.05/image | Google Gemini, free tier available |
| Composio (Zoho MCP) | Free tier available | Handles OAuth, 1000 actions/month free |
| New skills | Free | Just prompt templates |
| Claude Code | Existing Max plan | No additional cost |
