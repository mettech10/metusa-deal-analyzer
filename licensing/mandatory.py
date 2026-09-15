"""England mandatory HMO licensing and sui generis planning rules.

These are national statutory rules, not local designations. Confidence is
high and freshness is statutory (the 2018 prescribed-description order).

Not applied to Wales, Scotland, or Northern Ireland.

Mandatory licensing carve-out (2018 Order / GOV.UK): a purpose-built flat
in a block of 3 or more self-contained flats is excluded from mandatory
HMO licensing. Additional/selective schemes may still apply.
"""

from __future__ import annotations

from typing import Optional

from licensing.models import (
    AnalyseHook,
    Flag,
    Source,
    fee_from_range,
    hook,
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
        note=(
            "Mandatory HMO licence: 5+ occupants in 2+ households. Storey test removed. "
            "Purpose-built flats in a block of 3+ self-contained flats are excluded."
        ),
    ),
    Source(
        name="GOV.UK HMO licensing guidance",
        kind="legislation",
        url="https://www.gov.uk/government/publications/houses-in-multiple-occupation-and-residential-property-licensing-reform-guidance-for-local-housing-authorities",
        note="Purpose-built flat in a block of 3+ self-contained flats is outside mandatory licensing.",
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
    kwargs.setdefault("deal_impact", kwargs.get("severity"))
    return Flag(**kwargs)


def england_mandatory_and_sui_generis_flags(
    *,
    occupants: Optional[int],
    households: Optional[int],
    sharing_amenities: Optional[bool],
    intended_use: str,
    purpose_built_flat_in_block_of_3_plus: Optional[bool] = None,
    purpose_built_flat: Optional[bool] = None,
    self_contained_flats_in_block: Optional[int] = None,
    flats_in_block: Optional[int] = None,
) -> list[Flag]:
    """Return statutory England flags. Occupants/households may be unknown."""
    use = (intended_use or "unknown").lower()
    sharing = True if sharing_amenities is None else bool(sharing_amenities)
    block = (
        self_contained_flats_in_block
        if self_contained_flats_in_block is not None
        else flats_in_block
    )
    carve_out = _resolve_purpose_built_carve_out(
        explicit=purpose_built_flat_in_block_of_3_plus,
        purpose_built_flat=purpose_built_flat,
        flats_in_block=block,
    )
    carve_out_needs_block_count = (
        purpose_built_flat is True
        and block is None
        and purpose_built_flat_in_block_of_3_plus is None
    )

    flags: list[Flag] = [_threshold_explainer(carve_out=carve_out)]
    flags.append(
        _mandatory_hmo_flag(
            occupants=occupants,
            households=households,
            sharing=sharing,
            intended_use=use,
            carve_out=carve_out,
            carve_out_needs_block_count=carve_out_needs_block_count,
        )
    )
    flags.append(_planning_use_class_flag(occupants=occupants, households=households))
    flags.append(_sui_generis_flag(occupants=occupants, households=households))
    return flags


def _resolve_purpose_built_carve_out(
    *,
    explicit: Optional[bool],
    purpose_built_flat: Optional[bool],
    flats_in_block: Optional[int],
) -> Optional[bool]:
    """True = carve-out applies; False = does not; None = unknown."""
    if explicit is True:
        return True
    if explicit is False:
        return False
    if purpose_built_flat is True and flats_in_block is not None:
        return flats_in_block >= 3
    if purpose_built_flat is False:
        return False
    return None


def _threshold_explainer(*, carve_out: Optional[bool]) -> Flag:
    extra = ""
    if carve_out is True:
        extra = (
            " This unit is a purpose-built flat in a block of 3+ self-contained flats, "
            "so mandatory licensing is carved out (additional/selective may still apply)."
        )
    return _base_flag(
        id="england_hmo_thresholds",
        category="ruleset",
        title="England HMO thresholds (mandatory licence + planning use class)",
        summary=(
            "Mandatory HMO licence: 5+ people in 2+ households sharing amenities "
            "(storey test removed in 2018), except purpose-built flats in a block of "
            "3+ self-contained flats. Planning: C4 covers 3–6 residents; "
            "7+ residents is sui generis and always needs planning permission."
            + extra
        ),
        detail=(
            "These thresholds are national for England. Additional and selective "
            "licensing are local designations layered on top. Article 4 directions "
            "can remove C3→C4 permitted development; they do not replace licensing."
        ),
        severity="info",
        applies="yes",
        analyse_hooks=[
            hook("ruleset.england_hmo", "ruleset", "info"),
            hook("verify.lpa", "verify", "info"),
        ],
    )


def _mandatory_hooks(
    *,
    impact: str,
    include_fee: bool,
    extra: Optional[list[AnalyseHook]] = None,
) -> list[AnalyseHook]:
    fee = fee_from_range(
        kind="hmo_licence",
        range_text=None,
        term_years=5,
        include_in_cashflow=include_fee,
        confidence=0.0,
    ) if include_fee else None
    hooks = [
        hook("licence.mandatory_hmo", "licence", impact, fee=fee if include_fee else None),  # type: ignore[arg-type]
        hook("verify.lpa", "verify", "info"),
    ]
    if include_fee:
        hooks.append(
            hook(
                "cost.hmo_licence_fee",
                "cost",
                "compliance_cost",
                summary="Include a mandatory HMO licence fee in cashflow (LA-specific; seed fees when known).",
                fee=fee,
            )
        )
    if extra:
        hooks.extend(extra)
    return hooks


def _mandatory_hmo_flag(
    *,
    occupants: Optional[int],
    households: Optional[int],
    sharing: bool,
    intended_use: str,
    carve_out: Optional[bool],
    carve_out_needs_block_count: bool = False,
) -> Flag:
    if carve_out is True:
        return _base_flag(
            id="mandatory_hmo_licence",
            category="licensing",
            title="Mandatory HMO licence carved out (purpose-built flat in 3+ block)",
            summary=(
                "MHCLG carve-out: a purpose-built flat in a block of 3 or more "
                "self-contained flats is excluded from England mandatory HMO licensing "
                "(Licensing of Houses in Multiple Occupation (Prescribed Description) "
                "(England) Order 2018). Additional HMO licensing or selective licensing "
                "may still apply. Converted blocks (Housing Act s257) are not in this carve-out."
            ),
            severity="info",
            applies="no",
            analyse_hooks=_mandatory_hooks(impact="info", include_fee=False)
            + [
                hook("licence.additional_hmo", "licence", "compliance_cost"),
                hook("licence.selective", "licence", "compliance_cost"),
            ],
        )

    if occupants is None and households is None:
        return _base_flag(
            id="mandatory_hmo_licence",
            category="licensing",
            title="Mandatory HMO licence — occupancy not supplied",
            summary=(
                "If this property will be occupied by 5 or more people forming 2 or "
                "more households and sharing amenities, a mandatory HMO licence is "
                "required in England (unless it is a purpose-built flat in a block of "
                "3+ self-contained flats). Occupancy was not supplied, so this is conditional."
            ),
            severity="compliance_cost",
            applies="conditional",
            analyse_hooks=_mandatory_hooks(impact="compliance_cost", include_fee=False)
            + [hook("analyse.need_occupancy", "analyse", "soft_warning")],
        )

    occ = occupants
    hh = households

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
            analyse_hooks=_mandatory_hooks(impact="info", include_fee=False),
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
            severity="soft_warning",
            applies="possible",
            confidence=0.70,
            analyse_hooks=_mandatory_hooks(impact="soft_warning", include_fee=False),
        )

    known_hmo_size = occ is not None and hh is not None and occ >= 5 and hh >= 2 and sharing
    if known_hmo_size and carve_out_needs_block_count:
        return _base_flag(
            id="mandatory_hmo_licence",
            category="licensing",
            title="Mandatory HMO licence — MHCLG purpose-built carve-out needs block size",
            summary=(
                "Occupancy meets the England mandatory HMO threshold, but this is flagged "
                "as a purpose-built flat without flats_in_block. MHCLG carve-out: a "
                "purpose-built flat in a block of 3+ self-contained flats is excluded from "
                "mandatory licensing (2018 Prescribed Description Order). Converted (s257) "
                "blocks are not carved out. Supply flats_in_block to resolve."
            ),
            severity="compliance_cost",
            applies="conditional",
            analyse_hooks=_mandatory_hooks(impact="compliance_cost", include_fee=False)
            + [
                hook("analyse.need_flats_in_block", "analyse", "soft_warning"),
                hook("licence.additional_hmo", "licence", "compliance_cost"),
            ],
        )
    if known_hmo_size:
        if carve_out is None:
            extra_note = (
                " Purpose-built-flat carve-out was not supplied; if this is a purpose-built "
                "flat in a block of 3+ self-contained flats, mandatory licensing does not apply "
                "(MHCLG / 2018 Order)."
            )
        else:
            extra_note = ""
        return _base_flag(
            id="mandatory_hmo_licence",
            category="licensing",
            title="Mandatory HMO licence required",
            summary=(
                f"England mandatory HMO licensing applies: {occ} occupants in "
                f"{hh} households sharing amenities (threshold is 5+ people in 2+ households)."
                + extra_note
            ),
            severity="deal_killer",
            applies="yes",
            analyse_hooks=_mandatory_hooks(impact="deal_killer", include_fee=True)
            + [hook("blocker.unlicensed_hmo", "blocker", "deal_killer")],
        )

    if occ is not None and occ >= 5 and hh is None:
        return _base_flag(
            id="mandatory_hmo_licence",
            category="licensing",
            title="Mandatory HMO licence likely if 2+ households",
            summary=(
                f"{occ} occupants were supplied but household count was not. "
                "If they form 2 or more households and share amenities, a mandatory "
                "HMO licence is required in England (subject to the purpose-built-flat carve-out)."
            ),
            severity="deal_killer",
            applies="conditional",
            analyse_hooks=_mandatory_hooks(impact="deal_killer", include_fee=True)
            + [hook("analyse.need_households", "analyse", "soft_warning")],
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
            severity="soft_warning",
            applies="no",
            analyse_hooks=_mandatory_hooks(impact="info", include_fee=False)
            + [hook("licence.additional_hmo", "licence", "compliance_cost")],
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
            analyse_hooks=_mandatory_hooks(impact="info", include_fee=False)
            + [hook("licence.selective", "licence", "compliance_cost")],
        )

    return _base_flag(
        id="mandatory_hmo_licence",
        category="licensing",
        title="Mandatory HMO licence — insufficient occupancy detail",
        summary=(
            "Could not determine mandatory HMO licensing from the occupancy fields "
            "supplied. Apply the 5+ people / 2+ households / shared amenities test, "
            "and the purpose-built-flat carve-out."
        ),
        severity="compliance_cost",
        applies="conditional",
        analyse_hooks=_mandatory_hooks(impact="compliance_cost", include_fee=False)
        + [hook("analyse.need_occupancy", "analyse", "soft_warning")],
    )


def _planning_use_class_flag(
    *,
    occupants: Optional[int],
    households: Optional[int],
) -> Flag:
    base_hooks = [
        hook("planning.c3_to_c4", "planning", "compliance_cost"),
        hook("planning.article4_hmo", "planning", "soft_warning"),
        hook("verify.lpa", "verify", "info"),
    ]
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
            analyse_hooks=base_hooks,
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
            severity="compliance_cost",
            applies="conditional",
            analyse_hooks=base_hooks
            + [hook("analyse.need_occupancy", "analyse", "soft_warning")],
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
            severity="deal_killer",
            applies="yes",
            analyse_hooks=base_hooks
            + [
                hook("planning.sui_generis", "planning", "deal_killer"),
                hook("blocker.planning_permission", "blocker", "deal_killer"),
            ],
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
            severity="compliance_cost",
            applies="conditional" if households is None else "yes",
            analyse_hooks=base_hooks,
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
        analyse_hooks=base_hooks,
    )


def _sui_generis_flag(
    *,
    occupants: Optional[int],
    households: Optional[int],
) -> Flag:
    hooks = [
        hook("planning.sui_generis", "planning", "deal_killer"),
        hook("blocker.planning_permission", "blocker", "deal_killer"),
        hook("verify.lpa", "verify", "info"),
    ]
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
            severity="compliance_cost",
            applies="conditional",
            analyse_hooks=hooks + [hook("analyse.need_occupancy", "analyse", "soft_warning")],
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
            severity="deal_killer",
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
        analyse_hooks=[
            hook("planning.sui_generis", "planning", "info"),
            hook("verify.lpa", "verify", "info"),
        ],
    )


def out_of_scope_nation_flag(country: str) -> Flag:
    return Flag(
        id="england_scope",
        category="scope",
        title=f"Licensing checker is England-only (resolved country: {country})",
        summary=(
            f"This postcode resolved to {country}. P0–P2 of the licensing checker "
            "implements England mandatory HMO, C4/sui generis, Article 4 ingest, and "
            "English additional/selective schemes only. Do not apply England rules here. "
            "Legacy HMO_LICENSING_LOOKUP rows (including Wales/Scotland) are not used."
        ),
        severity="deal_killer",
        deal_impact="deal_killer",
        applies="yes",
        confidence=0.95,
        sources=list(LEGISLATION_SOURCES[:1]),
        analyse_hooks=[
            hook("scope.not_england", "scope", "deal_killer"),
            hook("verify.lpa", "verify", "info"),
        ],
        last_verified_at=STATUTE_VERIFIED_AT,
        freshness=statute_freshness(),
        spatial_resolution="national",
        detail="Wales (Rent Smart Wales), Scotland (HMO at 3+), and NI have separate regimes.",
    )
