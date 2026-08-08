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
| Instructor | `[class*="course_username"]` text | Line-based label scan for `/instructor/i` | **NOT working against the real page** — came back `(not found)` for all 5 courses in a real run, despite the class existing per the user's own DevTools inspection. Open question — see below. |
| Term | — | Always `None` | Not attempted — no evidence a term/semester label exists on the card; left unset rather than guessed. |

### Open question: why is the instructor selector missing?

Three live hypotheses, in order of likelihood:

1. The `course_username` span is empty/absent in the *collapsed* card view
   and only gets populated when the "More info" toggle is clicked (would
   explain why it "exists" on inspection but the parser finds nothing —
   DevTools inspection may have happened after clicking it).
2. The real class name differs slightly from what was described (e.g. a
   different word order/casing than `course_username`).
3. The instructor field is simply blank for these particular courses in
   Blackboard itself (some institutions don't populate it on every course).

To tell which one it is, from `backend/` with the venv active:

```bash
python -m app.blackboard debug-dump-courses-html
python3 -c "
from bs4 import BeautifulSoup
html = open('$HOME/.school-agent/debug_html/courses_page.html', encoding='utf-8').read()
soup = BeautifulSoup(html, 'html.parser')
card = soup.select_one('article[data-course-id]')
print('any element with course_username in its class:',
      [(el.name, el.get('class')) for el in card.find_all(class_=lambda c: c and 'course_username' in ' '.join(c).lower())])
print('full card text:', card.get_text(' | ', strip=True))
"
```

Paste the output (instructor names in it are fine to share — they're the
same info Blackboard already shows you). If hypothesis 1 is right
(instructor is genuinely absent until "More info" is clicked), the fix is
either accepting `instructor: None` as correct for the collapsed view, or
adding a deliberate, disclosed click on that toggle before parsing — worth
deciding explicitly rather than silently, since Phase 2 was built to
minimize unnecessary page interactions.

## Assignments — Original Course View (`parsers/original_course.py`)

Unchanged from Phase 2. Validated against synthetic fixtures only, never
against a real Original Course View course content page. See
`backend/README.md`'s "honest note on the parser" section.

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
