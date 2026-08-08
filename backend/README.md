# Backend — Blackboard module (Phase 2)

This is the only module implemented so far, per Phase 2 scope: read-only
access to Blackboard via `BlackboardProvider` /
`PlaywrightBlackboardProvider`. Nothing here touches PostgreSQL, Google
Calendar, Claude, Telegram, or the frontend — see
[`../ARCHITECTURE.md`](../ARCHITECTURE.md) for how this fits into the full
system and why those are separate, later phases.

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium      # downloads the browser binary Playwright drives
```

## Configuration

Everything is read from environment variables — nothing is hardcoded to a
specific institution:

| Variable | Required | Default | Notes |
|---|---|---|---|
| `BLACKBOARD_BASE_URL` | **yes** | — | e.g. `https://your-institution.blackboard.com` |
| `BLACKBOARD_TIMEZONE` | no | `UTC` | IANA name, e.g. `America/Bogota`. Used to interpret due dates that don't include an explicit timezone. |
| `SCHOOL_AGENT_STATE_DIR` | no | `~/.school-agent` | Where the encrypted session, its key, the change-detection cache, and debug screenshots live. Never put this inside the repo. |
| `BLACKBOARD_HEADLESS` | no | `true` | Set to `false` to watch the browser during `courses`/`assignments`/`upcoming` too (useful for debugging selectors). `login` always runs headful regardless of this setting. |
| `BLACKBOARD_LOGIN_TIMEOUT_SECONDS` | no | `600` | How long `login` waits for you to finish manual SSO/MFA. |
| `BLACKBOARD_PROVIDER_IMPL` | no | `playwright` | `playwright` or `official` (the latter is an intentional stub today). |

Example:

```bash
export BLACKBOARD_BASE_URL="https://your-institution.blackboard.com"
export BLACKBOARD_TIMEZONE="America/Bogota"
```

## Running the CLI

From `backend/`, with the venv active:

```bash
python -m app.blackboard login
```

This opens a **visible** Chromium window pointed at your Blackboard. Log in
by hand — including whatever SSO provider and MFA step your institution
uses. Nothing you type into that browser window is seen or stored by this
program. Once you can see your Blackboard homepage, come back to the
terminal and press ENTER as it asks. Your session (cookies) is then saved,
encrypted, under `SCHOOL_AGENT_STATE_DIR`.

```bash
python -m app.blackboard courses
```

Lists the courses detected on your account:

```
COURSES FOUND

course_id:   _12345_1
course_name: FINANCE 301 - Corporate Finance
course_url:  https://your-institution.blackboard.com/webapps/blackboard/execute/courseMain?course_id=_12345_1
```

```bash
python -m app.blackboard assignments _12345_1
```

Lists assignments for a single course (use a `course_id` from the `courses`
output).

```bash
python -m app.blackboard upcoming
python -m app.blackboard upcoming --days 14
python -m app.blackboard upcoming --include-overdue --include-no-due-date
```

Lists assignments due in the next N days (default 7) across all courses:

```
UPCOMING (next 7 days)

COURSE: _12345_1
ASSIGNMENT: Chapter 4 Homework
DUE: August 12, 2026 11:59 PM
URL: https://your-institution.blackboard.com/webapps/blackboard/content/listContent.jsp?content_id=_9001_1&course_id=_12345_1
STATUS: UPCOMING
```

Any command that lists assignments also compares them against the local
snapshot cache from the previous run and prints changes, e.g.:

```
[CHANGED] Chapter 4 Homework: due date 2026-08-10 23:59:00+00:00 -> 2026-08-12 23:59:00+00:00
```

You can also run it as `python -m app.blackboard --help` for the full
command reference, and add `--verbose` to any command for debug logging.

## An honest note on the parser

`app/blackboard/parser.py` was written without access to your actual
Blackboard's HTML — no real page was available while building this. The
selectors it tries are a best-effort fallback chain based on common
patterns across Blackboard Original Experience and Ultra, and every
extraction step logs a warning and returns "not found" (never a guess) when
nothing matches, instead of crashing or inventing data.

If `courses` or `assignments` comes back empty against your real
Blackboard, that almost certainly means the selectors need adjusting for
your institution's skin — see `ARCHITECTURE.md` section 16 for the list of
things (base URL, Ultra vs Original, and ideally a couple of sanitized
screenshots or saved HTML pages) that would let the selector lists in
`parser.py` be corrected precisely instead of guessed at again.

## Running tests / lint / type checks

```bash
python -m pytest -q
ruff check app tests
mypy app tests
```

All of these run against fixture HTML and a fake provider — none of them
open a real browser or touch a real Blackboard instance, so they run the
same in CI as on your machine.

## What's out of scope here (by design)

Per Phase 2 scope, this module does **not**: connect to PostgreSQL, call
Google Calendar, call Claude, send Telegram notifications, or expose a
frontend. It also does not download attachment file contents (only
filename/URL/type references) and does not fetch full assignment detail
pages (description/instructions are left unset from the list view — a
later phase's job). See `ARCHITECTURE.md` for the full phased plan.
