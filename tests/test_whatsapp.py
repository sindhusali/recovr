import pytest

from app.messaging.whatsapp import normalize_phone, whatsapp_url


@pytest.mark.parametrize("raw,expected", [
    ("9876543210", "919876543210"),
    ("+91 98765 43210", "919876543210"),
    ("09876543210", "919876543210"),
    ("919876543210", "919876543210"),
    ("12345", None),
    ("", None),
    (None, None),
])
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_url_encodes_message_and_includes_number():
    url = whatsapp_url("9876543210", "Pay ₹500 & thanks")
    assert url.startswith("https://wa.me/919876543210?text=")
    assert " " not in url and "&" not in url.split("text=")[1]


def test_missing_phone_still_gives_usable_link():
    assert whatsapp_url(None, "hi").startswith("https://wa.me/?text=")
