from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import hashlib
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import tempfile


DEFAULT_CALENDAR_NAME = "Email Agent"
DEFAULT_EVENT_DURATION = timedelta(hours=1)
FORCE_CALENDAR_WRITE_FAILURE_ENV = "FORCE_CALENDAR_WRITE_FAILURE"
NEEDS_REVIEW = "Needs review"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "ics"
CALENDAR_APP_PATHS = (
    Path("/System/Applications/Calendar.app"),
    Path("/Applications/Calendar.app"),
)
EVENTKIT_HELPER_SOURCE = Path(__file__).with_name("calendar_eventkit_writer.m")
EVENTKIT_HELPER_INFO_PLIST = Path(__file__).with_name("calendar_eventkit_writer_info.plist")
EVENTKIT_HELPER_APP_BUNDLE = (
    PROJECT_ROOT / "Calendar Writer Helper" / "Gmail Calendar Agent Calendar Writer.app"
)
EVENTKIT_HELPER_BINARY = EVENTKIT_HELPER_APP_BUNDLE / "Contents" / "MacOS" / "gmail_calendar_eventkit_writer"
EVENTKIT_HELPER_BUNDLE_INFO_PLIST = EVENTKIT_HELPER_APP_BUNDLE / "Contents" / "Info.plist"
APPLE_SCRIPT_EVENTKIT_FALLBACK_MARKERS = (
    "-10827",
    "Application can't be found",
    "Can’t get application",
    "不能获得",
)

TIME_RANGE_PATTERN = re.compile(
    r"^\s*(?P<start>\d{1,2}:\d{2})\s*(?:-|to)\s*(?P<end>\d{1,2}:\d{2})\s*$",
    re.IGNORECASE,
)
TIME_PATTERN = re.compile(r"^\s*(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*$")

APPLE_CALENDAR_SCRIPT = """
using terms from application "/System/Applications/Calendar.app"
on buildCalendarDate(dateText, timeText)
    return date (dateText & " " & timeText & ":00")
end buildCalendarDate

on run argv
    set theTitle to item 1 of argv
    set startDateText to item 2 of argv
    set startTimeText to item 3 of argv
    set endDateText to item 4 of argv
    set endTimeText to item 5 of argv
    set theLocation to item 6 of argv
    set theDescription to item 7 of argv
    set theCalendarName to item 8 of argv
    set calendarAppPath to item 9 of argv

    set startAt to my buildCalendarDate(startDateText, startTimeText)
    set endAt to my buildCalendarDate(endDateText, endTimeText)

    tell application calendarAppPath
        set matchingCalendars to calendars whose name is theCalendarName
        if (count of matchingCalendars) is 0 then
            set targetCalendar to make new calendar with properties {name:theCalendarName}
        else
            set targetCalendar to item 1 of matchingCalendars
        end if

        set createdEvent to make new event at end of events of targetCalendar with properties {summary:theTitle, start date:startAt, end date:endAt, location:theLocation, description:theDescription}
        return uid of createdEvent
    end tell
end run
end using terms from
"""


class CalendarWriterError(RuntimeError):
    """Raised when an event cannot be written to Apple Calendar."""


class CalendarEventValidationError(CalendarWriterError):
    """Raised when an extracted event is not specific enough for calendar sync."""


@dataclass(frozen=True)
class CalendarWriteResult:
    uid: str
    calendar_name: str
    title: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class IcsWriteResult:
    path: Path
    uid: str
    title: str
    start: datetime
    end: datetime


def write_event_to_calendar(
    event: dict[str, str],
    calendar_name: str = DEFAULT_CALENDAR_NAME,
) -> CalendarWriteResult:
    """Create one event in Apple Calendar and return the created event details."""

    prepared_event = prepare_calendar_event(event, calendar_name)

    if os.environ.get(FORCE_CALENDAR_WRITE_FAILURE_ENV) == "1":
        raise CalendarWriterError("Forced Apple Calendar write failure for testing.")

    osascript_path = shutil.which("osascript")

    if sys.platform != "darwin" or not osascript_path:
        raise CalendarWriterError("Apple Calendar sync requires macOS with Calendar installed.")

    calendar_app_path = find_calendar_app_path()

    command = [
        osascript_path,
        "-e",
        APPLE_CALENDAR_SCRIPT,
        prepared_event.title,
        prepared_event.start.date().isoformat(),
        prepared_event.start.strftime("%H:%M"),
        prepared_event.end.date().isoformat(),
        prepared_event.end.strftime("%H:%M"),
        prepared_event.location,
        prepared_event.description,
        prepared_event.calendar_name,
        calendar_app_path,
    ]

    try:
        completed = run_calendar_command(command)
    except subprocess.TimeoutExpired as exc:
        raise CalendarWriterError("Apple Calendar did not respond in time.") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        if should_fallback_to_eventkit(detail):
            return write_event_with_eventkit(prepared_event)
        if not detail:
            detail = "Unknown Apple Calendar error."
        raise CalendarWriterError(detail)

    return CalendarWriteResult(
        uid=completed.stdout.strip(),
        calendar_name=prepared_event.calendar_name,
        title=prepared_event.title,
        start=prepared_event.start,
        end=prepared_event.end,
    )


def write_event_to_ics(
    event: dict[str, str],
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    calendar_name: str = DEFAULT_CALENDAR_NAME,
) -> IcsWriteResult:
    prepared_event = prepare_calendar_event(event, calendar_name)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    digest = build_event_digest(event, prepared_event)
    uid = f"{digest}@gmail-calendar-agent.local"
    filename = build_ics_filename(prepared_event, digest)
    path = output_dir / filename
    path.write_text(build_ics_text(prepared_event, uid), encoding="utf-8")

    return IcsWriteResult(
        path=path,
        uid=uid,
        title=prepared_event.title,
        start=prepared_event.start,
        end=prepared_event.end,
    )


def build_event_digest(
    event: dict[str, str],
    prepared_event: "PreparedCalendarEvent",
) -> str:
    identity = "|".join(
        [
            clean_calendar_text(event.get("message_id")),
            prepared_event.title,
            prepared_event.start.isoformat(),
            prepared_event.end.isoformat(),
            prepared_event.location,
        ]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def build_ics_filename(prepared_event: "PreparedCalendarEvent", digest: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", prepared_event.title.lower()).strip("-")
    slug = slug[:40].strip("-") or "event"
    return f"{prepared_event.start:%Y%m%d-%H%M}-{slug}-{digest[:8]}.ics"


def build_ics_text(prepared_event: "PreparedCalendarEvent", uid: str) -> str:
    now_utc = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Gmail Calendar Agent//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        ics_line("UID", uid),
        ics_line("DTSTAMP", now_utc),
        ics_line("DTSTART", format_ics_datetime(prepared_event.start)),
        ics_line("DTEND", format_ics_datetime(prepared_event.end)),
        ics_line("SUMMARY", prepared_event.title),
    ]

    if prepared_event.location:
        lines.append(ics_line("LOCATION", prepared_event.location))
    if prepared_event.description:
        lines.append(ics_line("DESCRIPTION", prepared_event.description))

    lines.extend(["END:VEVENT", "END:VCALENDAR"])
    folded_lines = [fold_ics_line(line) for line in lines]
    return "\r\n".join(folded_lines) + "\r\n"


def ics_line(name: str, value: str) -> str:
    return f"{name}:{escape_ics_text(value)}"


def format_ics_datetime(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")


def escape_ics_text(value: str) -> str:
    return (
        clean_calendar_text(value)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
    )


def fold_ics_line(line: str) -> str:
    chunks = []
    current = ""
    current_length = 0

    for character in line:
        character_length = len(character.encode("utf-8"))
        limit = 75 if not chunks else 74

        if current and current_length + character_length > limit:
            chunks.append(current)
            current = " " + character
            current_length = 1 + character_length
        else:
            current += character
            current_length += character_length

    if current:
        chunks.append(current)

    return "\r\n".join(chunks)


def run_calendar_command(
    command: list[str],
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def should_fallback_to_eventkit(error_detail: str) -> bool:
    return any(marker in error_detail for marker in APPLE_SCRIPT_EVENTKIT_FALLBACK_MARKERS)


def write_event_with_eventkit(prepared_event: PreparedCalendarEvent) -> CalendarWriteResult:
    helper_app_path = build_eventkit_helper()
    open_path = shutil.which("open")
    event_args = [
        prepared_event.title,
        prepared_event.start.date().isoformat(),
        prepared_event.start.strftime("%H:%M"),
        prepared_event.end.date().isoformat(),
        prepared_event.end.strftime("%H:%M"),
        prepared_event.location,
        prepared_event.description,
        prepared_event.calendar_name,
    ]

    if open_path:
        completed, result_text = run_eventkit_helper_with_result(
            [
                open_path,
                "-W",
                "-n",
                helper_app_path,
                "--args",
            ],
            event_args,
            timeout=180,
        )
        launch_detail = (completed.stderr or completed.stdout).strip()
        if not (
            completed.returncode != 0
            and not result_text
            and should_fallback_to_eventkit(launch_detail)
        ):
            return eventkit_result_to_calendar_result(
                completed,
                result_text,
                prepared_event,
            )

    completed, result_text = run_eventkit_helper_with_result(
        [str(EVENTKIT_HELPER_BINARY)],
        event_args,
        timeout=180,
    )
    return eventkit_result_to_calendar_result(completed, result_text, prepared_event)


def run_eventkit_helper_with_result(
    command_prefix: list[str],
    event_args: list[str],
    timeout: int,
) -> tuple[subprocess.CompletedProcess[str], str]:
    result_path = Path(tempfile.gettempdir()) / f"gmail_calendar_result_{os.getpid()}.txt"
    if result_path.exists():
        result_path.unlink()

    command = command_prefix + ["--result-file", str(result_path), *event_args]

    try:
        completed = run_calendar_command(command, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise CalendarWriterError("Calendar access did not respond in time.") from exc

    result_text = result_path.read_text(encoding="utf-8").strip() if result_path.exists() else ""
    if result_path.exists():
        result_path.unlink()

    return completed, result_text


def eventkit_result_to_calendar_result(
    completed: subprocess.CompletedProcess[str],
    result_text: str,
    prepared_event: PreparedCalendarEvent,
) -> CalendarWriteResult:
    if result_text.startswith("OK\n"):
        uid = result_text.split("\n", 1)[1].strip()
        return CalendarWriteResult(
            uid=uid,
            calendar_name=prepared_event.calendar_name,
            title=prepared_event.title,
            start=prepared_event.start,
            end=prepared_event.end,
        )

    if result_text.startswith("ERROR\n"):
        raise CalendarWriterError(add_calendar_permission_help(result_text.split("\n", 1)[1].strip()))

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        if not detail:
            detail = "Unknown Calendar writer error."
        raise CalendarWriterError(add_calendar_permission_help(detail))

    raise CalendarWriterError("Calendar writer finished without returning a result.")


def add_calendar_permission_help(message: str) -> str:
    if "Calendar access" not in message:
        return message

    helper_path = EVENTKIT_HELPER_APP_BUNDLE
    return (
        f"{message} If it is not listed in Calendar privacy settings, "
        f"double-click {helper_path} once, allow Calendar access, then click Confirm again."
    )


def build_eventkit_helper() -> str:
    clang_path = shutil.which("clang")
    if not clang_path:
        raise CalendarWriterError("Could not find clang to build the Calendar writer helper.")

    if not EVENTKIT_HELPER_SOURCE.exists():
        raise CalendarWriterError("Calendar writer helper source file is missing.")
    if not EVENTKIT_HELPER_INFO_PLIST.exists():
        raise CalendarWriterError("Calendar writer helper permission file is missing.")

    helper_is_current = (
        EVENTKIT_HELPER_BINARY.exists()
        and EVENTKIT_HELPER_BUNDLE_INFO_PLIST.exists()
        and EVENTKIT_HELPER_BINARY.stat().st_mtime >= EVENTKIT_HELPER_SOURCE.stat().st_mtime
        and EVENTKIT_HELPER_BINARY.stat().st_mtime >= EVENTKIT_HELPER_INFO_PLIST.stat().st_mtime
        and EVENTKIT_HELPER_BUNDLE_INFO_PLIST.stat().st_mtime
        >= EVENTKIT_HELPER_INFO_PLIST.stat().st_mtime
    )
    if helper_is_current:
        return str(EVENTKIT_HELPER_APP_BUNDLE)

    EVENTKIT_HELPER_BINARY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(EVENTKIT_HELPER_INFO_PLIST, EVENTKIT_HELPER_BUNDLE_INFO_PLIST)
    command = [
        clang_path,
        "-fobjc-arc",
        "-fblocks",
        "-framework",
        "Foundation",
        "-framework",
        "EventKit",
        "-Wl,-sectcreate,__TEXT,__info_plist," + str(EVENTKIT_HELPER_INFO_PLIST),
        str(EVENTKIT_HELPER_SOURCE),
        "-o",
        str(EVENTKIT_HELPER_BINARY),
    ]
    completed = run_calendar_command(command)

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise CalendarWriterError(f"Could not build Calendar writer helper: {detail}")

    sign_eventkit_helper_if_possible()
    return str(EVENTKIT_HELPER_APP_BUNDLE)


def sign_eventkit_helper_if_possible() -> None:
    codesign_path = shutil.which("codesign")
    if not codesign_path:
        return

    completed = run_calendar_command(
        [
            codesign_path,
            "--force",
            "--deep",
            "--sign",
            "-",
            str(EVENTKIT_HELPER_APP_BUNDLE),
        ]
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise CalendarWriterError(f"Could not sign Calendar writer helper: {detail}")


def find_calendar_app_path() -> str:
    for path in CALENDAR_APP_PATHS:
        if path.exists():
            return str(path)

    raise CalendarWriterError("Calendar.app was not found on this Mac.")


@dataclass(frozen=True)
class PreparedCalendarEvent:
    title: str
    start: datetime
    end: datetime
    location: str
    description: str
    calendar_name: str


def prepare_calendar_event(
    event: dict[str, str],
    calendar_name: str = DEFAULT_CALENDAR_NAME,
) -> PreparedCalendarEvent:
    event_date = parse_event_date(event.get("date", ""))
    start_time, end_time = parse_event_time(event.get("time", ""))

    start = datetime.combine(event_date, start_time)
    end = datetime.combine(event_date, end_time)

    if end <= start:
        end += timedelta(days=1)

    title = clean_calendar_text(event.get("title")) or "Email event"
    location = clean_optional_field(event.get("location"))
    description = build_description(event)

    return PreparedCalendarEvent(
        title=title,
        start=start,
        end=end,
        location=location,
        description=description,
        calendar_name=calendar_name,
    )


def parse_event_date(value: str | None) -> date:
    value = clean_calendar_text(value)

    if not value or value == NEEDS_REVIEW:
        raise CalendarEventValidationError("Add a date before sending this event to Calendar.")

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CalendarEventValidationError(
            f"Calendar needs an ISO date like 2026-05-28, got {value!r}."
        ) from exc


def parse_event_time(value: str | None) -> tuple[time, time]:
    value = clean_calendar_text(value)

    if not value or value == NEEDS_REVIEW:
        raise CalendarEventValidationError("Add a time before sending this event to Calendar.")

    range_match = TIME_RANGE_PATTERN.match(value)
    if range_match:
        return (
            parse_time_value(range_match.group("start")),
            parse_time_value(range_match.group("end")),
        )

    start = parse_time_value(value)
    end_datetime = datetime.combine(date.today(), start) + DEFAULT_EVENT_DURATION
    return start, end_datetime.time()


def parse_time_value(value: str) -> time:
    match = TIME_PATTERN.match(value)
    if not match:
        raise CalendarEventValidationError(
            f"Calendar needs a 24-hour time like 15:00, got {value!r}."
        )

    hour = int(match.group("hour"))
    minute = int(match.group("minute"))

    try:
        return time(hour=hour, minute=minute)
    except ValueError as exc:
        raise CalendarEventValidationError(
            f"Calendar needs a valid time, got {value!r}."
        ) from exc


def build_description(event: dict[str, str]) -> str:
    parts = []
    description = clean_optional_field(event.get("description"))
    source_email = clean_optional_field(event.get("source_email"))

    if description:
        parts.append(description)
    if source_email:
        parts.append(f"Source email: {source_email}")

    return "\n\n".join(parts)


def clean_optional_field(value: str | None) -> str:
    value = clean_calendar_text(value)
    return "" if value == NEEDS_REVIEW else value


def clean_calendar_text(value: str | None) -> str:
    if value is None:
        return ""

    return str(value).strip()
