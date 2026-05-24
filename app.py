from pathlib import Path

import streamlit as st

from agent.event_extractor import extract_events_from_emails


BASE_DIR = Path(__file__).resolve().parent
SAMPLE_EMAIL_DIR = BASE_DIR / "data" / "sample_emails"
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


def scan_sample_emails(emails: list[dict[str, str]]) -> None:
    schedule_items = extract_events_from_emails(emails)
    st.session_state["schedule_items"] = schedule_items
    st.session_state["event_decisions"] = ["pending"] * len(schedule_items)


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


st.set_page_config(page_title="Gmail Calendar Agent Demo")

st.title("Gmail Calendar Agent Demo")
st.caption("Sample email prototype")

emails = read_sample_emails()

st.subheader("Sample emails")

if not emails:
    st.info("No sample emails found.")
else:
    for email in emails:
        with st.expander(email["subject"], expanded=True):
            st.write(email["body"])

st.divider()

st.button(
    "Scan sample emails",
    type="primary",
    on_click=scan_sample_emails,
    args=(emails,),
)

st.subheader("Schedule preview")

schedule_items = st.session_state.get("schedule_items", [])
event_decisions = st.session_state.get("event_decisions", [])

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
            "Title": event.get("title", "Untitled event"),
            "Date": event.get("date", "Needs review"),
            "Time": event.get("time", "Needs review"),
            "Location": event.get("location", "Needs review"),
            "Source email": event.get("source_email", "sample email"),
            "Decision": DECISION_LABELS.get(event_decisions[index], "Pending review"),
        }
        for index, event in enumerate(schedule_items)
    ]
    st.dataframe(table_rows, width="stretch", hide_index=True)

    for index, event in enumerate(schedule_items):
        preview_event(event, index, event_decisions[index])
else:
    st.write("Click the scan button to preview possible calendar events.")
