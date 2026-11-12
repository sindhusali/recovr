"""Rupee formatting in the Indian style (lakh/crore grouping)."""


def format_inr(amount) -> str:
    """12500 -> '12,500', 125000 -> '1,25,000'. Shows paise only when not whole."""
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


def rupees(amount) -> str:
    """For display: '₹9,80,000'. Rounds to whole rupees."""
    return "₹" + format_inr(round(float(amount)))
