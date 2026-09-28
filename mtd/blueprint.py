"""Flask blueprint: /v1/mtd/*  (MTD Pack v1, no HMRC submit)."""

from __future__ import annotations

import os
from typing import Any

from flask import Blueprint, current_app, jsonify, request, send_file
import io

from mtd.categories import CATEGORIES, load_catalogue
from mtd.open_banking import OpenBankingNotAvailable
from mtd.packs import DISCLAIMER
from mtd.service import MtdService
from mtd.store import Conflict, InMemoryMtdStore, MtdStoreError, NotFound
from mtd.supabase_store import SupabaseMtdStore, supabase_store_configured
from supabase_gotrue import (
    GotrueAuthError,
    auth_readiness,
    fetch_gotrue_user,
)

mtd_bp = Blueprint("mtd", __name__, url_prefix="/v1/mtd")

_STORAGE_UNAVAILABLE = (
    "MTD storage is not configured on this server, so records would not be "
    "saved. Nothing was changed. Set SUPABASE_URL and SUPABASE_SERVICE_KEY."
)


def configure_mtd(app) -> MtdService:
    """Attach the MTD service. Supabase when configured, else in-memory.

    Tests (and local dev) inject ``MTD_SERVICE`` or run without Supabase env.
    """
    service = app.config.get("MTD_SERVICE")
    if service is None:
        store = SupabaseMtdStore() if supabase_store_configured() else InMemoryMtdStore()
        service = MtdService(store)
        app.config["MTD_SERVICE"] = service
    return service


@mtd_bp.errorhandler(MtdStoreError)
def _store_unavailable(exc: MtdStoreError):
    return jsonify({"error": str(exc), "code": "storage_unavailable"}), 503


def _store_backend() -> str:
    return getattr(_service().store, "backend", "memory")


def _memory_store_refused() -> bool:
    """In-memory records vanish on restart. Only dev/test may use them."""
    if _store_backend() != "memory":
        return False
    if current_app.config.get("TESTING") or current_app.config.get("MTD_ALLOW_MEMORY_STORE"):
        return False
    if os.environ.get("MTD_ALLOW_MEMORY_STORE") == "1":
        return False
    return os.environ.get("FLASK_ENV", "").lower() not in ("development", "testing", "test")


def _service() -> MtdService:
    return current_app.config["MTD_SERVICE"]


def _json() -> dict[str, Any]:
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("JSON object required")
    return data


def _csv_body() -> tuple[str, str]:
    if request.files:
        upload = request.files.get("file") or next(iter(request.files.values()), None)
        if upload:
            raw = upload.read()
            text = raw.decode("utf-8-sig")
            return text, upload.filename or "import.csv"
    if request.mimetype and "text/csv" in request.mimetype:
        return request.get_data(as_text=True), "import.csv"
    body = _json()
    text = body.get("csv") or body.get("content") or body.get("text")
    if not text:
        raise ValueError("csv is required (JSON {csv} or multipart file)")
    return str(text), str(body.get("filename") or "import.csv")


def _testing() -> bool:
    return bool(
        current_app.config.get("TESTING")
        or os.environ.get("FLASK_ENV") == "testing"
    )


def _resolve_ctx():
    svc = _service()
    org_hint = (
        request.headers.get("X-Org-Id")
        or request.headers.get("X-Mtd-Org-Id")
        or request.args.get("orgId")
    )
    user_id = request.headers.get("X-Mtd-User-Id")
    email = request.headers.get("X-Mtd-User-Email")
    auth = request.headers.get("Authorization") or ""
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else None

    if _testing() and user_id:
        return svc.ensure_org(user_id, email=email, org_id=org_hint or None)

    if token:
        if _testing():
            try:
                user = _supabase_user(token)
            except GotrueAuthError:
                user = None
        else:
            user = _supabase_user(token)
        if user:
            return svc.ensure_org(
                user["id"],
                email=user.get("email"),
                org_id=org_hint or None,
            )

    if _testing() and token:
        return svc.ensure_org(token, org_id=org_hint or None)

    return None


def _supabase_user(token: str) -> dict[str, Any] | None:
    """Validate the Bearer via shared GoTrue helper.

    Raises GotrueAuthError (503 if URL/apikey missing, 401 if rejected).
    Returns None only when the helper is skipped (empty token).
    """
    if not token:
        return None
    return fetch_gotrue_user(token)


def _auth():
    if _memory_store_refused():
        return None, (jsonify({"error": _STORAGE_UNAVAILABLE, "code": "storage_unavailable"}), 503)
    try:
        ctx = _resolve_ctx()
    except PermissionError as exc:
        return None, (jsonify({"error": str(exc)}), 403)
    except GotrueAuthError as exc:
        body = {"error": exc.message, "code": exc.code}
        return None, (jsonify(body), exc.status)
    except MtdStoreError as exc:
        return None, (jsonify({"error": str(exc), "code": "storage_unavailable"}), 503)
    if ctx is None:
        return None, (jsonify({"error": "Unauthorised"}), 401)
    return ctx, None


def _err(exc: Exception):
    if isinstance(exc, MtdStoreError):
        return jsonify({"error": str(exc), "code": "storage_unavailable"}), 503
    if isinstance(exc, NotFound):
        return jsonify({"error": str(exc)}), 404
    if isinstance(exc, Conflict):
        return jsonify({"error": str(exc)}), 409
    if isinstance(exc, PermissionError):
        return jsonify({"error": str(exc)}), 403
    if isinstance(exc, ValueError):
        return jsonify({"error": str(exc)}), 400
    if isinstance(exc, OpenBankingNotAvailable):
        return jsonify({"error": str(exc), "code": "open_banking_unavailable"}), 501
    if current_app.config.get("TESTING"):
        return jsonify({"error": str(exc), "type": type(exc).__name__}), 500
    return jsonify({"error": "Internal server error"}), 500


@mtd_bp.get("/health")
def health():
    store = _service().store
    backend = _store_backend()
    probe = store.probe() if hasattr(store, "probe") else {"backend": backend, "ready": True, "tables": "n/a"}
    refused = _memory_store_refused()
    return jsonify(
        {
            "status": "ok" if probe.get("ready") and not refused else "degraded",
            "pack": "mtd-v1",
            "hmrcSubmit": False,
            "openBanking": False,
            "disclaimer": DISCLAIMER,
            "auth": auth_readiness(),
            "store": backend,
            "persistent": backend == "supabase",
            "storeProbe": probe,
            "writesAccepted": bool(probe.get("ready")) and not refused,
        }
    )


@mtd_bp.get("/categories")
def categories():
    cat = load_catalogue()
    return jsonify(
        {
            "version": cat.get("version"),
            "alignment": cat.get("alignment"),
            "notes": cat.get("notes"),
            "categories": CATEGORIES,
        }
    )


@mtd_bp.get("/orgs")
def list_orgs():
    ctx, err = _auth()
    if err:
        return err
    return jsonify({"orgs": _service().list_orgs(ctx)})


@mtd_bp.post("/orgs")
def create_org():
    ctx, err = _auth()
    if err:
        return err
    try:
        return jsonify(_service().create_org(ctx, _json())), 201
    except Exception as exc:
        return _err(exc)


@mtd_bp.get("/orgs/current")
def current_org():
    ctx, err = _auth()
    if err:
        return err
    try:
        return jsonify(_service().current_org(ctx))
    except Exception as exc:
        return _err(exc)


@mtd_bp.post("/orgs/current/members")
def add_member():
    ctx, err = _auth()
    if err:
        return err
    try:
        return jsonify(_service().add_member(ctx, _json())), 201
    except Exception as exc:
        return _err(exc)


@mtd_bp.get("/businesses")
def list_businesses():
    ctx, err = _auth()
    if err:
        return err
    return jsonify({"businesses": _service().list_businesses(ctx)})


@mtd_bp.post("/businesses")
def create_business():
    ctx, err = _auth()
    if err:
        return err
    try:
        return jsonify(_service().create_business(ctx, _json())), 201
    except Exception as exc:
        return _err(exc)


@mtd_bp.get("/businesses/<business_id>")
def get_business(business_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        return jsonify(_service().get_business(ctx, business_id))
    except Exception as exc:
        return _err(exc)


@mtd_bp.patch("/businesses/<business_id>")
def update_business(business_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        return jsonify(_service().update_business(ctx, business_id, _json()))
    except Exception as exc:
        return _err(exc)


@mtd_bp.delete("/businesses/<business_id>")
def delete_business(business_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        _service().delete_business(ctx, business_id)
        return jsonify({"ok": True})
    except Exception as exc:
        return _err(exc)


@mtd_bp.get("/businesses/<business_id>/properties")
def list_properties(business_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        return jsonify({"properties": _service().list_properties(ctx, business_id)})
    except Exception as exc:
        return _err(exc)


@mtd_bp.post("/businesses/<business_id>/properties")
def create_property(business_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        return jsonify(_service().create_property(ctx, business_id, _json())), 201
    except Exception as exc:
        return _err(exc)


@mtd_bp.get("/properties/<property_id>")
def get_property(property_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        return jsonify(_service().get_property(ctx, property_id))
    except Exception as exc:
        return _err(exc)


@mtd_bp.patch("/properties/<property_id>")
def update_property(property_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        return jsonify(_service().update_property(ctx, property_id, _json()))
    except Exception as exc:
        return _err(exc)


@mtd_bp.delete("/properties/<property_id>")
def delete_property(property_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        _service().delete_property(ctx, property_id)
        return jsonify({"ok": True})
    except Exception as exc:
        return _err(exc)


@mtd_bp.get("/businesses/<business_id>/ledger")
def list_ledger(business_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        return jsonify({"entries": _service().list_ledger(ctx, business_id)})
    except Exception as exc:
        return _err(exc)


@mtd_bp.post("/businesses/<business_id>/ledger")
def create_ledger(business_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        return jsonify(_service().create_entry(ctx, business_id, _json())), 201
    except Exception as exc:
        return _err(exc)


@mtd_bp.get("/ledger/<entry_id>")
def get_ledger(entry_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        return jsonify(_service().get_entry(ctx, entry_id))
    except Exception as exc:
        return _err(exc)


@mtd_bp.patch("/ledger/<entry_id>")
def update_ledger(entry_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        return jsonify(_service().update_entry(ctx, entry_id, _json()))
    except Exception as exc:
        return _err(exc)


@mtd_bp.delete("/ledger/<entry_id>")
def delete_ledger(entry_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        _service().delete_entry(ctx, entry_id)
        return jsonify({"ok": True})
    except Exception as exc:
        return _err(exc)


@mtd_bp.post("/businesses/<business_id>/imports/preview")
def preview_import(business_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        text, _name = _csv_body()
        return jsonify(_service().preview_import(ctx, business_id, text))
    except Exception as exc:
        return _err(exc)


@mtd_bp.post("/businesses/<business_id>/imports/commit")
def commit_import(business_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        text, filename = _csv_body()
        result = _service().commit_import(ctx, business_id, text, filename)
        status = 200 if result.get("idempotent") else 201
        return jsonify(result), status
    except Exception as exc:
        return _err(exc)


@mtd_bp.get("/businesses/<business_id>/packs")
def list_packs(business_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        return jsonify({"packs": _service().list_packs(ctx, business_id)})
    except Exception as exc:
        return _err(exc)


@mtd_bp.post("/businesses/<business_id>/packs")
def create_pack(business_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        return jsonify(_service().create_pack(ctx, business_id, _json())), 201
    except Exception as exc:
        return _err(exc)


@mtd_bp.get("/packs/<pack_id>")
def get_pack(pack_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        return jsonify(_service().get_pack(ctx, pack_id))
    except Exception as exc:
        return _err(exc)


def _send_export(pack_id: str, fmt: str, ctx=None, pack=None):
    svc = _service()
    if pack is not None:
        data, mime, filename = svc.export_pack_public(pack, fmt)
    else:
        data, mime, filename = svc.export_pack(ctx, pack_id, fmt)
    return send_file(
        io.BytesIO(data),
        mimetype=mime,
        as_attachment=True,
        download_name=filename,
    )


@mtd_bp.get("/packs/<pack_id>/export.json")
def export_json(pack_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        return _send_export(pack_id, "json", ctx=ctx)
    except Exception as exc:
        return _err(exc)


@mtd_bp.get("/packs/<pack_id>/export.csv")
def export_csv(pack_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        return _send_export(pack_id, "csv", ctx=ctx)
    except Exception as exc:
        return _err(exc)


@mtd_bp.get("/packs/<pack_id>/export.pdf")
def export_pdf(pack_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        return _send_export(pack_id, "pdf", ctx=ctx)
    except Exception as exc:
        return _err(exc)


@mtd_bp.post("/packs/<pack_id>/share")
def create_share(pack_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        return jsonify(_service().create_share(ctx, pack_id, _json())), 201
    except Exception as exc:
        return _err(exc)


@mtd_bp.get("/share/<token>")
def read_share(token: str):
    try:
        pack = _service().resolve_share(token)
        fmt = (request.args.get("format") or "json").lower()
        if fmt in ("csv", "pdf"):
            return _send_export(pack.id, fmt, pack=pack)
        return jsonify(
            {
                "readonly": True,
                "immutable": True,
                "hmrcSubmit": False,
                "pack": _service()._pack_summary(pack, include_snapshot=True),
            }
        )
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 410
    except Exception as exc:
        return _err(exc)


@mtd_bp.delete("/share-links/<share_id>")
def revoke_share(share_id: str):
    ctx, err = _auth()
    if err:
        return err
    try:
        _service().revoke_share(ctx, share_id)
        return jsonify({"ok": True})
    except Exception as exc:
        return _err(exc)


@mtd_bp.get("/open-banking/status")
def open_banking_status():
    ctx, err = _auth()
    if err:
        return err
    return jsonify(_service().open_banking_status())


@mtd_bp.post("/open-banking/sync")
def open_banking_sync():
    ctx, err = _auth()
    if err:
        return err
    try:
        body = _json()
        business_id = (
            body.get("businessId") or body.get("business_id") or request.args.get("businessId") or ""
        )
        if not business_id:
            return jsonify({"error": "businessId is required"}), 400
        _service().open_banking_sync(ctx, business_id)
        return jsonify({"ok": True})
    except Exception as exc:
        return _err(exc)
