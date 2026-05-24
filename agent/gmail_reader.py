from __future__ import annotations

import base64
import html as html_lib
import re
from pathlib import Path
from typing import Any


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CREDENTIALS_PATH = PROJECT_ROOT / "credentials.json"
DEFAULT_TOKEN_PATH = PROJECT_ROOT / "token.json"


class GmailReaderError(RuntimeError):
    """Raised when Gmail cannot be read."""


class GmailSetupError(GmailReaderError):
    """Raised when local Gmail OAuth setup is incomplete."""


def read_recent_emails(
    max_results: int = 10,
    credentials_path: Path | str = DEFAULT_CREDENTIALS_PATH,
    token_path: Path | str = DEFAULT_TOKEN_PATH,
    user_id: str = "me",
) -> list[dict[str, str]]:
    """Read recent Gmail inbox messages in the normalized email shape used by the app."""

    service = build_gmail_service(credentials_path, token_path)
    max_results = max(1, min(max_results, 20))

    response = (
        service.users()
        .messages()
        .list(userId=user_id, labelIds=["INBOX"], maxResults=max_results)
        .execute()
    )
    message_refs = response.get("messages", [])

    emails = []
    for message_ref in message_refs:
        message = (
            service.users()
            .messages()
            .get(userId=user_id, id=message_ref["id"], format="full")
            .execute()
        )
        emails.append(gmail_message_to_email(message))

    return emails


def build_gmail_service(
    credentials_path: Path | str = DEFAULT_CREDENTIALS_PATH,
    token_path: Path | str = DEFAULT_TOKEN_PATH,
) -> Any:
    credentials_path = Path(credentials_path)
    token_path = Path(token_path)

    if not token_path.exists() and not credentials_path.exists():
        raise GmailSetupError(
            f"Missing {credentials_path.name}. Download it from Google Cloud "
            f"Console and place it in {credentials_path.parent}."
        )

    Request, Credentials, InstalledAppFlow, build = _load_google_libraries()

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        if not credentials_path.exists():
            raise GmailSetupError(
                f"Missing {credentials_path.name}. Download it from Google Cloud "
                f"Console and place it in {credentials_path.parent}."
            )

        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
        creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


def gmail_message_to_email(message: dict[str, Any]) -> dict[str, str]:
    payload = message.get("payload", {})
    headers = _headers_by_name(payload.get("headers", []))

    subject = headers.get("subject", "No subject").strip() or "No subject"
    sender = headers.get("from", "Unknown sender").strip() or "Unknown sender"
    sent_date = headers.get("date", "Unknown date").strip() or "Unknown date"
    message_id = message.get("id", "")
    body = _extract_message_body(payload) or message.get("snippet", "")

    return {
        "id": message_id,
        "message_id": message_id,
        "thread_id": message.get("threadId", ""),
        "subject": subject,
        "sender": sender,
        "date": sent_date,
        "body": body,
        "source": f"Gmail message {message_id}",
    }


def _load_google_libraries() -> tuple[Any, Any, Any, Any]:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise GmailSetupError(
            "Gmail packages are not installed. Run `python -m pip install -r "
            "requirements.txt` from the project folder."
        ) from exc

    return Request, Credentials, InstalledAppFlow, build


def _headers_by_name(headers: list[dict[str, str]]) -> dict[str, str]:
    return {
        header.get("name", "").lower(): header.get("value", "")
        for header in headers
        if header.get("name")
    }


def _extract_message_body(payload: dict[str, Any]) -> str:
    plain_parts: list[str] = []
    html_parts: list[str] = []

    def visit(part: dict[str, Any]) -> None:
        mime_type = part.get("mimeType", "")
        data = part.get("body", {}).get("data")

        if data:
            decoded = _decode_base64url(data)
            if mime_type == "text/plain":
                plain_parts.append(decoded)
            elif mime_type == "text/html":
                html_parts.append(_html_to_text(decoded))

        for child in part.get("parts", []):
            visit(child)

    visit(payload)
    body = "\n".join(plain_parts or html_parts)
    return _clean_body_text(body)


def _decode_base64url(data: str) -> str:
    padding = "=" * (-len(data) % 4)
    decoded = base64.urlsafe_b64decode((data + padding).encode("utf-8"))
    return decoded.decode("utf-8", errors="replace")


def _html_to_text(raw_html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw_html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return html_lib.unescape(text)


def _clean_body_text(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)
