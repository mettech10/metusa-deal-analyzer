"""
Scrapling-Style Web Scraper
Uses working requests as primary (since it works reliably)
Keeps Scrapling structure for future upgrade
"""

import requests
import re
from typing import Dict, Optional

class PropertyExtractor:
    """
    Extracts property data from listing pages
    Works reliably with Rightmove, Zoopla, OnTheMarket
    """
    
    def fetch(self, url: str) -> Optional[str]:
        """Fetch page with anti-bot headers"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-GB,en;q=0.9',
            'Referer': 'https://www.google.com/search?q=property+for+sale'
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            # Check for blocks
            if 'captcha' in response.text.lower():
                print("[Scraper] CAPTCHA detected")
                return None
                
            return response.text
        except Exception as e:
            print(f"[Scraper] Fetch failed: {e}")
            return None
    
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
        
        # 2. Extract postcode with validation
        all_postcodes = re.findall(r'([A-Z]{1,2}[\d][A-Z\d]?\s?[\d][A-Z]{2})', html)
        valid = []
        for pc in set(all_postcodes):
            pc_clean = pc.replace(' ', '')
            if len(pc_clean) >= 5 and len(pc_clean) <= 7 and pc_clean[0] not in 'QVXZ':
                valid.append(pc)
        
        if valid:
            # Try to match with address area
            title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
            if title_match:
                title = title_match.group(1)
                area_match = re.search(r'([A-Z]{1,2}\d{1,2})', title)
                if area_match:
                    area_code = area_match.group(1)
                    for pc in valid:
                        if pc.replace(' ', '').startswith(area_code):
                            data['postcode'] = pc
                            break
            
            if not data['postcode']:
                data['postcode'] = valid[0]
        
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
