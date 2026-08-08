"""Selects which BlackboardProvider implementation to use.

The rest of the application (CLI today, future ingestion/pipeline code)
only ever imports `get_provider` and the `BlackboardProvider` interface —
never a concrete provider class directly. Swapping Playwright for an
official API later is a one-line env var change here, nothing else.
"""
from __future__ import annotations

import os

from app.blackboard.config import BlackboardSettings
from app.blackboard.provider import BlackboardProvider


def get_provider(settings: BlackboardSettings) -> BlackboardProvider:
    impl = os.environ.get("BLACKBOARD_PROVIDER_IMPL", "playwright").lower()

    if impl == "playwright":
        from app.blackboard.providers.playwright_provider import PlaywrightBlackboardProvider

        return PlaywrightBlackboardProvider(settings)

    if impl == "official":
        from app.blackboard.providers.official_provider import OfficialBlackboardProvider

        return OfficialBlackboardProvider(settings)

    raise ValueError(f"Unknown BLACKBOARD_PROVIDER_IMPL={impl!r}; expected 'playwright' or 'official'")
