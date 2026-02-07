"""Unit tests for bot/security.py password hashing utilities."""

from bot.security import hash_password, verify_password


def test_hash_password_returns_bcrypt_hash():
    """Test that hash_password returns a bcrypt hash starting with $2b$."""
    password = "test_password"
    hashed = hash_password(password)

    assert hashed.startswith("$2b$")
    assert len(hashed) > 50  # bcrypt hashes are typically 60 characters


def test_verify_password_correct():
    """Test that verify_password returns True for correct password."""
    password = "my_secret_password"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True


def test_verify_password_wrong():
    """Test that verify_password returns False for wrong password."""
    password = "correct_password"
    wrong_password = "wrong_password"
    hashed = hash_password(password)

    assert verify_password(wrong_password, hashed) is False


def test_hash_password_different_salts():
    """Test that hashing the same password twice produces different hashes (different salts)."""
    password = "same_password"
    hash1 = hash_password(password)
    hash2 = hash_password(password)

    assert hash1 != hash2
    # But both should verify correctly
    assert verify_password(password, hash1) is True
    assert verify_password(password, hash2) is True


def test_verify_password_empty_string():
    """Test that empty password can be hashed and verified."""
    password = ""
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True


def test_verify_password_unicode():
    """Test that unicode passwords can be hashed and verified."""
    password = "пароль"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True
