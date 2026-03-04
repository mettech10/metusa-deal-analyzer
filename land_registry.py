"""
Land Registry API Integration
UK Price Paid Data via HMLR Linked Data REST API
(replaces the old SPARQL endpoint which was unreliable / blocked)
"""

import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import os


# HMLR Linked Data REST API — no API key required, free to use
# Docs: https://landregistry.data.gov.uk/app/ppd
_HMLR_API = "https://landregistry.data.gov.uk/data/ppi/transaction-record.json"

# Fallback: HMLR SPARQL endpoint (kept as backup)
_SPARQL_ENDPOINT = "https://landregistry.data.gov.uk/landregistry/query"


def _norm_postcode(postcode: str) -> str:
    """Upper-case and ensure a single space before the inward code."""
    pc = postcode.upper().replace(' ', '')
    if len(pc) > 3:
        pc = pc[:-3] + ' ' + pc[-3:]
    return pc


class LandRegistryAPI:
    """Client for UK Land Registry Price Paid Data."""

    # Map HMLR property type codes → readable strings
    _PROP_TYPE = {
        'D': 'Detached', 'S': 'Semi-Detached',
        'T': 'Terraced', 'F': 'Flat/Maisonette', 'O': 'Other',
    }

    def get_sold_prices(self, postcode: str, limit: int = 10) -> List[Dict]:
        """
        Fetch recent sold prices for a postcode via HMLR Linked Data API.

        Returns a list of dicts with keys: price, date, street, town, type.
        Falls back to SPARQL endpoint if the REST API fails.
        """
        pc = _norm_postcode(postcode)
        results = self._get_via_rest(pc, limit)
        if not results:
            results = self._get_via_sparql(pc, limit)
        return results

    # ------------------------------------------------------------------ #
    # HMLR Linked Data REST API                                            #
    # ------------------------------------------------------------------ #

    def _get_via_rest(self, postcode: str, limit: int) -> List[Dict]:
        try:
            params = {
                'postcode': postcode,
                '_pageSize': limit,
                '_sort': '-transactionDate',
            }
            resp = requests.get(_HMLR_API, params=params, timeout=8)
            resp.raise_for_status()
            body = resp.json()
            items = body.get('result', {}).get('items', [])
            out = []
            for item in items:
                try:
                    addr = item.get('propertyAddress', {})
                    street_parts = [
                        item.get('paon', ''),
                        item.get('saon', ''),
                        addr.get('street', ''),
                    ]
                    street = ' '.join(p for p in street_parts if p).strip() or 'N/A'
                    town = addr.get('town', 'N/A') or addr.get('locality', 'N/A')
                    price_raw = item.get('pricePaid')
                    date_raw  = item.get('transactionDate', '')
                    ptype_raw = item.get('propertyType', {})
                    if isinstance(ptype_raw, dict):
                        ptype_code = ptype_raw.get('prefLabel', {}).get('_value', '')
                    else:
                        ptype_code = str(ptype_raw)
                    ptype = self._PROP_TYPE.get(ptype_code[:1].upper(), ptype_code or 'N/A')

                    if price_raw:
                        out.append({
                            'price': int(price_raw),
                            'date':  date_raw[:10] if date_raw else 'N/A',
                            'street': street,
                            'town':   town,
                            'type':   ptype,
                        })
                except Exception:
                    continue
            print(f"[LandRegistry REST] {len(out)} records for {postcode}")
            return out
        except Exception as e:
            print(f"[LandRegistry REST] error: {e}")
            return []

    # ------------------------------------------------------------------ #
    # SPARQL fallback                                                       #
    # ------------------------------------------------------------------ #

    def _get_via_sparql(self, postcode: str, limit: int) -> List[Dict]:
        query = f"""
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        PREFIX ppd: <http://landregistry.data.gov.uk/def/ppi/>
        PREFIX lrcommon: <http://landregistry.data.gov.uk/def/common/>

        SELECT ?price ?date ?street ?town ?paon ?propertyType
        WHERE {{
          ?transaction ppd:pricePaid ?price ;
                       ppd:transactionDate ?date ;
                       ppd:propertyAddress ?property .
          ?property lrcommon:postcode "{postcode}"^^xsd:string .
          OPTIONAL {{ ?property lrcommon:street ?street }}
          OPTIONAL {{ ?property lrcommon:town ?town }}
          OPTIONAL {{ ?property lrcommon:paon ?paon }}
          OPTIONAL {{ ?transaction ppd:propertyType ?propertyType }}
        }}
        ORDER BY DESC(?date)
        LIMIT {limit}
        """
        try:
            resp = requests.post(
                _SPARQL_ENDPOINT,
                headers={
                    'Accept': 'application/sparql-results+json',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                data={'query': query},
                timeout=10,
            )
            resp.raise_for_status()
            bindings = resp.json().get('results', {}).get('bindings', [])
            out = []
            for b in bindings:
                price_raw = b.get('price', {}).get('value')
                if not price_raw:
                    continue
                paon   = b.get('paon',  {}).get('value', '')
                street = b.get('street', {}).get('value', '')
                combined = (paon + ' ' + street).strip() or 'N/A'
                ptype_uri = b.get('propertyType', {}).get('value', '')
                ptype = self._PROP_TYPE.get(ptype_uri[-1:].upper(), 'N/A') if ptype_uri else 'N/A'
                out.append({
                    'price':  int(price_raw),
                    'date':   b.get('date', {}).get('value', 'N/A')[:10],
                    'street': combined,
                    'town':   b.get('town', {}).get('value', 'N/A'),
                    'type':   ptype,
                })
            print(f"[LandRegistry SPARQL] {len(out)} records for {postcode}")
            return out
        except Exception as e:
            print(f"[LandRegistry SPARQL] error: {e}")
            return []

    # ------------------------------------------------------------------ #
    # Derived helpers                                                       #
    # ------------------------------------------------------------------ #

    def get_average_price(self, postcode: str, months: int = 12) -> Optional[float]:
        sales = self.get_sold_prices(postcode, limit=50)
        cutoff = datetime.now() - timedelta(days=30 * months)
        prices = []
        for s in sales:
            try:
                if datetime.strptime(s['date'], '%Y-%m-%d') >= cutoff:
                    prices.append(s['price'])
            except Exception:
                continue
        return sum(prices) / len(prices) if prices else None

    def get_price_trend(self, postcode: str) -> Dict:
        sales = self.get_sold_prices(postcode, limit=50)
        now = datetime.now()
        recent, older = [], []
        for s in sales:
            try:
                dt = datetime.strptime(s['date'], '%Y-%m-%d')
                if dt >= now - timedelta(days=180):
                    recent.append(s['price'])
                elif dt >= now - timedelta(days=365):
                    older.append(s['price'])
            except Exception:
                continue

        if not recent or not older:
            return {'trend': 'insufficient_data', 'change_percent': 0}

        recent_avg = sum(recent) / len(recent)
        older_avg  = sum(older)  / len(older)
        change_pct = (recent_avg - older_avg) / older_avg * 100

        trend = 'rising' if change_pct > 5 else ('falling' if change_pct < -5 else 'stable')
        return {
            'trend':          trend,
            'change_percent': round(change_pct, 1),
            'recent_avg':     recent_avg,
            'older_avg':      older_avg,
        }


# Global instance
land_registry = LandRegistryAPI()


if __name__ == "__main__":
    postcode = "M14 6LT"
    print(f"Testing Land Registry for {postcode}…")
    sales = land_registry.get_sold_prices(postcode, 5)
    for s in sales:
        print(f"  £{s['price']:,}  {s['date']}  {s['street']}")
    avg = land_registry.get_average_price(postcode)
    print(f"Average (12mo): £{avg:,.0f}" if avg else "No average data")
    print("Trend:", land_registry.get_price_trend(postcode))
