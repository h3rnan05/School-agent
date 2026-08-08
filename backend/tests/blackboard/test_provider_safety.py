"""Demonstrates, in code, that the Blackboard module cannot submit, edit,
delete, or modify anything on Blackboard — not just that it's documented
as read-only.
"""
import inspect

from app.blackboard.provider import BlackboardProvider
from app.blackboard.providers.official_provider import OfficialBlackboardProvider
from app.blackboard.providers.playwright_provider import PlaywrightBlackboardProvider

FORBIDDEN_SUBSTRINGS = (
    "submit",
    "edit",
    "modify",
    "delete",
    "update",
    "write",
    "upload",
    "post",
    "grade",
    "remove",
)

# `update` legitimately shows up in words like `updated_at` if we ever add
# one; none of our current public methods do, so an exact-word check on
# method names (not substrings of unrelated words) is enough here.


def _public_method_names(cls) -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(cls, predicate=inspect.isfunction)
        if not name.startswith("_")
    }


def test_interface_exposes_no_write_operations():
    names = _public_method_names(BlackboardProvider)
    for name in names:
        lowered = name.lower()
        for forbidden in FORBIDDEN_SUBSTRINGS:
            assert forbidden not in lowered, f"BlackboardProvider.{name} looks like a write operation"


def test_playwright_provider_exposes_no_extra_write_operations():
    interface_names = _public_method_names(BlackboardProvider)
    concrete_names = _public_method_names(PlaywrightBlackboardProvider)
    extra_public_methods = concrete_names - interface_names
    for name in extra_public_methods:
        lowered = name.lower()
        for forbidden in FORBIDDEN_SUBSTRINGS:
            assert forbidden not in lowered, (
                f"PlaywrightBlackboardProvider.{name} is a public method not on the "
                f"interface and looks like a write operation"
            )


def test_official_provider_exposes_no_extra_write_operations():
    interface_names = _public_method_names(BlackboardProvider)
    concrete_names = _public_method_names(OfficialBlackboardProvider)
    extra_public_methods = concrete_names - interface_names
    assert extra_public_methods == set()


def test_provider_is_missing_any_submission_method_entirely():
    all_names = _public_method_names(BlackboardProvider) | _public_method_names(
        PlaywrightBlackboardProvider
    )
    assert "submit_assignment" not in all_names
    assert "modify_assignment" not in all_names
    assert "delete_assignment" not in all_names
    assert "edit_grade" not in all_names
