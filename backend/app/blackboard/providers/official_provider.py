"""Stub for a future official Blackboard/Anthology REST API integration.

Intentionally unimplemented. Per ARCHITECTURE.md section 8, this only gets
built if we confirm the user's institution actually exposes a REST API
accessible to their account (institutional developer-portal client
credentials) — see the open questions in ARCHITECTURE.md section 16. No
endpoints are invented here in the meantime.
"""
from __future__ import annotations

from app.blackboard.config import BlackboardSettings
from app.blackboard.dto import Assignment, Course, UpcomingAssignments
from app.blackboard.exceptions import ProviderNotImplementedError
from app.blackboard.provider import BlackboardProvider, ProviderHealth, SessionHandle

_NOT_IMPLEMENTED = (
    "OfficialBlackboardProvider is not implemented. It will only be built "
    "once institutional REST API access is confirmed (see ARCHITECTURE.md "
    "section 16). Use PlaywrightBlackboardProvider for now."
)


class OfficialBlackboardProvider(BlackboardProvider):
    def __init__(self, settings: BlackboardSettings):
        self._settings = settings

    def login(self) -> SessionHandle:
        raise ProviderNotImplementedError(_NOT_IMPLEMENTED)

    def is_session_valid(self) -> bool:
        raise ProviderNotImplementedError(_NOT_IMPLEMENTED)

    def get_current_user(self) -> str | None:
        raise ProviderNotImplementedError(_NOT_IMPLEMENTED)

    def get_courses(self) -> list[Course]:
        raise ProviderNotImplementedError(_NOT_IMPLEMENTED)

    def get_assignments(self, course_id: str) -> list[Assignment]:
        raise ProviderNotImplementedError(_NOT_IMPLEMENTED)

    def get_upcoming_assignments(
        self,
        days: int = 7,
        include_overdue: bool = False,
        include_no_due_date: bool = False,
    ) -> UpcomingAssignments:
        raise ProviderNotImplementedError(_NOT_IMPLEMENTED)

    def health_check(self) -> ProviderHealth:
        raise ProviderNotImplementedError(_NOT_IMPLEMENTED)
