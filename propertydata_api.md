# PropertyData API Integration

**Service:** PropertyData.co.uk
**Cost:** £49-149/month (API access)
**Value:** Professional-grade property intelligence

## Why PropertyData Beats Free APIs

| Feature | Land Registry | PropertyData |
|---------|---------------|--------------|
| Sold Prices | ✅ Yes | ✅ Yes + more detail |
| Rental Valuations | ❌ No | ✅ Yes (accurate) |
| Market Trends | ⚠️ Basic | ✅ Detailed |
| Void Periods | ❌ No | ✅ Yes |
| Tenant Demand | ❌ No | ✅ Yes |
| Demographics | ❌ No | ✅ Yes |
| Planning Apps | ❌ No | ✅ Yes |
| Broadband Speed | ❌ No | ✅ Yes |

## API Endpoints

Base URL: `https://api.propertydata.co.uk/v1`

### 1. Property Valuation (Rental)
```
GET /valuation-rent?key={API_KEY}&postcode={POSTCODE}&bedrooms={N}
```

Returns:
```json
{
  "status": "success",
  "postcode": "SW1A 1AA",
  "bedrooms": 2,
  "estimate": {
    "weekly": 450,
    "monthly": 1950,
    "yearly": 23400
  },
  "confidence": "high",
  "comparables": [...]
}
```

### 2. Sold Prices
```
GET /sold-prices?key={API_KEY}&postcode={POSTCODE}
```

### 3. Market Trends
```
GET /market-trends?key={API_KEY}&postcode={POSTCODE}
```

### 4. Area Intelligence
```
GET /area?key={API_KEY}&postcode={POSTCODE}
```

Returns demographics, crime, schools, transport

### 5. Planning Applications
```
GET /planning?key={API_KEY}&postcode={POSTCODE}&radius=1000
```

## Python Integration

```python
import requests
import os

PROPERTY_DATA_API_KEY = os.getenv('PROPERTY_DATA_API_KEY')
BASE_URL = "https://api.propertydata.co.uk/v1"

class PropertyDataAPI:
    def __init__(self, api_key=None):
        self.api_key = api_key or PROPERTY_DATA_API_KEY
        self.base_url = BASE_URL
    
    def get_rental_valuation(self, postcode, bedrooms):
        """Get accurate rental estimate"""
        endpoint = f"{self.base_url}/valuation-rent"
        params = {
            'key': self.api_key,
            'postcode': postcode,
            'bedrooms': bedrooms
        }
        
        response = requests.get(endpoint, params=params)
        return response.json()
    
    def get_sold_prices(self, postcode):
        """Get recent sold prices with more detail than Land Registry"""
        endpoint = f"{self.base_url}/sold-prices"
        params = {
            'key': self.api_key,
            'postcode': postcode
        }
        
        response = requests.get(endpoint, params=params)
        return response.json()
    
    def get_market_trends(self, postcode):
        """Get comprehensive market trends"""
        endpoint = f"{self.base_url}/market-trends"
        params = {
            'key': self.api_key,
            'postcode': postcode
        }
        
        response = requests.get(endpoint, params=params)
        return response.json()
    
    def get_area_data(self, postcode):
        """Get area intelligence (demographics, crime, schools)"""
        endpoint = f"{self.base_url}/area"
        params = {
            'key': self.api_key,
            'postcode': postcode
        }
        
        response = requests.get(endpoint, params=params)
        return response.json()
    
    def get_planning_applications(self, postcode, radius=1000):
        """Get nearby planning applications"""
        endpoint = f"{self.base_url}/planning"
        params = {
            'key': self.api_key,
            'postcode': postcode,
            'radius': radius
        }
        
        response = requests.get(endpoint, params=params)
        return response.json()

# Usage
api = PropertyDataAPI()

# Get rental estimate
rental = api.get_rental_valuation("M14 6LT", 3)
print(f"Estimated rent: £{rental['estimate']['monthly']}/month")

# Get market trends
trends = api.get_market_trends("M14 6LT")
print(f"Price growth: {trends['growth_12m']}%")
```

## Data for Deal Analysis

### 1. **Rental Valuation** (Most Important)
- Accurate monthly rent estimate
- Confidence level
- Comparable rentals
- **Use:** Validate user's rent assumption

### 2. **Sold Prices**
- Recent sales (up to 5 years)
- Property type breakdown
- Price per sq ft
- **Use:** Compare to asking price

### 3. **Market Trends**
- 1-year price growth
- 5-year forecast
- Sales volume trends
- Days on market
- **Use:** Assess market timing

### 4. **Area Intelligence**
- Population demographics
- Employment rates
- Crime statistics
- School ratings
- Transport links
- **Use:** Evaluate rental demand

### 5. **Planning Applications**
- New developments nearby
- Change of use applications
- Extensions/conversions
- **Use:** Identify future supply/demand

## Sample Response - Rental Valuation

```json
{
  "status": "success",
  "postcode": "M14 6LT",
  "bedrooms": 2,
  "property_type": "flat",
  "estimate": {
    "weekly": 425,
    "monthly": 1842,
    "yearly": 22100
  },
  "range": {
    "low_weekly": 395,
    "high_weekly": 455
  },
  "confidence": "high",
  "sample_size": 47,
  "comparables": [
    {
      "address": "14 Oakfield Avenue",
      "rent": 450,
      "date": "2025-12-15",
      "distance": 0.2
    }
  ],
  "market_trend": "rising",
  "demand_score": 8.5
}
```

## Cost-Benefit Analysis

**Monthly Cost:** £49-149
**Per Deal Value:** If it prevents ONE bad deal (£20k+ loss), it's worth 100+ months

### When to Subscribe:
- ✅ Going live with paying customers
- ✅ Need highest accuracy possible
- ✅ Analyzing 10+ deals per month

### When Free APIs Are Enough:
- ⚠️ MVP/testing phase
- ⚠️ < 5 deals per month
- ⚠️ Tight budget

## Getting API Key

1. Go to: https://propertydata.co.uk/api
2. Sign up for plan (£49 Bronze or £149 Silver)
3. Get API key from dashboard
4. Set environment variable:
   ```bash
   export PROPERTY_DATA_API_KEY="your_key_here"
   ```

## Rate Limits

- Bronze (£49): 1000 requests/month
- Silver (£149): 5000 requests/month
- Gold (£499): Unlimited

**Caching Strategy:** Cache results for 7 days to save requests
