# Gmail Calendar Agent

A small Streamlit prototype that reads sample emails or recent Gmail messages, extracts possible calendar events, and writes confirmed events to Apple Calendar.

## Run the demo

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

## Gmail setup

The app uses read-only Gmail access.

1. Open Google Cloud Console and create a project.
2. Enable the Gmail API.
3. Configure the OAuth consent screen.
4. Create an OAuth Client ID and choose Desktop App.
5. Download the file and rename it to `credentials.json`.
6. Put `credentials.json` in this project folder, next to `app.py`.
7. Run the app and choose `Gmail`.
8. Click `Create Gmail login link`, then click `Open Google login`.
9. Allow Gmail read-only access. Google will return to the local app.
10. Click `Connect and scan Gmail`.

After approval, the app saves `token.json` locally so the next run can reuse the login.

`credentials.json` and `token.json` are ignored by Git and should not be uploaded to GitHub.

## Current behavior

- Sample mode reads files from `data/sample_emails/`.
- Gmail mode reads the latest 10-20 inbox messages.
- Each Gmail message is normalized with `message_id`, `subject`, `sender`, `date`, and `body`.
- Extracted events are shown in a preview step with `Confirm` and `Skip` buttons.
- Confirmed events are added to an Apple Calendar named `Email Agent`.
- Confirmed or skipped Gmail messages are recorded in `data/processed_emails.json`, so future scans leave them out.
- If Apple Calendar cannot be written, the app creates an `.ics` fallback file in `ics/`.
- The first calendar write may ask for macOS Calendar access.
- If no permission prompt appears, double-click `Calendar Writer Helper/Gmail Calendar Agent Calendar Writer.app`, then open System Settings > Privacy & Security > Calendars and allow `Gmail Calendar Agent Calendar Writer`.

To use an `.ics` fallback, open the generated file from `ics/` and import it into your calendar app.
