"""Article 4 ingest from planning.data.gov.uk.

Coverage is partial (MHCLG beta; not every LPA publishes). Absence of a
hit is NOT evidence that no Article 4 direction exists. HMO-relevance is
classified from permitted-development-rights / text (Class L / C3–C4 / HMO).

Geometries are evaluated server-side by the Planning Data API (point in
polygon). This module does not invent or store boundaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import requests

from licensing.models import (
    ARTICLE4_REGISTER_STALE_AFTER_DAYS,
    ARTICLE4_STALE_AFTER_DAYS,
    Flag,
    Source,
    component_freshness,
    isoformat,
    utcnow,
)

PLANNING_DATA_URL = "https://www.planning.data.gov.uk/entity.json"
PLANNING_DATA_DATASET = "https://www.planning.data.gov.uk/dataset/article-4-direction-area"
USER_AGENT = "MetalyziLicensing/0.1 (+https://metalyzi.co.uk)"

Fetcher = Callable[[str, dict[str, Any]], dict[str, Any]]

HMO_TEXT_RE = re.compile(
    r"\b(hmo|houses?\s+in\s+multiple\s+occupation|use class c4|\bc4\b|c3\s*.*\s*c4|c3 to c4)\b",
    re.IGNORECASE,
)
CLASS_L_RE = re.compile(r"\b(3l|class\s*l|part\s*3\s*class\s*l)\b", re.IGNORECASE)


class Article4Error(Exception):
    def __init__(self, message: str, *, code: str = "article4_upstream_error"):
        super().__init__(message)
        self.code = code


@dataclass
class Article4Entity:
    entity: Optional[int]
    name: Optional[str]
    reference: Optional[str]
    notes: Optional[str]
    description: Optional[str]
    permitted_development_rights: Optional[str]
    start_date: Optional[str]
    end_date: Optional[str]
    entry_date: Optional[str]
    organisation_entity: Optional[int]
    hmo_relevant: bool
    relevance_reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity": self.entity,
            "name": self.name,
            "reference": self.reference,
            "notes": self.notes,
            "description": self.description,
            "permitted_development_rights": self.permitted_development_rights,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "entry_date": self.entry_date,
            "organisation_entity": self.organisation_entity,
            "hmo_relevant": self.hmo_relevant,
            "relevance_reason": self.relevance_reason,
            "url": f"https://www.planning.data.gov.uk/entity/{self.entity}" if self.entity else None,
        }


@dataclass
class Article4Result:
    queried: bool
    ok: bool
    coverage: str
    hits: list[Article4Entity] = field(default_factory=list)
    hmo_hits: list[Article4Entity] = field(default_factory=list)
    error: Optional[str] = None
    fetched_at: Optional[str] = None
    confidence: float = 0.0
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "queried": self.queried,
            "ok": self.ok,
            "coverage": self.coverage,
            "hit_count": len(self.hits),
            "hmo_hit_count": len(self.hmo_hits),
            "hits": [h.to_dict() for h in self.hits],
            "confidence": round(self.confidence, 3),
            "error": self.error,
            "fetched_at": self.fetched_at,
            "note": self.note,
            "source": PLANNING_DATA_DATASET,
        }


def planning_data_source() -> Source:
    return Source(
        name="planning.data.gov.uk article-4-direction-area",
        kind="planning_data",
        url=PLANNING_DATA_DATASET,
        note="MHCLG Planning Data beta. Incomplete LPA coverage; absence ≠ no Article 4.",
    )


def classify_hmo_relevance(entity: dict[str, Any]) -> tuple[bool, str]:
    pdr = str(entity.get("permitted-development-rights") or "")
    blob = " ".join(
        str(entity.get(k) or "")
        for k in ("name", "notes", "description", "permitted-development-rights")
    )
    if CLASS_L_RE.search(pdr) or CLASS_L_RE.search(blob):
        return True, "permitted-development-rights / text matches GPDO Part 3 Class L (C3↔C4)"
    if HMO_TEXT_RE.search(blob):
        return True, "name/notes/description refers to HMO or C3–C4"
    if pdr.strip():
        return False, "has permitted-development-rights but not Class L / HMO"
    return False, "insufficient text to classify as HMO-related"


def _blank(value: Any) -> Any:
    if value is None or value == "":
        return None
    return value


def _parse_entity(raw: dict[str, Any]) -> Article4Entity:
    relevant, reason = classify_hmo_relevance(raw)
    return Article4Entity(
        entity=raw.get("entity"),
        name=_blank(raw.get("name")),
        reference=_blank(raw.get("reference")),
        notes=_blank(raw.get("notes")),
        description=_blank(raw.get("description")),
        permitted_development_rights=_blank(raw.get("permitted-development-rights")),
        start_date=_blank(raw.get("start-date")),
        end_date=_blank(raw.get("end-date")),
        entry_date=_blank(raw.get("entry-date")),
        organisation_entity=_blank(raw.get("organisation-entity")),
        hmo_relevant=relevant,
        relevance_reason=reason,
    )


def _default_fetch(url: str, params: dict[str, Any]) -> dict[str, Any]:
    response = requests.get(
        url,
        params=params,
        timeout=12,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    if response.status_code != 200:
        raise Article4Error(
            f"planning.data.gov.uk returned HTTP {response.status_code}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise Article4Error("planning.data.gov.uk returned non-JSON") from exc


def ingest_article4_for_point(
    latitude: float,
    longitude: float,
    *,
    fetcher: Optional[Fetcher] = None,
    now=None,
) -> Article4Result:
    """Query Article 4 direction areas whose geometry covers this WGS84 point."""
    fetched_at = isoformat(now or utcnow())
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "dataset": "article-4-direction-area",
        "limit": 50,
        # Restricting `field=` blanks start-date / organisation-entity on this API.
        # Drop bulky geometry only so dates and PD-rights stay populated.
        "exclude_field": ["geometry", "point"],
    }
    fetch = fetcher or _default_fetch
    coverage_note = (
        "Planning Data Article 4 coverage is partial (beta, not all LPAs). "
        "A miss must not be treated as 'no Article 4'."
    )
    try:
        payload = fetch(PLANNING_DATA_URL, params)
    except Article4Error as exc:
        return Article4Result(
            queried=True,
            ok=False,
            coverage="partial_unknown",
            error=str(exc),
            fetched_at=fetched_at,
            confidence=0.0,
            note=coverage_note,
        )
    except requests.RequestException as exc:
        return Article4Result(
            queried=True,
            ok=False,
            coverage="partial_unknown",
            error=f"planning.data.gov.uk request failed: {exc}",
            fetched_at=fetched_at,
            confidence=0.0,
            note=coverage_note,
        )

    raw_entities = payload.get("entities") if isinstance(payload, dict) else None
    if not isinstance(raw_entities, list):
        return Article4Result(
            queried=True,
            ok=False,
            coverage="partial_unknown",
            error="unexpected payload",
            fetched_at=fetched_at,
            confidence=0.0,
            note=coverage_note,
        )

    hits = [_parse_entity(e) for e in raw_entities if isinstance(e, dict)]
    hmo_hits = [h for h in hits if h.hmo_relevant]

    if hmo_hits:
        confidence = 0.80
        coverage = "partial_hit_hmo"
    elif hits:
        confidence = 0.50
        coverage = "partial_hit_other"
    else:
        confidence = 0.30
        coverage = "partial_miss"

    return Article4Result(
        queried=True,
        ok=True,
        coverage=coverage,
        hits=hits,
        hmo_hits=hmo_hits,
        fetched_at=fetched_at,
        confidence=confidence,
        note=coverage_note,
    )


def article4_flags(
    result: Article4Result,
    *,
    district_fallback: Optional[dict[str, Any]] = None,
    conversion_from_c3: Optional[bool] = None,
    intended_use: str = "unknown",
) -> list[Flag]:
    """Build Article 4 flags from Planning Data plus optional district index.

    conversion_from_c3=True is an explicit C3→C4 conversion play (deal_killer on hit).
    conversion_from_c3=False means continued use — the direction exists but is not
    a conversion blocker. None + intended_use in {hmo, c4, sui_generis} is
    treated as conversion-relevant.
    """
    from licensing.models import hook

    flags: list[Flag] = []
    src = planning_data_source()
    fetched = result.fetched_at
    freshness = component_freshness(
        fetched,
        stale_after_days=ARTICLE4_STALE_AFTER_DAYS,
        basis="live_lookup" if result.ok else "lookup_failed",
        notes=result.note,
    )
    conversion_play = _is_conversion_play(conversion_from_c3, intended_use)

    if result.hmo_hits:
        primary = result.hmo_hits[0]
        names = "; ".join(
            (h.name or h.reference or f"entity {h.entity}") for h in result.hmo_hits[:4]
        )
        if conversion_from_c3 is False:
            severity = "info"
            applies = "yes"
            title = "Article 4 (HMO / C3→C4) present — not a conversion play"
            summary = (
                f"Planning Data covers this point with {len(result.hmo_hits)} HMO-related "
                f"Article 4 area(s): {names}. conversion_from_c3 is false, so this is "
                "not treated as a C3→C4 planning blocker for continued use."
            )
            hooks = [
                hook("planning.article4_hmo", "planning", "info"),
                hook("planning.c3_to_c4", "planning", "info"),
                hook("verify.lpa", "verify", "info"),
            ]
        elif conversion_play:
            severity = "deal_killer"
            applies = "yes"
            title = "Article 4 (HMO / C3→C4) blocks permitted development"
            summary = (
                f"Planning Data geometry covers this coordinate with "
                f"{len(result.hmo_hits)} HMO-related Article 4 area(s): {names}. "
                "C3→C4 permitted development is removed — full planning permission "
                "is required for a conversion play."
            )
            hooks = [
                hook("planning.article4_hmo", "planning", "deal_killer"),
                hook("planning.c3_to_c4", "planning", "deal_killer"),
                hook("blocker.planning_permission", "blocker", "deal_killer"),
                hook("verify.lpa", "verify", "info"),
            ]
        else:
            severity = "compliance_cost"
            applies = "yes"
            title = "Article 4 (HMO / C3→C4) indicated at this point"
            summary = (
                f"Planning Data geometry covers this coordinate with "
                f"{len(result.hmo_hits)} HMO-related Article 4 area(s): {names}. "
                "If this is a C3→C4 conversion, planning permission is required. "
                "Pass conversion_from_c3 to classify the play."
            )
            hooks = [
                hook("planning.article4_hmo", "planning", "compliance_cost"),
                hook("planning.c3_to_c4", "planning", "compliance_cost"),
                hook("blocker.planning_permission", "blocker", "deal_killer"),
                hook("verify.lpa", "verify", "info"),
            ]
        flags.append(
            Flag(
                id="article4_hmo",
                category="planning",
                title=title,
                summary=summary,
                detail=primary.relevance_reason,
                severity=severity,
                deal_impact=severity,
                applies=applies,
                confidence=result.confidence,
                sources=[src],
                analyse_hooks=hooks,
                last_verified_at=fetched,
                freshness=freshness,
                spatial_resolution="point_in_polygon",
            )
        )
    elif result.ok and result.hits:
        flags.append(
            Flag(
                id="article4_hmo",
                category="planning",
                title="Article 4 area(s) at this point — not classified as HMO",
                summary=(
                    f"{len(result.hits)} Article 4 direction area(s) cover this "
                    "coordinate but none were classified as Class L / HMO / C3–C4. "
                    "They may still affect other PD rights. Verify with the LPA."
                ),
                severity="soft_warning",
                applies="possible",
                confidence=result.confidence,
                sources=[src],
                analyse_hooks=[
                    hook("planning.article4_other", "planning", "soft_warning"),
                    hook("verify.lpa", "verify", "info"),
                ],
                last_verified_at=fetched,
                freshness=freshness,
                spatial_resolution="point_in_polygon",
            )
        )
    elif result.ok:
        flags.append(
            Flag(
                id="article4_hmo",
                category="planning",
                title="No Planning Data Article 4 hit (coverage is partial)",
                summary=(
                    "planning.data.gov.uk returned no article-4-direction-area covering "
                    "this point. That is not evidence the LPA has no HMO Article 4 — "
                    "dataset coverage is incomplete. Verify with the local planning authority."
                ),
                severity="soft_warning" if not conversion_play else "compliance_cost",
                applies="possible",
                confidence=result.confidence,
                sources=[src],
                analyse_hooks=[
                    hook("planning.article4_hmo", "planning", "soft_warning"),
                    hook("verify.lpa", "verify", "info"),
                ],
                last_verified_at=fetched,
                freshness=freshness,
                spatial_resolution="point_in_polygon",
            )
        )
    else:
        flags.append(
            Flag(
                id="article4_hmo",
                category="planning",
                title="Article 4 lookup failed",
                summary=(
                    "Could not query planning.data.gov.uk. Article 4 status is unknown. "
                    f"{result.error or ''}"
                ).strip(),
                severity="compliance_cost",
                applies="possible",
                confidence=0.0,
                sources=[src],
                analyse_hooks=[
                    hook("planning.article4_hmo", "planning", "soft_warning"),
                    hook("verify.lpa", "verify", "info"),
                ],
                last_verified_at=fetched,
                freshness=freshness,
                spatial_resolution="unknown",
            )
        )

    if district_fallback:
        flags.extend(
            _district_fallback_flags(
                district_fallback,
                result,
                conversion_from_c3=conversion_from_c3,
                conversion_play=conversion_play,
            )
        )

    return flags


def _is_conversion_play(conversion_from_c3: Optional[bool], intended_use: str) -> bool:
    if conversion_from_c3 is True:
        return True
    if conversion_from_c3 is False:
        return False
    return (intended_use or "").lower() in {"hmo", "c4", "sui_generis"}


def _district_fallback_flags(
    fallback: dict[str, Any],
    planning_result: Article4Result,
    *,
    conversion_from_c3: Optional[bool] = None,
    conversion_play: bool = False,
) -> list[Flag]:
    """District-level Article 4 evidence — never an address-level boundary.

    Two sources, labelled for what they are:
    - ``verified_register``: Supabase ``article4_areas``, council-checked and
      refreshed monthly. Carries a real last_verified_at.
    - ``static``: the legacy in-repo outward-code list. Unverified, so it can
      only raise a soft warning, never a deal killer.
    Must never be fed HMO_LICENSING_LOOKUP / Wales rows.
    """
    if not fallback.get("known"):
        return []
    if fallback.get("tier") or fallback.get("rent_smart_wales") or fallback.get("scope"):
        return []
    if fallback.get("source") == "verified_register":
        return _register_flags(fallback, planning_result, conversion_play=conversion_play)
    return _legacy_list_flags(fallback, planning_result)


def _district_flag(
    *,
    title: str,
    summary: str,
    severity: str,
    impact: str,
    applies: str,
    confidence: float,
    source: Source,
    last_verified_at: Optional[str],
    stale_after_days: int,
    basis: str,
    freshness_note: str,
) -> Flag:
    from licensing.models import hook

    return Flag(
        id="article4_hmo_district_index",
        category="planning",
        title=title,
        summary=summary,
        severity=severity,  # type: ignore[arg-type]
        deal_impact=impact,  # type: ignore[arg-type]
        applies=applies,  # type: ignore[arg-type]
        confidence=confidence,
        sources=[source],
        analyse_hooks=[
            hook("planning.article4_hmo", "planning", impact),  # type: ignore[arg-type]
            hook("verify.lpa", "verify", "info"),
            hook("verify.scheme_boundary", "verify", "soft_warning"),
        ],
        last_verified_at=last_verified_at,
        freshness=component_freshness(
            last_verified_at,
            stale_after_days=stale_after_days,
            basis=basis,
            notes=freshness_note,
        ),
        spatial_resolution="postcode_district",
    )


def _register_flags(
    fb: dict[str, Any],
    planning_result: Article4Result,
    *,
    conversion_play: bool,
) -> list[Flag]:
    council = fb.get("council") or "Local planning authority"
    district = fb.get("district") or "this district"
    status = str(fb.get("status") or "unknown")
    verified_on = str(fb.get("last_verified_at") or "")[:10] or "unknown date"
    confidence = 0.7 if fb.get("verified") else 0.5
    source = Source(
        name="Metalyzi verified Article 4 register",
        kind="verified_register",
        url=fb.get("url"),
        note="Council-checked monthly. District-level only, not a legal boundary.",
    )
    common = dict(
        source=source,
        last_verified_at=fb.get("last_verified_at"),
        stale_after_days=ARTICLE4_REGISTER_STALE_AFTER_DAYS,
        basis="verified_register",
        freshness_note=f"Council register row last verified {verified_on}; refreshed monthly.",
    )
    if status == "active" and fb.get("district_listed"):
        if planning_result.hmo_hits:
            return [_district_flag(
                title="Verified register corroborates HMO Article 4",
                summary=(
                    f"{council}'s HMO Article 4 area includes {district} (register verified "
                    f"{verified_on}). District-level, not the property itself."
                ),
                severity="info", impact="info", applies="yes", confidence=confidence, **common,
            )]
        impact = "deal_killer" if conversion_play else "compliance_cost"
        return [_district_flag(
            title="HMO Article 4 covers this postcode district",
            summary=(
                f"{council} has an HMO Article 4 direction that includes {district} "
                f"(register verified {verified_on}). C3→C4 conversion needs full planning "
                "permission. The register is district-level, so confirm the exact boundary "
                "for this address with the council."
            ),
            severity=impact, impact=impact, applies="possible", confidence=confidence, **common,
        )]
    if planning_result.hmo_hits:
        return []  # a Planning Data polygon hit outranks district-level evidence
    if status == "active":
        return [_district_flag(
            title="District is outside the council's HMO Article 4 area",
            summary=(
                f"{council}'s HMO Article 4 direction lists specific districts, and {district} "
                f"is not one of them (register verified {verified_on}). Boundaries are "
                "district-level, so confirm with the council before relying on this."
            ),
            severity="info", impact="info", applies="no", confidence=min(confidence, 0.6), **common,
        )]
    if status == "none":
        return [_district_flag(
            title="No HMO Article 4 direction for this council",
            summary=(
                f"{council} has no HMO Article 4 direction in force (register verified "
                f"{verified_on}). C3→C4 conversion is permitted development, subject to "
                "licensing and building regulations."
            ),
            severity="info", impact="info", applies="no", confidence=confidence, **common,
        )]
    if status in ("proposed", "consultation"):
        return [_district_flag(
            title="HMO Article 4 direction proposed",
            summary=(
                f"{council} has proposed an HMO Article 4 direction (register verified "
                f"{verified_on}). It is not yet in force, but a conversion may need planning "
                "permission by the time you complete. Check the council's timetable."
            ),
            severity="soft_warning", impact="soft_warning", applies="possible",
            confidence=min(confidence, 0.6), **common,
        )]
    return []


def _legacy_list_flags(fb: dict[str, Any], planning_result: Article4Result) -> list[Flag]:
    active = bool(fb.get("is_article_4") or fb.get("isArticle4"))
    if not active:
        return []  # unverified data never asserts "no Article 4"
    council = fb.get("council") or "Local planning authority"
    source = Source(
        name="Legacy in-repo Article 4 list (unverified)",
        kind="district_index",
        note="Outward-code list last edited in 2025. Not verified against council records.",
    )
    common = dict(
        source=source,
        last_verified_at=None,
        stale_after_days=ARTICLE4_STALE_AFTER_DAYS,
        basis="unverified_legacy_list",
        freshness_note="Unverified legacy list with no verification date.",
    )
    if planning_result.hmo_hits:
        return [_district_flag(
            title="Legacy list also marks this district as HMO Article 4",
            summary=(
                f"An unverified in-repo list also marks this outward code as Article 4 ({council})."
            ),
            severity="info", impact="info", applies="yes", confidence=0.35, **common,
        )]
    return [_district_flag(
        title="Unverified list suggests HMO Article 4 (check with the council)",
        summary=(
            f"An unverified in-repo list marks this outward code as Article 4 for {council}. "
            "It has not been checked against council records, so treat it as a prompt to "
            "check rather than a finding."
        ),
        severity="soft_warning", impact="soft_warning", applies="possible", confidence=0.35, **common,
    )]
