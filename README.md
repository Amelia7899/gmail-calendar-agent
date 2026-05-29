# Gmail Calendar Agent

A Streamlit prototype that scans email, finds likely calendar events, creates `.ics` files for confirmed items, and tries to add them to Apple Calendar. It can work from bundled sample emails or from a connected Gmail inbox, so the app is usable before any Google setup is done.

The app is intentionally review-first: extracted events are shown in a preview table, and nothing is created until you click `Confirm`.

## What it does

- Reads sample emails from `data/sample_emails/` or recent Gmail inbox messages.
- Extracts event title, date, time, location, description, and source email.
- Uses rule-based extraction by default.
- Can use OpenAI extraction when `OPENAI_API_KEY` is set, with rule-based fallback.
- Lets you confirm or skip each extracted event.
- Creates an `.ics` file in `ics/` for each confirmed event.
- Tries to write confirmed events to an Apple Calendar named `Email Agent`.
- Remembers confirmed or skipped Gmail messages in `data/processed_emails.json` to avoid repeat processing.

## Requirements

- Python 3.10 or newer.
- macOS if you want direct Apple Calendar sync.
- Google Cloud OAuth credentials if you want to read Gmail.
- Optional: an OpenAI API key for LLM-based extraction.

The sample-email flow works without Gmail, OpenAI, or Apple Calendar access.

## Setup

From this project folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Run the app:

```bash
streamlit run app.py
```

Streamlit should open the app in your browser. If it does not, use the local URL printed in the terminal.

## Quick Demo

1. Start the app with `streamlit run app.py`.
2. Keep `Extraction method` set to `Rule-based`.
3. Choose `Sample emails`.
4. Click `Scan sample emails`.
5. Review the extracted events.
6. Click `Confirm` to create an `.ics` file and add the event to Calendar, or `Skip` to ignore it.

The `.ics` file is created after `Confirm` whether or not Apple Calendar sync succeeds.

## Gmail Setup

The app only asks for read-only Gmail access.

1. Open Google Cloud Console and create or select a project.
2. Enable the Gmail API.
3. Configure the OAuth consent screen.
4. Create an OAuth Client ID.
5. Choose `Desktop app` as the application type.
6. Download the client secret JSON file.
7. Rename it to `credentials.json`.
8. Put `credentials.json` in this project folder, next to `app.py`.
9. Start the app and choose `Gmail`.
10. Click `Create Gmail login link`.
11. Click `Open Google login` and approve read-only Gmail access.
12. Return to the Streamlit page and click `Connect and scan Gmail`.

After approval, the app saves `token.json` locally so future runs can reuse the login.

## Optional LLM Extraction

Rule-based extraction is the default. To enable the `LLM + rules fallback` mode, set an OpenAI API key before starting Streamlit:

```bash
export OPENAI_API_KEY="your_api_key_here"
streamlit run app.py
```

By default, the app uses `gpt-4o-mini`. You can choose another model with:

```bash
export OPENAI_MODEL="gpt-4o-mini"
```

If the LLM call fails or the key is missing, the app falls back to the rule-based parser.

## Apple Calendar Access

Confirmed events always create an `.ics` file under `ics/`. The app then tries to write the same event to a calendar named `Email Agent`.

On the first write, macOS may ask for Calendar permission. Allow access when prompted. If no prompt appears, open:

```text
Calendar Writer Helper/Gmail Calendar Agent Calendar Writer.app
```

Then go to:

```text
System Settings > Privacy & Security > Calendars
```

Allow calendar access for the helper app before confirming events if you want direct Apple Calendar sync.

If Apple Calendar sync is unavailable or fails, the generated `.ics` file is still available in `ics/` and can be imported into your calendar app.

## Project Structure

```text
gmail-calendar-agent/
|-- app.py                              # Streamlit UI and review flow
|-- agent/
|   |-- event_extractor.py              # Rule-based and optional LLM extraction
|   |-- gmail_reader.py                 # Gmail OAuth and message loading
|   |-- calendar_writer.py              # Apple Calendar and ICS writing
|   |-- memory.py                       # Processed Gmail message tracking
|   |-- calendar_eventkit_writer.m      # macOS Calendar helper source
|   `-- calendar_eventkit_writer_info.plist
|-- data/
|   `-- sample_emails/                  # Demo email fixtures
|-- ics/                                # Generated ICS files
|-- requirements.txt
`-- README.md
```

## Local Files and Privacy

These files are created locally and should not be committed:

- `credentials.json`: Google OAuth client credentials.
- `token.json`: Gmail access token.
- `.gmail_oauth_state.json`: temporary OAuth login state.
- `data/processed_emails.json`: IDs of Gmail messages already confirmed or skipped.
- `ics/*.ics`: generated calendar files.
- `Calendar Writer Helper/`: generated macOS helper app.

They are already listed in `.gitignore`.

## Troubleshooting

**`credentials.json` is missing**

Download the OAuth client JSON file from Google Cloud Console, rename it to `credentials.json`, and place it beside `app.py`.

**Gmail login expired**

Click `Create Gmail login link` again and restart the Google login flow.

**No Gmail messages appear**

The app scans recent inbox messages only. Increase the slider up to 20 messages, or test the extraction flow with sample emails first.

**Calendar says a date needs review**

The extracted event is missing a concrete date. If the event has a date but no time, the app creates it as an all-day event.

**Calendar permission did not show up**

Open the helper app once from `Calendar Writer Helper/`, then allow it under macOS Calendar privacy settings.

**Test Apple Calendar sync failure**

Start Streamlit with `FORCE_CALENDAR_WRITE_FAILURE=1 streamlit run app.py`, then click `Confirm`. The app should still create an `.ics` file and mark the event confirmed while showing the simulated Apple Calendar sync failure.

**Running outside macOS**

Direct Apple Calendar sync requires macOS. On other systems, use the `.ics` files generated in `ics/`.
