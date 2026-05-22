from pathlib import Path
import re

import streamlit as st


BASE_DIR = Path(__file__).resolve().parent
SAMPLE_EMAIL_DIR = BASE_DIR / "data" / "sample_emails"
EVENT_WORDS = (
    "meeting",
    "appointment",
    "deadline",
    "event",
    "interview",
    "class",
    "workshop",
)


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


def extract_schedule_items(emails: list[dict[str, str]]) -> list[dict[str, str]]:
    items = []

    for email in emails:
        text = f"{email['subject']}\n{email['body']}"
        lower_text = text.lower()

        if not any(word in lower_text for word in EVENT_WORDS):
            continue

        date_match = re.search(
            r"\b(?:tomorrow|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
            r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
            r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
            r"\s+\d{1,2})\b",
            text,
            re.IGNORECASE,
        )
        time_match = re.search(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", text, re.IGNORECASE)
        location_match = re.search(
            r"\b(?:in|at)\s+([A-Z][A-Za-z0-9 ]+(?:Room|Clinic|Center|Hall|Office|online)?\d*)",
            text,
        )

        items.append(
            {
                "title": email["subject"],
                "date": date_match.group(0) if date_match else "Needs review",
                "time": time_match.group(0) if time_match else "Needs review",
                "location": location_match.group(1).strip() if location_match else "Needs review",
                "source_email": email["source"],
            }
        )

    return items


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
    st.session_state["schedule_items"] = extract_schedule_items(emails)

st.subheader("Extracted schedule")

schedule_items = st.session_state.get("schedule_items", [])

if schedule_items:
    st.dataframe(schedule_items, width="stretch", hide_index=True)
else:
    st.write("Click the scan button to preview possible calendar events.")
