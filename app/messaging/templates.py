"""Fixed reminder templates. These are the source of truth and the fallback.

Placeholders: {customer} {shop} {amount} {days}
All values are filled in by code, never by the LLM.

NOTE: have a native Telugu / Hindi speaker review these before real use.
"""

LANGUAGES = {"en": "English", "te": "తెలుగు (Telugu)", "hi": "हिन्दी (Hindi)"}
TONES = ["friendly", "firm", "final"]

TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "friendly": (
            "Hello {customer}, this is a gentle reminder from {shop}. "
            "Your payment of ₹{amount} has been pending for {days} days. "
            "Kindly pay at your earliest convenience. Thank you!"
        ),
        "firm": (
            "Dear {customer}, your payment of ₹{amount} to {shop} is overdue by "
            "{days} days. Please clear it within 3 days. "
            "If there is any issue, kindly let us know."
        ),
        "final": (
            "Dear {customer}, this is a final reminder. ₹{amount} to {shop} has been "
            "overdue for {days} days. Please pay immediately or contact us today, "
            "otherwise we will not be able to give further credit."
        ),
    },
    "te": {
        "friendly": (
            "నమస్కారం {customer} గారు, {shop} నుండి చిన్న గుర్తు. "
            "మీ ₹{amount} చెల్లింపు {days} రోజులుగా పెండింగ్‌లో ఉంది. "
            "వీలైనంత త్వరగా చెల్లించగలరు. ధన్యవాదాలు!"
        ),
        "firm": (
            "{customer} గారు, {shop}కు మీరు చెల్లించాల్సిన ₹{amount} {days} రోజులు "
            "ఆలస్యమైంది. దయచేసి 3 రోజుల్లో చెల్లించండి. "
            "ఏదైనా సమస్య ఉంటే మాకు తెలియజేయండి."
        ),
        "final": (
            "{customer} గారు, ఇది చివరి గుర్తు. {shop}కు మీరు చెల్లించాల్సిన ₹{amount} "
            "{days} రోజులుగా బకాయి ఉంది. దయచేసి వెంటనే చెల్లించండి లేదా ఈ రోజే "
            "మమ్మల్ని సంప్రదించండి, లేకపోతే ఇకపై అరువు ఇవ్వడం కుదరదు."
        ),
    },
    "hi": {
        "friendly": (
            "नमस्ते {customer} जी, {shop} की ओर से एक छोटा सा रिमाइंडर। "
            "आपका ₹{amount} का भुगतान {days} दिनों से बाकी है। "
            "कृपया जल्द भुगतान करें। धन्यवाद!"
        ),
        "firm": (
            "{customer} जी, {shop} को आपका ₹{amount} का भुगतान {days} दिन से लंबित है। "
            "कृपया 3 दिन के भीतर भुगतान करें। कोई समस्या हो तो हमें बताएं।"
        ),
        "final": (
            "{customer} जी, यह अंतिम रिमाइंडर है। {shop} का ₹{amount} {days} दिनों से "
            "बकाया है। कृपया तुरंत भुगतान करें या आज ही हमसे संपर्क करें, "
            "नहीं तो आगे उधार देना संभव नहीं होगा।"
        ),
    },
}


def format_inr(amount) -> str:
    """12500 -> '12,500', 125000 -> '1,25,000' (Indian grouping)."""
    s = f"{float(amount):.2f}"
    whole, dec = s.split(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    out = ",".join([*groups, tail]) if groups else tail
    return out if dec == "00" else f"{out}.{dec}"


def render_template(language: str, tone: str, *, customer: str, shop: str,
                    amount, days: int) -> str:
    return TEMPLATES[language][tone].format(
        customer=customer, shop=shop, amount=format_inr(amount), days=days
    )
