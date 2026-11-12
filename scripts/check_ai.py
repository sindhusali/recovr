"""Check that the Gemini key works, using an example message.

Run from the project folder:   python scripts\\check_ai.py
Prints the real error if something is wrong (the app itself hides errors and
falls back to the template).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.messaging.builder import validate_rewrite  # noqa: E402
from app.messaging.llm import build_prompt  # noqa: E402
from app.messaging.templates import render_template  # noqa: E402

CUSTOMER, SHOP, AMOUNT, DAYS = "Ravi Traders", "Sri Stores", 12500, 45

print(f"Model: {config.GEMINI_MODEL}")
if not config.ai_available():
    print("FAIL: no key found. Check that .env is in the project folder and has "
          "GEMINI_API_KEY=... (no quotes, no spaces).")
    raise SystemExit(1)
print(f"Key found (length {len(config.GEMINI_API_KEY)}).\n")

for lang, tone in [("en", "friendly"), ("te", "firm"), ("hi", "final")]:
    base = render_template(lang, tone, customer=CUSTOMER, shop=SHOP, amount=AMOUNT, days=DAYS)
    print(f"=== {lang} / {tone} ===")
    print("TEMPLATE:", base, flush=True)
    try:
        from google import genai
        from google.genai import types

        print(f"Calling Gemini (gives up after {config.AI_TIMEOUT_SECONDS}s)...", flush=True)
        client = genai.Client(
            api_key=config.GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=config.AI_TIMEOUT_SECONDS * 1000),
        )
        response = client.models.generate_content(
            model=config.GEMINI_MODEL, contents=build_prompt(base, tone, lang))
        out = (response.text or "").strip()
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}\n")
        continue
    print("AI REWRITE:", out)
    ok = validate_rewrite(base, out, customer=CUSTOMER, amount=AMOUNT)
    print("CHECK:", "PASS (safe to use)" if ok else
          "REJECTED (a fact changed; the app would use the template instead)", "\n")
