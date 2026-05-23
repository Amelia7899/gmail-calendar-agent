from __future__ import annotations

import re


EVENT_KEYWORDS = (
    "meeting",
    "appointment",
    "deadline",
    "event",
    "interview",
    "class",
    "workshop",
)

MONTH_PATTERN = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)

DATE_PATTERNS = (
    r"\b(?:today|tomorrow|tonight)\b",
    r"\b(?:next\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    rf"\b(?:{MONTH_PATTERN})\s+\d{{1,2}}(?:,\s*\d{{4}})?\b",
    rf"\b\d{{1,2}}\s+(?:{MONTH_PATTERN})(?:\s+\d{{4}})?\b",
)

TIME_PATTERN = re.compile(
    r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b"
    r"(?:\s*(?:-|to|until)\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)\b)?",
    re.IGNORECASE,
)

ONLINE_LOCATION_WORDS = ("online", "zoom", "google meet", "teams")


def is_event_related(text: str) -> bool:
    lower_text = text.lower()
    return any(keyword in lower_text for keyword in EVENT_KEYWORDS)


def extract_events_from_emails(emails: list[dict[str, str]]) -> list[dict[str, str]]:
    events = []

    for email in emails:
        event = extract_event_from_email(email)
        if event:
            events.append(event)

    return events


def extract_event_from_email(email: dict[str, str]) -> dict[str, str] | None:
    subject = email.get("subject", "No subject").strip() or "No subject"
    body = email.get("body", "").strip()
    text = f"{subject}\n{body}"

    if not is_event_related(text):
        return None

    return {
        "title": subject,
        "date": extract_date(text),
        "time": extract_time(text),
        "location": extract_location(text),
        "description": build_description(body),
        "source_email": email.get("source", email.get("id", "sample email")),
    }


def extract_date(text: str) -> str:
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return clean_value(match.group(0))

    return "Needs review"


def extract_time(text: str) -> str:
    match = TIME_PATTERN.search(text)
    if match:
        return clean_value(match.group(0))

    return "Needs review"


def extract_location(text: str) -> str:
    lower_text = text.lower()

    for word in ONLINE_LOCATION_WORDS:
        if word in lower_text:
            return "Online" if word == "online" else word.title()

    room_match = re.search(r"\b(?:in|at)\s+((?:Room|room)\s*[A-Za-z0-9-]+)\b", text)
    if room_match:
        return clean_value(room_match.group(1))

    place_match = re.search(
        r"\b(?:in|at)\s+([A-Z][A-Za-z0-9&.' -]{1,60}"
        r"(?:Clinic|Center|Centre|Hall|Office|Room|Building|Library|Lab|Theater|Theatre))\b",
        text,
    )
    if place_match:
        return clean_value(place_match.group(1))

    return "Needs review"


def build_description(body: str) -> str:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    return " ".join(lines) if lines else "No description"


def clean_value(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" .,")
