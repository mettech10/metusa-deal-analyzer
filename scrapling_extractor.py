"""
Scrapling Integration - Real Scrapling v0.4
Modern web scraping with anti-bot bypass
"""

import os
import sys

# Add user site-packages to path for Scrapling
user_site = os.path.expanduser('~/Library/Python/3.8/lib/python/site-packages')
if user_site not in sys.path:
    sys.path.insert(0, user_site)

try:
    from scrapling import Fetcher
    SCRAPLING_AVAILABLE = True
except ImportError:
    SCRAPLING_AVAILABLE = False
    print("[Scraper] Scrapling not available, using fallback")

import requests
import re
from typing import Dict, Optional
from urllib.parse import urlparse


class ScraplingPropertyExtractor:
    """
    Uses real Scrapling Fetcher for web scraping
    Falls back to requests if Scrapling not available
    """
    
    def __init__(self):
        self.scraper = None
        if SCRAPLING_AVAILABLE:
            try:
                # Initialize Scrapling Fetcher with stealth mode
                self.scraper = Fetcher(
                    stealth=True,  # Bypass anti-bot measures
                    auto_match=True  # Adaptive parsing
                )
                print("[Scraper] Scrapling Fetcher initialized with stealth mode")
            except Exception as e:
                print(f"[Scraper] Failed to initialize Scrapling: {e}")
                self.scraper = None
    
    def fetch(self, url: str) -> Optional[str]:
        """Fetch page using Scrapling or fallback"""
        if self.scraper:
            try:
                # Use Scrapling's adaptive fetcher
                page = self.scraper.get(url, timeout=15)
                return page.text
            except Exception as e:
                print(f"[Scraper] Scrapling fetch failed: {e}, trying fallback")
        
        # Fallback to requests with anti-bot headers
        return self._fetch_fallback(url)
    
    def _fetch_fallback(self, url: str) -> Optional[str]:
        """Fallback requests-based fetching"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-GB,en;q=0.9',
            'Referer': 'https://www.google.com/'
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"[Scraper] Fallback fetch failed: {e}")
            return None
    
    def extract_property(self, url: str) -> Dict:
        """Extract property data from URL"""
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
        
        # Use Scrapling's adaptive parser if available
        if self.scraper and SCRAPLING_AVAILABLE:
            try:
                return self._extract_with_scrapling(html, url)
            except Exception as e:
                print(f"[Scraper] Scrapling extraction failed: {e}, using regex fallback")
        
        # Fallback to regex extraction
        return self._extract_with_regex(html, url)
    
    def _extract_with_scrapling(self, html: str, url: str) -> Dict:
        """Extract using Scrapling's adaptive parser"""
        # Scrapling can parse HTML and extract data intelligently
        page = self.scraper.adaptive_parser(html)
        
        data = {
            'address': None,
            'postcode': None,
            'price': None,
            'property_type': None,
            'bedrooms': None,
            'description': None
        }
        
        # Try to extract price - look for £ patterns
        price_text = page.find(text=re.compile(r'£[\d,]+'))
        if price_text:
            price_match = re.search(r'£([\d,]+)', price_text)
            if price_match:
                try:
                    data['price'] = int(price_match.group(1).replace(',', ''))
                except:
                    pass
        
        # Extract other fields using regex (Scrapling + regex hybrid)
        return self._extract_with_regex(html, url, existing_data=data)
    
    def _extract_with_regex(self, html: str, url: str, existing_data: Dict = None) -> Dict:
        """Extract using regex patterns (fallback)"""
        if existing_data is None:
            data = {
                'address': None,
                'postcode': None,
                'price': None,
                'property_type': None,
                'bedrooms': None,
                'description': None
            }
        else:
            data = existing_data
        
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text)
        
        # Price extraction
        if not data.get('price'):
            patterns = [r'£([\d,]+)', r'&pound;([\d,]+)']
            for pattern in patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    try:
                        data['price'] = int(match.group(1).replace(',', ''))
                        break
                    except:
                        continue
        
        # Postcode extraction with validation
        all_postcodes = re.findall(r'([A-Z]{1,2}[\d][A-Z\d]?\s?[\d][A-Z]{2})', html)
        valid_postcodes = [pc for pc in set(all_postcodes) 
                          if len(pc.replace(' ', '')) >= 5 
                          and pc[0] not in 'QVXZ']
        
        if valid_postcodes:
            data['postcode'] = valid_postcodes[0]
        
        # Bedrooms
        match = re.search(r'(\d+)\s*bed', text, re.IGNORECASE)
        if match:
            data['bedrooms'] = int(match.group(1))
        
        # Property type
        types = ['detached', 'semi', 'terraced', 'flat', 'apartment', 'bungalow']
        for ptype in types:
            if re.search(r'\b' + ptype + r'\b', text, re.IGNORECASE):
                data['property_type'] = 'Semi-Detached' if ptype == 'semi' else ptype.title()
                break
        
        # Address from title
        title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
        if title_match:
            title = title_match.group(1)
            title = re.sub(r'\s*[-|]\s*(Rightmove|Zoopla|OnTheMarket).*', '', title, flags=re.IGNORECASE)
            sale_match = re.search(r'for sale\s+(?:in|at)\s+(.+?)(?:,\s*[A-Z]|$)', title, re.IGNORECASE)
            if sale_match:
                data['address'] = sale_match.group(1).strip()
        
        return data


# Main function - uses Scrapling if available, falls back to requests
def extract_property_from_url(url: str) -> Dict:
    """
    Extract property data using Scrapling v0.4
    With automatic fallback to requests
    """
    extractor = ScraplingPropertyExtractor()
    return extractor.extract_property(url)


# Keep backward compatibility
if __name__ == "__main__":
    # Test the scraper
    test_url = "https://www.rightmove.co.uk/properties/171877781"
    result = extract_property_from_url(test_url)
    print("\nTest Results:")
    for key, value in result.items():
        print(f"  {key}: {value}")
