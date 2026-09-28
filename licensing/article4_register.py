"""Verified Article 4 register (Supabase ``article4_areas``).

The register is council-checked and refreshed monthly by the frontend
cron (dealcheck-uk /api/cron/article4-update). It is keyed by ONS council
code and lists the postcode districts each HMO Article 4 direction covers.
District-level only: it is never treated as an address-level boundary.

This replaces the legacy district fallback, which asked an LLM for the
Article 4 status and presented the answer as an "in-repo index".
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable, Optional

import requests

logger = logging.getLogger("licensing.article4_register")

_CACHE_TTL_SECONDS = 6 * 60 * 60
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_lock = threading.Lock()

_SELECT = (
    "council_name,council_code,status,direction_type,verified,last_verified_at,"
    "postcode_districts,effective_date,council_planning_url,source_document_url,"
    "planning_portal_url"
)


def _config() -> tuple[str, str] | None:
    if os.environ.get("FLASK_ENV", "").lower() in ("testing", "test"):
        return None
    url = (os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    return (url, key) if url and key else None


def _fetch_rows(la_code: str) -> list[dict[str, Any]]:
    cfg = _config()
    if not cfg:
        return []
    url, key = cfg
    resp = requests.get(
        f"{url}/rest/v1/article4_areas",
        params={"council_code": f"eq.{la_code}", "select": _SELECT},
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=6,
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows if isinstance(rows, list) else []


def _rows_for(la_code: str, fetch_rows: Callable[[str], list[dict[str, Any]]]) -> list[dict[str, Any]]:
    now = time.monotonic()
    with _lock:
        hit = _cache.get(la_code)
        if hit and now - hit[0] < _CACHE_TTL_SECONDS:
            return hit[1]
    rows = fetch_rows(la_code)
    with _lock:
        _cache[la_code] = (now, rows)
    return rows


def outward_code(postcode: str) -> str:
    text = (postcode or "").strip().upper()
    if " " in text:
        return text.split()[0]
    return text[:-3] if len(text) > 3 else text


def lookup_verified_article4(
    postcode: str,
    la_code: Optional[str],
    *,
    fetch_rows: Callable[[str], list[dict[str, Any]]] | None = None,
) -> Optional[dict[str, Any]]:
    """District-level Article 4 status from the verified register, or None
    when the council is not in the register (callers fall back)."""
    if not la_code:
        return None
    try:
        # Only the real network fetch is cached; injected fetchers (tests) are not.
        rows = fetch_rows(la_code) if fetch_rows else _rows_for(la_code, _fetch_rows)
    except Exception as exc:  # register outage must never break the checker
        logger.warning("article4 register lookup failed for %s: %s", la_code, exc)
        return None
    hmo_rows = [r for r in rows if "hmo" in str(r.get("direction_type") or "").lower() or "c4" in str(r.get("direction_type") or "").lower()]
    if not hmo_rows:
        return None
    district = outward_code(postcode)
    listed = [r for r in hmo_rows if district in (r.get("postcode_districts") or [])]
    row = listed[0] if listed else hmo_rows[0]
    status = str(row.get("status") or "unknown").lower()
    return {
        "source": "verified_register",
        "known": True,
        "status": status,
        "is_article_4": status == "active" and bool(listed),
        "district": district,
        "district_listed": bool(listed),
        "council": row.get("council_name"),
        "verified": bool(row.get("verified")),
        "last_verified_at": row.get("last_verified_at"),
        "effective_date": row.get("effective_date"),
        "url": row.get("council_planning_url") or row.get("source_document_url") or row.get("planning_portal_url"),
        "districts": list(row.get("postcode_districts") or []),
    }
