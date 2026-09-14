"""Shared types for the licensing checker.

Confidence and freshness are first-class: every flag and every data
component carries a 0–1 confidence, a band, a last_verified_at, and
an explicit stale signal. Callers must not infer freshness from
presence/absence of a field.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional

# deal_killer > compliance_cost > soft_warning > info
Severity = Literal["deal_killer", "compliance_cost", "soft_warning", "info"]
Applies = Literal["yes", "no", "possible", "conditional"]
ConfidenceBand = Literal["high", "medium", "low", "unknown"]
SourceKind = Literal[
    "legislation",
    "official_api",
    "planning_data",
    "curated_seed",
    "district_index",
    "geo",
]
HookKind = Literal[
    "licence",
    "planning",
    "cost",
    "blocker",
    "verify",
    "analyse",
    "scope",
    "ruleset",
]

STATUTE_VERIFIED_AT = "2018-10-01T00:00:00+00:00"  # 2018 HMO prescribed-description order

# Scheme stale SLOs (not 365d): priority LAs re-verify monthly; other covered rows quarterly.
SCHEME_STALE_AFTER_DAYS_PRIORITY = 30
SCHEME_STALE_AFTER_DAYS_COVERED = 90
ARTICLE4_STALE_AFTER_DAYS = 90
GEO_STALE_AFTER_DAYS = 30

DISCLAIMER_VERSION = "licensing-checker-disclaimer-v1"
DISCLAIMER_TEXT = (
    "Indicative England-only licensing and planning flags for research. "
    "Not legal advice, not a CON29, and not a substitute for the local authority. "
    "Confirm designations, maps, and fees with the LPA before acting. "
    "Absence of a hit is not evidence of no restriction unless a national "
    "statutory rule says so. UPRN is not resolved. Do not apply this output "
    "in Wales, Scotland, or Northern Ireland."
)

SEVERITY_RANK = {
    "deal_killer": 3,
    "compliance_cost": 2,
    "soft_warning": 1,
    "info": 0,
}

FEATURE_FLAG = "licensing_checker_v1"


def canonical_severity(value: Optional[str], *, category: str = "") -> Severity:
    """Map high|medium|low onto deal_killer|compliance_cost|soft_warning|info."""
    raw = (value or "info").strip().lower()
    if raw in SEVERITY_RANK:
        return raw  # type: ignore[return-value]
    if raw == "high":
        if category in {"planning", "scope", "blocker"}:
            return "deal_killer"
        return "compliance_cost"
    if raw == "medium":
        return "compliance_cost"
    if raw == "low":
        return "info"
    return "info"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def confidence_band(confidence: float) -> ConfidenceBand:
    if confidence >= 0.85:
        return "high"
    if confidence >= 0.55:
        return "medium"
    if confidence >= 0.30:
        return "low"
    return "unknown"


def is_stale(
    last_verified_at: Optional[str],
    *,
    stale_after_days: int,
    now: Optional[datetime] = None,
    never_stale: bool = False,
) -> bool:
    if never_stale:
        return False
    dt = parse_iso(last_verified_at)
    if dt is None:
        return True
    now = now or utcnow()
    return (now - dt).days > stale_after_days


def disclaimer_payload() -> dict[str, str]:
    return {"version": DISCLAIMER_VERSION, "text": DISCLAIMER_TEXT}


def worst_severity(levels: list[str]) -> Severity:
    if not levels:
        return "info"
    return max(levels, key=lambda s: SEVERITY_RANK.get(s, 0))  # type: ignore[return-value]


@dataclass
class Source:
    name: str
    kind: SourceKind
    url: Optional[str] = None
    note: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None}


@dataclass
class FeeHook:
    kind: str  # hmo_licence | selective_licence
    include_in_cashflow: bool
    range_text: Optional[str] = None
    min_gbp: Optional[int] = None
    max_gbp: Optional[int] = None
    term_years: Optional[int] = None
    currency: str = "GBP"
    known: bool = False
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None}


@dataclass
class AnalyseHook:
    id: str
    kind: HookKind
    deal_impact: Severity
    summary: Optional[str] = None
    fee: Optional[FeeHook] = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "deal_impact": self.deal_impact,
        }
        if self.summary:
            payload["summary"] = self.summary
        if self.fee:
            payload["fee"] = self.fee.to_dict()
        return payload


def hook(
    hook_id: str,
    kind: HookKind,
    deal_impact: Severity,
    summary: Optional[str] = None,
    fee: Optional[FeeHook] = None,
) -> AnalyseHook:
    return AnalyseHook(id=hook_id, kind=kind, deal_impact=deal_impact, summary=summary, fee=fee)


@dataclass
class Freshness:
    last_verified_at: Optional[str]
    stale: bool
    stale_after_days: Optional[int] = None
    basis: str = "observed"
    notes: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None}


@dataclass
class Flag:
    id: str
    category: str
    title: str
    summary: str
    severity: Severity
    applies: Applies
    confidence: float
    sources: list[Source] = field(default_factory=list)
    analyse_hooks: list[AnalyseHook] = field(default_factory=list)
    last_verified_at: Optional[str] = None
    freshness: Optional[Freshness] = None
    detail: Optional[str] = None
    spatial_resolution: Optional[str] = None
    deal_impact: Optional[Severity] = None

    def to_dict(self) -> dict[str, Any]:
        severity = canonical_severity(self.severity, category=self.category)
        impact = canonical_severity(self.deal_impact or self.severity, category=self.category)
        # F4: keep `severity` for FE; severity_class is the taxonomy. Stale/partial
        # coverage is soft_warning unless already a deal_killer (F6 conversion plays).
        severity_class = impact
        stale = bool(self.freshness and self.freshness.stale)
        partial = self.applies in {"possible", "conditional"}
        if (stale or partial) and impact != "deal_killer":
            severity_class = "soft_warning"
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "summary": self.summary,
            "detail": self.detail,
            "severity": severity,
            "severity_class": severity_class,
            "deal_impact": impact,
            "applies": self.applies,
            "confidence": round(self.confidence, 3),
            "confidence_band": confidence_band(self.confidence),
            "sources": [s.to_dict() for s in self.sources],
            "analyse_hooks": [h.to_dict() for h in self.analyse_hooks],
            "last_verified_at": self.last_verified_at,
            "freshness": self.freshness.to_dict() if self.freshness else None,
            "spatial_resolution": self.spatial_resolution,
        }


def statute_freshness(now: Optional[datetime] = None) -> Freshness:
    return Freshness(
        last_verified_at=STATUTE_VERIFIED_AT,
        stale=False,
        stale_after_days=None,
        basis="statutory",
        notes="England primary legislation / statutory instrument; not a local designation.",
    )


def component_freshness(
    last_verified_at: Optional[str],
    *,
    stale_after_days: int,
    basis: str,
    notes: Optional[str] = None,
    now: Optional[datetime] = None,
    never_stale: bool = False,
) -> Freshness:
    return Freshness(
        last_verified_at=last_verified_at,
        stale=is_stale(
            last_verified_at,
            stale_after_days=stale_after_days,
            now=now,
            never_stale=never_stale,
        ),
        stale_after_days=None if never_stale else stale_after_days,
        basis=basis,
        notes=notes,
    )


def fee_from_range(
    *,
    kind: str,
    range_text: Optional[str],
    term_years: Optional[int],
    include_in_cashflow: bool,
    confidence: float = 0.4,
) -> Optional[FeeHook]:
    if not range_text and term_years is None:
        return None
    min_gbp, max_gbp = _parse_gbp_range(range_text)
    return FeeHook(
        kind=kind,
        include_in_cashflow=include_in_cashflow,
        range_text=range_text,
        min_gbp=min_gbp,
        max_gbp=max_gbp,
        term_years=term_years,
        known=bool(range_text),
        confidence=confidence if range_text else 0.0,
    )


def _parse_gbp_range(text: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    if not text:
        return None, None
    import re

    nums = re.findall(r"£\s*([\d,]+)", text)
    values = []
    for n in nums:
        try:
            values.append(int(n.replace(",", "")))
        except ValueError:
            continue
    if len(values) >= 2:
        return values[0], values[1]
    if len(values) == 1:
        return values[0], values[0]
    return None, None
