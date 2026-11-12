"""Settings, loaded from environment / .env. Never hard-code keys."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "20"))
DEFAULT_SHOP_NAME = os.getenv("SHOP_NAME", "Our Shop")
# SQLite file. *.db is git-ignored, so shop data never reaches GitHub.
DB_PATH = Path(os.getenv("RECOVR_DB", ROOT / "data" / "real" / "recovr.db"))


def ai_available() -> bool:
    return bool(GEMINI_API_KEY) and GEMINI_API_KEY != "your_key_here"
