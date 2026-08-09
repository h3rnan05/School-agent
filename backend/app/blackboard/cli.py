"""Development CLI for the Blackboard module.

    blackboard login        open a visible browser to log in manually
    blackboard courses      list detected courses
    blackboard assignments  list assignments for one course
    blackboard upcoming     list assignments due in the next N days

Nothing here touches PostgreSQL, Google Calendar, Claude, Telegram, or the
frontend — this CLI only exercises the Blackboard module in isolation, on
purpose (Phase 2 scope). See backend/README.md for setup and usage.
"""
from __future__ import annotations

import hashlib
import logging
import sys

import click

from app.blackboard.changes import diff_assignments
from app.blackboard.config import load_settings
from app.blackboard.dto import Assignment, Course
from app.blackboard.exceptions import BlackboardError
from app.blackboard.factory import get_provider
from app.blackboard.formatting import format_due_date_parts, format_points
from app.blackboard.snapshot_store import SnapshotStore


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@click.group()
@click.option("--verbose", is_flag=True, help="Enable debug logging.")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """Student Academic Assistant — Blackboard module CLI (Phase 2)."""
    _configure_logging(verbose)
    ctx.ensure_object(dict)


@cli.command()
def login() -> None:
    """Open a visible browser window to log in to Blackboard manually."""
    settings = load_settings()
    provider = get_provider(settings)
    try:
        session = provider.login()
    except BlackboardError as exc:
        click.echo(f"Login failed: {exc}", err=True)
        sys.exit(1)

    if session.username:
        click.echo(f"Logged in as: {session.username}")
    else:
        click.echo("Logged in. (Couldn't detect your display name — cosmetic only, doesn't affect anything.)")
    click.echo("Session saved (encrypted) for future commands.")


@cli.command()
def courses() -> None:
    """List courses detected on your Blackboard account."""
    settings = load_settings()
    provider = get_provider(settings)
    try:
        found = provider.get_courses()
    except BlackboardError as exc:
        click.echo(f"Could not list courses: {exc}", err=True)
        sys.exit(1)

    if not found:
        click.echo("No courses found. This almost certainly means the parser needs updating")
        click.echo("for your Blackboard's real markup — run this to help fix it:")
        click.echo("")
        click.echo("    python -m app.blackboard debug-dump-courses-html")
        click.echo("")
        click.echo("It saves the real page HTML to a local file (no login/session data in it)")
        click.echo("that can be shared to build correct selectors instead of guesses.")
        return

    click.echo("COURSES FOUND\n")
    for course in found:
        click.echo(f"course_id:   {course.id}")
        click.echo(f"course_name: {course.name}")
        click.echo(f"course_url:  {course.url}")
        click.echo(f"course_view: {course.course_view.value}")
        click.echo(f"instructor:  {course.instructor or '(not found)'}")
        click.echo("")

    unknown_views = [c for c in found if c.course_view.value == "UNKNOWN"]
    if unknown_views:
        click.echo(
            f"Note: course_view could not be determined for {len(unknown_views)} course(s) "
            "(shown as UNKNOWN above) — the parser didn't find an 'Original/Ultra Course View' "
            "label on the card. See backend/README.md if you can share the real markup."
        )


@cli.command(name="debug-dump-courses-html")
def debug_dump_courses_html() -> None:
    """Save the raw HTML of your Blackboard course list page to a local file.

    Uses your already-saved session (run `login` first if you haven't).
    Read-only, no new browser interaction needed. The saved file contains
    the same page content you'd see yourself in the browser — never any
    login, cookie, or session data.
    """
    settings = load_settings()
    provider = get_provider(settings)
    dump = getattr(provider, "dump_courses_html", None)
    if dump is None:
        click.echo(
            "This command is only available with the Playwright provider "
            "(current BLACKBOARD_PROVIDER_IMPL doesn't support it).",
            err=True,
        )
        sys.exit(1)

    try:
        path = dump(settings.debug_html_dir / "courses_page.html")
    except BlackboardError as exc:
        click.echo(f"Could not dump the course list page: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Saved the course list page's HTML to:\n{path}\n")
    click.echo("Open it and copy the chunk around one of your course cards (course name")
    click.echo("or instructor text is fine to include — there's no login/session data in")
    click.echo("this file) so real selectors can replace the guessed ones.")


@cli.command(name="debug-dump-url")
@click.argument("url")
def debug_dump_url(url: str) -> None:
    """Save the raw HTML of any Blackboard URL (same institution only) to
    a local file — e.g. a specific assignment's page, to check for a due
    date not visible in the content list. Uses your already-saved session.
    Read-only: just navigates and reads, submits nothing.
    """
    settings = load_settings()
    provider = get_provider(settings)
    dump = getattr(provider, "dump_url_html", None)
    if dump is None:
        click.echo(
            "This command is only available with the Playwright provider "
            "(current BLACKBOARD_PROVIDER_IMPL doesn't support it).",
            err=True,
        )
        sys.exit(1)

    slug = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    try:
        path = dump(url, settings.debug_html_dir / f"url_{slug}.html")
    except (BlackboardError, ValueError) as exc:
        click.echo(f"Could not dump that URL: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Saved to:\n{path}\n")
    click.echo("Open it and share the chunk around the due date / relevant field so real")
    click.echo("selectors can be built from it — no login/session data is in this file.")


@cli.command(name="debug-dump-course-html")
@click.argument("course_id")
@click.option(
    "--follow",
    "follow_link_text",
    default=None,
    help='Also follow one more link whose text contains this (e.g. --follow "Assessments") '
    "to inspect a specific content area one level deeper.",
)
def debug_dump_course_html(course_id: str, follow_link_text: str | None) -> None:
    """Save the raw HTML of a single course's content page to a local file.

    Uses your already-saved session. Read-only. Prints which URL it
    actually landed on (Blackboard sometimes redirects), which matters
    because `assignments` returning nothing usually means the parser is
    looking at the wrong page, not that there's nothing there.
    """
    settings = load_settings()
    provider = get_provider(settings)
    dump = getattr(provider, "dump_course_html", None)
    if dump is None:
        click.echo(
            "This command is only available with the Playwright provider "
            "(current BLACKBOARD_PROVIDER_IMPL doesn't support it).",
            err=True,
        )
        sys.exit(1)

    try:
        result = dump(course_id, settings.debug_html_dir / f"course_{course_id}.html", follow_link_text)
    except BlackboardError as exc:
        click.echo(f"Could not dump the course page: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Saved the course page's HTML to:\n{result.html_path}\n")
    click.echo(f"course.url (from the course list):  {result.course_url}")
    click.echo(f"page URL right after navigating there: {result.url_before_content_link}")
    if result.content_link_followed:
        click.echo(f"Followed a link matching 'assignments/content/coursework': {result.content_link_followed}")
    else:
        click.echo("No link matching 'assignments/content/coursework' was found on that page.")
    if result.follow_link_text_requested:
        if result.follow_link_result:
            click.echo(f"Followed --follow {result.follow_link_text_requested!r}: {result.follow_link_result}")
        else:
            click.echo(f"--follow {result.follow_link_text_requested!r}: no matching link found on that page.")
    click.echo(f"final page URL (what the saved HTML is from): {result.final_url}\n")
    click.echo("If the final URL doesn't look like a content/assignments listing, that's the")
    click.echo("real problem — share these URLs (with the numeric course id is fine) and a")
    click.echo("chunk of the saved HTML around one visible assignment/item.")


@cli.command()
@click.argument("course_id")
def assignments(course_id: str) -> None:
    """List assignments for a single course (see `blackboard courses` for ids)."""
    settings = load_settings()
    provider = get_provider(settings)
    try:
        # Fetched first so the provider's course cache is warm before
        # get_assignments() resolves course_id -> Course internally, and so
        # we have course.name/course_view available for display below.
        course_map = {c.id: c for c in provider.get_courses()}
        found = provider.get_assignments(course_id)
    except BlackboardError as exc:
        click.echo(f"Could not list assignments: {exc}", err=True)
        sys.exit(1)

    _report_changes(settings, found)
    _print_assignments(found, course_map)


@cli.command()
@click.option("--days", default=7, show_default=True, help="Window size in days.")
@click.option("--include-overdue", is_flag=True, help="Also list overdue assignments, separately.")
@click.option("--include-no-due-date", is_flag=True, help="Also list assignments with no due date, separately.")
def upcoming(days: int, include_overdue: bool, include_no_due_date: bool) -> None:
    """List assignments due in the next N days across all courses."""
    settings = load_settings()
    provider = get_provider(settings)
    try:
        course_map = {c.id: c for c in provider.get_courses()}
        result = provider.get_upcoming_assignments(
            days=days,
            include_overdue=include_overdue,
            include_no_due_date=include_no_due_date,
        )
    except BlackboardError as exc:
        click.echo(f"Could not list upcoming assignments: {exc}", err=True)
        sys.exit(1)

    all_found = list(result.upcoming) + list(result.overdue) + list(result.no_due_date)
    _report_changes(settings, all_found)

    click.echo(f"UPCOMING (next {days} days)\n")
    _print_assignments(result.upcoming, course_map)

    if include_overdue:
        click.echo("\nOVERDUE\n")
        _print_assignments(result.overdue, course_map)

    if include_no_due_date:
        click.echo("\nNO DUE DATE\n")
        _print_assignments(result.no_due_date, course_map)


def _print_assignments(
    found: tuple[Assignment, ...] | list[Assignment],
    course_map: dict[str, Course],
) -> None:
    if not found:
        click.echo("(none)")
        return
    for assignment in found:
        course = course_map.get(assignment.course_id)
        due_date, time_ = format_due_date_parts(assignment)
        click.echo(f"COURSE: {course.name if course else assignment.course_id}")
        click.echo(f"ASSIGNMENT: {assignment.title}")
        click.echo(f"DUE DATE: {due_date}")
        click.echo(f"TIME: {time_}")
        # This is the timezone the due date was INTERPRETED with, not
        # necessarily one Blackboard displayed explicitly — see
        # parsers/common.py's parse_due_date and backend/README.md.
        click.echo(f"TIMEZONE: {assignment.timezone}")
        click.echo(f"POINTS: {format_points(assignment)}")
        click.echo(f"URL: {assignment.url}")
        click.echo(f"COURSE VIEW: {course.course_view.value if course else 'UNKNOWN'}")
        click.echo(f"STATUS: {assignment.timing_status.value}")
        click.echo("")


def _report_changes(settings, found: list[Assignment]) -> None:
    """Compares against the local snapshot cache and prints any changes,
    then updates the cache. Purely local, file-based — no database yet
    (Phase 2 scope, see ARCHITECTURE.md section 18)."""
    store = SnapshotStore(settings.snapshot_cache_path)
    previous = store.load()

    for assignment in found:
        old = previous.get(assignment.id)
        if old is None:
            continue
        changes = diff_assignments(old, assignment)
        for change in changes:
            if change.field == "due_date":
                click.echo(
                    f"[CHANGED] {assignment.title}: due date {change.old_value} -> {change.new_value}"
                )
            else:
                click.echo(
                    f"[CHANGED] {assignment.title}: {change.field} changed"
                )

    updated = dict(previous)
    updated.update({a.id: a for a in found})
    store.save(updated)


if __name__ == "__main__":
    cli()
