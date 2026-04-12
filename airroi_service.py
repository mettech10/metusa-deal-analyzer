"""
Airroi API Integration
Real Airbnb market intelligence for SA/R2SA investment analysis

API docs: https://api.airroi.com
Pricing: Market data $0.05/call, Nearby listings $0.25/call, Comparables $0.05/call
"""

import requests
import os
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple

# Configuration
AIRROI_API_KEY = os.getenv('AIRROI_API_KEY', '')
AIRROI_BASE_URL = "https://api.airroi.com"


class AirroiAPI:
    """
    Client for the Airroi API — Airbnb market intelligence.

    Provides market summaries, occupancy/ADR trends, nearby listings
    and listing comparables for SA and R2SA investment analysis.
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or AIRROI_API_KEY
        self.base_url = AIRROI_BASE_URL

        # In-memory cache: { cache_key: (data, timestamp) }
        self.cache: Dict[str, Tuple[dict, datetime]] = {}
        # Market data changes slowly → 7 day TTL
        self.market_cache_duration = timedelta(days=7)
        # Listings change more often → 3 day TTL
        self.listing_cache_duration = timedelta(days=3)

        # Running cost tracker (resets on process restart)
        self.total_cost = 0.0
        self.call_count = 0

    # ── Internal helpers ─────────────────────────────────────────────────

    def _cache_get(self, key: str, is_listing: bool = False) -> Optional[dict]:
        """Return cached data if still valid, else None."""
        if key not in self.cache:
            return None
        data, cached_time = self.cache[key]
        ttl = self.listing_cache_duration if is_listing else self.market_cache_duration
        if datetime.now() - cached_time < ttl:
            print(f"[Airroi] Cache HIT: {key[:60]}")
            return data
        # Expired — remove
        del self.cache[key]
        return None

    def _cache_set(self, key: str, data: dict) -> None:
        self.cache[key] = (data, datetime.now())

    def _log_cost(self, endpoint: str, cost: float) -> None:
        """Track API spend for monitoring."""
        self.total_cost += cost
        self.call_count += 1
        print(
            f"[Airroi] {endpoint} — ${cost:.2f} "
            f"(session total: ${self.total_cost:.2f} across {self.call_count} calls)"
        )

    def _post(self, endpoint: str, payload: dict, cost: float,
              is_listing: bool = False) -> dict:
        """POST request with caching, auth, error handling, and cost logging."""
        if not self.api_key:
            return {'error': 'AIRROI_API_KEY not configured', 'status': 'error'}

        cache_key = f"POST:{endpoint}:{json.dumps(payload, sort_keys=True)}"
        cached = self._cache_get(cache_key, is_listing=is_listing)
        if cached is not None:
            return cached

        try:
            response = requests.post(
                f"{self.base_url}/{endpoint}",
                json=payload,
                headers={
                    'X-api-key': self.api_key,
                    'Content-Type': 'application/json',
                },
                timeout=30,
            )
            self._log_cost(endpoint, cost)
            response.raise_for_status()
            data = response.json()
            self._cache_set(cache_key, data)
            return data

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            body = ''
            try:
                body = e.response.text[:300] if e.response is not None else ''
            except Exception:
                pass
            print(f"[Airroi] HTTP {status} on {endpoint}: {body}")
            return {
                'error': f'Airroi API returned {status}',
                'status': 'error',
                'http_status': status,
            }
        except requests.exceptions.RequestException as e:
            print(f"[Airroi] Request failed for {endpoint}: {e}")
            return {'error': f'Airroi API request failed: {str(e)}', 'status': 'error'}
        except json.JSONDecodeError:
            print(f"[Airroi] Invalid JSON from {endpoint}")
            return {'error': 'Invalid JSON response from Airroi', 'status': 'error'}

    def _get(self, endpoint: str, params: dict, cost: float,
             is_listing: bool = False) -> dict:
        """GET request with caching, auth, error handling, and cost logging."""
        if not self.api_key:
            return {'error': 'AIRROI_API_KEY not configured', 'status': 'error'}

        cache_key = f"GET:{endpoint}:{json.dumps(params, sort_keys=True)}"
        cached = self._cache_get(cache_key, is_listing=is_listing)
        if cached is not None:
            return cached

        try:
            response = requests.get(
                f"{self.base_url}/{endpoint}",
                params=params,
                headers={'X-api-key': self.api_key},
                timeout=30,
            )
            self._log_cost(endpoint, cost)
            response.raise_for_status()
            data = response.json()
            self._cache_set(cache_key, data)
            return data

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            body = ''
            try:
                body = e.response.text[:300] if e.response is not None else ''
            except Exception:
                pass
            print(f"[Airroi] HTTP {status} on {endpoint}: {body}")
            return {
                'error': f'Airroi API returned {status}',
                'status': 'error',
                'http_status': status,
            }
        except requests.exceptions.RequestException as e:
            print(f"[Airroi] Request failed for {endpoint}: {e}")
            return {'error': f'Airroi API request failed: {str(e)}', 'status': 'error'}
        except json.JSONDecodeError:
            print(f"[Airroi] Invalid JSON from {endpoint}")
            return {'error': 'Invalid JSON response from Airroi', 'status': 'error'}

    # ── Postcode → lat/lng helper ────────────────────────────────────────

    @staticmethod
    def postcode_to_latlng(postcode: str) -> Optional[Tuple[float, float]]:
        """
        Convert UK postcode to latitude/longitude via postcodes.io (free, no key).
        Returns (lat, lng) or None on failure.
        """
        try:
            pc = postcode.strip().replace(' ', '%20')
            res = requests.get(
                f"https://api.postcodes.io/postcodes/{pc}",
                timeout=5,
            )
            if res.status_code == 200:
                data = res.json()
                if data.get('status') == 200 and data.get('result'):
                    lat = data['result']['latitude']
                    lng = data['result']['longitude']
                    print(f"[Airroi] Postcode {postcode} → ({lat}, {lng})")
                    return (lat, lng)
            print(f"[Airroi] postcodes.io lookup failed for {postcode}: {res.status_code}")
            return None
        except Exception as e:
            print(f"[Airroi] postcodes.io error for {postcode}: {e}")
            return None

    # ── Public API methods ───────────────────────────────────────────────

    def get_market_summary(self, postcode: str) -> dict:
        """
        Get Airbnb market summary for an area.

        POST /markets/summary  ($0.05)
        Returns: market overview including avg nightly rate, occupancy,
                 revenue estimates, active listings count, etc.
        """
        coords = self.postcode_to_latlng(postcode)
        if not coords:
            return {'error': f'Could not geocode postcode {postcode}', 'status': 'error'}

        lat, lng = coords
        return self._post(
            'markets/summary',
            {
                'lat': lat,
                'lon': lng,
                'currency': 'GBP',
            },
            cost=0.05,
            is_listing=False,
        )

    def get_occupancy_trend(self, market_id: str) -> dict:
        """
        Get occupancy rate trends for a market.

        POST /markets/metrics/occupancy  ($0.05)
        Returns: monthly occupancy rates over time.
        Requires market_id from get_market_summary().
        """
        if not market_id:
            return {'error': 'market_id is required', 'status': 'error'}

        return self._post(
            'markets/metrics/occupancy',
            {'market_id': market_id},
            cost=0.05,
            is_listing=False,
        )

    def get_adr_trend(self, market_id: str) -> dict:
        """
        Get Average Daily Rate (ADR) trends for a market.

        POST /markets/metrics/average-daily-rate  ($0.05)
        Returns: monthly ADR over time.
        Requires market_id from get_market_summary().
        """
        if not market_id:
            return {'error': 'market_id is required', 'status': 'error'}

        return self._post(
            'markets/metrics/average-daily-rate',
            {'market_id': market_id},
            cost=0.05,
            is_listing=False,
        )

    def get_nearby_listings(self, postcode: str, radius_km: float = 3.0,
                            bedrooms: int = None) -> dict:
        """
        Search Airbnb listings near a postcode.

        POST /listings/search/radius  ($0.25)
        Returns: list of nearby active Airbnb listings with nightly rates,
                 ratings, property type, etc.
        """
        coords = self.postcode_to_latlng(postcode)
        if not coords:
            return {'error': f'Could not geocode postcode {postcode}', 'status': 'error'}

        lat, lng = coords
        payload = {
            'lat': lat,
            'lon': lng,
            'radius': radius_km,
            'currency': 'GBP',
        }
        if bedrooms is not None:
            payload['bedrooms'] = bedrooms

        return self._post(
            'listings/search/radius',
            payload,
            cost=0.25,
            is_listing=True,
        )

    def get_listing_comparables(self, listing_id: str) -> dict:
        """
        Get comparable listings for a specific Airbnb listing.

        GET /listings/comparables  ($0.05)
        Returns: similar listings with performance metrics for comparison.
        """
        if not listing_id:
            return {'error': 'listing_id is required', 'status': 'error'}

        return self._get(
            'listings/comparables',
            {'listing_id': listing_id},
            cost=0.05,
            is_listing=True,
        )

    # ── Convenience: full SA market intelligence in one call ─────────────

    def get_sa_market_intelligence(self, postcode: str, bedrooms: int = 2) -> dict:
        """
        Combined call: market summary + nearby listings + trends.
        Returns a unified dict for the SA analysis pipeline.

        Total cost: $0.40 (summary $0.05 + occupancy $0.05 + ADR $0.05 + listings $0.25)
        With caching, repeat calls within TTL cost $0.00.
        """
        result = {
            'postcode': postcode.upper().strip(),
            'success': False,
            'market_summary': None,
            'occupancy_trend': None,
            'adr_trend': None,
            'nearby_listings': None,
            'errors': [],
        }

        # 1. Market summary (needed to get market_id for trends)
        summary = self.get_market_summary(postcode)
        if 'error' in summary:
            result['errors'].append(f"Market summary: {summary['error']}")
        else:
            result['market_summary'] = summary
            result['success'] = True  # At least partial success

            # 2. Extract market_id and fetch trends
            market_id = self._extract_market_id(summary)
            if market_id:
                occ = self.get_occupancy_trend(market_id)
                if 'error' not in occ:
                    result['occupancy_trend'] = occ
                else:
                    result['errors'].append(f"Occupancy trend: {occ['error']}")

                adr = self.get_adr_trend(market_id)
                if 'error' not in adr:
                    result['adr_trend'] = adr
                else:
                    result['errors'].append(f"ADR trend: {adr['error']}")

        # 3. Nearby listings (independent of market_id)
        listings = self.get_nearby_listings(postcode, bedrooms=bedrooms)
        if 'error' not in listings:
            result['nearby_listings'] = listings
            result['success'] = True
        else:
            result['errors'].append(f"Nearby listings: {listings['error']}")

        # 4. Build aggregated stats from nearby listings
        if result['nearby_listings']:
            result['listing_stats'] = self._compute_listing_stats(
                result['nearby_listings']
            )

        result['api_cost'] = f"${self.total_cost:.2f}"
        result['timestamp'] = datetime.now().isoformat()
        return result

    # ── Private helpers for data extraction ──────────────────────────────

    @staticmethod
    def _extract_market_id(summary: dict) -> Optional[str]:
        """
        Extract market_id from a market summary response.
        Airroi nests it differently depending on the response version.
        """
        # Try common locations
        for key in ('market_id', 'marketId', 'id'):
            if key in summary:
                return str(summary[key])
        # Nested under 'data' or 'market'
        for wrapper in ('data', 'market', 'result'):
            if isinstance(summary.get(wrapper), dict):
                nested = summary[wrapper]
                for key in ('market_id', 'marketId', 'id'):
                    if key in nested:
                        return str(nested[key])
        print("[Airroi] Could not extract market_id from summary response")
        return None

    @staticmethod
    def _compute_listing_stats(listings_response: dict) -> dict:
        """
        Compute summary statistics from nearby listings response.
        Returns avg/min/max nightly rate, avg occupancy, avg rating, count.
        """
        # Airroi may nest listings under 'data', 'listings', or 'results'
        items = []
        for key in ('data', 'listings', 'results'):
            candidate = listings_response.get(key)
            if isinstance(candidate, list):
                items = candidate
                break
        if not items and isinstance(listings_response, list):
            items = listings_response

        if not items:
            return {'count': 0}

        rates = []
        occupancies = []
        ratings = []
        revenues = []

        for item in items:
            # Nightly rate
            for k in ('adr', 'average_daily_rate', 'nightly_rate', 'price', 'rate'):
                val = item.get(k)
                if val is not None:
                    try:
                        r = float(val)
                        if r > 0:
                            rates.append(r)
                    except (ValueError, TypeError):
                        pass
                    break

            # Occupancy
            for k in ('occupancy', 'occupancy_rate', 'occ'):
                val = item.get(k)
                if val is not None:
                    try:
                        o = float(val)
                        occupancies.append(o)
                    except (ValueError, TypeError):
                        pass
                    break

            # Rating
            for k in ('rating', 'stars', 'review_score'):
                val = item.get(k)
                if val is not None:
                    try:
                        rt = float(val)
                        if rt > 0:
                            ratings.append(rt)
                    except (ValueError, TypeError):
                        pass
                    break

            # Revenue
            for k in ('revenue', 'monthly_revenue', 'annual_revenue'):
                val = item.get(k)
                if val is not None:
                    try:
                        rev = float(val)
                        if rev > 0:
                            revenues.append(rev)
                    except (ValueError, TypeError):
                        pass
                    break

        stats: Dict = {'count': len(items)}

        if rates:
            stats['avg_nightly_rate'] = round(sum(rates) / len(rates), 2)
            stats['min_nightly_rate'] = round(min(rates), 2)
            stats['max_nightly_rate'] = round(max(rates), 2)
            stats['median_nightly_rate'] = round(
                sorted(rates)[len(rates) // 2], 2
            )

        if occupancies:
            stats['avg_occupancy'] = round(sum(occupancies) / len(occupancies), 1)

        if ratings:
            stats['avg_rating'] = round(sum(ratings) / len(ratings), 1)

        if revenues:
            stats['avg_revenue'] = round(sum(revenues) / len(revenues), 0)

        # Estimated monthly revenue from rate + occupancy
        if rates and occupancies:
            avg_rate = sum(rates) / len(rates)
            avg_occ = sum(occupancies) / len(occupancies)
            # occupancy might be 0-1 or 0-100
            occ_fraction = avg_occ if avg_occ <= 1 else avg_occ / 100
            stats['estimated_monthly_revenue'] = round(
                avg_rate * 30 * occ_fraction, 0
            )

        return stats


# ── Module-level singleton ───────────────────────────────────────────────
# Mirrors pattern used by PropertyDataAPI in property_data.py
airroi_client = AirroiAPI()
