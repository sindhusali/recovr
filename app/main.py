"""Streamlit UI only. All business logic lives in app/domain, ingestion, messaging.

Pattern used everywhere: AI proposes -> code validates -> the shopkeeper approves.
"""
import io
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
from app.ai.gemini import generate_json, generate_text  # noqa: E402
from app.domain.advice import ai_summary, facts_from_history, recommend  # noqa: E402
from app.domain.aging import aging_report, total_overdue  # noqa: E402
from app.domain.money import rupees  # noqa: E402
from app.domain.ranking import rank_customers  # noqa: E402
from app.ingestion.cleaning import apply_cleaning, suggest_merge  # noqa: E402
from app.ingestion.loader import COLUMN_ALIASES, REQUIRED, invoices_from_frame, read_ledger_table  # noqa: E402
from app.ingestion.quality import find_suspicious  # noqa: E402
from app.ingestion.smart_mapping import resolve_mapping  # noqa: E402
from app.messaging.builder import build_message  # noqa: E402
from app.messaging.llm import gemini_rewrite  # noqa: E402
from app.messaging.reply_parser import parse_reply  # noqa: E402
from app.messaging.templates import LANGUAGES, TONES  # noqa: E402
from app.messaging.whatsapp import phone_lookup, whatsapp_url  # noqa: E402
from app.storage import repo  # noqa: E402

SAMPLE = ROOT / "data" / "sample_ledger.csv"
DB = config.DB_PATH
NONE = "— none —"
FIELD_LABELS = {
    "customer": "Customer name", "amount": "Bill amount", "due_date": "Due date",
    "invoice_date": "Bill date", "invoice_no": "Bill number",
    "paid_amount": "Paid / received", "phone": "Phone number",
}
ACTION_ICONS = {"wait": "⏳", "message": "✉️", "call": "📞", "escalate": "🚨"}
INTENT_HINTS = {
    "promise_to_pay": "The promise is copied into the form below. Check it, then press Save promise.",
    "already_paid": "Check your cash or bank first. If it arrived, record it under Record money received.",
    "needs_documents": "Send the bill or statement again, then wait a few days.",
    "dispute": "Pause reminders and sort out the bill with the customer. A call usually works best.",
    "asks_extension": "Decide whether to agree a new date. If you do, record it as a promise.",
    "other": "Nothing to record automatically. Reply to the customer yourself.",
}


def flash_and_refresh(message: str) -> None:
    """Show a message after the page redraws, so advice above the button updates too."""
    st.session_state["_flash"] = message
    st.rerun()


@st.cache_data(show_spinner=False)
def read_frame(data: bytes, filename: str):
    return read_ledger_table(io.BytesIO(data), filename)


@st.cache_data(show_spinner="Checking columns...")
def get_suggestion(data: bytes, filename: str, use_ai: bool):
    return resolve_mapping(read_frame(data, filename), ai=generate_json if use_ai else None)


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
        "Use AI (wording, messy files, replies)", value=False, disabled=not config.ai_available(),
        help="Needs GEMINI_API_KEY in your .env file. The AI only proposes: "
             "code checks every result and you approve it. Ledger values are never sent "
             "for column matching.",
    )

    with st.expander("Privacy"):
        st.caption("Saved data stays on this computer. Only the last 4 digits of "
                   "phone numbers are stored, and customer replies are not saved.")
        confirm_erase = st.checkbox("I want to erase everything saved")
        if st.button("Erase all saved data", disabled=not confirm_erase):
            st.success("All saved data erased." if repo.erase_all(DB)
                       else "Nothing was saved yet.")

if uploaded is not None:
    data, filename = uploaded.getvalue(), uploaded.name
elif use_sample and SAMPLE.exists():
    data, filename = SAMPLE.read_bytes(), SAMPLE.name
else:
    st.info("Upload a ledger file, or tick the sample data box, to begin.")
    st.stop()

# ---- 1. read the file and work out which column is which -------------------------
try:
    df = read_frame(data, filename)
    suggestion = get_suggestion(data, filename, use_ai)
except Exception as exc:  # unreadable or empty file
    st.error(f"Could not read this file: {exc}")
    st.stop()

headers = [str(c) for c in df.columns]
by_ai = [f for f, s in suggestion.source.items() if s == "ai"]
needs_confirm = bool(suggestion.missing_required) or bool(by_ai)
with st.expander("Column mapping" + (" ⚠️ please check" if needs_confirm else " ✓"),
                 expanded=needs_confirm):
    if suggestion.missing_required:
        st.warning("I could not match every required column automatically. "
                   "Choose them below" + ("." if use_ai or not config.ai_available()
                                          else ", or tick 'Use AI' in the sidebar to get suggestions."))
    if by_ai:
        st.info("AI suggested: " + ", ".join(FIELD_LABELS[f] for f in by_ai)
                + ". Please check these against the preview before trusting the numbers.")
    mapping: dict[str, str] = {}
    cols = st.columns(len(COLUMN_ALIASES))
    for col, fld in zip(cols, COLUMN_ALIASES):
        options = [NONE] + headers
        current = suggestion.mapping.get(fld, NONE)
        choice = col.selectbox(FIELD_LABELS[fld] + (" *" if fld in REQUIRED else ""), options,
                               index=options.index(current) if current in options else 0,
                               key=f"map_{filename}_{fld}")
        if choice != NONE:
            mapping[fld] = choice
    st.caption("First rows of your file (as read):")
    st.dataframe(df.head(5), hide_index=True, width="stretch")

chosen = list(mapping.values())
if len(chosen) != len(set(chosen)):
    st.error("The same column is chosen for two different fields. Please fix the mapping.")
    st.stop()
missing = [FIELD_LABELS[f] for f in REQUIRED if f not in mapping]
if missing:
    st.error("Choose a column for: " + ", ".join(missing))
    st.stop()

try:
    result = invoices_from_frame(df, mapping)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

if not result.invoices:
    st.warning("No valid invoices were found in this file. Check the column mapping above.")
    st.stop()

# ---- 2. data checks: the shopkeeper decides what to skip or merge -----------------
flags = find_suspicious(result.invoices, as_of)
skip_rows: set[int] = set()
merges: dict[str, str] = {}
if flags:
    with st.expander(f"🔍 {len(flags)} thing(s) worth a look in your data"):
        st.caption("Tick a box to leave a row out of the totals, or to merge two names. "
                   "Your file is never changed, and unticking puts everything back.")
        boxed_rows: set[int] = set()
        for n, fl in enumerate(flags):
            if fl.kind == "names":
                keep, drop = suggest_merge(result.invoices, fl.customer, fl.other)
                st.write(f"- {fl.message}")
                if st.checkbox(f"Merge '{drop}' into '{keep}'", key=f"merge_{filename}_{n}"):
                    merges[drop] = keep
                continue
            where = f"Row {fl.row_number}: " if fl.row_number else ""
            st.write(f"- {where}**{fl.customer}**. {fl.message}")
            if fl.row_number is not None and fl.row_number not in boxed_rows:
                boxed_rows.add(fl.row_number)
                if st.checkbox(f"Leave row {fl.row_number} out of the totals",
                               key=f"skip_{filename}_{fl.row_number}"):
                    skip_rows.add(fl.row_number)

invoices = apply_cleaning(result.invoices, skip_rows, merges)
if skip_rows or merges:
    st.info(f"Totals below leave out {len(skip_rows)} row(s) and merge {len(merges)} name(s), "
            "as you chose above.")
if not invoices:
    st.warning("Every row has been left out. Untick some boxes above.")
    st.stop()

report = aging_report(invoices, as_of)
ranked = rank_customers(report)

c1, c2, c3 = st.columns(3)
c1.metric("Total overdue", rupees(total_overdue(invoices, as_of)))
c2.metric("Customers to chase", len(ranked))
c3.metric("Invoices counted", len(invoices))

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
    phones = phone_lookup(invoices)
    flash = st.session_state.pop("_flash", None)
    if flash:
        st.success(flash)
    pick = st.selectbox("Customer", ranked["customer"],
                        format_func=lambda c: f"{c}")
    row = ranked[ranked["customer"] == pick].iloc[0]
    outstanding = Decimal(str(row["overdue_amount"]))

    # ---- 3. next-best-action (rules over real history) ----------------------------
    facts = facts_from_history(
        repo.customer_history(DB, pick), days_overdue=int(row["max_days_overdue"]),
        overdue_amount=outstanding, today=as_of)
    action = recommend(facts, as_of)
    with st.container(border=True):
        st.markdown(f"**{ACTION_ICONS[action.kind]} Suggested next step: {action.headline}**")
        for reason in action.reasons:
            st.write(f"- {reason}")
        if use_ai:
            if st.button("Explain in plain words (AI)", key=f"explain_btn_{pick}"):
                st.session_state[f"explain_{pick}"] = ai_summary(action, facts, generate_text) \
                    or "AI explanation unavailable right now. The reasons above still apply."
            if st.session_state.get(f"explain_{pick}"):
                st.caption(st.session_state[f"explain_{pick}"])
        st.caption("This is advice only. You decide.")

    st.session_state.setdefault(f"tone_{pick}", action.tone or row["tone"])
    tone = st.radio("Tone", TONES, key=f"tone_{pick}", horizontal=True)

    text, src, note = make_draft(
        pick, shop, float(row["overdue_amount"]), int(row["max_days_overdue"]),
        tone, language, use_ai,
    )
    st.caption(f"Overdue {rupees(row['overdue_amount'])} · oldest {int(row['max_days_overdue'])} days"
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
            source=src, amount=outstanding,
            days_overdue=int(row["max_days_overdue"]),
            draft_text=text, final_text=final_text,
        )
        st.session_state["last_reminder_id"] = rid
        flash_and_refresh("Saved to the activity log.")

    # ---- 4. reading the customer's reply -------------------------------------------
    p_amount_key, p_date_key = f"p_amount_{pick}", f"p_date_{pick}"
    st.session_state.setdefault(p_amount_key, float(row["overdue_amount"]))
    st.session_state.setdefault(p_date_key, date.today())

    def read_reply() -> None:
        analysis = parse_reply(
            st.session_state.get(f"reply_{pick}", ""), today=date.today(),
            outstanding=outstanding, ai=generate_json if use_ai else None)
        st.session_state[f"analysis_{pick}"] = analysis
        if analysis.intent == "promise_to_pay":
            if analysis.promised_date:
                st.session_state[p_date_key] = analysis.promised_date
            if analysis.amount:
                st.session_state[p_amount_key] = float(analysis.amount)
        if analysis.summary or analysis.promised_date or analysis.amount:
            repo.log_reply_read(DB, customer=pick, intent=analysis.intent, source=analysis.source,
                                amount=analysis.amount, promised_date=analysis.promised_date)

    with st.expander("Customer replied? Paste their message"):
        st.text_area("Their reply (any language if AI is on)", key=f"reply_{pick}", height=90,
                     placeholder="e.g. I will pay 5000 on Friday")
        st.button("Read this reply", key="read_reply_btn", on_click=read_reply)
        a = st.session_state.get(f"analysis_{pick}")
        if a:
            st.markdown(f"**{a.label}** · read by {'AI (checked)' if a.source == 'ai' else 'simple rules'}")
            if a.summary:
                st.caption(a.summary)
            if a.amount or a.promised_date:
                amt = rupees(a.amount) if a.amount else "not stated"
                when = f"{a.promised_date:%d %b %Y}" if a.promised_date else "not stated"
                st.write(f"Amount: {amt} · Date: {when}")
            for w in a.warnings:
                st.warning(w)
            st.info(INTENT_HINTS[a.intent])

    with st.expander("Customer promised to pay? Record it"):
        p_amount = st.number_input("Promised amount (₹)", min_value=0.0, step=100.0, key=p_amount_key)
        p_date = st.date_input("Promised date", key=p_date_key)
        if st.button("Save promise", key="promise_btn"):
            if p_amount <= 0:
                st.error("Enter an amount above zero.")
            else:
                repo.add_promise(DB, customer=pick, amount=Decimal(str(p_amount)),
                                 promised_date=p_date,
                                 reminder_id=st.session_state.get("last_reminder_id"))
                flash_and_refresh("Promise saved. The suggested next step above is updated.")

st.subheader("Results so far")
stats = repo.summary(DB)
r1, r2, r3, r4 = st.columns(4)
r1.metric("Reminders sent", stats["reminders_sent"])
r2.metric("Promises pending", stats["promises_pending"],
          rupees(stats["promises_pending_amount"]), delta_color="off")
r3.metric("Promises kept", stats["promises_kept"])
r4.metric("Money recovered", rupees(stats["recovered_total"]))

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
        a.write(f"{p['customer']} · {rupees(p['amount'])} by {due:%d %b %Y}{late}")
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
