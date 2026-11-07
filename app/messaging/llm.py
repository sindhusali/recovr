"""Thin Gemini wrapper. The LLM only REWRITES an already-correct message.

It never receives the ledger, and it never decides amounts, dates or names.
Any failure returns None so the caller falls back to the fixed template.
"""
from __future__ import annotations

from app import config

LANG_NAMES = {"en": "English", "te": "Telugu", "hi": "Hindi"}


def build_prompt(text: str, tone: str, language: str) -> str:
    return (
        f"Rewrite this payment reminder in {LANG_NAMES[language]} with a {tone} tone, "
        "as a polite shopkeeper would send on WhatsApp.\n"
        "Rules: keep every number, amount, name and shop name EXACTLY as written; "
        "write numbers using normal digits 0-9; do not add threats, legal claims, "
        "deadlines or any new facts; keep it under 60 words; "
        "return only the message text.\n\n"
        f"Message:\n{text}"
    )


def gemini_rewrite(text: str, tone: str, language: str) -> str | None:
    """Return a rewritten message, or None on any problem."""
    if not config.ai_available():
        return None
    try:
        import google.generativeai as genai

        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel(config.GEMINI_MODEL)
        response = model.generate_content(build_prompt(text, tone, language))
        out = (response.text or "").strip()
        return out or None
    except Exception:  # network, quota, safety block, missing package...
        return None
