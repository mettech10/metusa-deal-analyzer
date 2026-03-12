#!/usr/bin/env python3
"""Test PropertyData API directly"""

import requests
import os

# Get the API key from environment
API_KEY = os.environ.get('PROPERTY_DATA_API_KEY', '')

print(f"API Key from env: {API_KEY[:20]}..." if API_KEY else "No API key found")
print(f"Key length: {len(API_KEY)}")

if not API_KEY:
    print("\n❌ PROPERTY_DATA_API_KEY not set in environment")
    exit(1)

# Test different endpoints
endpoints = [
    ('prices', {'postcode': 'M1 1AA'}),
    ('valuation-rent', {'postcode': 'M1 1AA', 'bedrooms': 3}),
    ('sold-prices', {'postcode': 'M1 1AA'}),
]

BASE_URL = "https://api.propertydata.co.uk"

for endpoint, params in endpoints:
    print(f"\n{'='*60}")
    print(f"Testing: {endpoint}")
    print(f"{'='*60}")
    
    params['key'] = API_KEY
    
    try:
        response = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=15)
        print(f"Status: {response.status_code}")
        print(f"URL: {response.url.replace(API_KEY, 'API_KEY_HIDDEN')}")
        
        if response.ok:
            data = response.json()
            print(f"✅ Success!")
            if 'estimate' in data:
                print(f"Estimate: £{data['estimate'].get('monthly', 'N/A')}/month")
            elif 'data' in data:
                print(f"Data keys: {list(data['data'].keys())[:5]}")
        else:
            print(f"❌ Error: {response.text[:200]}")
            
    except Exception as e:
        print(f"❌ Exception: {e}")
