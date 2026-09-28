"""
article_generator.py — Generate full SEO-optimized blog articles using Gemini.

For each topic, builds a rich prompt that includes:
  - Topic + primary keywords
  - Competitor patterns (format, style, depth) learned today
  - SEO structure requirements
  - Niche context and blog voice

Returns a complete HTML article ready to publish to Blogger.
"""

import logging
import os
import re
import time
from datetime import datetime

import requests

from config.settings import (
    BLOG_NAME, GEMINI_API_KEY, GEMINI_FALLBACK, GEMINI_MODEL,
    GEMINI_TEMPERATURE, MAX_WORD_COUNT, MIN_WORD_COUNT,
)

logger = logging.getLogger(__name__)

GEMINI_REST_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _build_prompt(topic: dict, competitor_analysis: dict) -> str:
    """
    Build a detailed Gemini prompt that incorporates:
    - The target topic and keywords
    - Competitor format/style patterns learned today
    - SEO article structure
    - Blog voice guidelines
    """
    topic_text  = topic["topic"]
    keywords    = topic.get("keywords", [])
    niche       = topic.get("niche", "ai_finance_overlap")
    fmt         = topic.get("format", "listicle")
    patterns    = competitor_analysis.get("patterns", {})
    hot_kws     = patterns.get("hot_keywords", [])[:8]
    avg_words   = patterns.get("avg_title_words", 8)

    # Format instruction
    format_instructions = {
        "listicle":    "Write a numbered list article (e.g., '7 Best...' or '5 Ways to...'). Each item should have a bold H3 heading, 2-3 sentences of explanation, and a practical tip.",
        "how_to":      "Write a step-by-step how-to guide. Use numbered steps with H3 headings. Include a 'Before You Start' section and a 'Common Mistakes' section.",
        "educational": "Write an educational explainer article. Start with a simple definition, then go deeper. Use real-world examples and comparisons.",
        "review":      "Write a balanced review/comparison article. Include pros, cons, pricing, and a final verdict section.",
        "roundup":     "Write a roundup article covering the latest developments. Include context, key players, and practical implications for readers.",
        "general":     "Write an informative article with clear H2 sections. Balance education with actionable advice.",
    }
    fmt_instruction = format_instructions.get(fmt, format_instructions["general"])

    # Niche voice
    niche_voices = {
        "ai_tools":          "You write for people who want to use AI tools practically — busy professionals and side hustlers who need clear, no-fluff guidance.",
        "personal_finance":  "You write for people building financial freedom — practical advice, real numbers, no jargon.",
        "ai_finance_overlap": "You write for people who want to use AI to improve their finances and build income — the intersection of technology and money.",
    }
    voice = niche_voices.get(niche, niche_voices["ai_finance_overlap"])

    # Related keywords from competitor trends to weave in naturally
    related_kw_str = ", ".join(hot_kws[:6]) if hot_kws else "AI, income, tools, productivity"

    return f"""You are a professional blogger writing for "{BLOG_NAME}" — a blog with the tagline "Real ways to earn with AI. No hype."

BLOG VOICE: {voice}

TODAY'S ARTICLE TOPIC: {topic_text}

PRIMARY SEO KEYWORDS (use naturally throughout): {", ".join(keywords)}
RELATED KEYWORDS (weave in where natural): {related_kw_str}

FORMAT REQUIREMENT:
{fmt_instruction}

ARTICLE REQUIREMENTS:
1. Word count: {MIN_WORD_COUNT}–{MAX_WORD_COUNT} words
2. Title: {int(avg_words)+2}–{int(avg_words)+5} words, include primary keyword, no clickbait
3. Structure: Introduction → Main content (H2/H3 sections) → FAQ (5 questions) → Conclusion with CTA
4. Writing style: Conversational, direct, factual. NO fluff. Every sentence must add value.
5. Include at least ONE specific example or real tool/number to make it concrete
6. End each major section with one actionable takeaway
7. FAQ section: 5 real questions people ask, with concise answers (40-60 words each)
8. CTA in conclusion: Invite readers to comment, share, or subscribe to newsletter
9. DO NOT use fake statistics. If citing data, say "according to [general knowledge]"
10. DO NOT include affiliate links (leave placeholder: [AFFILIATE_PLACEHOLDER])

RETURN FORMAT — Respond with valid JSON only (no markdown wrapper):
{{
  "title": "exact article title (55-60 chars ideal)",
  "meta_description": "compelling 150-160 char description for Google search results",
  "labels": ["tag1", "tag2", "tag3", "tag4"],
  "html_content": "FULL article HTML starting with <h2> (NOT <h1>, title is separate). Include proper HTML: <h2>, <h3>, <strong>, <ul>, <ol>, <li>, <p> tags. Do NOT include <html>, <head>, or <body> tags."
}}"""


_cached_models: list[str] = []


def _get_available_models(api_key: str) -> list[str]:
    """Dynamically query Google Gemini API for available models that support generateContent."""
    global _cached_models
    if _cached_models:
        return _cached_models

    discovered = []
    try:
        url = f"{GEMINI_REST_BASE}?key={api_key}"
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            for m in resp.json().get("models", []):
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" in methods:
                    name = m.get("name", "").replace("models/", "")
                    if "gemini" in name:
                        discovered.append(name)
    except Exception as e:
        logger.warning("Could not dynamically query Gemini models: %s", e)

    if discovered:
        # Prioritize flash models, sorted descending (e.g. 2.5 before 2.0 before 1.5)
        flash = sorted([m for m in discovered if "flash" in m], reverse=True)
        others = sorted([m for m in discovered if "flash" not in m], reverse=True)
        _cached_models = flash + others
        logger.info("Discovered available Gemini models: %s", _cached_models[:5])
        return _cached_models

    _cached_models = [
        GEMINI_MODEL,
        GEMINI_FALLBACK,
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash-latest",
        "gemini-1.5-flash",
        "gemini-pro",
    ]
    return _cached_models


def _call_gemini(prompt: str, api_key: str) -> dict | None:
    """Call Gemini REST API, return parsed JSON or None."""
    models = _get_available_models(api_key)

    for model in models:
        url = f"{GEMINI_REST_BASE}/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": GEMINI_TEMPERATURE,
                "maxOutputTokens": 4096,
                "response_mime_type": "application/json",
            },
        }
        try:
            resp = requests.post(url, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            raw = (
                data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                    .strip()
            )
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = "\n".join(
                    l for l in raw.split("\n") if not l.strip().startswith("```")
                ).strip()
            # Extract JSON object
            start, end = raw.find("{"), raw.rfind("}")
            if start != -1 and end > start:
                raw = raw[start:end + 1]
            import json
            parsed = json.loads(raw)
            logger.info("Gemini [%s] generated: %s", model, parsed.get("title", "?")[:60])
            return parsed
        except requests.HTTPError as e:
            logger.warning("Gemini HTTP error [%s]: %s", model, e)
        except Exception as e:
            logger.warning("Gemini call failed [%s]: %s", model, e)
        time.sleep(1)

    return None


def _build_full_html(article_data: dict, topic: dict) -> str:
    """
    Wrap the Gemini-generated HTML content in a clean blog post structure.
    Adds a publication date, niche tag, and subtle branding.
    """
    title       = article_data.get("title", topic["topic"])
    html_body   = article_data.get("html_content", "<p>Article content unavailable.</p>")
    niche_label = topic.get("niche", "").replace("_", " ").title()
    pub_date    = datetime.now().strftime("%B %d, %Y")

    # Add responsive image placeholder (first paragraph area)
    # In Phase 3 we can add real images via Unsplash API
    header_block = f"""
<div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            padding: 2rem; border-radius: 12px; margin-bottom: 2rem; color: white;">
  <span style="background: #e94560; padding: 4px 12px; border-radius: 20px;
               font-size: 0.8rem; font-weight: bold; text-transform: uppercase;
               letter-spacing: 1px;">{niche_label}</span>
  <p style="margin: 0.8rem 0 0; opacity: 0.75; font-size: 0.9rem;">
    Published {pub_date} &middot; {BLOG_NAME}
  </p>
</div>
"""

    footer_block = """
<hr style="margin: 2rem 0; border-color: #eee;">
<div style="background: #f8f9fa; padding: 1.5rem; border-radius: 8px;
            border-left: 4px solid #e94560;">
  <strong>&#128161; Found this useful?</strong>
  Share it with someone building their side income. And
  <a href="#" style="color: #e94560;">subscribe to our newsletter</a>
  for weekly AI &amp; finance tips — straight to your inbox.
</div>
"""

    return header_block + html_body + footer_block


def generate_article(topic: dict, competitor_analysis: dict) -> dict | None:
    """
    Main entry point: generate a complete, publish-ready article.

    Returns:
    {
        "title":            str,
        "meta_description": str,
        "labels":           [str],
        "html_content":     str,   # full HTML ready for Blogger
        "keywords":         [str],
        "niche":            str,
    }
    Or None on failure.
    """
    api_key = GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        logger.error("GEMINI_API_KEY not set")
        return None

    logger.info("Generating article: %s", topic["topic"][:70])

    prompt = _build_prompt(topic, competitor_analysis)
    article_data = _call_gemini(prompt, api_key)

    if not article_data:
        logger.error("Gemini failed to generate article for: %s", topic["topic"])
        return None

    # Validate minimum quality
    html = article_data.get("html_content", "")
    word_count = len(re.sub(r"<[^>]+>", "", html).split())
    if word_count < 300:
        logger.warning("Article too short (%d words) for: %s", word_count, topic["topic"])
        return None

    # Build full HTML with header/footer
    full_html = _build_full_html(article_data, topic)
    article_data["html_content"] = full_html
    article_data["keywords"] = topic.get("keywords", [])
    article_data["niche"] = topic.get("niche", "")

    logger.info(
        "Article generated: '%s' | ~%d words | labels: %s",
        article_data.get("title", "?")[:60],
        word_count,
        article_data.get("labels", []),
    )
    return article_data
