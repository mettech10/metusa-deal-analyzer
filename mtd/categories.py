"""SA105-aligned category catalogue for UK property businesses."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_CATALOGUE_PATH = Path(__file__).resolve().parent / "categories.json"


@lru_cache(maxsize=1)
def load_catalogue() -> dict[str, Any]:
    with _CATALOGUE_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _norm(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())


@lru_cache(maxsize=1)
def _index() -> dict[str, dict[str, Any]]:
    catalogue = load_catalogue()
    by_key: dict[str, dict[str, Any]] = {}
    for cat in catalogue["categories"]:
        by_key[cat["code"]] = cat
        by_key[_norm(cat["code"])] = cat
        by_key[_norm(cat["name"])] = cat
        if cat.get("hmrcField"):
            by_key[_norm(cat["hmrcField"])] = cat
            by_key[_norm(cat["hmrcField"].split(".")[-1])] = cat
        if cat.get("sa105Box"):
            by_key[f"box {cat['sa105Box']}"] = cat
            by_key[f"box{cat['sa105Box']}"] = cat
        for alias in cat.get("aliases") or []:
            by_key[_norm(alias)] = cat
    return by_key


def get_category(code: str) -> dict[str, Any] | None:
    if not code:
        return None
    return _index().get(code) or _index().get(_norm(code))


def resolve_category_code(value: str) -> str | None:
    cat = get_category(value)
    return cat["code"] if cat else None


def is_residential_finance(code: str) -> bool:
    cat = get_category(code)
    return bool(cat and cat.get("isResidentialFinance"))


CATEGORIES: list[dict[str, Any]] = load_catalogue()["categories"]

RESIDENTIAL_FINANCE_CODES = frozenset(
    c["code"] for c in CATEGORIES if c.get("isResidentialFinance")
)

INCOME_CODES = frozenset(c["code"] for c in CATEGORIES if c["kind"] == "income")
EXPENSE_CODES = frozenset(c["code"] for c in CATEGORIES if c["kind"] == "expense")
