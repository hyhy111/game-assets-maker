"""Credential recovery through the public PyWebView bridge."""

import base64

import pytest
from cryptography.fernet import Fernet

from backend.core import credential_crypto
from backend.main import API


@pytest.fixture
def credential_api(tmp_path, monkeypatch):
    monkeypatch.setattr(credential_crypto.sys, "platform", "linux")
    monkeypatch.setenv("GAM_DATA_ROOT", str(tmp_path))
    crypto = credential_crypto.CredentialCrypto()
    monkeypatch.setattr(API, "_credential_crypto", staticmethod(lambda: crypto))
    return API.__new__(API)


def test_credential_bridge_round_trip_after_restart(credential_api, monkeypatch):
    plaintext = '{"email":"test@example.com","password":"synthetic-password"}'
    ciphertext = credential_api.encrypt_credential(plaintext)
    reloaded = credential_crypto.CredentialCrypto()
    monkeypatch.setattr(API, "_credential_crypto", staticmethod(lambda: reloaded))

    assert credential_api.decrypt_credential(ciphertext) == plaintext


def test_credential_bridge_rejects_another_key_without_replacing_keystore(credential_api, tmp_path):
    keystore = tmp_path / ".keystore"
    original_key = keystore.read_bytes()
    ciphertext = Fernet(Fernet.generate_key()).encrypt(b"synthetic credential").decode("ascii")

    assert credential_api.decrypt_credential(ciphertext) == ""
    assert keystore.read_bytes() == original_key
    assert credential_api.decrypt_credential(credential_api.encrypt_credential("new credential")) == "new credential"


def test_credential_bridge_rejects_tampered_signature(credential_api):
    ciphertext = credential_api.encrypt_credential("synthetic credential")
    token = bytearray(base64.urlsafe_b64decode(ciphertext))
    token[-1] ^= 1

    assert credential_api.decrypt_credential(base64.urlsafe_b64encode(token).decode("ascii")) == ""


@pytest.mark.parametrize("ciphertext", ["", "not-a-fernet-token"])
def test_credential_bridge_rejects_malformed_token(credential_api, ciphertext):
    assert credential_api.decrypt_credential(ciphertext) == ""


def test_credential_bridge_does_not_hide_unexpected_errors(credential_api, monkeypatch):
    def unavailable():
        raise OSError("keystore unavailable")

    monkeypatch.setattr(API, "_credential_crypto", staticmethod(unavailable))

    with pytest.raises(OSError, match="keystore unavailable"):
        credential_api.decrypt_credential("token")
