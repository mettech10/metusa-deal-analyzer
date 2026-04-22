"""
ARV Calculator — Shared service for Flip and BRRRR strategies

Given a UK postcode + property type + bedrooms (+ optional floor size),
returns a conservative/mid/optimistic After-Refurb Value using the
"top 40% by £/m²" methodology:

  1. Pull sold comps from PropertyData (preferred) with Land Registry
     fallback when PD is unavailable or sparse.
  2. Filter to last 12 months, same property type (±1 bed widening),
     within the postcode district (expanding to 0.5 mi if needed).
  3. Enrich each comp with floor area from EPC register (matched by
     postcode + street + house number).
  4. Keep the TOP 40% of comps by £/m² — these represent modernised /
     refurbished stock (standard UK proptech proxy).
  5. Compute weighted average £/m² (recency × size similarity).
  6. Project onto subject floor size:
       conservative = subject_m² × lower-quartile £/m²
       mid          = subject_m² × weighted-average £/m²
       optimistic   = subject_m² × upper-quartile £/m²

If fewer than 3 usable comps, return None so the caller can show
"Enter ARV manually". Never throw.

Exposed:  calculate_arv(postcode, property_type, bedrooms, floor_size_m2,
                        property_type_detail=None)
"""

from __future__ import annotations

import os
import re
import math
import statistics
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

try:
    from property_data import property_data as _pd_api
except Exception:
    _pd_api = None

try:
    from land_registry import land_registry as _lr_api
except Exception:
    _lr_api = None


# ── EPC config ─────────────────────────────────────────────────────────────
# Same env vars the Next.js route consults, so no duplicated secrets.
EPC_BEARER = (
    os.environ.get('EPC_API_TOKEN')
    or os.environ.get('EPC_TOKEN')
    or os.environ.get('EPC_BEARER_TOKEN')
    or os.environ.get('EPC_API_KEY')
    or ''
)
EPC_URL = 'https://api.get-energy-performance-data.communities.gov.uk/api/v1/domestic/search'

# ── Constants ──────────────────────────────────────────────────────────────
MIN_COMPS = 3          # below this, return None ("Enter ARV manually")
TOP_QUANTILE = 0.40    # keep top 40% by £/m²
LOOKBACK_MONTHS = 12
DEFAULT_COMP_LIMIT = 40


# ── Helpers ────────────────────────────────────────────────────────────────

def _district(postcode: str) -> str:
    """B14 7XY → B14   |   B14 → B14"""
    pc = (postcode or '').strip().upper()
    return pc.split(' ')[0] if ' ' in pc else pc


def _parse_date(d: str) -> Optional[datetime]:
    """Handle YYYY-MM-DD, DD/MM/YYYY, and ISO timestamps."""
    if not d:
        return None
    if isinstance(d, datetime):
        return d
    s = str(d).strip()
    for fmt in ('%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ', '%d/%m/%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(s[:len(fmt) if '%' not in fmt else 19], fmt)
        except Exception:
            pass
    # Last try — take just the YYYY-MM-DD prefix
    try:
        return datetime.strptime(s[:10], '%Y-%m-%d')
    except Exception:
        return None


def _months_ago(dt: Optional[datetime]) -> float:
    if not dt:
        return 999.0
    delta = datetime.utcnow() - dt
    return delta.days / 30.44


def _norm_type(s: Optional[str]) -> str:
    """Normalise a property-type label to a coarse bucket."""
    if not s:
        return ''
    t = str(s).lower().replace('_', ' ').replace('-', ' ').strip()
    if 'semi' in t:
        return 'semi-detached'
    if 'detached' in t:
        return 'detached'
    if 'terrace' in t or 'end of' in t or 'mid terrace' in t:
        return 'terraced'
    if 'flat' in t or 'apartment' in t or 'maisonette' in t:
        return 'flat'
    if 'bungalow' in t:
        return 'detached'   # LR groups bungalows with detached
    return t


# ── EPC enrichment ─────────────────────────────────────────────────────────

_epc_cache: Dict[str, List[dict]] = {}

def _epc_lookup_postcode(postcode: str) -> List[dict]:
    """
    Fetch all EPCs for a postcode (returns [] on any failure).
    Cached per-postcode for the process lifetime.
    """
    pc = (postcode or '').strip().upper()
    if not pc:
        return []
    if pc in _epc_cache:
        return _epc_cache[pc]
    if not EPC_BEARER:
        return []
    try:
        resp = requests.get(
            EPC_URL,
            params={'postcode': pc, 'size': 50},
            headers={'Authorization': f'Bearer {EPC_BEARER}', 'Accept': 'application/json'},
            timeout=10,
        )
        if resp.status_code != 200:
            _epc_cache[pc] = []
            return []
        payload = resp.json() or {}
        # MHCLG endpoint shape: {data: [{...}], totalCount: N}
        entries = payload.get('data') or payload.get('rows') or []
        norm: List[dict] = []
        for e in entries:
            addr = (e.get('address') or e.get('address1') or '').strip()
            floor = e.get('total-floor-area') or e.get('totalFloorArea') or e.get('floorArea')
            try:
                floor_f = float(floor) if floor is not None else None
            except (TypeError, ValueError):
                floor_f = None
            if floor_f and floor_f > 10:     # sanity floor — ignore garbage
                norm.append({
                    'address': addr,
                    'postcode': (e.get('postcode') or pc).upper(),
                    'floor_area_m2': floor_f,
                })
        _epc_cache[pc] = norm
        return norm
    except Exception as e:
        print(f'[ARV] EPC lookup failed for {pc}: {e}')
        _epc_cache[pc] = []
        return []


_ADDR_NUM_RE = re.compile(r'(\d+[A-Za-z]?)')

def _address_tokens(addr: str) -> Tuple[str, str]:
    """Crude split: first number token + first word-ish street token."""
    if not addr:
        return ('', '')
    s = addr.upper()
    num_m = _ADDR_NUM_RE.search(s)
    num = num_m.group(1) if num_m else ''
    # Strip house number, postcode tail, take first word as street key
    street_part = _ADDR_NUM_RE.sub('', s).strip(' ,.-')
    street_key = street_part.split(',')[0].strip()[:20]
    return (num, street_key)


def _match_floor_area(comp_address: str, epc_entries: List[dict]) -> Optional[float]:
    """Best-effort fuzzy match of a comp's address to an EPC entry."""
    if not comp_address or not epc_entries:
        return None
    c_num, c_street = _address_tokens(comp_address)
    if not c_num:
        return None
    # Prefer exact number + street prefix match
    best: Optional[float] = None
    for e in epc_entries:
        e_num, e_street = _address_tokens(e.get('address', ''))
        if e_num != c_num:
            continue
        if c_street and e_street and (c_street[:6] == e_street[:6] or c_street in e_street or e_street in c_street):
            return e['floor_area_m2']
        # number matches but street doesn't — remember as weak candidate
        if best is None:
            best = e['floor_area_m2']
    return best


# ── Comparable sourcing ────────────────────────────────────────────────────

def _ingest_pd_sold(postcode: str, out: List[dict], seen: set) -> int:
    """PropertyData sold-price ingest. Returns count added."""
    added = 0
    if not (_pd_api and _pd_api.is_configured()):
        return 0
    try:
        sold = _pd_api.get_sold_prices(postcode) or {}
        raw = sold.get('data')
        if isinstance(raw, dict):
            raw = raw.get('raw_data') or []
        if not isinstance(raw, list):
            return 0
        for r in raw:
            if not isinstance(r, dict):
                continue
            price = r.get('price')
            if not price:
                continue
            addr = r.get('address') or r.get('street') or ''
            key = (int(price), str(r.get('date', ''))[:10], str(addr).upper()[:40])
            if key in seen:
                continue
            seen.add(key)
            out.append({
                'price': int(price),
                'date': str(r.get('date', ''))[:10],
                'address': addr,
                'property_type': _norm_type(r.get('type')),
                'bedrooms': r.get('bedrooms'),
                'source': 'PropertyData',
                '_origin_postcode': postcode.upper(),
            })
            added += 1
    except Exception as e:
        print(f'[ARV] PropertyData ingest failed for {postcode}: {e}')
    return added


def _ingest_lr_sold(
    postcode: str,
    property_type: Optional[str],
    property_type_detail: Optional[str],
    out: List[dict],
    seen: set,
    source_tag: str = 'Land Registry',
) -> int:
    """Land Registry ingest at a single postcode (no auto-radius widening)."""
    added = 0
    if not _lr_api:
        return 0
    try:
        results = _lr_api.get_sold_prices(
            postcode, limit=DEFAULT_COMP_LIMIT,
            property_type_detail=property_type_detail,
            property_type=property_type,
        )
        for r in results or []:
            price = r.get('price')
            if not price:
                continue
            street = r.get('street') or ''
            key = (int(price), str(r.get('date', ''))[:10], street.upper()[:40])
            if key in seen:
                continue
            seen.add(key)
            out.append({
                'price': int(price),
                'date': str(r.get('date', ''))[:10],
                'address': f"{street}, {postcode}".strip(', '),
                'property_type': _norm_type(r.get('propertyType')),
                'bedrooms': None,
                'source': source_tag,
                '_origin_postcode': postcode.upper(),
            })
            added += 1
    except Exception as e:
        print(f'[ARV] Land Registry ingest failed for {postcode}: {e}')
    return added


def _count_recent(comps: List[dict], months: int = LOOKBACK_MONTHS) -> int:
    cutoff = datetime.utcnow() - timedelta(days=months * 31)
    n = 0
    for c in comps:
        dt = _parse_date(c.get('date'))
        if dt and dt >= cutoff:
            n += 1
    return n


def _fetch_raw_comps(
    postcode: str,
    property_type: Optional[str],
    property_type_detail: Optional[str],
) -> Tuple[List[dict], str]:
    """
    Pull sold comps from PropertyData + Land Registry. Actively widens the
    search area until we have enough RECENT (last-12-month) comps, since
    some postcodes are quiet.

    Widening ladder:
      1. Subject postcode only
      2. + 0.5 mile radius via postcodes.io
      3. + 1.0 mile radius

    Returns (comps, widening_label). Label describes how far we went.
    """
    merged: List[dict] = []
    seen: set = set()
    target_recent = MIN_COMPS * 3   # aim for ≥9 recent comps before we stop widening

    # Step 1 — exact postcode
    _ingest_pd_sold(postcode, merged, seen)
    _ingest_lr_sold(postcode, property_type, property_type_detail, merged, seen,
                    source_tag='Land Registry')

    recent = _count_recent(merged)
    label = f'exact postcode ({recent} recent)'

    # Step 2/3 — expand via postcodes.io if recent comps are sparse
    if recent < target_recent and _lr_api:
        for radius_mi, tag in [(0.5, '0.5mi'), (1.0, '1.0mi')]:
            try:
                nearby = _lr_api._get_nearby_postcodes(postcode, radius_mi)  # type: ignore[attr-defined]
            except Exception as e:
                print(f'[ARV] nearby-postcode lookup failed: {e}')
                nearby = []
            for pc in nearby[:10]:      # cap fan-out so we don't SPARQL the world
                _ingest_lr_sold(pc, property_type, property_type_detail, merged, seen,
                                source_tag=f'Land Registry +{tag}')
                if _count_recent(merged) >= target_recent:
                    break
            recent = _count_recent(merged)
            label = f'widened to {tag} ({recent} recent)'
            if recent >= target_recent:
                break

    return merged, label


# ── Core scoring ───────────────────────────────────────────────────────────

def _similarity_score(
    comp_m2: Optional[float],
    comp_type: str,
    comp_bedrooms: Optional[int],
    subject_m2: Optional[float],
    subject_type: str,
    subject_bedrooms: int,
    months_old: float,
) -> float:
    """
    Composite weight 0..1 combining recency + type match + size similarity.
    Used both as a filter and as the weighted-average weight.
    """
    # Recency: 1.0 at 0 mo → 0.4 at 12 mo → 0.1 beyond
    recency = max(0.1, 1.0 - (months_old / 20.0))

    # Type: exact match 1.0, mismatch 0.5
    type_score = 1.0 if (comp_type == subject_type and comp_type) else 0.5

    # Bedrooms: exact 1.0, ±1 0.7, else 0.4
    if comp_bedrooms is None:
        bed_score = 0.75
    elif comp_bedrooms == subject_bedrooms:
        bed_score = 1.0
    elif abs(comp_bedrooms - subject_bedrooms) == 1:
        bed_score = 0.7
    else:
        bed_score = 0.4

    # Size: bell-shape around subject_m². ±10% → 1.0, ±30% → 0.7, ±50% → 0.4
    if comp_m2 and subject_m2 and subject_m2 > 0:
        ratio = abs(comp_m2 - subject_m2) / subject_m2
        if ratio <= 0.10:
            size_score = 1.0
        elif ratio <= 0.30:
            size_score = 0.85
        elif ratio <= 0.50:
            size_score = 0.6
        else:
            size_score = 0.35
    else:
        size_score = 0.75

    return recency * type_score * bed_score * size_score


def calculate_arv(
    postcode: str,
    property_type: Optional[str],
    bedrooms: int,
    floor_size_m2: Optional[float] = None,
    property_type_detail: Optional[str] = None,
) -> Optional[dict]:
    """
    Main entry point. Returns a dict with conservative/mid/optimistic ARVs
    plus the comps used, or None if insufficient data.
    """
    try:
        postcode = (postcode or '').strip().upper()
        district = _district(postcode)
        if not postcode:
            return None

        subject_type = _norm_type(property_type) or _norm_type(property_type_detail)
        try:
            subject_bedrooms = int(bedrooms) if bedrooms is not None else 0
        except Exception:
            subject_bedrooms = 0
        try:
            subject_m2 = float(floor_size_m2) if floor_size_m2 else None
        except Exception:
            subject_m2 = None

        # Step 1 — fetch raw comps (active widening built in)
        raw, widening_label = _fetch_raw_comps(postcode, property_type, property_type_detail)
        if not raw:
            return {
                'error': 'No sold comparables found in Land Registry or PropertyData',
                'message': 'Insufficient comparable data — please enter ARV manually',
                'comparablesUsed': 0,
            }

        # Step 2 — filter by recency + type match, with graceful relaxation
        def _collect(lookback_mo: int, require_type: bool) -> List[dict]:
            cutoff_dt = datetime.utcnow() - timedelta(days=lookback_mo * 31)
            out: List[dict] = []
            for c in raw:
                dt = _parse_date(c['date'])
                if not dt or dt < cutoff_dt:
                    continue
                if require_type and subject_type and c['property_type'] and c['property_type'] != subject_type:
                    continue
                c['_date_obj'] = dt
                c['_months_old'] = _months_ago(dt)
                out.append(dict(c))   # shallow-copy so relaxation tiers don't collide
            return out

        # Tier A — same type, 12 mo
        passed = _collect(LOOKBACK_MONTHS, require_type=True)
        relaxation = f'last {LOOKBACK_MONTHS} months · same property type'

        # Tier B — any type, 12 mo (type mismatch often noise in LR data)
        if len(passed) < MIN_COMPS:
            passed = _collect(LOOKBACK_MONTHS, require_type=False)
            relaxation = f'last {LOOKBACK_MONTHS} months · any property type'

        # Tier C — extend lookback to 24 mo, any type (quiet postcodes)
        if len(passed) < MIN_COMPS:
            passed = _collect(24, require_type=False)
            relaxation = 'last 24 months · any property type (sparse area)'

        if len(passed) < MIN_COMPS:
            return {
                'error': f'Only {len(passed)} comps after widening + relaxation',
                'message': 'Insufficient comparable data — please enter ARV manually',
                'comparablesUsed': len(passed),
                'wideningLabel': widening_label,
            }

        # Step 3 — enrich with EPC floor areas
        epc_entries = _epc_lookup_postcode(postcode)
        # Also fetch for the first comp street's postcode if different (best-effort cheap)
        for c in passed:
            c['floor_area_m2'] = _match_floor_area(c['address'], epc_entries)

        # Step 4 — compute £/m² for each comp.
        # Preferred:  use the comp's own EPC floor area
        # Fallback 1: if no EPC for this comp, use median of all EPC areas in
        #             the postcode (they're the closest available proxy)
        # Fallback 2: if EPC unavailable altogether, use subject_m2 as the
        #             working floor area. This collapses £/m² into a raw
        #             price-based model — mathematically: ARV = mean of
        #             top-40% comp prices (the m² cancels out). We note this
        #             in the methodology string so the UI can flag it.
        priced: List[dict] = []
        epc_areas = [c['floor_area_m2'] for c in passed if c.get('floor_area_m2')]
        epc_median = statistics.median(epc_areas) if epc_areas else None
        fallback_m2 = epc_median or subject_m2
        epc_used = bool(epc_median)

        if not fallback_m2 or fallback_m2 <= 10:
            # No EPC and no subject size — can't do £/m². Use a nominal 85m²
            # purely as a divisor (cancels through the math). ARV will equal
            # the mean top-40% comp price, which is still a defensible number.
            fallback_m2 = 85.0
            no_size_available = True
        else:
            no_size_available = False

        for c in passed:
            m2 = c.get('floor_area_m2') or fallback_m2
            if not m2 or m2 <= 10:
                continue
            c['_m2_used'] = m2
            c['price_per_m2'] = c['price'] / m2
            c['_similarity'] = _similarity_score(
                comp_m2=c.get('floor_area_m2'),
                comp_type=c['property_type'],
                comp_bedrooms=c.get('bedrooms'),
                subject_m2=subject_m2 or fallback_m2,
                subject_type=subject_type,
                subject_bedrooms=subject_bedrooms,
                months_old=c['_months_old'],
            )
            priced.append(c)

        if len(priced) < MIN_COMPS:
            return {
                'error': f'Only {len(priced)} usable comps after enrichment',
                'message': 'Insufficient comparable data — please enter ARV manually',
                'comparablesUsed': len(priced),
            }

        # Step 5 — top 40% by £/m² (modernised proxy)
        priced.sort(key=lambda x: x['price_per_m2'], reverse=True)
        cutoff_n = max(MIN_COMPS, math.ceil(len(priced) * TOP_QUANTILE))
        top_comps = priced[:cutoff_n]

        # Step 6 — weighted average £/m² using similarity as weight
        ppsm_values = [c['price_per_m2'] for c in top_comps]
        weights = [max(0.1, c['_similarity']) for c in top_comps]
        weight_sum = sum(weights) or 1.0
        avg_ppsm = sum(p * w for p, w in zip(ppsm_values, weights)) / weight_sum

        # Quartiles from the top-band for scenario spread
        sorted_ppsm = sorted(ppsm_values)
        lower_q = sorted_ppsm[max(0, len(sorted_ppsm) // 4)]
        upper_q = sorted_ppsm[min(len(sorted_ppsm) - 1, (3 * len(sorted_ppsm)) // 4)]
        # Guard: if only 3 comps, quartiles collapse — widen manually
        if upper_q == lower_q:
            lower_q = avg_ppsm * 0.92
            upper_q = avg_ppsm * 1.08

        # Projection floor size: subject if user provided it, else EPC median,
        # else the nominal 85m² (which cancels through — see Step 4).
        project_m2 = subject_m2 or fallback_m2

        conservative = int(round(project_m2 * lower_q / 100) * 100)
        mid = int(round(project_m2 * avg_ppsm / 100) * 100)
        optimistic = int(round(project_m2 * upper_q / 100) * 100)

        # Format comparables payload for UI
        comps_out = []
        for c in top_comps:
            comps_out.append({
                'address': c['address'] or f"Sold in {district}",
                'saleDate': c['date'],
                'salePrice': c['price'],
                'floorAreaM2': round(c['_m2_used'], 1),
                'pricePerM2': int(round(c['price_per_m2'])),
                'similarityScore': round(c['_similarity'], 2),
                'source': c['source'],
                'floorAreaEstimated': c.get('floor_area_m2') is None,
            })

        # Methodology string reflects whether EPC floor areas were actually
        # used. When EPC is unavailable we fall back to raw-price ranking,
        # so it's misleading to claim "per m²" as the source.
        if epc_used:
            methodology = (
                f'Based on {len(top_comps)} refurbished comparable sales averaging '
                f'£{int(round(avg_ppsm)):,}/m² in {district} (top 40% by £/m², '
                f'last {LOOKBACK_MONTHS} months)'
            )
            data_source = 'HM Land Registry + PropertyData + EPC Register'
        elif no_size_available:
            # No subject size AND no EPC — pure price-based ranking
            mean_price = int(round(statistics.mean([c['price'] for c in top_comps])))
            methodology = (
                f'Based on {len(top_comps)} top-priced sales in {district} over the '
                f'last {LOOKBACK_MONTHS} months (floor areas unavailable — using '
                f'mean top-40% sale price £{mean_price:,})'
            )
            data_source = 'HM Land Registry + PropertyData'
        else:
            # Subject size provided, but no comp EPC — scaled to subject m²
            methodology = (
                f'Based on {len(top_comps)} top-priced comparable sales in {district} '
                f'(last {LOOKBACK_MONTHS} months) scaled to subject floor size '
                f'of {int(round(project_m2))}m² — comp floor areas unavailable'
            )
            data_source = 'HM Land Registry + PropertyData'

        return {
            'conservativeARV': conservative,
            'midARV': mid,
            'optimisticARV': optimistic,
            'avgPricePerM2': int(round(avg_ppsm)),
            'subjectFloorSizeM2': round(project_m2, 1),
            'comparablesUsed': len(top_comps),
            'comparables': comps_out,
            'methodology': methodology,
            'dataSource': data_source,
            'epcDataUsed': epc_used,
            'wideningLabel': widening_label,
            'relaxation': relaxation,
        }

    except Exception as e:
        # Never throw — caller treats None / error as "enter manually"
        import traceback
        traceback.print_exc()
        return {
            'error': f'ARV calculator error: {e}',
            'message': 'Could not calculate ARV — please enter manually',
            'comparablesUsed': 0,
        }


if __name__ == '__main__':
    # Smoke test
    import json
    for pc in ['BL4 8LQ', 'M14 6LT', 'SW1A 1AA']:
        print(f'\n=== ARV for {pc} (semi-detached, 3 bed, 85m²) ===')
        r = calculate_arv(pc, 'house', 3, floor_size_m2=85, property_type_detail='semi-detached')
        print(json.dumps(r, indent=2, default=str)[:1500])
