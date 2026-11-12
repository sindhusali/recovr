"""Shared Gemini helpers. Every call has a time limit and fails soft (returns None).

Callers must treat the result as an untrusted PROPOSAL and validate it in code.
"""
from __future__ import annotations

import json
import re

from app import config


def parse_json(text: str | None):
    """Parse model output into JSON, tolerating ```json fences. None if invalid."""
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    try:
        return json.loads(cleaned)
    except (ValueError, TypeError):
        return None


def _generate(prompt: str, *, json_mode: bool) -> str | None:
    if not config.ai_available():
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=config.GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=config.AI_TIMEOUT_SECONDS * 1000),
        )
        cfg = types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json" if json_mode else None,
        )
        response = client.models.generate_content(
            model=config.GEMINI_MODEL, contents=prompt, config=cfg)
        return (response.text or "").strip() or None
    except Exception:  # network, quota, safety block, missing package...
        return None


def generate_json(prompt: str):
    """Return parsed JSON (dict or list), or None on any problem."""
    return parse_json(_generate(prompt, json_mode=True))


def generate_text(prompt: str) -> str | None:
    return _generate(prompt, json_mode=False)
