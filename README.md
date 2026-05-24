# Gmail Calendar Agent

A small Streamlit prototype that reads sample emails or recent Gmail messages, extracts possible calendar events, and asks the user to confirm or skip each event before anything is written to a calendar.

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
7. Run the app, choose `Gmail`, then click `Connect and scan Gmail`.

On the first Gmail scan, Google opens a browser login page. After approval, the app saves `token.json` locally so the next run can reuse the login.

`credentials.json` and `token.json` are ignored by Git and should not be uploaded to GitHub.

## Current behavior

- Sample mode reads files from `data/sample_emails/`.
- Gmail mode reads the latest 10-20 inbox messages.
- Each Gmail message is normalized with `message_id`, `subject`, `sender`, `date`, and `body`.
- Extracted events are shown in a preview step with `Confirm` and `Skip` buttons.
- Apple Calendar writing will be added in the next step.
