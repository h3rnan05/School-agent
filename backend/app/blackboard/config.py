"""Configuration for the Blackboard module.

Nothing here is hardcoded to a specific institution: base URL, timezone and
storage locations are read from the environment so the same code works for
any Blackboard instance. No credentials live in this module or anywhere
else in the codebase — see auth.py for why.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BlackboardSettings:
    base_url: str
    timezone: str
    state_dir: Path
    login_timeout_seconds: int
    request_timeout_ms: int
    max_retries: int
    headless_for_non_login: bool

    @property
    def storage_state_path(self) -> Path:
        return self.state_dir / "blackboard_storage_state.enc"

    @property
    def encryption_key_path(self) -> Path:
        return self.state_dir / "keys" / "blackboard_session.key"

    @property
    def debug_screenshots_dir(self) -> Path:
        return self.state_dir / "debug_screenshots"

    @property
    def snapshot_cache_path(self) -> Path:
        return self.state_dir / "cache" / "assignments_snapshot.json"


def load_settings() -> BlackboardSettings:
    base_url = os.environ.get("BLACKBOARD_BASE_URL")
    if not base_url:
        raise RuntimeError(
            "BLACKBOARD_BASE_URL is not set. Export it before running any "
            "blackboard command, e.g. "
            "export BLACKBOARD_BASE_URL=https://your-institution.blackboard.com"
        )

    state_dir = Path(os.environ.get("SCHOOL_AGENT_STATE_DIR", str(Path.home() / ".school-agent")))

    return BlackboardSettings(
        base_url=base_url.rstrip("/"),
        timezone=os.environ.get("BLACKBOARD_TIMEZONE", "UTC"),
        state_dir=state_dir,
        login_timeout_seconds=int(os.environ.get("BLACKBOARD_LOGIN_TIMEOUT_SECONDS", "600")),
        request_timeout_ms=int(os.environ.get("BLACKBOARD_REQUEST_TIMEOUT_MS", "30000")),
        max_retries=int(os.environ.get("BLACKBOARD_MAX_RETRIES", "3")),
        headless_for_non_login=os.environ.get("BLACKBOARD_HEADLESS", "true").lower() != "false",
    )
