#!/usr/bin/env python3
"""Test ScrapingBee API with a real Rightmove URL"""

import requests
import os

# Test URLs (Rightmove properties)
TEST_URLS = [
    "https://www.rightmove.co.uk/properties/144949591",  # Your test URL
    "https://www.rightmove.co.uk/property-for-sale/Manchester/3-bed-houses.html",
]

# Get API key from env or use the hardcoded one
SCRAPINGBEE_API_KEY = os.environ.get('SCRAPINGBEE_API_KEY') or 'FLJ5HUFLWZTW46GNZDDXRD93VM3ONK6BO3YYEKRR9L77O1NA5BYNUVFTYXV3J9BJ056ZWF50ZRY1DNDA'

def test_scrapingbee(url):
    """Test ScrapingBee with a URL"""
    print(f"\n{'='*60}")
    print(f"Testing URL: {url}")
    print(f"{'='*60}")
    
    if not SCRAPINGBEE_API_KEY:
        print("❌ ERROR: SCRAPINGBEE_API_KEY not configured")
        return False
    
    api_url = 'https://app.scrapingbee.com/api/v1/'
    params = {
        'api_key': SCRAPINGBEE_API_KEY,
        'url': url,
        'render_js': 'true',
        'premium_proxy': 'true',
        'country_code': 'gb',
        'wait': '2000',
    }
    
    print(f"API Key (first 20 chars): {SCRAPINGBEE_API_KEY[:20]}...")
    print(f"Using premium_proxy: True")
    print(f"Country: GB")
    
    try:
        response = requests.get(api_url, params=params, timeout=60)
        print(f"\nResponse Status: {response.status_code}")
        print(f"Content Length: {len(response.text)} bytes")
        
        if response.status_code == 200:
            # Check if we got real content or a block page
            html = response.text
            if "You appear to be using a very old browser" in html:
                print("⚠️ WARNING: Got Rightmove block page")
                return False
            elif "property" in html.lower() or "price" in html.lower() or "£" in html:
                print("✅ SUCCESS: Got property content")
                # Extract some data to verify
                import re
                
                # Try to find price
                price_match = re.search(r'£([\d,]+)', html)
                if price_match:
                    print(f"💰 Found price: £{price_match.group(1)}")
                
                # Try to find address/postcode
                postcode_match = re.search(r'([A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})', html)
                if postcode_match:
                    print(f"📍 Found postcode: {postcode_match.group(1)}")
                
                return True
            else:
                print("⚠️ WARNING: Got HTML but no property data detected")
                print(f"Preview: {html[:200]}...")
                return False
        else:
            print(f"❌ ERROR: HTTP {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ ERROR: Request timed out (60s)")
        return False
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False

if __name__ == "__main__":
    print("🐝 ScrapingBee Test Script")
    print(f"API Key configured: {'Yes' if SCRAPINGBEE_API_KEY else 'No'}")
    
    results = []
    for url in TEST_URLS:
        success = test_scrapingbee(url)
        results.append((url, success))
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for url, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {url}")
    
    all_passed = all(r[1] for r in results)
    if all_passed:
        print("\n🎉 All tests passed! ScrapingBee is working correctly.")
    else:
        print("\n⚠️ Some tests failed. Check the errors above.")
