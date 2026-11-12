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
        "Rules:\n"
        "- Keep every person name and shop name EXACTLY as written, in the same "
        "letters. Never translate or transliterate names into another script "
        "(for example, keep 'Ravi Traders' in English letters even inside Telugu "
        "or Hindi text).\n"
        "- Keep every number and amount exactly as written, using normal digits 0-9.\n"
        "- Do not add threats, legal claims, deadlines or any new facts.\n"
        "- Keep it under 60 words.\n"
        "- Return only the message text.\n\n"
        f"Message:\n{text}"
    )


def gemini_rewrite(text: str, tone: str, language: str) -> str | None:
    """Return a rewritten message, or None on any problem."""
    if not config.ai_available():
        return None
    try:
        from google import genai
        from google.genai import types

        # Hard time limit so a slow network can never freeze the app
        client = genai.Client(
            api_key=config.GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=config.AI_TIMEOUT_SECONDS * 1000),
        )
        response = client.models.generate_content(
            model=config.GEMINI_MODEL, contents=build_prompt(text, tone, language)
        )
        out = (response.text or "").strip()
        return out or None
    except Exception:  # network, quota, safety block, missing package...
        return None
