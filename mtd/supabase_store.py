"""Supabase (PostgREST) MTD store — the production backend for /v1/mtd.

Same interface as ``InMemoryMtdStore``. Rows live in the ``mtd_*`` tables
from ``supabase/migrations/20260914_mtd_pack_v1.sql``. Flask talks to
PostgREST with the service-role key (RLS bypassed); org isolation is
enforced here by always filtering on ``org_id``, exactly like the
in-memory store.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import fields
from datetime import date, datetime, timezone
from typing import Any, TypeVar

import requests

from mtd.models import (
    CsvImport,
    LedgerEntry,
    MtdProperty,
    OrgMember,
    Organisation,
    PropertyBusiness,
    QuarterPack,
    ShareLink,
)
from mtd.store import Conflict, MtdStoreError, NotFound
from supabase_gotrue import supabase_url

logger = logging.getLogger("mtd.supabase_store")

MIGRATION_HINT = (
    "Apply supabase/migrations/20260914_mtd_pack_v1.sql on the production "
    "Supabase project, then confirm GET /v1/mtd/health storeProbe.ready is true."
)

# Supabase caps a single PostgREST read at 1000 rows by default.
PAGE_SIZE = 1000
_TIMEOUT = 12

T = TypeVar("T")


def service_key() -> str:
    """Service-role key only. The anon key cannot write through RLS."""
    return (
        os.environ.get("SUPABASE_SERVICE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    ).strip()


def supabase_store_configured() -> bool:
    if os.environ.get("MTD_FORCE_MEMORY_STORE") == "1":
        return False
    return bool(supabase_url() and service_key())


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (TypeError, ValueError, AttributeError):
        return False


_FRACTION = re.compile(r"\.(\d+)")


def _dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    # Postgres trims trailing zeros from fractional seconds; pad to micros.
    text = _FRACTION.sub(lambda m: "." + m.group(1)[:6].ljust(6, "0"), text, count=1)
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _d(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def _row(obj: Any, *, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in fields(obj):
        if f.name in exclude:
            continue
        value = getattr(obj, f.name)
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        out[f.name] = value
    return out


def _org(r: dict) -> Organisation:
    return Organisation(
        id=r["id"],
        name=r["name"],
        created_by=r["created_by"],
        created_at=_dt(r["created_at"]),
        updated_at=_dt(r["updated_at"]),
    )


def _member(r: dict) -> OrgMember:
    return OrgMember(
        org_id=r["org_id"],
        user_id=r["user_id"],
        role=r["role"],
        created_at=_dt(r["created_at"]),
        email=r.get("email"),
    )


def _business(r: dict) -> PropertyBusiness:
    return PropertyBusiness(
        id=r["id"],
        org_id=r["org_id"],
        name=r["name"],
        tax_year_start=_d(r["tax_year_start"]),
        basis=r["basis"],
        country=r["country"],
        status=r["status"],
        created_at=_dt(r["created_at"]),
        updated_at=_dt(r["updated_at"]),
    )


def _property(r: dict) -> MtdProperty:
    return MtdProperty(
        id=r["id"],
        org_id=r["org_id"],
        business_id=r["business_id"],
        property_id=r.get("property_id"),
        label=r["label"],
        address=r.get("address"),
        postcode=r.get("postcode"),
        occupancy_type=r["occupancy_type"],
        created_at=_dt(r["created_at"]),
        updated_at=_dt(r["updated_at"]),
    )


def _entry(r: dict) -> LedgerEntry:
    return LedgerEntry(
        id=r["id"],
        org_id=r["org_id"],
        business_id=r["business_id"],
        property_id=r.get("property_id"),
        entry_date=_d(r["entry_date"]),
        amount_pence=int(r["amount_pence"]),
        category_code=r["category_code"],
        description=r.get("description"),
        counterparty=r.get("counterparty"),
        source=r["source"],
        source_ref=r.get("source_ref"),
        fingerprint=r["fingerprint"],
        created_by=r["created_by"],
        created_at=_dt(r["created_at"]),
        updated_at=_dt(r["updated_at"]),
        voided_at=_dt(r.get("voided_at")),
    )


def _import(r: dict) -> CsvImport:
    return CsvImport(
        id=r["id"],
        org_id=r["org_id"],
        business_id=r["business_id"],
        filename=r["filename"],
        content_sha256=r["content_sha256"],
        status=r["status"],
        row_count=int(r["row_count"]),
        created_count=int(r["created_count"]),
        skipped_count=int(r["skipped_count"]),
        created_by=r["created_by"],
        created_at=_dt(r["created_at"]),
        committed_at=_dt(r.get("committed_at")),
    )


def _pack(r: dict) -> QuarterPack:
    return QuarterPack(
        id=r["id"],
        org_id=r["org_id"],
        business_id=r["business_id"],
        tax_year=r["tax_year"],
        quarter=int(r["quarter"]),
        basis=r["basis"],
        period_start=_d(r["period_start"]),
        period_end=_d(r["period_end"]),
        snapshot=r["snapshot"],
        created_by=r["created_by"],
        created_at=_dt(r["created_at"]),
    )


def _share(r: dict) -> ShareLink:
    return ShareLink(
        id=r["id"],
        org_id=r["org_id"],
        pack_id=r["pack_id"],
        token_hash=r["token_hash"],
        expires_at=_dt(r["expires_at"]),
        created_by=r["created_by"],
        created_at=_dt(r["created_at"]),
        revoked_at=_dt(r.get("revoked_at")),
    )


class SupabaseMtdStore:
    """PostgREST-backed MTD store. Every read and write is org-scoped."""

    backend = "supabase"

    def __init__(
        self,
        url: str | None = None,
        key: str | None = None,
        *,
        rest_url: str | None = None,
    ) -> None:
        """``rest_url`` points straight at a PostgREST root (integration tests)."""
        base = (url or supabase_url()).rstrip("/")
        self.rest_url = (rest_url or (f"{base}/rest/v1" if base else "")).rstrip("/")
        self.key = key or service_key()
        if not self.rest_url or not self.key:
            raise MtdStoreError("MTD store is not configured (SUPABASE_URL + service key)")
        self._http = requests.Session()

    # ── transport ─────────────────────────────────────────────────────
    def _headers(self, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _call(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        json_body: Any = None,
        prefer: str | None = None,
    ) -> list[dict]:
        try:
            resp = self._http.request(
                method,
                f"{self.rest_url}/{table}",
                params=params,
                json=json_body,
                headers=self._headers(prefer),
                timeout=_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.warning("mtd store %s %s unreachable: %s", method, table, exc)
            raise MtdStoreError(f"MTD storage unreachable ({table})") from exc
        if resp.status_code < 300:
            if not resp.content:
                return []
            data = resp.json()
            return data if isinstance(data, list) else [data]
        self._raise(resp, table)
        return []  # unreachable

    def _raise(self, resp: requests.Response, table: str) -> None:
        try:
            body = resp.json()
        except ValueError:
            body = {}
        code = str(body.get("code") or "")
        message = str(body.get("message") or resp.text or "")[:300]
        if code == "23505":
            raise Conflict(f"duplicate record ({table})")
        if code == "23503":
            raise ValueError(f"referenced record does not exist ({table})")
        if code in ("23514", "22P02", "22007", "22008"):
            raise ValueError(f"invalid value for {table}: {message}")
        if code == "P0001" and "immutable" in message.lower():
            raise Conflict("quarter packs are immutable records and cannot be changed or deleted")
        logger.error("mtd store %s failed: %s %s %s", table, resp.status_code, code, message)
        raise MtdStoreError(f"MTD storage error on {table} ({resp.status_code}). {MIGRATION_HINT}")

    def _get(self, table: str, params: dict[str, str]) -> list[dict]:
        return self._call("GET", table, params=params)

    def _get_all(self, table: str, params: dict[str, str]) -> list[dict]:
        """Page through a read so results never silently stop at 1000 rows."""
        rows: list[dict] = []
        offset = 0
        while True:
            page = self._get(
                table, {**params, "limit": str(PAGE_SIZE), "offset": str(offset)}
            )
            rows.extend(page)
            if len(page) < PAGE_SIZE:
                return rows
            offset += PAGE_SIZE

    def _one(self, table: str, params: dict[str, str]) -> dict | None:
        rows = self._get(table, {**params, "limit": "1"})
        return rows[0] if rows else None

    def _upsert(self, table: str, row: dict, on_conflict: str = "id") -> dict:
        rows = self._call(
            "POST",
            table,
            params={"on_conflict": on_conflict},
            json_body=row,
            prefer="resolution=merge-duplicates,return=representation",
        )
        return rows[0] if rows else row

    def _insert(self, table: str, row: dict) -> dict:
        rows = self._call("POST", table, json_body=row, prefer="return=representation")
        return rows[0] if rows else row

    def probe(self) -> dict[str, Any]:
        try:
            self._get("mtd_categories", {"select": "code", "limit": "1"})
            self._get("mtd_ledger_entries", {"select": "id", "limit": "1"})
        except (MtdStoreError, ValueError, Conflict) as exc:
            return {"backend": self.backend, "ready": False, "tables": "missing", "message": str(exc)[:200]}
        return {"backend": self.backend, "ready": True, "tables": "ok"}

    # ── orgs ──────────────────────────────────────────────────────────
    def upsert_org(self, org: Organisation) -> Organisation:
        return _org(self._upsert("mtd_organisations", _row(org)))

    def get_org(self, org_id: str) -> Organisation | None:
        if not _is_uuid(org_id):
            return None
        row = self._one("mtd_organisations", {"id": f"eq.{org_id}"})
        return _org(row) if row else None

    def list_orgs_for_user(self, user_id: str) -> list[Organisation]:
        if not _is_uuid(user_id):
            return []
        members = self._get_all(
            "mtd_org_members",
            {"user_id": f"eq.{user_id}", "select": "org_id", "order": "created_at.asc,org_id.asc"},
        )
        ids = [m["org_id"] for m in members]
        if not ids:
            return []
        rows = self._get_all("mtd_organisations", {"id": f"in.({','.join(ids)})"})
        by_id = {r["id"]: _org(r) for r in rows}
        return [by_id[i] for i in ids if i in by_id]

    def add_member(self, member: OrgMember) -> OrgMember:
        return _member(self._upsert("mtd_org_members", _row(member), on_conflict="org_id,user_id"))

    def get_member(self, org_id: str, user_id: str) -> OrgMember | None:
        if not (_is_uuid(org_id) and _is_uuid(user_id)):
            return None
        row = self._one("mtd_org_members", {"org_id": f"eq.{org_id}", "user_id": f"eq.{user_id}"})
        return _member(row) if row else None

    def list_members(self, org_id: str) -> list[OrgMember]:
        if not _is_uuid(org_id):
            return []
        rows = self._get_all("mtd_org_members", {"org_id": f"eq.{org_id}", "order": "created_at.asc"})
        return [_member(r) for r in rows]

    def default_org_id(self, user_id: str) -> str | None:
        if not _is_uuid(user_id):
            return None
        # Deterministic ordering so concurrent first requests converge on one org.
        rows = self._get_all(
            "mtd_org_members",
            {"user_id": f"eq.{user_id}", "order": "created_at.asc,org_id.asc"},
        )
        owned = [r for r in rows if r["role"] == "owner"]
        if owned:
            return owned[0]["org_id"]
        return rows[0]["org_id"] if rows else None

    # ── businesses ────────────────────────────────────────────────────
    def save_business(self, business: PropertyBusiness) -> PropertyBusiness:
        return _business(self._upsert("mtd_property_businesses", _row(business)))

    def get_business(self, org_id: str, business_id: str) -> PropertyBusiness | None:
        if not (_is_uuid(org_id) and _is_uuid(business_id)):
            return None
        row = self._one(
            "mtd_property_businesses", {"id": f"eq.{business_id}", "org_id": f"eq.{org_id}"}
        )
        return _business(row) if row else None

    def list_businesses(self, org_id: str) -> list[PropertyBusiness]:
        if not _is_uuid(org_id):
            return []
        rows = self._get_all(
            "mtd_property_businesses", {"org_id": f"eq.{org_id}", "order": "created_at.asc"}
        )
        return [_business(r) for r in rows]

    def delete_business(self, org_id: str, business_id: str) -> None:
        if not self.get_business(org_id, business_id):
            raise NotFound("property business not found")
        # Quarter packs are immutable (DB trigger), so a cascade delete would fail.
        if self._one(
            "mtd_quarter_packs",
            {"business_id": f"eq.{business_id}", "org_id": f"eq.{org_id}", "select": "id"},
        ):
            raise Conflict(
                "This property business has quarter packs, which are kept as permanent "
                "records. Archive the business instead of deleting it."
            )
        self._call(
            "DELETE",
            "mtd_property_businesses",
            params={"id": f"eq.{business_id}", "org_id": f"eq.{org_id}"},
        )

    # ── properties ────────────────────────────────────────────────────
    def save_property(self, prop: MtdProperty) -> MtdProperty:
        return _property(self._upsert("mtd_properties", _row(prop)))

    def get_property(self, org_id: str, property_pk: str) -> MtdProperty | None:
        if not (_is_uuid(org_id) and _is_uuid(property_pk)):
            return None
        row = self._one("mtd_properties", {"id": f"eq.{property_pk}", "org_id": f"eq.{org_id}"})
        return _property(row) if row else None

    def list_properties(self, org_id: str, business_id: str) -> list[MtdProperty]:
        if not (_is_uuid(org_id) and _is_uuid(business_id)):
            return []
        rows = self._get_all(
            "mtd_properties",
            {"org_id": f"eq.{org_id}", "business_id": f"eq.{business_id}", "order": "created_at.asc"},
        )
        return [_property(r) for r in rows]

    def delete_property(self, org_id: str, property_pk: str) -> None:
        if not (_is_uuid(org_id) and _is_uuid(property_pk)):
            raise NotFound("property not found")
        deleted = self._call(
            "DELETE",
            "mtd_properties",
            params={"id": f"eq.{property_pk}", "org_id": f"eq.{org_id}"},
            prefer="return=representation",
        )
        if not deleted:
            raise NotFound("property not found")

    # ── ledger ────────────────────────────────────────────────────────
    def save_entry(self, entry: LedgerEntry) -> LedgerEntry:
        try:
            return _entry(self._upsert("mtd_ledger_entries", _row(entry)))
        except Conflict as exc:
            raise Conflict("duplicate ledger fingerprint") from exc

    def get_entry(self, org_id: str, entry_id: str) -> LedgerEntry | None:
        if not (_is_uuid(org_id) and _is_uuid(entry_id)):
            return None
        row = self._one("mtd_ledger_entries", {"id": f"eq.{entry_id}", "org_id": f"eq.{org_id}"})
        return _entry(row) if row else None

    def get_entry_by_fingerprint(self, fingerprint: str) -> LedgerEntry | None:
        # Fingerprints embed the business id, so they are unique across orgs.
        # Prefer the live row; fall back to the newest voided one.
        row = self._one(
            "mtd_ledger_entries",
            {"fingerprint": f"eq.{fingerprint}", "order": "voided_at.desc.nullsfirst,created_at.desc"},
        )
        return _entry(row) if row else None

    def list_entries(
        self,
        org_id: str,
        business_id: str,
        *,
        include_voided: bool = False,
    ) -> list[LedgerEntry]:
        if not (_is_uuid(org_id) and _is_uuid(business_id)):
            return []
        params = {
            "org_id": f"eq.{org_id}",
            "business_id": f"eq.{business_id}",
            "order": "entry_date.asc,created_at.asc,id.asc",
        }
        if not include_voided:
            params["voided_at"] = "is.null"
        return [_entry(r) for r in self._get_all("mtd_ledger_entries", params)]

    def delete_entry(self, org_id: str, entry_id: str) -> None:
        if not (_is_uuid(org_id) and _is_uuid(entry_id)):
            raise NotFound("ledger entry not found")
        now = datetime.now(timezone.utc).isoformat()
        updated = self._call(
            "PATCH",
            "mtd_ledger_entries",
            params={"id": f"eq.{entry_id}", "org_id": f"eq.{org_id}"},
            json_body={"voided_at": now, "updated_at": now},
            prefer="return=representation",
        )
        if not updated:
            raise NotFound("ledger entry not found")

    # ── csv imports ───────────────────────────────────────────────────
    def save_import(self, record: CsvImport) -> CsvImport:
        return _import(self._upsert("mtd_csv_imports", _row(record)))

    def get_import(self, org_id: str, import_id: str) -> CsvImport | None:
        if not (_is_uuid(org_id) and _is_uuid(import_id)):
            return None
        row = self._one("mtd_csv_imports", {"id": f"eq.{import_id}", "org_id": f"eq.{org_id}"})
        return _import(row) if row else None

    def get_import_by_hash(self, org_id: str, business_id: str, digest: str) -> CsvImport | None:
        if not (_is_uuid(org_id) and _is_uuid(business_id)):
            return None
        rows = self._get_all(
            "mtd_csv_imports",
            {
                "org_id": f"eq.{org_id}",
                "business_id": f"eq.{business_id}",
                "content_sha256": f"eq.{digest}",
                "order": "created_at.asc",
            },
        )
        committed = [r for r in rows if r["status"] == "committed"]
        if committed:
            return _import(committed[0])
        return _import(rows[0]) if rows else None

    # ── packs ─────────────────────────────────────────────────────────
    def save_pack(self, pack: QuarterPack) -> QuarterPack:
        try:
            return _pack(self._insert("mtd_quarter_packs", _row(pack)))
        except Conflict as exc:
            raise Conflict("quarter pack already exists and is immutable") from exc

    def get_pack(self, org_id: str, pack_id: str) -> QuarterPack | None:
        if not (_is_uuid(org_id) and _is_uuid(pack_id)):
            return None
        row = self._one("mtd_quarter_packs", {"id": f"eq.{pack_id}", "org_id": f"eq.{org_id}"})
        return _pack(row) if row else None

    def get_pack_unchecked(self, pack_id: str) -> QuarterPack | None:
        if not _is_uuid(pack_id):
            return None
        row = self._one("mtd_quarter_packs", {"id": f"eq.{pack_id}"})
        return _pack(row) if row else None

    def list_packs(self, org_id: str, business_id: str) -> list[QuarterPack]:
        if not (_is_uuid(org_id) and _is_uuid(business_id)):
            return []
        rows = self._get_all(
            "mtd_quarter_packs",
            {"org_id": f"eq.{org_id}", "business_id": f"eq.{business_id}", "order": "created_at.asc"},
        )
        return [_pack(r) for r in rows]

    # ── share links ───────────────────────────────────────────────────
    def save_share(self, share: ShareLink) -> ShareLink:
        # The raw token is returned once at creation and never persisted.
        return _share(self._upsert("mtd_share_links", _row(share, exclude=("token",))))

    def get_share(self, share_id: str) -> ShareLink | None:
        if not _is_uuid(share_id):
            return None
        row = self._one("mtd_share_links", {"id": f"eq.{share_id}"})
        return _share(row) if row else None

    def get_share_by_token_hash(self, token_hash: str) -> ShareLink | None:
        row = self._one("mtd_share_links", {"token_hash": f"eq.{token_hash}"})
        return _share(row) if row else None

    def list_shares_for_pack(self, org_id: str, pack_id: str) -> list[ShareLink]:
        if not (_is_uuid(org_id) and _is_uuid(pack_id)):
            return []
        rows = self._get_all(
            "mtd_share_links", {"org_id": f"eq.{org_id}", "pack_id": f"eq.{pack_id}"}
        )
        return [_share(r) for r in rows]
