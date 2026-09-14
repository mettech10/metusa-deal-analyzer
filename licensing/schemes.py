"""Additional / selective licensing scheme model.

Seeds are curator-edited JSON. Boundaries are never invented: coverage is
`citywide`, `designated_areas` (named areas only), or `unknown`. Address-level
membership is not resolved without an official geometry (out of scope here).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from licensing.models import (
    HMO_LICENCE_STALE_AFTER_DAYS,
    Flag,
    Source,
    component_freshness,
    confidence_band,
    parse_iso,
)

DATA_PATH = Path(__file__).parent / "data" / "priority_schemes.json"


def _norm(name: str) -> str:
    text = (name or "").lower()
    text = re.sub(r"\b(city|metropolitan|borough|council|london borough of|royal borough of)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


@dataclass
class SchemeCoverage:
    kind: str  # citywide | designated_areas | unknown
    spatial_resolution: str  # none | la | named_areas
    named_areas: list[str] = field(default_factory=list)
    notes: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "spatial_resolution": self.spatial_resolution,
            "named_areas": list(self.named_areas),
            "boundary_geojson": None,
            "notes": self.notes,
        }


@dataclass
class LicenceScheme:
    la_code: str
    la_name: str
    scheme_type: str  # additional | selective
    coverage: SchemeCoverage
    confidence: float
    last_verified_at: Optional[str]
    sources: list[Source]
    status: str = "active"  # active | expired | proposed | unknown
    term_years: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    fee_range: Optional[str] = None
    occupants_threshold: Optional[str] = None
    curator_notes: Optional[str] = None
    verification_method: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "la_code": self.la_code,
            "la_name": self.la_name,
            "scheme_type": self.scheme_type,
            "status": self.status,
            "coverage": self.coverage.to_dict(),
            "confidence": round(self.confidence, 3),
            "confidence_band": confidence_band(self.confidence),
            "last_verified_at": self.last_verified_at,
            "freshness": component_freshness(
                self.last_verified_at,
                stale_after_days=HMO_LICENCE_STALE_AFTER_DAYS,
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


def _parse_scheme(raw: dict[str, Any]) -> LicenceScheme:
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
        la_code=raw["la_code"],
        la_name=raw["la_name"],
        scheme_type=raw["scheme_type"],
        status=raw.get("status") or "active",
        coverage=SchemeCoverage(
            kind=cov.get("kind") or "unknown",
            spatial_resolution=cov.get("spatial_resolution") or "none",
            named_areas=list(cov.get("named_areas") or []),
            notes=cov.get("notes"),
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
    return [_parse_scheme(row) for row in payload.get("schemes") or []]


def schemes_meta(path: Optional[str] = None) -> dict[str, Any]:
    target = Path(path) if path else DATA_PATH
    payload = json.loads(target.read_text(encoding="utf-8"))
    meta = dict(payload.get("meta") or {})
    meta["scheme_count"] = len(payload.get("schemes") or [])
    meta["la_count"] = len({s.get("la_code") for s in payload.get("schemes") or []})
    return meta


def match_schemes(
    *,
    la_code: str,
    la_name: str,
    path: Optional[str] = None,
) -> list[LicenceScheme]:
    """Match by ONS LA code first, then normalised name. No spatial join."""
    schemes = load_priority_schemes(path)
    code = (la_code or "").strip().upper()
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
    # Deduplicate by (la_code, scheme_type) if name matching is loose
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
                    "This local authority is not in the priority seed (~25 LAs). "
                    "That is not evidence there is no additional or selective licensing. "
                    "Check the council's private-rented licensing pages."
                ),
                severity="medium",
                applies="possible",
                confidence=0.35,
                sources=[
                    Source(
                        name="Metalyzi priority scheme seed",
                        kind="curated_seed",
                        note="Seed is intentionally incomplete. Do not treat a miss as 'no scheme'.",
                    )
                ],
                analyse_hooks=["licence.additional_hmo", "licence.selective", "verify.lpa"],
                last_verified_at=None,
                freshness=component_freshness(
                    None,
                    stale_after_days=HMO_LICENCE_STALE_AFTER_DAYS,
                    basis="seed_miss",
                    notes="LA not present in priority_schemes.json.",
                ),
                spatial_resolution="none",
            )
        )
        return flags

    for scheme in schemes:
        flags.append(_flag_for_scheme(scheme, occupants=occupants, rentalish=rentalish, admin_ward=admin_ward))
    return flags


def _flag_for_scheme(
    scheme: LicenceScheme,
    *,
    occupants: Optional[int],
    rentalish: bool,
    admin_ward: Optional[str],
) -> Flag:
    citywide = scheme.coverage.kind == "citywide"
    designated = scheme.coverage.kind == "designated_areas"

    if citywide:
        applies = "yes" if rentalish else "possible"
        spatial = "local_authority"
        confidence = min(scheme.confidence, 0.70)
    elif designated:
        applies = "possible"
        spatial = "named_areas_only"
        # Named ward match is a hint only — wards are not boundaries we own.
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

    if scheme.scheme_type == "additional":
        flag_id = "additional_hmo_licence"
        hooks = ["licence.additional_hmo", "cost.hmo_licence_fee", "verify.lpa"]
        title = f"Additional HMO licensing — {scheme.la_name}"
        if occupants is not None and occupants >= 5:
            summary_extra = (
                " Occupancy is already at/above the mandatory threshold; additional "
                "licensing is secondary to the mandatory HMO licence."
            )
            severity = "low"
        elif occupants is not None and occupants < 3:
            summary_extra = (
                " Occupancy is below typical additional-HMO size (3–4). Confirm whether "
                "the property is still an HMO on household grounds."
            )
            severity = "low"
            applies = "possible"
        else:
            summary_extra = ""
            severity = "high" if citywide else "medium"
        if designated:
            hooks.append("verify.scheme_boundary")
        area_bit = (
            "citywide / borough-wide designation"
            if citywide
            else (
                "designated areas only"
                + (f" ({', '.join(scheme.coverage.named_areas[:8])})" if scheme.coverage.named_areas else "")
                + " — address-level membership is not resolved (no official boundary in this seed)"
            )
        )
        summary = (
            f"Curated additional HMO licensing scheme for {scheme.la_name} "
            f"({area_bit}).{summary_extra}"
        )
    else:
        flag_id = "selective_licence"
        hooks = ["licence.selective", "cost.selective_licence_fee", "verify.lpa"]
        title = f"Selective licensing — {scheme.la_name}"
        severity = "high" if citywide else "medium"
        if designated:
            hooks.append("verify.scheme_boundary")
        area_bit = (
            "covers all private rented properties in the LA (citywide / borough-wide)"
            if citywide
            else (
                "designated areas only"
                + (f" ({', '.join(scheme.coverage.named_areas[:8])})" if scheme.coverage.named_areas else "")
                + " — address-level membership is not resolved"
            )
        )
        summary = (
            f"Curated selective licensing scheme for {scheme.la_name}: {area_bit}. "
            "Selective licensing applies to privately rented homes, not only HMOs."
        )

    if scheme.end_date:
        end = parse_iso(scheme.end_date)
        summary += f" Published designation end date (if still current): {scheme.end_date}."
        _ = end  # parsed for future expiry logic; curator must confirm

    if scheme.fee_range:
        summary += f" Seed fee range (unverified): {scheme.fee_range}."

    return Flag(
        id=flag_id if not _duplicate_id_needed(scheme) else f"{flag_id}_{scheme.la_code.lower()}",
        category="licensing",
        title=title,
        summary=summary.strip(),
        detail=scheme.curator_notes,
        severity=severity,  # type: ignore[arg-type]
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
        freshness=component_freshness(
            scheme.last_verified_at,
            stale_after_days=HMO_LICENCE_STALE_AFTER_DAYS,
            basis="curated_seed",
            notes=scheme.verification_method,
        ),
        spatial_resolution=spatial,
    )


def _duplicate_id_needed(scheme: LicenceScheme) -> bool:
    # Keep stable ids per type so analyse_hooks stay aggregatable. Engine
    # may emit both additional and selective for the same LA.
    return False


def seed_inventory() -> dict[str, Any]:
    schemes = load_priority_schemes()
    by_la: dict[str, list[str]] = {}
    for s in schemes:
        by_la.setdefault(s.la_code, []).append(s.scheme_type)
    return {
        "meta": schemes_meta(),
        "local_authorities": [
            {"la_code": code, "scheme_types": types} for code, types in sorted(by_la.items())
        ],
    }
