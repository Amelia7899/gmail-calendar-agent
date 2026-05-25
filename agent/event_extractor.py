from __future__ import annotations

from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import re


EVENT_KEYWORDS = (
    "meeting",
    "appointment",
    "deadline",
    "event",
    "interview",
    "class",
    "workshop",
    "webinar",
    "seminar",
    "session",
    "lecture",
    "exam",
    "quiz",
    "invite",
    "invitation",
    "schedule",
    "booking",
    "reservation",
    "reminder",
    "due",
)

EVENT_KEYWORD_RE = re.compile(
    rf"\b(?:{'|'.join(re.escape(keyword) for keyword in EVENT_KEYWORDS)})s?\b",
    re.IGNORECASE,
)

MONTH_PATTERN = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
WEEKDAY_PATTERN = (
    r"mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|"
    r"fri(?:day)?|sat(?:urday)?|sun(?:day)?"
)
DAY_PATTERN = r"\d{1,2}(?:st|nd|rd|th)?"

DATE_PATTERNS = (
    rf"\b(?:{WEEKDAY_PATTERN}),?\s+(?:{MONTH_PATTERN})\.?\s+{DAY_PATTERN}(?:,\s*\d{{4}})?\b",
    rf"\b(?:{WEEKDAY_PATTERN}),?\s+{DAY_PATTERN}\s+(?:{MONTH_PATTERN})\.?(?:\s+\d{{4}})?\b",
    rf"\b(?:{MONTH_PATTERN})\.?\s+{DAY_PATTERN}(?:,\s*\d{{4}})?\b",
    rf"\b{DAY_PATTERN}\s+(?:{MONTH_PATTERN})\.?(?:\s+\d{{4}})?\b",
    r"\b\d{4}-\d{1,2}-\d{1,2}\b",
    r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b",
    r"\b(?:today|tomorrow|tonight)\b",
    rf"\b(?:this|next)\s+(?:{WEEKDAY_PATTERN})\b",
    rf"\b(?:{WEEKDAY_PATTERN})\b",
)

AMPM_PATTERN = r"(?:a\.?m\.?|p\.?m\.?)"
TIME_PATTERNS = (
    rf"\b\d{{1,2}}(?:(?::|\.)\d{{2}})?\s*(?:{AMPM_PATTERN})?\s*(?:-|to|until)\s*"
    rf"\d{{1,2}}(?:(?::|\.)\d{{2}})?\s*{AMPM_PATTERN}\b",
    rf"\b\d{{1,2}}(?:(?::|\.)\d{{2}})?\s*{AMPM_PATTERN}\b",
    r"\b(?:[01]?\d|2[0-3]):[0-5]\d\s*(?:-|to|until)\s*(?:[01]?\d|2[0-3]):[0-5]\d\b",
    r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b",
    r"\b(?:noon|midnight)\b",
)

DATE_TIME_LABELS = (
    "date",
    "when",
    "time",
    "start",
    "starts",
    "start time",
    "event date",
    "deadline",
    "due",
    "due date",
    "due by",
)
LOCATION_LABELS = (
    "where",
    "location",
    "venue",
    "place",
    "room",
    "address",
    "meeting location",
)

ONLINE_LOCATION_PATTERNS = (
    (re.compile(r"\bgoogle meet\b|meet\.google\.com", re.IGNORECASE), "Google Meet"),
    (re.compile(r"\bmicrosoft teams\b|\bms teams\b|\bteams\b", re.IGNORECASE), "Microsoft Teams"),
    (re.compile(r"\bzoom\b|zoom\.us", re.IGNORECASE), "Zoom"),
    (re.compile(r"\bonline\b|\bvirtual\b", re.IGNORECASE), "Online"),
)

ROOM_RE = re.compile(
    r"\b(?:Room|Rm|Lecture Theatre|Theatre|Lab)\s*[A-Za-z0-9-]+\b",
    re.IGNORECASE,
)
ADDRESS_RE = re.compile(
    r"\b\d{1,5}\s+[A-Z][A-Za-z0-9.' -]+"
    r"(?:Street|St|Road|Rd|Avenue|Ave|Drive|Dr|Lane|Ln|Boulevard|Blvd|Way|Place|Pl|Terrace|Tce)\b"
    r"(?:,\s*[A-Z][A-Za-z .'-]+)?",
)
NAMED_PLACE_RE = re.compile(
    r"\b(?:at|in)\s+([A-Z][A-Za-z0-9&.' -]{1,80}"
    r"(?:Clinic|Center|Centre|Hall|Office|Room|Building|Library|Lab|Theater|Theatre|Campus|School))\b"
)


def is_event_related(text: str) -> bool:
    return bool(EVENT_KEYWORD_RE.search(text))


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
    text = normalize_text(f"{subject}\n{body}")

    if not is_event_related(text):
        return None

    reference_date = parse_email_date(email.get("date", ""))

    return {
        "title": subject,
        "date": extract_date(text, reference_date=reference_date),
        "time": extract_time(text),
        "location": extract_location(text),
        "description": build_description(body),
        "source_email": email.get("source", email.get("id", "sample email")),
    }


def extract_date(text: str, reference_date: datetime | None = None) -> str:
    for block in build_search_blocks(text, DATE_TIME_LABELS):
        for pattern in DATE_PATTERNS:
            match = re.search(pattern, block, re.IGNORECASE)
            if match:
                value = clean_value(match.group(0))
                return resolve_relative_date(value, reference_date)

    return "Needs review"


def extract_time(text: str) -> str:
    for block in build_search_blocks(text, DATE_TIME_LABELS):
        for pattern in TIME_PATTERNS:
            match = re.search(pattern, block, re.IGNORECASE)
            if match:
                return clean_time_value(match.group(0))

    return "Needs review"


def extract_location(text: str) -> str:
    lines = meaningful_lines(text)
    label_values = labeled_values(lines, LOCATION_LABELS)

    for block in label_values:
        online_location = detect_online_location(block)
        if online_location:
            return online_location

        location = clean_location_value(block)
        if is_usable_location_label(location):
            return location

    for block in context_lines(lines):
        online_location = detect_online_location(block, require_location_context=True)
        if online_location:
            return online_location

        location = extract_physical_location(block)
        if location:
            return location

    return "Needs review"


def build_search_blocks(text: str, labels: tuple[str, ...]) -> list[str]:
    lines = meaningful_lines(text)
    blocks = labeled_values(lines, labels) + context_lines(lines)
    return dedupe(blocks) or [normalize_text(text)]


def context_lines(lines: list[str]) -> list[str]:
    selected = []

    for index, line in enumerate(lines):
        if is_context_line(line):
            selected.append(line)

            if index + 1 < len(lines) and should_include_following_line(lines[index + 1]):
                selected.append(lines[index + 1])

    return dedupe(selected)


def is_context_line(line: str) -> bool:
    return (
        EVENT_KEYWORD_RE.search(line) is not None
        or has_label(line, DATE_TIME_LABELS)
        or has_label(line, LOCATION_LABELS)
        or has_date_hint(line)
        or has_time_hint(line)
    )


def should_include_following_line(line: str) -> bool:
    return len(line) <= 120 and not looks_like_footer(line)


def labeled_values(lines: list[str], labels: tuple[str, ...]) -> list[str]:
    values = []
    labels_pattern = "|".join(re.escape(label) for label in labels)
    inline_label_re = re.compile(rf"^(?:{labels_pattern})\s*[:\-]\s*(.+)$", re.IGNORECASE)
    normalized_labels = {label.lower() for label in labels}

    for index, line in enumerate(lines):
        inline_match = inline_label_re.match(line)
        if inline_match:
            values.append(inline_match.group(1))
            continue

        normalized_line = line.lower().strip(" :-")
        if normalized_line in normalized_labels and index + 1 < len(lines):
            values.append(lines[index + 1])

    return dedupe(values)


def has_label(line: str, labels: tuple[str, ...]) -> bool:
    normalized = line.lower().strip(" :-")
    return normalized in {label.lower() for label in labels} or any(
        line.lower().startswith(f"{label.lower()}:") for label in labels
    )


def has_date_hint(text: str) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in DATE_PATTERNS)


def has_time_hint(text: str) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in TIME_PATTERNS)


def extract_physical_location(text: str) -> str | None:
    for pattern in (ROOM_RE, ADDRESS_RE, NAMED_PLACE_RE):
        match = pattern.search(text)
        if match:
            value = match.group(1) if match.lastindex else match.group(0)
            return clean_location_value(value)

    return None


def detect_online_location(text: str, require_location_context: bool = False) -> str | None:
    for pattern, label in ONLINE_LOCATION_PATTERNS:
        if pattern.search(text):
            if require_location_context and label == "Online" and not has_online_location_context(text):
                continue
            return label

    return None


def has_online_location_context(text: str) -> bool:
    return re.search(
        r"\b(?:held|happen|happens|meeting|session|event|interview|workshop|class|"
        r"webinar|join|via|where|location|venue)\b",
        text,
        re.IGNORECASE,
    ) is not None


def parse_email_date(raw_date: str) -> datetime | None:
    if not raw_date:
        return None

    try:
        return parsedate_to_datetime(raw_date)
    except (TypeError, ValueError, IndexError):
        return None


def resolve_relative_date(value: str, reference_date: datetime | None) -> str:
    if not reference_date:
        return value

    lower_value = value.lower()
    reference_day = reference_date.date()

    if lower_value in {"today", "tonight"}:
        return f"{reference_day.isoformat()} ({value})"

    if lower_value == "tomorrow":
        event_day = reference_day + timedelta(days=1)
        return f"{event_day.isoformat()} (tomorrow)"

    weekday = weekday_number(lower_value.removeprefix("this ").removeprefix("next "))
    if weekday is None:
        return value

    days_ahead = (weekday - reference_day.weekday()) % 7
    if lower_value.startswith("next ") and days_ahead == 0:
        days_ahead = 7

    event_day = reference_day + timedelta(days=days_ahead)
    return f"{event_day.isoformat()} ({value})"


def weekday_number(value: str) -> int | None:
    weekdays = {
        "mon": 0,
        "monday": 0,
        "tue": 1,
        "tuesday": 1,
        "wed": 2,
        "wednesday": 2,
        "thu": 3,
        "thursday": 3,
        "fri": 4,
        "friday": 4,
        "sat": 5,
        "saturday": 5,
        "sun": 6,
        "sunday": 6,
    }
    return weekdays.get(value.strip().lower())


def meaningful_lines(text: str) -> list[str]:
    return [line for line in normalize_text(text).splitlines() if line]


def normalize_text(text: str) -> str:
    replacements = {
        "\u00a0": " ",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\ufeff": "",
    }

    for original, replacement in replacements.items():
        text = text.replace(original, replacement)

    lines = [collapse_spaces(line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def build_description(body: str) -> str:
    lines = [collapse_spaces(line).strip() for line in body.splitlines()]
    lines = [line for line in lines if line]
    return " ".join(lines) if lines else "No description"


def clean_location_value(value: str) -> str:
    value = clean_value(value)
    value = re.split(
        r"\s+(?:date|when|time|description|details|join)\s*:",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return value.strip(" .,;-")


def is_usable_location_label(value: str) -> bool:
    if not value:
        return False

    return value.lower() not in {"tbd", "to be determined", "none", "n/a", "not specified"}


def clean_time_value(value: str) -> str:
    value = clean_value(value)
    return re.sub(r"(?<=\d)\.(?=\d{2})", ":", value)


def clean_value(value: str) -> str:
    return collapse_spaces(value).strip(" .,")


def collapse_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value)


def looks_like_footer(line: str) -> bool:
    lower_line = line.lower()
    return any(
        marker in lower_line
        for marker in (
            "unsubscribe",
            "privacy policy",
            "terms of service",
            "do not reply",
            "all rights reserved",
        )
    )


def dedupe(values: list[str]) -> list[str]:
    seen = set()
    unique_values = []

    for value in values:
        cleaned = clean_value(value)
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            unique_values.append(cleaned)

    return unique_values
