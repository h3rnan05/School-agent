"""Thin wrapper around Playwright: context lifecycle, retries, timeouts,
and best-effort debug screenshots on failure. No parsing logic lives here —
see the parsers/ package.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from app.blackboard.config import BlackboardSettings
from app.blackboard.exceptions import BlackboardUnavailableError

logger = logging.getLogger("blackboard.browser")

T = TypeVar("T")


class ManagedBrowser:
    """Owns a single Playwright browser + context for the lifetime of a command.

    Usage:
        with ManagedBrowser(settings, headless=True, storage_state=path) as browser:
            page = browser.new_page()
            ...
    """

    def __init__(self, settings: BlackboardSettings, headless: bool, storage_state: Path | None = None):
        self._settings = settings
        self._headless = headless
        self._storage_state = storage_state
        # Typed as Any rather than playwright's own classes: this wrapper
        # deliberately doesn't commit to playwright's exact API surface
        # beyond the handful of read-only calls it makes below.
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None

    def __enter__(self) -> ManagedBrowser:
        # Imported lazily so importing this module doesn't require the
        # playwright package (and its browser binaries) unless actually used.
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self._headless)
        context_kwargs = {}
        if self._storage_state and self._storage_state.exists():
            context_kwargs["storage_state"] = str(self._storage_state)
        self._context = self._browser.new_context(**context_kwargs)
        self._context.set_default_timeout(self._settings.request_timeout_ms)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def new_page(self):
        assert self._context is not None, "ManagedBrowser must be used as a context manager"
        return self._context.new_page()

    def save_storage_state(self, path: Path) -> None:
        assert self._context is not None
        path.parent.mkdir(parents=True, exist_ok=True)
        self._context.storage_state(path=str(path))

    def screenshot_on_error(self, page, label: str) -> None:
        try:
            self._settings.debug_screenshots_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            target = self._settings.debug_screenshots_dir / f"{label}-{ts}.png"
            page.screenshot(path=str(target))
            logger.info("Saved debug screenshot to %s", target)
        except Exception:  # pragma: no cover - best effort only
            logger.exception("Failed to capture debug screenshot")


def with_retries(fn: Callable[[], T], max_retries: int, description: str) -> T:
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - deliberately broad, re-raised as domain error below
            last_error = exc
            logger.warning("%s failed (attempt %d/%d): %s", description, attempt, max_retries, exc)
            if attempt < max_retries:
                time.sleep(min(2**attempt, 10))
    raise BlackboardUnavailableError(f"{description} failed after {max_retries} attempts") from last_error
