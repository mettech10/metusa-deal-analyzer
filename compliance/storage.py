"""Evidence blob storage.

Uses Supabase Storage when configured (bucket ``compliance-evidence``).
Falls back to local ``uploads/compliance/`` — the same uploads/ tree the
repo already gitignores — so tests and local MVP work without a bucket.
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger("compliance.storage")

BUCKET = "compliance-evidence"
MAX_EVIDENCE_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = frozenset({
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/jpg",
})

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")

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

_LOCAL_ROOT = Path(
    os.environ.get("COMPLIANCE_UPLOAD_DIR")
    or (Path(__file__).resolve().parent.parent / "uploads" / "compliance")
)

# In-process blob fallback used by tests / when disk is unavailable.
_MEMORY_BLOBS: dict[str, bytes] = {}


def sanitize_filename(name: str) -> str:
    base = os.path.basename(name or "evidence")
    cleaned = _SAFE_NAME.sub("_", base).strip("._")
    return (cleaned or "evidence")[:180]


def content_type_allowed(content_type: str) -> bool:
    ct = (content_type or "").split(";")[0].strip().lower()
    return ct in ALLOWED_CONTENT_TYPES


def _sb_configured() -> bool:
    return bool(_SUPABASE_URL and _SUPABASE_KEY)


def storage_backend() -> str:
    return "supabase" if _sb_configured() else "local"


def put_bytes(storage_key: str, data: bytes, content_type: str) -> dict:
    """Persist evidence bytes. Returns {backend, storageKey, url?}."""
    if _sb_configured():
        url = f"{_SUPABASE_URL}/storage/v1/object/{BUCKET}/{storage_key}"
        try:
            resp = requests.post(
                url,
                data=data,
                headers={
                    "Authorization": f"Bearer {_SUPABASE_KEY}",
                    "apikey": _SUPABASE_KEY,
                    "Content-Type": content_type.split(";")[0].strip(),
                    "x-upsert": "true",
                },
                timeout=30,
            )
            if resp.status_code in (200, 201):
                signed = sign_url(storage_key)
                return {
                    "backend": "supabase",
                    "storageKey": storage_key,
                    "url": signed,
                    "bucket": BUCKET,
                }
            logger.warning(
                "[compliance] supabase upload failed %s: %s",
                resp.status_code, resp.text[:300],
            )
        except requests.RequestException as exc:
            logger.warning("[compliance] supabase upload error: %s", exc)

    return _put_local(storage_key, data)


def _put_local(storage_key: str, data: bytes) -> dict:
    _MEMORY_BLOBS[storage_key] = data
    try:
        path = _LOCAL_ROOT / storage_key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError as exc:
        logger.warning("[compliance] local upload write failed: %s", exc)
    return {
        "backend": "local",
        "storageKey": storage_key,
        "url": None,
        "bucket": None,
    }


def get_bytes(storage_key: str) -> Optional[bytes]:
    if storage_key in _MEMORY_BLOBS:
        return _MEMORY_BLOBS[storage_key]
    path = _LOCAL_ROOT / storage_key
    if path.is_file():
        return path.read_bytes()
    if not _sb_configured():
        return None
    try:
        resp = requests.get(
            f"{_SUPABASE_URL}/storage/v1/object/{BUCKET}/{storage_key}",
            headers={
                "Authorization": f"Bearer {_SUPABASE_KEY}",
                "apikey": _SUPABASE_KEY,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.content
    except requests.RequestException as exc:
        logger.warning("[compliance] supabase download error: %s", exc)
    return None


def sign_url(storage_key: str, expires_in: int = 3600) -> Optional[str]:
    if not _sb_configured():
        return None
    try:
        resp = requests.post(
            f"{_SUPABASE_URL}/storage/v1/object/sign/{BUCKET}/{storage_key}",
            json={"expiresIn": expires_in},
            headers={
                "Authorization": f"Bearer {_SUPABASE_KEY}",
                "apikey": _SUPABASE_KEY,
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            signed = resp.json().get("signedURL") or resp.json().get("signedUrl")
            if signed:
                if signed.startswith("http"):
                    return signed
                return f"{_SUPABASE_URL}/storage/v1{signed}"
    except requests.RequestException as exc:
        logger.warning("[compliance] supabase sign error: %s", exc)
    return None


def reset_memory_blobs() -> None:
    _MEMORY_BLOBS.clear()
