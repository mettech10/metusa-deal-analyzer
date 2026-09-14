"""Dataclass models matching mtd_* tables."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date, datetime
from typing import Any, Literal

LedgerSource = Literal["manual", "csv"]
OccupancyType = Literal["residential", "non_residential", "mixed"]
QuarterBasis = Literal["standard", "calendar"]
OrgRole = Literal["owner", "admin", "member"]
ImportStatus = Literal["preview", "committed"]
BusinessStatus = Literal["active", "archived"]


def api_dict(obj: Any) -> Any:
    """Convert dataclasses to camelCase API dicts. Nested JSON blobs keep their keys."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return {_to_camel(f.name): api_dict(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, (list, tuple)):
        return [api_dict(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    return obj


def _to_camel(key: str) -> str:
    if key == "id" or "_" not in key:
        return key
    parts = key.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


@dataclass
class Organisation:
    id: str
    name: str
    created_by: str
    created_at: datetime
    updated_at: datetime


@dataclass
class OrgMember:
    org_id: str
    user_id: str
    role: OrgRole
    created_at: datetime
    email: str | None = None


@dataclass
class PropertyBusiness:
    id: str
    org_id: str
    name: str
    tax_year_start: date
    basis: QuarterBasis
    country: str
    status: BusinessStatus
    created_at: datetime
    updated_at: datetime


@dataclass
class MtdProperty:
    id: str
    org_id: str
    business_id: str
    property_id: str | None  # optional link to portfolio_properties.id
    label: str
    address: str | None
    postcode: str | None
    occupancy_type: OccupancyType
    created_at: datetime
    updated_at: datetime


@dataclass
class LedgerEntry:
    id: str
    org_id: str
    business_id: str
    property_id: str | None
    entry_date: date
    amount_pence: int
    category_code: str
    description: str | None
    counterparty: str | None
    source: LedgerSource
    source_ref: str | None
    fingerprint: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    voided_at: datetime | None = None


@dataclass
class CsvImport:
    id: str
    org_id: str
    business_id: str
    filename: str
    content_sha256: str
    status: ImportStatus
    row_count: int
    created_count: int
    skipped_count: int
    created_by: str
    created_at: datetime
    committed_at: datetime | None = None


@dataclass
class QuarterPack:
    id: str
    org_id: str
    business_id: str
    tax_year: str
    quarter: int
    basis: QuarterBasis
    period_start: date
    period_end: date
    snapshot: dict[str, Any]
    created_by: str
    created_at: datetime


@dataclass
class ShareLink:
    id: str
    org_id: str
    pack_id: str
    token_hash: str
    expires_at: datetime
    created_by: str
    created_at: datetime
    revoked_at: datetime | None = None
    # raw token is never persisted; only returned at creation time
    token: str | None = field(default=None, compare=False)


@dataclass
class AuthContext:
    user_id: str
    org_id: str
    role: OrgRole
    email: str | None = None
