"""
Airroi API Integration — Short-Let (SA/R2SA) Market Intelligence

Provides Airbnb-sourced market data for serviced accommodation analysis:
  - Market summary (avg nightly rate, occupancy, RevPAR, etc.)
  - Nearby listing comparables (individual listings with rates and stats)

API Docs: https://api.airroi.com
Auth: X-api-key header
"""

import os
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# ── Configuration ──────────────────────────────────────────────────────────
AIRROI_API_KEY = os.environ.get('AIRROI_API_KEY', 'tdJ0AQPh5baUZRWmQB7Je1T8u4eDtEZz3EPupCvi')
AIRROI_BASE_URL = 'https://api.airroi.com'
POSTCODES_IO_URL = 'https://api.postcodes.io/postcodes'


class AirroiService:
    """Client for Airroi short-let market data API."""

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
        """Return cached data if fresh, else None."""
        if key in self._cache:
            data, ts = self._cache[key]
            if datetime.now() - ts < self._cache_duration:
                return data
        return None

    def _cache_set(self, key: str, data: dict):
        """Store data in cache."""
        self._cache[key] = (data, datetime.now())

    # ── Core API calls ─────────────────────────────────────────────────────

    def _api_get(self, path: str, params: dict = None, timeout: int = 15) -> dict:
        """Make a GET request to Airroi API."""
        url = f'{self.base_url}{path}'
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            print(f'[AIRROI] GET {path} error: {e}')
            return {'error': str(e)}

    def _api_post(self, path: str, body: dict, timeout: int = 15) -> dict:
        """Make a POST request to Airroi API."""
        url = f'{self.base_url}{path}'
        try:
            resp = requests.post(url, headers=self.headers, json=body, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            print(f'[AIRROI] POST {path} error: {e}')
            return {'error': str(e)}

    # ── Public methods ─────────────────────────────────────────────────────

    def get_market_summary(self, postcode: str) -> Optional[dict]:
        """
        Get SA market summary for a postcode area.

        Step A: Search for market by postcode → get marketId
        Step B: Fetch market summary using marketId

        Returns dict with avgNightlyRate, avgOccupancyRate, avgMonthlyRevenue,
        revPAR, avgLengthOfStay, totalActiveListings, etc.
        Returns None on any failure.
        """
        district = postcode.strip().upper().split()[0] if ' ' in postcode.strip() else postcode.strip().upper()
        cache_key = f'airroi_{district}_market_summary'

        cached = self._cache_get(cache_key)
        if cached:
            print(f'[AIRROI] Cache hit for market summary: {district}')
            return cached

        # Step A: Search for market
        search_resp = self._api_get('/markets/search', params={'q': postcode.strip()})
        if search_resp.get('error') or not search_resp:
            print(f'[AIRROI] Market search failed for {postcode}')
            return None

        # Extract market ID — response could be a list or object with results
        market_id = None
        market_name = None
        if isinstance(search_resp, list) and len(search_resp) > 0:
            market_id = search_resp[0].get('id') or search_resp[0].get('marketId')
            market_name = search_resp[0].get('name') or search_resp[0].get('marketName')
        elif isinstance(search_resp, dict):
            results = search_resp.get('results') or search_resp.get('markets') or search_resp.get('data')
            if isinstance(results, list) and len(results) > 0:
                market_id = results[0].get('id') or results[0].get('marketId')
                market_name = results[0].get('name') or results[0].get('marketName')
            else:
                market_id = search_resp.get('id') or search_resp.get('marketId')
                market_name = search_resp.get('name') or search_resp.get('marketName')

        if not market_id:
            print(f'[AIRROI] No market found for {postcode}: {json.dumps(search_resp)[:300]}')
            return None

        # Step B: Get market summary
        summary_resp = self._api_post('/markets/summary', {'marketId': market_id})
        if summary_resp.get('error'):
            print(f'[AIRROI] Market summary failed for marketId={market_id}')
            return None

        # Normalise response — adapt to whatever shape Airroi returns
        result = {
            'marketId': market_id,
            'marketName': market_name or summary_resp.get('marketName') or district,
            'avgNightlyRate': _extract_num(summary_resp, ['avgNightlyRate', 'average_nightly_rate', 'adr', 'averageDailyRate']),
            'avgOccupancyRate': _extract_num(summary_resp, ['avgOccupancyRate', 'average_occupancy', 'occupancy', 'occupancyRate']),
            'avgMonthlyRevenue': _extract_num(summary_resp, ['avgMonthlyRevenue', 'average_monthly_revenue', 'monthlyRevenue', 'revenue']),
            'revPAR': _extract_num(summary_resp, ['revPAR', 'revpar', 'revenue_per_available_room']),
            'avgLengthOfStay': _extract_num(summary_resp, ['avgLengthOfStay', 'average_length_of_stay', 'avgStay']),
            'totalActiveListings': _extract_num(summary_resp, ['totalActiveListings', 'total_listings', 'activeListings', 'listingCount']),
            'dataSource': 'airroi',
            '_raw': summary_resp,  # Keep raw for debugging
        }

        self._cache_set(cache_key, result)
        print(f'[AIRROI] Market summary for {district}: rate=£{result["avgNightlyRate"]}, occ={result["avgOccupancyRate"]}%')
        return result

    def get_nearby_listings(self, postcode: str, radius: float = 2.0, limit: int = 10) -> Optional[List[dict]]:
        """
        Get nearby SA listings for a postcode.

        Step A: Resolve lat/lng from postcodes.io
        Step B: Search Airroi listings by radius

        Returns list of listing dicts, or None on failure.
        """
        district = postcode.strip().upper().split()[0] if ' ' in postcode.strip() else postcode.strip().upper()
        cache_key = f'airroi_{district}_nearby_listings'

        cached = self._cache_get(cache_key)
        if cached:
            print(f'[AIRROI] Cache hit for nearby listings: {district}')
            return cached

        # Step A: Get coordinates from postcodes.io
        try:
            geo_resp = requests.get(
                f'{POSTCODES_IO_URL}/{postcode.strip().replace(" ", "")}',
                timeout=10,
            )
            geo_data = geo_resp.json()
            if geo_data.get('status') != 200 or not geo_data.get('result'):
                print(f'[AIRROI] Postcodes.io lookup failed for {postcode}')
                return None
            lat = geo_data['result']['latitude']
            lng = geo_data['result']['longitude']
        except Exception as e:
            print(f'[AIRROI] Geo lookup error: {e}')
            return None

        # Step B: Search Airroi listings by radius
        search_resp = self._api_post('/listings/search/radius', {
            'lat': lat,
            'lng': lng,
            'radius': radius,
            'limit': limit,
        })

        if search_resp.get('error'):
            print(f'[AIRROI] Listing search failed for {postcode}')
            return None

        # Parse listings — adapt to Airroi response shape
        raw_listings = []
        if isinstance(search_resp, list):
            raw_listings = search_resp
        elif isinstance(search_resp, dict):
            raw_listings = (
                search_resp.get('listings') or
                search_resp.get('results') or
                search_resp.get('data') or
                []
            )

        listings = []
        for item in raw_listings[:limit]:
            listings.append({
                'listingId': item.get('listingId') or item.get('id') or '',
                'title': item.get('title') or item.get('name') or 'SA Listing',
                'nightlyRate': _extract_num_from_item(item, ['nightlyRate', 'nightly_rate', 'price', 'adr']),
                'bedrooms': _extract_num_from_item(item, ['bedrooms', 'beds', 'bedroom_count']),
                'occupancyRate': _extract_num_from_item(item, ['occupancyRate', 'occupancy', 'occupancy_rate']),
                'monthlyRevenue': _extract_num_from_item(item, ['monthlyRevenue', 'monthly_revenue', 'revenue']),
                'rating': _extract_num_from_item(item, ['rating', 'review_score', 'overallRating']),
                'reviewCount': _extract_num_from_item(item, ['reviewCount', 'review_count', 'reviews', 'numberOfReviews']),
                'listingUrl': item.get('listingUrl') or item.get('url') or item.get('listing_url') or '',
                'thumbnailUrl': item.get('thumbnailUrl') or item.get('thumbnail') or item.get('image_url') or item.get('imageUrl') or '',
                'distance': _extract_num_from_item(item, ['distance', 'distanceKm', 'distance_km']),
            })

        self._cache_set(cache_key, listings)
        print(f'[AIRROI] Found {len(listings)} nearby listings for {district}')
        return listings

    def is_configured(self) -> bool:
        """Check if API key is set."""
        return bool(self.api_key)


# ── Helper functions ───────────────────────────────────────────────────────

def _extract_num(d: dict, keys: list) -> float:
    """Try multiple keys in dict, return first numeric value found, else 0."""
    for k in keys:
        val = d.get(k)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return 0


def _extract_num_from_item(item: dict, keys: list) -> float:
    """Same as _extract_num but for individual listing items."""
    return _extract_num(item, keys)


# ── Global singleton ──────────────────────────────────────────────────────
airroi_service = AirroiService()
