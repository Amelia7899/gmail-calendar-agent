from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MEMORY_PATH = PROJECT_ROOT / "data" / "processed_emails.json"


def load_processed_message_ids(
    memory_path: Path | str = DEFAULT_MEMORY_PATH,
) -> set[str]:
    path = Path(memory_path)
    if not path.exists():
        return set()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()

    if isinstance(data, list):
        raw_ids = data
    elif isinstance(data, dict):
        raw_ids = data.get("processed_message_ids", [])
    else:
        raw_ids = []

    return {
        message_id
        for message_id in (normalize_message_id(value) for value in raw_ids)
        if message_id
    }


def save_processed_message_ids(
    message_ids: Iterable[str],
    memory_path: Path | str = DEFAULT_MEMORY_PATH,
) -> None:
    path = Path(memory_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"processed_message_ids": sorted(set(message_ids))}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def mark_message_processed(
    message_id: str | None,
    memory_path: Path | str = DEFAULT_MEMORY_PATH,
) -> bool:
    message_id = normalize_message_id(message_id)
    if not message_id:
        return False

    processed_ids = load_processed_message_ids(memory_path)
    if message_id in processed_ids:
        return False

    processed_ids.add(message_id)
    save_processed_message_ids(processed_ids, memory_path)
    return True


def is_message_processed(
    message_id: str | None,
    memory_path: Path | str = DEFAULT_MEMORY_PATH,
) -> bool:
    message_id = normalize_message_id(message_id)
    return bool(message_id and message_id in load_processed_message_ids(memory_path))


def filter_unprocessed_emails(
    emails: list[dict[str, str]],
    memory_path: Path | str = DEFAULT_MEMORY_PATH,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    processed_ids = load_processed_message_ids(memory_path)
    unprocessed_emails = []
    skipped_emails = []

    for email in emails:
        message_id = normalize_message_id(email.get("message_id"))
        if message_id and message_id in processed_ids:
            skipped_emails.append(email)
            continue

        unprocessed_emails.append(email)

    return unprocessed_emails, skipped_emails


def normalize_message_id(message_id: object) -> str:
    if message_id is None:
        return ""

    return str(message_id).strip()
