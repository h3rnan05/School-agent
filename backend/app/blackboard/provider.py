"""The BlackboardProvider interface — the only thing the rest of the
system is allowed to depend on. It must never gain a write method.

Per ARCHITECTURE.md section 8/12: PlaywrightBlackboardProvider is the only
real implementation today. OfficialBlackboardProvider is a stub for a
future institutional API and stays unimplemented until that access is
actually confirmed — nothing here assumes it exists.

READ-ONLY GUARANTEE: this ABC intentionally exposes no method whose name
contains submit / edit / modify / delete / update / write / upload / post
/ grade. tests/blackboard/test_provider_safety.py asserts this holds for
every concrete subclass, not just this file.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from app.blackboard.dto import Assignment, Course, UpcomingAssignments


@dataclass(frozen=True)
class SessionHandle:
    authenticated: bool
    username: str | None
    created_at: datetime


@dataclass(frozen=True)
class ProviderHealth:
    ok: bool
    message: str
    checked_at: datetime


class BlackboardProvider(ABC):
    """Read-only access to a Blackboard instance.

    Implementations must never perform any action that changes state on
    Blackboard: no submissions, no grade edits, no settings changes, no
    posts. If a future feature needs to write to Blackboard, it belongs in
    a completely separate, explicitly-approved module — not here.
    """

    # -- session -----------------------------------------------------
    @abstractmethod
    def login(self) -> SessionHandle:
        """Establish a session, pausing for manual SSO/MFA if needed.

        Never accepts or stores a password. See auth.py for the exact
        mechanism.
        """

    @abstractmethod
    def is_session_valid(self) -> bool:
        """Cheap check for whether the persisted session still works."""

    @abstractmethod
    def get_current_user(self) -> str | None:
        """Returns the authenticated username, or None if not logged in."""

    # -- read-only data ------------------------------------------------
    @abstractmethod
    def get_courses(self) -> list[Course]:
        ...

    @abstractmethod
    def get_assignments(self, course_id: str) -> list[Assignment]:
        ...

    @abstractmethod
    def get_upcoming_assignments(
        self,
        days: int = 7,
        include_overdue: bool = False,
        include_no_due_date: bool = False,
    ) -> UpcomingAssignments:
        ...

    @abstractmethod
    def health_check(self) -> ProviderHealth:
        ...
