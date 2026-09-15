"""Metalyzi Ltd Co Calculator — pure calc facade (no HTTP, no HMRC/MTD)."""

from __future__ import annotations

from typing import Any

from ltd_co.compare import compare_paths
from ltd_co.corporation_tax import compute_corporation_tax
from ltd_co.dividends import extract_dividends
from ltd_co.money import D, clamp0
from ltd_co.rates import DEFAULT_PACK_ID, RatePack, RatePackError, list_pack_ids, load_rate_pack
from ltd_co.sdlt import compare_sdlt, compute_sdlt
from ltd_co.section24 import compute_section24

ENGINE_VERSION = "1.0.0"
SCOPE = "landlord-mvp-paths-a-b"
EXCLUDED = ("hmrc-mtd", "compliance-module", "licensing-geo", "screener")


def _pack(payload: dict | None) -> RatePack:
    payload = payload or {}
    return load_rate_pack(payload.get("ratePackId") or DEFAULT_PACK_ID)


def _envelope(result: dict[str, Any], packs: RatePack) -> dict[str, Any]:
    return {
        "engine": {
            "name": "metalyzi-ltd-co-calculator",
            "version": ENGINE_VERSION,
            "scope": SCOPE,
            "excluded": list(EXCLUDED),
        },
        "ratePack": packs.pin(),
        **result,
    }


def discovery() -> dict[str, Any]:
    packs = load_rate_pack()
    return {
        "service": "metalyzi-ltd-co-calculator",
        "version": ENGINE_VERSION,
        "scope": SCOPE,
        "excluded": list(EXCLUDED),
        "defaultRatePackId": DEFAULT_PACK_ID,
        "availableRatePacks": list_pack_ids(),
        "ratePack": packs.pin(),
        "endpoints": [
            "GET  /v1/ltd-co",
            "GET  /v1/ltd-co/rates",
            "POST /v1/ltd-co/compare",
            "POST /v1/ltd-co/section-24",
            "POST /v1/ltd-co/sdlt",
            "POST /v1/ltd-co/corporation-tax",
            "POST /v1/ltd-co/dividends",
            "GET|POST aliases under /api/v1/ltd-co/*",
        ],
    }


def rates(payload: dict | None = None) -> dict[str, Any]:
    packs = _pack(payload or {})
    return {
        "ratePack": packs.pin(),
        "raw": packs.raw,
        "availableRatePacks": list_pack_ids(),
    }


def section24(payload: dict[str, Any]) -> dict[str, Any]:
    packs = _pack(payload)
    result = compute_section24(
        rental_income=clamp0(payload.get("rentalIncome") or payload.get("annualRent") or 0),
        allowable_non_finance_expenses=clamp0(payload.get("allowableNonFinanceExpenses") or 0),
        finance_costs=clamp0(payload.get("financeCosts") or 0),
        packs=packs,
        other_non_savings_income=clamp0(
            payload.get("otherNonSavingsIncome", payload.get("otherIncome", 0))
        ),
        savings_income=clamp0(payload.get("savingsIncome") or 0),
        dividend_income=clamp0(payload.get("dividendIncome") or 0),
        finance_costs_brought_forward=clamp0(payload.get("financeCostsBroughtForward") or 0),
        property_losses_brought_forward=clamp0(payload.get("propertyLossesBroughtForward") or 0),
    )
    return _envelope({"section24": result.to_dict()}, packs)


def sdlt(payload: dict[str, Any]) -> dict[str, Any]:
    packs = _pack(payload)
    price = clamp0(payload.get("consideration") or payload.get("purchasePrice") or 0)
    if price <= 0:
        raise ValueError("consideration (or purchasePrice) is required")
    relief = payload.get("rentalBusinessRelief")
    comparison = compare_sdlt(
        consideration=price,
        packs=packs,
        rental_business_relief=None if relief is None else bool(relief),
    )
    purchaser = payload.get("purchaser")
    extra: dict[str, Any] = {"comparison": comparison}
    if purchaser:
        extra["selected"] = compute_sdlt(
            consideration=price,
            packs=packs,
            purchaser=purchaser,
            rental_business_relief=None if relief is None else bool(relief),
        ).to_dict()
    return _envelope(extra, packs)


def corporation_tax(payload: dict[str, Any]) -> dict[str, Any]:
    packs = _pack(payload)
    profits = payload.get("taxableProfits")
    if profits is None:
        raise ValueError("taxableProfits is required")
    associated = int(payload.get("associatedCompanies") or 0)
    aug = payload.get("augmentedProfits")
    result = compute_corporation_tax(
        taxable_profits=D(profits),
        packs=packs,
        associated_companies=associated,
        augmented_profits=None if aug is None else D(aug),
        losses_brought_forward=clamp0(payload.get("lossesBroughtForward") or 0),
    )
    return _envelope({"corporationTax": result.to_dict()}, packs)


def dividends(payload: dict[str, Any]) -> dict[str, Any]:
    packs = _pack(payload)
    if payload.get("distributable") is None:
        raise ValueError("distributable is required")
    result = extract_dividends(
        distributable=clamp0(payload["distributable"]),
        packs=packs,
        other_non_savings_income=clamp0(
            payload.get("otherNonSavingsIncome", payload.get("otherIncome", 0))
        ),
        savings_income=clamp0(payload.get("savingsIncome") or 0),
        other_dividend_income=clamp0(payload.get("otherDividendIncome") or 0),
        extract=payload.get("extract", "all"),
    )
    return _envelope({"dividends": result.to_dict()}, packs)


def compare(payload: dict[str, Any]) -> dict[str, Any]:
    packs = _pack(payload)
    result = compare_paths(payload, packs)
    return _envelope(result, packs)


def dispatch(action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    action = action.strip("/").lower()
    if action in ("", "index", "discovery"):
        return discovery()
    if action in ("rates", "rate-pack", "rate_pack"):
        return rates(payload)
    if action in ("section-24", "section_24", "section24"):
        return section24(payload)
    if action == "sdlt":
        return sdlt(payload)
    if action in ("corporation-tax", "corporation_tax", "ct"):
        return corporation_tax(payload)
    if action in ("dividends", "extraction"):
        return dividends(payload)
    if action in ("compare", "paths"):
        return compare(payload)
    raise RatePackError(f"Unknown action: {action}")
