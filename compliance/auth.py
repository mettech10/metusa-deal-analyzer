"""Auth for Compliance Cockpit APIs.

Matches ``/v1/deals`` (deals_api.fetch_supabase_user): validate the
caller's Supabase *access* JWT via ``GET {SUPABASE_URL}/auth/v1/user``
with the **service role** as ``apikey`` (then anon). Never send the
user token as apikey.

Live QA: using only ``SUPABASE_ANON_KEY`` (or the user token itself
as apikey) made GoTrue return 401 ``Invalid or expired token`` for a
freshly signed-in user whose JWT /v1/deals would accept. Missing
URL/apikey is now 503 ``auth not configured`` instead of an
ambiguous 401.
"""

from functools import wraps

from flask import jsonify, request

from supabase_gotrue import (
    GotrueAuthError,
    auth_apikey as _auth_apikey,
    fetch_gotrue_user,
)

# Re-export for health + existing tests.
__all__ = [
    "cron_secret",
    "is_testing",
    "require_cron",
    "require_user",
    "resolve_user_id",
    "_auth_apikey",
]


def is_testing() -> bool:
    import os

    from flask import current_app

    env = os.environ.get("FLASK_ENV", "").lower()
    if env in ("testing", "test"):
        return True
    try:
        return bool(current_app.config.get("TESTING"))
    except RuntimeError:
        return False


def cron_secret() -> str:
    import os

    return (
        os.environ.get("COMPLIANCE_CRON_SECRET")
        or os.environ.get("BENCHMARK_CRON_SECRET")
        or ""
    )


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

    try:
        payload = fetch_gotrue_user(token)
    except GotrueAuthError as exc:
        body = {"success": False, "message": exc.message, "code": exc.code}
        return None, (jsonify(body), exc.status)

    return str(payload["id"]), None


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
