"""CSV preview + idempotent commit helpers.

Expected columns (any case, aliases accepted):
  date, property_id, category, amount_pence (or amount in pounds),
  description, counterparty, reference
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import date, datetime
from typing import Any

from mtd.categories import resolve_category_code

_HEADER_ALIASES = {
    "date": "date",
    "entry date": "date",
    "transaction date": "date",
    "property_id": "property_id",
    "propertyid": "property_id",
    "property id": "property_id",
    "property": "property_id",
    "category": "category",
    "hmrc category": "category",
    "sa105": "category",
    "amount_pence": "amount_pence",
    "amountpence": "amount_pence",
    "amount pence": "amount_pence",
    "pence": "amount_pence",
    "amount": "amount",
    "gbp": "amount",
    "value": "amount",
    "description": "description",
    "narrative": "description",
    "notes": "description",
    "counterparty": "counterparty",
    "payee": "counterparty",
    "payer": "counterparty",
    "tenant": "counterparty",
    "supplier": "counterparty",
    "reference": "reference",
    "ref": "reference",
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def row_fingerprint(
    *,
    business_id: str,
    entry_date: str,
    property_id: str | None,
    category_code: str,
    amount_pence: int,
    description: str | None,
    source_row: int,
    content_sha256: str,
) -> str:
    raw = "|".join(
        [
            business_id,
            content_sha256,
            str(source_row),
            entry_date,
            property_id or "",
            category_code,
            str(amount_pence),
            (description or "").strip(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_pence_cell(value: Any) -> int:
    """Parse a cell that is already in pence (integers, optional sign)."""
    text = str(value).strip().replace(",", "").replace("£", "").replace(" ", "")
    if not text:
        raise ValueError("amount is required")
    if "." in text:
        return pounds_to_pence(text)
    if text.startswith("(") and text.endswith(")"):
        return -int(text[1:-1])
    return int(text)


def pounds_to_pence(value: Any) -> int:
    if value is None or value == "":
        raise ValueError("amount is required")
    if isinstance(value, bool):
        raise ValueError("invalid amount")
    if isinstance(value, int):
        return value
    text = str(value).strip().replace(",", "").replace("£", "").replace("gbp", "")
    text = text.replace(" ", "")
    if text == "":
        raise ValueError("amount is required")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    if text.startswith("-"):
        negative = True
        text = text[1:]
    if "." in text:
        whole, frac = text.split(".", 1)
        frac = (frac + "00")[:2]
        pence = int(whole or "0") * 100 + int(frac)
    else:
        pence = int(text) * 100
    return -pence if negative else pence


def parse_entry_date(value: str) -> date:
    text = (value or "").strip()
    if not text:
        raise ValueError("date is required")
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date: {value}")


def _normalise_header(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", (name or "").strip().lower()).strip()
    return _HEADER_ALIASES.get(cleaned, cleaned.replace(" ", "_"))


def parse_csv(text: str) -> tuple[list[str], list[dict[str, str]], list[str]]:
    if text is None:
        raise ValueError("csv is required")
    sample = text.lstrip("\ufeff")
    if not sample.strip():
        raise ValueError("csv is empty")
    dialect = csv.excel
    try:
        dialect = csv.Sniffer().sniff(sample[:4096], delimiters=",;\t")
    except csv.Error:
        pass
    reader = csv.reader(io.StringIO(sample), dialect)
    try:
        raw_headers = next(reader)
    except StopIteration as exc:
        raise ValueError("csv is empty") from exc
    headers = [_normalise_header(h) for h in raw_headers]
    issues: list[str] = []
    if "date" not in headers:
        issues.append("missing date column")
    if "category" not in headers:
        issues.append("missing category column")
    if "amount_pence" not in headers and "amount" not in headers:
        issues.append("missing amount or amount_pence column")
    rows: list[dict[str, str]] = []
    for raw in reader:
        if not any(cell.strip() for cell in raw):
            continue
        padded = list(raw) + [""] * (len(headers) - len(raw))
        rows.append({headers[i]: padded[i].strip() if i < len(padded) else "" for i in range(len(headers))})
    return headers, rows, issues


def preview_rows(
    text: str,
    *,
    known_property_ids: set[str] | None = None,
    amount_column_is_pence_if_no_dot: bool = True,
) -> dict[str, Any]:
    headers, rows, header_issues = parse_csv(text)
    preview: list[dict[str, Any]] = []
    valid_count = 0
    for index, row in enumerate(rows, start=2):
        errors: list[str] = []
        mapped: dict[str, Any] = {"sourceRow": index}
        try:
            mapped["date"] = parse_entry_date(row.get("date", "")).isoformat()
        except ValueError as exc:
            errors.append(str(exc))
        category_raw = row.get("category", "")
        code = resolve_category_code(category_raw)
        if not code:
            errors.append(f"unknown category: {category_raw or '(blank)'}")
        else:
            mapped["categoryCode"] = code
        property_id = row.get("property_id") or None
        if property_id and known_property_ids is not None and property_id not in known_property_ids:
            errors.append(f"unknown propertyId: {property_id}")
        mapped["propertyId"] = property_id
        try:
            if row.get("amount_pence") not in (None, ""):
                mapped["amountPence"] = _parse_pence_cell(row["amount_pence"])
            else:
                mapped["amountPence"] = pounds_to_pence(row.get("amount", ""))
        except (ValueError, TypeError) as exc:
            errors.append(f"invalid amount: {exc}")
        mapped["description"] = row.get("description") or None
        mapped["counterparty"] = row.get("counterparty") or None
        mapped["reference"] = row.get("reference") or None
        ok = not errors
        if ok:
            valid_count += 1
        preview.append({"rowNumber": index, "valid": ok, "errors": errors, "mapped": mapped, "raw": row})
    return {
        "headers": headers,
        "headerIssues": header_issues,
        "rowCount": len(rows),
        "validCount": valid_count,
        "invalidCount": len(rows) - valid_count,
        "rows": preview,
        "readyToCommit": bool(rows) and not header_issues and valid_count == len(rows),
    }
