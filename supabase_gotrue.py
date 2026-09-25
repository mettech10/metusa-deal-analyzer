"""Shared GoTrue user lookup for Flask user-JWT routes.

Compliance and MTD both call ``GET {SUPABASE_URL}/auth/v1/user``.
``/v1/deals`` already uses the **service role** as ``apikey``. Live QA
(compliance 401 ``Invalid or expired token`` + MTD 401 ``Unauthorised``)
happened because those two paths used only the anon key — or, when it
was missing, no apikey (MTD) / the user token as apikey (compliance).
GoTrue rejects both. Never send the caller JWT as ``apikey``.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import requests

GOTRUE_PATH = "/auth/v1/user"


class GotrueAuthError(Exception):
    """Raised when GoTrue cannot be called or rejects the caller."""

    def __init__(self, status: int, message: str, *, code: str = ""):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code


def supabase_url() -> str:
    return (
        os.environ.get("SUPABASE_URL")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        or ""
    ).rstrip("/")


def auth_apikey() -> tuple[str, str]:
    """Return (apikey, source). Same precedence as deals_api._supabase_config.

    source is ``service`` | ``anon`` | ``none``. The user access token is
    never a valid source.
    """
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


def supabase_host() -> str:
    """Hostname only — safe to expose on /health. Empty if URL unset."""
    raw = supabase_url()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    return (parsed.hostname or "").lower()


def auth_readiness() -> dict[str, Any]:
    """Non-secret flags for /v1/compliance/health and /v1/mtd/health."""
    url = supabase_url()
    _key, source = auth_apikey()
    host = supabase_host()
    return {
        "ready": bool(url and _key),
        "gotrue": GOTRUE_PATH,
        "apikeySource": source,
        "supabaseHost": host,
        "note": (
            "ready means SUPABASE_URL plus a service/anon apikey are set — "
            "not that a given user JWT is valid. apikeySource should be "
            "'service' (same as /v1/deals). 'anon' works only if it is the "
            "project's anon key, not the JWT secret. 'none' means Render is "
            "missing SUPABASE_SERVICE_KEY / SUPABASE_ANON_KEY. supabaseHost "
            "must match the browser cookie project (sb-<ref>-auth-token)."
        ),
    }


def fetch_gotrue_user(access_token: str) -> dict[str, Any]:
    """GET /auth/v1/user. Returns the GoTrue user JSON (must include ``id``).

    Raises GotrueAuthError:
      503 — URL or apikey missing, or GoTrue unreachable
      401 — Bearer present but GoTrue rejected it
    """
    token = (access_token or "").strip()
    if not token:
        raise GotrueAuthError(
            401,
            "Unauthorised",
            code="missing_bearer",
        )

    url = supabase_url()
    if not url:
        raise GotrueAuthError(
            503,
            "auth not configured (missing SUPABASE_URL)",
            code="auth_not_configured",
        )

    apikey, source = auth_apikey()
    if not apikey:
        raise GotrueAuthError(
            503,
            "auth not configured (missing anon key)",
            code="auth_not_configured",
        )

    try:
        resp = requests.get(
            f"{url}{GOTRUE_PATH}",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": apikey,
            },
            timeout=8,
        )
    except requests.RequestException as exc:
        raise GotrueAuthError(
            503,
            "auth service unavailable",
            code="auth_unavailable",
        ) from exc

    host = supabase_host()
    if resp.status_code != 200:
        raise GotrueAuthError(
            401,
            (
                "Unauthorised. Flask GET {SUPABASE_URL}/auth/v1/user "
                f"returned HTTP {resp.status_code} (apikey={source}, "
                f"host={host or 'unset'}). Render SUPABASE_URL must be the "
                "same project as the browser cookie sb-<ref>-auth-token. "
                "Set SUPABASE_SERVICE_KEY (service role, same as /v1/deals). "
                "Never put the user JWT or JWT secret in SUPABASE_ANON_KEY."
            ),
            code="gotrue_rejected",
        )

    try:
        payload = resp.json()
    except ValueError as exc:
        raise GotrueAuthError(
            401,
            "Unauthorised",
            code="gotrue_invalid_body",
        ) from exc

    if not isinstance(payload, dict) or not payload.get("id"):
        raise GotrueAuthError(
            401,
            "Unauthorised",
            code="gotrue_missing_user",
        )
    return payload
