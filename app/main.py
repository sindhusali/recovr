"""Streamlit UI only. All business logic lives in app/domain, ingestion, messaging."""
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

# Make the project root importable, however the app is launched
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app import config  # noqa: E402
from app.domain.aging import aging_report, total_overdue  # noqa: E402
from app.domain.ranking import rank_customers  # noqa: E402
from app.ingestion.loader import load_invoices  # noqa: E402
from app.messaging.builder import build_message  # noqa: E402
from app.messaging.llm import gemini_rewrite  # noqa: E402
from app.messaging.templates import LANGUAGES, TONES  # noqa: E402
from app.messaging.whatsapp import phone_lookup, whatsapp_url  # noqa: E402
from app.storage import repo  # noqa: E402

SAMPLE = ROOT / "data" / "sample_ledger.csv"
DB = config.DB_PATH


@st.cache_data(show_spinner="Drafting message...")
def make_draft(customer, shop, amount, days, tone, language, use_ai):
    draft = build_message(
        customer=customer, shop=shop, amount=Decimal(str(amount)), days=int(days),
        tone=tone, language=language,
        rewriter=gemini_rewrite if use_ai else None,
    )
    return draft.text, draft.source, draft.note


st.set_page_config(page_title="recovr", page_icon="💰", layout="wide")
st.title("recovr")
st.caption("See who owes you money, and who to chase first.")

with st.sidebar:
    st.header("Ledger")
    uploaded = st.file_uploader("Upload CSV or Excel", type=["csv", "xlsx", "xls"])
    use_sample = st.checkbox("Use fake sample data", value=uploaded is None,
                             disabled=uploaded is not None)
    as_of = st.date_input("Calculate as of", value=date.today())
    st.header("Messages")
    shop = st.text_input("Your shop name", value=config.DEFAULT_SHOP_NAME)
    language = st.selectbox("Language", list(LANGUAGES), format_func=LANGUAGES.get)
    use_ai = st.checkbox(
        "Polish wording with AI", value=False, disabled=not config.ai_available(),
        help="Needs GEMINI_API_KEY in your .env file. Amounts are always checked.",
    )

    with st.expander("Privacy"):
        st.caption("Saved data stays on this computer. Only the last 4 digits of "
                   "phone numbers are stored.")
        confirm_erase = st.checkbox("I want to erase everything saved")
        if st.button("Erase all saved data", disabled=not confirm_erase):
            st.success("All saved data erased." if repo.erase_all(DB)
                       else "Nothing was saved yet.")

if uploaded is not None:
    source, filename = uploaded, uploaded.name
elif use_sample and SAMPLE.exists():
    source, filename = SAMPLE, SAMPLE.name
else:
    st.info("Upload a ledger file, or tick the sample data box, to begin.")
    st.stop()

try:
    result = load_invoices(source, filename)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

if not result.invoices:
    st.warning("No valid invoices were found in this file.")
    st.stop()

report = aging_report(result.invoices, as_of)
ranked = rank_customers(report)

c1, c2, c3 = st.columns(3)
c1.metric("Total overdue", f"₹{total_overdue(result.invoices, as_of):,.0f}")
c2.metric("Customers to chase", len(ranked))
c3.metric("Invoices loaded", len(result.invoices))

st.subheader("Chase these customers first")
st.dataframe(
    ranked,
    hide_index=True,
    width="stretch",
    column_config={
        "overdue_amount": st.column_config.NumberColumn("Overdue (₹)", format="%.0f"),
        "max_days_overdue": "Oldest (days)",
        "priority_score": st.column_config.NumberColumn("Priority", format="%.0f"),
    },
)

st.subheader("Reminder draft")
if ranked.empty:
    st.success("Nothing overdue. No reminders needed.")
else:
    phones = phone_lookup(result.invoices)
    pick = st.selectbox("Customer", ranked["customer"],
                        format_func=lambda c: f"{c}")
    row = ranked[ranked["customer"] == pick].iloc[0]
    tone = st.radio("Tone", TONES, index=TONES.index(row["tone"]), horizontal=True)

    text, src, note = make_draft(
        pick, shop, float(row["overdue_amount"]), int(row["max_days_overdue"]),
        tone, language, use_ai,
    )
    st.caption(f"Overdue ₹{row['overdue_amount']:,.0f} · oldest {int(row['max_days_overdue'])} days"
               f" · draft source: {'AI (checked)' if src == 'ai' else 'standard template'}")
    if note:
        st.warning(note)

    final_text = st.text_area("Review and edit before sending", value=text, height=140,
                              key=f"draft_{pick}_{tone}_{language}_{use_ai}")
    st.link_button("Open in WhatsApp (you tap send)", whatsapp_url(phones.get(pick), final_text))
    if pick not in phones:
        st.caption("No phone number found for this customer. WhatsApp will ask you to pick a contact.")

    if st.button("✅ I sent this message", key="sent_btn"):
        rid = repo.record_reminder(
            DB, customer=pick, phone=phones.get(pick), language=language, tone=tone,
            source=src, amount=Decimal(str(row["overdue_amount"])),
            days_overdue=int(row["max_days_overdue"]),
            draft_text=text, final_text=final_text,
        )
        st.session_state["last_reminder_id"] = rid
        st.success("Saved to the activity log.")

    with st.expander("Customer promised to pay? Record it"):
        p_amount = st.number_input("Promised amount (₹)", min_value=0.0, step=100.0,
                                   value=float(row["overdue_amount"]), key="p_amount")
        p_date = st.date_input("Promised date", value=date.today(), key="p_date")
        if st.button("Save promise", key="promise_btn"):
            if p_amount <= 0:
                st.error("Enter an amount above zero.")
            else:
                repo.add_promise(DB, customer=pick, amount=Decimal(str(p_amount)),
                                 promised_date=p_date,
                                 reminder_id=st.session_state.get("last_reminder_id"))
                st.success("Promise saved.")

st.subheader("Results so far")
stats = repo.summary(DB)
r1, r2, r3, r4 = st.columns(4)
r1.metric("Reminders sent", stats["reminders_sent"])
r2.metric("Promises pending", stats["promises_pending"],
          f"₹{stats['promises_pending_amount']:,.0f}", delta_color="off")
r3.metric("Promises kept", stats["promises_kept"])
r4.metric("Money recovered", f"₹{stats['recovered_total']:,.0f}")

with st.expander("Record money received"):
    names = list(ranked["customer"]) if not ranked.empty else []
    if names:
        m_customer = st.selectbox("Customer", names, key="m_customer")
        m_amount = st.number_input("Amount received (₹)", min_value=0.0, step=100.0, key="m_amount")
        m_date = st.date_input("Received on", value=date.today(), key="m_date")
        m_note = st.text_input("Note (optional)", key="m_note")
        if st.button("Save payment", key="recovery_btn"):
            if m_amount <= 0:
                st.error("Enter an amount above zero.")
            else:
                repo.add_recovery(DB, customer=m_customer, amount=Decimal(str(m_amount)),
                                  received_date=m_date, note=m_note)
                st.success("Payment saved.")
    else:
        st.caption("No overdue customers to record a payment for.")

pending = repo.list_promises(DB, "pending")
if pending:
    st.markdown("**Pending promises**")
    for p in pending[:20]:
        due = date.fromisoformat(p["promised_date"])
        late = " ⚠️ date passed" if due < date.today() else ""
        a, b, c = st.columns([5, 1, 1])
        a.write(f"{p['customer']} · ₹{p['amount']:,.0f} by {due:%d %b %Y}{late}")
        if b.button("Kept", key=f"kept_{p['id']}"):
            repo.set_promise_status(DB, p["id"], "kept")
            st.rerun()
        if c.button("Broken", key=f"broken_{p['id']}"):
            repo.set_promise_status(DB, p["id"], "broken")
            st.rerun()

with st.expander("Activity log (audit trail)"):
    events = repo.recent_activity(DB, 50)
    if events:
        st.dataframe([{"time (UTC)": e["ts"], "action": e["action"],
                       "customer": e["customer"]} for e in events],
                     hide_index=True, width="stretch")
    else:
        st.caption("Nothing yet.")

st.subheader("Aging by customer")
st.dataframe(report, hide_index=True, width="stretch")

if result.issues:
    with st.expander(f"⚠️ {len(result.issues)} row(s) skipped"):
        for issue in result.issues:
            st.write(f"Row {issue.row_number}: {issue.reason}")
if result.unmapped_columns:
    st.caption("Ignored columns: " + ", ".join(result.unmapped_columns))
