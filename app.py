from pathlib import Path

import streamlit as st

from agent.event_extractor import extract_events_from_emails


BASE_DIR = Path(__file__).resolve().parent
SAMPLE_EMAIL_DIR = BASE_DIR / "data" / "sample_emails"


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

if st.button("Scan sample emails", type="primary"):
    st.session_state["schedule_items"] = extract_events_from_emails(emails)

st.subheader("Extracted schedule")

schedule_items = st.session_state.get("schedule_items", [])

if schedule_items:
    st.dataframe(schedule_items, width="stretch", hide_index=True)
else:
    st.write("Click the scan button to preview possible calendar events.")
