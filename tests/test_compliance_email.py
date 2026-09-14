"""Brevo adapter: env-gated send, fail-soft skip, in_app never emailed."""

import os

import pytest

from compliance.email import brevo_configured, send_reminder_email
from compliance.storage import (
    build_evidence_key,
    key_belongs_to_tenant,
    tenant_prefix,
)


OBLIGATION = {
    "id": "obl-1",
    "code": "GAS",
    "expiresOn": "2026-09-01",
}
REMINDER = {
    "id": "rem-1",
    "offsetCode": "overdue",
    "scheduledFor": "2026-09-02",
    "channel": "email",
}


@pytest.fixture(autouse=True)
def _clear_brevo(monkeypatch):
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.delenv("BREVO_SENDER_EMAIL", raising=False)


def test_unconfigured_without_key():
    assert brevo_configured() is False


def test_skip_when_key_missing():
    result = send_reminder_email(
        user_id="user-1",
        obligation=OBLIGATION,
        reminder=REMINDER,
        to_email="landlord@example.com",
    )
    assert result["ok"] is True
    assert result["skipped"] is True
    assert result["delivered"] is False
    assert "BREVO_API_KEY" in result["message"]


def test_in_app_never_calls_brevo(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "x")
    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("should not POST")

    monkeypatch.setattr("compliance.email.requests.post", boom)
    result = send_reminder_email(
        user_id="user-1",
        obligation=OBLIGATION,
        reminder={**REMINDER, "channel": "in_app"},
        to_email="landlord@example.com",
    )
    assert result["skipped"] is True
    assert called["n"] == 0
    assert "in_app" in result["message"]


def test_brevo_send_success(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "test-key")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "noreply@metalyzi.co.uk")

    class Resp:
        status_code = 201
        text = '{"messageId":"abc-123"}'

        def json(self):
            return {"messageId": "abc-123"}

    def fake_post(url, json=None, headers=None, timeout=None):
        assert url.endswith("/smtp/email")
        assert headers["api-key"] == "test-key"
        assert json["to"][0]["email"] == "landlord@example.com"
        assert "Gas Safety" in json["subject"]
        return Resp()

    monkeypatch.setattr("compliance.email.requests.post", fake_post)
    result = send_reminder_email(
        user_id="user-1",
        obligation=OBLIGATION,
        reminder=REMINDER,
        to_email="landlord@example.com",
    )
    assert result["delivered"] is True
    assert result["ok"] is True
    assert result["messageId"] == "abc-123"
    assert result["provider"] == "brevo"


def test_brevo_http_error_is_fail_soft(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "test-key")

    class Resp:
        status_code = 400
        text = "bad sender"

        def json(self):
            return {}

    monkeypatch.setattr(
        "compliance.email.requests.post",
        lambda *a, **k: Resp(),
    )
    result = send_reminder_email(
        user_id="user-1",
        obligation=OBLIGATION,
        reminder=REMINDER,
        to_email="landlord@example.com",
    )
    assert result["ok"] is False
    assert result["delivered"] is False
    assert "400" in result["message"]


def test_skip_without_recipient(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "test-key")
    monkeypatch.setattr("compliance.email.lookup_user_email", lambda uid: None)
    result = send_reminder_email(
        user_id="user-1",
        obligation=OBLIGATION,
        reminder=REMINDER,
        to_email=None,
    )
    assert result["skipped"] is True
    assert "recipient" in result["message"].lower()


def test_evidence_key_is_tenant_prefixed():
    key = build_evidence_key(
        "11111111-1111-1111-1111-111111111111",
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "eid",
        "gas.pdf",
    )
    user = "11111111-1111-1111-1111-111111111111"
    assert key.startswith(tenant_prefix(user))
    assert key_belongs_to_tenant(user, key)
    assert not key_belongs_to_tenant(user, "../etc/passwd")
    assert not key_belongs_to_tenant(
        user, "22222222-2222-2222-2222-222222222222/x/y.pdf",
    )
