# DOM evidence notes (Phase 2.1)

Per Step 9: for every important piece of data, this documents the selector
strategy and fallback used, and — critically — **whether it's based on
real evidence or is still an unverified best guess.**

No real HTML from `cursos-udem.blackboard.com` was available while writing
this (see the top-level explanation for why this session can't drive an
interactive login). What *was* available: your text description of the
`/ultra/course` page (course cards showing Course ID, Course name, Course
view, Instructor, Open, More info) and the confirmed fact that some course
cards read "Original Course View". That's real evidence, just not DOM —
so the entries below are marked accordingly.

## Course list (`parsers/course_list.py`)

| DATA | Selector strategy | Fallback | Evidence |
|---|---|---|---|
| Card container | `[data-testid*="course-list-item" i]` → `[data-testid*="course-card" i]` → `[role="article"]` → `[role="listitem"]` | If none match, skip cards entirely and scan the whole page for course links directly (Original Experience's flatter markup) | **Unverified.** Ultra pages are React apps and commonly use `data-testid`/ARIA roles for exactly this kind of repeated-item list, but no real attribute name was seen. |
| Course link (within a card) | `a[href*="/ultra/courses/"]` → `a[href*="course_id="]` | None found → card skipped | **Partially verified.** The `/ultra/courses/` URL segment is standard Ultra Experience routing (confirmed by Blackboard's own product documentation pattern, not by seeing your page). `course_id=` is Original Experience's classic query param. |
| Course name | Link text, then `aria-label` on the link | Falls back to the course id itself rather than an empty string | Unverified against real markup. |
| Course view | Literal substring search for `"original course view"` / `"ultra course view"` (case-insensitive) across the card's full text | `CourseView.UNKNOWN` — never guessed | **Best evidence we have**: you explicitly reported this exact label text appears on the card. This is the one piece of the parser built from something closer to ground truth. |
| Instructor | Line-based label scan: a line matching `/instructor/i`, then either the remainder of that same line or the next line | `None` | Unverified layout (label-on-own-line vs same-line-colon), but the field's *existence* is confirmed by your description. |
| Term | — | Always `None` | Not attempted — no evidence a term/semester label exists on the card at all; left unset rather than guessed. |

## Assignments — Original Course View (`parsers/original_course.py`)

Unchanged from Phase 2. Validated against synthetic fixtures only, never
against a real Original Course View course content page. See
`backend/README.md`'s "honest note on the parser" section.

## Assignments — Ultra Course View (`parsers/ultra_course.py`)

Not attempted. `UltraCourseParser` is a stub that returns `[]` with a
warning — see its module docstring. Zero evidence was available about
Ultra Course View's content-page DOM.

## How to turn "unverified" into "verified"

Run `blackboard courses` locally (see `backend/README.md`) and tell me,
for one course card:

1. Whether it printed the right `course_id` / `course_name` / `course_view`
   / `instructor`, or came back wrong/empty.
2. If wrong: open DevTools on `cursos-udem.blackboard.com/ultra/course`,
   right-click the card → Inspect, and paste the outer HTML of just that
   one card (it's fine to redact anything personally identifying beyond
   course name/instructor, which Blackboard already shows you regardless).

That's enough to replace a guessed selector in the table above with a
confirmed one, without ever needing your login session.
