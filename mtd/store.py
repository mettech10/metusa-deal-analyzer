"""In-memory MTD store used by tests and local Flask without a database."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

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


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


class Forbidden(Exception):
    pass


class InMemoryMtdStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.orgs: dict[str, Organisation] = {}
        self.members: dict[tuple[str, str], OrgMember] = {}  # (org_id, user_id)
        self.businesses: dict[str, PropertyBusiness] = {}
        self.properties: dict[str, MtdProperty] = {}
        self.entries: dict[str, LedgerEntry] = {}
        self.imports: dict[str, CsvImport] = {}
        self.packs: dict[str, QuarterPack] = {}
        self.shares: dict[str, ShareLink] = {}
        self.fingerprints: dict[str, str] = {}  # fingerprint -> entry_id

    # ── orgs ──────────────────────────────────────────────────────────
    def upsert_org(self, org: Organisation) -> Organisation:
        with self._lock:
            self.orgs[org.id] = org
            return org

    def get_org(self, org_id: str) -> Organisation | None:
        return self.orgs.get(org_id)

    def list_orgs_for_user(self, user_id: str) -> list[Organisation]:
        org_ids = [m.org_id for m in self.members.values() if m.user_id == user_id]
        return [self.orgs[i] for i in org_ids if i in self.orgs]

    def add_member(self, member: OrgMember) -> OrgMember:
        with self._lock:
            self.members[(member.org_id, member.user_id)] = member
            return member

    def get_member(self, org_id: str, user_id: str) -> OrgMember | None:
        return self.members.get((org_id, user_id))

    def list_members(self, org_id: str) -> list[OrgMember]:
        return [m for m in self.members.values() if m.org_id == org_id]

    def default_org_id(self, user_id: str) -> str | None:
        owned = [
            m for m in self.members.values() if m.user_id == user_id and m.role == "owner"
        ]
        if owned:
            return owned[0].org_id
        any_m = [m for m in self.members.values() if m.user_id == user_id]
        return any_m[0].org_id if any_m else None

    # ── businesses ────────────────────────────────────────────────────
    def save_business(self, business: PropertyBusiness) -> PropertyBusiness:
        with self._lock:
            self.businesses[business.id] = business
            return business

    def get_business(self, org_id: str, business_id: str) -> PropertyBusiness | None:
        biz = self.businesses.get(business_id)
        if biz and biz.org_id == org_id:
            return biz
        return None

    def list_businesses(self, org_id: str) -> list[PropertyBusiness]:
        return [b for b in self.businesses.values() if b.org_id == org_id]

    def delete_business(self, org_id: str, business_id: str) -> None:
        with self._lock:
            biz = self.get_business(org_id, business_id)
            if not biz:
                raise NotFound("property business not found")
            del self.businesses[business_id]
            for pid in [p.id for p in self.properties.values() if p.business_id == business_id]:
                self.properties.pop(pid, None)
            for eid in [e.id for e in self.entries.values() if e.business_id == business_id]:
                fp = self.entries[eid].fingerprint
                self.fingerprints.pop(fp, None)
                self.entries.pop(eid, None)

    # ── properties ────────────────────────────────────────────────────
    def save_property(self, prop: MtdProperty) -> MtdProperty:
        with self._lock:
            self.properties[prop.id] = prop
            return prop

    def get_property(self, org_id: str, property_pk: str) -> MtdProperty | None:
        prop = self.properties.get(property_pk)
        if prop and prop.org_id == org_id:
            return prop
        return None

    def list_properties(self, org_id: str, business_id: str) -> list[MtdProperty]:
        return [
            p
            for p in self.properties.values()
            if p.org_id == org_id and p.business_id == business_id
        ]

    def delete_property(self, org_id: str, property_pk: str) -> None:
        with self._lock:
            prop = self.get_property(org_id, property_pk)
            if not prop:
                raise NotFound("property not found")
            del self.properties[property_pk]

    # ── ledger ────────────────────────────────────────────────────────
    def save_entry(self, entry: LedgerEntry) -> LedgerEntry:
        with self._lock:
            existing_id = self.fingerprints.get(entry.fingerprint)
            if existing_id and existing_id != entry.id:
                raise Conflict("duplicate ledger fingerprint")
            self.entries[entry.id] = entry
            self.fingerprints[entry.fingerprint] = entry.id
            return entry

    def get_entry(self, org_id: str, entry_id: str) -> LedgerEntry | None:
        entry = self.entries.get(entry_id)
        if entry and entry.org_id == org_id:
            return entry
        return None

    def get_entry_by_fingerprint(self, fingerprint: str) -> LedgerEntry | None:
        eid = self.fingerprints.get(fingerprint)
        return self.entries.get(eid) if eid else None

    def list_entries(
        self,
        org_id: str,
        business_id: str,
        *,
        include_voided: bool = False,
    ) -> list[LedgerEntry]:
        rows = [
            e
            for e in self.entries.values()
            if e.org_id == org_id and e.business_id == business_id
        ]
        if not include_voided:
            rows = [e for e in rows if e.voided_at is None]
        return sorted(rows, key=lambda e: (e.entry_date, e.created_at, e.id))

    def delete_entry(self, org_id: str, entry_id: str) -> None:
        with self._lock:
            entry = self.get_entry(org_id, entry_id)
            if not entry:
                raise NotFound("ledger entry not found")
            entry.voided_at = datetime.now(timezone.utc)
            self.entries[entry_id] = entry

    # ── csv imports ───────────────────────────────────────────────────
    def save_import(self, record: CsvImport) -> CsvImport:
        with self._lock:
            self.imports[record.id] = record
            return record

    def get_import(self, org_id: str, import_id: str) -> CsvImport | None:
        rec = self.imports.get(import_id)
        if rec and rec.org_id == org_id:
            return rec
        return None

    def get_import_by_hash(self, org_id: str, business_id: str, digest: str) -> CsvImport | None:
        matches = [
            r
            for r in self.imports.values()
            if r.org_id == org_id
            and r.business_id == business_id
            and r.content_sha256 == digest
        ]
        committed = [r for r in matches if r.status == "committed"]
        if committed:
            return committed[0]
        return matches[0] if matches else None

    # ── packs ─────────────────────────────────────────────────────────
    def save_pack(self, pack: QuarterPack) -> QuarterPack:
        with self._lock:
            key = (pack.org_id, pack.business_id, pack.tax_year, pack.quarter, pack.basis)
            for existing in self.packs.values():
                if (
                    existing.org_id,
                    existing.business_id,
                    existing.tax_year,
                    existing.quarter,
                    existing.basis,
                ) == key:
                    raise Conflict("quarter pack already exists and is immutable")
            self.packs[pack.id] = pack
            return pack

    def get_pack(self, org_id: str, pack_id: str) -> QuarterPack | None:
        pack = self.packs.get(pack_id)
        if pack and pack.org_id == org_id:
            return pack
        return None

    def get_pack_unchecked(self, pack_id: str) -> QuarterPack | None:
        return self.packs.get(pack_id)

    def list_packs(self, org_id: str, business_id: str) -> list[QuarterPack]:
        return [
            p
            for p in self.packs.values()
            if p.org_id == org_id and p.business_id == business_id
        ]

    # ── share links ───────────────────────────────────────────────────
    def save_share(self, share: ShareLink) -> ShareLink:
        with self._lock:
            self.shares[share.id] = share
            return share

    def get_share(self, share_id: str) -> ShareLink | None:
        return self.shares.get(share_id)

    def get_share_by_token_hash(self, token_hash: str) -> ShareLink | None:
        for share in self.shares.values():
            if share.token_hash == token_hash:
                return share
        return None

    def list_shares_for_pack(self, org_id: str, pack_id: str) -> list[ShareLink]:
        return [
            s
            for s in self.shares.values()
            if s.org_id == org_id and s.pack_id == pack_id
        ]
