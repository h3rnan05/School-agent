# DOM evidence notes (Phase 2.1)

Per Step 9: for every important piece of data, this documents the selector
strategy and fallback used, and — critically — **whether it's based on
real evidence or is still an unverified best guess.**

**Update — CONFIRMED against real markup.** You shared the actual DOM
structure from DevTools against `cursos-udem.blackboard.com` (redacted of
personal data). The selectors below were rewritten from that evidence; the
table marks exactly what's confirmed vs still an assumption.

## Course list (`parsers/course_list.py`)

Verified against a real run against `cursos-udem.blackboard.com`: `courses`
correctly returned all 5 real course names with `course_view: ORIGINAL`.

| DATA | Selector strategy | Fallback | Evidence |
|---|---|---|---|
| Card container | `article[data-course-id]` → `article.course-element-card` → `[data-testid*="course-list-item" i]` → `[data-testid*="course-card" i]` → `[role="article"]` → `[role="listitem"]` | If none match, skip cards entirely and scan the whole page for course links directly (Original Experience's flatter markup) | **CONFIRMED (real run).** |
| Course id | `article`'s `data-course-id` attribute | `course_id_from_href()` on the link's URL — only if the href is a real URL, see below | **CONFIRMED (real run)** — Blackboard puts its own internal id directly on the card (e.g. `_424872_1`), no URL parsing needed. |
| Course link href | — | If the href isn't a real URL (see next row), the URL is reconstructed as `{base_url}/ultra/courses/{course_id}/outline` from the confirmed course id instead | **CONFIRMED (real run): real UDEM cards use `href="javascript:void(0);"`** — a JS click handler, not a link. Course URLs are never read from this href; they're always reconstructed from `data-course-id`. |
| Course name | `h4.js-course-title-element` text, inside the course-title link | Link's own text, then its `aria-label`, then the course id | **CONFIRMED (real run)** — returned real names like "AD-1321-19 Gestión de negocios" correctly. |
| Course view | `.course-title .course-type` text, checked against `"original/ultra course view"` | `.course-type` anywhere in the card, then a whole-card text scan, then `UNKNOWN` | **CONFIRMED (real run)** — `.course-type` really does read "Original Course View"; all 5 of the user's courses came back correctly as `ORIGINAL`. |
| Instructor | `[class*="course_username"]` text | Line-based label scan for `/instructor/i` | **CONFIRMED ABSENT from the collapsed card (real run).** A real card's full text was exactly `<code> \| <name> \| Original Course View \| Open \| More info` — no instructor anywhere, and no element with `course_username` (or anything else instructor-shaped) in its class exists on the page. `instructor: None` is the correct, accurate result for this view — not a parser miss. |
| Term | — | Always `None` | Not attempted — no evidence a term/semester label exists on the card; left unset rather than guessed. |

### Resolved: instructor isn't available without an extra click

The earlier `course_username` selector was based on a description that
turned out not to match the collapsed card — likely from inspecting the
"More info" panel already expanded. Confirmed via a real run's full card
text (see above): the instructor name simply isn't in the DOM at all until
that toggle is clicked.

That makes filling it in a genuine scope decision, not a bug fix: it would
mean clicking "More info" once per course (still read-only, but more
browser interaction than today) to reveal it, and there's no confirmation
yet that the expanded panel even contains the instructor's name either.
Not implemented — `instructor` stays `None` for now, which is the accurate
result for the collapsed view. If it turns out to matter for a later
phase, this is the one place to revisit.

## Assignments — Original Course View (`parsers/original_course.py`)

Parser selectors themselves are unchanged from Phase 2, still validated
against synthetic fixtures only. But a real bug in how we even reach the
content was found and fixed against real UDEM:

**The iframe finding.** `get_assignments()` came back with "no assignment
items matched any known selector" against a real ORIGINAL course. Turned
out the Ultra outline page (`course.url`, e.g.
`.../ultra/courses/_424872_1/outline`) doesn't contain the course content
at all — it embeds it in `<iframe src="…/webapps/blackboard/execute/
courseMain?course_id=…">`. Playwright's `page.content()` only sees the
top-level document; a same-origin iframe's own document is invisible to
it without explicitly switching into that frame.

**CONFIRMED fix**: `PlaywrightBlackboardProvider._resolve_content_entry_url()`
now navigates ORIGINAL-view courses straight to
`{base_url}/webapps/blackboard/execute/courseMain?course_id={id}` instead
of the Ultra outline page, bypassing the iframe entirely rather than
trying to reach into it. That URL pattern itself is confirmed real (it's
the literal iframe `src` from a real page dump); what's NOT yet confirmed
is what `courseMain` itself contains — whether it's a direct content
listing OriginalCourseParser's existing selectors can already handle, or
Original Experience's own frameset (course menu frame + content frame,
classic Blackboard UI) needing one more level of navigation.

Next step to confirm: run `blackboard debug-dump-course-html <id>` again
now that it targets `courseMain` directly, and share what
`OriginalCourseParser`'s selectors find (or don't) against the real
result.

## Assignments — Ultra Course View (`parsers/ultra_course.py`)

Not attempted. `UltraCourseParser` is a stub that returns `[]` with a
warning — see its module docstring. Zero evidence was available about
Ultra Course View's content-page DOM.

## Login / session detection (`providers/playwright_provider.py`)

Learned the hard way against real UDEM Blackboard: the first version tried
to detect "logged in" *positively*, by looking for a guessed username
element (`USERNAME_SELECTORS`). Against your real page none of those
selectors matched, and the code treated that as a failed login — even
though you had genuinely logged in and confirmed it. That was a design
bug, not just a wrong selector.

Fixed by flipping the check to a *negative*, skin-agnostic signal instead:
`_looks_like_login_page()` looks for a visible `input[type="password"]`,
or a URL matching common login/SSO patterns (Okta, Azure AD, Shibboleth,
`/login`, `/sso`). A password field is a near-universal marker of "you're
looking at a login form," true across institutions and SSO providers,
unlike any specific "you're logged in" markup. `USERNAME_SELECTORS` is
still there but now purely cosmetic (the "Logged in as: ..." message) —
it never blocks saving a session or gates `courses`/`assignments` anymore.

| DATA | Selector strategy | Fallback | Evidence |
|---|---|---|---|
| "Are we logged out" | `input[type="password"]` present, or URL matches `LOGIN_PAGE_URL_HINTS` | Assume logged in if neither matches | Verified in principle (password fields are how login forms work), not against your specific page |
| Display name (cosmetic) | `USERNAME_SELECTORS` fallback chain | `None` — never blocks anything | Unverified, same caveat as the course card selectors above |

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
