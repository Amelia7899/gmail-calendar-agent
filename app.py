from pathlib import Path
from urllib.parse import urlencode

import streamlit as st

from agent.event_extractor import (
    extract_events_from_emails,
    get_extractor_status,
    llm_extractor_enabled,
)
from agent.gmail_reader import (
    DEFAULT_CREDENTIALS_PATH,
    GmailReaderError,
    create_authorization_url,
    read_recent_emails,
    save_token_from_callback,
    token_exists,
)


BASE_DIR = Path(__file__).resolve().parent
SAMPLE_EMAIL_DIR = BASE_DIR / "data" / "sample_emails"
GMAIL_REDIRECT_URI = "http://localhost:8501/"
DECISION_LABELS = {
    "pending": "Pending review",
    "confirmed": "Confirmed",
    "skipped": "Skipped",
}


def read_sample_emails() -> list[dict[str, str]]:
    emails = []

    for path in sorted(SAMPLE_EMAIL_DIR.glob("*.txt")):
        raw_text = path.read_text(encoding="utf-8").strip()
        lines = raw_text.splitlines()
        subject = "No subject"

        for line in lines:
            if line.lower().startswith("subject:"):
                subject = line.split(":", 1)[1].strip()
                break

        body_lines = [
            line
            for line in lines
            if not line.lower().startswith(("subject:", "from:"))
        ]
        body = "\n".join(body_lines).strip()

        emails.append(
            {
                "id": path.stem,
                "subject": subject,
                "body": body,
                "source": path.name,
            }
        )

    return emails


def scan_emails(emails: list[dict[str, str]], source_label: str, use_llm: bool) -> None:
    schedule_items = extract_events_from_emails(emails, use_llm=use_llm)
    st.session_state["schedule_items"] = schedule_items
    st.session_state["event_decisions"] = ["pending"] * len(schedule_items)
    st.session_state["schedule_source"] = source_label
    st.session_state["last_scan_email_count"] = len(emails)
    st.session_state["last_scan_event_count"] = len(schedule_items)
    st.session_state["last_extractor_status"] = get_extractor_status()


def mark_event(index: int, decision: str) -> None:
    decisions = st.session_state.get("event_decisions", [])

    if index < len(decisions):
        decisions[index] = decision
        st.session_state["event_decisions"] = decisions


def decision_badge(decision: str) -> None:
    label = DECISION_LABELS.get(decision, "Pending review")

    if decision == "confirmed":
        st.success(label)
    elif decision == "skipped":
        st.warning(label)
    else:
        st.info(label)


def preview_event(event: dict[str, str], index: int, decision: str) -> None:
    with st.container(border=True):
        header, status = st.columns([3, 1])
        header.markdown(f"**{event.get('title', 'Untitled event')}**")
        with status:
            decision_badge(decision)

        date_col, time_col, location_col, source_col = st.columns(4)
        date_col.caption("Date")
        date_col.write(event.get("date", "Needs review"))
        time_col.caption("Time")
        time_col.write(event.get("time", "Needs review"))
        location_col.caption("Location")
        location_col.write(event.get("location", "Needs review"))
        source_col.caption("Source email")
        source_col.write(event.get("source_email", "sample email"))

        with st.expander("Description"):
            st.write(event.get("description", "No description"))

        confirm_col, skip_col, _ = st.columns([1, 1, 4])
        confirm_col.button(
            "Confirm",
            key=f"confirm_event_{index}",
            type="primary",
            disabled=decision == "confirmed",
            on_click=mark_event,
            args=(index, "confirmed"),
        )
        skip_col.button(
            "Skip",
            key=f"skip_event_{index}",
            disabled=decision == "skipped",
            on_click=mark_event,
            args=(index, "skipped"),
        )


def build_current_url() -> str:
    params = dict(st.query_params)
    if not params:
        return GMAIL_REDIRECT_URI

    return f"{GMAIL_REDIRECT_URI}?{urlencode(params, doseq=True)}"


def handle_gmail_callback() -> None:
    params = dict(st.query_params)

    if "code" not in params:
        return

    state = st.session_state.get("gmail_oauth_state") or params.get("state")
    if not state:
        st.session_state["gmail_login_error"] = (
            "Gmail login returned without a state value. Start the login again."
        )
        st.query_params.clear()
        return

    try:
        save_token_from_callback(
            authorization_response=build_current_url(),
            state=state,
            redirect_uri=GMAIL_REDIRECT_URI,
        )
    except GmailReaderError as exc:
        st.session_state["gmail_login_error"] = str(exc)
        st.query_params.clear()
        return

    st.session_state.pop("gmail_auth_url", None)
    st.session_state.pop("gmail_oauth_state", None)
    st.session_state["gmail_login_success"] = True
    st.query_params.clear()


def show_gmail_login_controls() -> None:
    if not DEFAULT_CREDENTIALS_PATH.exists():
        st.warning(
            "Place credentials.json in the project folder before scanning Gmail."
        )
        return

    st.info("First connect Gmail, then scan recent messages.")

    if st.button("Create Gmail login link"):
        try:
            auth_url, state = create_authorization_url(GMAIL_REDIRECT_URI)
        except GmailReaderError as exc:
            st.error(str(exc))
            return

        st.session_state["gmail_auth_url"] = auth_url
        st.session_state["gmail_oauth_state"] = state

    auth_url = st.session_state.get("gmail_auth_url")
    if auth_url:
        st.link_button("Open Google login", auth_url)
        st.caption(
            "After allowing access, Google will return to this page. "
            "Then click Connect and scan Gmail."
        )


st.set_page_config(page_title="Gmail Calendar Agent Demo")
handle_gmail_callback()

st.title("Gmail Calendar Agent Demo")
st.caption("Scan sample emails or connect Gmail, then review events before confirming.")

extractor_mode = st.radio(
    "Extraction method",
    ("Rule-based", "LLM + rules fallback"),
    horizontal=True,
)
use_llm = extractor_mode == "LLM + rules fallback"

if use_llm and llm_extractor_enabled():
    st.success("LLM extraction is selected. Rules will still be used as fallback.")
elif use_llm:
    st.warning("LLM extraction is selected, but OPENAI_API_KEY is not available. Rules will be used.")
else:
    st.info("Rule-based event extraction is selected.")

if st.session_state.pop("gmail_login_success", False):
    st.success("Gmail login saved. You can scan Gmail now.")

if st.session_state.pop("gmail_login_error", None):
    st.error("Gmail login failed. Create a new login link and try again.")

source_mode = st.radio(
    "Email source",
    ("Sample emails", "Gmail"),
    horizontal=True,
)

if source_mode == "Sample emails":
    emails = read_sample_emails()

    st.subheader("Sample emails")

    if not emails:
        st.info("No sample emails found.")
    else:
        for email in emails:
            with st.expander(email["subject"], expanded=True):
                st.write(email["body"])

    st.divider()

    if st.button("Scan sample emails", type="primary"):
        scan_emails(emails, "Sample emails", use_llm)
        st.rerun()
else:
    st.subheader("Gmail inbox")

    if not token_exists():
        show_gmail_login_controls()

    max_results = st.slider("Recent emails to read", min_value=10, max_value=20, value=10)

    if st.button("Connect and scan Gmail", type="primary", disabled=not token_exists()):
        try:
            with st.spinner("Reading recent Gmail messages..."):
                gmail_emails = read_recent_emails(max_results=max_results)

            st.session_state["gmail_emails"] = gmail_emails
            scan_emails(gmail_emails, "Gmail", use_llm)
            st.rerun()
        except GmailReaderError as exc:
            st.error(str(exc))

    gmail_emails = st.session_state.get("gmail_emails", [])

    if gmail_emails:
        for email in gmail_emails:
            with st.expander(email["subject"]):
                st.caption(
                    f"{email.get('sender', 'Unknown sender')} | "
                    f"{email.get('date', 'Unknown date')} | "
                    f"ID: {email.get('message_id', '')}"
                )
                st.write(email.get("body", ""))
    else:
        st.write("Connect Gmail to show recent messages here.")

st.divider()

st.subheader("Schedule preview")
st.caption(f"Current source: {st.session_state.get('schedule_source', 'Not scanned yet')}")

schedule_items = st.session_state.get("schedule_items", [])
event_decisions = st.session_state.get("event_decisions", [])
last_scan_event_count = st.session_state.get("last_scan_event_count")

if last_scan_event_count is not None:
    extractor_status = st.session_state.get(
        "last_extractor_status",
        {"engine": "Rules", "message": "Rule-based extraction is active."},
    )
    scan_engine = extractor_status.get("engine", "Rules")
    email_count = st.session_state.get("last_scan_email_count", 0)
    st.caption(extractor_status.get("message", ""))
    if last_scan_event_count:
        st.success(
            f"{scan_engine} extracted {last_scan_event_count} event(s) "
            f"from {email_count} email(s)."
        )
    else:
        st.warning(
            f"{scan_engine} scanned {email_count} email(s), but found no clear calendar events."
        )

if len(event_decisions) != len(schedule_items):
    event_decisions = ["pending"] * len(schedule_items)
    st.session_state["event_decisions"] = event_decisions

if schedule_items:
    confirmed_count = event_decisions.count("confirmed")
    skipped_count = event_decisions.count("skipped")
    pending_count = event_decisions.count("pending")

    pending_col, confirmed_col, skipped_col = st.columns(3)
    pending_col.metric("Pending", pending_count)
    confirmed_col.metric("Confirmed", confirmed_count)
    skipped_col.metric("Skipped", skipped_count)

    table_rows = [
        {
            "Date": event.get("date", "Needs review"),
            "Time": event.get("time", "Needs review"),
            "Event": event.get("title", "Untitled event"),
            "Location": event.get("location", "Needs review"),
            "Source email": event.get("source_email", "sample email"),
            "Decision": DECISION_LABELS.get(event_decisions[index], "Pending review"),
        }
        for index, event in enumerate(schedule_items)
    ]
    st.markdown("**Extracted events**")
    st.dataframe(table_rows, width="stretch", hide_index=True)

    for index, event in enumerate(schedule_items):
        preview_event(event, index, event_decisions[index])
else:
    st.write("Click a scan button to preview possible calendar events.")
