"""Auth for Compliance Cockpit APIs.

Matches existing user-data APIs (portfolio / saved analyses): a Supabase
user JWT in ``Authorization: Bearer <access_token>``.

Flask analysis endpoints are intentionally public + rate-limited; these
routes persist landlord documents so they require the same identity check
the Next.js BFF uses via ``supabase.auth.getUser()``.

Testing (``FLASK_ENV=testing`` or Flask ``TESTING``): pass ``X-User-Id``.
Cron dispatch: ``X-Cron-Secret`` matching ``COMPLIANCE_CRON_SECRET`` or
``BENCHMARK_CRON_SECRET`` (same pattern as ``/api/benchmarks/update``).
"""

import os
from functools import wraps

import requests
from flask import current_app, jsonify, request

_SUPABASE_URL = (
    os.environ.get("SUPABASE_URL")
    or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    or ""
).rstrip("/")
_SUPABASE_ANON = (
    os.environ.get("SUPABASE_ANON_KEY")
    or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    or ""
)


def is_testing() -> bool:
    env = os.environ.get("FLASK_ENV", "").lower()
    if env in ("testing", "test"):
        return True
    try:
        return bool(current_app.config.get("TESTING"))
    except RuntimeError:
        return False


def cron_secret() -> str:
    return (
        os.environ.get("COMPLIANCE_CRON_SECRET")
        or os.environ.get("BENCHMARK_CRON_SECRET")
        or ""
    )


def _unauthorized(message: str = "Unauthorized"):
    return jsonify({"success": False, "message": message}), 401


def resolve_user_id() -> tuple[str | None, tuple | None]:
    """Return (user_id, error_response). error_response is a Flask (json, status)."""
    if is_testing():
        user_id = (request.headers.get("X-User-Id") or "").strip()
        if not user_id:
            return None, _unauthorized("X-User-Id required in testing")
        return user_id, None

    header = request.headers.get("Authorization") or ""
    if not header.startswith("Bearer "):
        return None, _unauthorized("Authorization Bearer token required")
    token = header[7:].strip()
    if not token:
        return None, _unauthorized("Authorization Bearer token required")

    if not _SUPABASE_URL:
        return None, (
            jsonify({
                "success": False,
                "message": "Auth is not configured (missing SUPABASE_URL)",
            }),
            503,
        )

    try:
        resp = requests.get(
            f"{_SUPABASE_URL}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": _SUPABASE_ANON or token,
            },
            timeout=8,
        )
    except requests.RequestException:
        return None, (
            jsonify({"success": False, "message": "Auth service unavailable"}),
            503,
        )

    if resp.status_code != 200:
        return None, _unauthorized("Invalid or expired token")

    try:
        payload = resp.json()
    except ValueError:
        return None, _unauthorized("Invalid or expired token")

    user_id = payload.get("id")
    if not user_id:
        return None, _unauthorized("Invalid or expired token")
    return str(user_id), None


def require_user(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        user_id, err = resolve_user_id()
        if err is not None:
            return err
        request.compliance_user_id = user_id
        return f(*args, **kwargs)
    return wrapped


def require_cron(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        secret = cron_secret()
        provided = request.headers.get("X-Cron-Secret", "")
        if is_testing() and provided and (not secret or provided == secret):
            return f(*args, **kwargs)
        if not secret or provided != secret:
            return _unauthorized("Unauthorized")
        return f(*args, **kwargs)
    return wrapped
