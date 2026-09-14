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

Severity = Literal["high", "medium", "low", "info"]
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

STATUTE_VERIFIED_AT = "2018-10-01T00:00:00+00:00"  # 2018 HMO prescribed-description order

HMO_LICENCE_STALE_AFTER_DAYS = 365
ARTICLE4_STALE_AFTER_DAYS = 180
GEO_STALE_AFTER_DAYS = 30


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
    analyse_hooks: list[str] = field(default_factory=list)
    last_verified_at: Optional[str] = None
    freshness: Optional[Freshness] = None
    detail: Optional[str] = None
    spatial_resolution: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "summary": self.summary,
            "detail": self.detail,
            "severity": self.severity,
            "applies": self.applies,
            "confidence": round(self.confidence, 3),
            "confidence_band": confidence_band(self.confidence),
            "sources": [s.to_dict() for s in self.sources],
            "analyse_hooks": list(self.analyse_hooks),
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
