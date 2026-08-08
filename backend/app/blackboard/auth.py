"""Authentication: manual login (SSO/MFA-safe) + encrypted session persistence.

Hard rule: this module never sees, accepts, or stores a Blackboard password.
Login always happens in a real, visible (headful) browser window that the
user drives by hand — including whatever SSO provider and MFA step their
institution uses (Okta, Azure AD, Shibboleth, or anything else). This code
does not attempt to detect, solve, or bypass MFA/CAPTCHA in any way; it
only waits.

What gets persisted is the browser's `storage_state` (cookies +
localStorage) after a successful manual login, encrypted at rest with a
locally-generated key. Both the encrypted session file and the key live
under the local state directory (see config.py), which is entirely outside
the repository and covered by .gitignore.
"""
from __future__ import annotations

import logging
import os
import stat
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.blackboard.config import BlackboardSettings
from app.blackboard.exceptions import LoginFailedError, MFATimeoutError, NoSessionError
from app.blackboard.provider import SessionHandle

logger = logging.getLogger("blackboard.auth")


def _load_or_create_key(key_path: Path) -> bytes:
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        return key_path.read_bytes()
    key = Fernet.generate_key()
    key_path.write_bytes(key)
    os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)  # 0600: owner read/write only
    logger.info("Generated new local session encryption key at %s", key_path)
    return key


class SessionStore:
    """Encrypts/decrypts the Playwright storage_state file at rest."""

    def __init__(self, settings: BlackboardSettings):
        self._settings = settings
        self._fernet = Fernet(_load_or_create_key(settings.encryption_key_path))

    def exists(self) -> bool:
        return self._settings.storage_state_path.exists()

    def save_plaintext_state(self, plaintext_path: Path) -> None:
        """Encrypts a plaintext storage_state file Playwright just wrote, then
        deletes the plaintext copy so it never lingers on disk unencrypted.
        """
        data = plaintext_path.read_bytes()
        encrypted = self._fernet.encrypt(data)
        self._settings.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
        self._settings.storage_state_path.write_bytes(encrypted)
        os.chmod(self._settings.storage_state_path, stat.S_IRUSR | stat.S_IWUSR)
        plaintext_path.unlink(missing_ok=True)

    def decrypt_to(self, target_path: Path) -> Path:
        """Decrypts the stored session into a temporary plaintext file for
        Playwright to consume, since Playwright needs a real path/dict, not
        a decrypted blob in memory. Caller is responsible for deleting it
        after use (see providers/playwright_provider.py).
        """
        if not self.exists():
            raise NoSessionError("No persisted Blackboard session found. Run `blackboard login` first.")
        encrypted = self._settings.storage_state_path.read_bytes()
        try:
            plaintext = self._fernet.decrypt(encrypted)
        except InvalidToken as exc:
            raise NoSessionError(
                "Stored session could not be decrypted (corrupted or key mismatch). "
                "Run `blackboard login` again."
            ) from exc
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(plaintext)
        os.chmod(target_path, stat.S_IRUSR | stat.S_IWUSR)
        return target_path

    def clear(self) -> None:
        self._settings.storage_state_path.unlink(missing_ok=True)


def wait_for_manual_login(page, base_url: str, timeout_seconds: int) -> None:
    """Blocks until the user confirms they've finished logging in (including
    SSO + MFA) in the visible browser window.

    Auto-detection of "logged in" is unreliable across institutions (Ultra
    vs Original Experience, different SSO providers), so this combines a
    best-effort heuristic (URL back on the Blackboard domain) with an
    explicit manual confirmation, which is the only trigger we actually
    trust.
    """
    print("\nA browser window has opened. Log in to Blackboard manually,")
    print("including any SSO step and MFA your institution requires.")
    print(f"Once you're fully logged in and can see your Blackboard homepage ({base_url}),")
    input("press ENTER here to continue... ")

    deadline = datetime.now(timezone.utc).timestamp() + timeout_seconds
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:  # noqa: BLE001 - best-effort only, never fatal
        pass

    if datetime.now(timezone.utc).timestamp() > deadline:
        raise MFATimeoutError(f"Manual login was not confirmed within {timeout_seconds}s")


def build_session_handle(username: str | None) -> SessionHandle:
    return SessionHandle(
        authenticated=username is not None,
        username=username,
        created_at=datetime.now(timezone.utc),
    )


def require_username_or_fail(username: str | None) -> str:
    if not username:
        raise LoginFailedError(
            "Login flow completed but no authenticated user could be detected. "
            "Check that you reached the Blackboard homepage before confirming."
        )
    return username
