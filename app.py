from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import json
import os
from datetime import datetime
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

def scrape_with_jina(url: str) -> dict:
    """Scrape property using Jina Reader API (free, no API key required).
    Prepends https://r.jina.ai/ to the target URL and gets back clean markdown.
    Works for Rightmove, Zoopla, OnTheMarket and other JS-heavy sites.
    """
    jina_url = f'https://r.jina.ai/{url}'
    headers = {
        'Accept': 'text/plain',
        'X-Timeout': '20',
        'X-Return-Format': 'markdown',
        'X-Remove-Selector': 'nav,footer,header,[class*="cookie"],[class*="banner"],[class*="popup"]',
    }

    try:
        response = requests.get(jina_url, headers=headers, timeout=22)
        if response.status_code != 200:
            print(f"[Jina] Error: status {response.status_code}")
            return None

        # Jina returns clean markdown/plain text - not raw HTML
        text = response.text
        
        # Jina returns clean markdown/text - parse it directly
        data = {
            'address': None,
            'postcode': None,
            'price': None,
            'property_type': None,
            'bedrooms': None,
            'description': None
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
                    if val > 10000:  # Must be a plausible property price
                        data['price'] = val
                        break
                except Exception:
                    pass

        # --- Bedrooms ---
        bed_candidates = []

        # Pattern 1: "X bed(room) [type]" - most reliable in clean text
        bed_near_type = re.search(
            r'(\d+)\s*bed(?:room)?s?\s+(?:semi-detached|detached|terraced|flat|house|bungalow|apartment)',
            text, re.IGNORECASE
        )
        if bed_near_type:
            val = int(bed_near_type.group(1))
            if 1 <= val <= 20:
                bed_candidates.append(('near_type', val, 90))

        # Pattern 2: Title line from Jina ("Title: 3 bed...")
        title_bed = re.search(r'^Title:.*?(\d+)\s*bed', text[:500], re.IGNORECASE | re.MULTILINE)
        if title_bed:
            val = int(title_bed.group(1))
            if 1 <= val <= 20:
                bed_candidates.append(('title', val, 80))

        # Pattern 3: General "X bed" anywhere
        plain_bed = re.search(r'(\d+)\s*bed(?:room)?s?', text, re.IGNORECASE)
        if plain_bed:
            val = int(plain_bed.group(1))
            if 1 <= val <= 20:
                bed_candidates.append(('plain', val, 50))

        if bed_candidates:
            bed_candidates.sort(key=lambda x: x[2], reverse=True)
            data['bedrooms'] = bed_candidates[0][1]
            print(f"[Jina] Bedroom candidates: {bed_candidates}")
        else:
            data['bedrooms'] = None

        # --- Property type ---
        property_types = ['semi-detached', 'detached', 'semi', 'terraced', 'flat', 'bungalow', 'apartment']
        for ptype in property_types:
            if re.search(r'\b' + ptype + r'\b', text, re.IGNORECASE):
                data['property_type'] = 'Semi-Detached' if ptype.lower() == 'semi' else ptype.title()
                break

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

        # --- Postcode extraction: four strategies in priority order ---

        def valid_pc(fp):
            """Return True if fp looks like a real UK postcode."""
            return (re.match(r'^[A-Z]{1,2}\d[A-Z\d]?\s\d[A-Z]{2}$', fp)
                    and is_valid_area(fp))

        found_postcode = None

        # Strategy 0: scan the first 1 200 chars (Jina always puts Title / URL
        # Source at the top).  This catches postcodes in the page title even if
        # the "Title:" line regex doesn't match due to line-ending quirks.
        header_pcs = re.findall(postcode_pattern, text[:1200].upper())
        for pc in header_pcs:
            fp = format_postcode(pc)
            if valid_pc(fp):
                found_postcode = fp
                print(f"[Jina] Postcode from header scan: {fp}")
                break

        # Strategy 1: parse the "Title:" line that Jina emits.
        # Rightmove/Zoopla titles look like:
        #   "3 bed semi for sale - Orme Avenue, Alkrington, Manchester M24 1JZ | Rightmove"
        if not found_postcode:
            title_search = re.search(r'Title:\s*(.+)', text, re.IGNORECASE)
            if title_search:
                title_text = title_search.group(1)
                title_pcs = re.findall(postcode_pattern, title_text.upper())
                for pc in title_pcs:
                    fp = format_postcode(pc)
                    if valid_pc(fp):
                        found_postcode = fp
                        print(f"[Jina] Postcode from title line: {fp}")
                        break

        # Strategy 2: explicit label — "Postcode: OL1 3LA" anywhere in page.
        if not found_postcode:
            explicit = re.search(
                r'postcode[:\s]+([A-Z]{1,2}\d[A-Z\d]?(?:\s)?\d[A-Z]{2})',
                text, re.IGNORECASE
            )
            if explicit:
                fp = format_postcode(explicit.group(1).upper())
                if valid_pc(fp):
                    found_postcode = fp
                    print(f"[Jina] Postcode from explicit label: {fp}")

        # Strategy 3: score every candidate; heavily penalise agent/footer context.
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

                    # Reward proximity to start (listing data comes first in Jina output)
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

                    # Strongly penalise agent/branch/contact sections
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
                print(f"[Jina] Postcode candidates: {sorted_pcs[:5]}")
                best_postcode = sorted_pcs[0][0] if sorted_pcs[0][1] >= 0 else None
                found_postcode = best_postcode
                print(f"[Jina] Selected postcode (scored): {best_postcode}")
            else:
                print("[Jina] No valid postcodes found")

        data['postcode'] = found_postcode

        # --- Address ---
        # Jina typically starts its output with "Title: <page title>"
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

        print(f"[Jina] Extracted: price={data['price']}, beds={data['bedrooms']}, "
              f"postcode={data['postcode']}, address={str(data['address'])[:60]}")
        return data

    except Exception as e:
        print(f"[Jina] Exception: {e}")
        return None

def validate_postcode_str(postcode):
    """Quick validation of UK postcode format"""
    if not postcode:
        return False
    pattern = r'^[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}$'
    return bool(re.match(pattern, postcode.upper().strip()))

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

# Security: Configure CORS properly (restrict in production)
_allowed_origins = ["https://metusaproperty.co.uk", "https://analyzer.metusaproperty.co.uk"]
# Allow additional origins via env var (comma-separated) - use for Vercel deployment URL
_extra_origins = os.environ.get('CORS_ALLOWED_ORIGINS', '')
if _extra_origins:
    _allowed_origins.extend([o.strip() for o in _extra_origins.split(',') if o.strip()])
CORS(app, resources={
    r"/analyze":                         {"origins": _allowed_origins},
    r"/ai-analyze":                      {"origins": _allowed_origins},
    r"/extract-url":                     {"origins": _allowed_origins},
    r"/download-pdf":                    {"origins": _allowed_origins},
    r"/api/*":                           {"origins": _allowed_origins},
})

# Security: Rate limiting to prevent abuse
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

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

def calculate_stamp_duty(price, second_property=True):
    """
    Calculate UK stamp duty for England & NI
    Updated for 2024/2025 rates including 5% surcharge for additional properties
    """
    # Thresholds (as of 2024)
    if not second_property:
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

def generate_5_year_projection(annual_rent, net_annual_income, purchase_price, cash_invested, interest_rate):
    """
    Generate 5-year cash flow and equity projection
    Accounts for rent growth (3% annually) and capital growth (4% annually)
    """
    projections = []
    cumulative_cashflow = 0
    
    # Market assumptions
    rent_growth_rate = 0.03  # 3% annual rent increase
    capital_growth_rate = 0.04  # 4% annual property value increase
    
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

    Data based on publicly available UK council planning records.
    'known' = True means the area is in our database; False means verify with council.
    Returns dict with article_4 status and details.
    """
    # ------------------------------------------------------------------ #
    # UK-WIDE Article 4 Direction Database                                #
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
    postcode = postcode.strip().upper()
    area_code = postcode.split()[0] if ' ' in postcode else postcode

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
    stamp_duty = calculate_stamp_duty(purchase_price)
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
        bridging_apr = (bridging_monthly_rate * 12) + (
            (bridging_arrangement_fee_pct + bridging_exit_fee_pct) / bridging_term_months * 12
        )
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
    five_year_projection = generate_5_year_projection(
        annual_rent, net_annual_income, purchase_price, 
        cash_invested, interest_rate
    )
    
    # Get Article 4 info
    article_4_info = check_article_4(postcode)

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
    internal_area = data.get('internal_area', 1000)  # Default 1000 sq ft
    refurb_estimates = get_refurb_estimate(postcode, property_type_for_refurb, bedrooms, internal_area)
    
    # Score visualization data
    score_breakdown = {
        'total': deal_score,
        'yield_score': min(30, max(0, (gross_yield / 8) * 30)) if gross_yield >= 6 else max(0, (gross_yield / 6) * 10),
        'cashflow_score': 25 if monthly_cashflow >= 300 else (20 if monthly_cashflow >= 200 else (15 if monthly_cashflow >= 100 else 5)),
        'coc_score': 25 if cash_on_cash >= 12 else (20 if cash_on_cash >= 10 else (15 if cash_on_cash >= 8 else (5 if cash_on_cash >= 4 else 0))),
        'net_yield_score': 15 if net_yield >= 5 else (10 if net_yield >= 4 else (5 if net_yield >= 2 else 0)),
        'risk_score': 5 if risk_level == 'LOW' else 0
    }
    
    # Compile results
    results = {
        'deal_type': deal_type,
        'address': address,
        'postcode': postcode,
        'location': {
            'country': 'England',
            'region': get_region_from_postcode(postcode),
            'council': article_4_info['council']
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
        'analysis_date': datetime.now().strftime('%Y-%m-%d'),
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
        ]
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
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

@app.route('/api/test-jina')
def test_jina():
    """Test Jina Reader connectivity (no API key required)"""
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
def test_propertydata():
    """Test PropertyData API configuration"""
    env_key = os.environ.get('PROPERTY_DATA_API_KEY', '')
    module_key = property_data.api_key if hasattr(property_data, 'api_key') else 'N/A'
    
    # Detailed diagnostics
    diagnostics = {
        'env_key_present': 'PROPERTY_DATA_API_KEY' in os.environ,
        'env_key_length': len(env_key),
        'env_key_full': env_key,  # Show full key for debugging (remove in production)
        'module_key_length': len(module_key) if module_key else 0,
        'module_key_full': module_key if module_key else 'N/A',
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
        
        # Run Jina Reader and basic scraper in parallel to stay well under
        # Gunicorn's 30s worker timeout (Jina alone can take 15-20s).
        print("[extract-url] Running Jina Reader + basic scraper in parallel...")
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _has_data(d):
            if not d:
                return False
            addr = d.get('address')
            return bool(d.get('price') or (addr and addr != 'Address not available'))

        with ThreadPoolExecutor(max_workers=2) as pool:
            jina_future = pool.submit(scrape_with_jina, url)
            basic_future = pool.submit(extract_property_from_url, url)

            jina_result  = None
            basic_result = None
            try:
                for future in as_completed([jina_future, basic_future], timeout=25):
                    result = future.result()
                    if future is jina_future:
                        jina_result = result
                        print(f"[extract-url] Jina finished, has_data={_has_data(result)}")
                    else:
                        basic_result = result
                        print(f"[extract-url] Basic scraper finished, has_data={_has_data(result)}")
            except Exception:
                pass

            # Merge: start with whichever has data, then overlay Jina fields
            # because Jina's postcode/address logic is more accurate.
            if _has_data(jina_result) and _has_data(basic_result):
                # Both succeeded — use basic as base, override with Jina's values
                extracted_data = {**basic_result, **{
                    k: v for k, v in jina_result.items() if v not in (None, '', 'Address not available')
                }}
                print("[extract-url] Merged both scrapers (Jina fields take precedence)")
            elif _has_data(jina_result):
                extracted_data = jina_result
                print("[extract-url] Using Jina result only")
            elif _has_data(basic_result):
                extracted_data = basic_result
                print("[extract-url] Using basic scraper result only")
            else:
                extracted_data = None

        if extracted_data and _has_data(extracted_data):
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

JSON schema:
{{
  "verdict": "<2-3 sentences: clear overall assessment referencing key figures>",
  "strengths": "<bullet list using • and <br> separating each point — 3-4 specific strengths>",
  "risks": "<bullet list using • and <br> separating each point — 3-4 specific, deal-relevant risks including Article 4 if applicable>",
  "area": "<2-3 sentences: specific to the postcode — rental demand, tenant profile, comparable areas, growth prospects>",
  "next_steps": "<numbered list 1-5 with <br> between items — actionable, deal-specific steps. If HMO strategy, include Article 4 / licensing guidance as instructed above>"
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
    verdict    = calculated_metrics.get('verdict', 'REVIEW')
    score      = calculated_metrics.get('deal_score', 50)
    gross      = calculated_metrics.get('gross_yield', 0)
    cashflow   = calculated_metrics.get('monthly_cashflow', 0)
    coc        = calculated_metrics.get('cash_on_cash', 0)
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
            "strengths": (
                f"• Gross yield of {gross:.1f}% above the {benchmarks['gross_yield']}% benchmark<br>"
                f"• Monthly cashflow of £{cashflow:,.0f} provides a financial buffer<br>"
                f"• Cash-on-cash return of {coc:.1f}% indicates efficient capital deployment<br>"
                f"• Deal score of {score}/100 meets investment criteria"
            ),
            "risks": (
                "• Void periods and unexpected maintenance could erode cashflow<br>"
                "• Mortgage rate rises will compress net yield — stress-test at 6%+<br>"
                "• Verify advertised rent against local comparables before committing<br>"
                f"{_a4_risk_line}"
            ),
            "area": (
                f"{postcode} shows sufficient rental demand to support the assumed rent. "
                "Verify tenant demand with local letting agents and check comparable listings."
            ),
            "next_steps": (
                "1. Confirm achievable rent with 2-3 local letting agents<br>"
                "2. Arrange a viewing and independent RICS survey (£400-600)<br>"
                "3. Obtain mortgage Decision in Principle at current rates<br>"
                f"4. Instruct a solicitor for preliminary searches<br>"
                f"{_a4_step}"
            )
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
            "strengths": (
                "• Property may have value-add potential through refurbishment or strategy change<br>"
                "• Some metrics are close to benchmark — small price reduction could make it work<br>"
                f"• {postcode} may offer longer-term capital growth<br>"
                f"• Could work as {_alt_strategy} if current figures are marginal"
            ),
            "risks": (
                f"• Gross yield of {gross:.1f}% is below the {benchmarks['gross_yield']}% minimum<br>"
                f"• Monthly cashflow of £{cashflow:,.0f} leaves little buffer for voids or repairs<br>"
                "• Overpaying vs comparable sales would worsen position<br>"
                f"{_a4_risk_line}"
            ),
            "area": (
                f"{postcode} warrants careful research — confirm rental demand and "
                "recent comparable sales before assuming the projected rent is achievable."
            ),
            "next_steps": (
                "1. Research 5+ comparable rentals and 5+ recent sold prices in the postcode<br>"
                "2. Attempt to negotiate purchase price down by 5-10%<br>"
                f"3. Model the deal as {_alt_strategy} to check if alternative strategies work<br>"
                "4. Get a local letting agent's written opinion on achievable rent<br>"
                f"{_a4_step}"
            )
        }
    else:
        return {
            "verdict": (
                f"Weak deal scoring {score}/100. Gross yield of {gross:.1f}% and cashflow of "
                f"£{cashflow:,.0f}/month are materially below target — this deal does not meet "
                "minimum investment criteria and should be avoided."
            ),
            "strengths": (
                "• Physical asset provides some security<br>"
                "• May suit a different buyer profile (e.g. owner-occupier)<br>"
                "• Could be revisited if purchase price drops significantly"
            ),
            "risks": (
                f"• Gross yield of {gross:.1f}% is well below the {benchmarks['gross_yield']}% target<br>"
                f"• Cashflow of £{cashflow:,.0f}/month is insufficient — risk of negative cashflow<br>"
                "• Capital at risk if market softens<br>"
                f"{_a4_risk_line}"
            ),
            "area": (
                f"{postcode} may have good fundamentals but this specific deal is mispriced. "
                "Continue searching the same area for better-value stock."
            ),
            "next_steps": (
                "1. Do not proceed with this deal at the current asking price<br>"
                "2. Calculate the maximum price that delivers a 6%+ gross yield<br>"
                "3. Either submit a significantly lower offer or walk away<br>"
                "4. Set Rightmove/Zoopla alerts for similar properties at lower prices<br>"
                f"{_a4_step}"
            )
        }

@app.route('/ai-analyze', methods=['POST'])
@limiter.limit("5 per minute")  # Lower limit for AI analysis
def ai_analyze():
    """
    Full AI-powered deal analysis
    1. Calculates all financial metrics
    2. Gets AI-enhanced insights
    3. Returns comprehensive analysis
    """
    try:
        if not request.is_json:
            return jsonify({'success': False, 'message': 'Content-Type must be application/json'}), 400
        
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'success': False, 'message': 'Invalid JSON data'}), 400
        
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
                    
                    market_data = {
                        'source': 'Land Registry',
                        'recent_sales': sold_prices,
                        'price_trend': price_trend,
                        'average_price': avg_price
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
            rent_comparables = [
                {
                    'address': f"{bedrooms}-bed property, {postcode}",
                    'monthly_rent': market_data['estimated_rent'],
                    'bedrooms': bedrooms,
                    'source': 'PropertyData market estimate',
                    'confidence': market_data.get('rental_confidence', 'N/A')
                }
            ]

        # ------------------------------------------------------------------ #
        # HOUSE VALUATION                                                      #
        # Priority: PropertyData valuation → Land Registry avg → asking price #
        # ------------------------------------------------------------------ #
        house_valuation = market_data.get('sales_valuation')
        if not house_valuation:
            avg_sold = market_data.get('avg_sold_price') or market_data.get('average_price')
            if avg_sold:
                house_valuation = {
                    'estimate': int(avg_sold),
                    'confidence': 'Low',
                    'source': 'Land Registry area average',
                    'note': 'Based on recent sold prices in postcode area — not property-specific.'
                }
            else:
                house_valuation = {
                    'estimate': int(data.get('purchasePrice', 0)),
                    'confidence': 'Low',
                    'source': 'Asking price only',
                    'note': 'No external valuation available. Commission a RICS survey for an accurate figure.'
                }

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

if __name__ == '__main__':
    # Security: Don't run with debug in production
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    port = int(os.environ.get('PORT', os.environ.get('FLASK_PORT', 5002)))
    app.run(debug=debug_mode, host='0.0.0.0', port=port)
