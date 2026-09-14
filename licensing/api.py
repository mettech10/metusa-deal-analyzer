"""Flask handlers for /v1/licensing/*."""

from __future__ import annotations

from flask import jsonify, request

from licensing.engine import run_licensing_check
from licensing.geo import GeoError
from licensing.schemes import seed_inventory


def handle_check(district_fallback=None):
    if not request.is_json:
        return jsonify({
            "ok": False,
            "error": {"code": "invalid_content_type", "message": "Content-Type must be application/json"},
        }), 400

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({
            "ok": False,
            "error": {"code": "invalid_json", "message": "Request body must be a JSON object"},
        }), 400

    if len(str(payload)) > 10000:
        return jsonify({
            "ok": False,
            "error": {"code": "payload_too_large", "message": "Request too large"},
        }), 413

    try:
        result = run_licensing_check(payload, district_fallback=district_fallback)
    except GeoError as exc:
        return jsonify({
            "ok": False,
            "error": {"code": exc.code, "message": str(exc)},
        }), exc.http_status
    except Exception:
        return jsonify({
            "ok": False,
            "error": {
                "code": "internal_error",
                "message": "Licensing check failed. Please retry.",
            },
        }), 500

    return jsonify(result), 200


def handle_seed_inventory():
    """Curator helper — list seeded LAs. Not a substitute for /check."""
    return jsonify({"ok": True, **seed_inventory()}), 200
