"""
Scrapling-Style Web Scraper
Enhanced with better anti-bot bypass headers
"""

import requests
import re
import time
import random
from typing import Dict, Optional

# Rotate user agents to avoid detection
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]

class PropertyExtractor:
    """
    Extracts property data from listing pages
    Enhanced anti-bot measures
    """
    
    def __init__(self):
        self.session = requests.Session()
    
    def fetch(self, url: str) -> Optional[str]:
        """Fetch page with enhanced anti-bot headers"""
        
        # Select random user agent
        ua = random.choice(USER_AGENTS)
        
        headers = {
            'User-Agent': ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-GB,en;q=0.9,en-US;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'Referer': 'https://www.google.com/',
        }
        
        # Add some delays to seem more human
        time.sleep(random.uniform(0.5, 1.5))
        
        try:
            # Use session with cookies
            response = self.session.get(url, headers=headers, timeout=20, allow_redirects=True)
            response.raise_for_status()
            
            # Check for blocks
            text_lower = response.text.lower()
            if any(block in text_lower for block in ['captcha', 'blocked', 'access denied', 'rate limit', 'we\'re sorry']):
                print("[Scraper] Blocked or CAPTCHA detected")
                return None
            
            return response.text
        except requests.exceptions.Timeout:
            print("[Scraper] Request timed out")
            return None
        except requests.exceptions.RequestException as e:
            print(f"[Scraper] Fetch failed: {e}")
            return None
    
    def _extract_postcode(self, html: str, text: str, url: str) -> Optional[str]:
        """Extract postcode using multiple strategies"""
        # Strategy 1: Look for standard UK postcode patterns
        patterns = [
            r'([A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})',  # Standard format
            r'([A-Z]{1,2}\d{1,2}\s?\d?[A-Z]{2})',   # Relaxed format
            r'"postcode":\s*"([A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})"',  # JSON
            r'"postalCode":\s*"([A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})"',  # Schema.org
        ]
        
        all_postcodes = []
        for pattern in patterns:
            found = re.findall(pattern, html, re.IGNORECASE)
            all_postcodes.extend(found)
        
        # Validate and dedupe
        valid = []
        for pc in set(all_postcodes):
            pc_clean = re.sub(r'\s+', '', pc).upper()
            # Basic UK postcode validation
            if len(pc_clean) >= 5 and len(pc_clean) <= 7:
                if pc_clean[0].isalpha() and pc_clean[0] not in 'QVXZ':
                    valid.append(pc.strip().upper())
        
        if not valid:
            return None
        
        # Strategy 2: Try to match with address/title area
        title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
        if title_match:
            title = title_match.group(1)
            area_match = re.search(r'([A-Z]{1,2}\d{1,2})', title)
            if area_match:
                area_code = area_match.group(1)
                for pc in valid:
                    if pc.replace(' ', '').startswith(area_code):
                        return pc
        
        # Strategy 3: Look for patterns near "postcode" or address words
        for keyword in ['postcode', 'address', 'location']:
            nearby = re.findall(rf'{keyword}.*?([A-Z]{{1,2}}\d[A-Z\d]?\s?\d[A-Z]{{2}})', html, re.IGNORECASE)
            if nearby:
                return nearby[0].strip().upper()
        
        # Return first valid as fallback
        return valid[0] if valid else None
    
    def extract_property(self, url: str) -> Dict:
        """Extract all property data from URL"""
        html = self.fetch(url)
        
        if not html:
            return {
                'address': None,
                'postcode': None,
                'price': None,
                'property_type': None,
                'bedrooms': None,
                'description': None,
                'error': 'Failed to fetch page'
            }
        
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text)
        
        data = {
            'address': None,
            'postcode': None,
            'price': None,
            'property_type': None,
            'bedrooms': None,
            'description': None
        }
        
        # 1. Extract price
        match = re.search(r'£([\d,]+)', html)
        if match:
            try:
                data['price'] = int(match.group(1).replace(',', ''))
            except:
                pass
        
        # 2. Extract postcode with multiple strategies
        data['postcode'] = self._extract_postcode(html, text, url)
        
        # If no postcode found, try to get area code from URL
        if not data['postcode']:
            url_match = re.search(r'properties/(\d+)', url)
            if url_match:
                # Try to find any postcode-like pattern in the page more aggressively
                fallback = re.findall(r'([A-Z]{1,2}\d{1,2}\s?\d?[A-Z]{2})', html)
                if fallback:
                    data['postcode'] = fallback[0]
        
        # 3. Extract bedrooms
        match = re.search(r'(\d+)\s*bed', text, re.IGNORECASE)
        if match:
            data['bedrooms'] = int(match.group(1))
        
        # 4. Property type
        for ptype in ['detached', 'semi', 'terraced', 'flat', 'bungalow']:
            if re.search(r'\b' + ptype + r'\b', text, re.IGNORECASE):
                data['property_type'] = 'Semi-Detached' if ptype == 'semi' else ptype.title()
                break
        
        # 5. Address from title
        title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
        if title_match:
            title = title_match.group(1)
            title = re.sub(r'\s*[-|]\s*(Rightmove|Zoopla|OnTheMarket).*', '', title, flags=re.IGNORECASE)
            match = re.search(r'for sale\s+(?:in|at)\s+(.+?)(?:,\s*[A-Z]|$)', title, re.IGNORECASE)
            if match:
                data['address'] = match.group(1).strip()
        
        return data


# Main function
def extract_property_from_url(url: str) -> Dict:
    """Extract property data from URL"""
    extractor = PropertyExtractor()
    return extractor.extract_property(url)


if __name__ == "__main__":
    # Test
    url = "https://www.rightmove.co.uk/properties/169317764"
    result = extract_property_from_url(url)
    print("\nTest Results:")
    for k, v in result.items():
        print(f"  {k}: {v}")
