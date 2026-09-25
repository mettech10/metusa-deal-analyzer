"""Supabase store failure paths for /v1/compliance."""

import os
import sys
from pathlib import Path

os.environ.setdefault("FLASK_ENV", "testing")
os.environ["COMPLIANCE_FORCE_MEMORY_STORE"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from compliance.store import (  # noqa: E402
    ComplianceStoreError,
    MIGRATION_HINT,
    _raise_store_failure,
    _sb_list_obligations,
    probe_store,
)


class _Resp:
    def __init__(self, status_code, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data

    def json(self):
        return self._json


def test_raise_store_failure_mentions_migration_on_missing_table():
    resp = _Resp(404, '{"code":"PGRST205","message":"Could not find the table"}')
    with pytest.raises(ComplianceStoreError) as exc:
        _raise_store_failure(resp, "compliance_obligations")
    assert exc.value.status_code == 503
    assert "20260914_compliance_cockpit" in str(exc.value)
    assert "20260925_compliance_obligation_applicability" in str(exc.value)


def test_missing_applicability_column_is_503_not_unhandled():
    """PostgREST PGRST204 when the migration has not run yet."""
    resp = _Resp(
        400,
        '{"code":"PGRST204","message":"Could not find the \'applicability\' column '
        'of \'compliance_obligations\' in the schema cache"}',
    )
    with pytest.raises(ComplianceStoreError) as exc:
        _raise_store_failure(resp, "compliance_obligations")
    assert exc.value.status_code == 503
    assert "20260925_compliance_obligation_applicability" in str(exc.value)
    assert "PGRST204" in exc.value.body


def test_list_obligations_does_not_use_nested_embed(monkeypatch):
    calls = []

    def fake_sb(method, path, **kwargs):
        calls.append((method, path, kwargs.get("params", {})))
        if path == "compliance_obligations":
            assert "compliance_reminders" not in kwargs.get("params", {}).get("select", "")
            return _Resp(200, json_data=[{
                "id": "obl-1",
                "user_id": "user-1",
                "property_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "code": "GAS",
                "issued_on": "2026-01-01",
                "expires_on": "2027-01-01",
                "notes": "",
                "created_at": "2026-09-21T00:00:00+00:00",
                "updated_at": "2026-09-21T00:00:00+00:00",
            }])
        return _Resp(200, json_data=[])

    monkeypatch.setattr("compliance.store._sb", fake_sb)
    rows = _sb_list_obligations("user-1")
    assert len(rows) == 1
    tables = {path for _method, path, _params in calls}
    assert "compliance_obligations" in tables
    assert "compliance_reminders" in tables
    assert "compliance_evidence" in tables
    assert all(
        "compliance_reminders(*)" not in (params.get("select") or "")
        for _m, _p, params in calls
    )


def test_list_obligations_missing_table_is_store_error(monkeypatch):
    def fake_sb(method, path, **kwargs):
        return _Resp(404, '{"code":"PGRST205","message":"Could not find the table public.compliance_obligations"}')

    monkeypatch.setattr("compliance.store._sb", fake_sb)
    with pytest.raises(ComplianceStoreError) as exc:
        _sb_list_obligations("user-1")
    assert exc.value.status_code == 503
    assert "PGRST205" in exc.value.body or "20260914" in str(exc.value)


def test_probe_store_memory_when_forced():
    probe = probe_store()
    assert probe["backend"] == "memory"
    assert probe["ready"] is True
    assert MIGRATION_HINT
