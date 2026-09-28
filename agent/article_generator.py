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
    BLOG_NAME, BLOG_TAGLINE, GEMINI_API_KEY, GEMINI_FALLBACK, GEMINI_MODEL,
    GEMINI_TEMPERATURE, MAX_WORD_COUNT, MIN_WORD_COUNT, SLOT_CONFIGS,
)

logger = logging.getLogger(__name__)

GEMINI_REST_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _build_prompt(topic: dict, competitor_analysis: dict, slot: str = "morning", recent_titles: list[str] = None) -> str:
    """
    Build a rich Gemini prompt incorporating:
    - Target topic and SEO keywords
    - Slot-based editorial archetype (Morning / Noon / Evening)
    - Strict anti-AI cliché rules for 100% human-grade uniqueness
    - Recent article memory to prevent repetitive angles
    """
    topic_text  = topic["topic"]
    keywords    = topic.get("keywords", [])
    niche       = topic.get("niche", "ai_finance_overlap")
    fmt         = topic.get("format", "how_to")
    patterns    = competitor_analysis.get("patterns", {})
    hot_kws     = patterns.get("hot_keywords", [])[:8]
    avg_words   = patterns.get("avg_title_words", 8)
    slot_cfg    = SLOT_CONFIGS.get(slot, SLOT_CONFIGS.get("morning", {}))

    # Format instructions with distinct structures
    format_instructions = {
        "market_breakdown": (
            "Write a sharp, high-signal market & technology analysis.\n"
            "Structure:\n"
            "1. <h2>The Core Signal: What Just Happened</h2> (Direct, factual hook)\n"
            "2. <h2>Why This Shift Matters for Income & Business</h2> (Economic & productivity impact)\n"
            "3. <h2>Winners vs. Losers Comparison Table</h2> (Use a clean HTML <table> with <th> and <td> tags)\n"
            "4. <h2>3 Strategic Moves to Capitalize on This Now</h2> (Actionable, no-fluff steps)\n"
            "5. <h2>Frequently Asked Questions</h2> (4 concise FAQ answers)"
        ),
        "how_to": (
            "Write a practical, hands-on masterclass / tutorial.\n"
            "Structure:\n"
            "1. <h2>Quick Overview & Prerequisites Checklist</h2> (What you need before starting)\n"
            "2. <h2>Step-by-Step Implementation Blueprint</h2> (Numbered steps with <h3> headings and real tool settings)\n"
            "3. <h2>Cost vs. Expected Return Breakdown</h2> (Realistic numbers and time investment)\n"
            "4. <h2>Common Pitfalls & How to Avoid Them</h2>\n"
            "5. <h2>Frequently Asked Questions</h2> (4 concise FAQ answers)"
        ),
        "case_study": (
            "Write an engaging, narrative case study & playbook.\n"
            "Structure:\n"
            "1. <h2>The Story & Setup: Breaking Down the Scenario</h2> (Human narrative, real stakes)\n"
            "2. <h2>The Strategy & Unit Economics</h2> (Transparent breakdown of tools and math)\n"
            "3. <h2>The Replicable Framework for Beginners</h2> (3-step actionable process)\n"
            "4. <h2>Key Lessons Learned & Hard Truths</h2>\n"
            "5. <h2>Discussion & Frequently Asked Questions</h2> (4 questions with answers)"
        ),
        "listicle": (
            "Write a curated, high-value roundup listicle (e.g. 5 Best... or 7 Ways...).\n"
            "Each item MUST have a bold <h3> heading, 2-3 sentences of evaluation, an 'Ideal For' line, and a 'Practical Caveat'."
        ),
        "review": (
            "Write a balanced, critical review and comparison.\n"
            "Include features, real pricing tiers, pros & cons lists (<ul>), and a definitive verdict."
        ),
    }
    fmt_instruction = format_instructions.get(fmt, format_instructions["how_to"])

    # Recent titles memory
    recent_memory_block = ""
    if recent_titles:
        titles_preview = "\n".join(f"- {t}" for t in recent_titles[:6])
        recent_memory_block = f"""
RECENT ARTICLES ALREADY PUBLISHED ON THIS BLOG (DO NOT REPEAT THEIR ANGLES OR PHRASINGS):
{titles_preview}
"""

    related_kw_str = ", ".join(hot_kws[:6]) if hot_kws else "AI, income, tools, productivity"

    return f"""You are a professional digital journalist and entrepreneur writing for "{BLOG_NAME}" ({BLOG_TAGLINE}).
EDITION: {slot_cfg.get("name", "Daily Feature")}

TODAY'S TOPIC: {topic_text}
PRIMARY SEO KEYWORDS (incorporate naturally): {", ".join(keywords)}
RELATED KEYWORDS: {related_kw_str}

ARTICLE FORMAT:
{fmt_instruction}

STRICT ANTI-AI & HUMAN WRITING RULES:
1. FORBIDDEN PHRASES (NEVER use any of these):
   "In this comprehensive guide", "In today's fast-paced digital world", "delve into", "tapestry",
   "game changer", "revolutionary", "look no further", "navigating the complex world of",
   "at the end of the day", "it's crucial to remember", "a testament to".
2. NO GENERIC OPENING QUESTIONS: Do NOT start with "Have you ever wondered...?" or "Are you looking for...?".
   Open immediately with a striking fact, a concrete figure, or a direct observation.
3. CONCRETE DETAILS: Name specific tools, realistic prices (e.g., "$20/mo", "free tier with 50 credits"),
   and real benchmarks. Avoid vague advice like "utilize smart software".
4. WORD COUNT: {MIN_WORD_COUNT}–{MAX_WORD_COUNT} words. Every paragraph must provide clear value.
5. NO FAKE DATA: State "based on industry testing" or "according to standard benchmarks".
{recent_memory_block}
RETURN FORMAT — Valid JSON only (no markdown code fences):
{{
  "title": "high-CTR, compelling article title (50-65 chars, primary keyword included)",
  "meta_description": "engaging meta description for Google search (150-160 chars)",
  "labels": ["tag1", "tag2", "tag3", "tag4"],
  "html_content": "Full article HTML starting directly with <h2>. Use clean HTML: <h2>, <h3>, <p>, <ul>, <ol>, <li>, <strong>, <table>, <tr>, <th>, <td>. Do NOT include <html>, <head>, or <body> tags."
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
        # Exclude audio, tts, realtime, and omni preview models that have restrictive rate limits
        filtered = [
            m for m in discovered
            if not any(x in m for x in ("tts", "embedding", "omni", "audio", "realtime", "live"))
        ]
        # Prioritize standard text flash models (e.g. gemini-flash-latest, gemini-2.5-flash), then lite, then others
        flash = sorted([m for m in filtered if "flash" in m and "lite" not in m], reverse=True)
        lite = sorted([m for m in filtered if "lite" in m], reverse=True)
        others = sorted([m for m in filtered if "flash" not in m], reverse=True)
        _cached_models = flash + lite + others
        logger.info("Discovered available Gemini models: %s", _cached_models[:5])
        return _cached_models

    _cached_models = [
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
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


def _build_full_html(article_data: dict, topic: dict, slot: str = "morning") -> str:
    """
    Wrap the Gemini-generated HTML content in a clean blog post structure.
    Adds a publication date, niche tag, and subtle branding styled specifically
    for this edition (Morning / Noon / Evening).
    """
    title       = article_data.get("title", topic["topic"])
    html_body   = article_data.get("html_content", "<p>Article content unavailable.</p>")
    niche_label = topic.get("niche", "").replace("_", " ").title()
    pub_date    = datetime.now().strftime("%B %d, %Y")

    slot_cfg    = SLOT_CONFIGS.get(slot, SLOT_CONFIGS.get("morning", {}))
    bg_gradient = slot_cfg.get("bg_gradient", "linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #1e3a8a 100%)")
    badge_bg    = slot_cfg.get("badge_bg", "#2563eb")
    primary_col = slot_cfg.get("primary_color", "#2563eb")
    slot_name   = slot_cfg.get("name", "Daily Intelligence")

    header_block = f"""
<div style="background: {bg_gradient};
            padding: 2.2rem; border-radius: 14px; margin-bottom: 2rem; color: #ffffff; box-shadow: 0 4px 20px rgba(0,0,0,0.12);">
  <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 0.8rem; flex-wrap: wrap;">
    <span style="background: {badge_bg}; padding: 4px 12px; border-radius: 20px;
                 font-size: 0.75rem; font-weight: 700; text-transform: uppercase;
                 letter-spacing: 1px; color: #ffffff;">{niche_label}</span>
    <span style="opacity: 0.85; font-size: 0.82rem; letter-spacing: 0.5px; font-weight: 500;">&bull; {slot_name}</span>
  </div>
  <p style="margin: 0; opacity: 0.8; font-size: 0.9rem;">
    Published {pub_date} &middot; {BLOG_NAME}
  </p>
</div>
"""

    footer_block = f"""
<hr style="margin: 2.5rem 0; border: none; border-top: 1px solid #e2e8f0;">
<div style="background: #f8fafc; padding: 1.8rem; border-radius: 10px;
            border-left: 5px solid {primary_col}; box-shadow: 0 2px 10px rgba(0,0,0,0.03);">
  <strong style="font-size: 1.05rem; color: #0f172a;">💡 Actionable Next Step</strong>
  <p style="margin: 0.5rem 0 1.2rem; color: #475569; font-size: 0.95rem; line-height: 1.6;">
    Real income comes from implementation, not just reading. Test one concept or tool from this guide today.
  </p>
  <div style="display: flex; gap: 10px; flex-wrap: wrap; align-items: center;">
    <a href="#" style="background: {primary_col}; color: #ffffff; padding: 9px 18px; border-radius: 6px; text-decoration: none; font-size: 0.88rem; font-weight: 600; display: inline-block;">
      Subscribe to Free Weekly Newsletter
    </a>
    <span style="color: #64748b; font-size: 0.85rem;">&bull; Free tools &amp; tactical income frameworks</span>
  </div>
</div>
"""

    return header_block + html_body + footer_block


def generate_article(
    topic: dict,
    competitor_analysis: dict,
    slot: str = "morning",
    recent_titles: list[str] = None,
) -> dict | None:
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
        "slot":             str,
    }
    Or None on failure.
    """
    api_key = GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        logger.error("GEMINI_API_KEY not set")
        return None

    logger.info("Generating article for slot [%s]: %s", slot, topic["topic"][:70])

    prompt = _build_prompt(topic, competitor_analysis, slot=slot, recent_titles=recent_titles)
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
    full_html = _build_full_html(article_data, topic, slot=slot)
    article_data["html_content"] = full_html
    article_data["keywords"] = topic.get("keywords", [])
    article_data["niche"] = topic.get("niche", "")
    article_data["slot"] = slot

    logger.info(
        "Article generated: '%s' | ~%d words | labels: %s",
        article_data.get("title", "?")[:60],
        word_count,
        article_data.get("labels", []),
    )
    return article_data
