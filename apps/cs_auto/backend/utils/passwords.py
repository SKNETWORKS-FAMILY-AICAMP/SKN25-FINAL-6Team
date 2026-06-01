from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    """Hash a plain-text password with bcrypt before storing it."""
    password_bytes = password.encode("utf-8")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Verify a plain-text password against a stored bcrypt hash."""
    if not password_hash:
        return False

    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False
