"""
Land Registry API Integration
UK Price Paid Data access for deal analysis
"""

import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import os

# API Configuration
LAND_REGISTRY_ENDPOINT = "http://landregistry.data.gov.uk/landregistry/query"
API_KEY = os.getenv('LAND_REGISTRY_API_KEY', '9f426bbe-b54e-487f-bc20-42f38f143686')

class LandRegistryAPI:
    """Client for UK Land Registry Price Paid Data"""
    
    def __init__(self):
        self.endpoint = LAND_REGISTRY_ENDPOINT
        self.headers = {
            "Accept": "application/sparql-results+json",
            "Content-Type": "application/x-www-form-urlencoded"
        }
    
    # Land Registry ppd:propertyType URI suffixes → human-readable labels
    # Actual URIs: http://landregistry.data.gov.uk/def/common/{suffix}
    PROPERTY_TYPE_MAP = {
        'detached': 'detached',
        'semi-detached': 'semi-detached',
        'terraced': 'terraced',
        'flat-maisonette': 'flat',
        'otherPropertyType': 'other',
    }

    # Map our frontend property-type-detail values to Land Registry URI suffixes
    DETAIL_TO_LR_CODE = {
        'detached': 'detached',
        'semi-detached': 'semi-detached',
        'terraced': 'terraced',
        'end-of-terrace': 'terraced',          # LR groups end-terrace with terraced
        'flat-apartment': 'flat-maisonette',
        'maisonette': 'flat-maisonette',        # LR groups maisonettes with flats
        'bungalow': 'detached',                 # Bungalows typically detached in LR
        'other': 'otherPropertyType',
    }

    # Map our frontend broad type to LR URI suffixes
    BROAD_TO_LR_CODE = {
        'house': None,                          # don't filter — could be D/S/T
        'flat': 'flat-maisonette',
        'commercial': 'otherPropertyType',
    }

    def get_sold_prices(
        self,
        postcode: str,
        limit: int = 10,
        property_type_detail: str = None,
        property_type: str = None,
        tenure_type: str = None,
    ) -> List[Dict]:
        """
        Get recent sold prices for a postcode, optionally filtered by property type and tenure.

        Args:
            postcode: UK postcode (e.g., "M14 6LT")
            limit: Maximum number of results
            property_type_detail: Granular type (terraced, semi-detached, flat-apartment etc.)
            property_type: Broad type (house, flat, commercial) — used if detail not given
            tenure_type: 'freehold' or 'leasehold'

        Returns:
            List of sold price records with propertyType and tenure fields
        """
        # Resolve property type filter code for post-query filtering
        lr_code = None
        if property_type_detail:
            lr_code = self.DETAIL_TO_LR_CODE.get(property_type_detail)
        elif property_type:
            lr_code = self.BROAD_TO_LR_CODE.get(property_type)

        # Fetch a larger batch so post-filtering still yields enough results.
        # We do NOT filter in SPARQL because the Land Registry endpoint is
        # extremely slow with property-type / estate-type constraints.
        fetch_limit = limit * 5

        query = f"""
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        PREFIX ppd: <http://landregistry.data.gov.uk/def/ppi/>
        PREFIX lrcommon: <http://landregistry.data.gov.uk/def/common/>

        SELECT ?price ?date ?street ?town ?pType ?eType
        WHERE {{
          ?transaction ppd:pricePaid ?price ;
                       ppd:transactionDate ?date ;
                       ppd:propertyAddress ?property ;
                       ppd:propertyType ?pType .

          ?property lrcommon:postcode "{postcode}"^^xsd:string .

          OPTIONAL {{ ?property lrcommon:street ?street }}
          OPTIONAL {{ ?property lrcommon:town ?town }}
          OPTIONAL {{ ?transaction ppd:estateType ?eType }}
        }}
        ORDER BY DESC(?date)
        LIMIT {fetch_limit}
        """

        try:
            response = requests.post(
                self.endpoint,
                headers=self.headers,
                data={"query": query},
                timeout=30
            )
            response.raise_for_status()

            data = response.json()
            results = []

            for binding in data.get('results', {}).get('bindings', []):
                # Extract property type suffix from URI, e.g. ".../common/detached" → "detached"
                ptype_uri = binding.get('pType', {}).get('value', '')
                ptype_code = ptype_uri.rsplit('/', 1)[-1] if ptype_uri else ''
                ptype_label = self.PROPERTY_TYPE_MAP.get(ptype_code, ptype_code)

                # Extract tenure from URI
                etype_uri = binding.get('eType', {}).get('value', '')
                tenure = 'freehold' if 'freehold' in etype_uri else ('leasehold' if 'leasehold' in etype_uri else '')

                record = {
                    'price': int(binding['price']['value']),
                    'date': binding['date']['value'],
                    'street': binding.get('street', {}).get('value', 'N/A'),
                    'town': binding.get('town', {}).get('value', 'N/A'),
                    'propertyType': ptype_label,
                    'tenure': tenure,
                }

                # Post-filter by property type if requested
                if lr_code and ptype_code != lr_code:
                    continue

                # Post-filter by tenure if requested
                if tenure_type and tenure != tenure_type:
                    continue

                results.append(record)

            return results[:limit]

        except Exception as e:
            print(f"Land Registry API error: {e}")
            return []
    
    def get_average_price(self, postcode: str, months: int = 12) -> Optional[float]:
        """
        Calculate average sold price for postcode over time period
        
        Args:
            postcode: UK postcode
            months: Number of months to look back
            
        Returns:
            Average price or None if no data
        """
        # Get sales from last N months
        cutoff_date = (datetime.now() - timedelta(days=30*months)).strftime("%Y-%m-%d")
        
        query = f"""
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        PREFIX ppd: <http://landregistry.data.gov.uk/def/ppi/>
        PREFIX lrcommon: <http://landregistry.data.gov.uk/def/common/>
        
        SELECT ?price
        WHERE {{
          ?transaction ppd:pricePaid ?price ;
                       ppd:transactionDate ?date ;
                       ppd:propertyAddress ?property .
          
          ?property lrcommon:postcode "{postcode}"^^xsd:string .
          
          FILTER (?date >= "{cutoff_date}"^^xsd:date)
        }}
        """
        
        try:
            response = requests.post(
                self.endpoint,
                headers=self.headers,
                data={"query": query},
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            prices = []
            
            for binding in data.get('results', {}).get('bindings', []):
                prices.append(int(binding['price']['value']))
            
            if prices:
                return sum(prices) / len(prices)
            return None
            
        except Exception as e:
            print(f"Error calculating average: {e}")
            return None
    
    def get_price_trend(self, postcode: str) -> Dict:
        """
        Get price trend (rising/falling/stable) for postcode
        
        Returns:
            Dict with trend analysis
        """
        # Get prices from last 6 months vs 6-12 months ago
        now = datetime.now()
        
        recent_sales = self._get_sales_in_period(postcode, (now - timedelta(days=180)).strftime("%Y-%m-%d"))
        older_sales = self._get_sales_in_period(
            postcode, 
            (now - timedelta(days=365)).strftime("%Y-%m-%d"),
            (now - timedelta(days=180)).strftime("%Y-%m-%d")
        )
        
        if not recent_sales or not older_sales:
            return {"trend": "insufficient_data", "change_percent": 0}
        
        recent_avg = sum(recent_sales) / len(recent_sales)
        older_avg = sum(older_sales) / len(older_sales)
        
        change_percent = ((recent_avg - older_avg) / older_avg) * 100
        
        if change_percent > 5:
            trend = "rising"
        elif change_percent < -5:
            trend = "falling"
        else:
            trend = "stable"
        
        return {
            "trend": trend,
            "change_percent": round(change_percent, 1),
            "recent_avg": recent_avg,
            "older_avg": older_avg,
            "recent_sales": len(recent_sales),
            "older_sales": len(older_sales)
        }
    
    def _get_sales_in_period(self, postcode: str, start_date: str, end_date: str = None) -> List[int]:
        """Helper to get sales prices in a date range"""
        
        date_filter = f'FILTER (?date >= "{start_date}"^^xsd:date)'
        if end_date:
            date_filter += f' FILTER (?date < "{end_date}"^^xsd:date)'
        
        query = f"""
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        PREFIX ppd: <http://landregistry.data.gov.uk/def/ppi/>
        PREFIX lrcommon: <http://landregistry.data.gov.uk/def/common/>
        
        SELECT ?price
        WHERE {{
          ?transaction ppd:pricePaid ?price ;
                       ppd:transactionDate ?date ;
                       ppd:propertyAddress ?property .
          
          ?property lrcommon:postcode "{postcode}"^^xsd:string .
          
          {date_filter}
        }}
        """
        
        try:
            response = requests.post(
                self.endpoint,
                headers=self.headers,
                data={"query": query},
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            return [int(b['price']['value']) for b in data.get('results', {}).get('bindings', [])]
            
        except Exception as e:
            print(f"Error getting sales: {e}")
            return []

# Create global instance
land_registry = LandRegistryAPI()

if __name__ == "__main__":
    # Test the API
    print("Testing Land Registry API...")
    
    # Test with Manchester postcode
    postcode = "M14 6LT"
    
    print(f"\nRecent sales in {postcode}:")
    sales = land_registry.get_sold_prices(postcode, 5)
    for sale in sales:
        print(f"  £{sale['price']:,} - {sale['date']} - {sale['street']}")
    
    print(f"\nAverage price (12 months):")
    avg = land_registry.get_average_price(postcode)
    if avg:
        print(f"  £{avg:,.0f}")
    
    print(f"\nPrice trend:")
    trend = land_registry.get_price_trend(postcode)
    print(f"  {trend}")
