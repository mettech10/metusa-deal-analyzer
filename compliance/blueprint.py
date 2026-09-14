"""Flask blueprint: /v1/compliance/*

Endpoints:
  GET    /v1/compliance/health
  GET    /v1/compliance/catalogue
  GET    /v1/compliance/dashboard
  GET    /v1/compliance/obligations
  POST   /v1/compliance/obligations
  GET    /v1/compliance/obligations/<id>
  PATCH  /v1/compliance/obligations/<id>
  DELETE /v1/compliance/obligations/<id>
  GET    /v1/compliance/properties/<propertyId>/obligations
  POST   /v1/compliance/obligations/<id>/evidence
  GET    /v1/compliance/obligations/<id>/evidence
  GET    /v1/compliance/obligations/<id>/evidence/<eid>/download
  GET    /v1/compliance/reminders
  POST   /v1/compliance/reminders/dispatch   (cron)
"""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import date

from flask import Blueprint, jsonify, request, send_file
from io import BytesIO

from compliance.auth import require_cron, require_user
from compliance.catalogue import CATALOGUE, CATALOGUE_CODES
from compliance.email_stub import send_reminder_email
from compliance import store
from compliance import storage as blob_store
from compliance.storage import (
    ALLOWED_CONTENT_TYPES,
    MAX_EVIDENCE_BYTES,
    content_type_allowed,
    sanitize_filename,
)

bp = Blueprint("compliance", __name__, url_prefix="/v1/compliance")


def _as_of_from_request():
    raw = request.args.get("asOf") or request.args.get("as_of")
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _json():
    return request.get_json(silent=True) or {}


def _bad_request(message: str, extra: dict | None = None):
    body = {"success": False, "message": message}
    if extra:
        body.update(extra)
    return jsonify(body), 400


@bp.get("/health")
def health():
    return jsonify({
        "success": True,
        "status": "ok",
        "service": "compliance",
        "store": "supabase" if store.supabase_configured() else "memory",
        "blobStore": blob_store.storage_backend(),
        "catalogueCodes": sorted(CATALOGUE_CODES),
    })


@bp.get("/catalogue")
def catalogue():
    return jsonify({
        "success": True,
        "items": list(CATALOGUE.values()),
        "statuses": ["valid", "due_soon", "overdue"],
        "reminderOffsetsDays": [-90, -60, -30, -14, -7, 0, 1],
    })


@bp.get("/dashboard")
@require_user
def dashboard():
    as_of = _as_of_from_request()
    property_id = request.args.get("propertyId") or request.args.get("property_id")
    items = store.list_obligations(
        request.compliance_user_id,
        property_id=property_id,
        as_of=as_of,
    )
    counts = {"valid": 0, "due_soon": 0, "overdue": 0}
    for item in items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    upcoming = []
    for item in items:
        for rem in item.get("reminders") or []:
            if rem.get("status") == "pending":
                upcoming.append({**rem, "code": item["code"], "propertyId": item["propertyId"]})
    upcoming.sort(key=lambda r: r.get("scheduledFor") or "")
    return jsonify({
        "success": True,
        "asOf": (as_of or date.today()).isoformat(),
        "counts": counts,
        "obligations": items,
        "upcomingReminders": upcoming[:50],
    })


@bp.get("/obligations")
@require_user
def list_obligations():
    as_of = _as_of_from_request()
    items = store.list_obligations(
        request.compliance_user_id,
        property_id=request.args.get("propertyId") or request.args.get("property_id"),
        code=request.args.get("code"),
        status=request.args.get("status"),
        as_of=as_of,
    )
    return jsonify({"success": True, "obligations": items, "count": len(items)})


@bp.post("/obligations")
@require_user
def create_obligation():
    body = _json()
    property_id = body.get("propertyId") or body.get("property_id")
    code = body.get("code")
    if not property_id:
        return _bad_request("propertyId is required")
    if not code:
        return _bad_request("code is required", {"allowed": sorted(CATALOGUE_CODES)})
    try:
        created = store.create_obligation(
            request.compliance_user_id,
            property_id=str(property_id),
            code=str(code),
            issued_on=body.get("issuedOn") or body.get("issued_on"),
            expires_on=body.get("expiresOn") or body.get("expires_on"),
            notes=body.get("notes") or "",
            as_of=_as_of_from_request(),
        )
    except ValueError as exc:
        return _bad_request(str(exc), {"allowed": sorted(CATALOGUE_CODES)})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 500
    return jsonify({"success": True, "obligation": created}), 201


@bp.get("/obligations/<obligation_id>")
@require_user
def get_obligation(obligation_id):
    item = store.get_obligation(
        request.compliance_user_id, obligation_id, as_of=_as_of_from_request(),
    )
    if not item:
        return jsonify({"success": False, "message": "Obligation not found"}), 404
    return jsonify({"success": True, "obligation": item})


@bp.patch("/obligations/<obligation_id>")
@require_user
def patch_obligation(obligation_id):
    body = _json()
    try:
        updated = store.update_obligation(
            request.compliance_user_id, obligation_id, body, as_of=_as_of_from_request(),
        )
    except ValueError as exc:
        return _bad_request(str(exc))
    if not updated:
        return jsonify({"success": False, "message": "Obligation not found"}), 404
    return jsonify({"success": True, "obligation": updated})


@bp.delete("/obligations/<obligation_id>")
@require_user
def delete_obligation(obligation_id):
    ok = store.delete_obligation(request.compliance_user_id, obligation_id)
    if not ok:
        return jsonify({"success": False, "message": "Obligation not found"}), 404
    return jsonify({"success": True, "deleted": True})


@bp.get("/properties/<property_id>/obligations")
@require_user
def property_obligations(property_id):
    items = store.list_obligations(
        request.compliance_user_id,
        property_id=property_id,
        as_of=_as_of_from_request(),
    )
    return jsonify({
        "success": True,
        "propertyId": property_id,
        "obligations": items,
        "count": len(items),
    })


def _read_upload_payload():
    """Accept multipart file or JSON {filename, contentType, dataBase64}."""
    if request.files:
        upload = request.files.get("file") or next(iter(request.files.values()), None)
        if upload is None or not upload.filename:
            return None, _bad_request("file is required")
        data = upload.read()
        filename = sanitize_filename(upload.filename)
        content_type = (
            upload.mimetype
            or request.form.get("contentType")
            or "application/octet-stream"
        )
        return (filename, content_type, data), None

    body = _json()
    raw_b64 = body.get("dataBase64") or body.get("data_base64")
    if not raw_b64:
        return None, _bad_request("file or dataBase64 is required")
    try:
        data = base64.b64decode(raw_b64, validate=False)
    except (binascii.Error, ValueError):
        return None, _bad_request("dataBase64 is not valid base64")
    filename = sanitize_filename(body.get("filename") or "evidence")
    content_type = body.get("contentType") or body.get("content_type") or "application/pdf"
    return (filename, content_type, data), None


@bp.post("/obligations/<obligation_id>/evidence")
@require_user
def upload_evidence(obligation_id):
    user_id = request.compliance_user_id
    parent = store.get_obligation(user_id, obligation_id)
    if not parent:
        return jsonify({"success": False, "message": "Obligation not found"}), 404

    parsed, err = _read_upload_payload()
    if err is not None:
        return err
    filename, content_type, data = parsed

    if not data:
        return _bad_request("empty file")
    if len(data) > MAX_EVIDENCE_BYTES:
        return jsonify({"success": False, "message": "File exceeds 10MB limit"}), 413
    if not content_type_allowed(content_type):
        return _bad_request(
            "Unsupported content type",
            {"allowed": sorted(ALLOWED_CONTENT_TYPES)},
        )

    evidence_id = str(uuid.uuid4())
    storage_key = f"{user_id}/{obligation_id}/{evidence_id}_{filename}"
    stored = blob_store.put_bytes(storage_key, data, content_type)
    evidence = store.add_evidence(
        user_id,
        obligation_id,
        filename=filename,
        content_type=content_type.split(";")[0].strip().lower(),
        size_bytes=len(data),
        storage_key=stored["storageKey"],
        url=stored.get("url"),
    )
    return jsonify({
        "success": True,
        "evidence": evidence,
        "backend": stored.get("backend"),
    }), 201


@bp.get("/obligations/<obligation_id>/evidence")
@require_user
def list_evidence(obligation_id):
    item = store.get_obligation(request.compliance_user_id, obligation_id)
    if not item:
        return jsonify({"success": False, "message": "Obligation not found"}), 404
    return jsonify({"success": True, "evidence": item.get("evidence") or []})


@bp.get("/obligations/<obligation_id>/evidence/<evidence_id>/download")
@require_user
def download_evidence(obligation_id, evidence_id):
    item = store.get_evidence(request.compliance_user_id, obligation_id, evidence_id)
    if not item:
        return jsonify({"success": False, "message": "Evidence not found"}), 404
    data = blob_store.get_bytes(item["storageKey"])
    if data is None:
        signed = blob_store.sign_url(item["storageKey"])
        if signed:
            return jsonify({"success": True, "url": signed, "evidence": item})
        return jsonify({"success": False, "message": "Evidence bytes not found"}), 404
    return send_file(
        BytesIO(data),
        mimetype=item.get("contentType") or "application/octet-stream",
        as_attachment=True,
        download_name=item.get("filename") or "evidence",
    )


@bp.get("/reminders")
@require_user
def list_reminders():
    items = store.list_reminders(
        request.compliance_user_id,
        obligation_id=request.args.get("obligationId") or request.args.get("obligation_id"),
        status=request.args.get("status"),
    )
    return jsonify({"success": True, "reminders": items, "count": len(items)})


@bp.post("/reminders/dispatch")
@require_cron
def dispatch_reminders():
    """Process pending stubs whose scheduledFor is today or earlier.

    Email is stubbed (see compliance/email_stub.py). Call from Render cron
    with X-Cron-Secret, same pattern as /api/benchmarks/update.
    """
    body = _json() if request.is_json else {}
    as_of = _as_of_from_request()
    if as_of is None and (body.get("asOf") or body.get("as_of")):
        try:
            as_of = date.fromisoformat(str(body.get("asOf") or body.get("as_of"))[:10])
        except ValueError:
            return _bad_request("asOf must be YYYY-MM-DD")

    due = store.due_reminders(as_of=as_of)
    dispatched = []
    for rem in due:
        obligation = rem.get("obligation") or {}
        result = send_reminder_email(
            user_id=rem.get("userId") or "",
            obligation=obligation,
            reminder=rem,
        )
        new_status = "sent" if result.get("ok") else "failed"
        updated = store.mark_reminder(
            rem["id"],
            status=new_status,
            last_error=None if result.get("ok") else result.get("message"),
        )
        dispatched.append({
            "id": rem["id"],
            "status": new_status,
            "stubbed": bool(result.get("stubbed")),
            "offsetCode": rem.get("offsetCode"),
            "obligationId": rem.get("obligationId"),
            "email": updated,
        })
    return jsonify({
        "success": True,
        "asOf": (as_of or date.today()).isoformat(),
        "due": len(due),
        "dispatched": dispatched,
        "note": (
            "Email delivery is stubbed. TODO: wire Brevo in "
            "compliance/email_stub.py before enabling tenant-facing reminders."
        ),
    })


def register_compliance(app, limiter=None):
    """Attach the blueprint to the Flask app.

    ``limiter`` is accepted for call-site compatibility with app.py.
    Per-IP defaults already applied by Flask-Limiter on the parent app
    (50/hour, 200/day) cover these routes; we do not wrap the shared
    blueprint object so unit tests can register it on a mini Flask app.
    """
    app.register_blueprint(bp)
    return bp
