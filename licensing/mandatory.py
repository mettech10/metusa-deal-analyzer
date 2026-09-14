"""England mandatory HMO licensing and sui generis planning rules.

These are national statutory rules, not local designations. Confidence is
high and freshness is statutory (the 2018 prescribed-description order).

Not applied to Wales, Scotland, or Northern Ireland.
"""

from __future__ import annotations

from typing import Optional

from licensing.models import (
    Flag,
    Source,
    statute_freshness,
    STATUTE_VERIFIED_AT,
)

LEGISLATION_SOURCES = [
    Source(
        name="Housing Act 2004 Part 2",
        kind="legislation",
        url="https://www.legislation.gov.uk/ukpga/2004/34/part/2",
        note="HMO licensing framework (mandatory / additional / selective).",
    ),
    Source(
        name="Licensing of Houses in Multiple Occupation (Prescribed Description) (England) Order 2018",
        kind="legislation",
        url="https://www.legislation.gov.uk/uksi/2018/221/contents/made",
        note="Mandatory HMO licence: 5+ occupants in 2+ households. Storey test removed.",
    ),
    Source(
        name="Town and Country Planning (Use Classes) Order 1987 (C4 / sui generis)",
        kind="legislation",
        url="https://www.legislation.gov.uk/uksi/2010/653/article/2/made",
        note="C4 = HMO of 3–6 residents; 7+ residents is sui generis.",
    ),
    Source(
        name="GPDO 2015 Schedule 2 Part 3 Class L",
        kind="legislation",
        url="https://www.legislation.gov.uk/uksi/2015/596/schedule/2/part/3",
        note="Permitted development C3 ↔ C4 unless an Article 4 direction removes it. Sui generis never PD.",
    ),
]


def _base_flag(**kwargs) -> Flag:
    freshness = statute_freshness()
    kwargs.setdefault("last_verified_at", STATUTE_VERIFIED_AT)
    kwargs.setdefault("freshness", freshness)
    kwargs.setdefault("sources", list(LEGISLATION_SOURCES))
    kwargs.setdefault("spatial_resolution", "national_england")
    kwargs.setdefault("confidence", 0.99)
    return Flag(**kwargs)


def england_mandatory_and_sui_generis_flags(
    *,
    occupants: Optional[int],
    households: Optional[int],
    sharing_amenities: Optional[bool],
    intended_use: str,
) -> list[Flag]:
    """Return statutory England flags. Occupants/households may be unknown."""
    flags: list[Flag] = []
    use = (intended_use or "unknown").lower()
    sharing = True if sharing_amenities is None else bool(sharing_amenities)

    flags.append(_threshold_explainer())

    # --- Mandatory HMO licence (housing) ---
    flags.append(
        _mandatory_hmo_flag(
            occupants=occupants,
            households=households,
            sharing=sharing,
            intended_use=use,
        )
    )

    # --- Planning use class / sui generis ---
    flags.append(_planning_use_class_flag(occupants=occupants, households=households))
    flags.append(_sui_generis_flag(occupants=occupants, households=households))

    return flags


def _threshold_explainer() -> Flag:
    return _base_flag(
        id="england_hmo_thresholds",
        category="ruleset",
        title="England HMO thresholds (mandatory licence + planning use class)",
        summary=(
            "Mandatory HMO licence: 5+ people in 2+ households sharing amenities "
            "(storey test removed in 2018). Planning: C4 covers 3–6 residents; "
            "7+ residents is sui generis and always needs planning permission."
        ),
        detail=(
            "These thresholds are national for England. Additional and selective "
            "licensing are local designations layered on top. Article 4 directions "
            "can remove C3→C4 permitted development; they do not replace licensing."
        ),
        severity="info",
        applies="yes",
        analyse_hooks=["ruleset.england_hmo", "verify.lpa"],
    )


def _mandatory_hmo_flag(
    *,
    occupants: Optional[int],
    households: Optional[int],
    sharing: bool,
    intended_use: str,
) -> Flag:
    hooks = ["licence.mandatory_hmo", "cost.hmo_licence_fee", "verify.lpa"]

    if occupants is None and households is None:
        return _base_flag(
            id="mandatory_hmo_licence",
            category="licensing",
            title="Mandatory HMO licence — occupancy not supplied",
            summary=(
                "If this property will be occupied by 5 or more people forming 2 or "
                "more households and sharing amenities, a mandatory HMO licence is "
                "required in England. Occupancy was not supplied, so this is conditional."
            ),
            severity="medium",
            applies="conditional",
            confidence=0.99,
            analyse_hooks=hooks + ["analyse.need_occupancy"],
        )

    occ = occupants if occupants is not None else None
    hh = households if households is not None else None

    # Single household is not an HMO regardless of headcount.
    if hh == 1:
        return _base_flag(
            id="mandatory_hmo_licence",
            category="licensing",
            title="Mandatory HMO licence does not apply (single household)",
            summary=(
                "A single household is not an HMO under the Housing Act 2004, so a "
                "mandatory HMO licence is not triggered. Additional/selective schemes "
                "and planning use class still need a separate check."
            ),
            severity="info",
            applies="no",
            analyse_hooks=hooks,
        )

    if not sharing and occ is not None and occ >= 5:
        return _base_flag(
            id="mandatory_hmo_licence",
            category="licensing",
            title="Mandatory HMO licence unlikely (no shared amenities stated)",
            summary=(
                "Mandatory licensing of HMOs in England requires shared amenities "
                "(or a lack of amenities) as well as 5+ occupants in 2+ households. "
                "Sharing amenities was stated as false — confirm the standard/self-contained layout."
            ),
            severity="low",
            applies="possible",
            confidence=0.70,
            analyse_hooks=hooks,
        )

    known_hmo_size = occ is not None and hh is not None and occ >= 5 and hh >= 2 and sharing
    if known_hmo_size:
        return _base_flag(
            id="mandatory_hmo_licence",
            category="licensing",
            title="Mandatory HMO licence required",
            summary=(
                f"England mandatory HMO licensing applies: {occ} occupants in "
                f"{hh} households sharing amenities (threshold is 5+ people in 2+ households)."
            ),
            severity="high",
            applies="yes",
            analyse_hooks=hooks + ["blocker.unlicensed_hmo"],
        )

    if occ is not None and occ >= 5 and hh is None:
        return _base_flag(
            id="mandatory_hmo_licence",
            category="licensing",
            title="Mandatory HMO licence likely if 2+ households",
            summary=(
                f"{occ} occupants were supplied but household count was not. "
                "If they form 2 or more households and share amenities, a mandatory "
                "HMO licence is required in England."
            ),
            severity="high",
            applies="conditional",
            analyse_hooks=hooks + ["analyse.need_households"],
        )

    if occ is not None and 3 <= occ <= 4:
        return _base_flag(
            id="mandatory_hmo_licence",
            category="licensing",
            title="Below mandatory HMO threshold (additional licensing may still apply)",
            summary=(
                f"{occ} occupants is below the England mandatory threshold (5+). "
                "A smaller HMO may still need an additional HMO licence where the "
                "local authority has designated one, and C4 planning rules may apply."
            ),
            severity="low",
            applies="no",
            analyse_hooks=hooks + ["licence.additional_hmo"],
        )

    if occ is not None and occ < 3:
        return _base_flag(
            id="mandatory_hmo_licence",
            category="licensing",
            title="Mandatory HMO licence does not apply (below HMO size)",
            summary=(
                f"{occ} occupants is below the usual HMO planning (C4, 3+) and "
                "mandatory licensing (5+) thresholds. Selective licensing of all "
                "private rented homes may still apply in designated areas."
            ),
            severity="info",
            applies="no",
            analyse_hooks=hooks + ["licence.selective"],
        )

    return _base_flag(
        id="mandatory_hmo_licence",
        category="licensing",
        title="Mandatory HMO licence — insufficient occupancy detail",
        summary=(
            "Could not determine mandatory HMO licensing from the occupancy fields "
            "supplied. Apply the 5+ people / 2+ households / shared amenities test."
        ),
        severity="medium",
        applies="conditional",
        analyse_hooks=hooks + ["analyse.need_occupancy"],
    )


def _planning_use_class_flag(
    *,
    occupants: Optional[int],
    households: Optional[int],
) -> Flag:
    hooks = ["planning.c3_to_c4", "planning.article4_hmo", "verify.lpa"]
    if households == 1:
        return _base_flag(
            id="planning_use_class",
            category="planning",
            title="Planning use class C3 (single household)",
            summary=(
                "A single household is C3 dwellinghouse. Conversion to C4 (small HMO) "
                "is permitted development unless an Article 4 direction removes it."
            ),
            severity="info",
            applies="yes",
            analyse_hooks=hooks,
        )
    if occupants is None:
        return _base_flag(
            id="planning_use_class",
            category="planning",
            title="Planning use class not determined (occupancy missing)",
            summary=(
                "C4 covers HMOs of 3–6 residents. 7+ residents is sui generis and "
                "always needs planning permission. Occupancy was not supplied."
            ),
            severity="medium",
            applies="conditional",
            analyse_hooks=hooks + ["analyse.need_occupancy"],
        )
    if occupants >= 7:
        return _base_flag(
            id="planning_use_class",
            category="planning",
            title="Planning use class sui generis (large HMO)",
            summary=(
                f"{occupants} residents is above the C4 cap of 6, so the use is "
                "sui generis. There are no permitted development rights into this use."
            ),
            severity="high",
            applies="yes",
            analyse_hooks=hooks + ["planning.sui_generis", "blocker.planning_permission"],
        )
    if occupants >= 3:
        return _base_flag(
            id="planning_use_class",
            category="planning",
            title="Planning use class C4 (small HMO) if 2+ households",
            summary=(
                f"{occupants} residents falls in the C4 range (3–6). C3→C4 is "
                "permitted development unless an Article 4 direction applies at this address."
            ),
            severity="medium",
            applies="conditional" if households is None else "yes",
            analyse_hooks=hooks,
        )
    return _base_flag(
        id="planning_use_class",
        category="planning",
        title="Planning use class likely C3 (below small-HMO size)",
        summary=(
            f"{occupants} occupants is below the C4 HMO range (3–6 residents). "
            "Treat as C3 unless the household composition is an HMO on other grounds."
        ),
        severity="info",
        applies="possible",
        confidence=0.85,
        analyse_hooks=hooks,
    )


def _sui_generis_flag(
    *,
    occupants: Optional[int],
    households: Optional[int],
) -> Flag:
    hooks = ["planning.sui_generis", "blocker.planning_permission", "verify.lpa"]
    if occupants is None:
        return _base_flag(
            id="sui_generis_hmo",
            category="planning",
            title="Sui generis HMO — conditional on 7+ residents",
            summary=(
                "An HMO occupied by 7 or more residents is sui generis. Planning "
                "permission is always required for a material change of use into this class. "
                "Occupancy was not supplied."
            ),
            severity="medium",
            applies="conditional",
            analyse_hooks=hooks + ["analyse.need_occupancy"],
        )
    if occupants >= 7 and households != 1:
        return _base_flag(
            id="sui_generis_hmo",
            category="planning",
            title="Sui generis HMO — planning permission required",
            summary=(
                f"{occupants} residents means this is a large (sui generis) HMO. "
                "C3/C4 → sui generis is not permitted development anywhere in England."
            ),
            severity="high",
            applies="yes",
            analyse_hooks=hooks,
        )
    return _base_flag(
        id="sui_generis_hmo",
        category="planning",
        title="Not a sui generis HMO on occupant count",
        summary=(
            f"{occupants} occupants is within or below the C4 range (max 6). "
            "Sui generis planning permission is not triggered by headcount alone."
        ),
        severity="info",
        applies="no",
        analyse_hooks=hooks,
    )


def out_of_scope_nation_flag(country: str) -> Flag:
    return Flag(
        id="england_scope",
        category="scope",
        title=f"Licensing checker is England-only (resolved country: {country})",
        summary=(
            f"This postcode resolved to {country}. P0–P2 of the licensing checker "
            "implements England mandatory HMO, C4/sui generis, Article 4 ingest, and "
            "English additional/selective schemes only. Do not apply England rules here."
        ),
        severity="high",
        applies="yes",
        confidence=0.95,
        sources=list(LEGISLATION_SOURCES[:1]),
        analyse_hooks=["scope.not_england", "verify.lpa"],
        last_verified_at=STATUTE_VERIFIED_AT,
        freshness=statute_freshness(),
        spatial_resolution="national",
        detail="Wales (Rent Smart Wales), Scotland (HMO at 3+), and NI have separate regimes.",
    )
