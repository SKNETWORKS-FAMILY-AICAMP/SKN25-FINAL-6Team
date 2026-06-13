from __future__ import annotations

import bcrypt


def verify_password(password: str, password_hash: str | None) -> bool:
    """Verify a plain-text password against a stored bcrypt hash."""
    if not password_hash:
        return False

    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False
