"""Auth for Compliance Cockpit APIs.

Matches ``/v1/deals`` (deals_api.fetch_supabase_user): validate the
caller's Supabase *access* JWT via ``GET {SUPABASE_URL}/auth/v1/user``
with the **service role** as ``apikey`` (then anon).

Live QA r3: using only ``SUPABASE_ANON_KEY`` (or the user token itself
as apikey) made GoTrue return 401 ``Invalid or expired token`` for a
freshly signed-in user whose JWT /v1/deals would accept. Do not set
``SUPABASE_ANON_KEY`` to the JWT secret — that is not an apikey.
"""

import os
from functools import wraps

import requests
from flask import current_app, jsonify, request


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


def _supabase_url() -> str:
    return (
        os.environ.get("SUPABASE_URL")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        or ""
    ).rstrip("/")


def _auth_apikey() -> tuple[str, str]:
    """Return (apikey, source). Same precedence as deals_api._supabase_config."""
    service = (
        os.environ.get("SUPABASE_SERVICE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    ).strip()
    if service:
        return service, "service"
    anon = (
        os.environ.get("SUPABASE_ANON_KEY")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        or ""
    ).strip()
    if anon:
        return anon, "anon"
    return "", "none"


def _unauthorized(message: str = "Unauthorized"):
    return jsonify({"success": False, "message": message}), 401


def _bearer_token() -> str | None:
    header = request.headers.get("Authorization") or ""
    if not header.lower().startswith("bearer "):
        return None
    token = header[7:].strip()
    return token or None


def resolve_user_id() -> tuple[str | None, tuple | None]:
    """Return (user_id, error_response). error_response is a Flask (json, status)."""
    if is_testing():
        user_id = (request.headers.get("X-User-Id") or "").strip()
        if not user_id:
            return None, _unauthorized("X-User-Id required in testing")
        return user_id, None

    token = _bearer_token()
    if not token:
        return None, _unauthorized("Authorization Bearer token required")

    url = _supabase_url()
    if not url:
        return None, (
            jsonify({
                "success": False,
                "message": "Auth is not configured (missing SUPABASE_URL)",
            }),
            503,
        )

    apikey, source = _auth_apikey()
    if not apikey:
        return None, (
            jsonify({
                "success": False,
                "message": (
                    "Auth is not configured (missing SUPABASE_SERVICE_KEY / "
                    "SUPABASE_ANON_KEY). Use the service role, same as /v1/deals — "
                    "not the JWT secret."
                ),
            }),
            503,
        )

    try:
        resp = requests.get(
            f"{url}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": apikey,
            },
            timeout=8,
        )
    except requests.RequestException:
        return None, (
            jsonify({"success": False, "message": "Auth service unavailable"}),
            503,
        )

    if resp.status_code != 200:
        return None, _unauthorized(
            "Invalid or expired token. Flask GET {SUPABASE_URL}/auth/v1/user "
            f"returned HTTP {resp.status_code} (apikey={source}). "
            "Render SUPABASE_URL must be the same project as Vercel "
            "NEXT_PUBLIC_SUPABASE_URL. Set SUPABASE_SERVICE_KEY (service role, "
            "same as /v1/deals). Do not put the JWT secret in SUPABASE_ANON_KEY."
        )

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
