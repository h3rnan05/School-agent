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

import logging
import sys

import click

from app.blackboard.changes import diff_assignments
from app.blackboard.config import load_settings
from app.blackboard.dto import Assignment
from app.blackboard.exceptions import BlackboardError
from app.blackboard.factory import get_provider
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

    click.echo(f"Logged in as: {session.username}")
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
        click.echo("No courses found. This may mean the parser needs updating for your")
        click.echo("Blackboard skin — see ARCHITECTURE.md section 16 for what to share.")
        return

    click.echo("COURSES FOUND\n")
    for course in found:
        click.echo(f"course_id:   {course.id}")
        click.echo(f"course_name: {course.name}")
        click.echo(f"course_url:  {course.url}")
        click.echo("")


@cli.command()
@click.argument("course_id")
def assignments(course_id: str) -> None:
    """List assignments for a single course (see `blackboard courses` for ids)."""
    settings = load_settings()
    provider = get_provider(settings)
    try:
        found = provider.get_assignments(course_id)
    except BlackboardError as exc:
        click.echo(f"Could not list assignments: {exc}", err=True)
        sys.exit(1)

    _report_changes(settings, found)
    _print_assignments(found)


@cli.command()
@click.option("--days", default=7, show_default=True, help="Window size in days.")
@click.option("--include-overdue", is_flag=True, help="Also list overdue assignments, separately.")
@click.option("--include-no-due-date", is_flag=True, help="Also list assignments with no due date, separately.")
def upcoming(days: int, include_overdue: bool, include_no_due_date: bool) -> None:
    """List assignments due in the next N days across all courses."""
    settings = load_settings()
    provider = get_provider(settings)
    try:
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
    _print_assignments(result.upcoming)

    if include_overdue:
        click.echo("\nOVERDUE\n")
        _print_assignments(result.overdue)

    if include_no_due_date:
        click.echo("\nNO DUE DATE\n")
        _print_assignments(result.no_due_date)


def _format_due_date(assignment: Assignment) -> str:
    if assignment.due_date is not None:
        return assignment.due_date.strftime("%B %d, %Y %I:%M %p %Z")
    if assignment.due_date_status.value == "UNPARSEABLE":
        return "DATA_UNAVAILABLE"
    return "(no due date)"


def _print_assignments(found: tuple[Assignment, ...] | list[Assignment]) -> None:
    if not found:
        click.echo("(none)")
        return
    for assignment in found:
        due = _format_due_date(assignment)
        click.echo(f"COURSE: {assignment.course_id}")
        click.echo(f"ASSIGNMENT: {assignment.title}")
        click.echo(f"DUE: {due}")
        click.echo(f"URL: {assignment.url}")
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
