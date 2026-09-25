"""Auth apikey precedence — must match /v1/deals, not JWT secret."""

import os
import sys
from pathlib import Path

os.environ.setdefault("FLASK_ENV", "testing")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from compliance.auth import _auth_apikey  # noqa: E402


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
