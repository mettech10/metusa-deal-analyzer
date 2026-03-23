from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for, abort
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from collections import defaultdict
import threading
import json
import os
import hmac
import hashlib
from datetime import datetime, timedelta
import pdfkit
from jinja2 import Template
import requests
import secrets
import re
import io
from html import escape

# Import Land Registry API
from land_registry import land_registry

# Import PropertyData API (premium data)
from property_data import property_data, get_market_context as get_propertydata_context

# Import Transport APIs
from transport_api import transport_api, get_transport_context  # TfL (London)
from national_rail import national_rail, get_national_rail_context  # UK-wide

# Import Web Scrapers
from scrapling_extractor import extract_property_from_url  # For most sites

def _parse_property_markdown(text: str, source: str = 'scraper') -> dict:
    """Parse property details from markdown/plain text returned by a scraper.
    Shared by scrape_with_jina() and scrape_with_firecrawl().
    """
    data = {
        'address': None,
        'postcode': None,
        'price': None,
        'property_type': None,
        'bedrooms': None,
        'description': None,
        'sqm': None,
    }

    # --- Price ---
    price_patterns = [
        r'£([\d,]+)',
        r'price[":\s]*£?([\d,]+)',
    ]
    for pattern in price_patterns:
        price_match = re.search(pattern, text, re.IGNORECASE)
        if price_match:
            try:
                val = int(price_match.group(1).replace(',', ''))
                if val > 10000:
                    data['price'] = val
                    break
            except Exception:
                pass

    # --- Bedrooms ---
    bed_candidates = []

    bed_near_type = re.search(
        r'(\d+)\s*bed(?:room)?s?\s+(?:semi-detached|detached|terraced|flat|house|bungalow|apartment)',
        text, re.IGNORECASE
    )
    if bed_near_type:
        val = int(bed_near_type.group(1))
        if 1 <= val <= 20:
            bed_candidates.append(('near_type', val, 90))

    title_bed = re.search(r'^Title:.*?(\d+)\s*bed', text[:500], re.IGNORECASE | re.MULTILINE)
    if title_bed:
        val = int(title_bed.group(1))
        if 1 <= val <= 20:
            bed_candidates.append(('title', val, 80))

    plain_bed = re.search(r'(\d+)\s*bed(?:room)?s?', text, re.IGNORECASE)
    if plain_bed:
        val = int(plain_bed.group(1))
        if 1 <= val <= 20:
            bed_candidates.append(('plain', val, 50))

    if bed_candidates:
        bed_candidates.sort(key=lambda x: x[2], reverse=True)
        data['bedrooms'] = bed_candidates[0][1]
        print(f"[{source}] Bedroom candidates: {bed_candidates}")
    else:
        data['bedrooms'] = None

    # --- Property type ---
    property_types = ['semi-detached', 'detached', 'semi', 'terraced', 'flat', 'bungalow', 'apartment']
    for ptype in property_types:
        if re.search(r'\b' + ptype + r'\b', text, re.IGNORECASE):
            data['property_type'] = 'Semi-Detached' if ptype.lower() == 'semi' else ptype.title()
            break

    # --- Floor area (sqm) ---
    sqm_val = None
    sqm_patterns_list = [
        (r'(\d+(?:\.\d+)?)\s*(?:sq\.?\s*m|m²|m2|sqm)\b', False),
        (r'(\d+(?:\.\d+)?)\s*(?:sq\.?\s*ft|ft²|sqft)\b', True),
    ]
    for pat, is_sqft in sqm_patterns_list:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            if is_sqft:
                val = val / 10.764
            if 10 <= val <= 2000:
                sqm_val = round(val, 1)
                break
    data['sqm'] = sqm_val
    print(f"[{source}] Floor area: {sqm_val} sqm")

    # --- Postcode ---
    VALID_AREAS = {
        'AB', 'AL', 'B', 'BA', 'BB', 'BD', 'BH', 'BL', 'BN', 'BR', 'BS', 'BT',
        'CA', 'CB', 'CF', 'CH', 'CM', 'CO', 'CR', 'CT', 'CV', 'CW', 'DA', 'DD',
        'DE', 'DG', 'DH', 'DL', 'DN', 'DT', 'DY', 'E', 'EC', 'EH', 'EN', 'EX',
        'FK', 'FY', 'G', 'GL', 'GU', 'HA', 'HD', 'HG', 'HP', 'HR', 'HS', 'HU',
        'HX', 'IG', 'IP', 'IV', 'KA', 'KT', 'KW', 'KY', 'L', 'LA', 'LD', 'LE',
        'LL', 'LN', 'LS', 'LU', 'M', 'ME', 'MK', 'ML', 'N', 'NE', 'NG', 'NN',
        'NP', 'NR', 'NW', 'OL', 'OX', 'PA', 'PE', 'PH', 'PL', 'PO', 'PR', 'RG',
        'RH', 'RM', 'S', 'SA', 'SE', 'SG', 'SK', 'SL', 'SM', 'SN', 'SO', 'SP',
        'SR', 'SS', 'ST', 'SW', 'SY', 'TA', 'TD', 'TF', 'TN', 'TQ', 'TR', 'TS',
        'TW', 'UB', 'W', 'WA', 'WC', 'WD', 'WF', 'WN', 'WR', 'WS', 'WV', 'YO', 'ZE'
    }

    postcode_pattern = r'[A-Z]{1,2}\d[A-Z\d]?(?:\s)?\d[A-Z]{2}'
    all_postcodes = re.findall(postcode_pattern, text.upper())

    def format_postcode(pc):
        pc = pc.strip()
        if ' ' not in pc:
            pc = pc[:-3] + ' ' + pc[-3:]
        return pc

    def is_valid_area(pc):
        area = pc.split()[0]
        area_letters = ''.join(c for c in area if c.isalpha())
        return area_letters in VALID_AREAS

    def valid_pc(fp):
        return (re.match(r'^[A-Z]{1,2}\d[A-Z\d]?\s\d[A-Z]{2}$', fp)
                and is_valid_area(fp))

    found_postcode = None

    # Strategy 0: scan the first 1200 chars (title/URL are at the top)
    header_pcs = re.findall(postcode_pattern, text[:1200].upper())
    for pc in header_pcs:
        fp = format_postcode(pc)
        if valid_pc(fp):
            found_postcode = fp
            print(f"[{source}] Postcode from header scan: {fp}")
            break

    # Strategy 1: parse the "Title:" line
    if not found_postcode:
        title_search = re.search(r'Title:\s*(.+)', text, re.IGNORECASE)
        if title_search:
            title_text = title_search.group(1)
            title_pcs = re.findall(postcode_pattern, title_text.upper())
            for pc in title_pcs:
                fp = format_postcode(pc)
                if valid_pc(fp):
                    found_postcode = fp
                    print(f"[{source}] Postcode from title line: {fp}")
                    break

    # Strategy 2: explicit label — "Postcode: OL1 3LA"
    if not found_postcode:
        explicit = re.search(
            r'postcode[:\s]+([A-Z]{1,2}\d[A-Z\d]?(?:\s)?\d[A-Z]{2})',
            text, re.IGNORECASE
        )
        if explicit:
            fp = format_postcode(explicit.group(1).upper())
            if valid_pc(fp):
                found_postcode = fp
                print(f"[{source}] Postcode from explicit label: {fp}")

    # Strategy 3: score every candidate; penalise agent/footer context
    if not found_postcode:
        postcode_scores = {}
        for pc in all_postcodes:
            formatted_pc = format_postcode(pc)
            if formatted_pc in postcode_scores:
                continue
            if not valid_pc(formatted_pc):
                continue

            best_score = 0
            for match in re.finditer(re.escape(pc), text.upper()):
                idx = match.start()
                context = text[max(0, idx - 300):idx + 300].lower()
                score = 0

                if idx < 3000:
                    score += 60

                if any(w in context for w in ['price', '£', 'for sale', 'asking']):
                    score += 80
                if any(w in context for w in ['bedroom', 'bed', 'house', 'flat', 'property']):
                    score += 60
                if any(w in context for w in ['road', 'street', 'avenue', 'lane', 'drive', 'close']):
                    score += 50
                if 'address' in context or 'postcode' in context:
                    score += 40

                if any(w in context for w in ['estate agent', 'branch', 'contact us',
                                               'tel:', 'phone', 'call us', 'our office']):
                    score -= 200
                if any(w in context for w in ['agent address', 'agent postcode',
                                               'branch address', 'office address']):
                    score -= 100
                if any(w in context for w in ['vat', 'registration', 'company number']):
                    score -= 200

                best_score = max(best_score, score)
            postcode_scores[formatted_pc] = best_score

        if postcode_scores:
            sorted_pcs = sorted(postcode_scores.items(), key=lambda x: x[1], reverse=True)
            print(f"[{source}] Postcode candidates: {sorted_pcs[:5]}")
            best_postcode = sorted_pcs[0][0] if sorted_pcs[0][1] >= 0 else None
            found_postcode = best_postcode
            print(f"[{source}] Selected postcode (scored): {best_postcode}")
        else:
            print(f"[{source}] No valid postcodes found")

    data['postcode'] = found_postcode

    # --- Address ---
    title_line = re.search(r'^Title:\s*(.+)$', text, re.MULTILINE | re.IGNORECASE)
    if title_line:
        title = title_line.group(1).strip()
        title = re.sub(
            r'\s*[-|]\s*(Rightmove|Zoopla|OnTheMarket|Property|For Sale).*',
            '', title, flags=re.IGNORECASE
        )
        title = title.strip()
        if title and len(title) > 5:
            if data['postcode'] and data['postcode'] not in title:
                title = f"{title}, {data['postcode']}"
            data['address'] = title

    if not data['address']:
        addr_pattern = re.search(
            r'([A-Z][a-z]+(?:\s[A-Z][a-z]+)?\s+(?:Road|Street|Avenue|Lane|Drive|Way|Close|Crescent|Gardens))'
            r'[,\s]+([^,\n]{5,50})',
            text
        )
        if addr_pattern:
            data['address'] = f"{addr_pattern.group(1)}, {addr_pattern.group(2).strip()}"

    if not data['address']:
        data['address'] = "Address not available"

    print(f"[{source}] Extracted: price={data['price']}, beds={data['bedrooms']}, "
          f"sqm={data['sqm']}, postcode={data['postcode']}, address={str(data['address'])[:60]}")
    return data


def scrape_with_jina(url: str) -> dict:
    """Scrape property using Jina Reader API.
    Prepends https://r.jina.ai/ to the target URL and gets back clean markdown.
    Works for Rightmove, Zoopla, OnTheMarket and other JS-heavy sites.
    Set JINA_API_KEY env var for higher rate limits (free key from jina.ai).
    """
    jina_url = f'https://r.jina.ai/{url}'
    headers = {
        'Accept': 'text/plain',
        'X-Timeout': '20',
        'X-Return-Format': 'markdown',
        'X-No-Cache': 'true',
        'X-Remove-Selector': 'nav,footer,header,[class*="cookie"],[class*="banner"],[class*="popup"]',
    }
    if JINA_API_KEY:
        headers['Authorization'] = f'Bearer {JINA_API_KEY}'

    try:
        response = requests.get(jina_url, headers=headers, timeout=22)
        if response.status_code != 200:
            print(f"[Jina] Error: status {response.status_code}")
            return None

        text = response.text
        return _parse_property_markdown(text, source='Jina')

    except Exception as e:
        print(f"[Jina] Exception: {e}")
        return None


def scrape_with_firecrawl(url: str) -> dict:
    """Scrape property using Firecrawl API (firecrawl.dev).
    Returns clean markdown — same format as Jina but with better JS rendering.
    Free tier: 500 pages/month. Set FIRECRAWL_API_KEY env var.
    """
    if not FIRECRAWL_API_KEY:
        print("[Firecrawl] No API key configured, skipping")
        return None

    try:
        headers = {
            'Authorization': f'Bearer {FIRECRAWL_API_KEY}',
            'Content-Type': 'application/json',
        }
        payload = {
            'url': url,
            'formats': ['markdown'],
            'onlyMainContent': True,
            'timeout': 20000,
        }
        response = requests.post(
            'https://api.firecrawl.dev/v1/scrape',
            headers=headers,
            json=payload,
            timeout=25,
        )
        if response.status_code != 200:
            print(f"[Firecrawl] Error: status {response.status_code}")
            return None

        body = response.json()
        if not body.get('success'):
            print("[Firecrawl] API returned success=false")
            return None

        text = body.get('data', {}).get('markdown', '')
        if not text or len(text) < 200:
            print("[Firecrawl] Empty or very short response")
            return None

        return _parse_property_markdown(text, source='Firecrawl')

    except Exception as e:
        print(f"[Firecrawl] Exception: {e}")
        return None

def scrape_with_scrapingbee(url: str) -> dict:
    """Scrape property using ScrapingBee API with JS rendering and premium UK proxies.
    Used as a fallback when Jina and direct scraping fail (e.g. Rightmove/Zoopla block).
    Requires SCRAPINGBEE_API_KEY env var.
    """
    if not SCRAPINGBEE_API_KEY:
        print("[ScrapingBee] No API key configured, skipping")
        return None

    try:
        params = {
            'api_key': SCRAPINGBEE_API_KEY,
            'url': url,
            'render_js': 'true',
            'premium_proxy': 'true',
            'country_code': 'gb',
            'wait': '2000',
        }
        response = requests.get(
            'https://app.scrapingbee.com/api/v1/',
            params=params,
            timeout=55,
        )

        if response.status_code != 200:
            print(f"[ScrapingBee] Error: status {response.status_code}")
            return None

        html = response.text
        if not html or len(html) < 500:
            print("[ScrapingBee] Empty or very short response")
            return None

        # Use the existing PropertyExtractor to parse the raw HTML
        from scrapling_extractor import PropertyExtractor
        extractor = PropertyExtractor()
        # Bypass the fetch() method — we already have the HTML
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text)

        data = {
            'address': None,
            'postcode': None,
            'price': None,
            'property_type': None,
            'bedrooms': None,
            'description': None,
            'sqm': None,
        }

        # Price
        price_match = re.search(r'£([\d,]+)', html)
        if price_match:
            try:
                val = int(price_match.group(1).replace(',', ''))
                if val > 10000:
                    data['price'] = val
            except Exception:
                pass

        # Postcode
        data['postcode'] = extractor._extract_postcode(html, text, url)

        # Bedrooms
        bed_match = re.search(r'(\d+)\s*bed(?:room)?s?', text, re.IGNORECASE)
        if bed_match:
            val = int(bed_match.group(1))
            if 1 <= val <= 20:
                data['bedrooms'] = val

        # Property type
        for ptype in ['semi-detached', 'detached', 'terraced', 'flat', 'bungalow', 'apartment']:
            if re.search(r'\b' + ptype + r'\b', text, re.IGNORECASE):
                data['property_type'] = 'Semi-Detached' if 'semi' in ptype.lower() else ptype.title()
                break

        # Floor area
        sqm_patterns = [
            (r'(\d+(?:\.\d+)?)\s*(?:sq\.?\s*m|m²|m2|sqm)\b', False),
            (r'(\d+(?:\.\d+)?)\s*(?:sq\.?\s*ft|ft²|sqft)\b', True),
        ]
        for pat, is_sqft in sqm_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = float(m.group(1))
                if is_sqft:
                    val = val / 10.764
                if 10 <= val <= 2000:
                    data['sqm'] = round(val, 1)
                    break

        # Address from page title
        title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
        if title_match:
            title = title_match.group(1)
            title = re.sub(r'\s*[-|]\s*(Rightmove|Zoopla|OnTheMarket|Property|For Sale).*',
                           '', title, flags=re.IGNORECASE).strip()
            if title and len(title) > 5:
                if data['postcode'] and data['postcode'] not in title:
                    title = f"{title}, {data['postcode']}"
                data['address'] = title

        if not data['address']:
            data['address'] = "Address not available"

        print(f"[ScrapingBee] Extracted: price={data['price']}, beds={data['bedrooms']}, "
              f"postcode={data['postcode']}, address={str(data['address'])[:60]}")
        return data

    except Exception as e:
        print(f"[ScrapingBee] Exception: {e}")
        return None


def validate_postcode_str(postcode):
    """Quick validation of UK postcode format"""
    if not postcode:
        return False
    pattern = r'^[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}$'
    return bool(re.match(pattern, postcode.upper().strip()))


def resolve_postcode_from_address(address: str) -> str | None:
    """Query Ideal Postcodes Address Search API with a scraped address string.

    Submits the address to Royal Mail PAF and returns the postcode of the
    closest-matching result.  Returns None if the key is unset, the request
    fails, or no results are returned.
    """
    if not IDEAL_POSTCODES_API_KEY or not address:
        return None
    try:
        resp = requests.get(
            'https://api.ideal-postcodes.co.uk/v1/addresses',
            params={'api_key': IDEAL_POSTCODES_API_KEY, 'q': address},
            timeout=5,
        )
        body = resp.json()
        results = body.get('result', {}).get('hits', [])
        if results:
            postcode = results[0].get('postcode', '')
            if postcode:
                print(f"[IdealPostcodes] Resolved '{address[:60]}' → {postcode}")
                return postcode.upper().strip()
    except Exception as e:
        print(f"[IdealPostcodes] Error resolving postcode: {e}")
    return None


def get_floor_area_from_epc(address: str, postcode: str) -> float | None:
    """Look up a property's total floor area (sqm) from the UK EPC Open Data API.

    Registration at https://epc.opendatacommunities.org is required.
    Set EPC_API_EMAIL and EPC_API_KEY environment variables.
    Returns None if the API is unconfigured, the property is not found, or the
    request fails.
    """
    if not EPC_API_EMAIL or not EPC_API_KEY:
        return None
    try:
        import base64
        credentials = base64.b64encode(f"{EPC_API_EMAIL}:{EPC_API_KEY}".encode()).decode()
        params = {'size': 1}
        if postcode:
            params['postcode'] = postcode.replace(' ', '').upper()
        if address:
            # Strip the postcode from the address string so we don't double-up
            addr_clean = re.sub(r'[A-Z]{1,2}[0-9][A-Z0-9]?\s?[0-9][A-Z]{2}', '', address, flags=re.IGNORECASE).strip().strip(',')
            if addr_clean:
                params['address'] = addr_clean[:100]
        resp = requests.get(
            'https://epc.opendatacommunities.org/api/v1/domestic/search',
            headers={
                'Authorization': f'Basic {credentials}',
                'Accept': 'application/json',
            },
            params=params,
            timeout=8,
        )
        if resp.status_code != 200:
            print(f"[EPC] API error: {resp.status_code}")
            return None
        body = resp.json()
        columns = body.get('column-names', [])
        rows    = body.get('rows', [])
        if not rows:
            print(f"[EPC] No records found for {address}, {postcode}")
            return None
        try:
            idx = columns.index('total-floor-area')
            val = rows[0][idx]
            if val not in (None, '', 'N/A'):
                area = float(val)
                if 10 <= area <= 2000:
                    print(f"[EPC] Floor area: {area} sqm for {postcode}")
                    return area
        except (ValueError, IndexError):
            pass
    except Exception as e:
        print(f"[EPC] Error: {e}")
    return None


# Security: Input validation functions
def validate_postcode(postcode):
    """Validate UK postcode format"""
    pattern = r'^[A-Z]{1,2}[0-9][A-Z0-9]?\s?[0-9][A-Z]{2}$'
    return re.match(pattern, postcode.upper().strip()) is not None

def sanitize_input(value, max_length=500):
    """Sanitize user input to prevent XSS"""
    if not isinstance(value, str):
        return str(value)[:max_length]
    # Escape HTML entities
    sanitized = escape(value.strip())
    # Truncate to max length
    return sanitized[:max_length]

def validate_numeric(value, min_val=0, max_val=100000000):
    """Validate numeric inputs"""
    try:
        num = float(value)
        return min_val <= num <= max_val
    except (ValueError, TypeError):
        return False

app = Flask(__name__, template_folder='templates')

# Security: Generate secret key from environment or random
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

# Security: Session configuration
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

# ── Admin Authentication Configuration ─────────────────────────────────────
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
_admin_raw_password = os.environ.get('ADMIN_PASSWORD', '')
ADMIN_PASSWORD_HASH = generate_password_hash(_admin_raw_password) if _admin_raw_password else None
ADMIN_SESSION_TIMEOUT_MINUTES = int(os.environ.get('ADMIN_SESSION_TIMEOUT', '30'))

# ── Analytics & Error Tracking (in-memory, thread-safe) ────────────────────
_analytics_lock = threading.Lock()
_analytics = {
    'total_visits': 0,
    'page_counts': defaultdict(int),
    'api_counts': defaultdict(int),
    'daily_visits': defaultdict(int),
    'hourly_visits': defaultdict(int),
    'error_log': [],       # last 100 errors
    'recent_requests': [], # last 50 requests
    'start_time': datetime.utcnow().isoformat(),
}

def _record_visit(path, method, status_code=200, is_error=False, error_detail=None):
    """Thread-safe visit/analytics recorder."""
    now = datetime.utcnow()
    date_str = now.strftime('%Y-%m-%d')
    hour_str = now.strftime('%Y-%m-%d %H:00')
    user_agent = request.headers.get('User-Agent', '')[:200]
    ip = get_remote_address()

    entry = {
        'ts': now.isoformat(),
        'path': path,
        'method': method,
        'status': status_code,
        'ip': ip,
        'ua': user_agent,
    }

    with _analytics_lock:
        _analytics['total_visits'] += 1
        _analytics['daily_visits'][date_str] += 1
        _analytics['hourly_visits'][hour_str] += 1

        if path.startswith('/api/') or path in ('/analyze', '/ai-analyze', '/extract-url',
                                                  '/epc-lookup', '/download-pdf'):
            _analytics['api_counts'][path] += 1
        else:
            _analytics['page_counts'][path] += 1

        _analytics['recent_requests'].append(entry)
        if len(_analytics['recent_requests']) > 50:
            _analytics['recent_requests'] = _analytics['recent_requests'][-50:]

        if is_error:
            err_entry = {**entry, 'error': error_detail or 'Unknown error'}
            _analytics['error_log'].append(err_entry)
            if len(_analytics['error_log']) > 100:
                _analytics['error_log'] = _analytics['error_log'][-100:]


def admin_required(f):
    """Decorator: require active admin session with inactivity timeout."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        last_activity = session.get('admin_last_activity')
        if last_activity:
            last_dt = datetime.fromisoformat(last_activity)
            if datetime.utcnow() - last_dt > timedelta(minutes=ADMIN_SESSION_TIMEOUT_MINUTES):
                session.clear()
                return redirect(url_for('admin_login') + '?timeout=1')
        session['admin_last_activity'] = datetime.utcnow().isoformat()
        return f(*args, **kwargs)
    return decorated


@app.before_request
def track_analytics():
    """Record every incoming request for analytics (skip static/admin)."""
    path = request.path
    if path.startswith('/admin') or path.startswith('/static'):
        return
    _record_visit(path, request.method)

# Security: Configure CORS properly (restrict in production)
_allowed_origins = [
    "https://metusaproperty.co.uk",
    "https://analyzer.metusaproperty.co.uk",
    # dealcheck-uk / Metalyzi frontend
    "https://metalyzi.co.uk",
    "https://www.metalyzi.co.uk",
    "https://dealcheck-uk.vercel.app",
]
# Allow additional origins via env var (comma-separated) - use for Vercel preview URLs
_extra_origins = os.environ.get('CORS_ALLOWED_ORIGINS', '')
if _extra_origins:
    _allowed_origins.extend([o.strip() for o in _extra_origins.split(',') if o.strip()])
CORS(app, resources={
    r"/analyze":                         {"origins": _allowed_origins},
    r"/ai-analyze":                      {"origins": _allowed_origins},
    r"/extract-url":                     {"origins": _allowed_origins},
    r"/epc-lookup":                      {"origins": _allowed_origins},
    r"/download-pdf":                    {"origins": _allowed_origins},
    r"/api/*":                           {"origins": _allowed_origins},
})

# Security: Rate limiting to prevent abuse
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Security: Add hardening headers to every response
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

# ── Jina Reader API (URL-to-markdown scraping) ───────────────────────────────
JINA_API_KEY = os.environ.get('JINA_API_KEY', '')

# ── Firecrawl API (URL-to-markdown, runs in parallel with Jina) ──────────────
FIRECRAWL_API_KEY = os.environ.get('FIRECRAWL_API_KEY', '')

# ── ScrapingBee (legacy, no longer used) ─────────────────────────────────────
SCRAPINGBEE_API_KEY = os.environ.get('SCRAPINGBEE_API_KEY', '')

# ── Ideal Postcodes (address → postcode lookup) ─────────────────────────────
IDEAL_POSTCODES_API_KEY = os.environ.get('IDEAL_POSTCODES_API_KEY', '')

# ── EPC Open Data API (floor area lookup) ────────────────────────────────────
EPC_API_EMAIL = os.environ.get('EPC_API_EMAIL', '')
EPC_API_KEY   = os.environ.get('EPC_API_KEY', '')

# ── Supabase (optional) ────────────────────────────────────────────────────
_SUPABASE_URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
_SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', '') or os.environ.get('SUPABASE_ANON_KEY', '')

def _sb_headers():
    return {
        'apikey': _SUPABASE_KEY,
        'Authorization': f'Bearer {_SUPABASE_KEY}',
        'Content-Type': 'application/json',
    }

def supabase_upsert_subscription(row: dict):
    """Write/update a subscription row in Supabase. Silently ignores errors if not configured."""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return
    try:
        requests.post(
            f'{_SUPABASE_URL}/rest/v1/subscriptions',
            json=row,
            headers={**_sb_headers(), 'Prefer': 'resolution=merge-duplicates,return=minimal'},
            timeout=6,
        )
    except Exception as e:
        app.logger.warning(f'[Supabase] upsert failed: {e}')

def check_subscription(email: str) -> bool:
    """Return True if email has an active subscription. Open-access when Supabase not configured."""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return True
    if not email:
        return False
    try:
        resp = requests.get(
            f'{_SUPABASE_URL}/rest/v1/subscriptions',
            params={'email': f'eq.{email}', 'status': f'eq.active', 'select': 'id'},
            headers=_sb_headers(),
            timeout=5,
        )
        return resp.status_code == 200 and len(resp.json()) > 0
    except Exception as e:
        app.logger.warning(f'[Supabase] subscription check failed: {e}')
        return True  # Fail open — don't block users on infra error

# ── Stripe HMAC verification ───────────────────────────────────────────────
def verify_stripe_signature(raw_body: bytes, signature_header: str, secret: str) -> bool:
    """
    Verify Stripe webhook signature.
    Header format: t=TIMESTAMP,v1=HMAC_SHA256_HEX,...
    Signed string:  {timestamp}.{raw_body}
    """
    if not signature_header or not secret:
        return False
    try:
        parts: dict[str, list] = {}
        for item in signature_header.split(','):
            key, _, value = item.partition('=')
            parts.setdefault(key.strip(), []).append(value.strip())
        ts         = parts.get('t', [''])[0]
        signatures = parts.get('v1', [])
        if not ts or not signatures:
            return False
        signed   = f'{ts}.{raw_body.decode("utf-8")}'
        expected = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
        return any(hmac.compare_digest(expected, sig) for sig in signatures)
    except Exception:
        return False

# PDF Generation Configuration
PDF_CONFIG = {
    'page-size': 'A4',
    'margin-top': '0.5in',
    'margin-right': '0.5in',
    'margin-bottom': '0.5in',
    'margin-left': '0.5in',
    'encoding': 'UTF-8',
    'enable-local-file-access': None
}

def calculate_stamp_duty(price, second_property=True, first_time_buyer=False):
    """
    Calculate UK stamp duty for England & NI
    Updated for 2024/2025 rates including 5% surcharge for additional properties
    """
    if first_time_buyer:
        # First-time buyer relief (England/NI, 2024/2025)
        # 0% up to £425,000; 5% on £425,001–£625,000; standard rates above £625k
        if price <= 425000:
            return 0
        elif price <= 625000:
            return (price - 425000) * 0.05
        else:
            # No FTB relief above £625k — standard rates apply
            if price <= 125000:
                return 0
            elif price <= 250000:
                return (price - 125000) * 0.02
            elif price <= 925000:
                return 2500 + ((price - 250000) * 0.05)
            elif price <= 1500000:
                return 36250 + ((price - 925000) * 0.10)
            else:
                return 93750 + ((price - 1500000) * 0.12)
    elif not second_property:
        # Standard residential rates (England, effective from Oct 2022)
        if price <= 125000:
            return 0
        elif price <= 250000:
            return (price - 125000) * 0.02
        elif price <= 925000:
            return 2500 + ((price - 250000) * 0.05)
        elif price <= 1500000:
            return 36250 + ((price - 925000) * 0.10)
        else:
            return 93750 + ((price - 1500000) * 0.12)
    else:
        # Additional property rates (5% surcharge on entire amount)
        # Updated 2024 rates for second homes/BTL
        if price <= 250000:
            return price * 0.05  # 5% on everything up to 250k
        elif price <= 925000:
            return (250000 * 0.05) + ((price - 250000) * 0.10)
        elif price <= 1500000:
            return (250000 * 0.05) + (675000 * 0.10) + ((price - 925000) * 0.15)
        else:
            return (250000 * 0.05) + (675000 * 0.10) + (575000 * 0.15) + ((price - 1500000) * 0.17)

def calculate_deal_score(deal_type, gross_yield, net_yield, monthly_cashflow, cash_on_cash, risk_level, brr_metrics=None, flip_metrics=None):
    """
    Calculate AI-powered deal score (0-100)
    Based on multiple factors weighted by deal type
    
    Scoring rubric:
    90-100: Excellent deal (exceeds all benchmarks)
    75-89:  Good deal (meets most benchmarks)
    60-74:  Decent deal (acceptable but not great)
    40-59:  Mediocre deal (borderline)
    20-39:  Poor deal (below benchmarks)
    0-19:   Bad deal (avoid)
    """
    score = 0
    
    # Yield scoring (30 points max) - Most important metric
    if deal_type == 'HMO':
        if gross_yield >= 12:
            score += 30
        elif gross_yield >= 10:
            score += 24
        elif gross_yield >= 8:
            score += 18
        elif gross_yield >= 6:
            score += 10
        elif gross_yield >= 4:
            score += 5
        else:
            score -= 10
    else:
        # BTL scoring - higher threshold
        if gross_yield >= 8:
            score += 30
        elif gross_yield >= 7:
            score += 24
        elif gross_yield >= 6:
            score += 18
        elif gross_yield >= 5:
            score += 10
        elif gross_yield >= 4:
            score += 5
        else:
            score -= 10
    
    # Cashflow scoring (25 points max)
    if monthly_cashflow >= 400:
        score += 25
    elif monthly_cashflow >= 300:
        score += 20
    elif monthly_cashflow >= 200:
        score += 15
    elif monthly_cashflow >= 100:
        score += 8
    elif monthly_cashflow >= 0:
        score += 2
    else:
        score -= 15
    
    # Cash-on-cash scoring (25 points max)
    if cash_on_cash >= 12:
        score += 25
    elif cash_on_cash >= 10:
        score += 20
    elif cash_on_cash >= 8:
        score += 15
    elif cash_on_cash >= 6:
        score += 10
    elif cash_on_cash >= 4:
        score += 5
    else:
        score -= 10
    
    # Strategy-specific scoring (15 points max) - Net yield/ROI
    if deal_type == 'BRR' and brr_metrics:
        brr_roi = brr_metrics.get('brr_roi', 0)
        if brr_roi >= 30:
            score += 15
        elif brr_roi >= 25:
            score += 12
        elif brr_roi >= 20:
            score += 8
        elif brr_roi >= 15:
            score += 4
    elif deal_type == 'FLIP' and flip_metrics:
        flip_roi = flip_metrics.get('flip_roi', 0)
        if flip_roi >= 25:
            score += 15
        elif flip_roi >= 20:
            score += 12
        elif flip_roi >= 15:
            score += 8
        elif flip_roi >= 10:
            score += 4
    else:
        # BTL/HMO - Net yield (after all expenses)
        if net_yield >= 5:
            score += 15
        elif net_yield >= 4:
            score += 10
        elif net_yield >= 3:
            score += 5
        elif net_yield >= 2:
            score += 2
        else:
            score -= 5
    
    # Risk adjustment (5 points max)
    if risk_level == 'LOW':
        score += 5
    elif risk_level == 'MEDIUM':
        score += 0
    else:
        score -= 10
    
    # Ensure score is within 0-100
    return max(0, min(100, score))

def generate_5_year_projection(annual_rent, net_annual_income, purchase_price, cash_invested, interest_rate, capital_growth_pct=4.0):
    """
    Generate 5-year cash flow and equity projection.
    capital_growth_pct: annual property appreciation (user-supplied or default 4%).
    """
    projections = []
    cumulative_cashflow = 0

    rent_growth_rate   = 0.03  # 3% annual rent increase (fixed assumption)
    capital_growth_rate = max(0.0, min(float(capital_growth_pct), 30.0)) / 100  # clamp 0-30%

    current_rent = annual_rent
    current_property_value = purchase_price

    for year in range(1, 6):
        # Apply growth rates
        current_rent = current_rent * (1 + rent_growth_rate)
        current_property_value = current_property_value * (1 + capital_growth_rate)
        
        # Calculate annual figures (expenses grow with rent)
        annual_net = current_rent * (net_annual_income / annual_rent) if annual_rent > 0 else 0
        cumulative_cashflow += annual_net
        
        # Equity = Property value - loan (assuming 75% LTV maintained)
        loan_balance = purchase_price * 0.75  # Simplified - assumes interest only
        equity = current_property_value - loan_balance
        total_return = cumulative_cashflow + equity - (purchase_price * 0.25)  # Less initial deposit
        
        projections.append({
            'year': year,
            'annual_rent': round(current_rent, 0),
            'annual_net': round(annual_net, 0),
            'cumulative_cashflow': round(cumulative_cashflow, 0),
            'property_value': round(current_property_value, 0),
            'equity': round(equity, 0),
            'total_return': round(total_return, 0)
        })
    
    return projections

def get_score_label(score):
    """Get label for deal score based on new rubric"""
    if score >= 90:
        return "Excellent"
    elif score >= 75:
        return "Good"
    elif score >= 60:
        return "Decent"
    elif score >= 40:
        return "Mediocre"
    elif score >= 20:
        return "Poor"
    else:
        return "Bad Deal"


def get_strategy_recommendations(deal_type, gross_yield, cash_on_cash, monthly_cashflow, postcode, article_4_area=False):
    """
    Get strategy recommendations based on deal metrics and area
    
    Returns dict with suitability scores and recommendations
    """
    recommendations = {
        'BTL': {'suitable': True, 'score': 0, 'note': ''},
        'HMO': {'suitable': False, 'score': 0, 'note': ''},
        'BRR': {'suitable': False, 'score': 0, 'note': ''},
        'FLIP': {'suitable': False, 'score': 0, 'note': ''},
        'SOCIAL_HOUSING': {'suitable': False, 'score': 0, 'note': ''}
    }
    
    # Base BTL score
    if gross_yield >= 6 and monthly_cashflow >= 200:
        recommendations['BTL']['score'] = 80
        recommendations['BTL']['note'] = 'Strong buy-to-let candidate'
    elif gross_yield >= 5 and monthly_cashflow >= 100:
        recommendations['BTL']['score'] = 60
        recommendations['BTL']['note'] = 'Acceptable BTL with decent cashflow'
    else:
        recommendations['BTL']['score'] = 40
        recommendations['BTL']['note'] = 'Marginal BTL - consider better areas'
    
    # HMO suitability
    if not article_4_area:
        if gross_yield >= 10 and monthly_cashflow >= 300:
            recommendations['HMO']['suitable'] = True
            recommendations['HMO']['score'] = 85
            recommendations['HMO']['note'] = 'Excellent HMO potential - high yield area'
        elif gross_yield >= 8:
            recommendations['HMO']['suitable'] = True
            recommendations['HMO']['score'] = 70
            recommendations['HMO']['note'] = 'Good for HMO - consider room layout'
        elif gross_yield >= 6:
            recommendations['HMO']['suitable'] = True
            recommendations['HMO']['score'] = 55
            recommendations['HMO']['note'] = 'Possible HMO - check local demand'
        else:
            recommendations['HMO']['note'] = 'Not suitable for HMO - yields too low'
    else:
        recommendations['HMO']['note'] = '⚠️ ARTICLE 4: HMO requires planning permission'
    
    # BRR suitability
    if cash_on_cash >= 8 and gross_yield >= 5:
        recommendations['BRR']['suitable'] = True
        recommendations['BRR']['score'] = 75
        recommendations['BRR']['note'] = 'Good BRR candidate - recycle capital potential'
    elif cash_on_cash >= 5:
        recommendations['BRR']['suitable'] = True
        recommendations['BRR']['score'] = 60
        recommendations['BRR']['note'] = 'Possible BRR with value-add opportunity'
    else:
        recommendations['BRR']['note'] = 'Poor BRR - low cash-on-cash return'
    
    # Flip suitability
    if cash_on_cash >= 15 and gross_yield < 6:
        recommendations['FLIP']['suitable'] = True
        recommendations['FLIP']['score'] = 70
        recommendations['FLIP']['note'] = 'Consider flip if below market value'
    else:
        recommendations['FLIP']['note'] = 'Not ideal for flipping - rental is better'
    
    # Social Housing (C3-C3b conversion)
    if article_4_area:
        recommendations['SOCIAL_HOUSING']['suitable'] = True
        recommendations['SOCIAL_HOUSING']['score'] = 65
        recommendations['SOCIAL_HOUSING']['note'] = 'Article 4 area - consider C3 to C3b (social housing) conversion'
    
    return recommendations


def check_article_4(postcode):
    """
    Check if area is under Article 4 direction for HMO conversions (C3→C4).

    Uses Claude AI as the primary source to research Article 4 status for any postcode.
    Falls back to the built-in UK-wide database when AI is unavailable.
    Returns dict with article_4 status and details.
    """
    postcode_clean = postcode.strip().upper()
    area_code = postcode_clean.split()[0] if ' ' in postcode_clean else postcode_clean

    # ------------------------------------------------------------------ #
    # AI-powered Article 4 research (primary source)                      #
    # Claude researches current planning policy for the given postcode.   #
    # ------------------------------------------------------------------ #
    api_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            model_id = os.environ.get('ANTHROPIC_MODEL', 'claude-haiku-4-5-20251001')
            prompt = (
                f'You are a UK property and planning expert. Determine the Article 4 Direction status '
                f'for HMO (House in Multiple Occupation C3\u2192C4) conversions at UK postcode: {postcode_clean}\n\n'
                'Article 4 Directions remove permitted development rights and require full planning permission '
                'for C3\u2192C4 HMO conversions. Many UK councils have introduced these, especially in '
                'high-density rental or student areas.\n\n'
                'Based on your knowledge of UK local authority planning policy, return ONLY valid JSON:\n'
                '{\n'
                '  "is_article_4": true or false,\n'
                '  "known": true if you are reasonably confident, false if uncertain,\n'
                '  "council": "Full official council name",\n'
                '  "note": "Brief factual note about Article 4 status for this postcode area",\n'
                '  "advice": "One sentence of planning advice for an investor considering HMO here"\n'
                '}'
            )
            message = client.messages.create(
                model=model_id,
                max_tokens=300,
                messages=[{'role': 'user', 'content': prompt}]
            )
            raw = message.content[0].text.strip()
            if raw.startswith('```'):
                raw = re.sub(r'^```[a-z]*\n?', '', raw)
                raw = re.sub(r'\n?```$', '', raw)
            ai_data = json.loads(raw)
            return {
                'is_article_4': bool(ai_data.get('is_article_4', False)),
                'known': bool(ai_data.get('known', True)),
                'council': ai_data.get('council', 'Local Council'),
                'note': ai_data.get('note', ''),
                'area_code': area_code,
                'advice': ai_data.get('advice', ''),
                'source': 'ai'
            }
        except Exception as e:
            app.logger.error(f'[AI] Article 4 check error for {postcode}: {e}')

    # ------------------------------------------------------------------ #
    # Fallback: UK-WIDE Article 4 Direction Database                      #
    # Sources: Council planning portals, gov.uk planning records          #
    # Last updated: 2025. Always verify with local council for changes.   #
    # ------------------------------------------------------------------ #
    article_4_areas = {

        # ── GREATER MANCHESTER ──────────────────────────────────────────
        'M1':  {'active': True,  'council': 'Manchester City Council',  'note': 'City centre - Article 4 HMO restrictions in force'},
        'M2':  {'active': True,  'council': 'Manchester City Council',  'note': 'City centre - Article 4 HMO restrictions in force'},
        'M3':  {'active': True,  'council': 'Manchester City Council',  'note': 'Castlefield/Deansgate - Article 4 in force'},
        'M4':  {'active': True,  'council': 'Manchester City Council',  'note': 'Northern Quarter - Article 4 in force'},
        'M5':  {'active': True,  'council': 'Salford City Council',     'note': 'Ordsall/Salford - Article 4 in force'},
        'M6':  {'active': True,  'council': 'Salford City Council',     'note': 'Salford central - Article 4 in force'},
        'M7':  {'active': False, 'council': 'Salford City Council',     'note': 'No Article 4 currently'},
        'M13': {'active': True,  'council': 'Manchester City Council',  'note': 'Chorlton-on-Medlock/Victoria Park - Article 4 in force'},
        'M14': {'active': True,  'council': 'Manchester City Council',  'note': 'Fallowfield/Moss Side/Rusholme - Article 4 in force'},
        'M15': {'active': True,  'council': 'Manchester City Council',  'note': 'Hulme/Moss Side - Article 4 in force'},
        'M16': {'active': False, 'council': 'Trafford Council',         'note': 'Whalley Range/Firswood - No Article 4'},
        'M19': {'active': True,  'council': 'Manchester City Council',  'note': 'Levenshulme/Burnage - Article 4 in force'},
        'M20': {'active': True,  'council': 'Manchester City Council',  'note': 'Didsbury/Withington - Article 4 in force'},
        'M21': {'active': True,  'council': 'Manchester City Council',  'note': 'Chorlton-cum-Hardy - Article 4 in force'},
        'M24': {'active': False, 'council': 'Rochdale Council',         'note': 'Middleton - No Article 4 currently'},
        'M25': {'active': False, 'council': 'Bury Council',             'note': 'Prestwich - No Article 4 currently'},
        'M26': {'active': False, 'council': 'Bury Council',             'note': 'No Article 4 currently'},
        'M32': {'active': False, 'council': 'Trafford Council',         'note': 'No Article 4 currently'},
        'M33': {'active': False, 'council': 'Trafford Council',         'note': 'Sale - No Article 4 currently'},
        'M35': {'active': False, 'council': 'Oldham Council',           'note': 'No Article 4 currently'},
        'M43': {'active': False, 'council': 'Tameside Council',         'note': 'No Article 4 currently'},
        'M45': {'active': False, 'council': 'Bury Council',             'note': 'Whitefield - No Article 4 currently'},
        'SK1': {'active': False, 'council': 'Stockport Council',        'note': 'No Article 4 currently'},
        'SK2': {'active': False, 'council': 'Stockport Council',        'note': 'No Article 4 currently'},
        'SK3': {'active': False, 'council': 'Stockport Council',        'note': 'No Article 4 currently'},
        'SK4': {'active': False, 'council': 'Stockport Council',        'note': 'No Article 4 currently'},
        'SK5': {'active': False, 'council': 'Stockport Council',        'note': 'No Article 4 currently'},
        'SK6': {'active': False, 'council': 'Stockport Council',        'note': 'No Article 4 currently'},
        'SK7': {'active': False, 'council': 'Stockport Council',        'note': 'No Article 4 currently'},
        'SK8': {'active': True,  'council': 'Stockport Council',        'note': 'Cheadle/Gatley - selective licensing and Article 4 areas'},

        # ── NOTTINGHAM (extensive city-wide Article 4) ──────────────────
        'NG1': {'active': True,  'council': 'Nottingham City Council',  'note': 'City Centre - Article 4 in force across most of the city'},
        'NG2': {'active': True,  'council': 'Nottingham City Council',  'note': 'West Bridgford/Meadows - Article 4 in force'},
        'NG3': {'active': True,  'council': 'Nottingham City Council',  'note': 'Sneinton/St Ann\'s - Article 4 in force'},
        'NG5': {'active': True,  'council': 'Nottingham City Council',  'note': 'Sherwood/Carrington - Article 4 in force'},
        'NG6': {'active': True,  'council': 'Nottingham City Council',  'note': 'Basford/Bulwell - Article 4 in force'},
        'NG7': {'active': True,  'council': 'Nottingham City Council',  'note': 'Lenton/Dunkirk/Radford - Article 4 HMO restrictions (student area)'},
        'NG8': {'active': True,  'council': 'Nottingham City Council',  'note': 'Wollaton/Bilborough - Article 4 in force'},
        'NG9': {'active': True,  'council': 'Broxtowe Borough Council', 'note': 'Beeston - Article 4 in force (student area)'},
        'NG10': {'active': True, 'council': 'Erewash Borough Council',  'note': 'Long Eaton - Article 4 in force'},
        'NG11': {'active': True, 'council': 'Nottingham City Council',  'note': 'Clifton/Ruddington - Article 4 in force'},

        # ── OXFORD (extensive city-wide Article 4) ──────────────────────
        'OX1': {'active': True,  'council': 'Oxford City Council',      'note': 'City Centre/Cowley Road - Article 4 HMO restrictions across most of Oxford'},
        'OX2': {'active': True,  'council': 'Oxford City Council',      'note': 'Headington/Wolvercote - Article 4 in force'},
        'OX3': {'active': True,  'council': 'Oxford City Council',      'note': 'Marston/Barton - Article 4 in force'},
        'OX4': {'active': True,  'council': 'Oxford City Council',      'note': 'Littlemore/Blackbird Leys - Article 4 in force'},

        # ── LEEDS ────────────────────────────────────────────────────────
        'LS2': {'active': True,  'council': 'Leeds City Council',       'note': 'Burley/Hyde Park - Article 4 HMO restrictions (student area)'},
        'LS3': {'active': True,  'council': 'Leeds City Council',       'note': 'Burley/Hyde Park - Article 4 HMO restrictions (student area)'},
        'LS4': {'active': True,  'council': 'Leeds City Council',       'note': 'Kirkstall/Burley - Article 4 in force'},
        'LS5': {'active': True,  'council': 'Leeds City Council',       'note': 'Kirkstall - Article 4 in force'},
        'LS6': {'active': True,  'council': 'Leeds City Council',       'note': 'Headingley/Hyde Park - Article 4 HMO restrictions (student area)'},
        'LS7': {'active': True,  'council': 'Leeds City Council',       'note': 'Chapel Allerton/Scott Hall - Article 4 in force'},
        'LS8': {'active': False, 'council': 'Leeds City Council',       'note': 'Roundhay/Harehills - No Article 4 currently'},

        # ── SHEFFIELD ────────────────────────────────────────────────────
        'S1':  {'active': True,  'council': 'Sheffield City Council',   'note': 'City Centre - Article 4 HMO restrictions in force'},
        'S2':  {'active': True,  'council': 'Sheffield City Council',   'note': 'Heeley/Manor - Article 4 in force'},
        'S3':  {'active': True,  'council': 'Sheffield City Council',   'note': 'Burngreave/Walkley - Article 4 in force'},
        'S10': {'active': True,  'council': 'Sheffield City Council',   'note': 'Broomhill/Crookes - Article 4 HMO restrictions (student area)'},
        'S11': {'active': True,  'council': 'Sheffield City Council',   'note': 'Ecclesall/Nether Edge - Article 4 in force'},

        # ── BRISTOL ──────────────────────────────────────────────────────
        'BS1': {'active': True,  'council': 'Bristol City Council',     'note': 'City Centre/Clifton - Article 4 HMO restrictions in force'},
        'BS2': {'active': True,  'council': 'Bristol City Council',     'note': 'St Pauls/Easton - Article 4 in force'},
        'BS3': {'active': True,  'council': 'Bristol City Council',     'note': 'Bedminster/Southville - Article 4 in force'},
        'BS5': {'active': True,  'council': 'Bristol City Council',     'note': 'Easton/St George - Article 4 in force'},
        'BS6': {'active': True,  'council': 'Bristol City Council',     'note': 'Redland/Cotham - Article 4 HMO restrictions'},
        'BS7': {'active': True,  'council': 'Bristol City Council',     'note': 'Horfield/Bishopston - Article 4 in force'},
        'BS8': {'active': True,  'council': 'Bristol City Council',     'note': 'Clifton/Hotwells - Article 4 HMO restrictions'},

        # ── BIRMINGHAM ───────────────────────────────────────────────────
        'B5':  {'active': True,  'council': 'Birmingham City Council',  'note': 'Digbeth/Highgate - Article 4 HMO restrictions'},
        'B11': {'active': True,  'council': 'Birmingham City Council',  'note': 'Sparkhill/Tyseley - Article 4 in force'},
        'B12': {'active': True,  'council': 'Birmingham City Council',  'note': 'Balsall Heath/Sparkbrook - Article 4 in force'},
        'B15': {'active': True,  'council': 'Birmingham City Council',  'note': 'Edgbaston - Article 4 HMO restrictions (student/professional area)'},
        'B16': {'active': True,  'council': 'Birmingham City Council',  'note': 'Ladywood/Edgbaston - Article 4 in force'},
        'B17': {'active': True,  'council': 'Birmingham City Council',  'note': 'Harborne - Article 4 in force'},
        'B29': {'active': True,  'council': 'Birmingham City Council',  'note': 'Selly Oak/Bournbrook - Article 4 HMO restrictions (heavy student area)'},
        'B30': {'active': True,  'council': 'Birmingham City Council',  'note': 'Bournville/Stirchley - Article 4 in force'},

        # ── SOUTHAMPTON ──────────────────────────────────────────────────
        'SO14': {'active': True, 'council': 'Southampton City Council', 'note': 'City Centre/St Mary\'s - Article 4 HMO restrictions'},
        'SO15': {'active': True, 'council': 'Southampton City Council', 'note': 'Freemantle/Shirley - Article 4 in force'},
        'SO16': {'active': True, 'council': 'Southampton City Council', 'note': 'Bassett/Rownhams - Article 4 in force'},
        'SO17': {'active': True, 'council': 'Southampton City Council', 'note': 'Portswood/Highfield - Article 4 HMO restrictions (university area)'},

        # ── PORTSMOUTH ───────────────────────────────────────────────────
        'PO1': {'active': True,  'council': 'Portsmouth City Council',  'note': 'City Centre/Portsea - Article 4 HMO restrictions in force'},
        'PO2': {'active': True,  'council': 'Portsmouth City Council',  'note': 'Cosham/Hilsea - Article 4 in force'},
        'PO3': {'active': True,  'council': 'Portsmouth City Council',  'note': 'Copnor/Buckland - Article 4 in force'},
        'PO4': {'active': True,  'council': 'Portsmouth City Council',  'note': 'Southsea/Eastney - Article 4 HMO restrictions'},
        'PO5': {'active': True,  'council': 'Portsmouth City Council',  'note': 'Southsea - Article 4 in force'},
        'PO6': {'active': True,  'council': 'Portsmouth City Council',  'note': 'Cosham - Article 4 in force'},

        # ── LIVERPOOL ────────────────────────────────────────────────────
        'L1':  {'active': True,  'council': 'Liverpool City Council',   'note': 'City Centre - Article 4 HMO restrictions'},
        'L6':  {'active': True,  'council': 'Liverpool City Council',   'note': 'Everton/Kensington - Article 4 in force'},
        'L7':  {'active': True,  'council': 'Liverpool City Council',   'note': 'Edge Hill/Fairfield - Article 4 HMO restrictions'},
        'L8':  {'active': True,  'council': 'Liverpool City Council',   'note': 'Dingle/Toxteth - Article 4 in force'},
        'L15': {'active': True,  'council': 'Liverpool City Council',   'note': 'Wavertree/Picton - Article 4 HMO restrictions'},
        'L17': {'active': True,  'council': 'Liverpool City Council',   'note': 'Aigburth/Garston - Article 4 in force'},
        'L18': {'active': False, 'council': 'Liverpool City Council',   'note': 'Allerton/Mossley Hill - No Article 4 currently'},

        # ── NEWCASTLE UPON TYNE ──────────────────────────────────────────
        'NE1': {'active': True,  'council': 'Newcastle City Council',   'note': 'City Centre - Article 4 HMO restrictions in force'},
        'NE2': {'active': True,  'council': 'Newcastle City Council',   'note': 'Jesmond - Article 4 HMO restrictions (professional/student area)'},
        'NE4': {'active': True,  'council': 'Newcastle City Council',   'note': 'Fenham/Benwell - Article 4 in force'},
        'NE6': {'active': True,  'council': 'Newcastle City Council',   'note': 'Walker/Byker - Article 4 in force'},

        # ── BRIGHTON & HOVE ──────────────────────────────────────────────
        'BN1': {'active': True,  'council': 'Brighton & Hove City Council', 'note': 'City Centre/Kemptown - Article 4 HMO restrictions in force'},
        'BN2': {'active': True,  'council': 'Brighton & Hove City Council', 'note': 'Brighton/Rottingdean - Article 4 in force'},
        'BN3': {'active': True,  'council': 'Brighton & Hove City Council', 'note': 'Hove - Article 4 in force'},

        # ── COVENTRY ─────────────────────────────────────────────────────
        'CV1': {'active': True,  'council': 'Coventry City Council',    'note': 'City Centre - Article 4 HMO restrictions in force'},
        'CV2': {'active': True,  'council': 'Coventry City Council',    'note': 'Stoke/Wyken - Article 4 in force'},
        'CV5': {'active': True,  'council': 'Coventry City Council',    'note': 'Earlsdon/Canley - Article 4 in force (student area)'},
        'CV6': {'active': True,  'council': 'Coventry City Council',    'note': 'Radford/Holbrooks - Article 4 in force'},

        # ── LEICESTER ────────────────────────────────────────────────────
        'LE1': {'active': True,  'council': 'Leicester City Council',   'note': 'City Centre - Article 4 HMO restrictions in force'},
        'LE2': {'active': True,  'council': 'Leicester City Council',   'note': 'Aylestone/Knighton - Article 4 in force'},
        'LE3': {'active': True,  'council': 'Leicester City Council',   'note': 'Braunstone/Western Park - Article 4 in force'},
        'LE4': {'active': True,  'council': 'Leicester City Council',   'note': 'Belgrave/Beaumont Leys - Article 4 in force'},
        'LE5': {'active': True,  'council': 'Leicester City Council',   'note': 'Evington/Humberstone - Article 4 in force'},

        # ── CAMBRIDGE ────────────────────────────────────────────────────
        'CB1': {'active': True,  'council': 'Cambridge City Council',   'note': 'City Centre/Mill Road - Article 4 HMO restrictions in force'},
        'CB2': {'active': True,  'council': 'Cambridge City Council',   'note': 'Central Cambridge - Article 4 in force'},
        'CB3': {'active': True,  'council': 'Cambridge City Council',   'note': 'Newnham/Grantchester - Article 4 in force'},
        'CB4': {'active': True,  'council': 'Cambridge City Council',   'note': 'Chesterton/King\'s Hedges - Article 4 in force'},

        # ── YORK ─────────────────────────────────────────────────────────
        'YO1':  {'active': True, 'council': 'City of York Council',     'note': 'City Centre - Article 4 HMO restrictions in force'},
        'YO10': {'active': True, 'council': 'City of York Council',     'note': 'Fishergate/Fulford - Article 4 in force (student area)'},
        'YO24': {'active': True, 'council': 'City of York Council',     'note': 'Acomb/Dringhouses - Article 4 in force'},
        'YO30': {'active': True, 'council': 'City of York Council',     'note': 'Skelton/Rawcliffe - Article 4 in force'},
        'YO31': {'active': True, 'council': 'City of York Council',     'note': 'Heworth/Huntington - Article 4 in force'},

        # ── DERBY ────────────────────────────────────────────────────────
        'DE1':  {'active': True, 'council': 'Derby City Council',       'note': 'City Centre - Article 4 HMO restrictions in force'},
        'DE21': {'active': True, 'council': 'Derby City Council',       'note': 'Chaddesden/Oakwood - Article 4 in force'},
        'DE22': {'active': True, 'council': 'Derby City Council',       'note': 'Allestree/Darley Abbey - Article 4 in force'},
        'DE23': {'active': True, 'council': 'Derby City Council',       'note': 'Normanton/Sunny Hill - Article 4 in force'},

        # ── WOLVERHAMPTON ────────────────────────────────────────────────
        'WV1': {'active': True,  'council': 'City of Wolverhampton',    'note': 'City Centre - Article 4 HMO restrictions in force'},
        'WV2': {'active': True,  'council': 'City of Wolverhampton',    'note': 'Parkfields/Heath Town - Article 4 in force'},
        'WV3': {'active': True,  'council': 'City of Wolverhampton',    'note': 'Tettenhall/Newbridge - Article 4 in force'},

        # ── HULL ─────────────────────────────────────────────────────────
        'HU1': {'active': True,  'council': 'Kingston upon Hull Council', 'note': 'City Centre - Article 4 HMO restrictions in force'},
        'HU3': {'active': True,  'council': 'Kingston upon Hull Council', 'note': 'Hessle Road/Anlaby - Article 4 in force'},
        'HU5': {'active': True,  'council': 'Kingston upon Hull Council', 'note': 'Newland/Beverley Road - Article 4 in force (student area)'},

        # ── EXETER ───────────────────────────────────────────────────────
        'EX1': {'active': True,  'council': 'Exeter City Council',      'note': 'City Centre - Article 4 HMO restrictions in force'},
        'EX2': {'active': True,  'council': 'Exeter City Council',      'note': 'Heavitree/St Thomas - Article 4 in force'},
        'EX4': {'active': True,  'council': 'Exeter City Council',      'note': 'Pennsylvania/St David\'s - Article 4 in force (student area)'},

        # ── PLYMOUTH ─────────────────────────────────────────────────────
        'PL1': {'active': True,  'council': 'Plymouth City Council',    'note': 'City Centre/Stonehouse - Article 4 HMO restrictions in force'},
        'PL4': {'active': True,  'council': 'Plymouth City Council',    'note': 'Lipson/Prince Rock - Article 4 in force'},

        # ── BOURNEMOUTH ──────────────────────────────────────────────────
        'BH1': {'active': True,  'council': 'Bournemouth, Christchurch & Poole Council', 'note': 'Town Centre - Article 4 HMO restrictions in force'},
        'BH5': {'active': True,  'council': 'Bournemouth, Christchurch & Poole Council', 'note': 'Boscombe - Article 4 in force'},
        'BH8': {'active': True,  'council': 'Bournemouth, Christchurch & Poole Council', 'note': 'Charminster - Article 4 in force'},

        # ── READING ──────────────────────────────────────────────────────
        'RG1': {'active': True,  'council': 'Reading Borough Council',  'note': 'Town Centre - Article 4 HMO restrictions in force'},
        'RG2': {'active': True,  'council': 'Reading Borough Council',  'note': 'Whitley/Coley - Article 4 in force'},

        # ── LUTON ────────────────────────────────────────────────────────
        'LU1': {'active': True,  'council': 'Luton Borough Council',    'note': 'Town Centre - Article 4 HMO restrictions in force'},
        'LU2': {'active': True,  'council': 'Luton Borough Council',    'note': 'Bury Park/Leagrave - Article 4 in force'},
        'LU3': {'active': True,  'council': 'Luton Borough Council',    'note': 'Limbury/Sundon Park - Article 4 in force'},

        # ── SLOUGH ───────────────────────────────────────────────────────
        'SL1': {'active': True,  'council': 'Slough Borough Council',   'note': 'Town Centre - Article 4 HMO restrictions in force'},
        'SL2': {'active': True,  'council': 'Slough Borough Council',   'note': 'Farnham Royal/Slough - Article 4 in force'},

        # ── PETERBOROUGH ─────────────────────────────────────────────────
        'PE1': {'active': True,  'council': 'Peterborough City Council', 'note': 'City Centre - Article 4 HMO restrictions in force'},
        'PE2': {'active': True,  'council': 'Peterborough City Council', 'note': 'Dogsthorpe/Werrington - Article 4 in force'},

        # ── NORWICH ──────────────────────────────────────────────────────
        'NR1': {'active': True,  'council': 'Norwich City Council',     'note': 'City Centre - Article 4 HMO restrictions in force'},
        'NR2': {'active': True,  'council': 'Norwich City Council',     'note': 'Golden Triangle/Eaton - Article 4 in force'},
        'NR3': {'active': True,  'council': 'Norwich City Council',     'note': 'Dereham Road/Hellesdon - Article 4 in force'},

        # ── IPSWICH ──────────────────────────────────────────────────────
        'IP1': {'active': True,  'council': 'Ipswich Borough Council',  'note': 'Town Centre - Article 4 HMO restrictions in force'},
        'IP2': {'active': True,  'council': 'Ipswich Borough Council',  'note': 'Chantry/Belstead - Article 4 in force'},
        'IP4': {'active': True,  'council': 'Ipswich Borough Council',  'note': 'Rushmere/Whitton - Article 4 in force'},

        # ── SUNDERLAND ───────────────────────────────────────────────────
        'SR1': {'active': True,  'council': 'Sunderland City Council',  'note': 'City Centre - Article 4 HMO restrictions in force'},
        'SR2': {'active': True,  'council': 'Sunderland City Council',  'note': 'Hendon/Thornhill - Article 4 in force'},
        'SR4': {'active': True,  'council': 'Sunderland City Council',  'note': 'Millfield/Pallion - Article 4 in force'},

        # ── MIDDLESBROUGH ────────────────────────────────────────────────
        'TS1': {'active': True,  'council': 'Middlesbrough Council',    'note': 'Town Centre - Article 4 HMO restrictions in force'},
        'TS5': {'active': True,  'council': 'Middlesbrough Council',    'note': 'Acklam/Linthorpe - Article 4 in force'},

        # ── CHELTENHAM ───────────────────────────────────────────────────
        'GL50': {'active': True, 'council': 'Cheltenham Borough Council', 'note': 'Town Centre/Montpellier - Article 4 HMO restrictions in force'},
        'GL51': {'active': True, 'council': 'Cheltenham Borough Council', 'note': 'Hesters Way/Up Hatherley - Article 4 in force'},
        'GL52': {'active': True, 'council': 'Cheltenham Borough Council', 'note': 'Prestbury/Pittville - Article 4 in force'},

        # ── GLOUCESTER ───────────────────────────────────────────────────
        'GL1': {'active': True,  'council': 'Gloucester City Council',  'note': 'City Centre - Article 4 HMO restrictions in force'},
        'GL2': {'active': True,  'council': 'Gloucester City Council',  'note': 'Gloucester/Quedgeley - Article 4 in force'},

        # ── STOKE-ON-TRENT ───────────────────────────────────────────────
        'ST1': {'active': True,  'council': 'Stoke-on-Trent City Council', 'note': 'Hanley/Stoke Centre - Article 4 HMO restrictions in force'},
        'ST4': {'active': True,  'council': 'Stoke-on-Trent City Council', 'note': 'Stoke/Fenton - Article 4 in force'},

        # ── BEDFORD ──────────────────────────────────────────────────────
        'MK40': {'active': True, 'council': 'Bedford Borough Council',  'note': 'Bedford Town Centre - Article 4 HMO restrictions in force'},
        'MK41': {'active': True, 'council': 'Bedford Borough Council',  'note': 'Clapham/Goldington - Article 4 in force'},
        'MK42': {'active': True, 'council': 'Bedford Borough Council',  'note': 'Kempston - Article 4 in force'},

        # ── NORTHAMPTON ──────────────────────────────────────────────────
        'NN1': {'active': True,  'council': 'West Northamptonshire Council', 'note': 'Town Centre - Article 4 HMO restrictions in force'},
        'NN4': {'active': True,  'council': 'West Northamptonshire Council', 'note': 'Wootton/Hardingstone - Article 4 in force'},

        # ── WALES (Article 4 applies in Wales too) ───────────────────────
        'CF10': {'active': True, 'council': 'Cardiff Council',          'note': 'Cardiff City Centre - Article 4 HMO restrictions in force'},
        'CF24': {'active': True, 'council': 'Cardiff Council',          'note': 'Roath/Splott - Article 4 HMO restrictions (student area)'},
        'CF14': {'active': True, 'council': 'Cardiff Council',          'note': 'Whitchurch/Heath - Article 4 in force'},
        'SA1': {'active': True,  'council': 'Swansea Council',          'note': 'City Centre/SA1 Marina - Article 4 HMO restrictions in force'},
        'SA2': {'active': True,  'council': 'Swansea Council',          'note': 'Sketty/Uplands - Article 4 in force (student area)'},

        # ── LONDON – BARNET ──────────────────────────────────────────────
        'N2':  {'active': True,  'council': 'London Borough of Barnet', 'note': 'East Finchley - Article 4 HMO restrictions in force'},
        'N3':  {'active': True,  'council': 'London Borough of Barnet', 'note': 'Finchley Central - Article 4 in force'},
        'N12': {'active': True,  'council': 'London Borough of Barnet', 'note': 'North Finchley - Article 4 in force'},
        'NW4': {'active': True,  'council': 'London Borough of Barnet', 'note': 'Brent Cross/Hendon - Article 4 in force'},
        'NW7': {'active': True,  'council': 'London Borough of Barnet', 'note': 'Mill Hill - Article 4 in force'},

        # ── LONDON – BRENT ───────────────────────────────────────────────
        'HA0': {'active': True,  'council': 'London Borough of Brent',  'note': 'Wembley - Article 4 HMO restrictions in force'},
        'HA9': {'active': True,  'council': 'London Borough of Brent',  'note': 'Wembley Central - Article 4 in force'},
        'NW2': {'active': True,  'council': 'London Borough of Brent',  'note': 'Cricklewood - Article 4 in force'},
        'NW10': {'active': True, 'council': 'London Borough of Brent',  'note': 'Harlesden/Willesden - Article 4 HMO restrictions'},

        # ── LONDON – CAMDEN ──────────────────────────────────────────────
        'NW1': {'active': True,  'council': 'London Borough of Camden', 'note': 'Camden Town/Primrose Hill - Article 4 HMO restrictions'},
        'NW3': {'active': True,  'council': 'London Borough of Camden', 'note': 'Hampstead/Swiss Cottage - Article 4 in force'},
        'NW5': {'active': True,  'council': 'London Borough of Camden', 'note': 'Kentish Town/Gospel Oak - Article 4 in force'},
        'NW6': {'active': True,  'council': 'London Borough of Camden', 'note': 'West Hampstead/Kilburn - Article 4 in force'},

        # ── LONDON – EALING ──────────────────────────────────────────────
        'W3':  {'active': True,  'council': 'London Borough of Ealing', 'note': 'Acton - Article 4 HMO restrictions in force'},
        'W5':  {'active': True,  'council': 'London Borough of Ealing', 'note': 'Ealing - Article 4 in force'},
        'W7':  {'active': True,  'council': 'London Borough of Ealing', 'note': 'Hanwell - Article 4 in force'},
        'W13': {'active': True,  'council': 'London Borough of Ealing', 'note': 'West Ealing - Article 4 in force'},

        # ── LONDON – HACKNEY ─────────────────────────────────────────────
        'E2':  {'active': True,  'council': 'London Borough of Hackney','note': 'Bethnal Green/Hackney - Article 4 HMO restrictions'},
        'E5':  {'active': True,  'council': 'London Borough of Hackney','note': 'Clapton - Article 4 in force'},
        'E8':  {'active': True,  'council': 'London Borough of Hackney','note': 'Hackney/London Fields - Article 4 in force'},
        'E9':  {'active': True,  'council': 'London Borough of Hackney','note': 'Hackney Wick/Homerton - Article 4 in force'},
        'N16': {'active': True,  'council': 'London Borough of Hackney','note': 'Stoke Newington - Article 4 in force'},

        # ── LONDON – HARINGEY ────────────────────────────────────────────
        'N4':  {'active': True,  'council': 'London Borough of Haringey', 'note': 'Finsbury Park/Manor House - Article 4 HMO restrictions'},
        'N8':  {'active': True,  'council': 'London Borough of Haringey', 'note': 'Crouch End/Hornsey - Article 4 in force'},
        'N15': {'active': True,  'council': 'London Borough of Haringey', 'note': 'Seven Sisters/South Tottenham - Article 4 in force'},
        'N17': {'active': True,  'council': 'London Borough of Haringey', 'note': 'Tottenham - Article 4 in force'},
        'N22': {'active': True,  'council': 'London Borough of Haringey', 'note': 'Wood Green - Article 4 in force'},

        # ── LONDON – ISLINGTON ───────────────────────────────────────────
        'EC1': {'active': True,  'council': 'London Borough of Islington', 'note': 'Clerkenwell/Barbican - Article 4 HMO restrictions'},
        'N1':  {'active': True,  'council': 'London Borough of Islington', 'note': 'Islington/Angel - Article 4 HMO restrictions'},
        'N7':  {'active': True,  'council': 'London Borough of Islington', 'note': 'Holloway - Article 4 in force'},
        'N19': {'active': True,  'council': 'London Borough of Islington', 'note': 'Upper Holloway - Article 4 in force'},

        # ── LONDON – LAMBETH ─────────────────────────────────────────────
        'SE11': {'active': True, 'council': 'London Borough of Lambeth', 'note': 'Kennington/Vauxhall - Article 4 HMO restrictions'},
        'SE24': {'active': True, 'council': 'London Borough of Lambeth', 'note': 'Herne Hill/Tulse Hill - Article 4 in force'},
        'SW2': {'active': True,  'council': 'London Borough of Lambeth', 'note': 'Brixton Hill/Streatham Hill - Article 4 in force'},
        'SW4': {'active': True,  'council': 'London Borough of Lambeth', 'note': 'Clapham - Article 4 HMO restrictions'},
        'SW9': {'active': True,  'council': 'London Borough of Lambeth', 'note': 'Stockwell/Brixton - Article 4 in force'},

        # ── LONDON – LEWISHAM ────────────────────────────────────────────
        'SE4':  {'active': True, 'council': 'London Borough of Lewisham', 'note': 'Brockley/Crofton Park - Article 4 in force'},
        'SE6':  {'active': True, 'council': 'London Borough of Lewisham', 'note': 'Catford/Bellingham - Article 4 in force'},
        'SE8':  {'active': True, 'council': 'London Borough of Lewisham', 'note': 'Deptford - Article 4 in force'},
        'SE12': {'active': True, 'council': 'London Borough of Lewisham', 'note': 'Lee/Grove Park - Article 4 in force'},
        'SE13': {'active': True, 'council': 'London Borough of Lewisham', 'note': 'Lewisham/Hither Green - Article 4 in force'},
        'SE23': {'active': True, 'council': 'London Borough of Lewisham', 'note': 'Forest Hill - Article 4 in force'},

        # ── LONDON – NEWHAM ──────────────────────────────────────────────
        'E6':  {'active': True,  'council': 'London Borough of Newham', 'note': 'East Ham/Beckton - Article 4 HMO restrictions'},
        'E7':  {'active': True,  'council': 'London Borough of Newham', 'note': 'Forest Gate - Article 4 in force'},
        'E12': {'active': True,  'council': 'London Borough of Newham', 'note': 'Manor Park - Article 4 in force'},
        'E13': {'active': True,  'council': 'London Borough of Newham', 'note': 'Plaistow/West Ham - Article 4 in force'},
        'E15': {'active': True,  'council': 'London Borough of Newham', 'note': 'Stratford - Article 4 in force'},
        'E16': {'active': True,  'council': 'London Borough of Newham', 'note': 'Custom House/Canning Town - Article 4 in force'},

        # ── LONDON – REDBRIDGE ───────────────────────────────────────────
        'IG1': {'active': True,  'council': 'London Borough of Redbridge', 'note': 'Ilford - Article 4 HMO restrictions in force'},
        'IG2': {'active': True,  'council': 'London Borough of Redbridge', 'note': 'Gants Hill/Newbury Park - Article 4 in force'},
        'IG3': {'active': True,  'council': 'London Borough of Redbridge', 'note': 'Seven Kings - Article 4 in force'},
        'IG4': {'active': False, 'council': 'London Borough of Redbridge', 'note': 'Redbridge/Barkingside - No Article 4 currently'},

        # ── LONDON – SOUTHWARK ───────────────────────────────────────────
        'SE1':  {'active': True, 'council': 'London Borough of Southwark', 'note': 'London Bridge/Borough - Article 4 HMO restrictions'},
        'SE5':  {'active': True, 'council': 'London Borough of Southwark', 'note': 'Camberwell/Burgess Park - Article 4 in force'},
        'SE15': {'active': True, 'council': 'London Borough of Southwark', 'note': 'Peckham/Nunhead - Article 4 in force'},
        'SE16': {'active': True, 'council': 'London Borough of Southwark', 'note': 'Bermondsey/Rotherhithe - Article 4 in force'},
        'SE17': {'active': True, 'council': 'London Borough of Southwark', 'note': 'Walworth/Elephant - Article 4 in force'},
        'SE22': {'active': True, 'council': 'London Borough of Southwark', 'note': 'East Dulwich - Article 4 in force'},

        # ── LONDON – TOWER HAMLETS ───────────────────────────────────────
        'E1':  {'active': True,  'council': 'London Borough of Tower Hamlets', 'note': 'Whitechapel/Stepney - Article 4 HMO restrictions'},
        'E3':  {'active': True,  'council': 'London Borough of Tower Hamlets', 'note': 'Bow/Bromley-by-Bow - Article 4 in force'},
        'E14': {'active': True,  'council': 'London Borough of Tower Hamlets', 'note': 'Poplar/Isle of Dogs - Article 4 in force'},

        # ── LONDON – WALTHAM FOREST ──────────────────────────────────────
        'E4':  {'active': True,  'council': 'London Borough of Waltham Forest', 'note': 'Chingford - Article 4 HMO restrictions'},
        'E10': {'active': True,  'council': 'London Borough of Waltham Forest', 'note': 'Leyton - Article 4 in force'},
        'E11': {'active': True,  'council': 'London Borough of Waltham Forest', 'note': 'Leytonstone/Wanstead - Article 4 in force'},
        'E17': {'active': True,  'council': 'London Borough of Waltham Forest', 'note': 'Walthamstow - Article 4 HMO restrictions'},

        # ── LONDON – WANDSWORTH ──────────────────────────────────────────
        'SW11': {'active': True, 'council': 'London Borough of Wandsworth', 'note': 'Battersea/Clapham Junction - Article 4 HMO restrictions'},
        'SW12': {'active': True, 'council': 'London Borough of Wandsworth', 'note': 'Balham - Article 4 in force'},
        'SW15': {'active': True, 'council': 'London Borough of Wandsworth', 'note': 'Putney - Article 4 in force'},
        'SW17': {'active': True, 'council': 'London Borough of Wandsworth', 'note': 'Tooting - Article 4 in force'},
        'SW18': {'active': True, 'council': 'London Borough of Wandsworth', 'note': 'Earlsfield/Wandsworth - Article 4 in force'},
    }

    # ------------------------------------------------------------------ #
    # Extract outward code from postcode (e.g., 'M14' from 'M14 7EH')    #
    # ------------------------------------------------------------------ #
    # (postcode_clean and area_code already set above)

    # Try progressively shorter matches (e.g. SW11 → SW1 → SW)
    # to handle outward codes of different lengths
    for length in [5, 4, 3, 2]:
        candidate = area_code[:length]
        if candidate in article_4_areas:
            info = article_4_areas[candidate]
            return {
                'is_article_4': info['active'],
                'known': True,
                'council': info['council'],
                'note': info['note'],
                'area_code': candidate,
                'advice': (
                    'Planning permission required for C3→C4 (HMO) conversion in this area.'
                    if info['active'] else
                    'No Article 4 restrictions — permitted development applies for C3→C4 HMO conversion.'
                )
            }

    # Area not in database — be transparent, do not assume no Article 4
    return {
        'is_article_4': False,
        'known': False,
        'council': 'Local Council',
        'note': 'This postcode area is not in our Article 4 database — status unconfirmed.',
        'area_code': area_code,
        'advice': (
            'Article 4 status not confirmed for this area. '
            'Verify with the local planning authority before converting to HMO.'
        )
    }


def get_location_from_ai(postcode):
    """
    Use Claude AI + postcodes.io to get accurate location info (country, region, council).
    AI resolves the full official council name and metropolitan area from the postcode.
    Falls back to postcodes.io admin_district + static mapping if AI unavailable.
    """
    admin_district = None
    api_region = None
    try:
        resp = requests.get(
            f'https://api.postcodes.io/postcodes/{postcode.replace(" ", "")}',
            timeout=8
        )
        if resp.status_code == 200:
            geo = resp.json().get('result', {})
            admin_district = geo.get('admin_district', '')
            api_region = geo.get('region', '')
    except Exception:
        pass

    api_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            model_id = os.environ.get('ANTHROPIC_MODEL', 'claude-haiku-4-5-20251001')
            context = f' (postcodes.io admin_district: "{admin_district}")' if admin_district else ''
            prompt = (
                f'Given the UK postcode "{postcode}"{context}, provide the following in JSON:\n'
                '- country: England, Wales, Scotland, or Northern Ireland\n'
                '- region: The metropolitan county or well-known area name (e.g. "Greater Manchester", '
                '"West Yorkshire", "Greater London", "West Midlands", "Merseyside")\n'
                '- council: The full official local authority name '
                '(e.g. "Bury Metropolitan Borough Council", "Leeds City Council", '
                '"London Borough of Hackney")\n\n'
                'Return ONLY valid JSON, no markdown or explanation:\n'
                '{"country": "...", "region": "...", "council": "..."}'
            )
            message = client.messages.create(
                model=model_id,
                max_tokens=150,
                messages=[{'role': 'user', 'content': prompt}]
            )
            raw = message.content[0].text.strip()
            if raw.startswith('```'):
                raw = re.sub(r'^```[a-z]*\n?', '', raw)
                raw = re.sub(r'\n?```$', '', raw)
            loc = json.loads(raw)
            return {
                'country': loc.get('country', 'England'),
                'region': loc.get('region') or get_region_from_postcode(postcode),
                'council': loc.get('council') or admin_district or 'Local Council'
            }
        except Exception as e:
            app.logger.error(f'[AI] Location lookup error for {postcode}: {e}')

    # Fallback: postcodes.io + static region mapping
    return {
        'country': 'England',
        'region': get_region_from_postcode(postcode),
        'council': admin_district or 'Local Council'
    }


def get_refurb_estimate(postcode, property_type, bedrooms, internal_area=1000):
    """
    Get refurbishment cost estimate per square meter

    Based on typical UK refurbishment costs
    """
    # Base costs per sq ft (converted from sq m)
    base_costs = {
        'light': 50,      # £50 per sq m - cosmetic only
        'medium': 100,    # £100 per sq m - new kitchen, bathroom
        'heavy': 180,     # £180 per sq m - full refurb including electrics
        'structural': 250 # £250 per sq m - including structural work
    }
    
    # Property type multipliers
    type_multipliers = {
        'detached': 1.0,
        'semi': 0.9,
        'terraced': 0.85,
        'flat': 0.8,
        'bungalow': 1.1
    }
    
    # Area adjustment (London premium)
    area_adjustment = 1.0
    if postcode.startswith('SW') or postcode.startswith('W') or postcode.startswith('NW'):
        area_adjustment = 1.3  # 30% premium for London
    
    # Default internal area if not provided
    sqm = internal_area
    
    estimates = {}
    for level, base in base_costs.items():
        multiplier = type_multipliers.get(property_type.lower().replace('-detached', '').replace('semi-', 'semi'), 1.0)
        cost_per_sqm = base * multiplier * area_adjustment
        total = cost_per_sqm * sqm
        estimates[level] = {
            'per_sqm': round(cost_per_sqm, 2),
            'total': round(total, 0),
            'label': level.capitalize()
        }
    
    return estimates

def analyze_deal(data):
    """Perform comprehensive deal analysis with input validation"""
    
    # Security: Extract and sanitize inputs
    deal_type = sanitize_input(data.get('dealType', 'BTL'), 20)
    if deal_type not in ['BTL', 'BRR', 'HMO', 'FLIP', 'R2SA']:
        raise ValueError("Invalid deal type")
    
    # Security: Validate numeric inputs
    purchase_price_raw = data.get('purchasePrice', 0)
    if not validate_numeric(purchase_price_raw, 0, 50000000):
        raise ValueError("Invalid purchase price")
    purchase_price = float(purchase_price_raw)
    
    monthly_rent_raw = data.get('monthlyRent', 0)
    if not validate_numeric(monthly_rent_raw, 0, 100000):
        raise ValueError("Invalid monthly rent")
    monthly_rent = float(monthly_rent_raw)
    
    deposit_pct_raw = data.get('deposit', 25)
    if not validate_numeric(deposit_pct_raw, 0, 100):
        raise ValueError("Invalid deposit percentage")
    deposit_pct = float(deposit_pct_raw)
    
    interest_rate_raw = data.get('interestRate', 4.0)
    if not validate_numeric(interest_rate_raw, 0, 20):
        raise ValueError("Invalid interest rate")
    interest_rate = float(interest_rate_raw)
    
    # Security: Sanitize text inputs
    address = sanitize_input(data.get('address', ''), 200)
    postcode = sanitize_input(data.get('postcode', ''), 20)
    bedrooms = int(data.get('bedrooms', 3) or 3)
    
    # Security: Validate postcode format if provided
    if postcode and not validate_postcode(postcode):
        postcode = ""  # Clear invalid postcode rather than error
    
    # Purchase costs
    buyer_type = data.get('buyerType', 'second_home')
    is_first_time = buyer_type == 'first_time'
    stamp_duty = calculate_stamp_duty(purchase_price, second_property=not is_first_time, first_time_buyer=is_first_time)
    legal_fees = float(data.get('legalFees', 1500))
    valuation_fee = float(data.get('valuationFee', 500))
    arrangement_fee = float(data.get('arrangementFee', 1995))
    total_purchase_costs = purchase_price + stamp_duty + legal_fees + valuation_fee + arrangement_fee
    
    # Financing - handle different purchase types
    purchase_type = data.get('purchaseType', 'mortgage')
    # R2SA is a rent-not-buy strategy — no purchase financing
    if deal_type == 'R2SA':
        purchase_type = 'r2sa'

    bridging_loan_details = None

    if purchase_type == 'cash':
        # Cash purchase: no loan, no monthly mortgage
        deposit_amount = purchase_price
        loan_amount = 0
        monthly_mortgage = 0
        annual_mortgage = 0

    elif purchase_type == 'bridging-loan':
        deposit_amount = purchase_price * (deposit_pct / 100)
        loan_amount = purchase_price - deposit_amount
        # Bridging loan: typically 0.75%/month, 12 months, 1% arrangement, 0.5% exit
        bridging_monthly_rate = float(data.get('bridgingMonthlyRate', 0.75))
        bridging_term_months = int(data.get('bridgingTermMonths', 12))
        bridging_arrangement_fee_pct = float(data.get('bridgingArrangementFee', 1.0))
        bridging_exit_fee_pct = float(data.get('bridgingExitFee', 0.5))

        monthly_interest = loan_amount * (bridging_monthly_rate / 100)
        total_interest = monthly_interest * bridging_term_months
        arrangement_fee = loan_amount * (bridging_arrangement_fee_pct / 100)
        exit_fee = loan_amount * (bridging_exit_fee_pct / 100)
        total_bridging_cost = total_interest + arrangement_fee + exit_fee
        total_repayment = loan_amount + total_interest + exit_fee
        # True APR: compound monthly rate → effective annual + fee drag
        _monthly_r = bridging_monthly_rate / 100
        _effective_annual = ((1 + _monthly_r) ** 12 - 1) * 100
        _fee_drag = (bridging_arrangement_fee_pct + bridging_exit_fee_pct) / max(bridging_term_months / 12, 0.083)
        bridging_apr = round(_effective_annual + _fee_drag, 2)
        bridging_loan_details = {
            'loan_amount': round(loan_amount, 0),
            'monthly_rate': bridging_monthly_rate,
            'term_months': bridging_term_months,
            'monthly_interest': round(monthly_interest, 2),
            'total_interest': round(total_interest, 0),
            'arrangement_fee': round(arrangement_fee, 0),
            'exit_fee': round(exit_fee, 0),
            'total_cost': round(total_bridging_cost, 0),
            'total_repayment': round(total_repayment, 0),
            'apr': round(bridging_apr, 2)
        }
        # Interest rolled up — no monthly payments during term
        monthly_mortgage = 0
        annual_mortgage = 0

    elif purchase_type == 'r2sa':
        # Rent-to-SA: investor rents the property, not buys it
        deposit_amount = 0
        loan_amount = 0
        monthly_mortgage = 0
        annual_mortgage = 0

    else:
        # Standard mortgage (default)
        deposit_amount = purchase_price * (deposit_pct / 100)
        loan_amount = purchase_price - deposit_amount
        monthly_mortgage = (loan_amount * (interest_rate / 100)) / 12
        annual_mortgage = monthly_mortgage * 12

    # BRR/Flip specific
    refurb_costs = float(data.get('refurbCosts', 0)) if deal_type in ['BRR', 'FLIP'] else 0
    arv = float(data.get('arv', 0)) if deal_type in ['BRR', 'FLIP'] else 0

    # HMO specific — room count × avg rate overrides monthly_rent
    room_count = int(data.get('roomCount', 0)) if deal_type == 'HMO' else 0
    avg_room_rate = float(data.get('avgRoomRate', 0)) if deal_type == 'HMO' else 0
    if deal_type == 'HMO' and room_count > 0 and avg_room_rate > 0:
        monthly_rent = room_count * avg_room_rate

    # R2SA specific — investor rents property and sublets as serviced accommodation
    r2sa_metrics = {}
    if deal_type == 'R2SA':
        sa_revenue = float(data.get('saMonthlySARevenue', 0))
        sa_setup_costs = float(data.get('saSetupCosts', 5000))
        monthly_rent_paid = monthly_rent  # rent paid to the landlord
        # Operating costs: cleaning, utilities, platform fees (~30% of revenue)
        monthly_op_costs = sa_revenue * 0.30
        monthly_profit = sa_revenue - monthly_rent_paid - monthly_op_costs
        annual_profit = monthly_profit * 12
        r2sa_roi = (annual_profit / sa_setup_costs) * 100 if sa_setup_costs > 0 else 0
        r2sa_metrics = {
            'monthly_rent_paid': round(monthly_rent_paid, 0),
            'sa_monthly_revenue': round(sa_revenue, 0),
            'monthly_op_costs': round(monthly_op_costs, 0),
            'monthly_profit': round(monthly_profit, 0),
            'annual_profit': round(annual_profit, 0),
            'setup_costs': round(sa_setup_costs, 0),
            'r2sa_roi': round(r2sa_roi, 1),
        }
        # For standard metric calculations, use profit as net income
        net_annual_income = annual_profit
        monthly_cashflow = monthly_profit
        annual_rent = sa_revenue * 12
        total_annual_expenses = (monthly_rent_paid + monthly_op_costs) * 12
        gross_yield = 0  # N/A for R2SA (no purchase)
        cash_invested = sa_setup_costs
        cash_on_cash = r2sa_roi
        net_yield = 0

    # Income and expenses (skipped for R2SA which calculates directly above)
    if deal_type != 'R2SA':
        annual_rent = monthly_rent * 12
        management_costs = annual_rent * 0.10
        void_costs = (monthly_rent / 4.33) * 2  # 2 weeks void
        maintenance_reserve = annual_rent * 0.08
        insurance = 480
        total_annual_expenses = (management_costs + void_costs + maintenance_reserve
                                 + insurance + annual_mortgage)
        net_annual_income = annual_rent - total_annual_expenses
        monthly_cashflow = net_annual_income / 12

        # Key metrics
        gross_yield = (annual_rent / purchase_price) * 100 if purchase_price > 0 else 0
        cash_invested = deposit_amount + stamp_duty + legal_fees + valuation_fee + arrangement_fee
        cash_on_cash = (net_annual_income / cash_invested) * 100 if cash_invested > 0 else 0
        net_yield = (net_annual_income / purchase_price) * 100 if purchase_price > 0 else 0

    # BRR specific metrics
    brr_metrics = {}
    if deal_type == 'BRR' and arv > 0:
        total_investment = purchase_price + refurb_costs + stamp_duty + legal_fees + valuation_fee + arrangement_fee
        equity_created = arv - total_investment
        refinance_amount = arv * 0.75
        money_left_in = total_investment - refinance_amount
        brr_roi = (equity_created / total_investment) * 100 if total_investment > 0 else 0
        
        brr_metrics = {
            'arv': round(arv, 0),
            'total_investment': round(total_investment, 0),
            'equity_created': round(equity_created, 0),
            'refinance_amount': round(refinance_amount, 0),
            'money_left_in': round(money_left_in, 0),
            'brr_roi': round(brr_roi, 2)
        }
    
    # Flip specific metrics
    flip_metrics = {}
    if deal_type == 'FLIP' and arv > 0:
        total_costs = purchase_price + refurb_costs + stamp_duty + legal_fees + valuation_fee + arrangement_fee + (monthly_mortgage * 6)  # 6 months holding
        agent_fees = arv * 0.015
        selling_costs = 1000 + agent_fees
        total_costs += selling_costs
        profit = arv - total_costs
        flip_roi = (profit / total_costs) * 100 if total_costs > 0 else 0
        
        flip_metrics = {
            'total_costs': round(total_costs, 0),
            'profit': round(profit, 0),
            'flip_roi': round(flip_roi, 2),
            'selling_costs': round(selling_costs, 0)
        }
    
    # Determine verdict
    if deal_type == 'BTL':
        if gross_yield >= 6 and monthly_cashflow >= 200 and cash_on_cash >= 8:
            verdict = "PROCEED"
            risk_level = "LOW"
        elif gross_yield >= 5 and monthly_cashflow >= 100:
            verdict = "REVIEW"
            risk_level = "MEDIUM"
        else:
            verdict = "AVOID"
            risk_level = "HIGH"
    elif deal_type == 'HMO':
        if gross_yield >= 10 and monthly_cashflow >= 500:
            verdict = "PROCEED"
            risk_level = "MEDIUM"
        elif gross_yield >= 8:
            verdict = "REVIEW"
            risk_level = "MEDIUM"
        else:
            verdict = "AVOID"
            risk_level = "HIGH"
    elif deal_type == 'BRR':
        if brr_metrics.get('brr_roi', 0) >= 20 and brr_metrics.get('money_left_in', 999999) <= cash_invested * 0.5:
            verdict = "PROCEED"
            risk_level = "MEDIUM"
        elif brr_metrics.get('brr_roi', 0) >= 15:
            verdict = "REVIEW"
            risk_level = "MEDIUM"
        else:
            verdict = "AVOID"
            risk_level = "HIGH"
    elif deal_type == 'FLIP':
        if flip_metrics.get('flip_roi', 0) >= 20 and flip_metrics.get('profit', 0) >= 20000:
            verdict = "PROCEED"
            risk_level = "MEDIUM"
        elif flip_metrics.get('flip_roi', 0) >= 15:
            verdict = "REVIEW"
            risk_level = "MEDIUM"
        else:
            verdict = "AVOID"
            risk_level = "HIGH"
    elif deal_type == 'R2SA':
        mp = r2sa_metrics.get('monthly_profit', 0)
        roi = r2sa_metrics.get('r2sa_roi', 0)
        if mp >= 500 and roi >= 50:
            verdict = "PROCEED"
            risk_level = "MEDIUM"  # R2SA carries subletting/void risk
        elif mp >= 200:
            verdict = "REVIEW"
            risk_level = "MEDIUM"
        else:
            verdict = "AVOID"
            risk_level = "HIGH"
    else:
        verdict = "REVIEW"
        risk_level = "MEDIUM"
    
    # Generate analysis text
    strengths = []
    weaknesses = []
    
    if gross_yield >= 6:
        strengths.append(f"Strong gross yield of {gross_yield:.2f}% exceeds 6% target")
    else:
        weaknesses.append(f"Gross yield of {gross_yield:.2f}% is below 6% target")
    
    if monthly_cashflow >= 200:
        strengths.append(f"Healthy monthly cashflow of £{monthly_cashflow:.0f} provides good buffer")
    else:
        weaknesses.append(f"Monthly cashflow of £{monthly_cashflow:.0f} is below £200 target")
    
    if cash_on_cash >= 8:
        strengths.append(f"Cash-on-cash return of {cash_on_cash:.2f}% meets investment criteria")
    else:
        weaknesses.append(f"Cash-on-cash return of {cash_on_cash:.2f}% is below 8% target")
    
    # Calculate AI Deal Score (0-100)
    deal_score = calculate_deal_score(
        deal_type, gross_yield, net_yield, monthly_cashflow, 
        cash_on_cash, risk_level, brr_metrics, flip_metrics
    )
    
    # Generate 5-year projection
    capital_growth_pct = float(data.get('capitalGrowthRate', 4.0) or 4.0)
    five_year_projection = generate_5_year_projection(
        annual_rent, net_annual_income, purchase_price,
        cash_invested, interest_rate, capital_growth_pct
    )
    
    # Get Article 4 info (AI-powered research as primary source)
    article_4_info = check_article_4(postcode)

    # Get accurate location info (AI-powered: country, region, full council name)
    location_info = get_location_from_ai(postcode)

    # Add deal-type-specific Article 4 guidance
    _a4_active = article_4_info.get('is_article_4', False)
    _a4_known  = article_4_info.get('known', True)
    _council   = article_4_info.get('council', 'your local council')

    if deal_type == 'HMO':
        if _a4_active:
            article_4_info['hmo_guidance'] = (
                'Planning Permission required to convert C3\u2192C4 (HMO). '
                'Full PP application fee: \u00a3234. '
                'Architect drawings + solicitor: typically \u00a31,500\u20133,000 total. '
                'Many councils in Article 4 zones refuse HMO applications \u2014 success is not guaranteed.'
            )
            article_4_info['social_housing_suggestion'] = (
                'C3\u2192C3b Social/Supported Housing: lease the property to a housing association or council '
                'instead of converting to HMO. No planning permission needed (stays within C3 class). '
                'Guaranteed rent: \u00a3500\u2013900/room/month from LA, 3\u20137-year lease terms, '
                'minimal voids, low management burden. Strong alternative in Article 4 areas.'
            )
        elif not _a4_known:
            article_4_info['hmo_guidance'] = (
                f'Article 4 status unconfirmed for this area \u2014 verify with {_council} before converting. '
                'If confirmed no Article 4: Mandatory HMO Licence required for 5+ occupants '
                '(\u00a3500\u20131,500 fee, 5-year term). If Article 4 applies: planning permission needed.'
            )
        else:
            article_4_info['hmo_guidance'] = (
                'No Article 4 \u2014 Permitted Development applies for C3\u2192C4 HMO (up to 6 unrelated people). '
                'Mandatory HMO Licence (5+ occupants): apply to local council, fee \u00a3500\u20131,500 (varies), '
                'valid 5 years. Property must meet HMO standards: fire doors (FD30s), interconnected smoke alarms, '
                'min room size 6.51 m\u00b2 per person, adequate kitchen/bathroom facilities. '
                'Check if Additional or Selective Licensing also applies in this ward.'
            )
    else:
        if _a4_active:
            article_4_info['advice'] = (
                'Article 4 in force \u2014 HMO conversion requires Planning Permission. '
                'Your chosen strategy (BTL/BRR/Flip/R2SA) is unaffected. '
                'If you later consider HMO: obtain planning permission first, or explore '
                'C3\u2192C3b social/supported housing as a high-yield alternative with no planning requirement.'
            )
        elif not _a4_known:
            article_4_info['advice'] = (
                f'Article 4 status unconfirmed \u2014 verify with {_council} if considering HMO in future.'
            )

    # Get strategy recommendations
    strategy_recommendations = get_strategy_recommendations(
        deal_type, gross_yield, cash_on_cash, monthly_cashflow, postcode,
        article_4_area=article_4_info['is_article_4']
    )
    
    # Get refurb estimates
    property_type_for_refurb = data.get('property_type', 'terraced').lower()
    internal_area_raw = data.get('internal_area')
    internal_area = float(internal_area_raw) if internal_area_raw and validate_numeric(internal_area_raw, 10, 2000) else None
    refurb_estimates = get_refurb_estimate(postcode, property_type_for_refurb, bedrooms, internal_area or 85)

    # Determine which refurb level was selected by the user (condition-based)
    property_condition = sanitize_input(data.get('property_condition', ''), 30)
    condition_level_map = {
        'needs-works': 'heavy',
        'fair':        'medium',
        'good':        'light',
        'excellent':   'light',
    }
    selected_refurb_level = condition_level_map.get(property_condition, None)
    
    # Score visualization data
    score_breakdown = {
        'total': deal_score,
        'yield_score': min(30, max(0, (gross_yield / 8) * 30)) if gross_yield >= 6 else max(0, (gross_yield / 6) * 10),
        'cashflow_score': 25 if monthly_cashflow >= 300 else (20 if monthly_cashflow >= 200 else (15 if monthly_cashflow >= 100 else 5)),
        'coc_score': 25 if cash_on_cash >= 12 else (20 if cash_on_cash >= 10 else (15 if cash_on_cash >= 8 else (5 if cash_on_cash >= 4 else 0))),
        'net_yield_score': 15 if net_yield >= 5 else (10 if net_yield >= 4 else (5 if net_yield >= 2 else 0)),
        'risk_score': 5 if risk_level == 'LOW' else 0
    }

    # ── Regional benchmark comparison ─────────────────────────────────────────
    regional_benchmark = compare_to_regional_benchmark(
        postcode, deal_type, gross_yield, monthly_cashflow
    )

    # ── Risk flag dashboard ───────────────────────────────────────────────────
    _ltv = (loan_amount / purchase_price * 100) if purchase_price > 0 else 0
    risk_flags = generate_risk_flags(
        deal_type=deal_type,
        gross_yield=gross_yield,
        net_yield=net_yield,
        monthly_cashflow=monthly_cashflow,
        cash_on_cash=cash_on_cash,
        risk_level=risk_level,
        loan_to_value=_ltv,
        interest_rate=interest_rate,
        monthly_rent=monthly_rent,
        monthly_mortgage=monthly_mortgage,
        purchase_price=purchase_price,
        brr_metrics=brr_metrics,
        flip_metrics=flip_metrics,
        r2sa_metrics=r2sa_metrics,
        article_4_active=article_4_info.get('is_article_4', False),
    )

    # Financial Breakdown (spreadsheet-style summary)
    _fb_total_money_in = purchase_price + stamp_duty + legal_fees + refurb_costs
    _fb_arv = arv if deal_type in ['BRR', 'FLIP'] else 0
    _fb_new_btl_mortgage = round(_fb_arv * 0.75, 0) if _fb_arv > 0 else 0
    _fb_new_monthly_mortgage = round((_fb_new_btl_mortgage * interest_rate / 100) / 12, 2) if _fb_new_btl_mortgage > 0 else round(monthly_mortgage, 2)
    _fb_monthly_mm = round(monthly_rent * 0.20, 2)
    _fb_monthly_cashflow = round(monthly_rent - _fb_new_monthly_mortgage - _fb_monthly_mm, 2)
    _fb_annual_cashflow = round(_fb_monthly_cashflow * 12, 0)
    _fb_money_left_in = round(_fb_total_money_in - _fb_new_btl_mortgage, 0) if _fb_arv > 0 else round(deposit_amount + stamp_duty + legal_fees + refurb_costs, 0)
    _fb_profit = round(_fb_arv - _fb_total_money_in, 0) if _fb_arv > 0 else 0
    _fb_roi = round((_fb_annual_cashflow / _fb_money_left_in * 100), 2) if _fb_money_left_in > 0 else 0
    _fb_flip_net_pct = round((_fb_profit / _fb_arv * 100), 2) if _fb_arv > 0 else 0
    _fb_ltv_pct = round((loan_amount / purchase_price * 100), 2) if purchase_price > 0 else 0

    financial_breakdown = {
        'price_offered': round(purchase_price, 0),
        'mortgage_pct': _fb_ltv_pct,
        'mortgage_amount': round(loan_amount, 0),
        'deposit': round(deposit_amount, 0),
        'stamp_duty': round(stamp_duty, 0),
        'legals': round(legal_fees, 0),
        'refurb_costs': round(refurb_costs, 0),
        'total_money_in': round(_fb_total_money_in, 0),
        'end_value': round(_fb_arv, 0),
        'new_mortgage_amount': _fb_new_btl_mortgage,
        'money_pulled_out': round(_fb_arv - _fb_new_btl_mortgage, 0) if _fb_arv > 0 else 0,
        'profit': _fb_profit,
        'money_left_in': _fb_money_left_in,
        'monthly_rent': round(monthly_rent, 2),
        'monthly_mortgage_new': _fb_new_monthly_mortgage,
        'monthly_mm': _fb_monthly_mm,
        'monthly_cashflow': _fb_monthly_cashflow,
        'annual_cashflow': _fb_annual_cashflow,
        'roi': _fb_roi,
        'flip_net_profit_pct': _fb_flip_net_pct,
        'interest_rate': interest_rate,
    }

    # Compile results
    results = {
        'deal_type': deal_type,
        'address': address,
        'postcode': postcode,
        'location': {
            'country': location_info.get('country', 'England'),
            'region': location_info.get('region', get_region_from_postcode(postcode)),
            'council': location_info.get('council', article_4_info.get('council', 'Local Council'))
        },
        'purchase_price': f"{purchase_price:,.0f}",
        'stamp_duty': f"{stamp_duty:,.0f}",
        'total_purchase_costs': f"{total_purchase_costs:,.0f}",
        'deposit_amount': f"{deposit_amount:,.0f}",
        'deposit_pct': f"{deposit_pct:.0f}",
        'loan_amount': f"{loan_amount:,.0f}",
        'interest_rate': f"{interest_rate:.1f}",
        'monthly_mortgage': f"{monthly_mortgage:.0f}",
        'monthly_rent': f"{monthly_rent:,.0f}",
        'annual_rent': f"{annual_rent:,.0f}",
        'total_annual_expenses': f"{total_annual_expenses:,.0f}",
        'net_annual_income': f"{net_annual_income:,.0f}",
        'monthly_cashflow': round(monthly_cashflow, 0),
        'gross_yield': f"{gross_yield:.2f}",
        'net_yield': f"{net_yield:.2f}",
        'cash_on_cash': f"{cash_on_cash:.2f}",
        'verdict': verdict,
        'risk_level': risk_level,
        'strengths': strengths,
        'weaknesses': weaknesses,
        'brr_metrics': brr_metrics,
        'flip_metrics': flip_metrics,
        'r2sa_metrics': r2sa_metrics,
        'bridging_loan_details': bridging_loan_details,
        'purchase_type': purchase_type,
        'deal_score': deal_score,
        'deal_score_label': get_score_label(deal_score),
        'score_breakdown': score_breakdown,
        'five_year_projection': five_year_projection,
        'article_4': article_4_info,
        'strategy_recommendations': strategy_recommendations,
        'refurb_estimates': refurb_estimates,
        'selected_refurb_level': selected_refurb_level,
        'internal_area': internal_area,
        'analysis_date': datetime.now().strftime('%Y-%m-%d'),
        'regional_benchmark': regional_benchmark,
        'risk_flags': risk_flags,
        'next_steps': [
            "Verify rental comparables in the area",
            "Get RICS survey (£400-600)",
            "Confirm mortgage availability",
            "Instruct solicitor for preliminary checks",
            "Arrange property viewing"
        ] if verdict == "PROCEED" else [
            "Review comparable sales in area",
            "Investigate why yield/cashflow is below target",
            "Consider negotiating purchase price",
            "Explore alternative strategies (HMO, BRR)",
            "Get professional opinion on achievable rent"
        ],
        'financial_breakdown': financial_breakdown,
        'refurb_costs': f"{refurb_costs:,.0f}",
        'legal_fees': f"{legal_fees:,.0f}",
    }
    
    return results


def get_region_from_postcode(postcode):
    """Get region name from postcode area"""
    area = postcode.split()[0] if ' ' in postcode else postcode[:3]
    area = area.upper()
    
    regions = {
        'M': 'Greater Manchester',
        'S': 'South Yorkshire',
        'L': 'Liverpool/Merseyside',
        'WA': 'Warrington/Cheshire',
        'WN': 'Wigan',
        'BL': 'Bolton',
        'OL': 'Oldham',
        'SK': 'Stockport',
        'BB': 'Blackburn',
        'PR': 'Preston',
        'CH': 'Chester',
        'CW': 'Crewe',
        'DE': 'Derbyshire',
        'ST': 'Stoke-on-Trent',
        'TF': 'Telford',
        'WR': 'Worcester',
        'B': 'Birmingham',
        'CV': 'Coventry',
        'LE': 'Leicester',
        'NG': 'Nottingham',
        'NG': 'Nottingham',
        'LS': 'Leeds',
        'BD': 'Bradford',
        'HD': 'Huddersfield',
        'HX': 'Halifax',
        'WF': 'Wakefield',
        'YO': 'York',
        'HG': 'Harrogate',
        'DL': 'Darlington',
        'TS': 'Teesside',
        'NE': 'Newcastle',
        'DH': 'Durham',
        'SR': 'Sunderland',
        'CA': 'Carlisle',
        'LA': 'Lancaster',
        'FY': 'Blackpool',
        'PR': 'Preston',
        'WN': 'Wigan',
        'CW': 'Crewe',
        'ST': 'Stoke',
        'DE': 'Derby',
        'LE': 'Leicester',
        'NG': 'Nottingham',
        'LN': 'Lincoln',
        'PE': 'Peterborough',
        'CB': 'Cambridge',
        'IP': 'Ipswich',
        'NR': 'Norwich',
        'CO': 'Colchester',
        'CM': 'Chelmsford',
        'SS': 'Southend',
        'RM': 'Romford',
        'IG': 'Ilford',
        'E': 'East London',
        'EC': 'City of London',
        'N': 'North London',
        'NW': 'North West London',
        'SE': 'South East London',
        'SW': 'South West London',
        'W': 'West London',
        'WC': 'Central London',
        'BR': 'Bromley',
        'CR': 'Croydon',
        'DA': 'Dartford',
        'EN': 'Enfield',
        'HA': 'Harrow',
        'HP': 'Hemel Hempstead',
        'KT': 'Kingston',
        'LU': 'Luton',
        'MK': 'Milton Keynes',
        'OX': 'Oxford',
        'RG': 'Reading',
        'RH': 'Redhill',
        'SL': 'Slough',
        'SM': 'Sutton',
        'TN': 'Tunbridge Wells',
        'TW': 'Twickenham',
        'UB': 'Uxbridge',
        'WD': 'Watford',
        'PO': 'Portsmouth',
        'SO': 'Southampton',
        'GU': 'Guildford',
        'BN': 'Brighton',
        'CT': 'Canterbury',
        'ME': 'Medway',
        'TN': 'Tunbridge Wells',
        'TR': 'Truro',
        'PL': 'Plymouth',
        'EX': 'Exeter',
        'TQ': 'Torquay',
        'TA': 'Taunton',
        'BA': 'Bath',
        'BS': 'Bristol',
        'CF': 'Cardiff',
        'NP': 'Newport',
        'GL': 'Gloucester',
        'SN': 'Swindon',
        'SP': 'Salisbury',
        'DT': 'Dorchester',
        'BH': 'Bournemouth',
    }
    
    return regions.get(area, 'England')


# ============================================================
# REGIONAL BENCHMARK DATABASE
# Median yields & cashflow by UK postcode area, sourced from
# Land Registry, Zoopla & Rightmove market reports (2024-25).
# Covers BTL, HMO and general investment benchmarks.
# ============================================================

REGIONAL_BENCHMARKS = {
    # --- Greater London ---
    'EC': {'region': 'City of London',       'btl_median_yield': 3.8, 'hmo_median_yield': 6.2, 'median_cashflow': -120, 'avg_price': 820000, 'rental_growth_pa': 4.5},
    'WC': {'region': 'Central London',       'btl_median_yield': 3.5, 'hmo_median_yield': 5.9, 'median_cashflow': -180, 'avg_price': 950000, 'rental_growth_pa': 4.2},
    'W':  {'region': 'West London',          'btl_median_yield': 3.6, 'hmo_median_yield': 6.0, 'median_cashflow': -150, 'avg_price': 880000, 'rental_growth_pa': 4.0},
    'SW': {'region': 'South West London',    'btl_median_yield': 3.7, 'hmo_median_yield': 6.1, 'median_cashflow': -100, 'avg_price': 750000, 'rental_growth_pa': 4.3},
    'SE': {'region': 'South East London',    'btl_median_yield': 4.2, 'hmo_median_yield': 6.8, 'median_cashflow':   50, 'avg_price': 560000, 'rental_growth_pa': 4.8},
    'E':  {'region': 'East London',          'btl_median_yield': 4.5, 'hmo_median_yield': 7.2, 'median_cashflow':   80, 'avg_price': 490000, 'rental_growth_pa': 5.0},
    'N':  {'region': 'North London',         'btl_median_yield': 3.9, 'hmo_median_yield': 6.3, 'median_cashflow':  -60, 'avg_price': 680000, 'rental_growth_pa': 4.1},
    'NW': {'region': 'North West London',    'btl_median_yield': 4.0, 'hmo_median_yield': 6.5, 'median_cashflow':  -30, 'avg_price': 650000, 'rental_growth_pa': 4.2},
    'BR': {'region': 'Bromley',              'btl_median_yield': 4.1, 'hmo_median_yield': 6.6, 'median_cashflow':   20, 'avg_price': 520000, 'rental_growth_pa': 4.0},
    'CR': {'region': 'Croydon',              'btl_median_yield': 4.4, 'hmo_median_yield': 7.0, 'median_cashflow':   90, 'avg_price': 440000, 'rental_growth_pa': 4.5},
    'DA': {'region': 'Dartford',             'btl_median_yield': 4.6, 'hmo_median_yield': 7.3, 'median_cashflow':  120, 'avg_price': 400000, 'rental_growth_pa': 4.2},
    'EN': {'region': 'Enfield',              'btl_median_yield': 4.1, 'hmo_median_yield': 6.7, 'median_cashflow':   30, 'avg_price': 490000, 'rental_growth_pa': 4.0},
    'HA': {'region': 'Harrow',               'btl_median_yield': 4.0, 'hmo_median_yield': 6.5, 'median_cashflow':   10, 'avg_price': 510000, 'rental_growth_pa': 4.0},
    'IG': {'region': 'Ilford',               'btl_median_yield': 4.6, 'hmo_median_yield': 7.4, 'median_cashflow':  130, 'avg_price': 430000, 'rental_growth_pa': 4.8},
    'KT': {'region': 'Kingston',             'btl_median_yield': 3.8, 'hmo_median_yield': 6.2, 'median_cashflow':  -80, 'avg_price': 600000, 'rental_growth_pa': 3.8},
    'RM': {'region': 'Romford',              'btl_median_yield': 4.7, 'hmo_median_yield': 7.5, 'median_cashflow':  150, 'avg_price': 400000, 'rental_growth_pa': 4.7},
    'SM': {'region': 'Sutton',               'btl_median_yield': 4.1, 'hmo_median_yield': 6.6, 'median_cashflow':   40, 'avg_price': 490000, 'rental_growth_pa': 4.0},
    'TW': {'region': 'Twickenham',           'btl_median_yield': 3.7, 'hmo_median_yield': 6.0, 'median_cashflow': -110, 'avg_price': 640000, 'rental_growth_pa': 3.8},
    'UB': {'region': 'Uxbridge',             'btl_median_yield': 4.2, 'hmo_median_yield': 6.8, 'median_cashflow':   60, 'avg_price': 470000, 'rental_growth_pa': 4.2},
    'WD': {'region': 'Watford',              'btl_median_yield': 4.3, 'hmo_median_yield': 7.0, 'median_cashflow':   80, 'avg_price': 450000, 'rental_growth_pa': 4.0},
    # --- Home Counties ---
    'AL': {'region': 'St Albans',            'btl_median_yield': 3.9, 'hmo_median_yield': 6.3, 'median_cashflow':  -50, 'avg_price': 580000, 'rental_growth_pa': 3.8},
    'CM': {'region': 'Chelmsford',           'btl_median_yield': 4.4, 'hmo_median_yield': 7.0, 'median_cashflow':  100, 'avg_price': 420000, 'rental_growth_pa': 4.2},
    'CO': {'region': 'Colchester',           'btl_median_yield': 4.6, 'hmo_median_yield': 7.3, 'median_cashflow':  130, 'avg_price': 390000, 'rental_growth_pa': 4.0},
    'CT': {'region': 'Canterbury',           'btl_median_yield': 5.0, 'hmo_median_yield': 7.8, 'median_cashflow':  180, 'avg_price': 360000, 'rental_growth_pa': 4.2},
    'GU': {'region': 'Guildford',            'btl_median_yield': 3.7, 'hmo_median_yield': 6.0, 'median_cashflow': -100, 'avg_price': 620000, 'rental_growth_pa': 3.5},
    'HP': {'region': 'Hemel Hempstead',      'btl_median_yield': 4.1, 'hmo_median_yield': 6.6, 'median_cashflow':   40, 'avg_price': 490000, 'rental_growth_pa': 3.8},
    'LU': {'region': 'Luton',                'btl_median_yield': 5.2, 'hmo_median_yield': 8.2, 'median_cashflow':  220, 'avg_price': 320000, 'rental_growth_pa': 4.5},
    'ME': {'region': 'Medway',               'btl_median_yield': 5.1, 'hmo_median_yield': 8.0, 'median_cashflow':  200, 'avg_price': 330000, 'rental_growth_pa': 4.3},
    'MK': {'region': 'Milton Keynes',        'btl_median_yield': 4.8, 'hmo_median_yield': 7.6, 'median_cashflow':  160, 'avg_price': 370000, 'rental_growth_pa': 4.0},
    'OX': {'region': 'Oxford',               'btl_median_yield': 4.2, 'hmo_median_yield': 7.2, 'median_cashflow':   50, 'avg_price': 510000, 'rental_growth_pa': 4.0},
    'RG': {'region': 'Reading',              'btl_median_yield': 4.3, 'hmo_median_yield': 7.0, 'median_cashflow':   80, 'avg_price': 450000, 'rental_growth_pa': 4.0},
    'RH': {'region': 'Redhill',              'btl_median_yield': 4.0, 'hmo_median_yield': 6.5, 'median_cashflow':   10, 'avg_price': 510000, 'rental_growth_pa': 3.8},
    'SL': {'region': 'Slough',               'btl_median_yield': 4.5, 'hmo_median_yield': 7.2, 'median_cashflow':  110, 'avg_price': 410000, 'rental_growth_pa': 4.5},
    'SS': {'region': 'Southend',             'btl_median_yield': 4.9, 'hmo_median_yield': 7.7, 'median_cashflow':  170, 'avg_price': 340000, 'rental_growth_pa': 4.3},
    'TN': {'region': 'Tunbridge Wells',      'btl_median_yield': 4.0, 'hmo_median_yield': 6.5, 'median_cashflow':   20, 'avg_price': 500000, 'rental_growth_pa': 3.8},
    # --- South East / South ---
    'BN': {'region': 'Brighton',             'btl_median_yield': 4.5, 'hmo_median_yield': 7.3, 'median_cashflow':  110, 'avg_price': 420000, 'rental_growth_pa': 4.5},
    'PO': {'region': 'Portsmouth',           'btl_median_yield': 5.0, 'hmo_median_yield': 8.0, 'median_cashflow':  190, 'avg_price': 310000, 'rental_growth_pa': 4.2},
    'SO': {'region': 'Southampton',          'btl_median_yield': 5.2, 'hmo_median_yield': 8.3, 'median_cashflow':  220, 'avg_price': 300000, 'rental_growth_pa': 4.3},
    'SP': {'region': 'Salisbury',            'btl_median_yield': 4.2, 'hmo_median_yield': 6.8, 'median_cashflow':   60, 'avg_price': 460000, 'rental_growth_pa': 3.8},
    'BH': {'region': 'Bournemouth',          'btl_median_yield': 4.6, 'hmo_median_yield': 7.4, 'median_cashflow':  130, 'avg_price': 380000, 'rental_growth_pa': 4.2},
    'DT': {'region': 'Dorchester',           'btl_median_yield': 4.4, 'hmo_median_yield': 7.0, 'median_cashflow':   90, 'avg_price': 380000, 'rental_growth_pa': 3.5},
    # --- South West ---
    'BA': {'region': 'Bath',                 'btl_median_yield': 4.5, 'hmo_median_yield': 7.5, 'median_cashflow':  110, 'avg_price': 430000, 'rental_growth_pa': 4.0},
    'BS': {'region': 'Bristol',              'btl_median_yield': 4.8, 'hmo_median_yield': 7.8, 'median_cashflow':  160, 'avg_price': 390000, 'rental_growth_pa': 4.5},
    'EX': {'region': 'Exeter',               'btl_median_yield': 4.9, 'hmo_median_yield': 7.8, 'median_cashflow':  170, 'avg_price': 360000, 'rental_growth_pa': 4.2},
    'PL': {'region': 'Plymouth',             'btl_median_yield': 5.5, 'hmo_median_yield': 8.8, 'median_cashflow':  260, 'avg_price': 270000, 'rental_growth_pa': 4.5},
    'TA': {'region': 'Taunton',              'btl_median_yield': 4.7, 'hmo_median_yield': 7.5, 'median_cashflow':  140, 'avg_price': 350000, 'rental_growth_pa': 3.8},
    'TQ': {'region': 'Torquay',              'btl_median_yield': 5.2, 'hmo_median_yield': 8.2, 'median_cashflow':  210, 'avg_price': 300000, 'rental_growth_pa': 4.0},
    'TR': {'region': 'Truro',                'btl_median_yield': 4.8, 'hmo_median_yield': 7.6, 'median_cashflow':  150, 'avg_price': 340000, 'rental_growth_pa': 3.8},
    # --- Midlands ---
    'B':  {'region': 'Birmingham',           'btl_median_yield': 5.8, 'hmo_median_yield': 9.5, 'median_cashflow':  290, 'avg_price': 260000, 'rental_growth_pa': 5.2},
    'CV': {'region': 'Coventry',             'btl_median_yield': 5.5, 'hmo_median_yield': 9.0, 'median_cashflow':  250, 'avg_price': 270000, 'rental_growth_pa': 5.0},
    'DE': {'region': 'Derby',                'btl_median_yield': 5.8, 'hmo_median_yield': 9.3, 'median_cashflow':  280, 'avg_price': 230000, 'rental_growth_pa': 4.8},
    'GL': {'region': 'Gloucester',           'btl_median_yield': 5.0, 'hmo_median_yield': 8.0, 'median_cashflow':  190, 'avg_price': 310000, 'rental_growth_pa': 4.2},
    'LE': {'region': 'Leicester',            'btl_median_yield': 6.0, 'hmo_median_yield': 9.8, 'median_cashflow':  310, 'avg_price': 225000, 'rental_growth_pa': 5.5},
    'LN': {'region': 'Lincoln',              'btl_median_yield': 6.2, 'hmo_median_yield': 9.8, 'median_cashflow':  320, 'avg_price': 195000, 'rental_growth_pa': 4.5},
    'NG': {'region': 'Nottingham',           'btl_median_yield': 6.5, 'hmo_median_yield': 10.5,'median_cashflow':  360, 'avg_price': 210000, 'rental_growth_pa': 5.8},
    'NN': {'region': 'Northampton',          'btl_median_yield': 5.5, 'hmo_median_yield': 8.8, 'median_cashflow':  250, 'avg_price': 265000, 'rental_growth_pa': 4.8},
    'SN': {'region': 'Swindon',              'btl_median_yield': 4.8, 'hmo_median_yield': 7.6, 'median_cashflow':  160, 'avg_price': 310000, 'rental_growth_pa': 4.0},
    'ST': {'region': 'Stoke-on-Trent',       'btl_median_yield': 7.0, 'hmo_median_yield': 11.0,'median_cashflow':  400, 'avg_price': 165000, 'rental_growth_pa': 5.0},
    'TF': {'region': 'Telford',              'btl_median_yield': 5.8, 'hmo_median_yield': 9.2, 'median_cashflow':  270, 'avg_price': 230000, 'rental_growth_pa': 4.5},
    'WR': {'region': 'Worcester',            'btl_median_yield': 5.2, 'hmo_median_yield': 8.5, 'median_cashflow':  220, 'avg_price': 280000, 'rental_growth_pa': 4.2},
    'WS': {'region': 'Walsall',              'btl_median_yield': 6.2, 'hmo_median_yield': 9.8, 'median_cashflow':  330, 'avg_price': 200000, 'rental_growth_pa': 5.2},
    'WV': {'region': 'Wolverhampton',        'btl_median_yield': 6.5, 'hmo_median_yield': 10.2,'median_cashflow':  360, 'avg_price': 190000, 'rental_growth_pa': 5.0},
    # --- Yorkshire ---
    'BD': {'region': 'Bradford',             'btl_median_yield': 7.2, 'hmo_median_yield': 11.5,'median_cashflow':  410, 'avg_price': 155000, 'rental_growth_pa': 5.5},
    'DN': {'region': 'Doncaster',            'btl_median_yield': 6.8, 'hmo_median_yield': 10.8,'median_cashflow':  370, 'avg_price': 170000, 'rental_growth_pa': 5.2},
    'HD': {'region': 'Huddersfield',         'btl_median_yield': 6.8, 'hmo_median_yield': 10.8,'median_cashflow':  370, 'avg_price': 185000, 'rental_growth_pa': 5.2},
    'HG': {'region': 'Harrogate',            'btl_median_yield': 4.5, 'hmo_median_yield': 7.2, 'median_cashflow':  100, 'avg_price': 440000, 'rental_growth_pa': 4.0},
    'HU': {'region': 'Hull',                 'btl_median_yield': 7.5, 'hmo_median_yield': 12.0,'median_cashflow':  440, 'avg_price': 145000, 'rental_growth_pa': 5.0},
    'HX': {'region': 'Halifax',              'btl_median_yield': 6.9, 'hmo_median_yield': 11.0,'median_cashflow':  380, 'avg_price': 175000, 'rental_growth_pa': 5.2},
    'LS': {'region': 'Leeds',                'btl_median_yield': 6.2, 'hmo_median_yield': 10.0,'median_cashflow':  320, 'avg_price': 225000, 'rental_growth_pa': 5.8},
    'S':  {'region': 'Sheffield',            'btl_median_yield': 6.5, 'hmo_median_yield': 10.5,'median_cashflow':  350, 'avg_price': 200000, 'rental_growth_pa': 5.5},
    'WF': {'region': 'Wakefield',            'btl_median_yield': 6.5, 'hmo_median_yield': 10.5,'median_cashflow':  350, 'avg_price': 190000, 'rental_growth_pa': 5.2},
    'YO': {'region': 'York',                 'btl_median_yield': 5.0, 'hmo_median_yield': 8.0, 'median_cashflow':  190, 'avg_price': 340000, 'rental_growth_pa': 4.5},
    # --- North West ---
    'BB': {'region': 'Blackburn',            'btl_median_yield': 7.0, 'hmo_median_yield': 11.2,'median_cashflow':  390, 'avg_price': 160000, 'rental_growth_pa': 5.0},
    'BL': {'region': 'Bolton',               'btl_median_yield': 6.5, 'hmo_median_yield': 10.5,'median_cashflow':  340, 'avg_price': 190000, 'rental_growth_pa': 5.2},
    'CH': {'region': 'Chester',              'btl_median_yield': 5.2, 'hmo_median_yield': 8.3, 'median_cashflow':  220, 'avg_price': 310000, 'rental_growth_pa': 4.5},
    'CW': {'region': 'Crewe',                'btl_median_yield': 5.8, 'hmo_median_yield': 9.3, 'median_cashflow':  270, 'avg_price': 235000, 'rental_growth_pa': 4.5},
    'FY': {'region': 'Blackpool',            'btl_median_yield': 7.5, 'hmo_median_yield': 12.0,'median_cashflow':  430, 'avg_price': 140000, 'rental_growth_pa': 4.8},
    'L':  {'region': 'Liverpool',            'btl_median_yield': 7.0, 'hmo_median_yield': 11.2,'median_cashflow':  390, 'avg_price': 180000, 'rental_growth_pa': 5.5},
    'LA': {'region': 'Lancaster',            'btl_median_yield': 5.8, 'hmo_median_yield': 9.5, 'median_cashflow':  270, 'avg_price': 235000, 'rental_growth_pa': 4.5},
    'M':  {'region': 'Manchester',           'btl_median_yield': 6.8, 'hmo_median_yield': 11.0,'median_cashflow':  370, 'avg_price': 220000, 'rental_growth_pa': 6.0},
    'OL': {'region': 'Oldham',               'btl_median_yield': 7.0, 'hmo_median_yield': 11.2,'median_cashflow':  390, 'avg_price': 165000, 'rental_growth_pa': 5.5},
    'PR': {'region': 'Preston',              'btl_median_yield': 6.5, 'hmo_median_yield': 10.5,'median_cashflow':  340, 'avg_price': 185000, 'rental_growth_pa': 5.0},
    'SK': {'region': 'Stockport',            'btl_median_yield': 5.5, 'hmo_median_yield': 8.8, 'median_cashflow':  240, 'avg_price': 285000, 'rental_growth_pa': 4.8},
    'WA': {'region': 'Warrington',           'btl_median_yield': 5.8, 'hmo_median_yield': 9.3, 'median_cashflow':  270, 'avg_price': 235000, 'rental_growth_pa': 4.8},
    'WN': {'region': 'Wigan',                'btl_median_yield': 6.5, 'hmo_median_yield': 10.5,'median_cashflow':  340, 'avg_price': 185000, 'rental_growth_pa': 5.0},
    # --- North East ---
    'CA': {'region': 'Carlisle',             'btl_median_yield': 6.5, 'hmo_median_yield': 10.2,'median_cashflow':  330, 'avg_price': 180000, 'rental_growth_pa': 4.5},
    'DH': {'region': 'Durham',               'btl_median_yield': 6.8, 'hmo_median_yield': 10.8,'median_cashflow':  360, 'avg_price': 175000, 'rental_growth_pa': 4.8},
    'DL': {'region': 'Darlington',           'btl_median_yield': 6.5, 'hmo_median_yield': 10.5,'median_cashflow':  340, 'avg_price': 180000, 'rental_growth_pa': 4.5},
    'NE': {'region': 'Newcastle',            'btl_median_yield': 7.0, 'hmo_median_yield': 11.2,'median_cashflow':  390, 'avg_price': 180000, 'rental_growth_pa': 5.2},
    'SR': {'region': 'Sunderland',           'btl_median_yield': 7.5, 'hmo_median_yield': 12.0,'median_cashflow':  430, 'avg_price': 155000, 'rental_growth_pa': 5.0},
    'TS': {'region': 'Teesside',             'btl_median_yield': 7.2, 'hmo_median_yield': 11.5,'median_cashflow':  410, 'avg_price': 155000, 'rental_growth_pa': 5.0},
    # --- East / East Midlands ---
    'CB': {'region': 'Cambridge',            'btl_median_yield': 4.5, 'hmo_median_yield': 7.5, 'median_cashflow':  110, 'avg_price': 490000, 'rental_growth_pa': 4.5},
    'IP': {'region': 'Ipswich',              'btl_median_yield': 5.0, 'hmo_median_yield': 8.0, 'median_cashflow':  180, 'avg_price': 320000, 'rental_growth_pa': 4.2},
    'NR': {'region': 'Norwich',              'btl_median_yield': 5.2, 'hmo_median_yield': 8.3, 'median_cashflow':  210, 'avg_price': 300000, 'rental_growth_pa': 4.2},
    'PE': {'region': 'Peterborough',         'btl_median_yield': 5.5, 'hmo_median_yield': 8.8, 'median_cashflow':  250, 'avg_price': 270000, 'rental_growth_pa': 4.8},
    # --- Wales ---
    'CF': {'region': 'Cardiff',              'btl_median_yield': 5.5, 'hmo_median_yield': 9.0, 'median_cashflow':  250, 'avg_price': 280000, 'rental_growth_pa': 4.8},
    'LD': {'region': 'Llandrindod Wells',    'btl_median_yield': 5.8, 'hmo_median_yield': 9.3, 'median_cashflow':  270, 'avg_price': 220000, 'rental_growth_pa': 3.8},
    'LL': {'region': 'North Wales',          'btl_median_yield': 5.5, 'hmo_median_yield': 9.0, 'median_cashflow':  240, 'avg_price': 230000, 'rental_growth_pa': 4.0},
    'NP': {'region': 'Newport',              'btl_median_yield': 5.8, 'hmo_median_yield': 9.3, 'median_cashflow':  270, 'avg_price': 240000, 'rental_growth_pa': 4.5},
    'SA': {'region': 'Swansea',              'btl_median_yield': 5.8, 'hmo_median_yield': 9.3, 'median_cashflow':  270, 'avg_price': 225000, 'rental_growth_pa': 4.5},
    'SY': {'region': 'Shrewsbury/Mid Wales', 'btl_median_yield': 5.5, 'hmo_median_yield': 8.8, 'median_cashflow':  240, 'avg_price': 240000, 'rental_growth_pa': 4.0},
    # --- Scotland ---
    'AB': {'region': 'Aberdeen',             'btl_median_yield': 7.2, 'hmo_median_yield': 11.5,'median_cashflow':  400, 'avg_price': 190000, 'rental_growth_pa': 4.5},
    'DD': {'region': 'Dundee',               'btl_median_yield': 7.5, 'hmo_median_yield': 12.0,'median_cashflow':  420, 'avg_price': 165000, 'rental_growth_pa': 5.0},
    'EH': {'region': 'Edinburgh',            'btl_median_yield': 5.5, 'hmo_median_yield': 9.0, 'median_cashflow':  250, 'avg_price': 320000, 'rental_growth_pa': 5.5},
    'FK': {'region': 'Falkirk/Stirling',     'btl_median_yield': 6.8, 'hmo_median_yield': 10.8,'median_cashflow':  360, 'avg_price': 185000, 'rental_growth_pa': 4.8},
    'G':  {'region': 'Glasgow',              'btl_median_yield': 6.5, 'hmo_median_yield': 10.5,'median_cashflow':  340, 'avg_price': 195000, 'rental_growth_pa': 5.5},
    'KA': {'region': 'Kilmarnock/Ayrshire',  'btl_median_yield': 7.2, 'hmo_median_yield': 11.5,'median_cashflow':  400, 'avg_price': 155000, 'rental_growth_pa': 4.5},
    'KY': {'region': 'Kirkcaldy/Fife',       'btl_median_yield': 7.0, 'hmo_median_yield': 11.2,'median_cashflow':  380, 'avg_price': 165000, 'rental_growth_pa': 4.8},
    'ML': {'region': 'Motherwell/Lanark',    'btl_median_yield': 7.2, 'hmo_median_yield': 11.5,'median_cashflow':  400, 'avg_price': 155000, 'rental_growth_pa': 4.8},
    'PA': {'region': 'Paisley',              'btl_median_yield': 7.0, 'hmo_median_yield': 11.2,'median_cashflow':  380, 'avg_price': 160000, 'rental_growth_pa': 5.0},
    'PH': {'region': 'Perth',                'btl_median_yield': 6.5, 'hmo_median_yield': 10.5,'median_cashflow':  340, 'avg_price': 190000, 'rental_growth_pa': 4.5},
}

# National fallback benchmark
_NATIONAL_FALLBACK = {
    'region': 'England & Wales',
    'btl_median_yield': 5.5,
    'hmo_median_yield': 9.0,
    'median_cashflow': 240,
    'avg_price': 310000,
    'rental_growth_pa': 4.5
}


def get_regional_benchmark(postcode: str, deal_type: str = 'BTL') -> dict:
    """
    Return regional benchmark metrics for a given postcode and deal type.
    Looks up the postcode prefix (e.g. 'M', 'LS', 'SW') in REGIONAL_BENCHMARKS.
    Falls back to national averages if postcode area is not found.

    Returns a dict with:
        region, median_yield, median_cashflow, avg_price,
        rental_growth_pa, data_source
    """
    if not postcode:
        bench = _NATIONAL_FALLBACK.copy()
        bench['data_source'] = 'National average (no postcode)'
        bench['median_yield'] = bench['btl_median_yield']
        return bench

    area = postcode.strip().upper().split()[0] if ' ' in postcode else postcode.strip().upper()

    # Try exact match first (e.g. 'LS', 'SW', 'NW', 'M1')
    bench = REGIONAL_BENCHMARKS.get(area)

    # Try two-character alpha prefix (e.g. 'LS' from 'LS1', 'SW' from 'SW1A')
    if not bench:
        alpha_prefix_2 = ''.join(c for c in area if c.isalpha())[:2]
        bench = REGIONAL_BENCHMARKS.get(alpha_prefix_2)

    # Try single-character alpha prefix (e.g. 'M', 'L', 'B', 'S')
    if not bench:
        alpha_prefix_1 = ''.join(c for c in area if c.isalpha())[:1]
        bench = REGIONAL_BENCHMARKS.get(alpha_prefix_1)

    # National fallback
    if not bench:
        bench = _NATIONAL_FALLBACK.copy()
        bench['data_source'] = 'National average (postcode area not in database)'
    else:
        bench = bench.copy()
        bench['data_source'] = 'Metusa Proprietary Regional Database'

    # Select yield metric based on deal type
    if deal_type == 'HMO':
        bench['median_yield'] = bench['hmo_median_yield']
        bench['yield_label'] = 'HMO Median Gross Yield'
    else:
        bench['median_yield'] = bench['btl_median_yield']
        bench['yield_label'] = 'BTL Median Gross Yield'

    return bench


def compare_to_regional_benchmark(postcode: str, deal_type: str,
                                   deal_gross_yield: float,
                                   deal_monthly_cashflow: float) -> dict:
    """
    Compare deal metrics against the regional benchmark database.
    Returns a panel-ready dict for the frontend with:
        - regional_median_yield, your_yield, yield_vs_median (%, above/below)
        - regional_avg_cashflow, your_cashflow, cashflow_vs_avg (£, above/below)
        - yield_percentile (estimated), cashflow_percentile (estimated)
        - region_name, data_source
    """
    bench = get_regional_benchmark(postcode, deal_type)

    median_yield = bench['median_yield']
    median_cashflow = bench['median_cashflow']

    yield_diff = round(deal_gross_yield - median_yield, 2)
    cashflow_diff = round(deal_monthly_cashflow - median_cashflow, 0)

    # Percentile estimation: assume normal-ish distribution around the median
    # Yield std dev ~1.5pp for most UK areas, cashflow std dev ~£150/mo
    import math

    def _normal_cdf(x, mean, std):
        """Approximate normal CDF using error function."""
        if std <= 0:
            return 50.0
        z = (x - mean) / (std * math.sqrt(2))
        return round(50.0 * (1.0 + math.erf(z)), 1)

    yield_percentile = _normal_cdf(deal_gross_yield, median_yield, 1.5)
    cashflow_percentile = _normal_cdf(deal_monthly_cashflow, median_cashflow, 160)

    # Clamp percentiles to 1-99
    yield_percentile = max(1.0, min(99.0, yield_percentile))
    cashflow_percentile = max(1.0, min(99.0, cashflow_percentile))

    def _label(diff, unit='%'):
        if abs(diff) < 0.05 and unit == '%':
            return 'In line with regional median'
        if abs(diff) < 5 and unit == '£':
            return 'In line with regional average'
        direction = 'above' if diff > 0 else 'below'
        return f"{abs(diff)}{unit} {direction} regional {'median' if unit == '%' else 'average'}"

    return {
        'region_name': bench['region'],
        'postcode_area': postcode.strip().upper().split()[0] if postcode else 'N/A',
        'data_source': bench['data_source'],
        # Yield comparison
        'regional_median_yield': median_yield,
        'your_yield': round(deal_gross_yield, 2),
        'yield_difference': yield_diff,
        'yield_vs_median_label': _label(yield_diff, '%'),
        'yield_percentile': yield_percentile,
        # Cashflow comparison
        'regional_avg_cashflow': median_cashflow,
        'your_cashflow': round(deal_monthly_cashflow, 0),
        'cashflow_difference': cashflow_diff,
        'cashflow_vs_avg_label': _label(cashflow_diff, '£'),
        'cashflow_percentile': cashflow_percentile,
        # Summary
        'summary': (
            f"This deal's {deal_gross_yield:.1f}% yield ranks in the "
            f"top {100 - yield_percentile:.0f}% of {bench['region']} deals "
            f"and its £{deal_monthly_cashflow:,.0f}/mo cashflow beats "
            f"{cashflow_percentile:.0f}% of comparable properties in this area."
            if yield_diff >= 0 and cashflow_diff >= 0
            else f"This deal's yield and cashflow are "
                 f"{'above' if yield_diff >= 0 else 'below'} and "
                 f"{'above' if cashflow_diff >= 0 else 'below'} "
                 f"the {bench['region']} regional benchmarks respectively."
        )
    }


def generate_risk_flags(deal_type: str, gross_yield: float, net_yield: float,
                        monthly_cashflow: float, cash_on_cash: float,
                        risk_level: str, loan_to_value: float,
                        interest_rate: float, monthly_rent: float,
                        monthly_mortgage: float, purchase_price: float,
                        brr_metrics: dict = None, flip_metrics: dict = None,
                        r2sa_metrics: dict = None,
                        article_4_active: bool = False) -> list:
    """
    Generate colour-coded risk flag cards with severity levels.
    Each flag is a dict with:
        id, name, severity ('HIGH'|'MEDIUM'|'LOW'), color ('red'|'amber'|'green'),
        description, mitigation
    Flags are sorted highest severity first.
    """
    flags = []

    # ── 1. Leverage Risk ──────────────────────────────────────────────────────
    if loan_to_value >= 80:
        flags.append({
            'id': 'leverage_risk',
            'name': 'Leverage Risk',
            'severity': 'HIGH',
            'color': 'red',
            'icon': 'alert-triangle',
            'description': (
                f"LTV of {loan_to_value:.0f}% means a modest 15-20% fall in property value "
                "would put you in negative equity. High leverage amplifies both gains and losses."
            ),
            'mitigation': 'Consider increasing deposit to reduce LTV below 75%, or build an equity buffer via refurb before refinancing.',
        })
    elif loan_to_value >= 70:
        flags.append({
            'id': 'leverage_risk',
            'name': 'Leverage Risk',
            'severity': 'MEDIUM',
            'color': 'amber',
            'icon': 'alert-triangle',
            'description': (
                f"LTV of {loan_to_value:.0f}% is manageable but leaves limited equity buffer. "
                "A 25% correction in prices could erode equity significantly."
            ),
            'mitigation': 'Stress-test your numbers at a 20% price fall. Ensure rent covers mortgage at rates 3% higher than current.',
        })

    # ── 2. Interest Rate / Stress Test Risk ───────────────────────────────────
    stressed_rate = interest_rate + 3.0
    if monthly_mortgage > 0:
        stressed_mortgage = monthly_mortgage * (stressed_rate / interest_rate) if interest_rate > 0 else monthly_mortgage * 1.5
        stressed_cashflow = monthly_cashflow - (stressed_mortgage - monthly_mortgage)
    else:
        stressed_cashflow = monthly_cashflow

    if stressed_cashflow < -200:
        flags.append({
            'id': 'rate_risk',
            'name': 'Interest Rate Risk',
            'severity': 'HIGH',
            'color': 'red',
            'icon': 'trending-up',
            'description': (
                f"At +3% stressed rate ({stressed_rate:.1f}%), monthly cashflow would fall to "
                f"£{stressed_cashflow:,.0f} — significantly negative. "
                "This deal is highly sensitive to rising mortgage rates."
            ),
            'mitigation': 'Consider a 5-year fixed rate product to lock in current rates. Ensure rent can absorb at least a 2% rate rise.',
        })
    elif stressed_cashflow < 0:
        flags.append({
            'id': 'rate_risk',
            'name': 'Interest Rate Risk',
            'severity': 'MEDIUM',
            'color': 'amber',
            'icon': 'trending-up',
            'description': (
                f"At +3% stressed rate ({stressed_rate:.1f}%), cashflow turns negative (£{stressed_cashflow:,.0f}/mo). "
                "Lenders typically stress-test at current rate +3%."
            ),
            'mitigation': 'Fix the mortgage rate for 2-5 years. Negotiate a higher rent or reduce purchase price to create headroom.',
        })

    # ── 3. Yield Compression Risk ─────────────────────────────────────────────
    if gross_yield < 4.5:
        flags.append({
            'id': 'yield_compression',
            'name': 'Yield Compression',
            'severity': 'HIGH',
            'color': 'red',
            'icon': 'trending-down',
            'description': (
                f"Gross yield of {gross_yield:.1f}% is well below the 5%+ minimum investors typically require. "
                "In a rising-rate environment, low-yield property is the first to see demand fall."
            ),
            'mitigation': 'Renegotiate the purchase price, explore HMO/R2SA conversion, or target higher-yielding areas.',
        })
    elif gross_yield < 5.5:
        flags.append({
            'id': 'yield_compression',
            'name': 'Yield Compression',
            'severity': 'MEDIUM',
            'color': 'amber',
            'icon': 'trending-down',
            'description': (
                f"Gross yield of {gross_yield:.1f}% is below the preferred 6% threshold. "
                "Any drop in rent or rise in costs will quickly erode profitability."
            ),
            'mitigation': 'Achieve maximum achievable rent. Consider furnished lettings to justify a premium.',
        })

    # ── 4. Cash Flow Cliff ────────────────────────────────────────────────────
    if monthly_cashflow < 0:
        flags.append({
            'id': 'cashflow_cliff',
            'name': 'Cash Flow Cliff',
            'severity': 'HIGH',
            'color': 'red',
            'icon': 'dollar-sign',
            'description': (
                f"Monthly cashflow is negative (£{monthly_cashflow:,.0f}/mo). "
                "You will be topping up from personal income every month. "
                "Any void period or unexpected repair will compound this loss."
            ),
            'mitigation': 'Do not proceed without a minimum 6-month cash reserve (£5,000+). Re-examine the purchase price and financing structure.',
        })
    elif monthly_cashflow < 100:
        flags.append({
            'id': 'cashflow_cliff',
            'name': 'Cash Flow Cliff',
            'severity': 'HIGH',
            'color': 'red',
            'icon': 'dollar-sign',
            'description': (
                f"Cashflow of £{monthly_cashflow:,.0f}/mo provides virtually no buffer. "
                "A single void month or boiler replacement will wipe out 6+ months of profit."
            ),
            'mitigation': 'Target at least £200/mo cashflow. Consider interest-only mortgage if not already used, or negotiate a lower purchase price.',
        })
    elif monthly_cashflow < 200:
        flags.append({
            'id': 'cashflow_cliff',
            'name': 'Cash Flow Cliff',
            'severity': 'MEDIUM',
            'color': 'amber',
            'icon': 'dollar-sign',
            'description': (
                f"Cashflow of £{monthly_cashflow:,.0f}/mo is thin. "
                "Void periods, rent arrears, or maintenance could make this deal loss-making."
            ),
            'mitigation': 'Maintain a £3,000 cash reserve per property. Review management fee and maintenance budget assumptions.',
        })

    # ── 5. Void / Vacancy Risk ────────────────────────────────────────────────
    if monthly_rent > 0:
        void_break_even_weeks = (monthly_cashflow / (monthly_rent / 4.33)) if monthly_cashflow > 0 else 0
    else:
        void_break_even_weeks = 0

    if monthly_cashflow > 0 and void_break_even_weeks < 3:
        flags.append({
            'id': 'void_risk',
            'name': 'Void Period Vulnerability',
            'severity': 'HIGH',
            'color': 'red',
            'icon': 'home',
            'description': (
                f"Just {void_break_even_weeks:.1f} weeks of void will wipe out a full month's profit. "
                "National average void period is 3-4 weeks per year."
            ),
            'mitigation': 'Price rent competitively to minimise voids. Use a tenant find agent to fill quickly. Hold a maintenance float.',
        })

    # ── 6. Article 4 / Planning Risk ─────────────────────────────────────────
    if article_4_active and deal_type == 'HMO':
        flags.append({
            'id': 'planning_risk',
            'name': 'Article 4 Planning Risk',
            'severity': 'HIGH',
            'color': 'red',
            'icon': 'file-text',
            'description': (
                "This area has an Article 4 Direction — converting to HMO requires Full Planning Permission. "
                "Many councils in Article 4 zones routinely refuse HMO applications. "
                "There is no guarantee of approval."
            ),
            'mitigation': 'Consult the local planning authority before purchasing. Consider C3→C3b social/supported housing as a compliant alternative.',
        })

    # ── 7. BRR Equity Risk ────────────────────────────────────────────────────
    if deal_type == 'BRR' and brr_metrics:
        money_left_in = brr_metrics.get('money_left_in', 0)
        brr_roi = brr_metrics.get('brr_roi', 0)
        if money_left_in > 50000:
            flags.append({
                'id': 'brr_equity_risk',
                'name': 'BRR Capital Trap',
                'severity': 'HIGH',
                'color': 'red',
                'icon': 'lock',
                'description': (
                    f"£{money_left_in:,.0f} remains trapped in the property post-refinance. "
                    "The BRR model requires recycling most of your capital to work effectively."
                ),
                'mitigation': 'Negotiate a lower purchase price, increase the refurb scope to lift GDV, or refinance to a higher LTV product.',
            })
        elif money_left_in > 20000:
            flags.append({
                'id': 'brr_equity_risk',
                'name': 'BRR Capital Trap',
                'severity': 'MEDIUM',
                'color': 'amber',
                'icon': 'lock',
                'description': (
                    f"£{money_left_in:,.0f} will remain in the deal post-refinance, limiting your ability to recycle capital quickly."
                ),
                'mitigation': 'Target a GDV that enables a 75% LTV refinance to fully recycle your investment.',
            })

    # ── 8. Flip Profit Margin Risk ────────────────────────────────────────────
    if deal_type == 'FLIP' and flip_metrics:
        profit = flip_metrics.get('profit', 0)
        flip_roi = flip_metrics.get('flip_roi', 0)
        if profit < 15000:
            flags.append({
                'id': 'flip_margin_risk',
                'name': 'Thin Flip Margin',
                'severity': 'HIGH',
                'color': 'red',
                'icon': 'scissors',
                'description': (
                    f"Projected flip profit of £{profit:,.0f} ({flip_roi:.1f}% ROI) is dangerously thin. "
                    "Any refurb overrun, extended holding period, or price negotiation from buyer will erode this."
                ),
                'mitigation': 'Require minimum 20% ROI and £20,000 profit before committing. Renegotiate purchase price or walk away.',
            })
        elif profit < 25000:
            flags.append({
                'id': 'flip_margin_risk',
                'name': 'Flip Margin Pressure',
                'severity': 'MEDIUM',
                'color': 'amber',
                'icon': 'scissors',
                'description': (
                    f"Flip profit of £{profit:,.0f} ({flip_roi:.1f}% ROI) is below the recommended 20%+ threshold. "
                    "Factor in a 10-15% refurb contingency."
                ),
                'mitigation': 'Add a 15% contingency to all refurb estimates. Consider selling off-market to avoid agent fees.',
            })

    # ── 9. R2SA Subletting Consent Risk ──────────────────────────────────────
    if deal_type == 'R2SA':
        flags.append({
            'id': 'r2sa_consent_risk',
            'name': 'Subletting Consent Risk',
            'severity': 'HIGH',
            'color': 'red',
            'icon': 'key',
            'description': (
                "R2SA requires explicit written consent from the freeholder/landlord AND the mortgage lender "
                "to sublet as short-term accommodation. Many standard AST contracts and BTL mortgages prohibit this."
            ),
            'mitigation': 'Obtain written consent from landlord and lender before signing. Use a specialist R2SA lease clause and check local council short-term let regulations.',
        })

    # ── 10. Low Cash-on-Cash Return ───────────────────────────────────────────
    if cash_on_cash < 4 and deal_type not in ('FLIP', 'R2SA', 'BRR'):
        flags.append({
            'id': 'low_coc',
            'name': 'Low Cash-on-Cash Return',
            'severity': 'MEDIUM' if cash_on_cash >= 2 else 'HIGH',
            'color': 'amber' if cash_on_cash >= 2 else 'red',
            'icon': 'percent',
            'description': (
                f"Cash-on-cash return of {cash_on_cash:.1f}% is below the 8% investor benchmark. "
                "Your capital is earning less than it could in a savings account or REIT."
            ),
            'mitigation': 'Compare against alternative investments. A 6-8% cash-on-cash return is typically the minimum to justify the illiquidity of property.',
        })

    # ── Sort: HIGH first, then MEDIUM, then LOW ───────────────────────────────
    severity_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
    flags.sort(key=lambda f: severity_order.get(f['severity'], 3))

    return flags


def generate_pdf_report(results):
    """Generate professional PDF report"""
    
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 40px;
                color: #333;
                line-height: 1.6;
            }
            .header {
                background: #1B1F3B;
                color: white;
                padding: 30px;
                text-align: center;
                margin-bottom: 30px;
            }
            .header h1 {
                margin: 0;
                font-size: 28px;
            }
            .header p {
                margin: 10px 0 0 0;
                opacity: 0.9;
            }
            .gold-line {
                background: #D4AF37;
                height: 5px;
                margin-bottom: 30px;
            }
            .verdict-box {
                padding: 30px;
                text-align: center;
                margin-bottom: 30px;
                border-radius: 10px;
            }
            .verdict-proceed { background: #d4edda; border: 3px solid #28a745; }
            .verdict-review { background: #fff3cd; border: 3px solid #ffc107; }
            .verdict-avoid { background: #f8d7da; border: 3px solid #dc3545; }
            .verdict-title {
                font-size: 36px;
                font-weight: bold;
                margin-bottom: 10px;
            }
            .metrics {
                display: flex;
                justify-content: space-between;
                margin-bottom: 30px;
            }
            .metric-card {
                border: 2px solid #D4AF37;
                padding: 20px;
                text-align: center;
                width: 22%;
                border-radius: 8px;
            }
            .metric-label {
                font-size: 11px;
                color: #666;
                text-transform: uppercase;
                margin-bottom: 8px;
            }
            .metric-value {
                font-size: 24px;
                font-weight: bold;
                color: #1B1F3B;
            }
            .section {
                margin-bottom: 30px;
            }
            .section h2 {
                color: #1B1F3B;
                border-bottom: 2px solid #D4AF37;
                padding-bottom: 10px;
                margin-bottom: 20px;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 20px;
            }
            th, td {
                padding: 10px;
                text-align: left;
                border-bottom: 1px solid #ddd;
            }
            th {
                background: #f5f5f5;
                font-weight: bold;
            }
            .total-row {
                font-weight: bold;
                background: #f0f0f0;
            }
            ul {
                padding-left: 20px;
            }
            li {
                margin-bottom: 8px;
            }
            .footer {
                background: #1B1F3B;
                color: white;
                text-align: center;
                padding: 15px;
                margin-top: 40px;
                font-size: 12px;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>{{ deal_type }} Investment Analysis</h1>
            <p>{{ address }}</p>
        </div>
        <div class="gold-line"></div>
        
        <div class="verdict-box verdict-{{ verdict_class }}">
            <div class="verdict-title" style="color: {{ verdict_color }}">{{ verdict }}</div>
            <p>Investment Recommendation</p>
        </div>
        
        <div class="metrics">
            <div class="metric-card">
                <div class="metric-label">Gross Yield</div>
                <div class="metric-value">{{ gross_yield }}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Monthly Cashflow</div>
                <div class="metric-value">£{{ monthly_cashflow }}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Cash-on-Cash</div>
                <div class="metric-value">{{ cash_on_cash }}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Risk Level</div>
                <div class="metric-value">{{ risk_level }}</div>
            </div>
        </div>
        
        <div class="section">
            <h2>AI Deal Score</h2>
            <div style="text-align: center; padding: 20px; background: #f8f9fa; border-radius: 10px; margin-bottom: 20px;">
                <div style="font-size: 72px; font-weight: bold; color: {{ score_color }};">{{ deal_score }}</div>
                <div style="font-size: 24px; color: #666;">out of 100</div>
                <div style="font-size: 18px; color: {{ score_color }}; margin-top: 10px;">{{ deal_score_label }}</div>
            </div>
        </div>
        
        <div class="section">
            <h2>5-Year Projection</h2>
            <table>
                <tr>
                    <th>Year</th>
                    <th>Annual Rent</th>
                    <th>Annual Net</th>
                    <th>Cumulative Cashflow</th>
                    <th>Property Value</th>
                    <th>Total Return</th>
                </tr>
                {% for year_data in five_year_projection %}
                <tr>
                    <td>Year {{ year_data.year }}</td>
                    <td>£{{ "{:,.0f}".format(year_data.annual_rent) }}</td>
                    <td>£{{ "{:,.0f}".format(year_data.annual_net) }}</td>
                    <td>£{{ "{:,.0f}".format(year_data.cumulative_cashflow) }}</td>
                    <td>£{{ "{:,.0f}".format(year_data.property_value) }}</td>
                    <td>£{{ "{:,.0f}".format(year_data.total_return) }}</td>
                </tr>
                {% endfor %}
            </table>
            <p style="font-size: 12px; color: #666; margin-top: 10px;">
                <strong>Assumptions:</strong> 3% annual rent growth, 4% annual capital growth. 
                Projections are estimates only and not guaranteed.
            </p>
        </div>
        
        <div class="section">
            <h2>Financial Summary</h2>
            <table>
                <tr>
                    <td>Purchase Price</td>
                    <td>£{{ purchase_price }}</td>
                </tr>
                <tr>
                    <td>Stamp Duty</td>
                    <td>£{{ stamp_duty }}</td>
                </tr>
                <tr>
                    <td>Legal Fees</td>
                    <td>£1,500</td>
                </tr>
                <tr>
                    <td>Valuation Fee</td>
                    <td>£500</td>
                </tr>
                <tr>
                    <td>Arrangement Fee</td>
                    <td>£1,995</td>
                </tr>
                <tr class="total-row">
                    <td>Total Purchase Costs</td>
                    <td>£{{ total_purchase_costs }}</td>
                </tr>
            </table>
            
            <h3>Financing</h3>
            <table>
                <tr>
                    <td>Deposit ({{ deposit_pct }}%)</td>
                    <td>£{{ deposit_amount }}</td>
                </tr>
                <tr>
                    <td>Loan Amount</td>
                    <td>£{{ loan_amount }}</td>
                </tr>
                <tr>
                    <td>Interest Rate</td>
                    <td>{{ interest_rate }}%</td>
                </tr>
                <tr>
                    <td>Monthly Mortgage</td>
                    <td>£{{ monthly_mortgage }}</td>
                </tr>
            </table>
            
            <h3>Annual Returns</h3>
            <table>
                <tr>
                    <td>Annual Rent</td>
                    <td>£{{ annual_rent }}</td>
                </tr>
                <tr>
                    <td>Total Expenses</td>
                    <td>£{{ total_annual_expenses }}</td>
                </tr>
                <tr class="total-row">
                    <td>Net Annual Income</td>
                    <td>£{{ net_annual_income }}</td>
                </tr>
            </table>
        </div>
        
        <div class="section">
            <h2>Investment Analysis</h2>
            
            <h3>Strengths</h3>
            <ul>
                {% for strength in strengths %}
                <li>{{ strength }}</li>
                {% endfor %}
            </ul>
            
            <h3>Weaknesses</h3>
            <ul>
                {% for weakness in weaknesses %}
                <li>{{ weakness }}</li>
                {% endfor %}
            </ul>
        </div>
        
        <div class="section">
            <h2>Recommended Next Steps</h2>
            <ul>
                {% for step in next_steps %}
                <li>{{ step }}</li>
                {% endfor %}
            </ul>
        </div>
        
        <div class="footer">
            Metusa Property | Deal Analysis Report | Generated: {{ analysis_date }}
        </div>
    </body>
    </html>
    """
    
    template = Template(html_template)
    
    # Determine verdict styling
    verdict_colors = {
        'PROCEED': '#28a745',
        'REVIEW': '#ffc107',
        'AVOID': '#dc3545'
    }
    verdict_classes = {
        'PROCEED': 'proceed',
        'REVIEW': 'review',
        'AVOID': 'avoid'
    }
    
    # Determine score color
    score = results.get('deal_score', 50)
    if score >= 80:
        score_color = '#28a745'  # Green
    elif score >= 65:
        score_color = '#17a2b8'  # Blue
    elif score >= 50:
        score_color = '#ffc107'  # Yellow
    else:
        score_color = '#dc3545'  # Red
    
    html_content = template.render(
        **results,
        verdict_color=verdict_colors.get(results['verdict'], '#333'),
        verdict_class=verdict_classes.get(results['verdict'], 'review'),
        score_color=score_color
    )
    
    # Generate PDF
    try:
        pdf = pdfkit.from_string(html_content, False, options=PDF_CONFIG)
        return pdf
    except Exception as e:
        print(f"PDF generation error: {e}")
        return None

@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')

@app.route('/analyze', methods=['GET'])
def analyze_page():
    """Serve the deal analysis page"""
    return render_template('analyze.html')

@app.route('/analyze', methods=['POST'])
@limiter.limit("10 per minute")  # Security: Rate limit analysis requests
def analyze():
    """API endpoint for deal analysis"""
    try:
        # Security: Check content type
        if not request.is_json:
            return jsonify({'success': False, 'message': 'Content-Type must be application/json'}), 400
        
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'success': False, 'message': 'Invalid JSON data'}), 400
        
        # Security: Validate required fields
        required = ['address', 'postcode', 'dealType', 'purchasePrice']
        for field in required:
            if field not in data:
                return jsonify({'success': False, 'message': f'Missing required field: {field}'}), 400
        
        # Estimate monthly rent if not provided (based on purchase price as proxy)
        if not data.get('monthlyRent') or data['monthlyRent'] == 0:
            # Rough estimate: 0.5% of purchase price per month
            data['monthlyRent'] = int(data['purchasePrice'] * 0.005)
            app.logger.info(f"Estimated monthly rent: £{data['monthlyRent']} for price £{data['purchasePrice']}")
        
        # Security: Check payload size
        if len(str(data)) > 10000:  # Max 10KB
            return jsonify({'success': False, 'message': 'Request too large'}), 413
        
        # Perform analysis
        results = analyze_deal(data)
        
        return jsonify({
            'success': True,
            'results': results
        })
    
    except ValueError as e:
        # Validation errors
        return jsonify({
            'success': False,
            'message': f'Validation error: {str(e)}'
        }), 400
    
    except Exception as e:
        # Log error but don't expose details to client
        app.logger.error(f'Analysis error: {str(e)}')
        return jsonify({
            'success': False,
            'message': 'An error occurred during analysis. Please try again.'
        }), 500

@app.route('/download-pdf', methods=['POST'])
@limiter.limit("5 per minute")  # Security: Stricter rate limit for PDF generation
def download_pdf():
    """Generate and download PDF report"""
    try:
        # Security: Check content type
        if not request.is_json:
            return jsonify({'success': False, 'message': 'Content-Type must be application/json'}), 400
        
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'success': False, 'message': 'Invalid JSON data'}), 400
        
        # Security: Check payload size
        if len(str(data)) > 10000:
            return jsonify({'success': False, 'message': 'Request too large'}), 413
        
        results = analyze_deal(data)
        
        pdf = generate_pdf_report(results)
        if pdf:
            # Security: Set secure headers for PDF download
            response = send_file(
                io.BytesIO(pdf),
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f"deal_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            )
            response.headers['X-Content-Type-Options'] = 'nosniff'
            return response
        else:
            return jsonify({'success': False, 'message': 'PDF generation failed'}), 500
    
    except ValueError as e:
        return jsonify({
            'success': False,
            'message': f'Validation error: {str(e)}'
        }), 400
    
    except Exception as e:
        app.logger.error(f'PDF generation error: {str(e)}')
        return jsonify({
            'success': False,
            'message': 'An error occurred generating the PDF. Please try again.'
        }), 500

@app.route('/api/health')
def health_check():
    """Health check endpoint — kept public for uptime monitoring, returns minimal info only."""
    return jsonify({'status': 'ok'})

@app.route('/api/test-jina')
@admin_required
def test_jina():
    """Test Jina Reader connectivity (admin only)."""
    try:
        resp = requests.get('https://r.jina.ai/', timeout=10)
        reachable = resp.status_code < 500
    except Exception as e:
        reachable = False
    return jsonify({
        'status': 'reachable' if reachable else 'unreachable',
        'service': 'Jina Reader (r.jina.ai)',
        'api_key_required': False,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/test-propertydata')
@admin_required
def test_propertydata():
    """Test PropertyData API configuration (admin only)."""
    env_key = os.environ.get('PROPERTY_DATA_API_KEY', '')
    module_key = property_data.api_key if hasattr(property_data, 'api_key') else 'N/A'
    
    # Detailed diagnostics (never expose full keys in responses)
    diagnostics = {
        'env_key_present': 'PROPERTY_DATA_API_KEY' in os.environ,
        'env_key_length': len(env_key),
        'env_key_preview': (env_key[:4] + '...' + env_key[-4:]) if len(env_key) > 8 else ('set' if env_key else 'not set'),
        'module_key_length': len(module_key) if module_key else 0,
        'keys_match': env_key == module_key,
    }
    
    # Quick test of the API
    test_result = None
    if env_key and len(env_key) > 20:
        try:
            import requests
            test_response = requests.get(
                'https://api.propertydata.co.uk/prices?postcode=M1+1AA&key=' + env_key,
                timeout=10
            )
            test_result = {
                'status': test_response.status_code,
                'ok': test_response.ok
            }
        except Exception as e:
            test_result = {'error': str(e)}
    else:
        test_result = {'skipped': 'Key too short or missing'}
    
    return jsonify({
        'diagnostics': diagnostics,
        'test_result': test_result,
        'timestamp': datetime.now().isoformat()
    })

# ── Admin Routes ──────────────────────────────────────────────────────────────

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page. Credentials set via ADMIN_USERNAME / ADMIN_PASSWORD env vars."""
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))

    error = None
    timeout = request.args.get('timeout') == '1'

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not ADMIN_PASSWORD_HASH:
            error = 'Admin not configured. Set ADMIN_USERNAME and ADMIN_PASSWORD environment variables.'
        elif username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session.clear()
            session['admin_logged_in'] = True
            session['admin_last_activity'] = datetime.utcnow().isoformat()
            session.permanent = True
            return redirect(url_for('admin_dashboard'))
        else:
            error = 'Invalid username or password.'

    return render_template('admin_login.html', error=error, timeout=timeout,
                           configured=bool(ADMIN_PASSWORD_HASH))


@app.route('/admin/logout')
def admin_logout():
    """Clear admin session."""
    session.clear()
    return redirect(url_for('admin_login'))


@app.route('/admin')
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """Admin dashboard — visit analytics, error log, system status."""
    return render_template('admin_dashboard.html',
                           username=ADMIN_USERNAME,
                           timeout_minutes=ADMIN_SESSION_TIMEOUT_MINUTES)


@app.route('/admin/api/stats')
@admin_required
def admin_stats():
    """JSON stats endpoint for dashboard live refresh."""
    now = datetime.utcnow()
    today = now.strftime('%Y-%m-%d')
    week_dates = [(now - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]

    with _analytics_lock:
        daily = dict(_analytics['daily_visits'])
        page_counts = dict(_analytics['page_counts'])
        api_counts = dict(_analytics['api_counts'])
        error_log = list(reversed(_analytics['error_log']))  # newest first
        recent = list(reversed(_analytics['recent_requests']))  # newest first
        total = _analytics['total_visits']
        start_time = _analytics['start_time']

    today_visits = daily.get(today, 0)
    week_visits = sum(daily.get(d, 0) for d in week_dates)

    # Chart data: last 7 days
    chart_labels = week_dates
    chart_data = [daily.get(d, 0) for d in week_dates]

    # Top pages & endpoints
    top_pages = sorted(page_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    top_apis = sorted(api_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    # System status
    api_status = {
        'Anthropic AI': bool(os.environ.get('ANTHROPIC_API_KEY')),
        'PropertyData': bool(os.environ.get('PROPERTY_DATA_API_KEY')),
        'Stripe': bool(os.environ.get('STRIPE_SECRET_KEY')),
        'Supabase': bool(os.environ.get('SUPABASE_URL')),
        'Jina Reader': bool(os.environ.get('JINA_API_KEY')),
        'ScrapingBee': bool(os.environ.get('SCRAPINGBEE_API_KEY')),
        'Ideal Postcodes': bool(os.environ.get('IDEAL_POSTCODES_API_KEY')),
        'EPC API': bool(os.environ.get('EPC_API_EMAIL')),
        'TfL API': True,  # has public defaults
        'Land Registry': True,  # public API, no key needed
    }

    uptime_seconds = (now - datetime.fromisoformat(start_time)).total_seconds()
    uptime_str = f"{int(uptime_seconds // 3600)}h {int((uptime_seconds % 3600) // 60)}m"

    return jsonify({
        'total_visits': total,
        'today_visits': today_visits,
        'week_visits': week_visits,
        'chart_labels': chart_labels,
        'chart_data': chart_data,
        'top_pages': top_pages,
        'top_apis': top_apis,
        'error_log': error_log[:20],
        'error_count': len(error_log),
        'recent_requests': recent[:20],
        'api_status': api_status,
        'uptime': uptime_str,
        'server_start': start_time,
        'timestamp': now.isoformat(),
    })


@app.route('/admin/api/report-error', methods=['POST'])
def report_client_error():
    """Receive client-side error reports from the frontend."""
    try:
        data = request.get_json(silent=True) or {}
        error_detail = {
            'message': escape(str(data.get('message', 'Unknown error'))[:500]),
            'source': escape(str(data.get('source', ''))[:200]),
            'lineno': data.get('lineno'),
            'colno': data.get('colno'),
            'stack': escape(str(data.get('stack', ''))[:1000]),
            'page': escape(str(data.get('page', request.referrer or ''))[:200]),
            'type': 'client',
        }
        _record_visit(
            path=data.get('page', '/unknown'),
            method='CLIENT_ERROR',
            status_code=0,
            is_error=True,
            error_detail=error_detail,
        )
        return jsonify({'ok': True}), 200
    except Exception:
        return jsonify({'ok': False}), 200  # Always 200 to client


# Security: Error handlers
@app.errorhandler(429)
def ratelimit_handler(e):
    """Handle rate limit exceeded"""
    return jsonify({
        'success': False,
        'message': 'Rate limit exceeded. Please slow down.'
    }), 429

@app.errorhandler(404)
def not_found_handler(e):
    """Handle 404 errors"""
    return jsonify({
        'success': False,
        'message': 'Endpoint not found'
    }), 404

@app.errorhandler(500)
def server_error_handler(e):
    """Handle 500 errors"""
    app.logger.error(f'Server error: {str(e)}')
    _record_visit(
        path=request.path,
        method=request.method,
        status_code=500,
        is_error=True,
        error_detail={'message': 'Internal server error', 'path': request.path, 'type': 'server'},
    )
    return jsonify({
        'success': False,
        'message': 'Internal server error. Please try again later.'
    }), 500

# ============================================================================
# URL EXTRACTION & AI ANALYSIS ENDPOINTS
# ============================================================================

# NOTE: This function is DEPRECATED - using adaptive_scraper.extract_property_from_url instead
# Keeping for reference but imported version from adaptive_scraper.py is used
def _extract_property_from_url_old(url):
    """
    [DEPRECATED] Old extraction method - see adaptive_scraper.py for current implementation
    Extract property details from a URL using web scraping
    Supports: Rightmove, Zoopla, OnTheMarket
    Uses multiple extraction methods for robustness
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-GB,en;q=0.5',
            'Referer': 'https://www.google.com/'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        html = response.text
        text = re.sub(r'<[^>]+>', ' ', html)  # Strip HTML tags
        text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
        
        data = {
            'address': None,
            'postcode': None,
            'price': None,
            'property_type': None,
            'bedrooms': None,
            'description': None
        }
        
        # Universal extraction methods (work for all sites)
        
        # 1. Extract price - look for £ patterns
        price_patterns = [
            r'£([0-9,]+)',
            r'&pound;([0-9,]+)',
            r'Guide Price[\s:]*£([0-9,]+)',
            r'Offers in Excess of[\s:]*£([0-9,]+)',
            r'Asking Price[\s:]*£([0-9,]+)'
        ]
        for pattern in price_patterns:
            price_match = re.search(pattern, html, re.IGNORECASE)
            if price_match:
                price_str = price_match.group(1).replace(',', '')
                try:
                    data['price'] = int(price_str)
                    break
                except ValueError:
                    continue
        
        # 2. Extract postcode - UK postcode regex
        # Rightmove includes fake postcodes, so we need to be smart about this
        all_postcodes = re.findall(r'([A-Z]{1,2}[0-9][A-Z0-9]?\s?[0-9][A-Z]{2})', html)
        
        if all_postcodes:
            # Filter for likely real postcodes (not random strings)
            # UK postcodes don't have certain patterns like I, Q, V, X, Z in certain positions
            valid_postcodes = []
            for pc in set(all_postcodes):
                # Basic validation - UK postcodes follow specific patterns
                # Remove spaces for validation
                pc_clean = pc.replace(' ', '')
                if len(pc_clean) >= 5 and len(pc_clean) <= 7:
                    # Check first letter is valid (not Q, V, X, Z)
                    if pc_clean[0] not in 'QVXZ':
                        valid_postcodes.append(pc)
            
            # If we have the address area (e.g., "Whitefield, M45"), try to match
            if data.get('address'):
                area_match = re.search(r'([A-Z]{1,2}[0-9]{1,2})', data['address'])
                if area_match:
                    area_code = area_match.group(1)
                    # Find postcode that starts with this area
                    for pc in valid_postcodes:
                        if pc.replace(' ', '').startswith(area_code):
                            data['postcode'] = pc
                            break
            
            # If still no postcode, use the first valid one
            if not data['postcode'] and valid_postcodes:
                data['postcode'] = valid_postcodes[0]
        
        # 3. Extract bedrooms - look for bedroom patterns
        bedroom_patterns = [
            r'(\d+)\s*bedroom',
            r'(\d+)\s*bed',
            r'(\d+)\s*br',
            r'(\d+)\s*beds'
        ]
        for pattern in bedroom_patterns:
            bed_match = re.search(pattern, text, re.IGNORECASE)
            if bed_match:
                try:
                    data['bedrooms'] = int(bed_match.group(1))
                    break
                except ValueError:
                    continue
        
        # 4. Extract property type
        property_types = [
            'detached', 'semi-detached', 'semi', 'terraced', 'end terrace',
            'flat', 'apartment', 'studio', 'bungalow', 'maisonette',
            'townhouse', 'cottage', 'link-detached'
        ]
        for ptype in property_types:
            if re.search(r'\b' + ptype + r'\b', text, re.IGNORECASE):
                # Normalize 'semi' to 'semi-detached'
                if ptype == 'semi':
                    data['property_type'] = 'Semi-Detached'
                else:
                    data['property_type'] = ptype.title()
                break
        
        # Site-specific extraction (for better accuracy)
        
        # OnTheMarket: Extract address from meta description
        if 'onthemarket.com' in url:
            meta_desc = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"', html, re.IGNORECASE)
            if meta_desc:
                desc = meta_desc.group(1)
                # Look for "for sale in [ADDRESS]"
                addr_match = re.search(r'for sale in ([^,]+(?:Road|Street|Lane|Avenue|Drive|Close)[^,]*(?:,\s*[^,]+)?)', desc, re.IGNORECASE)
                if addr_match:
                    data['address'] = addr_match.group(1).strip()
                    # Try to extract postcode from this address
                    pc_in_addr = re.search(r'([A-Z]{1,2}[0-9][A-Z0-9]?\s?[0-9][A-Z]{2})', data['address'])
                    if pc_in_addr:
                        data['postcode'] = pc_in_addr.group(1)
        
        elif 'rightmove.co.uk' in url:
            # Rightmove specific - look for address patterns
            # Try to find street address
            address_patterns = [
                r'for sale in ([^,]+(?:Road|Street|Lane|Avenue|Drive|Close|Way|Place|Court|Gardens|Terrace)[^,]*)',
                r'property for sale[\s:]+([^£<]+)',
                r'<title>(.*?)(?:for sale|Rightmove)',
            ]
            for pattern in address_patterns:
                addr_match = re.search(pattern, html, re.IGNORECASE)
                if addr_match:
                    potential_addr = addr_match.group(1).strip()
                    # Clean up
                    potential_addr = re.sub(r'\s+', ' ', potential_addr)
                    potential_addr = potential_addr.replace(' - Rightmove', '').replace(' | Rightmove', '')
                    if len(potential_addr) > 10:
                        data['address'] = potential_addr
                        break
            
            # If no address found, build from components
            if not data['address'] and data['postcode']:
                # Try to extract street from text
                street_match = re.search(r'([0-9]+[^,]{5,50}(?:Road|Street|Lane|Avenue|Drive|Close|Way))', text)
                if street_match:
                    data['address'] = street_match.group(1).strip()
        
        elif 'zoopla.co.uk' in url:
            # Zoopla specific
            zoopla_address = re.search(r'<title>(.*?)\s*-\s*Zoopla', html, re.IGNORECASE)
            if zoopla_address:
                data['address'] = zoopla_address.group(1).strip()
        
        elif 'onthemarket.com' in url:
            # OnTheMarket specific - try meta description first (has full address)
            meta_match = re.search(r'<meta[^>]*name="description"[^>]*content="[^"]*for sale in ([^"]+)"', html, re.IGNORECASE)
            if meta_match:
                addr = meta_match.group(1)
                # Clean up - remove estate agent name and stop at reasonable length
                addr = re.sub(r'^.*?present this \d+ bedroom ', '', addr)
                addr = re.sub(r'\s+\d+ bedroom.*$', '', addr)
                addr = re.sub(r'\s+for sale.*$', '', addr)
                addr = addr.strip()
                if len(addr) > 10:
                    data['address'] = addr
                    # Try to extract full postcode from address
                    # OnTheMarket sometimes has partial postcode (e.g., "M23" instead of "M23 0GP")
                    full_postcode = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\s+\d[A-Z]{2})', addr)
                    if full_postcode and not data.get('postcode'):
                        data['postcode'] = full_postcode.group(1)
            
            # Fallback to title
            if not data['address']:
                otm_title = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
                if otm_title:
                    title = otm_title.group(1)
                    sale_match = re.search(r'for sale in (.+)', title, re.IGNORECASE)
                    if sale_match:
                        addr = sale_match.group(1)
                        addr = re.sub(r',\s*[A-Z]{1,2}[0-9].*$', '', addr)
                        data['address'] = addr.strip()
        
        # Fallback: if we have postcode but no address, try to build address
        if not data['address'] and data['postcode']:
            # Look for any text that might be an address near the postcode
            # This is a last resort
            pass
        
        return data
        
    except Exception as e:
        app.logger.error(f'URL extraction error: {str(e)}')
        return {
            'address': None,
            'postcode': None,
            'price': None,
            'property_type': None,
            'bedrooms': None,
            'description': None
        }
        return None

@app.route('/extract-url', methods=['POST'])
@limiter.limit("10 per minute")
def extract_url():
    """Extract property data from a URL"""
    try:
        if not request.is_json:
            return jsonify({'success': False, 'message': 'Content-Type must be application/json'}), 400
        
        data = request.get_json(silent=True)
        if not data or 'url' not in data:
            return jsonify({'success': False, 'message': 'URL is required'}), 400
        
        url = data['url']
        
        # Validate URL
        if not url.startswith(('http://', 'https://')):
            return jsonify({'success': False, 'message': 'Invalid URL format'}), 400
        
        # Run Jina, Firecrawl, and basic scraper in parallel.
        print("[extract-url] Running Jina + Firecrawl + basic scraper in parallel...")
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _has_data(d):
            if not d:
                return False
            addr = d.get('address')
            return bool(d.get('price') or (addr and addr != 'Address not available'))

        with ThreadPoolExecutor(max_workers=3) as pool:
            jina_future      = pool.submit(scrape_with_jina, url)
            firecrawl_future = pool.submit(scrape_with_firecrawl, url)
            basic_future     = pool.submit(extract_property_from_url, url)

            jina_result      = None
            firecrawl_result = None
            basic_result     = None
            try:
                for future in as_completed([jina_future, firecrawl_future, basic_future], timeout=27):
                    result = future.result()
                    if future is jina_future:
                        jina_result = result
                        print(f"[extract-url] Jina finished, has_data={_has_data(result)}")
                    elif future is firecrawl_future:
                        firecrawl_result = result
                        print(f"[extract-url] Firecrawl finished, has_data={_has_data(result)}")
                    else:
                        basic_result = result
                        print(f"[extract-url] Basic scraper finished, has_data={_has_data(result)}")
            except Exception:
                pass

            # Priority: Jina > Firecrawl > basic scraper.
            # API scraper fields take precedence over basic HTML parse.
            def _merge(api_result, base_result):
                return {**base_result, **{
                    k: v for k, v in api_result.items() if v not in (None, '', 'Address not available')
                }}

            if _has_data(jina_result):
                extracted_data = _merge(jina_result, basic_result) if _has_data(basic_result) else jina_result
                print("[extract-url] Using Jina result" + (" (merged with basic)" if _has_data(basic_result) else ""))
            elif _has_data(firecrawl_result):
                extracted_data = _merge(firecrawl_result, basic_result) if _has_data(basic_result) else firecrawl_result
                print("[extract-url] Using Firecrawl result" + (" (merged with basic)" if _has_data(basic_result) else ""))
            elif _has_data(basic_result):
                extracted_data = basic_result
                print("[extract-url] Using basic scraper result only")
            else:
                extracted_data = None

        if extracted_data and _has_data(extracted_data):
            # Always validate / fill postcode via Ideal Postcodes PAF lookup.
            # Uses the scraped address string as the query so we get a confirmed
            # Royal Mail postcode regardless of what the scraper pulled from the
            # listing HTML (handles abbreviations, missing postcodes, etc.).
            address_for_lookup = extracted_data.get('address') or ''
            if address_for_lookup and address_for_lookup != 'Address not available':
                resolved = resolve_postcode_from_address(address_for_lookup)
                if resolved:
                    extracted_data['postcode'] = resolved
                    print(f"[extract-url] Postcode set to {resolved} via Ideal Postcodes")

            return jsonify({
                'success': True,
                'data': extracted_data,
                'message': 'Data extracted successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Could not extract data from this URL. Please enter details manually.'
            }), 400
            
    except Exception as e:
        app.logger.error(f'Extract URL error: {str(e)}')
        return jsonify({
            'success': False,
            'message': 'Error extracting data from URL'
        }), 500

@app.route('/epc-lookup', methods=['POST'])
@limiter.limit("20 per minute")
def epc_lookup():
    """Look up floor area for a property from the UK EPC Open Data API."""
    try:
        if not request.is_json:
            return jsonify({'success': False, 'message': 'Content-Type must be application/json'}), 400
        data = request.get_json(silent=True) or {}
        address  = sanitize_input(data.get('address', ''), 200)
        postcode = sanitize_input(data.get('postcode', ''), 20)
        if not address and not postcode:
            return jsonify({'success': False, 'message': 'Address or postcode required'}), 400
        floor_area = get_floor_area_from_epc(address, postcode)
        if floor_area:
            return jsonify({'success': True, 'sqm': floor_area})
        return jsonify({'success': False, 'message': 'Floor area not found in EPC register'})
    except Exception as e:
        app.logger.error(f'EPC lookup error: {str(e)}')
        return jsonify({'success': False, 'message': 'EPC lookup failed'}), 500


def get_ai_property_analysis(property_data, calculated_metrics, market_data=None):
    """
    Get AI-powered property deal analysis using Claude (Anthropic).
    Falls back to a rule-based summary if ANTHROPIC_API_KEY is not set.
    """
    def _n(val, default=0):
        """Safely coerce API values (which may be strings) to float."""
        try:
            return float(val) if val is not None else default
        except (TypeError, ValueError):
            return default

    try:
        # ------------------------------------------------------------------ #
        # Build market data context                                            #
        # ------------------------------------------------------------------ #
        market_context = ""
        if market_data and isinstance(market_data, dict):
            source = market_data.get('source', 'Unknown')

            if source == 'PropertyData API':
                estimated_rent    = _n(market_data.get('estimated_rent'))
                rental_confidence = market_data.get('rental_confidence')
                rental_range      = market_data.get('rental_range', {})
                demand_score      = _n(market_data.get('rental_demand_score'))
                price_growth      = market_data.get('price_growth_12m')
                avg_sold          = _n(market_data.get('avg_sold_price'))
                area_score        = _n(market_data.get('area_score'))
                transport_score   = _n(market_data.get('transport_score'))
                rent_comps        = market_data.get('rent_comparables', [])
                sold_comps        = market_data.get('comparable_sales', [])
                sales_val         = market_data.get('sales_valuation', {})

                market_context += f"\nMARKET DATA (PropertyData API - Professional Grade):"

                # Rental valuation
                if estimated_rent:
                    market_context += f"\n- Estimated Market Rent: £{estimated_rent:,.0f}/month (Confidence: {rental_confidence})"
                    if rental_range:
                        low_w  = _n(rental_range.get('low_weekly'))
                        high_w = _n(rental_range.get('high_weekly'))
                        if low_w and high_w:
                            market_context += f" | Range: £{round(low_w*52/12):,}-£{round(high_w*52/12):,}/mo"
                    if demand_score:
                        market_context += f"\n- Rental Demand Score: {demand_score}/10"
                    assumed_rent = _n(property_data.get('monthlyRent'))
                    if assumed_rent and estimated_rent:
                        diff_pct = ((assumed_rent - estimated_rent) / estimated_rent) * 100
                        if abs(diff_pct) > 15:
                            market_context += f"\n  ⚠ Assumed rent is {diff_pct:+.0f}% vs market estimate — verify with local agents"

                # Sales valuation (real house value)
                if sales_val and sales_val.get('estimate'):
                    sv_est  = _n(sales_val['estimate'])
                    sv_conf = sales_val.get('confidence', 'N/A')
                    if sv_est:
                        market_context += f"\n- PropertyData Sales Valuation: £{sv_est:,.0f} (Confidence: {sv_conf})"
                        pp = _n(property_data.get('purchasePrice'))
                        if pp and sv_est:
                            vs_val = ((pp - sv_est) / sv_est) * 100
                            tag = "BELOW" if vs_val < 0 else "ABOVE"
                            market_context += f" → purchase price is {abs(vs_val):.1f}% {tag} estimated value"

                # Price growth + average sold
                if price_growth is not None:
                    market_context += f"\n- 12-Month Price Growth: {_n(price_growth):.1f}%"
                if avg_sold:
                    market_context += f"\n- Average Sold Price: £{avg_sold:,.0f}"
                    pp = _n(property_data.get('purchasePrice'))
                    if pp and avg_sold:
                        vs_avg = ((pp - avg_sold) / avg_sold) * 100
                        market_context += f" (purchase price is {vs_avg:+.1f}% vs average sold)"

                # Area scores
                if area_score:
                    market_context += f"\n- Area Quality Score: {area_score}/10"
                if transport_score:
                    market_context += f"\n- Transport Links Score: {transport_score}/10"

                # Real rent comparables
                if rent_comps:
                    market_context += f"\n- Rental Comparables ({len(rent_comps)} nearby lettings used for estimate):"
                    for i, rc in enumerate(rent_comps[:5], 1):
                        mr   = _n(rc.get('monthly_rent'))
                        addr = rc.get('address', 'Nearby property')
                        date = rc.get('date', 'N/A')
                        dist = rc.get('distance_miles')
                        line = f"\n  {i}. {addr}: £{mr:,.0f}/mo" if mr else f"\n  {i}. {addr}"
                        if dist:
                            line += f" ({_n(dist):.1f} miles away)"
                        if date and date != 'N/A':
                            line += f" — {date}"
                        market_context += line

                # Real sold comparables
                if sold_comps:
                    market_context += f"\n- Sold Comparables ({len(sold_comps)} recent sales):"
                    for i, sc in enumerate(sold_comps[:5], 1):
                        market_context += (
                            f"\n  {i}. {sc.get('address', 'Nearby property')}: "
                            f"£{_n(sc.get('price', 0)):,.0f} — {sc.get('type', 'N/A')} "
                            f"({sc.get('bedrooms', '?')} bed) on {sc.get('date', 'N/A')}"
                        )

            elif source == 'Land Registry':
                avg_price    = _n(market_data.get('average_price'))
                trend        = market_data.get('price_trend', {})
                recent_sales = market_data.get('recent_sales', [])

                if avg_price:
                    market_context += f"\nMARKET DATA (Land Registry - Government Sold Prices):"
                    market_context += f"\n- Average Sold Price (12 months): £{avg_price:,.0f}"
                    pp = _n(property_data.get('purchasePrice'))
                    if pp and avg_price:
                        vs_avg = ((pp - avg_price) / avg_price) * 100
                        market_context += f" (purchase price is {vs_avg:+.1f}% vs average)"
                if trend:
                    market_context += f"\n- Price Trend: {trend.get('trend', 'stable')} ({_n(trend.get('change_percent')):.1f}% change)"
                if recent_sales:
                    market_context += "\n- Recent Comparable Sales:"
                    for i, sale in enumerate(recent_sales[:3], 1):
                        market_context += f"\n  {i}. £{_n(sale.get('price')):,.0f} on {str(sale.get('date', ''))[:10]} - {sale.get('street', 'N/A')}"
            else:
                market_context = "\nMARKET DATA: Limited data available for this postcode"

        if not market_context:
            market_context = "\nMARKET DATA: No external market data available — rely on local knowledge"

    except Exception as _ctx_err:
        app.logger.warning(f"[AI] Market context build failed ({_ctx_err}), proceeding without it")
        market_context = "\nMARKET DATA: Could not format market data — review calculated metrics above"

    # ------------------------------------------------------------------ #
    # Strategy-specific context                                            #
    # ------------------------------------------------------------------ #
    deal_type = property_data.get('dealType', 'BTL')
    strategy_context = ""
    if deal_type == 'BRR':
        brr = calculated_metrics.get('brr_metrics', {})
        if brr:
            strategy_context = f"""
BRR STRATEGY METRICS:
- Refurb Cost: £{brr.get('refurb_cost', 0):,}
- After Repair Value (ARV): £{brr.get('arv', 0):,}
- Money Left In: £{brr.get('money_left_in', 0):,}
- BRR ROI: {brr.get('brr_roi', 0):.1f}%
- Equity Released: £{brr.get('equity_released', 0):,}"""
    elif deal_type == 'FLIP':
        flip = calculated_metrics.get('flip_metrics', {})
        if flip:
            strategy_context = f"""
FLIP STRATEGY METRICS:
- Refurb Cost: £{flip.get('refurb_cost', 0):,}
- After Repair Value (ARV): £{flip.get('arv', 0):,}
- Projected Profit: £{flip.get('flip_profit', 0):,}
- Flip ROI: {flip.get('flip_roi', 0):.1f}%"""
    elif deal_type == 'HMO':
        _a4    = calculated_metrics.get('article_4', {})
        _is_a4 = _a4.get('is_article_4', False)
        _a4_kn = _a4.get('known', True)
        if _is_a4:
            _a4_line = (
                "⚠️ ARTICLE 4 IN FORCE: Planning Permission required for C3→C4 HMO conversion. "
                "Consider C3→C3b social/supported housing lease as an alternative (no PP needed)."
            )
        elif not _a4_kn:
            _a4_line = "Article 4 status UNCONFIRMED for this postcode — verify with local council before converting."
        else:
            _a4_line = (
                "No Article 4 — Permitted Development applies. "
                "Mandatory HMO Licence required for 5+ occupants (£500–1,500 fee, 5-year term)."
            )
        strategy_context = f"""
HMO STRATEGY:
- Room Count: {property_data.get('roomCount', 'N/A')}
- Avg Room Rate: £{property_data.get('avgRoomRate', 0)}/month
- Planning/Licensing: {_a4_line}"""
    elif deal_type == 'R2SA':
        r2sa = calculated_metrics.get('r2sa_metrics', {})
        if r2sa:
            strategy_context = f"""
RENT-TO-SA STRATEGY:
- Monthly Rent to Landlord: £{r2sa.get('monthly_rent_paid', 0):,}
- Monthly SA Revenue: £{r2sa.get('sa_monthly_revenue', 0):,}
- Monthly Operating Costs (cleaning/utilities/platform ~30%%): £{r2sa.get('monthly_op_costs', 0):,}
- Monthly Profit: £{r2sa.get('monthly_profit', 0):,}
- Setup/Furnishing Costs: £{r2sa.get('setup_costs', 0):,}
- ROI on Setup Costs: {r2sa.get('r2sa_roi', 0):.1f}%%
- Note: Investor rents from landlord and sublets as short-term SA (Airbnb/Booking.com). No purchase required."""

    # ------------------------------------------------------------------ #
    # Benchmarks for this deal type (to give Claude context)              #
    # ------------------------------------------------------------------ #
    benchmarks = {
        'BTL':  {'gross_yield': 6.0,  'cashflow': 200, 'coc': 8.0},
        'HMO':  {'gross_yield': 10.0, 'cashflow': 400, 'coc': 12.0},
        'BRR':  {'gross_yield': 6.0,  'cashflow': 200, 'coc': 8.0},
        'FLIP': {'gross_yield': 0,    'cashflow': 0,   'coc': 15.0},
        'R2SA': {'gross_yield': 0,    'cashflow': 500, 'coc': 50.0},
    }.get(deal_type, {'gross_yield': 6.0, 'cashflow': 200, 'coc': 8.0})

    # ------------------------------------------------------------------ #
    # Article 4 planning context for the prompt                           #
    # ------------------------------------------------------------------ #
    _a4p      = calculated_metrics.get('article_4', {})
    _is_a4p   = _a4p.get('is_article_4', False)
    _a4p_kn   = _a4p.get('known', True)
    _a4p_note = _a4p.get('note', '')
    _a4p_cncl = _a4p.get('council', 'local council')

    if _is_a4p:
        planning_status = f"YES — Article 4 Direction IS in force ({_a4p_note}). HMO conversion (C3→C4) requires Full Planning Permission — not just a licence."
        planning_hmo_instruction = (
            "Because Article 4 IS in force: if the strategy is HMO, explain clearly that "
            "planning permission is required (PP fee ~£234 + architect/solicitor ~£1,500-3,000 total, outcome uncertain). "
            "Strongly suggest C3→C3b social/supported housing lease as the primary Article 4-compliant alternative "
            "(no planning needed, guaranteed LA rent £500-900/room/month, 3-7 year lease). "
            "Include this guidance in next_steps."
        )
    elif not _a4p_kn:
        planning_status = f"UNCONFIRMED — this postcode is not in our Article 4 database. Investor MUST verify with {_a4p_cncl} before converting to HMO."
        planning_hmo_instruction = (
            "Article 4 status is unconfirmed. Advise the investor to check with the local planning authority "
            "before any HMO conversion. Include this as the first next_step."
        )
    else:
        planning_status = f"NO — No Article 4 restrictions in force. Permitted Development applies for C3→C4 HMO conversion (up to 6 people)."
        if deal_type == 'HMO':
            planning_hmo_instruction = (
                "Because there is NO Article 4, explain the HMO licensing process in next_steps: "
                "Mandatory HMO Licence required for 5+ occupants — apply to local council, fee ~£500-1,500 (varies by council), "
                "valid 5 years. Property must meet HMO standards: fire doors (FD30s), interconnected smoke alarms, "
                "min room size 6.51 m² per person, adequate kitchen/bathroom facilities. "
                "Also advise checking for Additional or Selective Licensing in this area."
            )
        else:
            planning_hmo_instruction = (
                "No Article 4 — HMO is available as an alternative strategy if the investor changes approach."
            )

    # ------------------------------------------------------------------ #
    # Build the prompt                                                     #
    # ------------------------------------------------------------------ #
    prompt = f"""You are an expert UK property investment analyst specialising in buy-to-let, \
HMO, BRR, flip and rent-to-SA strategies. Analyse the deal below and return a JSON object.

== PROPERTY ==
Address:        {property_data.get('address', 'N/A')}
Postcode:       {property_data.get('postcode', 'N/A')}
Type:           {property_data.get('property_type', 'N/A')}
Bedrooms:       {property_data.get('bedrooms', 'N/A')}
Strategy:       {deal_type}
Purchase Price: £{property_data.get('purchasePrice', 0):,}
Monthly Rent:   £{property_data.get('monthlyRent', 0):,}

== CALCULATED METRICS ==
Gross Yield:        {calculated_metrics.get('gross_yield', 0)}%  (benchmark ≥ {benchmarks['gross_yield']}%)
Net Yield:          {calculated_metrics.get('net_yield', 0)}%
Monthly Cashflow:   £{calculated_metrics.get('monthly_cashflow', 0):,.0f}  (benchmark ≥ £{benchmarks['cashflow']}/mo)
Cash-on-Cash:       {calculated_metrics.get('cash_on_cash', 0)}%  (benchmark ≥ {benchmarks['coc']}%)
Annual Net Income:  £{calculated_metrics.get('net_annual_income', 0)}
Monthly Mortgage:   £{calculated_metrics.get('monthly_mortgage', 0)}
Deal Score:         {calculated_metrics.get('deal_score', 0)}/100
System Verdict:     {calculated_metrics.get('verdict', 'REVIEW')}
{strategy_context}
{market_context}

== PLANNING & ARTICLE 4 ==
Article 4 Direction: {planning_status}
Council:             {_a4p_cncl}
Instruction:         {planning_hmo_instruction}

== INSTRUCTIONS ==
Return ONLY a valid JSON object — no markdown, no code fences, no extra text.
Be specific: reference actual figures, the specific postcode/area, and the strategy.
Do NOT use generic filler. If a metric is weak, say so plainly.
The Article 4 planning data above is REAL — reference it accurately in your analysis.

JSON schema (use arrays — no HTML, no <br>, no bullet characters):
{{
  "verdict": "<2-3 sentences: clear overall assessment referencing key figures>",
  "strengths": ["<strength 1>", "<strength 2>", "<strength 3>", "<strength 4>"],
  "risks": ["<risk 1>", "<risk 2>", "<risk 3>", "<risk 4>"],
  "area": "<2-3 sentences: specific to the postcode — rental demand, tenant profile, comparable areas, growth prospects>",
  "next_steps": ["<step 1>", "<step 2>", "<step 3>", "<step 4>", "<step 5 — Article 4 / licensing if HMO>"]
}}"""

    # ------------------------------------------------------------------ #
    # Call Claude if API key is available                                  #
    # ------------------------------------------------------------------ #
    api_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            model_id = os.environ.get('ANTHROPIC_MODEL', 'claude-haiku-4-5-20251001')
            message = client.messages.create(
                model=model_id,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = message.content[0].text.strip()
            # Strip any accidental markdown fences
            if raw.startswith('```'):
                raw = re.sub(r'^```[a-z]*\n?', '', raw)
                raw = re.sub(r'\n?```$', '', raw)
            ai_response = json.loads(raw)
            app.logger.info(f"[AI] Claude analysis successful for {property_data.get('postcode', '?')}")
            return ai_response
        except json.JSONDecodeError as e:
            app.logger.error(f"[AI] Claude returned non-JSON: {e}")
        except Exception as e:
            app.logger.error(f"[AI] Claude API error: {e}")
    else:
        app.logger.warning("[AI] ANTHROPIC_API_KEY not set — using rule-based fallback")

    # ------------------------------------------------------------------ #
    # Rule-based fallback (no API key / API error)                        #
    # ------------------------------------------------------------------ #
    def _f(v, default=0.0):
        try: return float(v) if v is not None else default
        except (TypeError, ValueError): return default

    verdict    = calculated_metrics.get('verdict', 'REVIEW')
    score      = int(_f(calculated_metrics.get('deal_score', 50)))
    gross      = _f(calculated_metrics.get('gross_yield', 0))
    cashflow   = _f(calculated_metrics.get('monthly_cashflow', 0))
    coc        = _f(calculated_metrics.get('cash_on_cash', 0))
    postcode   = property_data.get('postcode', 'this area')

    # Article 4 fallback guidance
    _fb_a4     = calculated_metrics.get('article_4', {})
    _fb_is_a4  = _fb_a4.get('is_article_4', False)
    _fb_a4_kn  = _fb_a4.get('known', True)

    if deal_type == 'HMO':
        if _fb_is_a4:
            _a4_risk_line = (
                "• ⚠️ Article 4 Direction in force — planning permission required before converting to HMO (C4 use class)"
            )
            _a4_step = (
                "5. Article 4 is in force: obtain planning permission (£234 fee + ~£1,500-3,000 total) "
                "before converting to HMO — OR lease to a housing association as C3b social housing "
                "(no PP needed, guaranteed LA rent)"
            )
        elif not _fb_a4_kn:
            _a4_risk_line = "• Article 4 status unconfirmed — verify with local council before HMO conversion"
            _a4_step = "5. Verify Article 4 status with local planning authority before committing to HMO conversion"
        else:
            _a4_risk_line = "• Mandatory HMO Licence required for 5+ occupants — budget £500-1,500 fee (5-year term)"
            _a4_step = (
                "5. Apply for Mandatory HMO Licence (5+ occupants) from local council — "
                "fee £500-1,500, property must meet fire safety and room-size standards"
            )
    else:
        if _fb_is_a4:
            _a4_risk_line = "• Article 4 in force — if switching to HMO strategy, planning permission will be required"
            _a4_step = "5. Note: Article 4 applies — any future HMO conversion needs planning permission; consider C3b social housing as alternative"
        elif not _fb_a4_kn:
            _a4_risk_line = "• Article 4 status unconfirmed for this postcode — verify if considering HMO in future"
            _a4_step = "5. Confirm Article 4 status with local council if considering HMO as an alternative strategy"
        else:
            _a4_risk_line = "• No Article 4 — HMO conversion via Permitted Development is an option if numbers improve"
            _a4_step = "5. Consider HMO as an alternative strategy — no Article 4 barrier, just standard licensing required"

    if verdict == 'PROCEED':
        return {
            "verdict": (
                f"Strong deal scoring {score}/100. The gross yield of {gross:.1f}% beats the "
                f"{benchmarks['gross_yield']}% benchmark and monthly cashflow of £{cashflow:,.0f} "
                f"exceeds the £{benchmarks['cashflow']} target, supporting a PROCEED recommendation."
            ),
            "strengths": [
                f"Gross yield of {gross:.1f}% is above the {benchmarks['gross_yield']}% benchmark",
                f"Monthly cashflow of £{cashflow:,.0f} provides a meaningful financial buffer",
                f"Cash-on-cash return of {coc:.1f}% indicates efficient capital deployment",
                f"Deal score of {score}/100 meets investment criteria",
            ],
            "risks": [
                "Void periods and unexpected maintenance could erode cashflow",
                "Mortgage rate rises will compress net yield — stress-test at 6%+",
                "Verify advertised rent against local comparables before committing",
                _a4_risk_line.lstrip('• '),
            ],
            "area": (
                f"{postcode} shows sufficient rental demand to support the assumed rent. "
                "Verify tenant demand with local letting agents and check comparable listings."
            ),
            "next_steps": [
                "Confirm achievable rent with 2-3 local letting agents",
                "Arrange a viewing and independent RICS survey (£400-600)",
                "Obtain mortgage Decision in Principle at current rates",
                "Instruct a solicitor for preliminary searches",
                _a4_step.split('. ', 1)[-1] if '. ' in _a4_step else _a4_step,
            ],
        }
    elif verdict == 'REVIEW':
        if _fb_is_a4 and deal_type != 'HMO':
            _alt_strategy = "social housing C3b lease (Article 4 area — no planning needed)"
        elif not _fb_is_a4 and deal_type != 'HMO':
            _alt_strategy = "HMO or BRR"
        else:
            _alt_strategy = "BRR or social housing lease"
        return {
            "verdict": (
                f"Borderline deal scoring {score}/100. The yield of {gross:.1f}% and cashflow of "
                f"£{cashflow:,.0f}/month are below target benchmarks — further due diligence or "
                f"price negotiation is required before proceeding."
            ),
            "strengths": [
                "Property may have value-add potential through refurbishment or strategy change",
                "Some metrics are close to benchmark — a small price reduction could make it work",
                f"{postcode} may offer longer-term capital growth",
                f"Could work as {_alt_strategy} if current figures are marginal",
            ],
            "risks": [
                f"Gross yield of {gross:.1f}% is below the {benchmarks['gross_yield']}% minimum",
                f"Monthly cashflow of £{cashflow:,.0f} leaves little buffer for voids or repairs",
                "Overpaying vs comparable sales would worsen the position",
                _a4_risk_line.lstrip('• '),
            ],
            "area": (
                f"{postcode} warrants careful research — confirm rental demand and "
                "recent comparable sales before assuming the projected rent is achievable."
            ),
            "next_steps": [
                "Research 5+ comparable rentals and 5+ recent sold prices in the postcode",
                "Attempt to negotiate the purchase price down by 5-10%",
                f"Model the deal as {_alt_strategy} to check if alternative strategies work",
                "Get a local letting agent's written opinion on achievable rent",
                _a4_step.split('. ', 1)[-1] if '. ' in _a4_step else _a4_step,
            ],
        }
    else:
        return {
            "verdict": (
                f"Weak deal scoring {score}/100. Gross yield of {gross:.1f}% and cashflow of "
                f"£{cashflow:,.0f}/month are materially below target — this deal does not meet "
                "minimum investment criteria and should be avoided."
            ),
            "strengths": [
                "Physical asset provides some security",
                "May suit a different buyer profile (e.g. owner-occupier)",
                "Could be revisited if the purchase price drops significantly",
            ],
            "risks": [
                f"Gross yield of {gross:.1f}% is well below the {benchmarks['gross_yield']}% target",
                f"Cashflow of £{cashflow:,.0f}/month is insufficient — risk of negative cashflow",
                "Capital at risk if the market softens",
                _a4_risk_line.lstrip('• '),
            ],
            "area": (
                f"{postcode} may have good fundamentals but this specific deal is mispriced. "
                "Continue searching the same area for better-value stock."
            ),
            "next_steps": [
                "Do not proceed with this deal at the current asking price",
                "Calculate the maximum price that delivers a 6%+ gross yield",
                "Either submit a significantly lower offer or walk away",
                "Set Rightmove/Zoopla alerts for similar properties at lower prices",
                _a4_step.split('. ', 1)[-1] if '. ' in _a4_step else _a4_step,
            ],
        }

@app.route('/ai-analyze', methods=['POST'])
@limiter.limit("5 per minute")  # Lower limit for AI analysis
def ai_analyze():
    """
    Full AI-powered deal analysis
    1. Checks subscription gate (if REQUIRE_SUBSCRIPTION=true)
    2. Calculates all financial metrics
    3. Gets AI-enhanced insights
    4. Returns comprehensive analysis
    """
    try:
        if not request.is_json:
            return jsonify({'success': False, 'message': 'Content-Type must be application/json'}), 400

        data = request.get_json(silent=True)
        if not data:
            return jsonify({'success': False, 'message': 'Invalid JSON data'}), 400

        # ── Subscription gate ──────────────────────────────────────────────
        if os.environ.get('REQUIRE_SUBSCRIPTION', '').lower() == 'true':
            user_email = (
                request.headers.get('X-User-Email', '')
                or str(data.get('userEmail', ''))
            ).strip().lower()
            if not check_subscription(user_email):
                return jsonify({
                    'success': False,
                    'code': 'subscription_required',
                    'message': 'An active subscription is required to run analyses. Please upgrade your plan.',
                }), 403
        # ──────────────────────────────────────────────────────────────────
        
        # Validate required fields (only purchasePrice is truly required)
        if 'purchasePrice' not in data or data['purchasePrice'] is None or data['purchasePrice'] == '':
            return jsonify({'success': False, 'message': 'Missing required field: purchasePrice'}), 400
        
        # Set defaults for optional fields
        if not data.get('dealType') or data['dealType'] is None or data['dealType'] == '':
            data['dealType'] = 'BTL'  # Default to Buy-to-Let
        
        app.logger.info(f"[ai-analyze] Processing request with purchasePrice: {data.get('purchasePrice')}, dealType: {data.get('dealType')}")
        
        if not data.get('address') or data['address'] is None:
            data['address'] = 'Unknown Address'
        
        if not data.get('postcode') or data['postcode'] is None:
            # Try to extract postcode from address
            addr = data['address']
            postcode_match = re.search(r'([A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})', addr, re.IGNORECASE)
            if postcode_match:
                data['postcode'] = postcode_match.group(1).upper()
                app.logger.info(f"Extracted postcode from address: {data['postcode']}")
            else:
                data['postcode'] = 'N/A'
                app.logger.warning("No postcode provided - proceeding without market data")
        
        # Estimate monthly rent if not provided
        if not data.get('monthlyRent') or data['monthlyRent'] == 0:
            data['monthlyRent'] = int(data['purchasePrice'] * 0.005)
            app.logger.info(f"Estimated monthly rent: £{data['monthlyRent']}")
        
        # Step 1: Calculate financial metrics
        app.logger.info(f"[ai-analyze] Calling analyze_deal with data: {data}")
        calculated_metrics = analyze_deal(data)
        app.logger.info(f"[ai-analyze] analyze_deal completed successfully")
        
        # Step 2: Get market data (PropertyData primary, Land Registry fallback)
        postcode = data.get('postcode', '').strip().upper()
        bedrooms = int(data.get('bedrooms', 3) or 3)
        market_data = {}
        
        if postcode and validate_postcode(postcode):
            # Try PropertyData API first (premium data)
            if property_data.is_configured():
                try:
                    market_data = get_propertydata_context(postcode, bedrooms)
                    market_data['source'] = 'PropertyData API'
                    app.logger.info(f"Using PropertyData for {postcode}")
                except Exception as e:
                    app.logger.warning(f'PropertyData API failed: {e}')
                    market_data = {}
            
            # Fallback to Land Registry if PropertyData unavailable
            if not market_data or 'error' in market_data:
                try:
                    sold_prices = land_registry.get_sold_prices(postcode, limit=5)
                    price_trend = land_registry.get_price_trend(postcode)
                    avg_price = land_registry.get_average_price(postcode, months=12)
                    
                    # Add rent estimate so rent_comparables fallback has data
                    rent_est = _estimate_rent_from_land_registry(postcode, bedrooms)
                    market_data = {
                        'source': 'Land Registry',
                        'recent_sales': sold_prices,
                        'price_trend': price_trend,
                        'average_price': avg_price,
                        'estimated_rent': rent_est.get('estimated_monthly_rent') if rent_est else None,
                        'rental_confidence': 'Low'
                    }
                    app.logger.info(f"Using Land Registry for {postcode}")
                except Exception as e:
                    app.logger.warning(f'Could not fetch Land Registry data: {e}')
                    market_data = {'source': 'None', 'error': 'Market data unavailable'}
        
        # Step 3: Get AI insights (with market data)
        ai_insights = get_ai_property_analysis(data, calculated_metrics, market_data)

        # ------------------------------------------------------------------ #
        # SOLD COMPARABLES                                                     #
        # Priority: PropertyData real sales → Land Registry → empty           #
        # ------------------------------------------------------------------ #
        sold_comparables = market_data.get('comparable_sales', [])
        if not sold_comparables and market_data.get('recent_sales'):
            sold_comparables = [
                {
                    'address': f"{s.get('street', 'Similar property')}, {postcode}",
                    'price': s.get('price', 0),
                    'bedrooms': bedrooms,
                    'date': s.get('date', 'N/A'),
                    'type': data.get('property_type', 'House').title(),
                    'source': 'Land Registry'
                }
                for s in market_data['recent_sales'][:5]
                if s.get('price')
            ]

        # ------------------------------------------------------------------ #
        # RENT COMPARABLES                                                     #
        # Priority: PropertyData real lettings → market estimate → empty      #
        # ------------------------------------------------------------------ #
        rent_comparables = market_data.get('rent_comparables', [])
        if not rent_comparables and market_data.get('estimated_rent'):
            # We have a market estimate but no individual comparables
            src = market_data.get('source', 'Market estimate')
            rent_comparables = [
                {
                    'address': f"{bedrooms}-bed property, {postcode}",
                    'monthly_rent': market_data['estimated_rent'],
                    'bedrooms': bedrooms,
                    'source': src,
                    'confidence': market_data.get('rental_confidence', 'N/A')
                }
            ]

        # ------------------------------------------------------------------ #
        # HOUSE VALUATION                                                      #
        # Priority: PropertyData valuation → Land Registry avg → none        #
        # ------------------------------------------------------------------ #
        house_valuation = market_data.get('sales_valuation')
        if not house_valuation:
            avg_sold = market_data.get('avg_sold_price') or market_data.get('average_price')
            if avg_sold:
                house_valuation = {
                    'estimate': int(avg_sold),
                    'confidence': 'low',
                    'source': 'Land Registry area average',
                    'note': 'Based on recent sold prices in postcode area — not property-specific.'
                }
            else:
                house_valuation = {
                    'estimate': None,
                    'confidence': None,
                    'source': None,
                    'note': 'No external valuation available. Commission a RICS survey for an accurate figure.'
                }

        # Always attach the purchase price for vs-valuation comparison
        if house_valuation is not None:
            house_valuation['purchase_price'] = float(data.get('purchasePrice', 0))

        # Combine results
        results = {
            **calculated_metrics,
            'ai_verdict': ai_insights['verdict'],
            'ai_strengths': ai_insights['strengths'],
            'ai_risks': ai_insights['risks'],
            'ai_area': ai_insights['area'],
            'ai_next_steps': ai_insights['next_steps'],
            'sold_comparables': sold_comparables,
            'rent_comparables': rent_comparables,
            'house_valuation': house_valuation,
            'avg_sold_price': market_data.get('avg_sold_price'),
            'market_source': market_data.get('source', 'None')
        }
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'message': f'Validation error: {str(e)}'
        }), 400
    
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        app.logger.error(f'AI analysis error: {str(e)}')
        app.logger.error(f'AI analysis traceback: {error_trace}')
        return jsonify({
            'success': False,
            'message': f'An error occurred during AI analysis: {str(e)}'
        }), 500

@app.route('/api/sold-prices', methods=['POST'])
@limiter.limit("10 per minute")
def get_sold_prices():
    """Get recent sold prices for a postcode from Land Registry"""
    try:
        if not request.is_json:
            return jsonify({'success': False, 'message': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        postcode = data.get('postcode', '').strip().upper()
        
        if not postcode:
            return jsonify({'success': False, 'message': 'Postcode is required'}), 400
        
        if not validate_postcode(postcode):
            return jsonify({'success': False, 'message': 'Invalid postcode format'}), 400
        
        # Get sold prices from Land Registry
        sales = land_registry.get_sold_prices(postcode, limit=10)
        
        if not sales:
            return jsonify({
                'success': True,
                'sales': [],
                'message': 'No recent sales found for this postcode'
            })
        
        # Calculate average
        prices = [sale['price'] for sale in sales]
        avg_price = sum(prices) / len(prices)
        
        return jsonify({
            'success': True,
            'sales': sales,
            'average': round(avg_price, 0),
            'count': len(sales)
        })
        
    except Exception as e:
        app.logger.error(f'Land Registry API error: {str(e)}')
        return jsonify({
            'success': False,
            'message': 'Error fetching sold prices. Please try again.'
        }), 500

@app.route('/api/price-trend', methods=['POST'])
@limiter.limit("10 per minute")
def get_price_trend():
    """Get price trend for a postcode"""
    try:
        if not request.is_json:
            return jsonify({'success': False, 'message': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        postcode = data.get('postcode', '').strip().upper()
        
        if not postcode:
            return jsonify({'success': False, 'message': 'Postcode is required'}), 400
        
        if not validate_postcode(postcode):
            return jsonify({'success': False, 'message': 'Invalid postcode format'}), 400
        
        # Get price trend
        trend = land_registry.get_price_trend(postcode)
        
        return jsonify({
            'success': True,
            'trend': trend
        })
        
    except Exception as e:
        app.logger.error(f'Price trend error: {str(e)}')
        return jsonify({
            'success': False,
            'message': 'Error calculating price trend. Please try again.'
        }), 500

def _estimate_rent_from_land_registry(postcode, bedrooms):
    """Estimate monthly rent using Land Registry average price as a proxy.
    Uses a ~5% gross yield assumption (industry benchmark for UK BTL).
    Returns a dict compatible with the PropertyData API response shape."""
    try:
        avg_price = land_registry.get_average_price(postcode, months=18)
        if avg_price and avg_price > 0:
            # 5% gross yield / 12 months — standard UK BTL benchmark
            estimated = round(avg_price * 0.05 / 12)
            # Adjust by bedroom count relative to 3-bed baseline
            bed_multiplier = {1: 0.65, 2: 0.82, 3: 1.0, 4: 1.22, 5: 1.45}
            mult = bed_multiplier.get(bedrooms, 1.0)
            estimated = round(estimated * mult / 50) * 50  # round to nearest £50
            return {
                'estimated_monthly_rent': estimated,
                'confidence': 'Low',
                'market_rents': [
                    round(estimated * 0.92 / 50) * 50,
                    estimated,
                    round(estimated * 1.08 / 50) * 50,
                ],
                'data_source': 'Land Registry estimate (PropertyData API not configured)',
            }
    except Exception as e:
        app.logger.warning(f'[rental-fallback] Land Registry estimate failed: {e}')
    return None


@app.route('/api/propertydata/rental-valuation', methods=['POST'])
@limiter.limit("10 per minute")
def get_propertydata_rental():
    """Get rental valuation from PropertyData API (premium) with Land Registry fallback"""
    if not request.is_json:
        return jsonify({'success': False, 'message': 'Content-Type must be application/json'}), 400

    try:
        data = request.get_json()
        postcode = data.get('postcode', '').strip().upper()
        bedrooms = int(data.get('bedrooms', 3))

        if not postcode:
            return jsonify({'success': False, 'message': 'Postcode is required'}), 400

        if not validate_postcode(postcode):
            return jsonify({'success': False, 'message': 'Invalid postcode format'}), 400

        # --- Primary: PropertyData API ---
        if property_data.is_configured():
            key_length = len(property_data.api_key) if hasattr(property_data, 'api_key') else 0
            app.logger.info(f"[PropertyData] Postcode: {postcode}, Bedrooms: {bedrooms}")

            if key_length >= 20:
                result = property_data.get_rental_valuation(postcode, bedrooms)
                app.logger.info(f"[PropertyData] Result: {result}")

                if 'error' not in result:
                    return jsonify({'success': True, 'data': result, 'source': 'PropertyData API'})

                app.logger.warning(f"[PropertyData] Error in result, falling back: {result.get('error')}")
            else:
                app.logger.warning(f"[PropertyData] Key too short ({key_length}), falling back")

        # --- Fallback: Land Registry estimate ---
        app.logger.info(f"[rental-valuation] PropertyData unavailable, using Land Registry fallback for {postcode}")
        estimate = _estimate_rent_from_land_registry(postcode, bedrooms)
        if estimate:
            return jsonify({'success': True, 'data': estimate, 'source': 'Land Registry estimate'})

        return jsonify({
            'success': False,
            'message': 'Rental valuation unavailable. Set PROPERTY_DATA_API_KEY for accurate data.',
            'upgrade_url': 'https://propertydata.co.uk/api'
        }), 503

    except Exception as e:
        app.logger.error(f'PropertyData rental valuation error: {str(e)}')
        return jsonify({'success': False, 'message': 'Error fetching rental valuation. Please try again.'}), 500

@app.route('/api/propertydata/market-context', methods=['POST'])
@limiter.limit("10 per minute")
def get_propertydata_context_endpoint():
    """Get comprehensive market context from PropertyData API"""
    try:
        if not property_data.is_configured():
            return jsonify({
                'success': False,
                'message': 'PropertyData API not configured. Set PROPERTY_DATA_API_KEY environment variable.',
                'upgrade_url': 'https://propertydata.co.uk/api'
            }), 503
        
        if not request.is_json:
            return jsonify({'success': False, 'message': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        postcode = data.get('postcode', '').strip().upper()
        bedrooms = int(data.get('bedrooms', 3))
        
        if not postcode:
            return jsonify({'success': False, 'message': 'Postcode is required'}), 400
        
        if not validate_postcode(postcode):
            return jsonify({'success': False, 'message': 'Invalid postcode format'}), 400
        
        # Get comprehensive market context
        context = get_propertydata_context(postcode, bedrooms)
        
        if 'error' in context:
            return jsonify({
                'success': False,
                'message': context['error']
            }), 500
        
        return jsonify({
            'success': True,
            'data': context,
            'source': 'PropertyData API'
        })
        
    except Exception as e:
        app.logger.error(f'PropertyData context error: {str(e)}')
        return jsonify({
            'success': False,
            'message': 'Error fetching market context. Please try again.'
        }), 500

@app.route('/api/transport/stations', methods=['POST'])
@limiter.limit("10 per minute")
def get_transport_stations():
    """Get nearest transport stations for coordinates"""
    try:
        if not request.is_json:
            return jsonify({'success': False, 'message': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        lat = data.get('lat')
        lon = data.get('lon')
        postcode = data.get('postcode', '').strip().upper()
        
        # Need either coordinates or postcode
        if not lat or not lon:
            return jsonify({
                'success': False,
                'message': 'Latitude and longitude required'
            }), 400
        
        # Get nearest stations
        stations = transport_api.get_nearest_stations(float(lat), float(lon), radius=2000)
        
        if not stations:
            return jsonify({
                'success': True,
                'stations': [],
                'message': 'No stations found within 2km'
            })
        
        # Calculate transport score
        score_data = transport_api.calculate_transport_score(stations)
        
        # Format top stations
        top_stations = []
        for station in stations[:5]:
            top_stations.append({
                'name': station.name,
                'distance': round(station.distance),
                'modes': station.modes,
                'lines': station.lines[:3]
            })
        
        return jsonify({
            'success': True,
            'stations': top_stations,
            'connectivity_score': score_data,
            'source': 'Transport for London API'
        })
        
    except Exception as e:
        app.logger.error(f'Transport stations error: {str(e)}')
        return jsonify({
            'success': False,
            'message': 'Error fetching transport data. Please try again.'
        }), 500

@app.route('/api/transport/journey', methods=['POST'])
@limiter.limit("10 per minute")
def get_journey_time():
    """Get journey time between two locations"""
    try:
        if not request.is_json:
            return jsonify({'success': False, 'message': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        from_loc = data.get('from')
        to_loc = data.get('to')
        
        if not from_loc or not to_loc:
            return jsonify({
                'success': False,
                'message': 'Both from and to locations required'
            }), 400
        
        # Get journey
        journey = transport_api.get_journey_time(from_loc, to_loc)
        
        if not journey:
            return jsonify({
                'success': False,
                'message': 'Journey not found'
            }), 404
        
        return jsonify({
            'success': True,
            'journey': journey,
            'source': 'Transport for London API'
        })
        
    except Exception as e:
        app.logger.error(f'Journey time error: {str(e)}')
        return jsonify({
            'success': False,
            'message': 'Error calculating journey time. Please try again.'
        }), 500

@app.route('/api/transport/national-rail', methods=['POST'])
@limiter.limit("10 per minute")
def get_national_rail_endpoint():
    """Get UK-wide rail transport data (National Rail)"""
    try:
        if not request.is_json:
            return jsonify({'success': False, 'message': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        postcode = data.get('postcode', '').strip().upper()
        
        if not postcode:
            return jsonify({'success': False, 'message': 'Postcode is required'}), 400
        
        if not validate_postcode(postcode):
            return jsonify({'success': False, 'message': 'Invalid postcode format'}), 400
        
        # Get National Rail transport data
        result = get_national_rail_context(postcode)
        
        if 'error' in result and 'score' not in result:
            return jsonify({
                'success': False,
                'message': result['error']
            }), 500
        
        return jsonify({
            'success': True,
            'data': result,
            'source': 'National Rail / UK-Wide'
        })
        
    except Exception as e:
        app.logger.error(f'National Rail API error: {str(e)}')
        return jsonify({
            'success': False,
            'message': 'Error fetching rail data. Please try again.'
        }), 500

@app.route('/api/transport/uk-summary', methods=['POST'])
@limiter.limit("10 per minute")
def get_uk_transport_summary():
    """
    Get comprehensive UK transport summary
    Uses TfL for London, National Rail for rest of UK
    """
    try:
        if not request.is_json:
            return jsonify({'success': False, 'message': 'Content-Type must be application/json'}), 400
        
        data = request.get_json()
        postcode = data.get('postcode', '').strip().upper()
        lat = data.get('lat')
        lon = data.get('lon')
        
        if not postcode:
            return jsonify({'success': False, 'message': 'Postcode is required'}), 400
        
        if not validate_postcode(postcode):
            return jsonify({'success': False, 'message': 'Invalid postcode format'}), 400
        
        # Determine which API to use based on postcode area
        # London postcodes: E, EC, N, NW, SE, SW, W, WC
        london_areas = ['E', 'EC', 'N', 'NW', 'SE', 'SW', 'W', 'WC']
        postcode_area = postcode.split()[0][:2] if ' ' in postcode else postcode[:2]
        
        if any(postcode_area.startswith(area) for area in london_areas):
            # Use TfL for London
            if lat and lon:
                stations = transport_api.get_nearest_stations(float(lat), float(lon))
                score_data = transport_api.calculate_transport_score(stations)
                source = 'Transport for London (TfL)'
            else:
                # Fallback to National Rail if no coordinates
                result = get_national_rail_context(postcode)
                score_data = result.get('connectivity_score', {})
                source = 'National Rail (London fallback)'
        else:
            # Use National Rail for rest of UK
            result = get_national_rail_context(postcode)
            score_data = result.get('connectivity_score', {})
            source = 'National Rail (UK-wide)'
        
        return jsonify({
            'success': True,
            'transport_score': score_data,
            'postcode': postcode,
            'source': source,
            'is_london': postcode_area in london_areas
        })
        
    except Exception as e:
        app.logger.error(f'UK transport summary error: {str(e)}')
        return jsonify({
            'success': False,
            'message': 'Error fetching transport data. Please try again.'
        }), 500

@app.route('/api/crime', methods=['POST'])
@limiter.limit("20 per minute")
def get_crime_data():
    """Get crime statistics for a postcode using Police UK API (free, no key required)"""
    try:
        if not request.is_json:
            return jsonify({'success': False, 'message': 'Content-Type must be application/json'}), 400

        data = request.get_json()
        postcode = data.get('postcode', '').strip().upper()

        if not postcode:
            return jsonify({'success': False, 'message': 'Postcode is required'}), 400

        if not validate_postcode(postcode):
            return jsonify({'success': False, 'message': 'Invalid postcode format'}), 400

        # Step 1: Get lat/lng from postcodes.io
        geo_resp = requests.get(
            f'https://api.postcodes.io/postcodes/{postcode.replace(" ", "")}',
            timeout=8
        )
        if geo_resp.status_code != 200:
            return jsonify({'success': False, 'message': 'Could not geocode postcode'}), 404

        geo = geo_resp.json().get('result', {})
        lat = geo.get('latitude')
        lon = geo.get('longitude')
        if not lat or not lon:
            return jsonify({'success': False, 'message': 'No coordinates for postcode'}), 404

        # Step 2: Fetch crimes from Police UK API
        crime_resp = requests.get(
            'https://data.police.uk/api/crimes-street/all-crime',
            params={'lat': lat, 'lng': lon},
            timeout=12
        )
        if crime_resp.status_code != 200:
            return jsonify({'success': False, 'message': 'Crime API unavailable'}), 503

        crimes = crime_resp.json()
        total = len(crimes)

        # Aggregate by category
        categories = {}
        for c in crimes:
            cat = c.get('category', 'other')
            categories[cat] = categories.get(cat, 0) + 1

        # Determine crime level based on total monthly crimes in area
        if total < 30:
            crime_level = 'Low'
        elif total < 80:
            crime_level = 'Medium'
        else:
            crime_level = 'High'

        return jsonify({
            'success': True,
            'data': {
                'total_crimes': total,
                'crime_level': crime_level,
                'categories': categories,
                'lat': lat,
                'lon': lon,
            }
        })

    except requests.Timeout:
        return jsonify({'success': False, 'message': 'Crime API timed out'}), 503
    except Exception as e:
        app.logger.error(f'Crime data error: {str(e)}')
        return jsonify({'success': False, 'message': 'Error fetching crime data'}), 500


@app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    """
    Receive and verify Stripe billing webhooks.
    Set STRIPE_WEBHOOK_SECRET env var to your Stripe webhook signing secret (whsec_...).
    Set STRIPE_SECRET_KEY env var to your Stripe secret key (sk_...) for customer email lookup.
    Writes subscription rows to Supabase subscriptions table.

    Expected Supabase schema:
        CREATE TABLE subscriptions (
            id              TEXT PRIMARY KEY,  -- stripe subscription id
            email           TEXT NOT NULL,
            status          TEXT NOT NULL,     -- 'active' | 'cancelled' | 'paused'
            plan_id         TEXT,
            stripe_customer TEXT,
            created_at      TIMESTAMPTZ DEFAULT now(),
            updated_at      TIMESTAMPTZ DEFAULT now()
        );
    """
    raw_body = request.get_data()
    secret   = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

    # Verify signature (skip if secret not configured — dev/test only)
    if secret:
        sig_header = request.headers.get('Stripe-Signature', '')
        if not verify_stripe_signature(raw_body, sig_header, secret):
            app.logger.warning('[Stripe] Invalid webhook signature')
            return jsonify({'error': 'invalid signature'}), 400

    try:
        event = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({'error': 'bad json'}), 400

    event_type = event.get('type', '')
    obj        = event.get('data', {}).get('object', {})

    app.logger.info(f'[Stripe] Event: {event_type}')

    def get_stripe_customer_email(customer_id: str) -> str:
        """Fetch customer email from Stripe API using STRIPE_SECRET_KEY."""
        stripe_key = os.environ.get('STRIPE_SECRET_KEY', '')
        if not stripe_key or not customer_id:
            return ''
        try:
            resp = requests.get(
                f'https://api.stripe.com/v1/customers/{customer_id}',
                auth=(stripe_key, ''),
                timeout=5,
            )
            if resp.status_code == 200:
                return resp.json().get('email', '')
        except Exception as e:
            app.logger.warning(f'[Stripe] Customer lookup failed: {e}')
        return ''

    if event_type in ('customer.subscription.created', 'customer.subscription.updated'):
        sub_id      = obj.get('id', '')
        customer_id = obj.get('customer', '')
        status      = obj.get('status', '')
        items_data  = obj.get('items', {}).get('data', [])
        plan_id     = (items_data[0] if items_data else {}).get('price', {}).get('id', '')
        email       = obj.get('metadata', {}).get('email', '') or get_stripe_customer_email(customer_id)
        if status in ('active', 'trialing'):
            mapped_status = 'active'
        elif status in ('past_due', 'unpaid'):
            mapped_status = 'paused'
        else:
            mapped_status = 'cancelled'
        if sub_id and email:
            supabase_upsert_subscription({
                'id':              sub_id,
                'email':           email.lower().strip(),
                'status':          mapped_status,
                'plan_id':         plan_id,
                'stripe_customer': customer_id,
                'updated_at':      datetime.utcnow().isoformat(),
            })

    elif event_type == 'customer.subscription.deleted':
        sub_id      = obj.get('id', '')
        customer_id = obj.get('customer', '')
        email       = obj.get('metadata', {}).get('email', '') or get_stripe_customer_email(customer_id)
        if sub_id and email:
            supabase_upsert_subscription({
                'id':         sub_id,
                'email':      email.lower().strip(),
                'status':     'cancelled',
                'updated_at': datetime.utcnow().isoformat(),
            })

    elif event_type == 'invoice.payment_succeeded':
        sub_id      = obj.get('subscription', '')
        customer_id = obj.get('customer', '')
        email       = obj.get('customer_email', '') or get_stripe_customer_email(customer_id)
        if sub_id and email:
            supabase_upsert_subscription({
                'id':              sub_id,
                'email':           email.lower().strip(),
                'status':          'active',
                'stripe_customer': customer_id,
                'updated_at':      datetime.utcnow().isoformat(),
            })

    elif event_type == 'invoice.payment_failed':
        sub_id      = obj.get('subscription', '')
        customer_id = obj.get('customer', '')
        email       = obj.get('customer_email', '') or get_stripe_customer_email(customer_id)
        if sub_id and email:
            supabase_upsert_subscription({
                'id':         sub_id,
                'email':      email.lower().strip(),
                'status':     'paused',
                'updated_at': datetime.utcnow().isoformat(),
            })

    elif event_type == 'checkout.session.completed':
        # Pay-per-deal: one-time payment completed — grant access for one analysis
        session_id  = obj.get('id', '')
        customer_id = obj.get('customer', '')
        email       = (obj.get('customer_details') or {}).get('email', '') \
                      or obj.get('customer_email', '') \
                      or get_stripe_customer_email(customer_id)
        if session_id and email:
            supabase_upsert_subscription({
                'id':              session_id,
                'email':           email.lower().strip(),
                'status':          'active',
                'plan_id':         'pay_per_deal',
                'stripe_customer': customer_id,
                'updated_at':      datetime.utcnow().isoformat(),
            })

    return jsonify({'received': True}), 200


@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    """
    Create a Stripe Checkout Session for pay-per-deal (one-time payment).
    Requires env vars:
        STRIPE_SECRET_KEY            — Stripe secret key (sk_...)
        STRIPE_PRICE_ID_PAY_PER_DEAL — Stripe price ID for the one-off deal report
    Body JSON: { email?, successUrl?, cancelUrl? }
    Returns: { url } — redirect the browser to this URL to complete payment
    """
    data        = request.get_json(silent=True) or {}
    email       = str(data.get('email', '')).strip().lower()
    success_url = str(data.get('successUrl', '')).strip() or (request.host_url.rstrip('/') + '/analyze?payment=success')
    cancel_url  = str(data.get('cancelUrl',  '')).strip() or (request.host_url.rstrip('/') + '/analyze')

    stripe_key = os.environ.get('STRIPE_SECRET_KEY', '')
    price_id   = os.environ.get('STRIPE_PRICE_ID_PAY_PER_DEAL', '')

    if not stripe_key:
        app.logger.error('[Stripe] STRIPE_SECRET_KEY not configured')
        return jsonify({'error': 'Failed to create checkout session'}), 500
    if not price_id:
        app.logger.error('[Stripe] STRIPE_PRICE_ID_PAY_PER_DEAL not configured')
        return jsonify({'error': 'Failed to create checkout session'}), 500

    payload = {
        'mode':                                  'payment',
        'line_items[0][price]':                  price_id,
        'line_items[0][quantity]':               '1',
        'success_url':                           success_url,
        'cancel_url':                            cancel_url,
        # Always create a Stripe Customer so receipts are linkable
        'customer_creation':                     'always',
    }
    if email:
        payload['customer_email']                         = email
        # Explicitly set receipt_email so Stripe sends the confirmation
        # to the right address (requires receipt emails enabled in Dashboard)
        payload['payment_intent_data[receipt_email]']     = email

    try:
        resp = requests.post(
            'https://api.stripe.com/v1/checkout/sessions',
            auth=(stripe_key, ''),
            data=payload,
            timeout=10,
        )
        if resp.status_code == 200:
            return jsonify({'url': resp.json()['url']})
        app.logger.error(f'[Stripe] Checkout session error {resp.status_code}: {resp.text}')
        return jsonify({'error': 'Failed to create checkout session'}), 500
    except Exception as e:
        app.logger.error(f'[Stripe] Checkout session exception: {e}')
        return jsonify({'error': 'Failed to create checkout session'}), 500


@app.route('/api/sensitivity-analysis', methods=['POST'])
@limiter.limit("20 per minute")
def sensitivity_analysis():
    """
    AI "What If" Engine — Sensitivity Analysis endpoint.

    Accepts the original deal form data with optional overrides for:
        mortgage_rate   (float, %)
        monthly_rent    (float, £)
        vacancy_rate    (float, % of annual rent lost to voids — default 4.2%)

    Recalculates all financial metrics from scratch and returns:
        deal_score, monthly_cashflow, gross_yield, net_yield,
        cash_on_cash, verdict, risk_level, risk_flags, regional_benchmark,
        plus the three slider values actually used so the frontend can echo them.

    This endpoint is designed to be called on every slider change (debounced).
    It is pure calculation — no AI/LLM call is made, so it is fast (<100ms).
    """
    try:
        if not request.is_json:
            return jsonify({'success': False, 'message': 'Content-Type must be application/json'}), 400

        data = request.get_json(silent=True)
        if not data:
            return jsonify({'success': False, 'message': 'Invalid JSON data'}), 400

        # ── Validate required baseline field ─────────────────────────────────
        if not data.get('purchasePrice'):
            return jsonify({'success': False, 'message': 'purchasePrice is required'}), 400

        # ── Extract slider overrides ──────────────────────────────────────────
        override_rate     = data.get('override_mortgage_rate')
        override_rent     = data.get('override_monthly_rent')
        override_vacancy  = data.get('override_vacancy_rate')  # percent, e.g. 8.0

        # Validate overrides if supplied
        if override_rate is not None:
            try:
                override_rate = float(override_rate)
                if not (0.5 <= override_rate <= 20):
                    return jsonify({'success': False, 'message': 'override_mortgage_rate must be between 0.5 and 20'}), 400
            except (TypeError, ValueError):
                return jsonify({'success': False, 'message': 'override_mortgage_rate must be a number'}), 400

        if override_rent is not None:
            try:
                override_rent = float(override_rent)
                if not (100 <= override_rent <= 50000):
                    return jsonify({'success': False, 'message': 'override_monthly_rent must be between 100 and 50000'}), 400
            except (TypeError, ValueError):
                return jsonify({'success': False, 'message': 'override_monthly_rent must be a number'}), 400

        if override_vacancy is not None:
            try:
                override_vacancy = float(override_vacancy)
                if not (0 <= override_vacancy <= 30):
                    return jsonify({'success': False, 'message': 'override_vacancy_rate must be between 0 and 30'}), 400
            except (TypeError, ValueError):
                return jsonify({'success': False, 'message': 'override_vacancy_rate must be a number'}), 400

        # ── Apply overrides to the form data copy ─────────────────────────────
        import copy
        scenario_data = copy.deepcopy(data)

        if override_rate is not None:
            scenario_data['interestRate'] = override_rate

        if override_rent is not None:
            scenario_data['monthlyRent'] = override_rent

        # Vacancy rate override: store for use inside analyze_deal via a special key
        # analyze_deal uses a fixed 2-week void assumption internally.
        # We handle it here by adjusting the effective rent downwards.
        effective_vacancy_rate = override_vacancy if override_vacancy is not None else 4.2  # default ~2.2 weeks

        # If vacancy was overridden, reduce the monthly rent by the void fraction
        # so analyze_deal's downstream expense calculation reflects the real effective income.
        # (analyze_deal deducts management, maintenance, insurance from annual rent —
        # we scale annual rent by (1 - vacancy_rate/100) before passing it in.)
        if override_vacancy is not None and override_rent is None:
            # Use original rent from data, then scale by occupancy
            base_rent = float(data.get('monthlyRent') or data.get('purchasePrice', 0) * 0.005)
            occupancy = 1.0 - (effective_vacancy_rate / 100.0)
            scenario_data['monthlyRent'] = round(base_rent * occupancy, 2)
        elif override_vacancy is not None and override_rent is not None:
            # Both overridden: apply vacancy on top of the overridden rent
            occupancy = 1.0 - (effective_vacancy_rate / 100.0)
            scenario_data['monthlyRent'] = round(override_rent * occupancy, 2)

        # Ensure defaults
        if not scenario_data.get('dealType'):
            scenario_data['dealType'] = 'BTL'
        if not scenario_data.get('address'):
            scenario_data['address'] = 'Sensitivity Analysis'
        if not scenario_data.get('postcode'):
            scenario_data['postcode'] = 'N/A'
        if not scenario_data.get('monthlyRent') or scenario_data['monthlyRent'] == 0:
            scenario_data['monthlyRent'] = int(float(scenario_data['purchasePrice']) * 0.005)

        # ── Run core financial calculation ────────────────────────────────────
        metrics = analyze_deal(scenario_data)

        # ── Build sensitivity response ────────────────────────────────────────
        # Extract numeric values for the key metrics the frontend will display
        response = {
            'success': True,
            'scenario': {
                'mortgage_rate':   float(scenario_data.get('interestRate', data.get('interestRate', 5.5))),
                'monthly_rent':    float(scenario_data.get('monthlyRent', 0)),
                'vacancy_rate':    effective_vacancy_rate,
            },
            'metrics': {
                'deal_score':          metrics.get('deal_score', 0),
                'deal_score_label':    metrics.get('deal_score_label', ''),
                'monthly_cashflow':    metrics.get('monthly_cashflow', 0),
                'gross_yield':         float(metrics.get('gross_yield', 0)),
                'net_yield':           float(metrics.get('net_yield', 0)),
                'cash_on_cash':        float(metrics.get('cash_on_cash', 0)),
                'verdict':             metrics.get('verdict', 'REVIEW'),
                'risk_level':          metrics.get('risk_level', 'MEDIUM'),
                'monthly_mortgage':    float(metrics.get('monthly_mortgage', 0)),
                'net_annual_income':   float(str(metrics.get('net_annual_income', 0)).replace(',', '')),
                'annual_cashflow':     round(float(metrics.get('monthly_cashflow', 0)) * 12, 0),
                'score_breakdown':     metrics.get('score_breakdown', {}),
                'five_year_projection': metrics.get('five_year_projection', []),
            },
            'risk_flags':         metrics.get('risk_flags', []),
            'regional_benchmark': metrics.get('regional_benchmark', {}),
        }

        return jsonify(response)

    except ValueError as e:
        return jsonify({'success': False, 'message': f'Validation error: {str(e)}'}), 400
    except Exception as e:
        import traceback
        app.logger.error(f'[sensitivity-analysis] Error: {str(e)}')
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': f'Sensitivity analysis error: {str(e)}'}), 500


@app.route('/api/regional-benchmark', methods=['POST'])
@limiter.limit("20 per minute")
def regional_benchmark_lookup():
    """
    Standalone regional benchmark lookup.
    Accepts: { postcode, deal_type, gross_yield, monthly_cashflow }
    Returns the full benchmark comparison panel.
    """
    try:
        if not request.is_json:
            return jsonify({'success': False, 'message': 'Content-Type must be application/json'}), 400

        data = request.get_json(silent=True) or {}
        postcode       = sanitize_input(str(data.get('postcode', '')), 10).upper()
        deal_type      = sanitize_input(str(data.get('deal_type', 'BTL')), 10).upper()
        gross_yield    = float(data.get('gross_yield', 0) or 0)
        monthly_cashflow = float(data.get('monthly_cashflow', 0) or 0)

        if not postcode:
            return jsonify({'success': False, 'message': 'postcode is required'}), 400

        benchmark = compare_to_regional_benchmark(postcode, deal_type, gross_yield, monthly_cashflow)
        return jsonify({'success': True, 'benchmark': benchmark})

    except Exception as e:
        app.logger.error(f'[regional-benchmark] Error: {str(e)}')
        return jsonify({'success': False, 'message': str(e)}), 500


if __name__ == '__main__':
    # Security: Don't run with debug in production
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    port = int(os.environ.get('PORT', os.environ.get('FLASK_PORT', 5002)))
    app.run(debug=debug_mode, host='0.0.0.0', port=port)
