import pytest

from app.messaging.templates import (
    LANGUAGES, TEMPLATES, TONES, format_inr, render_template,
)


@pytest.mark.parametrize("lang", list(LANGUAGES))
@pytest.mark.parametrize("tone", TONES)
def test_every_language_and_tone_renders_with_all_facts(lang, tone):
    text = render_template(lang, tone, customer="Ravi Traders", shop="Sri Stores",
                           amount=12500, days=45)
    assert "Ravi Traders" in text
    assert "Sri Stores" in text
    assert "12,500" in text
    assert "45" in text
    assert "{" not in text  # no unfilled placeholder


def test_all_languages_have_all_tones():
    for lang in LANGUAGES:
        assert set(TEMPLATES[lang]) == set(TONES)


@pytest.mark.parametrize("amount,expected", [
    (500, "500"), (12500, "12,500"), (125000, "1,25,000"),
    (1234567, "12,34,567"), (1250.5, "1,250.50"),
])
def test_indian_number_format(amount, expected):
    assert format_inr(amount) == expected
