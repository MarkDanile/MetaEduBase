import pytest
from unittest.mock import AsyncMock, patch

from app.contexts.identity.application.auth_service import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password():
    password = "test_password_123"
    hashed = hash_password(password)
    assert isinstance(hashed, str)
    assert hashed != password
    assert verify_password(password, hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("correct_password")
    assert verify_password("wrong_password", hashed) is False


def test_create_and_decode_token():
    data = {"sub": "user-123", "tid": "tenant-456"}
    token = create_access_token(data)
    assert isinstance(token, str)

    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["tid"] == "tenant-456"


def test_decode_invalid_token():
    result = decode_access_token("invalid.token.string")
    assert result is None


def test_decode_tampered_token():
    data = {"sub": "user-123"}
    token = create_access_token(data)
    tampered = token + "x"
    result = decode_access_token(tampered)
    assert result is None
