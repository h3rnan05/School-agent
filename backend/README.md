# Backend — Blackboard module (Phase 2 / 2.1)

This is the only module implemented so far: read-only access to Blackboard
via `BlackboardProvider` / `PlaywrightBlackboardProvider`. Nothing here
touches PostgreSQL, Google Calendar, Claude, Telegram, or the frontend —
see [`../ARCHITECTURE.md`](../ARCHITECTURE.md) for how this fits into the
full system and why those are separate, later phases.

## Important: this must be run on YOUR machine, not in a cloud session

`blackboard login` opens a real, visible browser window and waits for
**you** to type your credentials and complete MFA/SSO into it. That's a
hard requirement — this code never sees or stores your password, and never
tries to automate past MFA/SSO/CAPTCHA.

That only works if you run the CLI somewhere you have a screen and a
terminal you're typing into directly — your laptop, for instance. It does
**not** work inside a remote/cloud Claude Code session: there's no display
for you to see the browser on, and no interactive terminal for the
"press ENTER" prompt to reach. If you're reading this from such a session,
that's why login couldn't be demonstrated live there — clone this repo (or
pull the branch) locally and follow the steps below.

## Setup

Requires **Python 3.9+**. On macOS, the system `python3` (from Xcode
Command Line Tools) is commonly 3.9 — that's fine, this code is tested
against it, but if `python3 --version` shows something older, install a
newer Python (e.g. `brew install python@3.11`) first.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install --upgrade pip        # macOS's bundled pip is often very old
pip install -r requirements.txt
playwright install chromium      # downloads the browser binary Playwright drives
```

## Configuration

Everything is read from environment variables — nothing is hardcoded to a
specific institution:

| Variable | Required | Default | Notes |
|---|---|---|---|
| `BLACKBOARD_BASE_URL` | **yes** | — | e.g. `https://cursos-udem.blackboard.com` |
| `BLACKBOARD_COURSES_PATH` | no | `/ultra/course` | Appended to the base URL to reach the course list. The Ultra Experience default matches what Phase 2.1 confirmed for UDEM; set to `""` for an institution on plain Original Experience (course list is the portal homepage). |
| `BLACKBOARD_TIMEZONE` | no | `UTC` | IANA name. Used to interpret due dates that don't carry their own timezone info — see "Timezone handling" below. |
| `SCHOOL_AGENT_STATE_DIR` | no | `~/.school-agent` | Where the encrypted session, its key, the change-detection cache, and debug screenshots live. Never put this inside the repo. |
| `BLACKBOARD_HEADLESS` | no | `true` | Set to `false` to watch the browser during `courses`/`assignments`/`upcoming` too (useful for debugging selectors). `login` always runs headful regardless of this setting. |
| `BLACKBOARD_LOGIN_TIMEOUT_SECONDS` | no | `600` | How long `login` waits for you to finish manual SSO/MFA. |
| `BLACKBOARD_PROVIDER_IMPL` | no | `playwright` | `playwright` or `official` (the latter is an intentional stub today). |

Example (UDEM):

```bash
export BLACKBOARD_BASE_URL="https://cursos-udem.blackboard.com"
export BLACKBOARD_TIMEZONE="America/Monterrey"
```

## Running the CLI

From `backend/`, with the venv active:

```bash
python -m app.blackboard login
```

This opens a **visible** Chromium window at `BLACKBOARD_BASE_URL`. Log in
by hand — including whatever SSO provider and MFA step your institution
uses. Nothing you type into that browser window is seen or stored by this
program. Once you can see your authenticated Blackboard homepage, come
back to the terminal and press ENTER as it asks. Your session (cookies) is
then saved, encrypted, under `SCHOOL_AGENT_STATE_DIR` — never your
password, never a plaintext session file.

```bash
python -m app.blackboard courses
```

Navigates to `BLACKBOARD_COURSES_PATH` (`/ultra/course` by default) and
lists the courses detected, including per-course view detection (Step 3):

```
COURSES FOUND

course_id:   _98765_1
course_name: FINC 301 - Corporate Finance
course_url:  https://cursos-udem.blackboard.com/ultra/courses/_98765_1/outline
course_view: ORIGINAL
instructor:  Dr. Maria Gonzalez

course_id:   _98766_1
course_name: CS 450 - Machine Learning
course_url:  https://cursos-udem.blackboard.com/ultra/courses/_98766_1/outline
course_view: ULTRA
instructor:  Dr. Carlos Ruiz
```

`course_view` is read per course from the course card itself — never
assumed from the institution being on Ultra Experience. If it can't be
determined it prints `UNKNOWN` rather than a guess, and the command tells
you how many courses that happened for.

```bash
python -m app.blackboard assignments _98765_1
```

Lists assignments for a single course (use a `course_id` from the
`courses` output). Which parser runs depends on that course's
`course_view`: `OriginalCourseParser` for `ORIGINAL`, `UltraCourseParser`
for `ULTRA` (currently a stub — see below), and a disclosed best-effort
attempt with `OriginalCourseParser` for `UNKNOWN`.

For `ORIGINAL` courses, this automatically visits every content-area link
in the course's own menu (e.g. "Unidad 1", "Unidad 2") and aggregates
results — it does not just parse whatever page it first lands on. Tool
links (Discussions, Announcements, My Grades, ...) and external links are
recognized and skipped, never visited. See
`app/blackboard/parsers/DOM_NOTES.md` for exactly how that classification
works and what's confirmed vs still unverified.

```bash
python -m app.blackboard upcoming
python -m app.blackboard upcoming --days 14
python -m app.blackboard upcoming --include-overdue --include-no-due-date
```

Lists assignments due in the next N days (default 7) across all courses:

```
UPCOMING (next 7 days)

COURSE: FINC 301 - Corporate Finance
ASSIGNMENT: Chapter 4 Homework
DUE DATE: August 12, 2026
TIME: 11:59 PM
TIMEZONE: America/Monterrey
POINTS: 50 points
URL: https://cursos-udem.blackboard.com/webapps/blackboard/content/listContent.jsp?content_id=_9001_1&course_id=_98765_1
COURSE VIEW: ORIGINAL
STATUS: UPCOMING
```

The date/time shown is in the assignment's own recorded timezone (printed
on the `TIMEZONE` line), not silently converted to UTC or your system
timezone.

Any command that lists assignments also compares them against the local
snapshot cache from the previous run and prints changes, e.g.:

```
[CHANGED] Chapter 4 Homework: due date 2026-08-10 23:59:00+00:00 -> 2026-08-12 23:59:00+00:00
```

You can also run it as `python -m app.blackboard --help` for the full
command reference, and add `--verbose` to any command for debug logging.

## Timezone handling

Blackboard's displayed due dates rarely carry explicit timezone info in
the page text — usually just "August 12, 2026 11:59 PM". When that's the
case, this code interprets it using `BLACKBOARD_TIMEZONE` (your
configured institution timezone, e.g. `America/Monterrey` for UDEM) and
records that assumption on the assignment itself (`timezone` field) rather
than converting it away silently. If a due date *does* include explicit
timezone info, that's what's used instead. There's no code path that
converts a due date to UTC (or anywhere else) and then drops the record of
which zone it came from.

## Architecture: OriginalCourseParser vs UltraCourseParser

Phase 2.1 confirmed (via UDEM) that an institution on Ultra Experience can
still have individual courses running Original Course View — so there is
no single "Blackboard parser". Parsing is split by responsibility:

```
PlaywrightBlackboardProvider
        │
        ├── CourseListParser        (course list page -> Course DTOs,
        │                             including course_view detection)
        │
        └── AssignmentParser        (routes by Course.course_view)
                ├── OriginalCourseParser   (implemented, fixture-tested)
                └── UltraCourseParser      (stub — see below)
```

All of them live under `app/blackboard/parsers/`, share low-level HTML
helpers from `parsers/common.py`, and produce the exact same `Course` /
`Assignment` DTOs regardless of which course-view path was taken.

`UltraCourseParser` is **not implemented**: no real Ultra Course View
content page was available to inspect. It returns an empty list with a
loud warning rather than guessing Ultra's DOM — see its docstring for
exactly what's needed to build it for real.

## An honest note on the parsers

None of the selectors in `parsers/course_list.py` or
`parsers/original_course.py` were built from real UDEM HTML — no real page
was available while writing this (see the top of this file for why). They
were built from a textual description of what your course cards show, plus
generic patterns common to Blackboard Original/Ultra. Every extraction
step logs a warning and returns "not found" / `UNKNOWN` (never a guess)
when nothing matches, instead of crashing or inventing data.

**See [`app/blackboard/parsers/DOM_NOTES.md`](app/blackboard/parsers/DOM_NOTES.md)**
for the full DATA → selector → fallback → evidence table (Step 9), and for
exactly what to paste back here (a course card's outer HTML, no login
needed) if `courses` or `assignments` comes back wrong once you run this
locally.

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

This module does **not**: connect to PostgreSQL, call Google Calendar,
call Claude, send Telegram notifications, or expose a frontend. It also
does not download attachment file contents (only filename/URL/type
references), does not fetch full assignment detail pages
(description/instructions are left unset from the list view), and does
not submit/edit/delete anything on Blackboard — see
`tests/blackboard/test_provider_safety.py` for that guarantee enforced in
code, not just documentation. See `ARCHITECTURE.md` for the full phased
plan.
