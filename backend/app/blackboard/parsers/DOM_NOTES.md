# DOM evidence notes (Phase 2.1)

Per Step 9: for every important piece of data, this documents the selector
strategy and fallback used, and — critically — **whether it's based on
real evidence or is still an unverified best guess.**

**Update — CONFIRMED against real markup.** You shared the actual DOM
structure from DevTools against `cursos-udem.blackboard.com` (redacted of
personal data). The selectors below were rewritten from that evidence; the
table marks exactly what's confirmed vs still an assumption.

## Course list (`parsers/course_list.py`)

| DATA | Selector strategy | Fallback | Evidence |
|---|---|---|---|
| Card container | `article[data-course-id]` → `article.course-element-card` → `[data-testid*="course-list-item" i]` → `[data-testid*="course-card" i]` → `[role="article"]` → `[role="listitem"]` | If none match, skip cards entirely and scan the whole page for course links directly (Original Experience's flatter markup) | **CONFIRMED** — you shared this exact structure: `<article data-course-id="..." class="element-card course-element-card ...">`. |
| Course id | `article`'s `data-course-id` attribute | `course_id_from_href()` on the link's URL, then the absolute URL itself | **CONFIRMED** — Blackboard puts its own internal id directly on the card, no URL parsing needed. |
| Course link | `a.course-title[href]` within the card | `a[href*="/ultra/courses/"]` → `a[href*="course_id="]` | **CONFIRMED** the class name and that it's an `<a>` with `href`. The exact href *value* pattern (`/ultra/courses/_XXXXX_1/outline` vs something else) is still unconfirmed — you weren't sure when asked, see below. |
| Course name | `h4.js-course-title-element` text, inside the course-title link | Link's own text, then its `aria-label`, then the course id | **CONFIRMED** — `<h4 class="js-course-title-element ellipsis">` sits inside `a.course-title`. |
| Course view | `.course-title .course-type` text, checked against `"original/ultra course view"` | `.course-type` anywhere in the card, then a whole-card text scan, then `UNKNOWN` | **Structure confirmed** (`<span class="course-type">` exists right next to the title), **exact text NOT confirmed** — you weren't able to check what it actually says. Currently assumed to read "Original Course View" / "Ultra Course View" like the rest of Blackboard's UI; if it says something else, this needs a one-line fix. |
| Instructor | `[class*="course_username"]` text | Line-based label scan for `/instructor/i` | **CONFIRMED** — `<span class="course_username course_user_...">` (the suffix is per-user/opaque, hence the wildcard match). |
| Term | — | Always `None` | Not attempted — no evidence a term/semester label exists on the card; left unset rather than guessed. |

### Still unconfirmed — quick way to check without DevTools

The dumped page is the live DOM serialized by the browser, not
nicely-formatted source, so plain `grep` on it is unreliable — use the
`bs4` parser that's already installed instead. From `backend/`, with the
venv active:

```bash
python3 -c "
from bs4 import BeautifulSoup
html = open('$HOME/.school-agent/debug_html/courses_page.html', encoding='utf-8').read()
soup = BeautifulSoup(html, 'html.parser')
print('course-type text:', [el.get_text(strip=True) for el in soup.select('.course-type')][:5])
print('course-title hrefs:', [a.get('href') for a in soup.select('a.course-title')][:5])
"
```

Paste the output (URLs/IDs are fine to share — no login/session data lives
in this file) to turn the last two "unconfirmed" rows above into confirmed
ones.

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
