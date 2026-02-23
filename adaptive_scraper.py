"""
Adaptive Web Scraper for Property Listings
Designed to work like Scrapling - handles anti-bot measures and adapts to site changes
"""

import requests
import re
import random
import time
from typing import Dict, Optional, List
from urllib.parse import urlparse

class AdaptiveScraper:
    """
    Adaptive web scraper that handles anti-bot measures
    Similar to Scrapling architecture - can be swapped for Scrapling.Fetcher later
    """
    
    # Rotating user agents to avoid detection
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0'
    ]
    
    def __init__(self):
        self.session = requests.Session()
        self.last_request_time = 0
        self.min_delay = 1  # Minimum seconds between requests
    
    def _get_headers(self, referer: str = None) -> Dict:
        """Generate realistic headers for each request"""
        headers = {
            'User-Agent': random.choice(self.USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-GB,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'cross-site',
            'Cache-Control': 'max-age=0'
        }
        
        if referer:
            headers['Referer'] = referer
        else:
            headers['Referer'] = 'https://www.google.com/search?q=property+for+sale+uk'
        
        return headers
    
    def _rate_limit(self):
        """Ensure we don't make requests too quickly"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self.last_request_time = time.time()
    
    def fetch(self, url: str, timeout: int = 15) -> Optional[str]:
        """
        Fetch page content with anti-bot measures
        Returns HTML content or None if failed
        """
        self._rate_limit()
        
        domain = urlparse(url).netloc
        
        try:
            headers = self._get_headers()
            
            response = self.session.get(
                url,
                headers=headers,
                timeout=timeout,
                allow_redirects=True,
                verify=True
            )
            
            response.raise_for_status()
            
            # Check if we got blocked
            if 'captcha' in response.text.lower() or 'cloudflare' in response.text.lower():
                print(f"[Scraper] Bot detection triggered for {domain}")
                return None
            
            return response.text
            
        except requests.exceptions.RequestException as e:
            print(f"[Scraper] Request failed: {e}")
            return None
        except Exception as e:
            print(f"[Scraper] Error: {e}")
            return None
    
    def extract_with_retry(self, url: str, max_retries: int = 2) -> Optional[str]:
        """Try to fetch with retries using different user agents"""
        for attempt in range(max_retries):
            result = self.fetch(url)
            if result:
                return result
            
            if attempt < max_retries - 1:
                time.sleep(2)  # Wait before retry
        
        return None


class PropertyExtractor:
    """
    Extracts property data from HTML
    Adaptive parser that learns from different site structures
    """
    
    def __init__(self, html: str, url: str):
        self.html = html
        self.url = url
        self.text = self._clean_text(html)
        self.domain = urlparse(url).netloc.lower()
    
    def _clean_text(self, html: str) -> str:
        """Clean HTML to extract readable text"""
        text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def extract(self) -> Dict:
        """Extract all property data"""
        return {
            'address': self._extract_address(),
            'postcode': self._extract_postcode(),
            'price': self._extract_price(),
            'property_type': self._extract_property_type(),
            'bedrooms': self._extract_bedrooms(),
            'description': self._extract_description()
        }
    
    def _extract_price(self) -> Optional[int]:
        """Extract price using multiple patterns"""
        patterns = [
            r'£([0-9,]+)',
            r'&pound;([0-9,]+)',
            r'Guide Price[\s:]*£([0-9,]+)',
            r'Offers in Excess of[\s:]*£([0-9,]+)',
            r'Asking Price[\s:]*£([0-9,]+)',
            r'Price[\s:]*£([0-9,]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, self.html, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1).replace(',', ''))
                except ValueError:
                    continue
        return None
    
    def _extract_postcode(self) -> Optional[str]:
        """Extract postcode with validation"""
        all_postcodes = re.findall(r'([A-Z]{1,2}[0-9][A-Z0-9]?\s?[0-9][A-Z]{2})', self.html)
        
        valid_postcodes = []
        for pc in set(all_postcodes):
            pc_clean = pc.replace(' ', '')
            if len(pc_clean) >= 5 and len(pc_clean) <= 7:
                if pc_clean[0] not in 'QVXZ':
                    valid_postcodes.append(pc)
        
        if not valid_postcodes:
            return None
        
        # Try to match with address area
        address = self._extract_address()
        if address:
            area_match = re.search(r'([A-Z]{1,2}[0-9]{1,2})', address)
            if area_match:
                area_code = area_match.group(1)
                for pc in valid_postcodes:
                    if pc.replace(' ', '').startswith(area_code):
                        return pc
        
        return valid_postcodes[0] if valid_postcodes else None
    
    def _extract_bedrooms(self) -> Optional[int]:
        """Extract bedroom count"""
        patterns = [
            r'(\d+)\s*bedroom',
            r'(\d+)\s*bed',
            r'(\d+)\s*br',
            r'(\d+)\s*beds',
            r'(\d+)\s*bed\s+property'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, self.text, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue
        return None
    
    def _extract_property_type(self) -> Optional[str]:
        """Extract property type"""
        types = [
            'detached', 'semi-detached', 'semi', 'terraced', 
            'end terrace', 'flat', 'apartment', 'studio', 
            'bungalow', 'maisonette', 'townhouse', 'cottage'
        ]
        
        for ptype in types:
            if re.search(r'\b' + ptype + r'\b', self.text, re.IGNORECASE):
                if ptype == 'semi':
                    return 'Semi-Detached'
                return ptype.title()
        return None
    
    def _extract_address(self) -> Optional[str]:
        """Extract address - site specific logic"""
        # Try title first
        title_match = re.search(r'<title>(.*?)</title>', self.html, re.IGNORECASE)
        if title_match:
            title = title_match.group(1)
            title = re.sub(r'\s*[-|]\s*(Rightmove|Zoopla|OnTheMarket).*', '', title, flags=re.IGNORECASE)
            
            # Extract after "for sale in"
            sale_match = re.search(r'for sale\s+(?:in|at)\s+(.+?)(?:,\s*[A-Z]{1,2}[0-9]|$)', title, re.IGNORECASE)
            if sale_match:
                return sale_match.group(1).strip()
        
        # Try meta description
        meta_match = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"', self.html, re.IGNORECASE)
        if meta_match:
            desc = meta_match.group(1)
            addr_match = re.search(r'for sale\s+(?:in|at)\s+([^,]+(?:Road|Street|Lane|Avenue|Drive|Close)[^,]*)', desc, re.IGNORECASE)
            if addr_match:
                return addr_match.group(1).strip()
        
        return None
    
    def _extract_description(self) -> Optional[str]:
        """Extract property description"""
        # Look for description meta or common description containers
        meta_match = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"', self.html, re.IGNORECASE)
        if meta_match:
            desc = meta_match.group(1)
            # Clean up
            desc = re.sub(r'for sale.*?\.\s*', '', desc, flags=re.IGNORECASE)
            return desc[:500] if desc else None
        return None


# Main function to use in app.py
def extract_property_from_url_adaptive(url: str) -> Dict:
    """
    Main entry point - extracts property data from URL
    Uses adaptive scraper with retry logic
    """
    scraper = AdaptiveScraper()
    
    # Try to fetch with retries
    html = scraper.extract_with_retry(url, max_retries=2)
    
    if not html:
        return {
            'address': None,
            'postcode': None,
            'price': None,
            'property_type': None,
            'bedrooms': None,
            'description': None,
            'error': 'Failed to fetch page - may be blocked or unavailable'
        }
    
    # Extract data
    extractor = PropertyExtractor(html, url)
    data = extractor.extract()
    
    return data


# Backward compatibility - replace old function
def extract_property_from_url(url):
    """Backward compatible wrapper"""
    return extract_property_from_url_adaptive(url)
