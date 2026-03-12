# Land Registry API Integration

API Key: 9f426bbe-b54e-487f-bc20-42f38f143686

## Endpoints

### Price Paid Data API
Base URL: `https://landregistry.data.gov.uk/ppd-data.html`

### SPARQL Query Endpoint
URL: `http://landregistry.data.gov.uk/landregistry/query`

## Common Queries

### 1. Get Sold Prices by Postcode
```sparql
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX ppd: <http://landregistry.data.gov.uk/def/ppi/>
PREFIX lrcommon: <http://landregistry.data.gov.uk/def/common/>

SELECT ?transaction ?price ?date ?property ?street ?town ?postcode
WHERE {
  ?transaction ppd:pricePaid ?price ;
               ppd:transactionDate ?date ;
               ppd:propertyAddress ?property .
  
  ?property lrcommon:postcode "M14 6LT"^^xsd:string .
  
  OPTIONAL { ?property lrcommon:street ?street }
  OPTIONAL { ?property lrcommon:town ?town }
  OPTIONAL { ?property lrcommon:postcode ?postcode }
}
ORDER BY DESC(?date)
LIMIT 10
```

### 2. Get Average Price by Postcode (Last 12 Months)
```sparql
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX ppd: <http://landregistry.data.gov.uk/def/ppi/>
PREFIX lrcommon: <http://landregistry.data.gov.uk/def/common/>

SELECT (AVG(?price) AS ?avgPrice) (COUNT(?transaction) AS ?salesCount)
WHERE {
  ?transaction ppd:pricePaid ?price ;
               ppd:transactionDate ?date ;
               ppd:propertyAddress ?property .
  
  ?property lrcommon:postcode "M14 6LT"^^xsd:string .
  
  FILTER (?date >= "2025-01-01"^^xsd:date)
}
```

## Python Integration

```python
import requests
import json

LAND_REGISTRY_API_KEY = "9f426bbe-b54e-487f-bc20-42f38f143686"
LAND_REGISTRY_ENDPOINT = "http://landregistry.data.gov.uk/landregistry/query"

def get_sold_prices(postcode, limit=10):
    """Get recent sold prices for a postcode"""
    
    query = f"""
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    PREFIX ppd: <http://landregistry.data.gov.uk/def/ppi/>
    PREFIX lrcommon: <http://landregistry.data.gov.uk/def/common/>
    
    SELECT ?price ?date ?street ?town
    WHERE {{
      ?transaction ppd:pricePaid ?price ;
                   ppd:transactionDate ?date ;
                   ppd:propertyAddress ?property .
      
      ?property lrcommon:postcode "{postcode}"^^xsd:string .
      
      OPTIONAL {{ ?property lrcommon:street ?street }}
      OPTIONAL {{ ?property lrcommon:town ?town }}
    }}
    ORDER BY DESC(?date)
    LIMIT {limit}
    """
    
    headers = {
        "Accept": "application/sparql-results+json",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    response = requests.post(
        LAND_REGISTRY_ENDPOINT,
        headers=headers,
        data={"query": query}
    )
    
    return response.json()

def get_market_trends(postcode, months=12):
    """Get price trends for an area"""
    # Implementation here
    pass
```

## Data Returned

- **Transaction ID** - Unique identifier
- **Price Paid** - Sale price in GBP
- **Date** - Transaction date
- **Property Type** - D=Detached, S=Semi, T=Terraced, F=Flat
- **Old/New** - Y=New build, N=Established
- **Duration** - F=Freehold, L=Leasehold
- **Postcode** - Full postcode
- **Street** - Street name
- **Town** - Town/city

## Limitations

- Data delayed by ~3 months
- Only includes registered sales
- Cash sales may not appear immediately
- Scotland uses different registry

## Usage Limits

- No explicit rate limits documented
- Be reasonable (max 100 requests/minute)
- Cache results for repeated queries
