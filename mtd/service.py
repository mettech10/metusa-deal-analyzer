"""Org-scoped MTD application service."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from mtd.categories import get_category
from mtd.csv_import import preview_rows, row_fingerprint, sha256_text
from mtd.models import (
    AuthContext,
    CsvImport,
    LedgerEntry,
    MtdProperty,
    OrgMember,
    Organisation,
    PropertyBusiness,
    QuarterPack,
    ShareLink,
    api_dict,
)
from mtd.open_banking import OpenBankingNotAvailable, StubOpenBankingProvider
from mtd.packs import DISCLAIMER, build_snapshot, snapshot_to_csv, snapshot_to_pdf_lines
from mtd.pdf import build_simple_pdf
from mtd.quarters import parse_tax_year_start, resolve_quarter, tax_year_label
from mtd.store import Conflict, InMemoryMtdStore, NotFound

_SOURCES = frozenset({"manual", "csv"})
_OCCUPANCY = frozenset({"residential", "non_residential", "mixed"})
_BASIS = frozenset({"standard", "calendar"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


def _parse_date(value: Any, field: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not value:
        raise ValueError(f"{field} is required")
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise ValueError(f"invalid {field}") from exc


def _require_int_pence(value: Any) -> int:
    if value is None or value == "":
        raise ValueError("amountPence is required")
    if isinstance(value, bool):
        raise ValueError("amountPence must be an integer")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError("amountPence must be whole pence, not pounds")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("amountPence must be an integer") from exc


class MtdService:
    def __init__(
        self,
        store: InMemoryMtdStore | None = None,
        open_banking: StubOpenBankingProvider | None = None,
    ) -> None:
        self.store = store or InMemoryMtdStore()
        self.open_banking = open_banking or StubOpenBankingProvider()

    # ── auth / orgs ───────────────────────────────────────────────────
    def ensure_org(self, user_id: str, email: str | None = None, org_id: str | None = None) -> AuthContext:
        if org_id:
            member = self.store.get_member(org_id, user_id)
            if not member:
                raise PermissionError("not a member of this organisation")
            return AuthContext(user_id=user_id, org_id=org_id, role=member.role, email=email)
        existing = self.store.default_org_id(user_id)
        if existing:
            member = self.store.get_member(existing, user_id)
            return AuthContext(
                user_id=user_id,
                org_id=existing,
                role=member.role if member else "member",
                email=email,
            )
        org = Organisation(
            id=_new_id(),
            name=(email.split("@")[0] + " organisation") if email else "Personal organisation",
            created_by=user_id,
            created_at=_now(),
            updated_at=_now(),
        )
        self.store.upsert_org(org)
        self.store.add_member(
            OrgMember(org_id=org.id, user_id=user_id, role="owner", created_at=_now(), email=email)
        )
        return AuthContext(user_id=user_id, org_id=org.id, role="owner", email=email)

    def list_orgs(self, ctx: AuthContext) -> list[dict[str, Any]]:
        return [api_dict(o) for o in self.store.list_orgs_for_user(ctx.user_id)]

    def current_org(self, ctx: AuthContext) -> dict[str, Any]:
        org = self.store.get_org(ctx.org_id)
        if not org:
            raise NotFound("organisation not found")
        return {
            **api_dict(org),
            "role": ctx.role,
            "members": [api_dict(m) for m in self.store.list_members(ctx.org_id)],
        }

    def create_org(self, ctx: AuthContext, body: dict[str, Any]) -> dict[str, Any]:
        name = (body.get("name") or "").strip()
        if not name:
            raise ValueError("name is required")
        org = Organisation(
            id=_new_id(),
            name=name,
            created_by=ctx.user_id,
            created_at=_now(),
            updated_at=_now(),
        )
        self.store.upsert_org(org)
        self.store.add_member(
            OrgMember(
                org_id=org.id,
                user_id=ctx.user_id,
                role="owner",
                created_at=_now(),
                email=ctx.email,
            )
        )
        return api_dict(org)

    def add_member(self, ctx: AuthContext, body: dict[str, Any]) -> dict[str, Any]:
        if ctx.role not in ("owner", "admin"):
            raise PermissionError("only owners and admins can add members")
        user_id = (body.get("userId") or body.get("user_id") or "").strip()
        role = (body.get("role") or "member").strip()
        if not user_id:
            raise ValueError("userId is required")
        if role not in ("owner", "admin", "member"):
            raise ValueError("invalid role")
        member = OrgMember(
            org_id=ctx.org_id,
            user_id=user_id,
            role=role,  # type: ignore[arg-type]
            created_at=_now(),
            email=body.get("email"),
        )
        self.store.add_member(member)
        return api_dict(member)

    # ── businesses ────────────────────────────────────────────────────
    def list_businesses(self, ctx: AuthContext) -> list[dict[str, Any]]:
        return [api_dict(b) for b in self.store.list_businesses(ctx.org_id)]

    def create_business(self, ctx: AuthContext, body: dict[str, Any]) -> dict[str, Any]:
        name = (body.get("name") or "").strip()
        if not name:
            raise ValueError("name is required")
        basis = (body.get("basis") or "standard").strip()
        if basis not in _BASIS:
            raise ValueError("basis must be standard or calendar")
        tax_year_start = parse_tax_year_start(
            body.get("taxYearStart") or body.get("tax_year_start")
        )
        biz = PropertyBusiness(
            id=_new_id(),
            org_id=ctx.org_id,
            name=name,
            tax_year_start=tax_year_start,
            basis=basis,  # type: ignore[arg-type]
            country=(body.get("country") or "uk").strip().lower(),
            status="active",
            created_at=_now(),
            updated_at=_now(),
        )
        return api_dict(self.store.save_business(biz))

    def _business(self, ctx: AuthContext, business_id: str) -> PropertyBusiness:
        biz = self.store.get_business(ctx.org_id, business_id)
        if not biz:
            raise NotFound("property business not found")
        return biz

    def get_business(self, ctx: AuthContext, business_id: str) -> dict[str, Any]:
        return api_dict(self._business(ctx, business_id))

    def update_business(self, ctx: AuthContext, business_id: str, body: dict[str, Any]) -> dict[str, Any]:
        biz = self._business(ctx, business_id)
        if "name" in body and str(body["name"]).strip():
            biz.name = str(body["name"]).strip()
        if body.get("basis") in _BASIS:
            biz.basis = body["basis"]
        if body.get("status") in ("active", "archived"):
            biz.status = body["status"]
        if body.get("taxYearStart") or body.get("tax_year_start"):
            biz.tax_year_start = parse_tax_year_start(
                body.get("taxYearStart") or body.get("tax_year_start")
            )
        biz.updated_at = _now()
        return api_dict(self.store.save_business(biz))

    def delete_business(self, ctx: AuthContext, business_id: str) -> None:
        self._business(ctx, business_id)
        self.store.delete_business(ctx.org_id, business_id)

    # ── properties ────────────────────────────────────────────────────
    def list_properties(self, ctx: AuthContext, business_id: str) -> list[dict[str, Any]]:
        self._business(ctx, business_id)
        return [api_dict(p) for p in self.store.list_properties(ctx.org_id, business_id)]

    def create_property(self, ctx: AuthContext, business_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self._business(ctx, business_id)
        label = (body.get("label") or body.get("address") or "").strip()
        if not label:
            raise ValueError("label is required")
        occupancy = (body.get("occupancyType") or body.get("occupancy_type") or "residential").strip()
        if occupancy not in _OCCUPANCY:
            raise ValueError("occupancyType must be residential, non_residential or mixed")
        prop = MtdProperty(
            id=_new_id(),
            org_id=ctx.org_id,
            business_id=business_id,
            property_id=body.get("propertyId") or body.get("property_id"),
            label=label,
            address=body.get("address"),
            postcode=body.get("postcode"),
            occupancy_type=occupancy,  # type: ignore[arg-type]
            created_at=_now(),
            updated_at=_now(),
        )
        return api_dict(self.store.save_property(prop))

    def get_property(self, ctx: AuthContext, property_pk: str) -> dict[str, Any]:
        prop = self.store.get_property(ctx.org_id, property_pk)
        if not prop:
            raise NotFound("property not found")
        return api_dict(prop)

    def update_property(self, ctx: AuthContext, property_pk: str, body: dict[str, Any]) -> dict[str, Any]:
        prop = self.store.get_property(ctx.org_id, property_pk)
        if not prop:
            raise NotFound("property not found")
        if body.get("label"):
            prop.label = str(body["label"]).strip()
        if "address" in body:
            prop.address = body.get("address")
        if "postcode" in body:
            prop.postcode = body.get("postcode")
        if "propertyId" in body or "property_id" in body:
            prop.property_id = body.get("propertyId") or body.get("property_id")
        occupancy = body.get("occupancyType") or body.get("occupancy_type")
        if occupancy:
            if occupancy not in _OCCUPANCY:
                raise ValueError("invalid occupancyType")
            prop.occupancy_type = occupancy  # type: ignore[arg-type]
        prop.updated_at = _now()
        return api_dict(self.store.save_property(prop))

    def delete_property(self, ctx: AuthContext, property_pk: str) -> None:
        self.store.delete_property(ctx.org_id, property_pk)

    # ── ledger ────────────────────────────────────────────────────────
    def list_ledger(self, ctx: AuthContext, business_id: str) -> list[dict[str, Any]]:
        self._business(ctx, business_id)
        return [api_dict(e) for e in self.store.list_entries(ctx.org_id, business_id)]

    def create_entry(self, ctx: AuthContext, business_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self._business(ctx, business_id)
        return api_dict(self._insert_entry(ctx, business_id, body, source="manual"))

    def _insert_entry(
        self,
        ctx: AuthContext,
        business_id: str,
        body: dict[str, Any],
        *,
        source: str,
        fingerprint: str | None = None,
        source_ref: str | None = None,
    ) -> LedgerEntry:
        category = body.get("categoryCode") or body.get("category_code") or body.get("category")
        cat = get_category(str(category or ""))
        if not cat:
            raise ValueError("unknown category")
        amount = _require_int_pence(body.get("amountPence") if "amountPence" in body else body.get("amount_pence"))
        entry_date = _parse_date(body.get("date") or body.get("entryDate") or body.get("entry_date"), "date")
        property_id = body.get("propertyId") or body.get("property_id")
        if property_id:
            prop = self.store.get_property(ctx.org_id, str(property_id))
            if not prop or prop.business_id != business_id:
                raise ValueError("propertyId does not belong to this business")
        src = (body.get("source") or source).strip()
        if src not in _SOURCES:
            raise ValueError("source must be manual or csv")
        fp = fingerprint or row_fingerprint(
            business_id=business_id,
            entry_date=entry_date.isoformat(),
            property_id=property_id,
            category_code=cat["code"],
            amount_pence=amount,
            description=body.get("description"),
            source_row=0,
            content_sha256=f"manual:{ctx.user_id}:{_new_id()}",
        )
        existing = self.store.get_entry_by_fingerprint(fp)
        if existing and existing.voided_at is None:
            raise Conflict("duplicate ledger entry")
        entry = LedgerEntry(
            id=_new_id(),
            org_id=ctx.org_id,
            business_id=business_id,
            property_id=property_id,
            entry_date=entry_date,
            amount_pence=amount,
            category_code=cat["code"],
            description=body.get("description"),
            counterparty=body.get("counterparty"),
            source=src,  # type: ignore[arg-type]
            source_ref=source_ref or body.get("sourceRef") or body.get("source_ref"),
            fingerprint=fp,
            created_by=ctx.user_id,
            created_at=_now(),
            updated_at=_now(),
        )
        return self.store.save_entry(entry)

    def get_entry(self, ctx: AuthContext, entry_id: str) -> dict[str, Any]:
        entry = self.store.get_entry(ctx.org_id, entry_id)
        if not entry:
            raise NotFound("ledger entry not found")
        return api_dict(entry)

    def update_entry(self, ctx: AuthContext, entry_id: str, body: dict[str, Any]) -> dict[str, Any]:
        entry = self.store.get_entry(ctx.org_id, entry_id)
        if not entry:
            raise NotFound("ledger entry not found")
        if entry.voided_at:
            raise ValueError("cannot edit a voided entry")
        if "amountPence" in body or "amount_pence" in body:
            entry.amount_pence = _require_int_pence(body.get("amountPence", body.get("amount_pence")))
        if body.get("date") or body.get("entryDate"):
            entry.entry_date = _parse_date(body.get("date") or body.get("entryDate"), "date")
        if body.get("categoryCode") or body.get("category"):
            cat = get_category(str(body.get("categoryCode") or body.get("category")))
            if not cat:
                raise ValueError("unknown category")
            entry.category_code = cat["code"]
        if "description" in body:
            entry.description = body.get("description")
        if "counterparty" in body:
            entry.counterparty = body.get("counterparty")
        if "propertyId" in body or "property_id" in body:
            pid = body.get("propertyId") or body.get("property_id")
            if pid:
                prop = self.store.get_property(ctx.org_id, str(pid))
                if not prop:
                    raise ValueError("propertyId not found")
            entry.property_id = pid
        entry.updated_at = _now()
        return api_dict(self.store.save_entry(entry))

    def delete_entry(self, ctx: AuthContext, entry_id: str) -> None:
        self.store.delete_entry(ctx.org_id, entry_id)

    # ── csv ───────────────────────────────────────────────────────────
    def preview_import(self, ctx: AuthContext, business_id: str, csv_text: str) -> dict[str, Any]:
        self._business(ctx, business_id)
        known = {p.id for p in self.store.list_properties(ctx.org_id, business_id)}
        known |= {p.property_id for p in self.store.list_properties(ctx.org_id, business_id) if p.property_id}
        result = preview_rows(csv_text, known_property_ids=known if known else None)
        digest = sha256_text(csv_text)
        result["contentSha256"] = digest
        result["businessId"] = business_id
        existing_file = self.store.get_import_by_hash(ctx.org_id, business_id, digest)
        already_file = bool(existing_file and existing_file.status == "committed")
        result["alreadyImportedFile"] = already_file
        already_count = 0
        for row in result["rows"]:
            mapped = row.get("mapped") or {}
            already = False
            if already_file:
                already = True
            elif (
                row.get("valid")
                and mapped.get("date")
                and mapped.get("categoryCode")
                and mapped.get("amountPence") is not None
            ):
                fp = row_fingerprint(
                    business_id=business_id,
                    entry_date=mapped["date"],
                    property_id=mapped.get("propertyId"),
                    category_code=mapped["categoryCode"],
                    amount_pence=mapped["amountPence"],
                    description=mapped.get("description"),
                    source_row=row["rowNumber"],
                    content_sha256=digest,
                )
                existing_entry = self.store.get_entry_by_fingerprint(fp)
                already = bool(existing_entry and existing_entry.voided_at is None)
            row["alreadyImported"] = already
            if already:
                already_count += 1
                warnings = list(row.get("warnings") or [])
                warnings.append("already imported — Flask will skip this row on commit")
                row["warnings"] = warnings
        result["alreadyImportedCount"] = already_count
        return result

    def commit_import(
        self,
        ctx: AuthContext,
        business_id: str,
        csv_text: str,
        filename: str = "import.csv",
    ) -> dict[str, Any]:
        self._business(ctx, business_id)
        digest = sha256_text(csv_text)
        existing = self.store.get_import_by_hash(ctx.org_id, business_id, digest)
        if existing and existing.status == "committed":
            return {
                "idempotent": True,
                "import": api_dict(existing),
                "createdCount": 0,
                "skippedCount": existing.created_count,
            }
        preview = self.preview_import(ctx, business_id, csv_text)
        if preview["headerIssues"]:
            raise ValueError("; ".join(preview["headerIssues"]))
        invalid = [r for r in preview["rows"] if not r["valid"]]
        if invalid:
            raise ValueError(f"{len(invalid)} invalid CSV row(s); preview and fix before commit")
        created = 0
        skipped = 0
        import_id = existing.id if existing else _new_id()
        for row in preview["rows"]:
            mapped = row["mapped"]
            fp = row_fingerprint(
                business_id=business_id,
                entry_date=mapped["date"],
                property_id=mapped.get("propertyId"),
                category_code=mapped["categoryCode"],
                amount_pence=mapped["amountPence"],
                description=mapped.get("description"),
                source_row=row["rowNumber"],
                content_sha256=digest,
            )
            if self.store.get_entry_by_fingerprint(fp):
                skipped += 1
                continue
            property_pk = mapped.get("propertyId")
            if property_pk:
                prop = self.store.get_property(ctx.org_id, property_pk)
                if not prop:
                    for candidate in self.store.list_properties(ctx.org_id, business_id):
                        if candidate.property_id == property_pk:
                            property_pk = candidate.id
                            break
            self._insert_entry(
                ctx,
                business_id,
                {
                    "date": mapped["date"],
                    "propertyId": property_pk,
                    "categoryCode": mapped["categoryCode"],
                    "amountPence": mapped["amountPence"],
                    "description": mapped.get("description"),
                    "counterparty": mapped.get("counterparty"),
                    "source": "csv",
                },
                source="csv",
                fingerprint=fp,
                source_ref=f"{import_id}:{row['rowNumber']}",
            )
            created += 1
        record = CsvImport(
            id=import_id,
            org_id=ctx.org_id,
            business_id=business_id,
            filename=filename,
            content_sha256=digest,
            status="committed",
            row_count=preview["rowCount"],
            created_count=created,
            skipped_count=skipped,
            created_by=ctx.user_id,
            created_at=existing.created_at if existing else _now(),
            committed_at=_now(),
        )
        self.store.save_import(record)
        return {
            "idempotent": False,
            "import": api_dict(record),
            "createdCount": created,
            "skippedCount": skipped,
        }

    # ── packs ─────────────────────────────────────────────────────────
    def list_packs(self, ctx: AuthContext, business_id: str) -> list[dict[str, Any]]:
        self._business(ctx, business_id)
        packs = self.store.list_packs(ctx.org_id, business_id)
        return [self._pack_summary(p) for p in packs]

    def create_pack(self, ctx: AuthContext, business_id: str, body: dict[str, Any]) -> dict[str, Any]:
        biz = self._business(ctx, business_id)
        quarter = int(body.get("quarter") or 0)
        if quarter not in (1, 2, 3, 4):
            raise ValueError("quarter must be 1-4")
        basis = (body.get("basis") or biz.basis or "standard").strip()
        if basis not in _BASIS:
            raise ValueError("basis must be standard or calendar")
        tax_year = body.get("taxYear") or body.get("tax_year") or tax_year_label(biz.tax_year_start)
        period_start, period_end = resolve_quarter(str(tax_year), quarter, basis)  # type: ignore[arg-type]
        snapshot = build_snapshot(
            business=biz,
            properties=self.store.list_properties(ctx.org_id, business_id),
            entries=self.store.list_entries(ctx.org_id, business_id, include_voided=True),
            tax_year=str(tax_year),
            quarter=quarter,
            basis=basis,
            generated_by=ctx.user_id,
        )
        pack = QuarterPack(
            id=_new_id(),
            org_id=ctx.org_id,
            business_id=business_id,
            tax_year=str(tax_year),
            quarter=quarter,
            basis=basis,  # type: ignore[arg-type]
            period_start=period_start,
            period_end=period_end,
            snapshot=snapshot,
            created_by=ctx.user_id,
            created_at=_now(),
        )
        try:
            saved = self.store.save_pack(pack)
        except Conflict as exc:
            raise Conflict(str(exc)) from exc
        return self._pack_summary(saved, include_snapshot=True)

    def get_pack(self, ctx: AuthContext, pack_id: str, *, include_snapshot: bool = True) -> dict[str, Any]:
        pack = self.store.get_pack(ctx.org_id, pack_id)
        if not pack:
            raise NotFound("quarter pack not found")
        return self._pack_summary(pack, include_snapshot=include_snapshot)

    def _pack_summary(self, pack: QuarterPack, include_snapshot: bool = False) -> dict[str, Any]:
        payload = api_dict(pack)
        if not include_snapshot:
            payload.pop("snapshot", None)
            payload["hasSnapshot"] = True
        payload["immutable"] = True
        payload["hmrcSubmit"] = False
        payload["disclaimer"] = DISCLAIMER
        return payload

    def export_pack(self, ctx: AuthContext, pack_id: str, fmt: str) -> tuple[bytes, str, str]:
        pack = self.store.get_pack(ctx.org_id, pack_id)
        if not pack:
            raise NotFound("quarter pack not found")
        return self._export(pack, fmt)

    def export_pack_public(self, pack: QuarterPack, fmt: str) -> tuple[bytes, str, str]:
        return self._export(pack, fmt)

    def _export(self, pack: QuarterPack, fmt: str) -> tuple[bytes, str, str]:
        fmt = fmt.lower().lstrip(".")
        filename = f"mtd-pack-{pack.tax_year}-q{pack.quarter}.{fmt}"
        if fmt == "json":
            import json

            body = json.dumps(pack.snapshot, indent=2).encode("utf-8")
            return body, "application/json", filename
        if fmt == "csv":
            return snapshot_to_csv(pack.snapshot).encode("utf-8"), "text/csv; charset=utf-8", filename
        if fmt == "pdf":
            snap = pack.snapshot
            return (
                build_simple_pdf(
                    "Metalyzi MTD Quarter Pack",
                    snapshot_to_pdf_lines(snap),
                    disclaimer=str(snap.get("disclaimer") or DISCLAIMER),
                ),
                "application/pdf",
                filename,
            )
        raise ValueError("format must be json, csv or pdf")

    # ── share links ───────────────────────────────────────────────────
    def create_share(self, ctx: AuthContext, pack_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        pack = self.store.get_pack(ctx.org_id, pack_id)
        if not pack:
            raise NotFound("quarter pack not found")
        body = body or {}
        days = int(body.get("expiresInDays") or body.get("expires_in_days") or 7)
        if days < 1 or days > 90:
            raise ValueError("expiresInDays must be between 1 and 90")
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        share = ShareLink(
            id=_new_id(),
            org_id=ctx.org_id,
            pack_id=pack_id,
            token_hash=token_hash,
            expires_at=_now() + timedelta(days=days),
            created_by=ctx.user_id,
            created_at=_now(),
            token=token,
        )
        self.store.save_share(share)
        payload = api_dict(share)
        payload["token"] = token
        payload["urlPath"] = f"/v1/mtd/share/{token}"
        payload.pop("tokenHash", None)
        return payload

    def resolve_share(self, token: str) -> QuarterPack:
        if not token:
            raise NotFound("share link not found")
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        share = self.store.get_share_by_token_hash(token_hash)
        if not share or share.revoked_at:
            raise NotFound("share link not found")
        if share.expires_at <= _now():
            raise PermissionError("share link has expired")
        pack = self.store.get_pack_unchecked(share.pack_id)
        if not pack:
            raise NotFound("quarter pack not found")
        return pack

    def revoke_share(self, ctx: AuthContext, share_id: str) -> None:
        share = self.store.get_share(share_id)
        if not share or share.org_id != ctx.org_id:
            raise NotFound("share link not found")
        share.revoked_at = _now()
        self.store.save_share(share)

    # ── open banking ──────────────────────────────────────────────────
    def open_banking_status(self) -> dict[str, Any]:
        return self.open_banking.status()

    def open_banking_sync(self, ctx: AuthContext, business_id: str) -> None:
        self._business(ctx, business_id)
        try:
            self.open_banking.sync(org_id=ctx.org_id, business_id=business_id)
        except OpenBankingNotAvailable:
            raise
