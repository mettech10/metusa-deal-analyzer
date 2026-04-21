"""
Airroi API Integration — Short-Let (SA/R2SA) Market Intelligence

Provides Airbnb-sourced market data for serviced accommodation analysis:
  - Market summary (avg nightly rate, occupancy, RevPAR, monthly revenue, etc.)
  - Nearby listing comparables (individual listings with rates and stats)

API Docs: https://www.airroi.com/api/documentation/
Auth:     X-api-key header

Flow:
  postcode → postcodes.io (lat/lng + admin_district + region + country)
           → Airroi POST /markets/summary  {market: {...}, currency: 'native'}
           → Airroi POST /listings/search/radius  {latitude, longitude, radius_miles}

Normalised output preserves the historical contract used by:
  - app.py line 5400 (AI prompt context)
  - app.py line 7119 (SA comparables endpoint)
  - components/analyse/sa-comparables.tsx (frontend display)
"""

import os
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# ── Configuration ──────────────────────────────────────────────────────────
# NOTE: the hard-coded fallback is only a convenience for local dev. Production
# must set AIRROI_API_KEY via env var. The literal key below contains a capital
# "O" (not a zero) — this is the real key issued for this account.
AIRROI_API_KEY = os.environ.get(
    'AIRROI_API_KEY',
    'tdJOAQPh5baUZRWmQB7Je1T8u4eDtEZz3EPupCvi',
)
AIRROI_BASE_URL = 'https://api.airroi.com'
POSTCODES_IO_URL = 'https://api.postcodes.io/postcodes'


class AirroiService:
    """Client for the Airroi short-let market data API (v2)."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or AIRROI_API_KEY
        self.base_url = AIRROI_BASE_URL
        self.headers = {
            'X-api-key': self.api_key,
            'Content-Type': 'application/json',
        }
        # Simple in-memory cache (same pattern as PropertyDataAPI)
        self._cache: Dict[str, tuple] = {}
        self._cache_duration = timedelta(days=7)

    # ── Cache helpers ──────────────────────────────────────────────────────

    def _cache_get(self, key: str) -> Optional[dict]:
        if key in self._cache:
            data, ts = self._cache[key]
            if datetime.now() - ts < self._cache_duration:
                return data
        return None

    def _cache_set(self, key: str, data: dict):
        self._cache[key] = (data, datetime.now())

    # ── Geocoding helper ───────────────────────────────────────────────────

    def _geocode_postcode(self, postcode: str) -> Optional[dict]:
        """
        Resolve a UK postcode via postcodes.io.

        Returns a dict with:
          latitude, longitude, admin_district, region, country
        Or None if the postcode cannot be resolved.
        """
        pc = (postcode or '').strip().replace(' ', '').upper()
        if not pc:
            return None
        try:
            resp = requests.get(f'{POSTCODES_IO_URL}/{pc}', timeout=10)
            if resp.status_code != 200:
                print(f'[AIRROI] postcodes.io {resp.status_code} for {postcode}')
                return None
            data = resp.json().get('result') or {}
            if not data:
                return None
            return {
                'latitude':       data.get('latitude'),
                'longitude':      data.get('longitude'),
                'admin_district': data.get('admin_district') or '',
                'region':         data.get('region') or '',
                'country':        data.get('country') or '',
            }
        except Exception as e:
            print(f'[AIRROI] geocode error for {postcode}: {e}')
            return None

    # ── Core API calls ─────────────────────────────────────────────────────

    def _api_post(self, path: str, body: dict, timeout: int = 20) -> dict:
        """POST to Airroi and always return a dict (never raise)."""
        url = f'{self.base_url}{path}'
        try:
            resp = requests.post(url, headers=self.headers, json=body, timeout=timeout)
            # Non-2xx: surface the error payload for logging
            if resp.status_code >= 400:
                try:
                    err = resp.json()
                except Exception:
                    err = {'raw': resp.text[:300]}
                print(f'[AIRROI] POST {path} → {resp.status_code}: {json.dumps(err)[:300]}')
                return {'error': f'HTTP {resp.status_code}', '_status': resp.status_code, '_detail': err}
            return resp.json() if resp.content else {}
        except requests.exceptions.RequestException as e:
            print(f'[AIRROI] POST {path} exception: {e}')
            return {'error': str(e)}

    def _search_uk_market(self, query: str) -> Optional[dict]:
        """
        Fallback: ask Airroi's /markets/search for the first UK entry matching
        `query`. Returns a market dict {country, region, locality, district}
        suitable for /markets/summary, or None.

        Needed because postcodes.io's admin_district names don't always match
        Airroi's locality names — e.g. postcodes.io says "Westminster" but
        Airroi stores it as "City of Westminster".
        """
        if not query:
            return None
        try:
            url = f'{self.base_url}/markets/search'
            resp = requests.get(url, headers=self.headers, params={'query': query}, timeout=15)
            if resp.status_code != 200:
                return None
            entries = (resp.json() or {}).get('entries') or []
            for e in entries:
                if e.get('country') == 'United Kingdom':
                    return {
                        'country':  'United Kingdom',
                        'region':   e.get('region')   or '',
                        'locality': e.get('locality') or '',
                        'district': '',   # always top-level city aggregate
                    }
            return None
        except Exception as ex:
            print(f'[AIRROI] market search "{query}" error: {ex}')
            return None

    # ── Public methods ─────────────────────────────────────────────────────

    def get_market_summary(self, postcode: str) -> Optional[dict]:
        """
        Get SA market summary for a UK postcode.

        Flow:
          1. Resolve postcode via postcodes.io → admin_district / region / country
          2. POST /markets/summary with a nested `market` object
          3. Normalise response keys to the contract expected by app.py + FE

        Returns None on any failure (caller treats this as "no data").
        """
        if not postcode or not postcode.strip():
            return None

        district = postcode.strip().upper().split()[0] if ' ' in postcode.strip() else postcode.strip().upper()
        cache_key = f'airroi_market_{postcode.strip().upper()}'

        cached = self._cache_get(cache_key)
        if cached:
            print(f'[AIRROI] Cache hit for market summary: {district}')
            return cached

        # Step 1 — geocode postcode to city/region/country
        geo = self._geocode_postcode(postcode)
        if not geo:
            print(f'[AIRROI] Could not geocode {postcode} — skipping market summary')
            return None

        # Airroi's market taxonomy flattens the UK:
        #   country  = "United Kingdom"
        #   region   = England / Scotland / Wales / Northern Ireland
        #              (this is what postcodes.io calls `country`)
        #   locality = the admin district / city (e.g. "Manchester", "London")
        #   district = optional sub-area (we leave blank; Airroi returns
        #              city-level aggregates when district is empty)
        # postcodes.io's `region` ("North West", etc.) is NOT accepted by
        # Airroi and will produce HTTP 404 "No market data matches…".
        market_obj = {
            'country':  'United Kingdom',
            'region':   geo.get('country') or 'England',
            'locality': geo.get('admin_district') or '',
            'district': '',
        }
        if not market_obj['locality']:
            print(f'[AIRROI] No locality for {postcode} — skipping')
            return None

        # Step 2 — POST /markets/summary
        body = {
            'market':     market_obj,
            'currency':   'native',    # returns GBP for UK
            'num_months': 12,
        }
        resp = self._api_post('/markets/summary', body)

        # Step 2b — fallback: if direct lookup 404s (locality name mismatch),
        # search Airroi's own market catalogue for the locality and retry.
        if resp.get('_status') == 404:
            alt = self._search_uk_market(market_obj['locality'])
            if alt and (alt['locality'], alt['region']) != (market_obj['locality'], market_obj['region']):
                print(f'[AIRROI] Retrying with catalogue match: {alt["locality"]}, {alt["region"]}')
                market_obj = alt
                body['market'] = market_obj
                resp = self._api_post('/markets/summary', body)

        if resp.get('error'):
            return None

        # Step 3 — normalise to the historical contract.
        # Airroi returns:
        #   occupancy            (0-1 decimal — multiply by 100 for UI)
        #   average_daily_rate   (£ per night)
        #   rev_par              (£)
        #   revenue              (£, monthly)
        #   length_of_stay       (nights)
        #   booking_lead_time    (days)
        #   min_nights           (avg)
        #   active_listings_count
        occ_raw = _num(resp.get('occupancy'))
        result = {
            'marketId':             None,  # v2 has no opaque ID; identity = market object
            'marketName':           market_obj['locality'] or district,
            'avgNightlyRate':       round(_num(resp.get('average_daily_rate')), 2),
            # Express as 0-100 % for the frontend (which does `.toFixed(0)%`)
            'avgOccupancyRate':     round(occ_raw * 100 if occ_raw <= 1 else occ_raw, 2),
            'avgMonthlyRevenue':    round(_num(resp.get('revenue')), 2),
            'revPAR':               round(_num(resp.get('rev_par')), 2),
            'avgLengthOfStay':      round(_num(resp.get('length_of_stay')), 2),
            'totalActiveListings':  round(_num(resp.get('active_listings_count'))),
            'bookingLeadTime':      round(_num(resp.get('booking_lead_time')), 1),
            'minNights':            round(_num(resp.get('min_nights')), 1),
            'dataSource':           'airroi',
            '_raw':                 resp,
        }

        self._cache_set(cache_key, result)
        print(
            f'[AIRROI] Market summary {district} ({market_obj["locality"]}): '
            f'rate=£{result["avgNightlyRate"]}, occ={result["avgOccupancyRate"]}%, '
            f'rev=£{result["avgMonthlyRevenue"]}/mo, listings={result["totalActiveListings"]}'
        )
        return result

    def get_nearby_listings(
        self,
        postcode: str,
        radius_miles: float = 1.0,
        limit: int = 10,
    ) -> Optional[List[dict]]:
        """
        Get nearby SA listings for a UK postcode.

        Flow:
          1. Resolve postcode via postcodes.io → lat/lng
          2. POST /listings/search/radius with {latitude, longitude, radius_miles, ...}
          3. Normalise each listing to the historical flat shape consumed by the FE
        """
        if not postcode or not postcode.strip():
            return None

        district = postcode.strip().upper().split()[0] if ' ' in postcode.strip() else postcode.strip().upper()
        cache_key = f'airroi_listings_{postcode.strip().upper()}_{radius_miles}_{limit}'

        cached = self._cache_get(cache_key)
        if cached:
            print(f'[AIRROI] Cache hit for nearby listings: {district}')
            return cached

        geo = self._geocode_postcode(postcode)
        if not geo or geo.get('latitude') is None:
            print(f'[AIRROI] No coords for {postcode} — skipping listings search')
            return None

        body = {
            'latitude':     geo['latitude'],
            'longitude':    geo['longitude'],
            'radius_miles': max(0.1, min(10.0, float(radius_miles))),
            'currency':     'native',
            'num_months':   12,
            'pagination':   {'page_size': max(1, min(50, int(limit))), 'offset': 0},
        }
        resp = self._api_post('/listings/search/radius', body)
        if resp.get('error'):
            return None

        raw_listings = resp.get('results') or []
        listings: List[dict] = []
        for item in raw_listings[:limit]:
            li   = item.get('listing_info')      or {}
            loc  = item.get('location_info')     or {}
            prop = item.get('property_details')  or {}
            rat  = item.get('ratings')           or {}
            perf = item.get('performance_metrics') or {}

            listing_id = li.get('listing_id') or li.get('id')
            listing_url = (
                f'https://www.airbnb.com/rooms/{listing_id}'
                if listing_id else ''
            )
            # Airroi returns performance as ttm_ (trailing twelve months).
            ttm_occ = _num(perf.get('ttm_occupancy'))

            listings.append({
                'listingId':      str(listing_id or ''),
                'title':          li.get('listing_name') or 'SA Listing',
                'nightlyRate':    round(_num(perf.get('ttm_avg_rate')), 2),
                'bedrooms':       _num(prop.get('bedrooms')),
                # Express occupancy 0-100 to match market summary
                'occupancyRate':  round(ttm_occ * 100 if ttm_occ <= 1 else ttm_occ, 2),
                'monthlyRevenue': round(_num(perf.get('ttm_revenue')) / 12.0, 2),
                'rating':         round(_num(rat.get('rating_overall')), 1),
                'reviewCount':    int(_num(rat.get('num_reviews'))),
                'listingUrl':     listing_url,
                'thumbnailUrl':   li.get('cover_photo_url') or '',
                'distance':       _haversine_miles(
                    geo['latitude'], geo['longitude'],
                    _num(loc.get('latitude')), _num(loc.get('longitude')),
                ),
            })

        self._cache_set(cache_key, listings)
        print(f'[AIRROI] Found {len(listings)} nearby listings for {district}')
        return listings

    def is_configured(self) -> bool:
        return bool(self.api_key)


# ── Helper functions ───────────────────────────────────────────────────────

def _num(val, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Rough distance in miles between two lat/lng points."""
    from math import radians, sin, cos, asin, sqrt
    if not all(isinstance(x, (int, float)) for x in (lat1, lng1, lat2, lng2)):
        return 0.0
    if lat2 == 0.0 and lng2 == 0.0:
        return 0.0
    R_MILES = 3958.8
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    c = 2 * asin(min(1.0, sqrt(a)))
    return round(R_MILES * c, 2)


# ── Global singleton ──────────────────────────────────────────────────────
airroi_service = AirroiService()
