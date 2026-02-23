"""
Playwright Scraper for Protected Sites (Zoopla, etc.)
Headless browser automation to bypass anti-bot measures
"""

import re
from typing import Dict, Optional

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("[Playwright] Not available")

from scrapling_extractor import PropertyExtractor as FallbackExtractor


class PlaywrightPropertyScraper:
    """
    Uses Playwright headless browser for sites with strong anti-bot protection
    Falls back to requests-based scraper if Playwright fails
    """
    
    def __init__(self):
        self.fallback = FallbackExtractor()
    
    def _extract_from_html(self, html: str, url: str) -> Dict:
        """Extract property data from HTML"""
        import re
        
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
        
        # Price
        match = re.search(r'£([\d,]+)', html)
        if match:
            try:
                data['price'] = int(match.group(1).replace(',', ''))
            except:
                pass
        
        # Postcode
        all_postcodes = re.findall(r'([A-Z]{1,2}[\d][A-Z\d]?\s?[\d][A-Z]{2})', html)
        valid = [pc for pc in set(all_postcodes) 
                if len(pc.replace(' ', '')) >= 5 
                and pc[0] not in 'QVXZ']
        if valid:
            data['postcode'] = valid[0]
        
        # Bedrooms
        match = re.search(r'(\d+)\s*bed', text, re.IGNORECASE)
        if match:
            data['bedrooms'] = int(match.group(1))
        
        # Property type
        for ptype in ['detached', 'semi', 'terraced', 'flat', 'bungalow']:
            if re.search(r'\b' + ptype + r'\b', text, re.IGNORECASE):
                data['property_type'] = 'Semi-Detached' if ptype == 'semi' else ptype.title()
                break
        
        # Address extraction - site specific
        is_zoopla = 'zoopla' in url.lower()
        
        if is_zoopla:
            # Zoopla-specific patterns
            # Try h1 tag first (Zoopla puts address there)
            h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
            if h1_match:
                h1_text = re.sub(r'<[^>]+>', '', h1_match.group(1))
                h1_text = re.sub(r'\s+', ' ', h1_text).strip()
                # Clean up - remove "for sale" and price
                h1_text = re.sub(r'for sale', '', h1_text, flags=re.IGNORECASE)
                h1_text = re.sub(r'£[\d,]+', '', h1_text)
                if len(h1_text) > 10:
                    data['address'] = h1_text.strip(' -,')
            
            # Fallback: look for address in JSON-LD or meta
            if not data['address']:
                addr_match = re.search(r'"streetAddress"\s*:\s*"([^"]+)"', html)
                if addr_match:
                    data['address'] = addr_match.group(1)
        
        else:
            # Rightmove/OTM pattern - from title
            title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
            if title_match:
                title = title_match.group(1)
                title = re.sub(r'\s*[-|]\s*(Rightmove|Zoopla|OnTheMarket).*', '', title, flags=re.IGNORECASE)
                match = re.search(r'for sale\s+(?:in|at)\s+(.+?)(?:,\s*[A-Z]|$)', title, re.IGNORECASE)
                if match:
                    data['address'] = match.group(1).strip()
        
        return data
    
    def _extract_with_playwright(self, url: str, wait_time: int = 3) -> Optional[str]:
        """
        Fetch page using Playwright headless browser
        Executes JavaScript, handles dynamic content
        """
        if not PLAYWRIGHT_AVAILABLE:
            return None
        
        try:
            with sync_playwright() as p:
                # Launch browser with anti-detection
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-web-security',
                        '--disable-features=IsolateOrigins,site-per-process',
                    ]
                )
                
                # Create context with realistic settings
                context = browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='en-GB',
                    timezone_id='Europe/London',
                )
                
                # Add scripts to hide automation
                context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    window.chrome = { runtime: {} };
                """)
                
                page = context.new_page()
                
                # Navigate with timeout (increased for Zoopla)
                page.goto(url, wait_until='domcontentloaded', timeout=30000)
                
                # Wait for content to load
                page.wait_for_timeout(wait_time * 1000)
                
                # Additional wait for dynamic content
                try:
                    page.wait_for_load_state('networkidle', timeout=10000)
                except:
                    pass  # Continue even if networkidle doesn't complete
                
                # Get page content
                html = page.content()
                
                browser.close()
                return html
                
        except PlaywrightTimeout:
            print("[Playwright] Timeout waiting for page")
            return None
        except Exception as e:
            print(f"[Playwright] Error: {e}")
            return None
    
    def extract_property(self, url: str) -> Dict:
        """
        Extract property data using best available method
        Tries Playwright first for protected sites, falls back to requests
        """
        # Determine if site needs Playwright
        needs_playwright = any(domain in url.lower() for domain in [
            'zoopla.co.uk',
            'primelocation.com',
        ])
        
        html = None
        used_method = "fallback"
        
        # Try Playwright for protected sites
        if needs_playwright and PLAYWRIGHT_AVAILABLE:
            print(f"[Scraper] Using Playwright for protected site: {url}")
            html = self._extract_with_playwright(url)
            if html:
                used_method = "playwright"
        
        # Fallback to requests if Playwright not available or failed
        if not html:
            print(f"[Scraper] Using fallback method: {url}")
            html = self.fallback.fetch(url)
        
        if not html:
            return {
                'address': None,
                'postcode': None,
                'price': None,
                'property_type': None,
                'bedrooms': None,
                'description': None,
                'error': 'Failed to fetch page',
                'method': 'failed'
            }
        
        # Extract data from HTML
        data = self._extract_from_html(html, url)
        data['method'] = used_method
        
        return data


# Unified function - combines both methods
def extract_property_advanced(url: str) -> Dict:
    """
    Main entry point - uses Playwright for protected sites, requests for others
    """
    scraper = PlaywrightPropertyScraper()
    return scraper.extract_property(url)


# Keep backward compatibility
def extract_property_from_url(url: str) -> Dict:
    """Backward compatible wrapper"""
    return extract_property_advanced(url)
