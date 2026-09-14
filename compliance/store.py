"""Persistence for ObligationInstance, reminder stubs, and evidence metadata.

Uses in-memory maps by default (tests, local Flask without Supabase).
When SUPABASE_URL + service key are set, rows go through PostgREST like
the rest of the Flask backend.
"""

from __future__ import annotations

import logging
import os
import threading
import uuid
from datetime import date, datetime, timezone
from typing import Optional

import requests

from compliance.catalogue import CATALOGUE_CODES, default_expires_on
from compliance.reminders import (
    DEFAULT_CHANNEL,
    OVERDUE_WEEKLY_CODE,
    build_reminder_stubs,
    build_weekly_overdue_stub,
)
from compliance.status import compute_status

logger = logging.getLogger("compliance.store")

_lock = threading.Lock()
_OBLIGATIONS: dict[str, dict] = {}
_REMINDERS: dict[str, dict] = {}
_EVIDENCE: dict[str, dict] = {}

_SUPABASE_URL = (
    os.environ.get("SUPABASE_URL")
    or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    or ""
).rstrip("/")
_SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_KEY")
    or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_ANON_KEY")
    or ""
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_date(value) -> Optional[date]:
    if value in (None, "", "null"):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()[:10]
    return date.fromisoformat(text)


def _as_of(as_of=None) -> date:
    if as_of is None:
        return date.today()
    return _parse_date(as_of) or date.today()


def supabase_configured() -> bool:
    if os.environ.get("COMPLIANCE_FORCE_MEMORY_STORE") == "1":
        return False
    env = os.environ.get("FLASK_ENV", "").lower()
    if env in ("testing", "test"):
        return False
    return bool(_SUPABASE_URL and _SUPABASE_KEY)


def _sb_headers(prefer: Optional[str] = None) -> dict:
    headers = {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _sb(method: str, path: str, **kwargs):
    url = f"{_SUPABASE_URL}/rest/v1/{path}"
    resp = requests.request(method, url, timeout=12, **kwargs)
    return resp


# ── serialisation ──────────────────────────────────────────────────────────


def _public_reminder(row: dict) -> dict:
    return {
        "id": row["id"],
        "obligationId": row["obligation_id"],
        "offsetCode": row["offset_code"],
        "offsetDays": row["offset_days"],
        "scheduledFor": row["scheduled_for"],
        "status": row["status"],
        "channel": row["channel"],
        "sentAt": row.get("sent_at"),
        "lastError": row.get("last_error"),
        "createdAt": row.get("created_at"),
    }


def _public_evidence(row: dict) -> dict:
    return {
        "id": row["id"],
        "obligationId": row["obligation_id"],
        "filename": row["filename"],
        "contentType": row["content_type"],
        "sizeBytes": row.get("size_bytes"),
        "storageKey": row["storage_key"],
        "url": row.get("url"),
        "createdAt": row.get("created_at"),
    }


def _public_obligation(
    row: dict,
    reminders: Optional[list] = None,
    evidence: Optional[list] = None,
    as_of: Optional[date] = None,
) -> dict:
    expires = _parse_date(row.get("expires_on"))
    issued = _parse_date(row.get("issued_on"))
    status = compute_status(
        expires, issued, as_of=_as_of(as_of), code=row.get("code"),
    )
    return {
        "id": row["id"],
        "userId": row["user_id"],
        "propertyId": row["property_id"],
        "code": row["code"],
        "status": status,
        "issuedOn": row.get("issued_on"),
        "expiresOn": row.get("expires_on"),
        "notes": row.get("notes") or "",
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
        "reminders": [_public_reminder(r) for r in (reminders or [])],
        "evidence": [_public_evidence(e) for e in (evidence or [])],
    }


# ── memory store ───────────────────────────────────────────────────────────


def reset_memory_store() -> None:
    with _lock:
        _OBLIGATIONS.clear()
        _REMINDERS.clear()
        _EVIDENCE.clear()


def _mem_reminders_for(obligation_id: str) -> list[dict]:
    rows = [r for r in _REMINDERS.values() if r["obligation_id"] == obligation_id]
    rows.sort(key=lambda r: (r["scheduled_for"], r["offset_days"]))
    return rows


def _mem_evidence_for(obligation_id: str) -> list[dict]:
    rows = [e for e in _EVIDENCE.values() if e["obligation_id"] == obligation_id]
    rows.sort(key=lambda e: e["created_at"])
    return rows


def _seed_reminders(obligation: dict, as_of: Optional[date]) -> list[dict]:
    stubs = build_reminder_stubs(
        _parse_date(obligation.get("expires_on")),
        obligation["code"],
        as_of=_as_of(as_of),
    )
    created = []
    now = _now_iso()
    for stub in stubs:
        row = {
            "id": str(uuid.uuid4()),
            "obligation_id": obligation["id"],
            "user_id": obligation["user_id"],
            "offset_code": stub["offsetCode"],
            "offset_days": stub["offsetDays"],
            "scheduled_for": stub["scheduledFor"],
            "status": stub["status"],
            "channel": stub["channel"],
            "sent_at": None,
            "last_error": None,
            "created_at": now,
        }
        _REMINDERS[row["id"]] = row
        created.append(row)
    return created


def _replace_unsent_reminders(obligation: dict, as_of: Optional[date]) -> list[dict]:
    to_delete = [
        rid for rid, r in _REMINDERS.items()
        if r["obligation_id"] == obligation["id"] and r["status"] in ("pending", "skipped")
    ]
    for rid in to_delete:
        _REMINDERS.pop(rid, None)
    return _seed_reminders(obligation, as_of)


# ── public API ─────────────────────────────────────────────────────────────


def create_obligation(
    user_id: str,
    *,
    property_id: str,
    code: str,
    issued_on=None,
    expires_on=None,
    notes: str = "",
    as_of=None,
) -> dict:
    code = (code or "").strip().upper()
    if code not in CATALOGUE_CODES:
        raise ValueError(f"Unknown catalogue code: {code}")
    if not property_id:
        raise ValueError("propertyId is required")
    try:
        property_id = str(uuid.UUID(str(property_id)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("propertyId must be a UUID") from exc

    issued = _parse_date(issued_on)
    expires = _parse_date(expires_on)
    if expires is None:
        expires = default_expires_on(code, issued)

    now = _now_iso()
    row = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "property_id": str(property_id),
        "code": code,
        "issued_on": issued.isoformat() if issued else None,
        "expires_on": expires.isoformat() if expires else None,
        "notes": notes or "",
        "created_at": now,
        "updated_at": now,
    }

    if supabase_configured():
        return _sb_create_obligation(row, as_of=as_of)

    with _lock:
        _OBLIGATIONS[row["id"]] = row
        reminders = _seed_reminders(row, as_of)
        return _public_obligation(row, reminders, [], as_of=as_of)


def get_obligation(user_id: str, obligation_id: str, as_of=None) -> Optional[dict]:
    if supabase_configured():
        return _sb_get_obligation(user_id, obligation_id, as_of=as_of)
    with _lock:
        row = _OBLIGATIONS.get(obligation_id)
        if not row or row["user_id"] != user_id:
            return None
        return _public_obligation(
            row,
            _mem_reminders_for(obligation_id),
            _mem_evidence_for(obligation_id),
            as_of=as_of,
        )


def list_obligations(
    user_id: str,
    *,
    property_id: Optional[str] = None,
    code: Optional[str] = None,
    status: Optional[str] = None,
    as_of=None,
) -> list[dict]:
    if supabase_configured():
        rows = _sb_list_obligations(user_id, property_id=property_id, code=code)
        out = []
        for row, reminders, evidence in rows:
            pub = _public_obligation(row, reminders, evidence, as_of=as_of)
            if status and pub["status"] != status:
                continue
            out.append(pub)
        return out

    with _lock:
        items = [r for r in _OBLIGATIONS.values() if r["user_id"] == user_id]
        if property_id:
            items = [r for r in items if r["property_id"] == property_id]
        if code:
            items = [r for r in items if r["code"] == code.strip().upper()]
        items.sort(key=lambda r: r["created_at"], reverse=True)
        out = []
        for row in items:
            pub = _public_obligation(
                row,
                _mem_reminders_for(row["id"]),
                _mem_evidence_for(row["id"]),
                as_of=as_of,
            )
            if status and pub["status"] != status:
                continue
            out.append(pub)
        return out


def update_obligation(user_id: str, obligation_id: str, fields: dict, as_of=None) -> Optional[dict]:
    allowed = {}
    if "propertyId" in fields or "property_id" in fields:
        allowed["property_id"] = str(fields.get("propertyId") or fields.get("property_id"))
    if "notes" in fields:
        allowed["notes"] = fields.get("notes") or ""
    if "issuedOn" in fields or "issued_on" in fields:
        issued = _parse_date(fields.get("issuedOn", fields.get("issued_on")))
        allowed["issued_on"] = issued.isoformat() if issued else None
    if "expiresOn" in fields or "expires_on" in fields:
        expires = _parse_date(fields.get("expiresOn", fields.get("expires_on")))
        allowed["expires_on"] = expires.isoformat() if expires else None
    if "code" in fields and fields["code"]:
        code = str(fields["code"]).strip().upper()
        if code not in CATALOGUE_CODES:
            raise ValueError(f"Unknown catalogue code: {code}")
        allowed["code"] = code

    if supabase_configured():
        return _sb_update_obligation(user_id, obligation_id, allowed, as_of=as_of)

    with _lock:
        row = _OBLIGATIONS.get(obligation_id)
        if not row or row["user_id"] != user_id:
            return None
        expires_changed = "expires_on" in allowed and allowed["expires_on"] != row.get("expires_on")
        issued_only = (
            "issued_on" in allowed
            and "expires_on" not in allowed
            and row.get("expires_on") is None
        )
        row.update(allowed)
        if issued_only:
            derived = default_expires_on(row["code"], _parse_date(row.get("issued_on")))
            if derived:
                row["expires_on"] = derived.isoformat()
                expires_changed = True
        row["updated_at"] = _now_iso()
        if expires_changed:
            _replace_unsent_reminders(row, as_of)
        reminders = _mem_reminders_for(obligation_id)
        return _public_obligation(row, reminders, _mem_evidence_for(obligation_id), as_of=as_of)


def delete_obligation(user_id: str, obligation_id: str) -> bool:
    if supabase_configured():
        return _sb_delete_obligation(user_id, obligation_id)
    with _lock:
        row = _OBLIGATIONS.get(obligation_id)
        if not row or row["user_id"] != user_id:
            return False
        _OBLIGATIONS.pop(obligation_id, None)
        for rid in [rid for rid, r in _REMINDERS.items() if r["obligation_id"] == obligation_id]:
            _REMINDERS.pop(rid, None)
        for eid in [eid for eid, e in _EVIDENCE.items() if e["obligation_id"] == obligation_id]:
            _EVIDENCE.pop(eid, None)
        return True


def add_evidence(
    user_id: str,
    obligation_id: str,
    *,
    filename: str,
    content_type: str,
    size_bytes: int,
    storage_key: str,
    url: Optional[str] = None,
) -> Optional[dict]:
    if supabase_configured():
        parent = _sb_get_obligation(user_id, obligation_id)
        if not parent:
            return None
        return _sb_add_evidence(
            user_id, obligation_id, filename, content_type, size_bytes, storage_key, url,
        )
    with _lock:
        row = _OBLIGATIONS.get(obligation_id)
        if not row or row["user_id"] != user_id:
            return None
        evidence = {
            "id": str(uuid.uuid4()),
            "obligation_id": obligation_id,
            "user_id": user_id,
            "filename": filename,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "storage_key": storage_key,
            "url": url,
            "created_at": _now_iso(),
        }
        _EVIDENCE[evidence["id"]] = evidence
        return _public_evidence(evidence)


def get_evidence(user_id: str, obligation_id: str, evidence_id: str) -> Optional[dict]:
    obl = get_obligation(user_id, obligation_id)
    if not obl:
        return None
    for item in obl.get("evidence") or []:
        if item["id"] == evidence_id:
            return item
    return None


def list_reminders(
    user_id: str,
    *,
    obligation_id: Optional[str] = None,
    status: Optional[str] = None,
    channel: Optional[str] = None,
) -> list[dict]:
    if supabase_configured():
        return _sb_list_reminders(
            user_id, obligation_id=obligation_id, status=status, channel=channel,
        )
    with _lock:
        rows = [r for r in _REMINDERS.values() if r["user_id"] == user_id]
        if obligation_id:
            rows = [r for r in rows if r["obligation_id"] == obligation_id]
        if status:
            rows = [r for r in rows if r["status"] == status]
        if channel:
            rows = [r for r in rows if r["channel"] == channel]
        rows.sort(key=lambda r: (r["scheduled_for"], r["offset_days"]))
        return [_public_reminder(r) for r in rows]


def due_reminders(as_of=None, status: str = "pending", channel: Optional[str] = "email") -> list[dict]:
    """All-users due reminders for the cron dispatcher.

    Defaults to channel=email so in_app stubs stay for the frontend.
    Pass channel=None to include every channel.
    """
    today = _as_of(as_of).isoformat()
    if supabase_configured():
        return _sb_due_reminders(today, status=status, channel=channel)
    with _lock:
        rows = [
            r for r in _REMINDERS.values()
            if r["status"] == status and r["scheduled_for"] <= today
        ]
        if channel:
            rows = [r for r in rows if r.get("channel") == channel]
        rows.sort(key=lambda r: (r["scheduled_for"], r["offset_days"]))
        out = []
        for r in rows:
            obl = _OBLIGATIONS.get(r["obligation_id"])
            item = _public_reminder(r)
            item["userId"] = r["user_id"]
            item["obligation"] = _public_obligation(obl, [], [], as_of=as_of) if obl else None
            out.append(item)
        return out


def mark_reminder(reminder_id: str, *, status: str, last_error: Optional[str] = None) -> Optional[dict]:
    sent_at = _now_iso() if status in ("sent", "skipped") else None
    if supabase_configured():
        return _sb_mark_reminder(reminder_id, status=status, sent_at=sent_at, last_error=last_error)
    with _lock:
        row = _REMINDERS.get(reminder_id)
        if not row:
            return None
        row["status"] = status
        row["sent_at"] = sent_at
        row["last_error"] = last_error
        return _public_reminder(row)


def _reminder_row_from_stub(obligation: dict, stub: dict) -> dict:
    user_id = obligation.get("user_id") or obligation.get("userId")
    obl_id = obligation.get("id") or obligation.get("obligationId")
    return {
        "id": str(uuid.uuid4()),
        "obligation_id": obl_id,
        "user_id": user_id,
        "offset_code": stub["offsetCode"],
        "offset_days": stub["offsetDays"],
        "scheduled_for": stub["scheduledFor"],
        "status": stub.get("status") or "pending",
        "channel": stub.get("channel") or DEFAULT_CHANNEL,
        "sent_at": None,
        "last_error": None,
        "created_at": _now_iso(),
    }


def add_reminder_stub(obligation: dict, stub: dict) -> dict:
    """Persist a single stub (weekly overdue / future in_app)."""
    row = _reminder_row_from_stub(obligation, stub)
    if supabase_configured():
        return _sb_insert_reminders([row])[0]
    with _lock:
        _REMINDERS[row["id"]] = row
        return _public_reminder(row)


def enqueue_weekly_overdue(
    obligation: dict,
    last_scheduled,
    *,
    as_of=None,
    channel: str = DEFAULT_CHANNEL,
) -> Optional[dict]:
    """If the obligation is still overdue, queue the next weekly email stub.

    Skips when a pending weekly stub already exists so cron re-runs don't
    duplicate. Does not catch up missed weeks (no email storm).
    """
    if not obligation or obligation.get("status") != "overdue":
        return None
    expires = _parse_date(obligation.get("expiresOn") or obligation.get("expires_on"))
    if expires is None:
        return None
    last = _parse_date(last_scheduled) or _as_of(as_of)
    obl_id = obligation.get("id")
    channel = (channel or DEFAULT_CHANNEL).lower()

    if supabase_configured():
        return _sb_enqueue_weekly(obligation, expires, last, as_of=as_of, channel=channel)

    with _lock:
        pending = [
            r for r in _REMINDERS.values()
            if r["obligation_id"] == obl_id
            and r["status"] == "pending"
            and r["offset_code"] == OVERDUE_WEEKLY_CODE
            and r.get("channel") == channel
        ]
        if pending:
            return None
        stub = build_weekly_overdue_stub(expires, last, as_of=_as_of(as_of), channel=channel)
        row = _reminder_row_from_stub(
            {
                "id": obl_id,
                "user_id": obligation.get("userId") or obligation.get("user_id"),
            },
            stub,
        )
        _REMINDERS[row["id"]] = row
        return _public_reminder(row)


# ── supabase implementations ───────────────────────────────────────────────


def _row_from_sb(data: dict) -> dict:
    return {
        "id": data["id"],
        "user_id": data["user_id"],
        "property_id": data["property_id"],
        "code": data["code"],
        "issued_on": data.get("issued_on"),
        "expires_on": data.get("expires_on"),
        "notes": data.get("notes") or "",
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
    }


def _sb_create_obligation(row: dict, as_of=None) -> dict:
    resp = _sb(
        "POST",
        "compliance_obligations",
        json={
            "id": row["id"],
            "user_id": row["user_id"],
            "property_id": row["property_id"],
            "code": row["code"],
            "issued_on": row["issued_on"],
            "expires_on": row["expires_on"],
            "notes": row["notes"],
        },
        headers=_sb_headers("return=representation"),
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Failed to persist obligation: {resp.status_code} {resp.text[:200]}")
    saved = resp.json()
    saved = saved[0] if isinstance(saved, list) else saved
    row = _row_from_sb(saved)
    stubs = build_reminder_stubs(
        _parse_date(row.get("expires_on")), row["code"], as_of=_as_of(as_of),
    )
    reminder_rows = []
    if stubs:
        payload = [{
            "obligation_id": row["id"],
            "user_id": row["user_id"],
            "offset_code": s["offsetCode"],
            "offset_days": s["offsetDays"],
            "scheduled_for": s["scheduledFor"],
            "status": s["status"],
            "channel": s["channel"],
        } for s in stubs]
        rresp = _sb(
            "POST",
            "compliance_reminders",
            json=payload,
            headers=_sb_headers("return=representation"),
        )
        if rresp.status_code in (200, 201):
            reminder_rows = rresp.json() if isinstance(rresp.json(), list) else [rresp.json()]
        else:
            logger.warning("[compliance] reminder insert failed: %s", rresp.text[:200])
    return _public_obligation(row, reminder_rows, [], as_of=as_of)


def _sb_get_obligation(user_id: str, obligation_id: str, as_of=None) -> Optional[dict]:
    resp = _sb(
        "GET",
        "compliance_obligations",
        params={
            "id": f"eq.{obligation_id}",
            "user_id": f"eq.{user_id}",
            "select": "*,compliance_reminders(*),compliance_evidence(*)",
        },
        headers=_sb_headers(),
    )
    if resp.status_code != 200:
        logger.warning("[compliance] get obligation failed: %s", resp.text[:200])
        return None
    rows = resp.json()
    if not rows:
        return None
    data = rows[0]
    return _public_obligation(
        _row_from_sb(data),
        data.get("compliance_reminders") or [],
        data.get("compliance_evidence") or [],
        as_of=as_of,
    )


def _sb_list_obligations(user_id: str, property_id=None, code=None):
    params = {
        "user_id": f"eq.{user_id}",
        "select": "*,compliance_reminders(*),compliance_evidence(*)",
        "order": "created_at.desc",
    }
    if property_id:
        params["property_id"] = f"eq.{property_id}"
    if code:
        params["code"] = f"eq.{code.strip().upper()}"
    resp = _sb("GET", "compliance_obligations", params=params, headers=_sb_headers())
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to list obligations: {resp.status_code}")
    out = []
    for data in resp.json():
        out.append((
            _row_from_sb(data),
            data.get("compliance_reminders") or [],
            data.get("compliance_evidence") or [],
        ))
    return out


def _sb_update_obligation(user_id, obligation_id, allowed, as_of=None):
    if not allowed:
        return _sb_get_obligation(user_id, obligation_id, as_of=as_of)
    allowed["updated_at"] = _now_iso()
    existing = _sb_get_obligation(user_id, obligation_id, as_of=as_of)
    if not existing:
        return None
    if "issued_on" in allowed and "expires_on" not in allowed and not existing.get("expiresOn"):
        derived = default_expires_on(
            allowed.get("code") or existing["code"],
            _parse_date(allowed.get("issued_on")),
        )
        if derived:
            allowed["expires_on"] = derived.isoformat()
    resp = _sb(
        "PATCH",
        "compliance_obligations",
        params={"id": f"eq.{obligation_id}", "user_id": f"eq.{user_id}"},
        json=allowed,
        headers=_sb_headers("return=representation"),
    )
    if resp.status_code not in (200, 204):
        raise RuntimeError(f"Failed to update obligation: {resp.status_code}")
    expires_changed = "expires_on" in allowed
    if expires_changed:
        _sb(
            "DELETE",
            "compliance_reminders",
            params={
                "obligation_id": f"eq.{obligation_id}",
                "status": "in.(pending,skipped)",
            },
            headers=_sb_headers(),
        )
        updated = _sb_get_obligation(user_id, obligation_id, as_of=as_of) or existing
        stubs = build_reminder_stubs(
            _parse_date(updated.get("expiresOn")),
            updated["code"],
            as_of=_as_of(as_of),
        )
        if stubs:
            payload = [{
                "obligation_id": obligation_id,
                "user_id": user_id,
                "offset_code": s["offsetCode"],
                "offset_days": s["offsetDays"],
                "scheduled_for": s["scheduledFor"],
                "status": s["status"],
                "channel": s["channel"],
            } for s in stubs]
            _sb("POST", "compliance_reminders", json=payload, headers=_sb_headers("return=minimal"))
    return _sb_get_obligation(user_id, obligation_id, as_of=as_of)


def _sb_delete_obligation(user_id, obligation_id) -> bool:
    existing = _sb_get_obligation(user_id, obligation_id)
    if not existing:
        return False
    resp = _sb(
        "DELETE",
        "compliance_obligations",
        params={"id": f"eq.{obligation_id}", "user_id": f"eq.{user_id}"},
        headers=_sb_headers(),
    )
    return resp.status_code in (200, 204)


def _sb_add_evidence(user_id, obligation_id, filename, content_type, size_bytes, storage_key, url):
    resp = _sb(
        "POST",
        "compliance_evidence",
        json={
            "obligation_id": obligation_id,
            "user_id": user_id,
            "filename": filename,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "storage_key": storage_key,
            "url": url,
        },
        headers=_sb_headers("return=representation"),
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Failed to persist evidence: {resp.status_code} {resp.text[:200]}")
    data = resp.json()
    data = data[0] if isinstance(data, list) else data
    return _public_evidence(data)


def _sb_list_reminders(user_id, obligation_id=None, status=None, channel=None):
    params = {"user_id": f"eq.{user_id}", "order": "scheduled_for.asc"}
    if obligation_id:
        params["obligation_id"] = f"eq.{obligation_id}"
    if status:
        params["status"] = f"eq.{status}"
    if channel:
        params["channel"] = f"eq.{channel}"
    resp = _sb("GET", "compliance_reminders", params=params, headers=_sb_headers())
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to list reminders: {resp.status_code}")
    return [_public_reminder(r) for r in resp.json()]


def _sb_due_reminders(today: str, status: str = "pending", channel: Optional[str] = "email"):
    params = {
        "status": f"eq.{status}",
        "scheduled_for": f"lte.{today}",
        "select": "*,compliance_obligations(*)",
        "order": "scheduled_for.asc",
    }
    if channel:
        params["channel"] = f"eq.{channel}"
    resp = _sb("GET", "compliance_reminders", params=params, headers=_sb_headers())
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to list due reminders: {resp.status_code}")
    out = []
    for r in resp.json():
        item = _public_reminder(r)
        item["userId"] = r.get("user_id")
        obl = r.get("compliance_obligations")
        item["obligation"] = _public_obligation(_row_from_sb(obl), [], []) if obl else None
        out.append(item)
    return out


def _sb_insert_reminders(rows: list[dict]) -> list[dict]:
    payload = [{
        "id": r["id"],
        "obligation_id": r["obligation_id"],
        "user_id": r["user_id"],
        "offset_code": r["offset_code"],
        "offset_days": r["offset_days"],
        "scheduled_for": r["scheduled_for"],
        "status": r["status"],
        "channel": r["channel"],
    } for r in rows]
    resp = _sb(
        "POST",
        "compliance_reminders",
        json=payload,
        headers=_sb_headers("return=representation"),
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Failed to insert reminders: {resp.status_code} {resp.text[:200]}")
    data = resp.json()
    if not isinstance(data, list):
        data = [data]
    return [_public_reminder(r) for r in data]


def _sb_enqueue_weekly(obligation, expires, last, *, as_of, channel):
    obl_id = obligation.get("id")
    user_id = obligation.get("userId") or obligation.get("user_id")
    resp = _sb(
        "GET",
        "compliance_reminders",
        params={
            "obligation_id": f"eq.{obl_id}",
            "status": "eq.pending",
            "offset_code": f"eq.{OVERDUE_WEEKLY_CODE}",
            "channel": f"eq.{channel}",
            "select": "id",
        },
        headers=_sb_headers(),
    )
    if resp.status_code == 200 and resp.json():
        return None
    stub = build_weekly_overdue_stub(expires, last, as_of=_as_of(as_of), channel=channel)
    row = _reminder_row_from_stub({"id": obl_id, "user_id": user_id}, stub)
    inserted = _sb_insert_reminders([row])
    return inserted[0] if inserted else None


def _sb_mark_reminder(reminder_id, *, status, sent_at, last_error):
    resp = _sb(
        "PATCH",
        "compliance_reminders",
        params={"id": f"eq.{reminder_id}"},
        json={"status": status, "sent_at": sent_at, "last_error": last_error},
        headers=_sb_headers("return=representation"),
    )
    if resp.status_code not in (200, 204):
        raise RuntimeError(f"Failed to update reminder: {resp.status_code}")
    data = resp.json()
    if not data:
        return None
    data = data[0] if isinstance(data, list) else data
    return _public_reminder(data)
