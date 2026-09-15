"""Versioned rate-pack loader. Every run pins the pack id + sha256."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from ltd_co.money import D, money

PACK_DIR = Path(__file__).resolve().parent / "rate_packs"
DEFAULT_PACK_ID = "uk-2026-27-illustrative-v1"


class RatePackError(ValueError):
    pass


@dataclass(frozen=True)
class IncomeTaxRates:
    personal_allowance: Decimal
    pa_taper_start: Decimal
    pa_taper_end: Decimal
    pa_taper_num: int
    pa_taper_den: int
    basic_rate: Decimal
    higher_rate: Decimal
    additional_rate: Decimal
    basic_rate_band: Decimal
    higher_rate_threshold: Decimal
    additional_rate_threshold: Decimal
    property_finance_reducer_rate: Decimal


@dataclass(frozen=True)
class SavingsRates:
    starting_rate_limit: Decimal
    psa_basic: Decimal
    psa_higher: Decimal
    psa_additional: Decimal


@dataclass(frozen=True)
class DividendRates:
    allowance: Decimal
    ordinary_rate: Decimal
    upper_rate: Decimal
    additional_rate: Decimal


@dataclass(frozen=True)
class CorporationTaxRates:
    financial_year: int
    small_profits_rate: Decimal
    main_rate: Decimal
    lower_limit: Decimal
    upper_limit: Decimal
    mr_numerator: int
    mr_denominator: int
    effective_marginal_rate: Decimal


@dataclass(frozen=True)
class SdltBand:
    up_to: Decimal | None
    rate: Decimal


@dataclass(frozen=True)
class SdltRates:
    jurisdiction: str
    minimum_consideration: Decimal
    residential_bands: tuple[SdltBand, ...]
    additional_dwelling_surcharge: Decimal
    corporate_envelope_flat_rate: Decimal
    corporate_envelope_threshold: Decimal
    corporate_envelope_threshold_inclusive: bool
    rental_business_relief_default: bool


@dataclass(frozen=True)
class RatePack:
    id: str
    label: str
    status: str
    tax_year: str
    jurisdiction: str
    effective_from: str
    effective_to: str
    pinned: bool
    notes: tuple[str, ...]
    sha256: str
    income_tax: IncomeTaxRates
    savings: SavingsRates
    dividends: DividendRates
    corporation_tax: CorporationTaxRates
    sdlt: SdltRates
    raw: dict[str, Any]

    def pin(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "status": self.status,
            "taxYear": self.tax_year,
            "jurisdiction": self.jurisdiction,
            "effectiveFrom": self.effective_from,
            "effectiveTo": self.effective_to,
            "pinned": True,
            "sha256": self.sha256,
            "notes": list(self.notes),
        }


def _pack_path(pack_id: str) -> Path:
    safe = pack_id.replace("..", "")
    path = PACK_DIR / f"{safe}.json"
    if not path.is_file():
        raise RatePackError(f"Unknown rate pack: {pack_id}")
    return path


def list_pack_ids() -> list[str]:
    return sorted(p.stem for p in PACK_DIR.glob("*.json"))


def load_rate_pack(pack_id: str | None = None) -> RatePack:
    pack_id = pack_id or DEFAULT_PACK_ID
    path = _pack_path(pack_id)
    raw_bytes = path.read_bytes()
    data = json.loads(raw_bytes.decode("utf-8"))
    if data.get("id") != pack_id:
        raise RatePackError(f"Rate pack id mismatch: file {pack_id} vs json {data.get('id')}")
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sha256 = hashlib.sha256(canonical).hexdigest()

    it = data["incomeTax"]
    sav = data["savings"]
    div = data["dividends"]
    ct = data["corporationTax"]
    sdlt = data["sdlt"]
    taper = it["paTaperPoundPerPounds"]

    bands = tuple(
        SdltBand(
            up_to=None if b.get("upTo") is None else money(b["upTo"]),
            rate=D(b["rate"]),
        )
        for b in sdlt["residentialBands"]
    )

    return RatePack(
        id=data["id"],
        label=data["label"],
        status=data["status"],
        tax_year=data["taxYear"],
        jurisdiction=data["jurisdiction"],
        effective_from=data["effectiveFrom"],
        effective_to=data["effectiveTo"],
        pinned=bool(data.get("pinned", True)),
        notes=tuple(data.get("notes") or ()),
        sha256=sha256,
        income_tax=IncomeTaxRates(
            personal_allowance=money(it["personalAllowance"]),
            pa_taper_start=money(it["paTaperStart"]),
            pa_taper_end=money(it["paTaperEnd"]),
            pa_taper_num=int(taper[0]),
            pa_taper_den=int(taper[1]),
            basic_rate=D(it["basicRate"]),
            higher_rate=D(it["higherRate"]),
            additional_rate=D(it["additionalRate"]),
            basic_rate_band=money(it["basicRateBand"]),
            higher_rate_threshold=money(it["higherRateThreshold"]),
            additional_rate_threshold=money(it["additionalRateThreshold"]),
            property_finance_reducer_rate=D(it["propertyFinanceReducerRate"]),
        ),
        savings=SavingsRates(
            starting_rate_limit=money(sav["startingRateLimit"]),
            psa_basic=money(sav["psaBasic"]),
            psa_higher=money(sav["psaHigher"]),
            psa_additional=money(sav["psaAdditional"]),
        ),
        dividends=DividendRates(
            allowance=money(div["allowance"]),
            ordinary_rate=D(div["ordinaryRate"]),
            upper_rate=D(div["upperRate"]),
            additional_rate=D(div["additionalRate"]),
        ),
        corporation_tax=CorporationTaxRates(
            financial_year=int(ct["financialYear"]),
            small_profits_rate=D(ct["smallProfitsRate"]),
            main_rate=D(ct["mainRate"]),
            lower_limit=money(ct["lowerLimit"]),
            upper_limit=money(ct["upperLimit"]),
            mr_numerator=int(ct["marginalReliefNumerator"]),
            mr_denominator=int(ct["marginalReliefDenominator"]),
            effective_marginal_rate=D(ct["effectiveMarginalRate"]),
        ),
        sdlt=SdltRates(
            jurisdiction=sdlt["jurisdiction"],
            minimum_consideration=money(sdlt["minimumConsideration"]),
            residential_bands=bands,
            additional_dwelling_surcharge=D(sdlt["additionalDwellingSurcharge"]),
            corporate_envelope_flat_rate=D(sdlt["corporateEnvelopeFlatRate"]),
            corporate_envelope_threshold=money(sdlt["corporateEnvelopeThreshold"]),
            corporate_envelope_threshold_inclusive=bool(
                sdlt.get("corporateEnvelopeThresholdInclusive", False)
            ),
            rental_business_relief_default=bool(sdlt["rentalBusinessReliefDefault"]),
        ),
        raw=data,
    )
