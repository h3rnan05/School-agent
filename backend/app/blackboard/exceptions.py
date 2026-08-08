"""Error hierarchy for the Blackboard module.

Every failure mode from ARCHITECTURE.md section 13 has a distinct
exception so callers (CLI, future pipeline orchestrator) can react
correctly instead of guessing from a generic error string. None of these
are ever raised in place of inventing missing data — see dto.py for how
"we don't know" is represented instead of guessed.
"""
from __future__ import annotations


class BlackboardError(Exception):
    """Base class for all Blackboard-module errors."""


class BlackboardUnavailableError(BlackboardError):
    """Blackboard did not respond, or responded with a server error."""


class LoginFailedError(BlackboardError):
    """Interactive login did not result in an authenticated session."""


class SessionExpiredError(BlackboardError):
    """A previously valid session is no longer authenticated."""


class MFATimeoutError(BlackboardError):
    """The user did not complete manual MFA/SSO within the allowed time."""


class NoSessionError(BlackboardError):
    """An operation needs an authenticated session but none was found.

    Raised instead of silently trying to log in, so automated runs never
    block forever waiting for a human who isn't there.
    """


class CourseUnavailableError(BlackboardError):
    """A specific course could not be reached (deleted, no access, etc.)."""


class AssignmentNotFoundError(BlackboardError):
    """A specific assignment could not be located."""


class ParsingError(BlackboardError):
    """The parser could not make sense of a Blackboard page.

    Raised only when the page structure is unrecognizable as a whole
    (e.g. an error page). Missing individual fields on an otherwise valid
    page are represented with FieldStatus.DATA_UNAVAILABLE, not this.
    """


class ProviderNotImplementedError(BlackboardError):
    """Raised by provider implementations that are intentionally stubs."""
