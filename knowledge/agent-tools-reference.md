# Agent Tools & Skills Reference

## Creative Agent (Muse) Tools

### Image Generation (Nano Banana 2 via mcp-image)
- **Tool:** `generate_image` — generate marketing visuals from text prompts
- **Capabilities:** text-to-image, image editing, 4K output, quality presets (fast/balanced/quality)
- **Use for:** social media banners, ad creatives, blog hero images, product visuals, event graphics
- **Aspect ratios:** 1:1 (Instagram), 16:9 (YouTube/LinkedIn), 9:16 (Stories/Reels), 4:3, 3:4
- **Output:** saved to `workspace/outputs/images/`
- **Tips:**
  - Use `quality: "fast"` for drafts, `quality: "quality"` for final deliverables
  - Be specific in prompts — describe style, colors, mood, composition
  - Use `purpose` parameter (e.g., "Instagram post", "LinkedIn banner") for better results
  - Can edit existing images by providing `inputImagePath`

### Email (Zoho Mail via tools/zoho_mail.py)
- **Commands:**
  - `python tools/zoho_mail.py list` — list inbox emails
  - `python tools/zoho_mail.py read <message_id>` — read full email
  - `python tools/zoho_mail.py send --to "x" --subject "x" --body "x"` — send email
  - `python tools/zoho_mail.py reply <message_id> --body "x"` — reply to email
  - `python tools/zoho_mail.py search --query "keyword"` — search emails
  - `python tools/zoho_mail.py draft --to "x" --subject "x" --body "x"` — save draft
- **Account:** info@navaia.sa
- **Tips:**
  - Always draft emails to `workspace/outputs/creative/` first for review
  - Use email-marketing skill for copy frameworks
  - Body supports HTML for rich emails
  - Personalization tags: {{first_name}}, {{company}}, {{role}}

### Available Skills
- `/content-engine` — multi-platform content (X, LinkedIn, TikTok, YouTube, newsletters)
- `/article-writing` — long-form content, guides, blog posts
- `/ad-copywriting` — paid ad copy for Google, Meta, LinkedIn, TikTok
- `/seo-content` — SEO-optimized blog posts and landing pages
- `/email-marketing` — email sequences, drip campaigns, newsletters
- `/investor-materials` — pitch decks, one-pagers
- `/market-research` — competitive analysis, market sizing

## Technical Agent (Arch) Skills
- Full-stack: React/Next.js, Python/FastAPI, Node.js/Express
- Cloud: AWS (EC2, ECS, Lambda, RDS, S3, CloudFront, Route53)
- DevOps: Docker, GitHub Actions, Nginx
- Databases: PostgreSQL, Redis, DynamoDB

## Admin Agent (Sage) Skills
- Business documents: proposals, contracts, MOUs, NDAs, invoices
- Financial: budgets, P&L, cash flow, revenue forecasting (SAR)
- Research: market analysis, TAM/SAM/SOM, competitive landscape
- Saudi compliance: CR, GOSI, VAT (15%), PDPL
