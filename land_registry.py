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
    
    def get_sold_prices(self, postcode: str, limit: int = 10) -> List[Dict]:
        """
        Get recent sold prices for a postcode
        
        Args:
            postcode: UK postcode (e.g., "M14 6LT")
            limit: Maximum number of results
            
        Returns:
            List of sold price records
        """
        query = f"""
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        PREFIX ppd: <http://landregistry.data.gov.uk/def/ppi/>
        PREFIX lrcommon: <http://landregistry.data.gov.uk/def/common/>
        
        SELECT ?price ?date ?street ?town ?propertyType ?duration
        WHERE {{
          ?transaction ppd:pricePaid ?price ;
                       ppd:transactionDate ?date ;
                       ppd:propertyAddress ?property .
          
          ?property lrcommon:postcode "{postcode}"^^xsd:string .
          
          OPTIONAL {{ ?property lrcommon:street ?street }}
          OPTIONAL {{ ?property lrcommon:town ?town }}
          OPTIONAL {{ ?property lrcommon:paon ?propertyType }}
        }}
        ORDER BY DESC(?date)
        LIMIT {limit}
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
            results = []
            
            for binding in data.get('results', {}).get('bindings', []):
                results.append({
                    'price': int(binding['price']['value']),
                    'date': binding['date']['value'],
                    'street': binding.get('street', {}).get('value', 'N/A'),
                    'town': binding.get('town', {}).get('value', 'N/A')
                })
            
            return results
            
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
