# AI Income Lab — Automated Blog Agent

> **"Real ways to earn with AI. No hype."**

Fully automated blog agent that posts 3 SEO articles/day to Blogger — 
runs 100% in GitHub Actions cloud. Zero local PC required after setup.

---

## How It Works

```
Every day at 9:00 AM IST (GitHub Actions):
  1. Fetches trending topics from HN + Google Trends + Reddit
  2. Analyzes 10 competitor blogs to find content gaps
  3. Selects 3 best topics (trend score × gap score)
  4. Generates full SEO articles via Gemini free API
  5. Publishes to Blogger automatically
  6. Saves results → commits to this repo
```

## One-Time Setup (~20 minutes)

### Step 1: Get Gemini API Key (free)
1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Click "Get API key" → Create → Copy the key

### Step 2: Enable Blogger API
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create project → Enable "Blogger API v3"
3. Create OAuth credentials (Desktop app) → download `credentials.json`
4. Place `credentials.json` in this folder

### Step 3: Run one-time auth (on your local PC)
```bash
pip install -r requirements.txt
python setup_auth.py
```
This opens your browser → log in → copies token to clipboard

### Step 4: Push to GitHub
```bash
git init
git add .
git commit -m "Initial blog agent"
git remote add origin https://github.com/YOUR_USERNAME/ai-income-lab.git
git push -u origin main
```

### Step 5: Add GitHub Secrets
Go to: **GitHub repo → Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Value |
|---|---|
| `GEMINI_API_KEY` | Your Gemini API key |
| `BLOGGER_BLOG_ID` | Your Blogger blog ID (shown by setup_auth.py) |
| `BLOGGER_TOKEN_B64` | The base64 string printed by setup_auth.py |

### Step 6: Done! ✅
GitHub Actions will trigger at 9:00 AM IST daily. No PC needed.

---

## Project Structure

```
blog-agent/
├── .github/workflows/blog_agent.yml  ← Cloud runner (GitHub Actions)
├── config/
│   ├── settings.py                   ← Configuration
│   ├── niches.json                   ← Topic categories
│   └── competitors.json              ← Blogs to monitor
├── agent/
│   ├── trend_fetcher.py              ← HN + Google Trends + Reddit
│   ├── competitor_analyzer.py        ← Learn from competitor blogs
│   ├── topic_selector.py             ← Smart topic selection
│   ├── article_generator.py          ← Gemini → SEO article
│   ├── publisher.py                  ← Blogger API
│   └── database.py                   ← Article history tracker
├── database/published_topics.json    ← Auto-updated by agent
├── scheduler.py                      ← Main orchestrator
├── setup_auth.py                     ← One-time local setup only
└── requirements.txt
```

## Income Timeline

| Month | Articles | Est. Traffic | Est. AdSense |
|---|---|---|---|
| 1 | 90 | 500–2,000 views | $5–20 |
| 3 | 270 | 8,000–20,000 views | $80–300 |
| 6 | 540 | 30,000–80,000 views | $300–1,500 |

*Traffic from US/UK/AU earns $15–50 RPM in AI+Finance niche*

## Free Tools Used
- Gemini API (1,500 free requests/day)
- Blogger (free hosting, Google-owned)
- GitHub Actions (free for public repos)
- HackerNews API (free, no key)
- Google Trends RSS (free)
- Reddit RSS (free)

**Monthly cost: $0**
