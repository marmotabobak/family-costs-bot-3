"""Password hashing utilities using bcrypt."""

import bcrypt


def hash_password(plain_password: str) -> str:
    """Hash a password using bcrypt. Returns the hash as a UTF-8 string."""
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed: str) -> bool:
    """Verify a plain password against a bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed.encode("utf-8"))
