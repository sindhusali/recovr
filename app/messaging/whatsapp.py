"""WhatsApp click-to-chat links. Nothing is sent automatically: the shopkeeper
opens the link and taps send themselves."""
from __future__ import annotations

import re
from urllib.parse import quote

from app.domain.models import Invoice


def normalize_phone(raw: str) -> str | None:
    """Return digits with India country code (91XXXXXXXXXX), or None if unusable."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10:
        return "91" + digits
    if len(digits) == 11 and digits.startswith("0"):
        return "91" + digits[1:]
    if len(digits) == 12 and digits.startswith("91"):
        return digits
    return None


def whatsapp_url(phone: str | None, text: str) -> str:
    """With a valid number opens that chat; otherwise lets the user pick a contact."""
    number = normalize_phone(phone or "")
    base = f"https://wa.me/{number}" if number else "https://wa.me/"
    return f"{base}?text={quote(text)}"


def phone_lookup(invoices: list[Invoice]) -> dict[str, str]:
    """First non-empty phone number per customer."""
    phones: dict[str, str] = {}
    for inv in invoices:
        if inv.phone and inv.customer not in phones:
            phones[inv.customer] = inv.phone
    return phones
