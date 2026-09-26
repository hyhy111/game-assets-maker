"""
Credential encryption for the "remember account/password" feature.

Protection levels:
- Windows: DPAPI (CryptProtectData) — the key is derived from the current
  Windows user's master key, so ciphertext copied to another user/machine
  cannot be decrypted.
- Non-Windows fallback: Fernet symmetric encryption with the key stored in a
  local file in the active GAM data root. This only stops casual inspection;
  anyone who can read the local file can decrypt. Used for dev on macOS/Linux.
"""

import base64
import os
import sys

from src.utils.data_paths import data_root


class CredentialCrypto:
    """Encrypt/decrypt short credential strings for local storage."""

    def __init__(self) -> None:
        self._use_dpapi = sys.platform == "win32"
        if self._use_dpapi:
            try:
                import win32crypt  # noqa: F401
            except ImportError:
                self._use_dpapi = False
        if not self._use_dpapi:
            from cryptography.fernet import Fernet

            self._fernet = Fernet(self._load_or_create_keystore())

    # ---------- Windows DPAPI ----------

    @staticmethod
    def _dpapi_protect(data: bytes) -> bytes:
        import win32crypt

        # entropy=None binds to the current user; no extra entropy so
        # decrypt_credential works transparently for the same user.
        desc = "game_assets_maker credential"
        result = win32crypt.CryptProtectData(
            data, desc, None, None, None, 0
        )
        return result

    @staticmethod
    def _dpapi_unprotect(data: bytes) -> bytes:
        import win32crypt

        _, plaintext = win32crypt.CryptUnprotectData(data, None, None, None, 0)
        return plaintext

    # ---------- Non-Windows fallback ----------

    @staticmethod
    def _load_or_create_keystore() -> bytes:
        keystore_path = data_root() / ".keystore"
        keystore_path.parent.mkdir(parents=True, exist_ok=True)
        if keystore_path.exists():
            return keystore_path.read_bytes().strip()
        from cryptography.fernet import Fernet

        key = Fernet.generate_key()
        # Restrict read to the current user where the platform supports it.
        fd = os.open(str(keystore_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key)
        return key

    # ---------- Public API ----------

    def encrypt(self, plaintext: str) -> str:
        data = plaintext.encode("utf-8")
        if self._use_dpapi:
            # DPAPI output is raw bytes; base64 so it survives JSON/localStorage.
            return base64.b64encode(self._dpapi_protect(data)).decode("ascii")
        # Fernet tokens are already URL-safe base64 text.
        return self._fernet.encrypt(data).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        if self._use_dpapi:
            return self._dpapi_unprotect(base64.b64decode(ciphertext)).decode("utf-8")
        return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
