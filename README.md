# Cambridge Co-founder Platform

Minimal MVP for verified Cambridge students to discover potential co-founders, send a short intro request, and unlock LinkedIn or Cambridge email once a request is accepted.

## Quickstart

If someone else wants to run this project on their own machine, these are the steps:

1. Clone the repository:

```bash
git clone <YOUR_GITHUB_REPO_URL>
cd cue-cofounder-matching-platform
```

2. Create and activate a virtual environment:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Check the root `.env` file.

For local development, you can leave SMTP unconfigured and use dev OTP codes, or add real Resend SMTP values if you want OTP emails delivered.

5. Start the app:

```bash
uvicorn backend.app.main:app --reload
```

6. Open the app in your browser:

```text
http://127.0.0.1:8000
```

## Local login flow

- Cambridge login:
  - Dev mode: if `OTP_DEV_MODE=true`, request an OTP and use the visible `dev_code`
  - SMTP mode: if SMTP is configured and `OTP_DEV_MODE=false`, the OTP is sent by email
- Demo mode: click `Explore demo` on the landing page

## Stack

- Frontend: React SPA served directly by FastAPI static files
- Backend: FastAPI
- Database: SQLite
- Auth: email OTP

## Project structure

```text
backend/
  app/
    main.py          FastAPI app and routes
    database.py      SQLite schema, seed data, matching, helpers
    schemas.py       Request models
    __init__.py
  data/              SQLite database created automatically on first run
  uploads/           Uploaded profile photos
frontend/
  index.html         SPA entry
  app.js             React app
  app.jsx            Mirror of app.js for editing convenience
  styles.css         Minimal UI styling
.env
requirements.txt
README.md
```

## What is included

- Cambridge-only email OTP login
- Seeded demo login for walkthroughs
- Short profile creation and editing
- Default profile avatars plus custom photo upload
- Deterministic matching feed
- Profile detail with hidden contacts until acceptance
- Connect request flow with pending, accepted, and declined states
- Accepted connections page with unlocked LinkedIn and Cambridge email
- Lightweight daily limits
  - 25 profile detail views per day
  - 10 connect requests per day

## SMTP configuration

The app loads settings automatically from the root `.env` file.

For Resend SMTP, use:

```text
SMTP_HOST=smtp.resend.com
SMTP_PORT=587
SMTP_USERNAME=resend
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_FROM_NAME=Cambridge Co-founder Platform
SMTP_USE_TLS=true
OTP_DEV_MODE=false
```

Fill in:

- `SMTP_PASSWORD` with your Resend API key
- `SMTP_FROM_EMAIL` with a verified sender email on your Resend domain

If SMTP is not configured and `OTP_DEV_MODE=true`, the app falls back to visible OTP codes for development.

## Notes

- Contact details are only revealed after a connect request is accepted
- Demo users cannot edit the demo profile, send real requests, or unlock contact details
- The SQLite database is created automatically at `backend/data/cambridge_cofounder.db`
- Uploaded profile photos are stored at `backend/uploads/`
- The frontend uses browser ESM imports from `esm.sh`, so there is no separate Node frontend setup for local development
