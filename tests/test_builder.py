from app.messaging.builder import build_message, numbers_in

ARGS = dict(customer="Ravi Traders", shop="Sri Stores", amount=12500, days=45,
            tone="firm", language="en")


def test_no_rewriter_uses_template():
    d = build_message(**ARGS)
    assert d.source == "template"
    assert "12,500" in d.text


def test_valid_rewrite_is_accepted():
    good = ("Hi Ravi Traders, your ₹12,500 to Sri Stores is 45 days late. "
            "Please pay within 3 days.")
    d = build_message(**ARGS, rewriter=lambda t, tone, lang: good)
    assert d.source == "ai"
    assert d.text == good


def test_rewrite_with_wrong_amount_is_rejected():
    bad = "Dear Ravi Traders, please pay ₹15,000 to Sri Stores, overdue 45 days. Pay in 3 days."
    d = build_message(**ARGS, rewriter=lambda t, tone, lang: bad)
    assert d.source == "template"
    assert "12,500" in d.text
    assert d.note


def test_rewrite_with_invented_number_is_rejected():
    bad = "Ravi Traders, pay ₹12,500 to Sri Stores (45 days late) within 7 days."
    d = build_message(**ARGS, rewriter=lambda t, tone, lang: bad)
    assert d.source == "template"


def test_rewrite_missing_customer_name_is_rejected():
    bad = "Please pay ₹12,500, overdue 45 days. Pay in 3 days."
    d = build_message(**ARGS, rewriter=lambda t, tone, lang: bad)
    assert d.source == "template"


def test_rewrite_using_non_ascii_digits_is_rejected():
    bad = "Ravi Traders, ₹१२,५०० overdue. Pay in 3 days. 45"
    d = build_message(**ARGS, rewriter=lambda t, tone, lang: bad)
    assert d.source == "template"


def test_rewriter_exception_falls_back():
    def boom(*a):
        raise RuntimeError("API down")
    d = build_message(**ARGS, rewriter=boom)
    assert d.source == "template"


def test_rewriter_returning_none_falls_back():
    d = build_message(**ARGS, rewriter=lambda *a: None)
    assert d.source == "template"


def test_empty_or_huge_rewrite_rejected():
    assert build_message(**ARGS, rewriter=lambda *a: "  ").source == "template"
    assert build_message(**ARGS, rewriter=lambda *a: "x" * 5000).source == "template"


def test_numbers_in_ignores_commas_and_punctuation():
    assert numbers_in("Pay ₹12,500, in 3 days.") == {"12500", "3"}
