"""Auth apikey precedence — must match /v1/deals, not JWT secret."""

import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("FLASK_ENV", "testing")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from compliance.auth import _auth_apikey  # noqa: E402
from supabase_gotrue import (  # noqa: E402
    GotrueAuthError,
    auth_readiness,
    fetch_gotrue_user,
    supabase_host,
)


def test_auth_apikey_prefers_service_role_like_deals(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-role-key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-or-jwt-secret")
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "public-anon")
    key, source = _auth_apikey()
    assert source == "service"
    assert key == "service-role-key"


def test_auth_apikey_falls_back_to_anon(monkeypatch):
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "public-anon")
    key, source = _auth_apikey()
    assert source == "anon"
    assert key == "public-anon"


def test_auth_apikey_none_when_unset(monkeypatch):
    for name in (
        "SUPABASE_SERVICE_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_ANON_KEY",
        "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    key, source = _auth_apikey()
    assert source == "none"
    assert key == ""


def test_missing_apikey_is_503_not_401(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://lftlugydvvcjtujalzwh.supabase.co")
    for name in (
        "SUPABASE_SERVICE_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_ANON_KEY",
        "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    try:
        fetch_gotrue_user("user-access-jwt")
    except GotrueAuthError as exc:
        assert exc.status == 503
        assert exc.code == "auth_not_configured"
        assert "missing anon key" in exc.message
    else:
        raise AssertionError("expected GotrueAuthError")


def test_missing_url_is_503(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-role-key")
    try:
        fetch_gotrue_user("user-access-jwt")
    except GotrueAuthError as exc:
        assert exc.status == 503
        assert "missing SUPABASE_URL" in exc.message
    else:
        raise AssertionError("expected GotrueAuthError")


def test_never_sends_user_token_as_apikey(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://lftlugydvvcjtujalzwh.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-role-key")
    token = "user-access-jwt"
    captured = {}

    def fake_get(url, headers=None, timeout=8):
        captured["url"] = url
        captured["headers"] = headers
        resp = Mock()
        resp.status_code = 200
        resp.json.return_value = {"id": "user-1", "email": "a@b.c"}
        return resp

    with patch("supabase_gotrue.requests.get", side_effect=fake_get):
        user = fetch_gotrue_user(token)

    assert user["id"] == "user-1"
    assert captured["headers"]["apikey"] == "service-role-key"
    assert captured["headers"]["apikey"] != token
    assert captured["headers"]["Authorization"] == f"Bearer {token}"


def test_auth_readiness_exposes_host_not_secrets(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://lftlugydvvcjtujalzwh.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-role-key")
    ready = auth_readiness()
    assert ready["ready"] is True
    assert ready["apikeySource"] == "service"
    assert ready["supabaseHost"] == "lftlugydvvcjtujalzwh.supabase.co"
    assert ready["gotrue"] == "/auth/v1/user"
    dumped = str(ready)
    assert "service-role-key" not in dumped
    assert supabase_host() == "lftlugydvvcjtujalzwh.supabase.co"
