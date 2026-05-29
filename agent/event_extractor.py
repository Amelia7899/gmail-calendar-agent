from __future__ import annotations

from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
import html
import json
import os
import re
from urllib import error, request
from zoneinfo import ZoneInfo


EVENT_KEYWORDS = (
    "meeting",
    "appointment",
    "deadline",
    "event",
    "interview",
    "class",
    "workshop",
    "presentation",
    "lecture",
    "assessment",
    "exam",
    "quiz",
    "seminar",
    "webinar",
    "scheduled",
    "schedule",
    "invite",
    "invited",
    "due",
)

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

MONTH_PATTERN = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
WEEKDAY_PATTERN = "|".join(WEEKDAYS)
DAY_PATTERN = r"\d{1,2}(?:st|nd|rd|th)?"
PERIOD_PATTERN = r"a\.?m\.?|p\.?m\.?"

DATE_EXTRACTORS = (
    re.compile(
        rf"\b(?:on\s+)?(?:the\s+)?(?P<day>{DAY_PATTERN})\s+of\s+"
        rf"(?P<month>{MONTH_PATTERN})\.?(?:,?\s*(?P<year>\d{{4}}))?\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?P<day>{DAY_PATTERN})\s+(?P<month>{MONTH_PATTERN})\.?"
        rf"(?:,?\s*(?P<year>\d{{4}}))?\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?P<month>{MONTH_PATTERN})\.?\s+(?P<day>{DAY_PATTERN})"
        rf"(?:,?\s*(?P<year>\d{{4}}))?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})\b"),
    re.compile(r"\b(?P<day>\d{1,2})[/-](?P<month>\d{1,2})(?:[/-](?P<year>\d{2,4}))?\b"),
    re.compile(r"\b(?P<month>\d{1,2})[/-](?P<day>\d{1,2})(?:[/-](?P<year>\d{2,4}))?\b"),
)

RELATIVE_DATE_PATTERN = re.compile(r"\b(today|tonight|tomorrow)\b", re.IGNORECASE)
WEEKDAY_DATE_PATTERN = re.compile(
    rf"\b(?:(?P<prefix>this|next)\s+)?(?P<weekday>{WEEKDAY_PATTERN})\b",
    re.IGNORECASE,
)
SCHEDULE_HEADER_PATTERN = re.compile(
    rf"\b(?P<weekday>{WEEKDAY_PATTERN})\s+(?P<day>{DAY_PATTERN})\s+"
    rf"(?P<month>{MONTH_PATTERN})\.?(?:\s+(?P<year>\d{{4}}))?\s*"
    r"\((?P<time>[^)]*\d[^)]*)\)",
    re.IGNORECASE,
)
LABELED_EVENT_PATTERN = re.compile(
    r"(?P<prefix>.*?)"
    r"(?:📅\s*)?Date\s*:\s*(?P<date>.*?)"
    r"(?:⏰\s*)?Time\s*:\s*(?P<time>.*?)"
    r"(?:📍\s*)?Where\s*:\s*(?P<location>.*?)"
    r"(?=\s+[A-Z0-9][^📅⏰📍]{2,260}?(?:📅\s*)?Date\s*:|\s+https?://|\s+_{5,}|$)",
    re.IGNORECASE | re.DOTALL,
)
DATE_LABEL_PATTERN = re.compile(r"(?:📅\s*)?Date\s*:", re.IGNORECASE)
TIME_LABEL_PATTERN = re.compile(r"(?:⏰\s*)?Time\s*:", re.IGNORECASE)
WHERE_LABEL_PATTERN = re.compile(r"(?:📍\s*)?Where\s*:", re.IGNORECASE)

TIME_RANGE_PATTERN = re.compile(
    rf"\b(?P<start>\d{{1,2}}(?:(?::|\.)\d{{2}})?)\s*(?P<start_period>{PERIOD_PATTERN})?"
    rf"\s*(?:-|to|until)\s*"
    rf"(?P<end>\d{{1,2}}(?:(?::|\.)\d{{2}})?)\s*(?P<end_period>{PERIOD_PATTERN})?\b",
    re.IGNORECASE,
)
TIME_SINGLE_PATTERN = re.compile(
    rf"\b(?P<time>\d{{1,2}}(?:(?::|\.)\d{{2}})?)\s*(?P<period>{PERIOD_PATTERN})\b"
    r"|\b(?P<time24>(?:[01]?\d|2[0-3]):[0-5]\d)\b",
    re.IGNORECASE,
)

LOCATION_LABEL_PATTERN = re.compile(
    r"\b(?:where|location|venue|place|address)\s*[:\-]\s*([^\n.]+)",
    re.IGNORECASE,
)
ROOM_LINE_PATTERN = re.compile(r"^ROOM\s*(?P<room>\d+)\s*:\s*(?P<location>.+)$", re.IGNORECASE)
ADDRESS_PATTERN = re.compile(
    r"\b\d{1,5}\s+[A-Z][A-Za-z0-9.' -]+"
    r"(?:Street|St|Road|Rd|Avenue|Ave|Drive|Dr|Lane|Ln|Boulevard|Blvd|Way|Place|Pl|Terrace|Tce)\b"
    r"(?:,\s*[A-Z][A-Za-z .'-]+)?"
)
CANVAS_ASSIGNMENT_PATTERN = re.compile(
    r"\bAssignment\s+created\s*-\s*"
    r"(?P<title>[^:\n]+?,\s*[A-Z]{2,}\s*\d{3}[A-Z]?)"
    r"\s*:\s*(?P<course>.*?)\s+due:\s*(?P<due>.*?)(?=\s+https?://|\s+You\s+can\s+change|$)",
    re.IGNORECASE | re.DOTALL,
)


def is_event_related(text: str) -> bool:
    lower_text = text.lower()
    if any(keyword in lower_text for keyword in EVENT_KEYWORDS):
        return True

    return has_scheduled_datetime(text)


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
LOCAL_TIMEZONE = ZoneInfo("Pacific/Auckland")
LAST_EXTRACTION_STATUS = {
    "engine": "Rules",
    "message": "Rule-based extraction is active.",
}


def extract_events_from_emails(
    emails: list[dict[str, str]],
    use_llm: bool = False,
) -> list[dict[str, str]]:
    if use_llm:
        llm_events = extract_events_with_llm_if_available(emails)
        if llm_events is not None:
            return llm_events

    if not use_llm:
        set_extractor_status("Rules", "Rule-based extraction is active.")
    events = []

    for email in emails:
        events.extend(extract_events_from_email(email))

    return events


def extract_events_from_email(email: dict[str, str]) -> list[dict[str, str]]:
    subject = email.get("subject", "No subject").strip() or "No subject"
    body = email.get("body", "").strip()
    text = normalize_text(f"{subject}\n{body}")
    reference_date = email_reference_date(email)

    if is_non_actionable_inspection_notice(text):
        return []

    if not is_event_related(text):
        return []

    canvas_events = extract_canvas_assignment_events(email, text, reference_date)
    if canvas_events:
        return canvas_events

    labeled_events = extract_labeled_events(email, text, reference_date)
    if labeled_events:
        return labeled_events

    schedule_events = extract_schedule_events(email, text, reference_date)
    if schedule_events:
        return schedule_events

    event = build_single_event(email, subject, body, text, reference_date)
    return [event] if is_meaningful_event(event) else []


def extract_event_from_email(email: dict[str, str]) -> dict[str, str] | None:
    events = extract_events_from_email(email)
    return events[0] if events else None


def llm_extractor_enabled() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def get_extractor_status() -> dict[str, str]:
    return LAST_EXTRACTION_STATUS.copy()


def set_extractor_status(engine: str, message: str) -> None:
    LAST_EXTRACTION_STATUS["engine"] = engine
    LAST_EXTRACTION_STATUS["message"] = message


def email_reference_date(email: dict[str, str]) -> date:
    internal_date = str(email.get("internal_date", "")).strip()
    if internal_date.isdigit():
        timestamp = int(internal_date) / 1000
        return datetime.fromtimestamp(timestamp, LOCAL_TIMEZONE).date()

    sent_date = str(email.get("date", "")).strip()
    if sent_date and sent_date.lower() != "unknown date":
        try:
            parsed_date = parsedate_to_datetime(sent_date)
        except (TypeError, ValueError):
            parsed_date = None

        if parsed_date:
            if parsed_date.tzinfo:
                parsed_date = parsed_date.astimezone(LOCAL_TIMEZONE)
            return parsed_date.date()

    return date.today()


def extract_events_with_llm_if_available(
    emails: list[dict[str, str]],
) -> list[dict[str, str]] | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        set_extractor_status("Rules", "No OPENAI_API_KEY found, using rule-based extraction.")
        return None

    events = []
    for email in emails:
        events.extend(extract_events_from_email_with_llm(email, api_key))

    return events


def extract_events_from_email_with_llm(
    email: dict[str, str],
    api_key: str,
) -> list[dict[str, str]]:
    subject = email.get("subject", "No subject").strip() or "No subject"
    sender = email.get("sender", "Unknown sender")
    sent_date = email.get("date", "Unknown date")
    reference_date = email_reference_date(email)
    body = normalize_text(email.get("body", ""))
    source_email = email.get("source", email.get("id", "email"))
    model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)

    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": build_llm_system_prompt()},
            {
                "role": "user",
                "content": (
                    f"Reference date from email received time: {reference_date.isoformat()}\n"
                    f"Email subject: {subject}\n"
                    f"Sender: {sender}\n"
                    f"Email sent date: {sent_date}\n"
                    f"Source email: {source_email}\n\n"
                    f"Email body:\n{body[:12000]}"
                ),
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "email_calendar_events",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "events": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "title": {"type": "string"},
                                    "date": {"type": "string"},
                                    "time": {"type": "string"},
                                    "location": {"type": "string"},
                                    "description": {"type": "string"},
                                    "source_email": {"type": "string"},
                                },
                                "required": [
                                    "title",
                                    "date",
                                    "time",
                                    "location",
                                    "description",
                                    "source_email",
                                ],
                            },
                        }
                    },
                    "required": ["events"],
                },
            }
        },
    }

    try:
        response_data = post_openai_response(payload, api_key)
        content = extract_response_text(response_data)
        parsed = json.loads(content)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        set_extractor_status("Rules", f"LLM extraction failed, using rules instead: {exc}")
        return extract_events_from_email(email)

    source_message_id = email.get("message_id", "")
    llm_events = normalize_llm_events(
        parsed.get("events", []),
        source_email,
        source_message_id,
    )
    rule_events = extract_events_from_email(email)

    if len(rule_events) > len(llm_events) and has_concrete_schedule(rule_events):
        set_extractor_status(
            "Rules",
            "LLM returned fewer events than the schedule parser, using the fuller rule-based split.",
        )
        return rule_events

    merged_events = merge_events_with_rule_fallback(llm_events, rule_events)
    set_extractor_status(
        "LLM",
        f"LLM extracted {len(merged_events)} event(s), with rules filling any missing fields.",
    )
    return merged_events


def build_llm_system_prompt() -> str:
    return (
        "Extract all real calendar events from the email. Return no events for digests, "
        "questions, footers, preferences links, or general announcements without a "
        "concrete scheduled date. If one email lists multiple Date/Time/Where blocks, "
        "return one event per block. If one date/time has multiple rooms or venues, "
        "return one event per room or venue. Dates must be YYYY-MM-DD. Infer missing "
        "years and relative dates from the email reference date, not today's scan date. "
        "Times must be 24-hour HH:MM or HH:MM-HH:MM. Use exactly 'Needs review' for "
        "missing time or location. Clean Markdown, links, emoji-only fragments, and HTML "
        "tags from names."
    )


def post_openai_response(payload: dict, api_key: str) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        OPENAI_RESPONSES_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=40) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OSError(f"OpenAI request failed: {detail}") from exc


def extract_response_text(response_data: dict) -> str:
    if response_data.get("output_text"):
        return response_data["output_text"]

    for output_item in response_data.get("output", []):
        for content_item in output_item.get("content", []):
            if content_item.get("type") == "output_text" and content_item.get("text"):
                return content_item["text"]

    raise KeyError("No output text in OpenAI response")


def normalize_llm_events(
    events: list[dict],
    source_email: str,
    source_message_id: str = "",
) -> list[dict[str, str]]:
    clean_events = []

    for event in events:
        if not isinstance(event, dict):
            continue

        clean_event = {
            "title": clean_title(str(event.get("title", "Untitled event"))),
            "date": clean_value(str(event.get("date", "Needs review"))),
            "time": clean_value(str(event.get("time", "Needs review"))),
            "location": clean_location_candidate(str(event.get("location", "Needs review")))
            or "Needs review",
            "description": clean_value(strip_markup(strip_html(str(event.get("description", ""))))),
            "source_email": clean_value(str(event.get("source_email", source_email))),
            "message_id": source_message_id,
        }

        if is_meaningful_event(clean_event):
            clean_events.append(clean_event)

    return clean_events


def merge_events_with_rule_fallback(
    llm_events: list[dict[str, str]],
    rule_events: list[dict[str, str]],
) -> list[dict[str, str]]:
    if len(llm_events) != len(rule_events):
        return llm_events

    merged_events = []
    for llm_event, rule_event in zip(llm_events, rule_events):
        merged_event = llm_event.copy()
        for field in ("date", "time", "location"):
            if needs_review(merged_event.get(field)) and not needs_review(rule_event.get(field)):
                merged_event[field] = rule_event[field]

        if needs_review(merged_event.get("title")) and not needs_review(rule_event.get("title")):
            merged_event["title"] = rule_event["title"]

        merged_events.append(merged_event)

    return merged_events


def needs_review(value: str | None) -> bool:
    return not value or clean_value(value).lower() in {"needs review", "untitled event"}


def has_concrete_schedule(events: list[dict[str, str]]) -> bool:
    if len(events) < 2:
        return False

    return all(
        event.get("date") != "Needs review"
        and event.get("time") != "Needs review"
        and event.get("location") != "Needs review"
        for event in events
    )


def build_single_event(
    email: dict[str, str],
    subject: str,
    body: str,
    text: str,
    reference_date: date,
) -> dict[str, str]:
    return {
        "title": clean_title(subject),
        "date": extract_date(text, reference_date),
        "time": extract_time(text),
        "location": extract_location(text),
        "description": build_description(body),
        "source_email": email.get("source", email.get("id", "sample email")),
        "message_id": email.get("message_id", ""),
    }


def extract_canvas_assignment_events(
    email: dict[str, str],
    text: str,
    reference_date: date,
) -> list[dict[str, str]]:
    source_email = email.get("source", email.get("id", "sample email"))
    source_message_id = email.get("message_id", "")
    events = []

    for match in CANVAS_ASSIGNMENT_PATTERN.finditer(text):
        assignment_title = clean_title(match.group("title"))
        due_text = clean_value(match.group("due"))
        course = clean_value(match.group("course"))
        title = clean_title(f"{assignment_title}: {course}" if course else assignment_title)
        description = clean_value(
            f"Canvas assignment created for {course}. Due: {due_text}"
        )

        event = {
            "title": title,
            "date": extract_date(due_text, reference_date),
            "time": extract_time(due_text),
            "location": "Needs review",
            "description": description,
            "source_email": source_email,
            "message_id": source_message_id,
        }

        if is_meaningful_event(event):
            events.append(event)

    return events


def extract_schedule_events(
    email: dict[str, str],
    text: str,
    reference_date: date,
) -> list[dict[str, str]]:
    headers = list(SCHEDULE_HEADER_PATTERN.finditer(text))
    if not headers:
        return []

    subject = email.get("subject", "No subject").strip() or "No subject"
    source_email = email.get("source", email.get("id", "sample email"))
    source_message_id = email.get("message_id", "")
    events = []

    for index, header in enumerate(headers):
        section_end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        section = text[header.end() : section_end]
        event_date = date_from_parts(
            header.group("day"),
            header.group("month"),
            header.groupdict().get("year"),
            reference_date,
        )
        event_time = normalize_time_expression(header.group("time")) or "Needs review"
        room_locations = extract_room_locations(section)

        if not room_locations:
            location = extract_location(section)
            room_locations = [("", location)] if location != "Needs review" else []

        for room_label, location in room_locations:
            title = subject
            if room_label:
                title = f"{subject} - Room {room_label}"

            events.append(
                {
                    "title": clean_title(title),
                    "date": event_date or "Needs review",
                    "time": event_time,
                    "location": location,
                    "description": build_schedule_description(section, room_label),
                    "source_email": source_email,
                    "message_id": source_message_id,
                }
            )

    return events


def extract_room_locations(section: str) -> list[tuple[str, str]]:
    items = [clean_value(item) for item in re.split(r"\s+\*\s+", section)]
    room_locations = []

    for item in items:
        item = item.lstrip("* ")
        match = ROOM_LINE_PATTERN.match(item)
        if not match:
            continue

        location = clean_location_candidate(match.group("location"))
        if location:
            room_locations.append((match.group("room"), location))

    return room_locations


def extract_labeled_events(
    email: dict[str, str],
    text: str,
    reference_date: date,
) -> list[dict[str, str]]:
    date_matches = list(DATE_LABEL_PATTERN.finditer(text))
    if not date_matches:
        return []

    subject = email.get("subject", "No subject").strip() or "No subject"
    source_email = email.get("source", email.get("id", "sample email"))
    source_message_id = email.get("message_id", "")
    events = []
    pending_prefix = text[: date_matches[0].start()]

    for index, date_match in enumerate(date_matches):
        next_date_start = (
            date_matches[index + 1].start() if index + 1 < len(date_matches) else len(text)
        )
        time_match = TIME_LABEL_PATTERN.search(text, date_match.end(), next_date_start)
        if not time_match:
            continue
        where_match = WHERE_LABEL_PATTERN.search(text, time_match.end(), next_date_start)
        if not where_match:
            continue

        date_text = text[date_match.end() : time_match.start()]
        time_text = text[time_match.end() : where_match.start()]
        raw_location = text[where_match.end() : next_date_start]
        location, next_prefix = split_location_and_next_prefix(raw_location)

        title = infer_title_from_prefix(pending_prefix, subject)
        event_date = parse_date_text(date_text, reference_date)
        event_time = normalize_time_expression(time_text) or "Needs review"
        description = clean_value(strip_html(pending_prefix)) or subject

        event = {
            "title": clean_title(title),
            "date": event_date or "Needs review",
            "time": event_time,
            "location": location or "Needs review",
            "description": description,
            "source_email": source_email,
            "message_id": source_message_id,
        }

        if is_meaningful_event(event):
            events.append(event)

        pending_prefix = next_prefix

    return events


def split_location_and_next_prefix(raw_location: str) -> tuple[str | None, str]:
    value = clean_value(strip_markup(strip_html(raw_location)))
    link_tail = ""
    link_match = re.search(
        r"\s+(?:Register here:\s*)?(?:\[[^\]]+\]\s*\([^)]+\)|https?://\S+)\s*(?P<tail>.*)$",
        value,
        re.IGNORECASE,
    )
    if link_match:
        link_tail = clean_value(link_match.group("tail"))
        value = value[: link_match.start()]

    value = clean_value(value)

    if not value:
        return None, ""

    location_patterns = (
        r"(?P<loc>[A-Z][A-Za-z0-9&.' -]{1,80}"
        r"(?:Hall|Library|Atrium|Kitchen|Centre|Center|Office|Building|Lab|Theater|Theatre)"
        r"\s*\([^)]*\))(?=\s|$|[,.;])",
        r"(?P<loc>Grafton Atrium and Sweet As Crepes will be outside the main entrance)\b",
        r"(?P<loc>Outside Grafton Atrium)\b",
        r"(?P<loc>Grafton Atrium)\b",
        r"(?P<loc>Domain Grandstand)\b",
        r"(?P<loc>\d{3}\s+Student Kitchen)\b",
        r"(?P<loc>\d{3}[A-Z]?(?:-\w+)?)\b",
        r"(?P<loc>SCIENCE\s+B\d+,\s*Room\s*\d+(?:\s*\([^)]*\))?)\b",
        r"(?P<loc>\d{3}-\d{3}\s+-\s+\d+\s+[A-Z ]+\s+-\s+[A-Za-z0-9 ]+)\b",
    )

    for pattern in location_patterns:
        match = re.match(pattern, value, re.IGNORECASE)
        if match:
            location = clean_location_candidate(match.group("loc"))
            tail = clean_value(f"{value[match.end() :]} {link_tail}")
            return location, tail

    words = value.split()
    if len(words) > 6:
        return (
            clean_location_candidate(" ".join(words[:6])),
            clean_value(f"{' '.join(words[6:])} {link_tail}"),
        )

    return clean_location_candidate(value), link_tail


def parse_date_text(value: str, reference_date: date) -> str | None:
    return parse_explicit_date(clean_value(value), reference_date)


def infer_title_from_prefix(prefix: str, fallback_title: str) -> str:
    raw_text = strip_markup(strip_html(prefix))
    raw_text = re.sub(
        r"(?i)^register here:\s*(?:\[[^\]]+\]\s*\([^)]+\)|https?://\S+)\s*",
        "",
        raw_text,
    )
    line_candidates = [clean_value(line) for line in raw_text.splitlines() if clean_value(line)]
    line_candidates = dedupe_adjacent_lines(line_candidates)
    text = clean_value(raw_text)
    section_match = re.search(r"\b(?:What['’]?s On This Week|Next Week)\b", text, re.IGNORECASE)
    if section_match and section_match.start() < 80:
        text = text[section_match.end() :]
        line_candidates = [clean_value(line) for line in text.splitlines() if clean_value(line)]
    text = clean_value(text)

    if not text:
        return fallback_title

    if line_candidates:
        heading = first_heading_like_text(line_candidates)
        if heading:
            return clean_title(shorten_before_description_verb(heading))

    sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    shortened = shorten_before_description_verb(sentence)
    return clean_title(shortened or fallback_title)


def first_heading_like_text(lines: list[str]) -> str | None:
    for line in reversed(lines):
        if 2 <= len(line) <= 90 and not line.endswith((".", "!", "?")):
            return line

    return None


def dedupe_adjacent_lines(lines: list[str]) -> list[str]:
    deduped = []

    for line in lines:
        if not deduped or deduped[-1].lower() != line.lower():
            deduped.append(line)

    return deduped


def shorten_before_description_verb(text: str) -> str:
    markers = (
        " is finally here",
        " The last week ",
        " make sure ",
        " Empower ",
        " Decorate ",
        " Join ",
        " An evening ",
        " Celebrate ",
        " Treat ",
        " Need ",
        " Our much-loved ",
    )
    for marker in markers:
        if marker in text:
            return clean_value(text.split(marker, 1)[0])

    words = text.split()
    if len(words) > 10:
        return clean_value(" ".join(words[:10]))

    return clean_value(text)


def extract_date(text: str, today: date | None = None) -> str:
    today = today or date.today()

    parsed_date = parse_best_explicit_date(text, today)
    if parsed_date:
        return parsed_date

    for unit in ranked_text_units(text):
        parsed_date = parse_relative_date(unit, today)
        if parsed_date:
            return parsed_date

    return "Needs review"


def extract_time(text: str) -> str:
    for unit in ranked_text_units(text):
        normalized_time = normalize_time_expression(unit)
        if normalized_time:
            return normalized_time

    normalized_time = normalize_time_expression(normalize_text(text).replace("\n", " "))
    if normalized_time:
        return normalized_time

    return "Needs review"


def normalize_time_expression(text: str) -> str | None:
    for match in TIME_RANGE_PATTERN.finditer(text):
        normalized_range = normalize_time_range(match)
        if normalized_range:
            return normalized_range

    for match in TIME_SINGLE_PATTERN.finditer(text):
        normalized_time = normalize_single_time_match(match)
        if normalized_time:
            return normalized_time

    return None


def normalize_time_range(match: re.Match[str]) -> str | None:
    start_token = match.group("start")
    end_token = match.group("end")
    start_period = normalize_period(match.groupdict().get("start_period"))
    end_period = normalize_period(match.groupdict().get("end_period"))

    if not start_period and end_period:
        start_period = infer_start_period(start_token, end_token, end_period)

    start_time = parse_time_token(start_token, start_period)
    end_time = parse_time_token(end_token, end_period or start_period)

    if not start_time or not end_time:
        return None

    if not start_period and not end_period:
        start_time, end_time = adjust_ambiguous_daytime_range(start_time, end_time)

    return f"{start_time}-{end_time}"


def adjust_ambiguous_daytime_range(start_time: str, end_time: str) -> tuple[str, str]:
    start_hour = int(start_time.split(":", 1)[0])
    end_hour = int(end_time.split(":", 1)[0])

    if 7 <= start_hour <= 11 and 1 <= end_hour <= 6 and end_hour < start_hour:
        return start_time, f"{end_hour + 12:02d}:00"

    return start_time, end_time


def normalize_single_time_match(match: re.Match[str]) -> str | None:
    if match.groupdict().get("time24"):
        return parse_time_token(match.group("time24"), None)

    return parse_time_token(match.group("time"), normalize_period(match.group("period")))


def infer_start_period(start_token: str, end_token: str, end_period: str) -> str:
    start_hour = int(start_token.replace(".", ":").split(":", 1)[0])
    end_hour = int(end_token.replace(".", ":").split(":", 1)[0])

    if end_period == "pm" and start_hour > end_hour and start_hour != 12:
        return "am"

    return end_period


def parse_time_token(token: str, period: str | None) -> str | None:
    token = token.replace(".", ":")

    if ":" in token:
        hour_text, minute_text = token.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    else:
        hour = int(token)
        minute = 0

    if minute > 59:
        return None

    if period:
        if not 1 <= hour <= 12:
            return None
        if period == "am" and hour == 12:
            hour = 0
        elif period == "pm" and hour != 12:
            hour += 12
    elif not 0 <= hour <= 23:
        return None

    return f"{hour:02d}:{minute:02d}"


def normalize_period(value: str | None) -> str | None:
    if not value:
        return None

    return value.lower().replace(".", "")


def extract_location(text: str) -> str:
    labeled_location = extract_labeled_location(text)
    if labeled_location:
        return labeled_location

    for unit in ranked_text_units(text):
        location = extract_location_from_unit(unit)
        if location:
            return location

    return "Needs review"


def extract_labeled_location(text: str) -> str | None:
    for match in LOCATION_LABEL_PATTERN.finditer(normalize_text(text)):
        location = clean_location_candidate(match.group(1))
        if location:
            return location

    return None


def extract_location_from_unit(unit: str) -> str | None:
    online_location = detect_online_location(unit)
    if online_location:
        return online_location

    class_match = re.search(r"\b(?:in|during)\s+class\b", unit, re.IGNORECASE)
    if class_match:
        return "In class"

    floor_common_room_match = re.search(
        r"\b(?:the\s+)?((?:\d+(?:st|nd|rd|th)\s+floor\s+)?"
        r"common\s+room(?:\s+area)?)\b",
        unit,
        re.IGNORECASE,
    )
    if floor_common_room_match:
        return clean_value(floor_common_room_match.group(1))

    compound_room_match = re.search(
        r"\b([A-Z][A-Za-z0-9&.' -]{1,80}"
        r"(?:Library|Center|Centre|Hall|Office|Building|Lab|Theater|Theatre|Atrium),\s*"
        r"Room\s*[A-Za-z0-9-]+(?:\s*\([^)]*\))?)(?=\s|$|[,.;])",
        unit,
    )
    if compound_room_match:
        return clean_location_candidate(compound_room_match.group(1))

    room_match = re.search(r"\b(?:in|at)?\s*((?:Room|room)\s*[A-Za-z0-9-]+)\b", unit)
    if room_match:
        return clean_value(room_match.group(1))

    address_match = ADDRESS_PATTERN.search(unit)
    if address_match:
        return clean_value(address_match.group(0))

    place_match = re.search(
        r"\b(?:in|at)\s+([A-Z][A-Za-z0-9&.' -]{1,80}"
        r"(?:Clinic|Center|Centre|Hall|Office|Room|Building|Library|Lab|Theater|Theatre))\b",
        unit,
    )
    if place_match:
        return clean_value(place_match.group(1))

    return None


def detect_online_location(unit: str) -> str | None:
    lower_unit = unit.lower()

    if "google meet" in lower_unit or "meet.google.com" in lower_unit:
        return "Google Meet"
    if "zoom" in lower_unit or "zoom.us" in lower_unit:
        return "Zoom"
    if "microsoft teams" in lower_unit or re.search(r"\bteams\b", lower_unit):
        return "Microsoft Teams"
    if re.search(r"\b(online|virtual)\b", lower_unit) and has_online_location_context(lower_unit):
        return "Online"

    return None


def has_online_location_context(unit: str) -> bool:
    return re.search(
        r"\b(held|happen|happens|meeting|session|event|interview|workshop|class|"
        r"webinar|lecture|presentation|join|via|where|location|venue)\b",
        unit,
        re.IGNORECASE,
    ) is not None


def clean_location_candidate(value: str) -> str | None:
    online_location = detect_online_location(value)
    if online_location:
        return online_location

    value = re.split(
        r"\s+(?:date|when|time|agenda|description|details|join)\s*:",
        clean_value(value),
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" ,;.-")

    if not value or value.lower() in {"tbd", "to be determined", "none", "n/a"}:
        return None

    return value


def ranked_text_units(text: str) -> list[str]:
    units = split_text_units(text)
    priority_units = [unit for unit in units if is_event_related(unit) or has_date_language(unit)]
    other_units = [unit for unit in units if unit not in priority_units]
    return priority_units + other_units


def split_text_units(text: str) -> list[str]:
    text = normalize_text(text)
    rough_units = re.split(r"(?<=[.!?])\s+|\n+", text)
    units = []

    for unit in rough_units:
        unit = clean_value(unit)
        if unit and not looks_like_footer(unit):
            units.append(unit)

    return units or [text]


def parse_explicit_date(text: str, today: date) -> str | None:
    matches = explicit_date_matches(text)
    if not matches:
        return None

    return date_from_match(matches[0], today)


def parse_best_explicit_date(text: str, today: date) -> str | None:
    matches = explicit_date_matches(text)
    if not matches:
        return None

    scored_dates = []

    for index, match in enumerate(matches):
        parsed_date = date_from_match(match, today)
        if not parsed_date:
            continue

        score = score_date_match(text, match, index, matches)
        scored_dates.append((score, index, parsed_date))

    if not scored_dates:
        return None

    scored_dates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return scored_dates[0][2]


def explicit_date_matches(text: str) -> list[re.Match[str]]:
    matches = []
    seen_spans = set()

    for pattern in DATE_EXTRACTORS:
        for match in pattern.finditer(text):
            span = match.span()
            if span in seen_spans:
                continue
            seen_spans.add(span)
            matches.append(match)

    return sorted(matches, key=lambda match: match.start())


def date_from_match(match: re.Match[str], today: date) -> str | None:
    return date_from_parts(
        match.group("day"),
        match.group("month"),
        match.groupdict().get("year"),
        today,
    )


def score_date_match(
    text: str,
    match: re.Match[str],
    index: int,
    matches: list[re.Match[str]],
) -> int:
    previous_end = matches[index - 1].end() if index > 0 else 0
    next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
    before = text[max(previous_end, match.start() - 140) : match.start()]
    after = text[match.end() : min(next_start, match.end() + 180)]
    local = f"{before} {match.group(0)} {after}"
    local_lower = local.lower()
    score = 0

    if normalize_time_expression(after) or normalize_time_expression(local):
        score += 8
    if re.search(r"\b(?:between|at|from|until)\b", after, re.IGNORECASE):
        score += 2
    if re.search(
        r"\b(?:re-?inspection date|due date|deadline|appointment|session|event|meeting|exam)\b",
        local_lower,
    ):
        score += 4
    if re.search(r"\b(?:completed|was completed|were completed|has completed)\b", local_lower):
        score -= 6

    return score


def parse_relative_date(text: str, today: date) -> str | None:
    relative_match = RELATIVE_DATE_PATTERN.search(text)
    if relative_match:
        value = relative_match.group(1).lower()
        if value in {"today", "tonight"}:
            return today.isoformat()
        if value == "tomorrow":
            return (today + timedelta(days=1)).isoformat()

    weekday_match = WEEKDAY_DATE_PATTERN.search(text)
    if not weekday_match:
        return None

    weekday = WEEKDAYS[weekday_match.group("weekday").lower()]
    days_ahead = (weekday - today.weekday()) % 7

    if weekday_match.group("prefix") and weekday_match.group("prefix").lower() == "next":
        days_ahead = days_ahead or 7

    return (today + timedelta(days=days_ahead)).isoformat()


def date_from_parts(
    day_text: str,
    month_text: str,
    year_text: str | None,
    today: date,
) -> str | None:
    day = parse_day(day_text)
    month = parse_month(month_text)
    if day is None or month is None:
        return None

    year = parse_year(year_text, month, day, today)
    parsed_date = safe_date(year, month, day)
    return parsed_date.isoformat() if parsed_date else None


def parse_month(value: str) -> int | None:
    value = value.lower().strip(".")

    if value.isdigit():
        month = int(value)
        return month if 1 <= month <= 12 else None

    return MONTHS.get(value[:3])


def parse_day(value: str) -> int | None:
    day = int(re.sub(r"(st|nd|rd|th)$", "", value.lower()))
    return day if 1 <= day <= 31 else None


def parse_year(value: str | None, month: int, day: int, today: date) -> int:
    if value:
        year = int(value)
        return 2000 + year if year < 100 else year

    candidate = safe_date(today.year, month, day)
    if candidate and candidate >= today:
        return today.year

    return today.year + 1


def safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def is_meaningful_event(event: dict[str, str]) -> bool:
    return event.get("date") != "Needs review" or event.get("time") != "Needs review"


def is_non_actionable_inspection_notice(text: str) -> bool:
    lower_text = text.lower()
    if "inspection comments" not in lower_text:
        return False

    specific_result = re.split(r"\bif you have failed\b", lower_text, maxsplit=1)[0]
    return re.search(r"\bpass\b\s*-\s*no further action required\b", specific_result) is not None


def has_date_language(text: str) -> bool:
    lower_text = text.lower()
    return any(word in lower_text for word in (" on ", "date", "when", "scheduled", "due", "deadline"))


def has_scheduled_datetime(text: str) -> bool:
    normalized = normalize_text(text)
    today = date.today()
    has_date = parse_explicit_date(normalized, today) or parse_relative_date(normalized, today)
    return bool(has_date and normalize_time_expression(normalized))


def build_description(body: str) -> str:
    lines = [clean_value(strip_markup(strip_html(line))) for line in body.splitlines()]
    lines = [line for line in lines if line and not looks_like_footer(line)]
    return " ".join(lines) if lines else "No description"


def build_schedule_description(section: str, room_label: str) -> str:
    items = [clean_value(item) for item in re.split(r"\s+\*\s+", section)]
    presenters = []
    room_seen = False

    for item in items:
        item = item.lstrip("* ")
        room_match = ROOM_LINE_PATTERN.match(item)
        if room_match:
            room_seen = room_match.group("room") == room_label
            continue
        if room_seen and item:
            presenters.append(item)

    return "; ".join(presenters) if presenters else clean_value(section)


def normalize_text(text: str) -> str:
    text = strip_markup(strip_html(text))
    text = text.replace("\u00a0", " ")
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    return "\n".join(clean_value(line) for line in text.splitlines() if clean_value(line))


def strip_html(text: str) -> str:
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    text = re.sub(r"(?is)<head\b.*?</head>", " ", text)
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(
        r"(?i)</?(?:p|div|tr|td|table|h[1-6]|li|ul|ol|section|article|body)[^>]*>",
        "\n",
        text,
    )
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text)


def strip_markup(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\s*\(([^)]+)\)", r"\1", text)
    text = re.sub(r"(\*{2,3}|_{2,3})(.*?)\1", r"\2", text)
    text = re.sub(r"(?<!\S)[*_]{2,}\s*", "", text)
    text = re.sub(r"\s*[*_]{2,}(?!\S)", "", text)
    return text


def clean_title(value: str) -> str:
    value = clean_value(strip_markup(strip_html(value))).strip(" *_")
    value = re.sub(r"(?i)^register here:\s*", "", value).strip()
    value = re.sub(r"\s+", " ", value)

    if not value or value.lower() in {"for the details", "for the details😊"}:
        return "Untitled event"

    return value


def looks_like_footer(text: str) -> bool:
    lower_text = text.lower()
    return any(
        marker in lower_text
        for marker in (
            "unsubscribe",
            "email notifications",
            "privacy policy",
            "terms of service",
            "you received this email because",
            "edit your email preferences",
        )
    )


def clean_value(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" .,")
