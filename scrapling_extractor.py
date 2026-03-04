"""
Scrapling-Style Web Scraper
Enhanced with better anti-bot bypass headers
"""

import requests
import re
import time
import random
import json
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
        postcode_re = r'[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}'

        # Strategy 1: HTML <title> tag — most reliable because it IS the listing address.
        # Rightmove/Zoopla titles look like:
        #   "3 bed semi for sale in Orme Avenue, Alkrington, Manchester M24 1JZ | Rightmove"
        title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
        if title_match:
            title_pc = re.findall(postcode_re, title_match.group(1).upper())
            if title_pc:
                pc = title_pc[0].strip()
                if ' ' not in pc:
                    pc = pc[:-3] + ' ' + pc[-3:]
                return pc

        # Strategy 2: JSON / schema.org structured data (also property-specific)
        for json_pattern in [
            r'"postcode":\s*"([A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})"',
            r'"postalCode":\s*"([A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})"',
        ]:
            m = re.search(json_pattern, html, re.IGNORECASE)
            if m:
                pc = m.group(1).strip().upper()
                if ' ' not in pc:
                    pc = pc[:-3] + ' ' + pc[-3:]
                return pc

        # Strategy 3: Collect all candidates from page and score by context
        # Penalise any postcode that appears near agent/branch/contact words
        AGENT_WORDS = {'estate agent', 'branch', 'contact us', 'tel:', 'our office',
                       'agent', 'call us', 'vat no', 'company number', 'registered'}
        all_pcs = re.findall(postcode_re, html.upper())
        seen = {}
        for raw_pc in all_pcs:
            pc = raw_pc.strip()
            if ' ' not in pc:
                pc = pc[:-3] + ' ' + pc[-3:]
            if not re.match(r'^[A-Z]{1,2}\d[A-Z\d]?\s\d[A-Z]{2}$', pc):
                continue
            if pc in seen:
                continue
            # Score this occurrence
            for m in re.finditer(re.escape(raw_pc), html.upper()):
                ctx = html[max(0, m.start() - 300): m.start() + 300].lower()
                score = 0
                if any(w in ctx for w in AGENT_WORDS):
                    score -= 200
                seen[pc] = max(seen.get(pc, -9999), score)

        if seen:
            best = max(seen, key=lambda k: seen[k])
            if seen[best] >= 0:
                return best

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
        
        # ── Structured-data address extraction (most reliable) ──────────────

        # 5a. __NEXT_DATA__ JSON (Rightmove is Next.js — this is the gold standard)
        next_data_match = re.search(
            r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
            html, re.DOTALL | re.IGNORECASE
        )
        if next_data_match:
            try:
                nd = json.loads(next_data_match.group(1))
                # Rightmove path: props.pageProps.propertyData.address.displayAddress
                prop = (nd.get('props', {})
                          .get('pageProps', {})
                          .get('propertyData', {}))
                addr_obj = prop.get('address', {})
                display = (addr_obj.get('displayAddress')
                           or addr_obj.get('streetAddress')
                           or addr_obj.get('summary'))
                if display and len(display) > 3:
                    data['address'] = display.strip()
                    print(f"[Scraper] Address from __NEXT_DATA__: {data['address']}")
                # Also grab postcode if not already found
                if not data['postcode']:
                    outcode = addr_obj.get('outcode', '')
                    incode  = addr_obj.get('incode', '')
                    if outcode and incode:
                        data['postcode'] = f"{outcode} {incode}".upper()
                    elif addr_obj.get('postcode'):
                        data['postcode'] = addr_obj['postcode'].upper()
            except Exception as e:
                print(f"[Scraper] __NEXT_DATA__ parse error: {e}")

        # 5b. meta itemprop="streetAddress" (schema.org — works on Rightmove & Zoopla)
        if not data['address']:
            meta_addr = re.search(
                r'<meta[^>]+itemprop=["\']streetAddress["\'][^>]+content=["\']([^"\']+)["\']'
                r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]+itemprop=["\']streetAddress["\']',
                html, re.IGNORECASE
            )
            if meta_addr:
                addr = (meta_addr.group(1) or meta_addr.group(2) or '').strip()
                if addr and len(addr) > 3:
                    data['address'] = addr
                    print(f"[Scraper] Address from meta itemprop: {data['address']}")

        # 5c. JSON-LD structured data (<script type="application/ld+json">)
        if not data['address']:
            for ld_match in re.finditer(
                r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                html, re.DOTALL | re.IGNORECASE
            ):
                try:
                    ld = json.loads(ld_match.group(1))
                    # Handle both single object and array
                    items = ld if isinstance(ld, list) else [ld]
                    for item in items:
                        addr_obj = item.get('address', {})
                        if isinstance(addr_obj, str):
                            if len(addr_obj) > 3:
                                data['address'] = addr_obj.strip()
                                break
                        elif isinstance(addr_obj, dict):
                            street = (addr_obj.get('streetAddress')
                                      or addr_obj.get('name'))
                            if street and len(street) > 3:
                                data['address'] = street.strip()
                                # Grab postalCode too
                                if not data['postcode'] and addr_obj.get('postalCode'):
                                    data['postcode'] = addr_obj['postalCode'].upper()
                                break
                    if data['address']:
                        print(f"[Scraper] Address from JSON-LD: {data['address']}")
                        break
                except Exception:
                    continue

        # 5d. CSS class selector — h1/h2 with 'address' in the class name
        if not data['address']:
            css_addr = re.search(
                r'<(?:h1|h2|span|p|div)[^>]+class=["\'][^"\']*address[^"\']*["\'][^>]*>\s*([^<]{5,120})\s*<',
                html, re.IGNORECASE
            )
            if css_addr:
                addr = css_addr.group(1).strip()
                if addr and len(addr) > 3:
                    data['address'] = addr
                    print(f"[Scraper] Address from CSS class: {data['address']}")

        # 5e. HTML <title> fallback — least reliable but catches remaining cases
        if not data['address']:
            title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
            if title_match:
                title = title_match.group(1)
                title = re.sub(r'\s*[-|]\s*(Rightmove|Zoopla|OnTheMarket).*', '', title, flags=re.IGNORECASE)
                title = re.sub(r'^(?:to let|for sale|to rent)\s*:\s*', '', title, flags=re.IGNORECASE)
                sale_in = re.search(r'\b(?:for sale|to rent|to let)\s+(?:in|at)\s+', title, re.IGNORECASE)
                if sale_in:
                    data['address'] = title[sale_in.end():].strip()
                else:
                    clean = re.sub(
                        r'^(?:\d+\s+)?(?:bed(?:room)?s?\s+)?'
                        r'(?:(?:detached|semi[- ]detached|terraced|flat|apartment|bungalow|maisonette|studio)\s+)?'
                        r'(?:house|property|home)?\s*',
                        '', title, flags=re.IGNORECASE
                    ).strip()
                    if clean and len(clean) > 5:
                        data['address'] = clean

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
