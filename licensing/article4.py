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


def _parse_entity(raw: dict[str, Any]) -> Article4Entity:
    relevant, reason = classify_hmo_relevance(raw)
    return Article4Entity(
        entity=raw.get("entity"),
        name=raw.get("name"),
        reference=raw.get("reference"),
        notes=raw.get("notes"),
        description=raw.get("description"),
        permitted_development_rights=raw.get("permitted-development-rights"),
        start_date=raw.get("start-date") or None,
        end_date=raw.get("end-date") or None,
        entry_date=raw.get("entry-date") or None,
        organisation_entity=raw.get("organisation-entity"),
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
        "field": [
            "name",
            "reference",
            "notes",
            "description",
            "permitted-development-rights",
            "start-date",
            "end-date",
            "entry-date",
            "organisation-entity",
            "entity",
        ],
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
) -> list[Flag]:
    """Build Article 4 flags from Planning Data plus optional district index."""
    flags: list[Flag] = []
    src = planning_data_source()
    fetched = result.fetched_at
    freshness = component_freshness(
        fetched,
        stale_after_days=ARTICLE4_STALE_AFTER_DAYS,
        basis="live_lookup" if result.ok else "lookup_failed",
        notes=result.note,
    )

    if result.hmo_hits:
        primary = result.hmo_hits[0]
        names = "; ".join(
            (h.name or h.reference or f"entity {h.entity}") for h in result.hmo_hits[:4]
        )
        flags.append(
            Flag(
                id="article4_hmo",
                category="planning",
                title="Article 4 (HMO / C3→C4) indicated at this point",
                summary=(
                    f"Planning Data geometry covers this coordinate with "
                    f"{len(result.hmo_hits)} HMO-related Article 4 area(s): {names}. "
                    "C3→C4 permitted development is likely removed — full planning "
                    "permission is the safe assumption."
                ),
                detail=primary.relevance_reason,
                severity="high",
                applies="yes",
                confidence=result.confidence,
                sources=[src],
                analyse_hooks=[
                    "planning.article4_hmo",
                    "planning.c3_to_c4",
                    "blocker.planning_permission",
                    "verify.lpa",
                ],
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
                severity="low",
                applies="possible",
                confidence=result.confidence,
                sources=[src],
                analyse_hooks=["planning.article4_other", "verify.lpa"],
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
                severity="medium",
                applies="possible",
                confidence=result.confidence,
                sources=[src],
                analyse_hooks=["planning.article4_hmo", "verify.lpa"],
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
                severity="medium",
                applies="possible",
                confidence=0.0,
                sources=[src],
                analyse_hooks=["planning.article4_hmo", "verify.lpa"],
                last_verified_at=fetched,
                freshness=freshness,
                spatial_resolution="unknown",
            )
        )

    if district_fallback:
        flags.extend(_district_fallback_flags(district_fallback, result))

    return flags


def _district_fallback_flags(
    fallback: dict[str, Any],
    planning_result: Article4Result,
) -> list[Flag]:
    """Optional postcode-district index — not a legal boundary."""
    if not fallback.get("known"):
        return []
    active = bool(fallback.get("is_article_4") or fallback.get("isArticle4"))
    council = fallback.get("council") or "Local planning authority"
    note = fallback.get("note") or fallback.get("advice") or ""
    # If Planning Data already gave an HMO hit, the district index is corroboration only.
    if planning_result.hmo_hits and active:
        applies: str = "yes"
        severity = "info"
        confidence = 0.55
        title = "District index corroborates HMO Article 4"
        summary = (
            f"In-repo postcode-district index also marks this outward code as Article 4 "
            f"({council}). Spatial resolution is district, not the property."
        )
    elif planning_result.hmo_hits:
        return []
    elif active:
        applies = "possible"
        severity = "high"
        confidence = 0.55
        title = "District index indicates HMO Article 4 (not address-level)"
        summary = (
            f"The in-repo postcode-district index marks this outward code as Article 4 "
            f"for {council}. This is not a polygon boundary and must not be treated as "
            f"address-level proof. {note}"
        ).strip()
    else:
        return []

    return [
        Flag(
            id="article4_hmo_district_index",
            category="planning",
            title=title,
            summary=summary,
            severity=severity,
            applies=applies,  # type: ignore[arg-type]
            confidence=confidence,
            sources=[
                Source(
                    name="Metalyzi postcode-district Article 4 index",
                    kind="district_index",
                    note="District-level only. Not a legal boundary. Do not invent polygons from this.",
                )
            ],
            analyse_hooks=["planning.article4_hmo", "verify.lpa", "verify.scheme_boundary"],
            last_verified_at=None,
            freshness=component_freshness(
                None,
                stale_after_days=ARTICLE4_STALE_AFTER_DAYS,
                basis="curated_index",
                notes="No last_verified_at on the district index — treat as stale until curator-confirmed.",
            ),
            spatial_resolution="postcode_district",
        )
    ]
