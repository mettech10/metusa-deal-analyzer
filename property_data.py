"""
PropertyData API Integration
Professional-grade UK property market intelligence
"""

import requests
import os
from datetime import datetime, timedelta
from typing import Dict, Optional
import json

# Configuration
PROPERTY_DATA_API_KEY = os.getenv('PROPERTY_DATA_API_KEY', '')
BASE_URL = "https://api.propertydata.co.uk"

class PropertyDataAPI:
    """
    Client for PropertyData.co.uk API
    Provides professional property intelligence
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or PROPERTY_DATA_API_KEY
        self.base_url = BASE_URL
        self.cache = {}  # Simple in-memory cache
        self.cache_duration = timedelta(days=7)  # Cache for 7 days
    
    def _make_request(self, endpoint: str, params: Dict) -> Dict:
        """Make API request with error handling"""
        if not self.api_key:
            return {'error': 'API key not configured'}
        
        # Add API key to params
        params['key'] = self.api_key
        
        # Check cache
        cache_key = f"{endpoint}:{json.dumps(params, sort_keys=True)}"
        if cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            if datetime.now() - cached_time < self.cache_duration:
                return cached_data
        
        try:
            response = requests.get(
                f"{self.base_url}/{endpoint}",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            # Cache successful response
            self.cache[cache_key] = (data, datetime.now())
            return data
            
        except requests.exceptions.RequestException as e:
            return {'error': f'API request failed: {str(e)}', 'status': 'error'}
        except json.JSONDecodeError:
            return {'error': 'Invalid JSON response', 'status': 'error'}
    
    def get_rental_valuation(self, postcode: str, bedrooms: int) -> Dict:
        """
        Get accurate rental valuation
        
        Args:
            postcode: UK postcode
            bedrooms: Number of bedrooms
            
        Returns:
            Dict with rental estimate, confidence, comparables
        """
        return self._make_request('valuation-rent', {
            'postcode': postcode,
            'bedrooms': bedrooms
        })
    
    def get_sales_valuation(self, postcode: str, bedrooms: int) -> Dict:
        """
        Get property sale valuation
        
        Args:
            postcode: UK postcode
            bedrooms: Number of bedrooms
            
        Returns:
            Dict with sale estimate
        """
        return self._make_request('valuation-sale', {
            'postcode': postcode,
            'bedrooms': bedrooms
        })
    
    def get_sold_prices(self, postcode: str) -> Dict:
        """
        Get recent sold prices with details
        
        Args:
            postcode: UK postcode
            
        Returns:
            Dict with sold price data
        """
        return self._make_request('sold-prices', {
            'postcode': postcode
        })
    
    def get_prices(self, postcode: str) -> Dict:
        """
        Get current market prices (active listings)
        
        Args:
            postcode: UK postcode
            
        Returns:
            Dict with current listing prices
        """
        return self._make_request('prices', {
            'postcode': postcode
        })
    
    def get_sales_valuation(self, postcode: str, bedrooms: int) -> Dict:
        """
        Get sales valuation estimate for a property
        
        Args:
            postcode: UK postcode
            bedrooms: Number of bedrooms
            
        Returns:
            Dict with sale estimate
        """
        return self._make_request('valuation-sale', {
            'postcode': postcode,
            'bedrooms': bedrooms
        })
    
    def get_market_trends(self, postcode: str) -> Dict:
        """
        Get comprehensive market trends
        
        Args:
            postcode: UK postcode
            
        Returns:
            Dict with trend data (growth, volume, etc.)
        """
        return self._make_request('market-trends', {
            'postcode': postcode
        })
    
    def get_area_data(self, postcode: str) -> Dict:
        """
        Get area intelligence
        
        Args:
            postcode: UK postcode
            
        Returns:
            Dict with demographics, crime, schools, transport
        """
        return self._make_request('area', {
            'postcode': postcode
        })
    
    def get_planning_applications(self, postcode: str, radius: int = 1000) -> Dict:
        """
        Get nearby planning applications
        
        Args:
            postcode: UK postcode
            radius: Search radius in meters (default 1000)
            
        Returns:
            Dict with planning applications
        """
        return self._make_request('planning', {
            'postcode': postcode,
            'radius': radius
        })
    
    def get_demographics(self, postcode: str) -> Dict:
        """
        Get demographic data
        
        Args:
            postcode: UK postcode
            
        Returns:
            Dict with population, age, employment data
        """
        return self._make_request('demographics', {
            'postcode': postcode
        })
    
    def get_crime_data(self, postcode: str) -> Dict:
        """
        Get crime statistics
        
        Args:
            postcode: UK postcode
            
        Returns:
            Dict with crime rates and trends
        """
        return self._make_request('crime', {
            'postcode': postcode
        })
    
    def get_comprehensive_analysis(self, postcode: str, bedrooms: int) -> Dict:
        """
        Get comprehensive property analysis
        Combines multiple endpoints for complete picture
        
        Args:
            postcode: UK postcode
            bedrooms: Number of bedrooms
            
        Returns:
            Dict with all available data
        """
        return {
            'rental_valuation': self.get_rental_valuation(postcode, bedrooms),
            'sales_valuation': self.get_sales_valuation(postcode, bedrooms),
            'sold_prices': self.get_sold_prices(postcode),
            'market_trends': self.get_market_trends(postcode),
            'area_data': self.get_area_data(postcode),
            'demographics': self.get_demographics(postcode),
            'crime': self.get_crime_data(postcode),
            'planning': self.get_planning_applications(postcode)
        }
    
    def is_configured(self) -> bool:
        """Check if API key is configured"""
        return bool(self.api_key and self.api_key != 'your_api_key_here')

# Global instance
property_data = PropertyDataAPI()

# Helper function for deal analysis
def get_market_context(postcode: str, bedrooms: int) -> Dict:
    """
    Get essential market context for deal analysis
    
    Args:
        postcode: UK postcode
        bedrooms: Number of bedrooms
        
    Returns:
        Dict with rental estimate, sold prices, trends, comparables
    """
    if not property_data.is_configured():
        return {'error': 'PropertyData API not configured'}
    
    # Get key data points
    rental = property_data.get_rental_valuation(postcode, bedrooms)
    trends = property_data.get_market_trends(postcode)
    sold = property_data.get_sold_prices(postcode)
    prices = property_data.get_prices(postcode)  # Current listings
    area = property_data.get_area_data(postcode)
    
    context = {
        'source': 'PropertyData API',
        'postcode': postcode,
        'bedrooms': bedrooms
    }
    
    # Extract rental estimate
    if 'estimate' in rental:
        context['estimated_rent'] = rental['estimate'].get('monthly')
        context['rental_confidence'] = rental.get('confidence')
        context['rental_range'] = rental.get('range', {})
    
    # Extract market trends
    if 'data' in trends:
        context['price_growth_12m'] = trends['data'].get('growth_12m')
        context['price_growth_5y'] = trends['data'].get('growth_5y')
        context['avg_days_on_market'] = trends['data'].get('avg_days_on_market')
        context['sales_volume'] = trends['data'].get('sales_volume_12m')
    
    # Extract sold prices (for comparables)
    if 'data' in sold:
        raw_sales = sold['data']
        prices_list = [p.get('price', 0) for p in raw_sales if p.get('price')]
        if prices_list:
            context['avg_sold_price'] = sum(prices_list) / len(prices_list)
            context['sold_price_count'] = len(prices_list)
            # Format comparable sales for display
            context['comparable_sales'] = [
                {
                    'address': f"{s.get('street', 'Unknown')}, {postcode}",
                    'price': s.get('price', 0),
                    'type': s.get('type', 'N/A').replace('_', ' ').title(),
                    'date': s.get('date', 'N/A'),
                    'bedrooms': s.get('bedrooms', bedrooms)
                }
                for s in raw_sales[:10]  # Top 10 sales
                if s.get('price')
            ]
    
    # Extract current market prices (comparable listings)
    if 'data' in prices:
        raw_prices = prices['data']
        context['comparable_listings'] = [
            {
                'address': f"{p.get('address', 'Unknown')}, {postcode}",
                'price': p.get('price', 0),
                'type': p.get('type', 'N/A').replace('_', ' ').title(),
                'bedrooms': p.get('bedrooms', bedrooms),
                'agent': p.get('agent', 'N/A')
            }
            for p in raw_prices[:10]  # Top 10 listings
            if p.get('price')
        ]
        # Calculate average asking price
        asking_prices = [p.get('price', 0) for p in raw_prices if p.get('price')]
        if asking_prices:
            context['avg_asking_price'] = sum(asking_prices) / len(asking_prices)
    
    # Extract area data
    if 'data' in area:
        context['area_score'] = area['data'].get('area_score')
        context['transport_score'] = area['data'].get('transport_score')
        context['schools_score'] = area['data'].get('schools_score')
    
    return context

if __name__ == "__main__":
    # Test the API
    print("Testing PropertyData API...")
    
    if not property_data.is_configured():
        print("❌ API key not configured. Set PROPERTY_DATA_API_KEY environment variable.")
        exit(1)
    
    postcode = "M14 6LT"
    bedrooms = 3
    
    print(f"\n📍 Testing with {postcode}, {bedrooms} bedrooms\n")
    
    # Test rental valuation
    print("1. Rental Valuation:")
    rental = property_data.get_rental_valuation(postcode, bedrooms)
    if 'estimate' in rental:
        print(f"   Monthly: £{rental['estimate']['monthly']}")
        print(f"   Confidence: {rental.get('confidence', 'N/A')}")
    else:
        print(f"   Error: {rental.get('error', 'Unknown error')}")
    
    # Test market trends
    print("\n2. Market Trends:")
    trends = property_data.get_market_trends(postcode)
    if 'data' in trends:
        print(f"   12-month growth: {trends['data'].get('growth_12m', 'N/A')}%")
        print(f"   Avg days on market: {trends['data'].get('avg_days_on_market', 'N/A')}")
    else:
        print(f"   Error: {trends.get('error', 'Unknown error')}")
    
    print("\n✅ Test complete!")
