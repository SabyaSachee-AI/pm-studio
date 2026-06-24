"""At-rest encryption for stored secrets (GitHub PAT, SSH keys, etc.).

Keyed off JWT_SECRET so no extra config is needed. Backward compatible: values
without the ``enc:v1:`` prefix are treated as legacy plaintext and returned as-is,
so existing rows keep working and get encrypted on next save.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

_PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    secret = (get_settings().jwt_secret or "pm-studio-fallback-key").encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def encrypt_secret(value: str | None) -> str | None:
    if not value or value.startswith(_PREFIX):
        return value
    return _PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str | None) -> str | None:
    if not value or not value.startswith(_PREFIX):
        return value  # legacy plaintext
    try:
        return _fernet().decrypt(value[len(_PREFIX):].encode()).decode()
    except InvalidToken:
        return value
