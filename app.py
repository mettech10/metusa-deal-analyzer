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

# ScrapingBee configuration (set SCRAPINGBEE_API_KEY env var for URL scraping)
SCRAPINGBEE_API_KEY = os.environ.get('SCRAPINGBEE_API_KEY') or 'FLJ5HUFLWZTW46GNZDDXRD93VM3ONK6BO3YYEKRR9L77O1NA5BYNUVFTYXV3J9BJ056ZWF50ZRY1DNDA'


def scrape_with_scrapingbee(url: str) -> dict:
    """Scrape property using ScrapingBee API with residential proxies"""
    if not SCRAPINGBEE_API_KEY:
        print("[ScrapingBee] No API key configured")
        return None
    
    api_url = 'https://app.scrapingbee.com/api/v1/'
    params = {
        'api_key': SCRAPINGBEE_API_KEY,
        'url': url,
        'render_js': 'true',
        'premium_proxy': 'true',
        'country_code': 'gb',
        'wait': '2000',
    }
    
    try:
        response = requests.get(api_url, params=params, timeout=60)
        if response.status_code != 200:
            print(f"[ScrapingBee] Error: status {response.status_code}")
            return None
        
        html = response.text
        
        # Extract data from HTML
        data = {
            'address': None,
            'postcode': None,
            'price': None,
            'property_type': None,
            'bedrooms': None,
            'description': None
        }
        
        # Price - look for price patterns
        price_patterns = [
            r'£([\d,]+)',  # Standard £price
            r'price[":\s]*£?([\d,]+)',  # JSON/structured data
            r'"price":\s*"?£?([\d,]+)',  # JSON format
        ]
        for pattern in price_patterns:
            price_match = re.search(pattern, html, re.IGNORECASE)
            if price_match:
                try:
                    data['price'] = int(price_match.group(1).replace(',', ''))
                    break
                except:
                    pass
        
        # Bedrooms - improved extraction with validation
        # Try multiple patterns and validate the result
        bed_candidates = []
        
        # Pattern 1: Structured data (most reliable)
        structured_bed = re.search(r'"bedrooms"[:>"\s]*(\d+)', html, re.IGNORECASE)
        if structured_bed:
            val = int(structured_bed.group(1))
            if 1 <= val <= 20:  # Sanity check
                bed_candidates.append(('structured', val, 100))
        
        # Pattern 2: Near property type indicators
        bed_near_property = re.search(r'(\d+)\s*bed(?:room)?s?\s+(?:semi-detached|detached|terraced|flat|house|bungalow)', html, re.IGNORECASE)
        if bed_near_property:
            val = int(bed_near_property.group(1))
            if 1 <= val <= 20:
                bed_candidates.append(('near_property_type', val, 90))
        
        # Pattern 3: In hero/title section (early in HTML)
        early_bed = re.search(r'<title[^>]*>.*?(\d+)\s*bed', html[:5000], re.IGNORECASE)
        if early_bed:
            val = int(early_bed.group(1))
            if 1 <= val <= 20:
                bed_candidates.append(('title', val, 80))
        
        # Pattern 4: Standard pattern with context
        bed_with_context = re.search(r'(\d+)\s*bed(?:room)?s?\s*(?:semi|detached|terraced|flat|house)?', html, re.IGNORECASE)
        if bed_with_context:
            val = int(bed_with_context.group(1))
            if 1 <= val <= 20:
                bed_candidates.append(('standard', val, 50))
        
        # Pick the highest confidence bedroom count
        if bed_candidates:
            bed_candidates.sort(key=lambda x: x[2], reverse=True)
            data['bedrooms'] = bed_candidates[0][1]
            print(f"[ScrapingBee] Bedroom candidates: {bed_candidates}")
        else:
            data['bedrooms'] = None
        
        # Property type
        property_types = ['detached', 'semi-detached', 'semi', 'terraced', 'flat', 'bungalow', 'apartment']
        for ptype in property_types:
            if re.search(r'\b' + ptype + r'\b', html, re.IGNORECASE):
                data['property_type'] = 'Semi-Detached' if ptype.lower() == 'semi' else ptype.title()
                break
        
        # Postcode - improved extraction with smart filtering
        # UK postcode pattern: AA9 9AA or A9 9AA or AA99 9AA etc.
        # Valid UK postcode areas (first 1-2 letters)
        VALID_AREAS = {'AB', 'AL', 'B', 'BA', 'BB', 'BD', 'BH', 'BL', 'BN', 'BR', 'BS', 'BT', 'CA', 'CB', 'CF', 'CH', 'CM', 'CO', 'CR', 'CT', 'CV', 'CW', 'DA', 'DD', 'DE', 'DG', 'DH', 'DL', 'DN', 'DT', 'DY', 'E', 'EC', 'EH', 'EN', 'EX', 'FK', 'FY', 'G', 'GL', 'GU', 'HA', 'HD', 'HG', 'HP', 'HR', 'HS', 'HU', 'HX', 'IG', 'IP', 'IV', 'KA', 'KT', 'KW', 'KY', 'L', 'LA', 'LD', 'LE', 'LL', 'LN', 'LS', 'LU', 'M', 'ME', 'MK', 'ML', 'N', 'NE', 'NG', 'NN', 'NP', 'NR', 'NW', 'OL', 'OX', 'PA', 'PE', 'PH', 'PL', 'PO', 'PR', 'RG', 'RH', 'RM', 'S', 'SA', 'SE', 'SG', 'SK', 'SL', 'SM', 'SN', 'SO', 'SP', 'SR', 'SS', 'ST', 'SW', 'SY', 'TA', 'TD', 'TF', 'TN', 'TQ', 'TR', 'TS', 'TW', 'UB', 'W', 'WA', 'WC', 'WD', 'WF', 'WN', 'WR', 'WS', 'WV', 'YO', 'ZE'}
        
        postcode_pattern = r'[A-Z]{1,2}\d[A-Z\d]?(?:\s)?\d[A-Z]{2}'
        all_postcodes = re.findall(postcode_pattern, html.upper())
        
        # Clean postcodes - ensure space is present
        def format_postcode(pc):
            pc = pc.strip()
            if ' ' not in pc:
                # Insert space before last 3 characters
                pc = pc[:-3] + ' ' + pc[-3:]
            return pc
        
        def is_valid_area(pc):
            """Check if postcode has a valid UK area code"""
            area = pc.split()[0]
            # Remove digits to get just the letters
            area_letters = ''.join(c for c in area if c.isalpha())
            return area_letters in VALID_AREAS
        
        # Get unique postcodes with their context
        postcode_scores = {}
        for pc in all_postcodes:
            formatted_pc = format_postcode(pc)
            
            # Skip if we've seen this postcode
            if formatted_pc in postcode_scores:
                continue
            
            # Validate format and area
            if not re.match(r'^[A-Z]{1,2}\d[A-Z\d]?\s\d[A-Z]{2}$', formatted_pc):
                continue
            
            # Check it's a valid UK area
            if not is_valid_area(formatted_pc):
                print(f"[ScrapingBee] Skipping invalid area: {formatted_pc}")
                continue
            
            # Skip obviously wrong postcodes (too short area codes like E4, M2)
            area_part = formatted_pc.split()[0]
            if len(area_part) < 2:
                continue
                
            # Find all occurrences and score them
            best_score = 0
            for match in re.finditer(re.escape(pc), html.upper()):
                idx = match.start()
                context = html[max(0, idx-400):idx+400].lower()
                score = 0
                
                # Very high scoring - near property title or hero section (Zoopla/Rightmove)
                if 'data-test="address-title"' in context or 'property-title' in context:
                    score += 200
                if '<h1' in context and ('property' in context or 'bed' in context):
                    score += 150
                if 'dp-address' in context or 'property-address' in context:
                    score += 140
                    
                # High scoring - near price/property indicators
                if any(word in context for word in ['price', '£', 'for sale', 'guide price', 'asking price']):
                    score += 100
                if any(word in context for word in ['property', 'bedroom', 'bed', 'house', 'flat']):
                    score += 80
                if any(word in context for word in ['road', 'street', 'avenue', 'lane', 'drive', 'way', 'close']):
                    score += 60
                if 'postcode' in context or 'post code' in context:
                    score += 40
                if 'manchester' in context or 'london' in context or 'birmingham' in context or 'bristol' in context:
                    score += 30  # Major city context
                    
                # Medium scoring - in address context
                if 'address' in context:
                    score += 20
                    
                # Penalize agent/office contexts
                if any(word in context for word in ['agent', 'office', 'branch', 'contact us', 'tel:', 'phone', 'call us']):
                    score -= 150
                if any(agent in context for agent in ['reeds rains', 'estate agent', 'your move', 'haart', 'connells']):
                    score -= 100
                    
                # Heavy penalty for financial/legal contexts
                if any(word in context for word in ['vat', 'registration', 'company number', 'vat no']):
                    score -= 200
                    
                # Boost if appears in title or main content area (first 8000 chars)
                if idx < 8000:
                    score += 50
                if idx < 3000:
                    score += 30  # Even earlier = main property section
                    
                best_score = max(best_score, score)
            
            postcode_scores[formatted_pc] = best_score
        
        # Pick the postcode with highest score
        if postcode_scores:
            # Sort by score descending
            sorted_postcodes = sorted(postcode_scores.items(), key=lambda x: x[1], reverse=True)
            print(f"[ScrapingBee] Postcode candidates: {sorted_postcodes[:5]}")
            
            # Take the highest scoring one with minimum score threshold
            best_postcode = None
            best_score = sorted_postcodes[0][1]
            
            # Use the top one if it has a decent score
            if best_score >= 50:
                best_postcode = sorted_postcodes[0][0]
            else:
                # Try to find any with positive score
                for pc, score in sorted_postcodes:
                    if score > 0:
                        best_postcode = pc
                        break
                
                # If still nothing, take the one that appears earliest in the page
                if not best_postcode and sorted_postcodes:
                    # Find which appears first
                    earliest_idx = float('inf')
                    for pc, _ in sorted_postcodes:
                        match = re.search(re.escape(pc.replace(' ', '')), html.upper())
                        if match and match.start() < earliest_idx:
                            earliest_idx = match.start()
                            best_postcode = format_postcode(pc)
            
            data['postcode'] = best_postcode
            print(f"[ScrapingBee] Selected postcode: {best_postcode} (score: {postcode_scores.get(best_postcode, 'N/A')})")
        else:
            data['postcode'] = None
            print("[ScrapingBee] No valid postcodes found")
        
        # Address extraction - improved
        # Try multiple sources for address
        address_sources = []
        
        # 1. Try to find address in meta tags or structured data
        address_match = re.search(r'"address"[:>"\s]*([^"<]+)', html, re.IGNORECASE)
        if address_match:
            addr = address_match.group(1).strip()
            if len(addr) > 10 and any(char.isdigit() for char in addr):
                address_sources.append(addr)
        
        # 2. Look for address in specific divs/spans (common patterns)
        address_div = re.search(r'data-test=["\']property-title["\'][^>]*>([^<]+)', html, re.IGNORECASE)
        if address_div:
            address_sources.append(address_div.group(1).strip())
        
        # 3. Extract from title - but clean it up better
        title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
        if title_match:
            title = title_match.group(1)
            # Clean up the title
            title = re.sub(r'\s*[-|]\s*(Rightmove|Zoopla|OnTheMarket|Property|For Sale).*', '', title, flags=re.IGNORECASE)
            title = re.sub(r'\s*\d+\s*bed\s*\w+\s*house', '', title, flags=re.IGNORECASE)
            title = title.strip()
            if title and len(title) > 5:
                address_sources.append(title)
        
        # 4. Look for address patterns in the HTML
        # Common pattern: Street name + location
        addr_pattern = re.search(r'([A-Z][a-z]+(?:\s[A-Z][a-z]+)?\s+(?:Road|Street|Avenue|Lane|Drive|Way|Close|Crescent|Gardens))[^<]*,\s*([^<,]{5,50})', html)
        if addr_pattern:
            street = addr_pattern.group(1)
            area = addr_pattern.group(2).strip()
            if street and area:
                address_sources.append(f"{street}, {area}")
        
        # Pick the best address
        for addr in address_sources:
            if addr and len(addr) > 5:
                # Clean up the address
                addr = re.sub(r'\s+', ' ', addr)
                addr = re.sub(r'\s*,\s*', ', ', addr)
                if validate_postcode_str(data.get('postcode', '')):
                    # If we have a postcode, make sure it's in the address or add it
                    if data['postcode'] and data['postcode'] not in addr:
                        addr = f"{addr}, {data['postcode']}"
                data['address'] = addr.strip()
                break
        
        # If still no address, use a default
        if not data['address']:
            data['address'] = "Address not available"
        
        print(f"[ScrapingBee] Extracted: price={data['price']}, beds={data['bedrooms']}, postcode={data['postcode']}")
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
CORS(app, resources={
    r"/analyze":     {"origins": _allowed_origins},
    r"/ai-analyze":  {"origins": _allowed_origins},
    r"/extract-url": {"origins": _allowed_origins},
    r"/download-pdf":{"origins": _allowed_origins},
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
    Check if area is under Article 4 direction
    
    Returns dict with article 4 status and details
    """
    # Article 4 areas database - key Manchester areas with Article 4
    article_4_areas = {
        # Manchester City Centre and surrounding
        'M1': {'active': True, 'council': 'Manchester City Council', 'note': 'City centre HMO restrictions'},
        'M2': {'active': True, 'council': 'Manchester City Council', 'note': 'City centre HMO restrictions'},
        'M3': {'active': True, 'council': 'Manchester City Council', 'note': 'City centre HMO restrictions'},
        'M4': {'active': True, 'council': 'Manchester City Council', 'note': 'Northern Quarter HMO restrictions'},
        'M13': {'active': True, 'council': 'Manchester City Council', 'note': 'Chorlton-on-Medlock / Victoria Park'},
        'M14': {'active': True, 'council': 'Manchester City Council', 'note': 'Fallowfield / Moss Side / Rusholme'},
        'M15': {'active': True, 'council': 'Manchester City Council', 'note': 'Hulme / Moss Side'},
        'M16': {'active': False, 'council': 'Manchester City Council', 'note': 'No Article 4 currently'},
        'M19': {'active': True, 'council': 'Manchester City Council', 'note': 'Levenshulme / Burnage'},
        'M20': {'active': True, 'council': 'Manchester City Council', 'note': 'Didsbury / Withington'},
        'M21': {'active': True, 'council': 'Manchester City Council', 'note': 'Chorlton-cum-Hardy'},
        
        # Salford
        'M5': {'active': True, 'council': 'Salford City Council', 'note': 'Ordsall / Salford areas'},
        'M6': {'active': True, 'council': 'Salford City Council', 'note': 'Salford central areas'},
        'M7': {'active': False, 'council': 'Salford City Council', 'note': 'No Article 4 currently'},
        
        # Trafford
        'M16': {'active': False, 'council': 'Trafford Council', 'note': 'Whalley Range / Firswood - No Article 4'},
        'M32': {'active': False, 'council': 'Trafford Council', 'note': 'No Article 4 currently'},
        'M33': {'active': False, 'council': 'Trafford Council', 'note': 'Sale - No Article 4'},
        
        # Bury
        'M25': {'active': False, 'council': 'Bury Council', 'note': 'Prestwich - No Article 4'},
        'M26': {'active': False, 'council': 'Bury Council', 'note': 'No Article 4 currently'},
        'M45': {'active': False, 'council': 'Bury Council', 'note': 'Whitefield - No Article 4'},
        
        # Rochdale
        'M24': {'active': False, 'council': 'Rochdale Council', 'note': 'Middleton - No Article 4'},
        
        # Oldham
        'M35': {'active': False, 'council': 'Oldham Council', 'note': 'No Article 4 currently'},
        
        # Tameside
        'M43': {'active': False, 'council': 'Tameside Council', 'note': 'No Article 4 currently'},
        
        # Stockport
        'SK1': {'active': False, 'council': 'Stockport Council', 'note': 'No Article 4 currently'},
        'SK2': {'active': False, 'council': 'Stockport Council', 'note': 'No Article 4 currently'},
        'SK3': {'active': False, 'council': 'Stockport Council', 'note': 'No Article 4 currently'},
        'SK4': {'active': False, 'council': 'Stockport Council', 'note': 'No Article 4 currently'},
        'SK5': {'active': False, 'council': 'Stockport Council', 'note': 'No Article 4 currently'},
        'SK6': {'active': False, 'council': 'Stockport Council', 'note': 'No Article 4 currently'},
        'SK7': {'active': False, 'council': 'Stockport Council', 'note': 'No Article 4 currently'},
        'SK8': {'active': True, 'council': 'Stockport Council', 'note': 'Cheadle / Gatley - Selective licensing areas'},
    }
    
    # Extract area code from postcode (e.g., M45 from M45 7EH)
    area_code = postcode.split()[0] if ' ' in postcode else postcode[:3]
    area_code = area_code.upper()
    
    if area_code in article_4_areas:
        info = article_4_areas[area_code]
        return {
            'is_article_4': info['active'],
            'council': info['council'],
            'note': info['note'],
            'area_code': area_code,
            'advice': 'Planning permission required for HMO conversion' if info['active'] else 'No Article 4 restrictions - permitted development applies'
        }
    else:
        # Unknown area - assume no Article 4
        return {
            'is_article_4': False,
            'council': 'Unknown Council',
            'note': 'Area not in database - verify with local council',
            'area_code': area_code,
            'advice': 'Check with local planning authority for HMO restrictions'
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
    if deal_type not in ['BTL', 'BRR', 'HMO', 'FLIP']:
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
    deposit_amount = purchase_price * (deposit_pct / 100)
    loan_amount = purchase_price - deposit_amount
    
    # Bridging loan calculations
    bridging_loan_details = None
    if purchase_type == 'bridging-loan':
        # Bridging loan: typically 0.75% per month, 12 months, 1% arrangement, 0.5% exit
        bridging_monthly_rate = float(data.get('bridgingMonthlyRate', 0.75))  # % per month
        bridging_term_months = int(data.get('bridgingTermMonths', 12))
        bridging_arrangement_fee_pct = float(data.get('bridgingArrangementFee', 1.0))  # 1%
        bridging_exit_fee_pct = float(data.get('bridgingExitFee', 0.5))  # 0.5%
        
        # Calculate bridging costs
        monthly_interest = loan_amount * (bridging_monthly_rate / 100)
        total_interest = monthly_interest * bridging_term_months
        arrangement_fee = loan_amount * (bridging_arrangement_fee_pct / 100)
        exit_fee = loan_amount * (bridging_exit_fee_pct / 100)
        total_bridging_cost = total_interest + arrangement_fee + exit_fee
        total_repayment = loan_amount + total_interest + exit_fee
        
        # Approximate APR
        bridging_apr = (bridging_monthly_rate * 12) + ((bridging_arrangement_fee_pct + bridging_exit_fee_pct) / bridging_term_months * 12)
        
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
        
        # For cashflow: bridging has no monthly payments (rolled up interest)
        monthly_mortgage = 0
        annual_mortgage = 0
    else:
        # Standard mortgage
        monthly_mortgage = (loan_amount * (interest_rate / 100)) / 12
        annual_mortgage = monthly_mortgage * 12
    
    # BRR/Flip specific calculations
    refurb_costs = float(data.get('refurbCosts', 0)) if deal_type in ['BRR', 'FLIP'] else 0
    arv = float(data.get('arv', 0)) if deal_type in ['BRR', 'FLIP'] else 0
    
    # HMO specific
    room_count = int(data.get('roomCount', 0)) if deal_type == 'HMO' else 0
    avg_room_rate = float(data.get('avgRoomRate', 0)) if deal_type == 'HMO' else 0
    
    if deal_type == 'HMO' and room_count > 0 and avg_room_rate > 0:
        monthly_rent = room_count * avg_room_rate
    
    # Income and expenses
    annual_rent = monthly_rent * 12
    management_costs = annual_rent * 0.10
    void_costs = (monthly_rent / 4.33) * 2  # 2 weeks
    maintenance_reserve = annual_rent * 0.08
    insurance = 480
    
    # Annual mortgage cost (0 for bridging since interest is rolled up)
    if purchase_type == 'bridging-loan':
        annual_mortgage = 0  # Interest rolled up, not paid monthly
    else:
        annual_mortgage = monthly_mortgage * 12
    
    total_annual_expenses = management_costs + void_costs + maintenance_reserve + insurance + annual_mortgage
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

@app.route('/api/test-scrapingbee')
def test_scrapingbee():
    """Test ScrapingBee configuration"""
    api_key = os.environ.get('SCRAPINGBEE_API_KEY')
    hardcoded_key = 'FLJ5HUFLWZTW46GNZDDXRD93VM3ONK6BO3YYEKRR9L77O1NA5BYNUVFTYXV3J9BJ056ZWF50ZRY1DNDA'
    
    # Determine which key is being used
    if api_key:
        key_source = "Environment Variable"
        key_prefix = api_key[:20]
        key_length = len(api_key)
    elif SCRAPINGBEE_API_KEY == hardcoded_key:
        key_source = "Hardcoded Fallback"
        key_prefix = SCRAPINGBEE_API_KEY[:20]
        key_length = len(SCRAPINGBEE_API_KEY)
    else:
        key_source = "Not Configured"
        key_prefix = None
        key_length = 0
    
    return jsonify({
        'status': 'configured' if SCRAPINGBEE_API_KEY else 'not_configured',
        'key_source': key_source,
        'key_prefix': key_prefix + "..." if key_prefix else None,
        'key_length': key_length,
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
        
        # Try ScrapingBee first (for protected sites like Rightmove, Zoopla, OTM)
        if SCRAPINGBEE_API_KEY:
            print("[extract-url] Trying ScrapingBee...")
            extracted_data = scrape_with_scrapingbee(url)
            if extracted_data and (extracted_data.get('address') or extracted_data.get('price')):
                print("[extract-url] ScrapingBee succeeded")
                return jsonify({
                    'success': True,
                    'data': extracted_data,
                    'message': 'Data extracted successfully'
                })
            print("[extract-url] ScrapingBee failed, trying fallback...")
        
        # Fallback to basic scraper
        print("[extract-url] Using basic scraper...")
        extracted_data = extract_property_from_url(url)
        
        if extracted_data and (extracted_data['address'] or extracted_data['price']):
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
    Get AI-powered analysis from OpenClaw
    This sends the data to the AI for enhanced insights
    """
    try:
        # Build market data context (PropertyData or Land Registry)
        market_context = ""
        if market_data and isinstance(market_data, dict):
            source = market_data.get('source', 'Unknown')
            
            if source == 'PropertyData API':
                # PropertyData format
                estimated_rent = market_data.get('estimated_rent')
                rental_confidence = market_data.get('rental_confidence')
                price_growth = market_data.get('price_growth_12m')
                avg_sold = market_data.get('avg_sold_price')
                area_score = market_data.get('area_score')
                transport_score = market_data.get('transport_score')
                
                if estimated_rent:
                    market_context += f"""
MARKET DATA (PropertyData API - Professional Grade):
- Estimated Market Rent: £{estimated_rent:,.0f}/month (Confidence: {rental_confidence})"""
                
                if price_growth is not None:
                    market_context += f"""
- 12-Month Price Growth: {price_growth:.1f}%"""
                
                if avg_sold:
                    market_context += f"""
- Average Sold Price: £{avg_sold:,.0f}"""
                
                if area_score:
                    market_context += f"""
- Area Quality Score: {area_score}/10"""
                
                if transport_score:
                    market_context += f"""
- Transport Links Score: {transport_score}/10"""
            
            elif source == 'Land Registry':
                # Land Registry format
                avg_price = market_data.get('average_price')
                trend = market_data.get('price_trend', {})
                recent_sales = market_data.get('recent_sales', [])
                
                if avg_price:
                    market_context += f"""
MARKET DATA (Land Registry - Free Government Data):
- Average Sold Price (12 months): £{avg_price:,.0f}"""
                
                if trend:
                    market_context += f"""
- Price Trend: {trend.get('trend', 'stable')} ({trend.get('change_percent', 0):.1f}% change)"""
                
                if recent_sales:
                    market_context += f"""
- Recent Comparable Sales:"""
                    for i, sale in enumerate(recent_sales[:3], 1):
                        market_context += f"""
  {i}. £{sale['price']:,} on {sale['date'][:10]} - {sale.get('street', 'N/A')}"""
            
            else:
                market_context = "MARKET DATA: Limited data available for this postcode"
        
        if not market_context:
            market_context = "MARKET DATA: No external market data available"
        
        # Build comprehensive prompt for AI
        prompt = f"""Analyze this UK property investment deal and provide detailed insights:

PROPERTY DETAILS:
- Address: {property_data.get('address', 'N/A')}
- Postcode: {property_data.get('postcode', 'N/A')}
- Deal Type: {property_data.get('dealType', 'BTL')}
- Purchase Price: £{property_data.get('purchasePrice', 0):,}
- Expected Monthly Rent: £{property_data.get('monthlyRent', 0)}

FINANCIAL METRICS:
- Gross Yield: {calculated_metrics.get('gross_yield', 0)}%
- Net Yield: {calculated_metrics.get('net_yield', 0)}%
- Monthly Cashflow: £{calculated_metrics.get('monthly_cashflow', 0)}
- Cash-on-Cash Return: {calculated_metrics.get('cash_on_cash', 0)}%
- Annual Net Income: £{calculated_metrics.get('net_annual_income', 0)}
- Deal Score: {calculated_metrics.get('deal_score', 0)}/100
- Investment Verdict: {calculated_metrics.get('verdict', 'REVIEW')}

{market_context}

Please provide:

1. INVESTMENT VERDICT (2-3 sentences): Summarize whether this is a good deal and why

2. KEY STRENGTHS (3-4 bullet points with HTML <br> tags): What makes this deal attractive

3. KEY RISKS (3-4 bullet points with HTML <br> tags): What could go wrong or needs investigation

4. AREA ASSESSMENT (2-3 sentences): Quick assessment of the postcode area for rental demand

5. RECOMMENDED NEXT STEPS (4-5 numbered items with HTML <br> tags): Actionable steps

Format your response as JSON:
{{
    "verdict": "...",
    "strengths": "...",
    "risks": "...",
    "area": "...",
    "next_steps": "..."
}}"""

        # For now, return mock AI response (integrate with OpenClaw API later)
        # This simulates what the AI would return
        verdict = calculated_metrics.get('verdict', 'REVIEW')
        score = calculated_metrics.get('deal_score', 50)
        
        if verdict == 'PROCEED':
            ai_response = {
                "verdict": f"This property represents a strong investment opportunity with a deal score of {score}/100. The gross yield of {calculated_metrics.get('gross_yield', 0)}% exceeds market averages, and the monthly cashflow of £{calculated_metrics.get('monthly_cashflow', 0)} provides a healthy buffer for expenses and void periods. The fundamentals support a PROCEED recommendation.",
                "strengths": "• Strong gross yield above 6% target, indicating good rental demand<br>• Positive monthly cashflow provides financial buffer<br>• Healthy cash-on-cash return above 8%<br>• Property appears priced fairly for the area",
                "risks": "• Market conditions could affect future capital growth<br>• Void periods may be longer than estimated<br>• Maintenance costs could exceed 8% assumption<br>• Interest rate increases would impact cashflow",
                "area": f"The {property_data.get('postcode', 'area')} postcode shows good rental demand with reasonable yields. Transport links and local amenities support tenant interest.",
                "next_steps": "1. Verify rental comparables with local agents<br>2. Arrange property viewing and inspection<br>3. Get RICS survey (£400-600)<br>4. Confirm mortgage availability<br>5. Instruct solicitor for preliminary checks"
            }
        elif verdict == 'REVIEW':
            ai_response = {
                "verdict": f"This deal requires further investigation with a score of {score}/100. While some metrics are acceptable, borderline cashflow or yield suggests caution. Consider negotiating the price or exploring alternative strategies.",
                "strengths": "• Some metrics meet investment criteria<br>• Potential for value add through refurbishment<br>• Area may have growth potential<br>• Property type suits rental market",
                "risks": "• Cashflow below £200 target reduces safety margin<br>• Yield may not justify the risk<br>• Higher void risk due to area or property condition<br>• Exit strategy concerns if market slows",
                "area": f"The {property_data.get('postcode', 'area')} area shows mixed signals. Research comparable rents and recent sales carefully.",
                "next_steps": "1. Research comparable sales and rents thoroughly<br>2. Investigate why metrics are below target<br>3. Consider negotiating purchase price down<br>4. Explore BRR or HMO strategy alternatives<br>5. Get professional opinion on achievable rent"
            }
        else:
            ai_response = {
                "verdict": f"This deal scores {score}/100 and falls below investment criteria. Poor yield, negative cashflow, or high risk factors suggest avoiding this property. Better opportunities likely exist elsewhere.",
                "strengths": "• Property exists in investable area<br>• May have unique features<br>• Could suit different strategy",
                "risks": "• Yield significantly below 6% target<br>• Cashflow insufficient or negative<br>• High risk of capital loss<br>• Better deals available elsewhere",
                "area": f"The {property_data.get('postcode', 'area')} area may have better opportunities. Continue searching.",
                "next_steps": "1. Avoid this deal - numbers don't work<br>2. Continue searching for better opportunities<br>3. Adjust search criteria if needed<br>4. Consider different areas with higher yields"
            }
        
        return ai_response
        
    except Exception as e:
        app.logger.error(f'AI analysis error: {str(e)}')
        return {
            "verdict": "AI analysis temporarily unavailable. Please review the calculated metrics.",
            "strengths": "• Please review the financial metrics<br>• Consider local market knowledge",
            "risks": "• Always verify figures independently<br>• Get professional advice",
            "area": "Area assessment unavailable",
            "next_steps": "1. Verify all calculations<br>2. Research the area independently<br>3. Consult local property experts"
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
        
        # Get sales valuation
        sales_valuation = None
        if property_data.is_configured() and postcode:
            try:
                valuation = property_data.get_sales_valuation(postcode, bedrooms)
                if 'estimate' in valuation:
                    sales_valuation = {
                        'estimate': valuation['estimate'].get('sale_price'),
                        'confidence': valuation.get('confidence'),
                        'range': valuation.get('range', {})
                    }
            except Exception as e:
                app.logger.warning(f'Could not get sales valuation: {e}')
        
        # Generate comparable data sections (workaround for limited PropertyData API)
        # SOLD COMPARABLES - Use Land Registry or estimates
        sold_comparables = market_data.get('comparable_sales', [])
        if not sold_comparables and market_data.get('recent_sales'):
            sold_comparables = [
                {
                    'address': f"{s.get('street', 'Similar Property')}, {postcode}",
                    'price': s.get('price', 0),
                    'bedrooms': bedrooms,
                    'date': s.get('date', 'Recent'),
                    'type': data.get('property_type', 'House').title()
                }
                for s in market_data['recent_sales'][:5]
            ]
        # Fallback: generate estimated comparables based on purchase price
        if not sold_comparables:
            avg_price = float(str(calculated_metrics.get('purchase_price', 200000)).replace(',', ''))
            sold_comparables = [
                {
                    'address': f"Similar 3-bed property, {postcode}",
                    'price': int(avg_price * 0.95),
                    'bedrooms': bedrooms,
                    'date': 'Recent sale',
                    'type': 'Semi-Detached',
                    'note': 'Estimated comparable'
                },
                {
                    'address': f"Similar 3-bed property, {postcode}",
                    'price': int(avg_price * 1.02),
                    'bedrooms': bedrooms,
                    'date': 'Recent sale',
                    'type': 'Semi-Detached',
                    'note': 'Estimated comparable'
                },
                {
                    'address': f"Similar 2-bed property, {postcode}",
                    'price': int(avg_price * 0.85),
                    'bedrooms': max(1, bedrooms - 1),
                    'date': 'Recent sale',
                    'type': 'Terraced',
                    'note': 'Estimated comparable (smaller)'
                }
            ]
        
        # RENT COMPARABLES - Use estimated rent or PropertyData
        monthly_rent = int(data.get('monthlyRent', 0))
        rent_comparables = []
        if market_data.get('estimated_rent'):
            market_rent = market_data['estimated_rent']
            rent_comparables = [
                {
                    'address': f"3-bed property, {postcode}",
                    'monthly_rent': market_rent,
                    'bedrooms': bedrooms,
                    'type': 'Similar property',
                    'source': 'PropertyData estimate'
                }
            ]
        elif monthly_rent > 0:
            # Generate comparables around the expected rent
            rent_comparables = [
                {
                    'address': f"3-bed house, {postcode}",
                    'monthly_rent': int(monthly_rent * 0.95),
                    'bedrooms': bedrooms,
                    'type': 'Terraced',
                    'source': 'Estimated comparable'
                },
                {
                    'address': f"3-bed house, {postcode}",
                    'monthly_rent': monthly_rent,
                    'bedrooms': bedrooms,
                    'type': 'Semi-Detached',
                    'source': 'Target property estimate'
                },
                {
                    'address': f"3-bed house, {postcode}",
                    'monthly_rent': int(monthly_rent * 1.05),
                    'bedrooms': bedrooms,
                    'type': 'Detached',
                    'source': 'Estimated comparable'
                }
            ]
        
        # HOUSE VALUATION - Use sales valuation, Land Registry, or estimate
        house_valuation = sales_valuation or {}
        if not house_valuation.get('estimate'):
            purchase_price = int(data.get('purchasePrice', 0))
            # Generate estimate based on purchase price with typical negotiation range
            house_valuation = {
                'estimate': purchase_price,
                'confidence': 'Medium (based on asking price)',
                'range': {
                    'low': int(purchase_price * 0.95),
                    'high': int(purchase_price * 1.05)
                },
                'source': 'Market estimate',
                'note': 'Based on current listing price. Professional valuation recommended.'
            }
        
        # Combine results
        results = {
            **calculated_metrics,
            'ai_verdict': ai_insights['verdict'],
            'ai_strengths': ai_insights['strengths'],
            'ai_risks': ai_insights['risks'],
            'ai_area': ai_insights['area'],
            'ai_next_steps': ai_insights['next_steps'],
            # Add comparable data sections
            'sold_comparables': sold_comparables,
            'rent_comparables': rent_comparables,
            'house_valuation': house_valuation,
            # Legacy fields
            'comparable_sales': market_data.get('comparable_sales', []),
            'comparable_listings': market_data.get('comparable_listings', []),
            'avg_sold_price': market_data.get('avg_sold_price'),
            'avg_asking_price': market_data.get('avg_asking_price'),
            'sales_valuation': sales_valuation,
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

@app.route('/api/propertydata/rental-valuation', methods=['POST'])
@limiter.limit("10 per minute")
def get_propertydata_rental():
    """Get rental valuation from PropertyData API (premium)"""
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
        
        # Debug: Log API key info (masked)
        key_length = len(property_data.api_key) if hasattr(property_data, 'api_key') else 0
        key_prefix = property_data.api_key[:10] if key_length > 0 else 'NONE'
        app.logger.info(f"[PropertyData] Key prefix: {key_prefix}..., Length: {key_length}")
        app.logger.info(f"[PropertyData] Postcode: {postcode}, Bedrooms: {bedrooms}")
        
        # Check if key seems wrong
        if key_length < 20:
            return jsonify({
                'success': False,
                'message': f'API key appears invalid (length: {key_length}). Check PROPERTY_DATA_API_KEY environment variable.',
                'debug': {
                    'key_length': key_length,
                    'key_prefix': key_prefix,
                    'env_var_set': bool(os.environ.get('PROPERTY_DATA_API_KEY'))
                }
            }), 500
        
        # Get rental valuation from PropertyData
        result = property_data.get_rental_valuation(postcode, bedrooms)
        
        app.logger.info(f"[PropertyData] Result: {result}")
        
        if 'error' in result:
            return jsonify({
                'success': False,
                'message': result['error'],
                'debug': {
                    'key_length': len(property_data.api_key),
                    'postcode': postcode,
                    'bedrooms': bedrooms
                }
            }), 500
        
        return jsonify({
            'success': True,
            'data': result,
            'source': 'PropertyData API'
        })
        
    except Exception as e:
        app.logger.error(f'PropertyData rental valuation error: {str(e)}')
        return jsonify({
            'success': False,
            'message': 'Error fetching rental valuation. Please try again.'
        }), 500

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
