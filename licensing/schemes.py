"""Additional / selective licensing scheme model.

Seeds are curator-edited JSON. Boundaries are never invented: coverage is
`citywide`, `designated_areas` (named areas only), or `unknown`. Address-level
membership is not resolved without an official geometry (out of scope here).

England-only: ONS codes must start with E. Wales/Scotland/NI rows are discarded
and must never override /v1/licensing/check.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from licensing.models import (
    SCHEME_STALE_AFTER_DAYS_COVERED,
    SCHEME_STALE_AFTER_DAYS_PRIORITY,
    Flag,
    Source,
    component_freshness,
    confidence_band,
    disclaimer_payload,
    fee_from_range,
    hook,
    utcnow,
)

DATA_PATH = Path(__file__).parent / "data" / "priority_schemes.json"

# Isolation: this module is the only scheme source for /v1/licensing/check.
# Do not import app.HMO_LICENSING_LOOKUP, STR_LICENSING_RULES, or Wales rows.


def _norm(name: str) -> str:
    text = (name or "").lower()
    text = re.sub(r"\b(city|metropolitan|borough|council|london borough of|royal borough of)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _ward_key(name: str) -> str:
    """Normalise ward names across councils and postcodes.io
    ("St Edward's" == "St Edwards", "Rainham & Wennington" == "Rainham and Wennington")."""
    text = (name or "").lower().replace("&", " and ")
    text = re.sub(r"['\u2019]", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _is_england_la_code(code: str) -> bool:
    return (code or "").strip().upper().startswith("E")


def stale_after_days_for_tier(tier: str) -> int:
    if (tier or "priority").lower() == "priority":
        return SCHEME_STALE_AFTER_DAYS_PRIORITY
    return SCHEME_STALE_AFTER_DAYS_COVERED


@dataclass
class SchemeCoverage:
    kind: str  # citywide | designated_areas | unknown
    spatial_resolution: str  # none | la | named_areas | wards
    named_areas: list[str] = field(default_factory=list)
    notes: Optional[str] = None
    # Wards added to a designation later than the scheme itself: {ward: YYYY-MM-DD}.
    ward_start_dates: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "spatial_resolution": self.spatial_resolution,
            "named_areas": list(self.named_areas),
            "ward_start_dates": dict(self.ward_start_dates),
            "boundary_geojson": None,
            "notes": self.notes,
        }


@dataclass
class LicenceScheme:
    la_code: str
    la_name: str
    scheme_type: str  # additional | selective | unknown
    coverage: SchemeCoverage
    confidence: float
    last_verified_at: Optional[str]
    sources: list[Source]
    status: str = "active"
    coverage_tier: str = "priority"  # priority (30d) | covered (90d)
    term_years: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    fee_range: Optional[str] = None
    occupants_threshold: Optional[str] = None
    curator_notes: Optional[str] = None
    verification_method: Optional[str] = None

    def stale_after_days(self) -> int:
        return stale_after_days_for_tier(self.coverage_tier)

    def to_dict(self) -> dict[str, Any]:
        return {
            "la_code": self.la_code,
            "la_name": self.la_name,
            "scheme_type": self.scheme_type,
            "status": self.status,
            "coverage_tier": self.coverage_tier,
            "coverage": self.coverage.to_dict(),
            "confidence": round(self.confidence, 3),
            "confidence_band": confidence_band(self.confidence),
            "last_verified_at": self.last_verified_at,
            "freshness": component_freshness(
                self.last_verified_at,
                stale_after_days=self.stale_after_days(),
                basis="curated_seed",
                notes=self.verification_method,
            ).to_dict(),
            "term_years": self.term_years,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "fee_range": self.fee_range,
            "occupants_threshold": self.occupants_threshold,
            "curator_notes": self.curator_notes,
            "verification_method": self.verification_method,
            "sources": [s.to_dict() for s in self.sources],
        }


def _parse_scheme(raw: dict[str, Any]) -> Optional[LicenceScheme]:
    la_code = (raw.get("la_code") or "").strip()
    if not _is_england_la_code(la_code):
        return None
    cov = raw.get("coverage") or {}
    sources = [
        Source(
            name=s.get("name") or "source",
            kind=s.get("kind") or "curated_seed",
            url=s.get("url"),
            note=s.get("note"),
        )
        for s in (raw.get("sources") or [])
    ]
    return LicenceScheme(
        la_code=la_code,
        la_name=raw["la_name"],
        scheme_type=raw.get("scheme_type") or "unknown",
        status=raw.get("status") or "active",
        coverage_tier=raw.get("coverage_tier") or "priority",
        coverage=SchemeCoverage(
            kind=cov.get("kind") or "unknown",
            spatial_resolution=cov.get("spatial_resolution") or "none",
            named_areas=list(cov.get("named_areas") or []),
            notes=cov.get("notes"),
            ward_start_dates=dict(cov.get("ward_start_dates") or {}),
        ),
        confidence=float(raw.get("confidence") or 0.5),
        last_verified_at=raw.get("last_verified_at"),
        sources=sources,
        term_years=raw.get("term_years"),
        start_date=raw.get("start_date"),
        end_date=raw.get("end_date"),
        fee_range=raw.get("fee_range"),
        occupants_threshold=raw.get("occupants_threshold"),
        curator_notes=raw.get("curator_notes"),
        verification_method=raw.get("verification_method"),
    )


@lru_cache(maxsize=1)
def load_priority_schemes(path: Optional[str] = None) -> list[LicenceScheme]:
    target = Path(path) if path else DATA_PATH
    payload = json.loads(target.read_text(encoding="utf-8"))
    schemes = []
    for row in payload.get("schemes") or []:
        parsed = _parse_scheme(row)
        if parsed is not None:
            schemes.append(parsed)
    return schemes


def schemes_meta(path: Optional[str] = None) -> dict[str, Any]:
    target = Path(path) if path else DATA_PATH
    payload = json.loads(target.read_text(encoding="utf-8"))
    meta = dict(payload.get("meta") or {})
    schemes = payload.get("schemes") or []
    england = [s for s in schemes if _is_england_la_code(s.get("la_code") or "")]
    priority_las = meta.get("priority_las") or []
    meta["scheme_count"] = len(england)
    meta["la_count"] = len(priority_las) if priority_las else len({s.get("la_code") for s in england})
    meta["stale_slo_days"] = {
        "priority": SCHEME_STALE_AFTER_DAYS_PRIORITY,
        "covered": SCHEME_STALE_AFTER_DAYS_COVERED,
    }
    return meta


def match_schemes(
    *,
    la_code: str,
    la_name: str,
    path: Optional[str] = None,
) -> list[LicenceScheme]:
    """Match by ONS LA code first, then normalised name. England codes only."""
    code = (la_code or "").strip().upper()
    if not _is_england_la_code(code):
        return []
    schemes = [s for s in load_priority_schemes(path) if _is_england_la_code(s.la_code)]
    by_code = [s for s in schemes if s.la_code.upper() == code]
    if by_code:
        return by_code
    needle = _norm(la_name)
    if not needle:
        return []
    hits = []
    for scheme in schemes:
        key = _norm(scheme.la_name)
        if needle == key or needle in key or key in needle:
            hits.append(scheme)
    seen: set[tuple[str, str]] = set()
    unique: list[LicenceScheme] = []
    for s in hits:
        k = (s.la_code, s.scheme_type)
        if k in seen:
            continue
        seen.add(k)
        unique.append(s)
    return unique


def scheme_flags(
    schemes: list[LicenceScheme],
    *,
    occupants: Optional[int],
    intended_use: str,
    admin_ward: Optional[str],
) -> list[Flag]:
    flags: list[Flag] = []
    use = (intended_use or "unknown").lower()
    rentalish = use in ("hmo", "btl", "sa", "str", "rental", "unknown", "")

    if not schemes:
        flags.append(
            Flag(
                id="local_schemes_unseeded",
                category="licensing",
                title="No curated additional/selective scheme for this LA",
                summary=(
                    "This local authority is not in the priority seed, or only has an "
                    "uncurated placeholder. That is not evidence there is no additional "
                    "or selective licensing. Check the council's private-rented licensing pages."
                ),
                severity="compliance_cost",
                applies="possible",
                confidence=0.35,
                sources=[
                    Source(
                        name="Metalyzi priority scheme seed",
                        kind="curated_seed",
                        note="Seed is intentionally incomplete. Do not treat a miss as 'no scheme'.",
                    )
                ],
                analyse_hooks=[
                    hook("licence.additional_hmo", "licence", "compliance_cost"),
                    hook("licence.selective", "licence", "compliance_cost"),
                    hook("verify.lpa", "verify", "info"),
                ],
                last_verified_at=None,
                freshness=component_freshness(
                    None,
                    stale_after_days=SCHEME_STALE_AFTER_DAYS_COVERED,
                    basis="seed_miss",
                    notes="LA not present in priority_schemes.json (90d covered SLO).",
                ),
                spatial_resolution="none",
            )
        )
        return flags

    today = utcnow().date().isoformat()
    for scheme in schemes:
        if scheme.end_date and scheme.end_date < today:
            continue  # designation has ended
        flags.append(
            _flag_for_scheme(
                scheme,
                occupants=occupants,
                rentalish=rentalish,
                admin_ward=admin_ward,
                single_household=use in ("btl", "sa", "str"),
            )
        )
    return flags


def _flag_for_scheme(
    scheme: LicenceScheme,
    *,
    occupants: Optional[int],
    rentalish: bool,
    admin_ward: Optional[str],
    single_household: bool = False,
) -> Flag:
    slo = scheme.stale_after_days()
    citywide = scheme.coverage.kind == "citywide"
    designated = scheme.coverage.kind == "designated_areas"
    by_ward = designated and scheme.coverage.spatial_resolution == "wards"
    ward_match: Optional[bool] = None
    if by_ward and admin_ward:
        ward_match = _ward_key(admin_ward) in {_ward_key(n) for n in scheme.coverage.named_areas}

    if scheme.status == "proposed":
        return _proposed_scheme_flag(scheme, slo)

    if citywide:
        applies = "yes" if rentalish else "possible"
        spatial = "local_authority"
        confidence = min(scheme.confidence, 0.70)
    elif ward_match is not None:
        # Council designations are by ward and postcodes.io gives the current
        # ward, so this is an address-level answer (not a named-area guess).
        applies = ("yes" if rentalish else "possible") if ward_match else "no"
        spatial = "ward"
        confidence = min(scheme.confidence, 0.8) if ward_match else min(scheme.confidence, 0.65)
    elif designated:
        applies = "possible"
        spatial = "named_areas_only"
        if admin_ward and any(
            _norm(admin_ward) == _norm(n) or _norm(admin_ward) in _norm(n)
            for n in scheme.coverage.named_areas
        ):
            confidence = min(scheme.confidence, 0.58)
        else:
            confidence = min(scheme.confidence, 0.45)
    else:
        applies = "possible"
        spatial = "none"
        confidence = min(scheme.confidence, 0.40)

    fee = fee_from_range(
        kind="hmo_licence" if scheme.scheme_type != "selective" else "selective_licence",
        range_text=scheme.fee_range,
        term_years=scheme.term_years,
        include_in_cashflow=True,
        confidence=0.4 if scheme.fee_range else 0.0,
    )

    if scheme.scheme_type == "unknown":
        return Flag(
            id="priority_la_uncurated",
            category="licensing",
            title=f"Priority LA — scheme not yet curated ({scheme.la_name})",
            summary=(
                f"{scheme.la_name} is on the priority list but additional/selective "
                "designations have not been curated. Do not invent coverage. Verify with the LPA."
            ),
            detail=scheme.curator_notes,
            severity="soft_warning",
            applies="possible",
            confidence=min(confidence, 0.35),
            sources=list(scheme.sources),
            analyse_hooks=[
                hook("licence.additional_hmo", "licence", "soft_warning"),
                hook("licence.selective", "licence", "soft_warning"),
                hook("verify.lpa", "verify", "info"),
            ],
            last_verified_at=scheme.last_verified_at,
            freshness=component_freshness(
                scheme.last_verified_at,
                stale_after_days=slo,
                basis="curated_seed",
                notes=scheme.verification_method,
            ),
            spatial_resolution="none",
        )

    if scheme.scheme_type == "additional":
        flag_id = "additional_hmo_licence"
        title = f"Additional HMO licensing — {scheme.la_name}"
        if single_household and (occupants is None or occupants < 3):
            # Additional licensing only covers HMOs. A single-household let or
            # holiday let is outside it unless it becomes a shared house.
            summary_extra = (
                " Not needed for a single-household let or holiday let. It applies if "
                "you let to 3+ people from 2+ households."
            )
            severity = "info"
            applies = "no"
        elif occupants is not None and occupants >= 5:
            summary_extra = (
                " Occupancy is already at/above the mandatory threshold; additional "
                "licensing is secondary to the mandatory HMO licence."
            )
            severity = "soft_warning"
        elif occupants is not None and occupants < 3:
            summary_extra = (
                " Occupancy is below typical additional-HMO size (3–4). Confirm whether "
                "the property is still an HMO on household grounds."
            )
            severity = "soft_warning"
            applies = "possible"
        else:
            summary_extra = ""
            severity = "compliance_cost"
        area_bit = (
            "citywide / borough-wide designation"
            if citywide
            else _designated_area_bit(scheme, admin_ward, ward_match)
        )
        summary = (
            f"Curated additional HMO licensing scheme for {scheme.la_name} "
            f"({area_bit}).{summary_extra}"
        )
        hooks = [
            hook("licence.additional_hmo", "licence", severity, fee=fee),
            hook(
                "cost.hmo_licence_fee",
                "cost",
                "compliance_cost",
                summary=f"Seed fee range: {scheme.fee_range}" if scheme.fee_range else "Fee not in seed.",
                fee=fee,
            ),
            hook("verify.lpa", "verify", "info"),
        ]
        if designated:
            hooks.append(hook("verify.scheme_boundary", "verify", "soft_warning"))
    else:
        flag_id = "selective_licence"
        title = f"Selective licensing — {scheme.la_name}"
        severity = "compliance_cost"
        area_bit = (
            "covers all private rented properties in the LA (citywide / borough-wide)"
            if citywide
            else _designated_area_bit(scheme, admin_ward, ward_match)
        )
        summary = (
            f"Curated selective licensing scheme for {scheme.la_name}: {area_bit}. "
            "Selective licensing applies to privately rented homes, not only HMOs."
        )
        hooks = [
            hook("licence.selective", "licence", "compliance_cost", fee=fee),
            hook(
                "cost.selective_licence_fee",
                "cost",
                "compliance_cost",
                summary=f"Seed fee range: {scheme.fee_range}" if scheme.fee_range else "Fee not in seed.",
                fee=fee,
            ),
            hook("verify.lpa", "verify", "info"),
        ]
        if designated:
            hooks.append(hook("verify.scheme_boundary", "verify", "soft_warning"))

    today = utcnow().date().isoformat()
    if scheme.start_date and scheme.start_date > today:
        summary += f" Designated but not yet in force: licences are required from {scheme.start_date}."
    if ward_match and admin_ward:
        ward_start = {_ward_key(k): v for k, v in scheme.coverage.ward_start_dates.items()}.get(_ward_key(admin_ward))
        if ward_start and ward_start > today:
            summary += f" {admin_ward} ward joins the scheme on {ward_start}; licences are required from then."
    if scheme.end_date:
        summary += f" Designation runs until {scheme.end_date}."

    if scheme.fee_range:
        summary += f" Seed fee range (unverified): {scheme.fee_range}."

    freshness = component_freshness(
        scheme.last_verified_at,
        stale_after_days=slo,
        basis="curated_seed",
        notes=f"{scheme.verification_method or 'curated_seed'}; SLO {slo}d ({scheme.coverage_tier})",
    )
    if freshness.stale:
        summary += (
            f" Seed last_verified_at is stale against the {slo}-day "
            f"{scheme.coverage_tier} SLO — treat as a soft warning, not a green light."
        )
        severity = "soft_warning"

    return Flag(
        id=flag_id,
        category="licensing",
        title=title,
        summary=summary.strip(),
        detail=scheme.curator_notes,
        severity=severity,  # type: ignore[arg-type]
        deal_impact=severity,  # type: ignore[arg-type]
        applies=applies,  # type: ignore[arg-type]
        confidence=confidence,
        sources=list(scheme.sources)
        + [
            Source(
                name="Metalyzi priority scheme seed",
                kind="curated_seed",
                note=scheme.verification_method
                or "Manual seed. Not a spatial join. Do not invent boundaries from named areas.",
            )
        ],
        analyse_hooks=hooks,
        last_verified_at=scheme.last_verified_at,
        freshness=freshness,
        spatial_resolution=spatial,
    )


def seed_inventory() -> dict[str, Any]:
    schemes = load_priority_schemes()
    by_la: dict[str, list[str]] = {}
    for s in schemes:
        by_la.setdefault(s.la_code, []).append(s.scheme_type)
    return {
        "ok": True,
        "meta": schemes_meta(),
        "disclaimer": disclaimer_payload(),
        "local_authorities": [
            {"la_code": code, "scheme_types": types} for code, types in sorted(by_la.items())
        ],
    }


def _designated_area_bit(
    scheme: LicenceScheme,
    admin_ward: Optional[str],
    ward_match: Optional[bool],
) -> str:
    areas = scheme.coverage.named_areas
    listed = f" ({', '.join(areas[:16])}{', ...' if len(areas) > 16 else ''})" if areas else ""
    if ward_match is True:
        return f"designated wards{listed}; this address is in {admin_ward} ward, which is covered"
    if ward_match is False:
        return f"designated wards{listed}; this address is in {admin_ward} ward, which is not covered"
    return (
        f"designated areas only{listed} — address-level membership is not resolved "
        "(no official boundary in this seed)"
    )


def _proposed_scheme_flag(scheme: LicenceScheme, slo: int) -> Flag:
    kind = "Additional HMO" if scheme.scheme_type == "additional" else "Selective"
    flag_id = "additional_hmo_licence" if scheme.scheme_type == "additional" else "selective_licence"
    fee = fee_from_range(
        kind="hmo_licence" if scheme.scheme_type == "additional" else "selective_licence",
        range_text=scheme.fee_range,
        term_years=scheme.term_years,
        include_in_cashflow=False,  # not in force yet
        confidence=0.3 if scheme.fee_range else 0.0,
    )
    area = "borough-wide" if scheme.coverage.kind == "citywide" else "in named areas"
    summary = (
        f"{scheme.la_name} has proposed {kind.lower()} licensing {area}. It is not in force"
        + (f"; proposed fee {scheme.fee_range}" if scheme.fee_range else "")
        + ". If approved it would apply to lets in the scheme, so check the council's "
        "decision before you buy."
    )
    return Flag(
        id=flag_id,
        category="licensing",
        title=f"{kind} licensing proposed — {scheme.la_name}",
        summary=summary,
        detail=scheme.curator_notes,
        severity="soft_warning",
        deal_impact="soft_warning",
        applies="possible",
        confidence=min(scheme.confidence, 0.5),
        sources=list(scheme.sources),
        analyse_hooks=[
            hook(f"licence.{'additional_hmo' if scheme.scheme_type == 'additional' else 'selective'}", "licence", "soft_warning", fee=fee),
            hook("verify.lpa", "verify", "info"),
        ],
        last_verified_at=scheme.last_verified_at,
        freshness=component_freshness(
            scheme.last_verified_at,
            stale_after_days=slo,
            basis="curated_seed",
            notes=scheme.verification_method,
        ),
        spatial_resolution="local_authority" if scheme.coverage.kind == "citywide" else "named_areas_only",
    )
