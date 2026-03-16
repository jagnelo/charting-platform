"""
Unit tests for app/services/auth.py

Covers: password hashing, JWT creation/decoding, token expiry,
        token type enforcement, authenticate_user logic.
No DB containers needed for the pure crypto tests; DB fixtures
are used only for authenticate_user.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.config import settings
from app.services.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

# ── Password hashing ───────────────────────────────────────────────────────────


class TestPasswordHashing:
    def test_hash_is_different_from_plaintext(self):
        plain = "mysecretpassword"
        hashed = hash_password(plain)
        assert hashed != plain

    def test_verify_correct_password(self):
        plain = "correcthorsebatterystaple"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_same_password_different_hashes(self):
        """bcrypt generates a new salt each time."""
        pw = "samepassword"
        h1 = hash_password(pw)
        h2 = hash_password(pw)
        assert h1 != h2
        assert verify_password(pw, h1)
        assert verify_password(pw, h2)

    def test_empty_password_handled(self):
        hashed = hash_password("")
        assert verify_password("", hashed) is True
        assert verify_password("notempty", hashed) is False


# ── JWT creation ───────────────────────────────────────────────────────────────


class TestJWTCreation:
    def test_access_token_is_string(self):
        token = create_access_token(1, "alice")
        assert isinstance(token, str)
        assert len(token) > 20

    def test_refresh_token_is_string(self):
        token = create_refresh_token(1)
        assert isinstance(token, str)

    def test_access_token_type_field(self):
        token = create_access_token(42, "bob")
        payload = decode_token(token)
        assert payload["type"] == "access"

    def test_refresh_token_type_field(self):
        token = create_refresh_token(42)
        payload = decode_token(token)
        assert payload["type"] == "refresh"

    def test_access_token_subject(self):
        token = create_access_token(99, "charlie")
        payload = decode_token(token)
        assert payload["sub"] == "99"
        assert payload["username"] == "charlie"

    def test_refresh_token_subject(self):
        token = create_refresh_token(99)
        payload = decode_token(token)
        assert payload["sub"] == "99"

    def test_access_token_expiry(self):
        token = create_access_token(1, "dave")
        payload = decode_token(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
        expected = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        assert abs((exp - expected).total_seconds()) < 5

    def test_refresh_token_expiry(self):
        token = create_refresh_token(1)
        payload = decode_token(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
        expected = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        assert abs((exp - expected).total_seconds()) < 5


# ── JWT decoding ───────────────────────────────────────────────────────────────


class TestJWTDecoding:
    def test_tampered_token_raises(self):
        token = create_access_token(1, "eve")
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(HTTPException) as exc_info:
            decode_token(tampered)
        assert exc_info.value.status_code == 401

    def test_completely_invalid_token_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            decode_token("not.a.token")
        assert exc_info.value.status_code == 401

    def test_expired_token_raises(self):
        from freezegun import freeze_time

        with freeze_time("2020-01-01"):
            token = create_access_token(1, "fred")
        # Token was valid in 2020, definitely expired now
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401

    def test_wrong_secret_raises(self, monkeypatch):
        token = create_access_token(1, "grace")
        monkeypatch.setattr(settings, "SECRET_KEY", "totally-different-secret")
        with pytest.raises(HTTPException):
            decode_token(token)


# ── authenticate_user ──────────────────────────────────────────────────────────


class TestAuthenticateUser:
    def test_valid_credentials_returns_user(self, db, user):
        result = authenticate_user(db, "testuser", "Password123!")
        assert result is not None
        assert result.id == user.id

    def test_wrong_password_returns_none(self, db, user):
        result = authenticate_user(db, "testuser", "wrongpassword")
        assert result is None

    def test_unknown_username_returns_none(self, db):
        result = authenticate_user(db, "doesnotexist", "anypassword")
        assert result is None

    def test_inactive_user_still_returned(self, db):
        """authenticate_user validates credentials only; caller checks is_active."""
        from app.models.user import User
        from app.services.auth import hash_password

        inactive = User(
            username="inactive",
            email="inactive@test.com",
            hashed_password=hash_password("pass"),
            is_active=False,
        )
        db.add(inactive)
        db.flush()
        result = authenticate_user(db, "inactive", "pass")
        assert result is not None
