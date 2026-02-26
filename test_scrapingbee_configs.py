#!/usr/bin/env python3
"""Test ScrapingBee with different configurations"""

import requests
import os

SCRAPINGBEE_API_KEY = os.environ.get('SCRAPINGBEE_API_KEY') or 'FLJ5HUFLWZTW46GNZDDXRD93VM3ONK6BO3YYEKRR9L77O1NA5BYNUVFTYXV3J9BJ056ZWF50ZRY1DNDA'

# Test with different Rightmove property URLs
TEST_URLS = [
    "https://www.rightmove.co.uk/properties/153629507",  # Different property
    "https://www.zoopla.co.uk/for-sale/details/68436704/",  # Try Zoopla instead
    "https://www.onthemarket.com/details/12345678",  # OnTheMarket
]

def test_with_config(url, config_name, extra_params=None):
    """Test ScrapingBee with specific config"""
    print(f"\n{'='*60}")
    print(f"Config: {config_name}")
    print(f"URL: {url}")
    print(f"{'='*60}")
    
    params = {
        'api_key': SCRAPINGBEE_API_KEY,
        'url': url,
        'render_js': 'true',
        'premium_proxy': 'true',
        'country_code': 'gb',
        'wait': '3000',  # Increased wait time
    }
    
    if extra_params:
        params.update(extra_params)
    
    try:
        response = requests.get('https://app.scrapingbee.com/api/v1/', params=params, timeout=90)
        print(f"Status: {response.status_code}")
        print(f"Length: {len(response.text)} bytes")
        
        html = response.text
        
        # Check for success indicators
        if response.status_code == 200:
            if "You appear to be using a very old browser" in html:
                print("❌ BLOCKED: Rightmove block page")
                return False
            elif "property-details" in html or "property-price" in html or "£" in html:
                print("✅ SUCCESS: Got property data")
                return True
            else:
                print(f"⚠️ UNCLEAR: No clear block, but no property data")
                return False
        else:
            print(f"❌ ERROR: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        return False

if __name__ == "__main__":
    print("🐝 ScrapingBee Configuration Test")
    
    # Test different configs on the same URL
    test_url = "https://www.rightmove.co.uk/properties/153629507"
    
    configs = [
        ("Standard", {}),
        ("Stealth JS", {'stealth_proxy': 'true'}),
        ("Longer wait", {'wait': '5000'}),
        ("No JS", {'render_js': 'false'}),
        ("Full stealth", {'stealth_proxy': 'true', 'wait': '5000'}),
    ]
    
    print(f"\nTesting URL: {test_url}")
    
    results = []
    for name, extra in configs:
        success = test_with_config(test_url, name, extra)
        results.append((name, success))
    
    print(f"\n{'='*60}")
    print("CONFIGURATION RESULTS")
    print(f"{'='*60}")
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {name}")
