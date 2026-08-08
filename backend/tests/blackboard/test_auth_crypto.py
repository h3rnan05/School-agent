import json

import pytest

from app.blackboard.auth import SessionStore
from app.blackboard.config import BlackboardSettings
from app.blackboard.exceptions import NoSessionError


def make_settings(tmp_path) -> BlackboardSettings:
    return BlackboardSettings(
        base_url="https://university.blackboard.com",
        timezone="UTC",
        state_dir=tmp_path,
        login_timeout_seconds=60,
        request_timeout_ms=5000,
        max_retries=1,
        headless_for_non_login=True,
    )


def test_session_round_trips_through_encryption(tmp_path):
    settings = make_settings(tmp_path)
    store = SessionStore(settings)

    plaintext_path = tmp_path / "plain_storage_state.json"
    plaintext_path.write_text(json.dumps({"cookies": [{"name": "session", "value": "abc123"}]}))

    store.save_plaintext_state(plaintext_path)

    assert store.exists()
    assert not plaintext_path.exists()  # plaintext copy must not linger on disk

    # the encrypted file on disk must not contain the raw cookie value
    encrypted_bytes = settings.storage_state_path.read_bytes()
    assert b"abc123" not in encrypted_bytes

    decrypted_path = tmp_path / "decrypted.json"
    store.decrypt_to(decrypted_path)
    data = json.loads(decrypted_path.read_text())
    assert data["cookies"][0]["value"] == "abc123"


def test_missing_session_raises_no_session_error(tmp_path):
    settings = make_settings(tmp_path)
    store = SessionStore(settings)
    with pytest.raises(NoSessionError):
        store.decrypt_to(tmp_path / "out.json")


def test_encryption_key_file_has_owner_only_permissions(tmp_path):
    settings = make_settings(tmp_path)
    SessionStore(settings)  # generates the key as a side effect
    mode = settings.encryption_key_path.stat().st_mode & 0o777
    assert mode == 0o600
