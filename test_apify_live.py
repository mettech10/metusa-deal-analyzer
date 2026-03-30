#!/usr/bin/env python3
"""
Standalone Apify diagnostic test.
Run this to verify your token and actors work.

Usage:
    APIFY_API_TOKEN=your_token_here python test_apify_live.py

Or set APIFY_API_TOKEN in your environment first.
"""
import os
import json
import requests
import sys

APIFY_API_TOKEN = os.environ.get('APIFY_API_TOKEN', '')

if not APIFY_API_TOKEN:
    print("ERROR: APIFY_API_TOKEN is not set.")
    print("Run:  APIFY_API_TOKEN=your_token python test_apify_live.py")
    sys.exit(1)

print(f"Token: {APIFY_API_TOKEN[:8]}...{APIFY_API_TOKEN[-4:]}")
print()

# ── Step 1: Verify token with /users/me ─────────────────────────────────────
print("=" * 60)
print("STEP 1: Verify API token")
print("=" * 60)
try:
    resp = requests.get(
        f'https://api.apify.com/v2/users/me?token={APIFY_API_TOKEN}',
        timeout=10
    )
    print(f"HTTP {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json().get('data', {})
        print(f"  Username:  {data.get('username')}")
        print(f"  Plan:      {data.get('plan', {}).get('id', 'unknown')}")
        print(f"  Email:     {data.get('email')}")
        usage = data.get('plan', {}).get('usageTotal', {})
        print(f"  Usage:     ${usage.get('USD', 0):.2f} of monthly credit used")
    else:
        print(f"  FAILED: {resp.text[:300]}")
        sys.exit(1)
except Exception as e:
    print(f"  EXCEPTION: {e}")
    sys.exit(1)

print()

# ── Step 2: Verify each actor exists ────────────────────────────────────────
ACTORS = {
    'Rightmove':    'dhrumil/rightmove-scraper',
    'OnTheMarket':  'shahidirfan/onthemarket-property-scraper',
    'SpareRoom':    'memo23/spareroom-scraper',
}

print("=" * 60)
print("STEP 2: Verify actor IDs exist")
print("=" * 60)
for name, actor_id in ACTORS.items():
    api_id = actor_id.replace('/', '~')
    resp = requests.get(
        f'https://api.apify.com/v2/acts/{api_id}?token={APIFY_API_TOKEN}',
        timeout=10
    )
    if resp.status_code == 200:
        info = resp.json().get('data', {})
        print(f"  {name} ({actor_id}): EXISTS ✓")
        print(f"    Title: {info.get('title', 'N/A')}")
        print(f"    Runs:  {info.get('stats', {}).get('totalRuns', 'N/A')}")
    else:
        print(f"  {name} ({actor_id}): HTTP {resp.status_code} ✗")
        print(f"    {resp.text[:200]}")
    print()

# ── Step 3: Live test — scrape a single Rightmove listing ──────────────────
print("=" * 60)
print("STEP 3: Live scrape test — Rightmove")
print("=" * 60)

TEST_URL = "https://www.rightmove.co.uk/properties/156561461"
actor_id = ACTORS['Rightmove']
input_payload = {'startUrls': [{'url': TEST_URL}], 'maxItems': 1}

print(f"  URL:     {TEST_URL}")
print(f"  Actor:   {actor_id}")
print(f"  Payload: {json.dumps(input_payload)}")
print()

api_url = (
    f'https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items'
    f'?token={APIFY_API_TOKEN}&timeout=60&memory=512'
)

try:
    print("  Sending request (this may take 30-60 seconds)...")
    resp = requests.post(api_url, json=input_payload, timeout=75)
    print(f"  HTTP {resp.status_code}")
    print(f"  Content-Length: {len(resp.content)} bytes")
    print(f"  Content-Type: {resp.headers.get('Content-Type', 'N/A')}")
    print()

    if resp.status_code == 200:
        try:
            data = resp.json()
            print(f"  Response type: {type(data).__name__}")
            if isinstance(data, list):
                print(f"  Items returned: {len(data)}")
                if data:
                    print()
                    print("  RAW FIRST ITEM:")
                    print("  " + json.dumps(data[0], indent=2, default=str)[:2000])
                else:
                    print("  WARNING: Empty dataset — actor ran but returned 0 items.")
                    print("  This could mean:")
                    print("    - The listing URL is invalid or has been removed")
                    print("    - The actor's scraping logic failed silently")
            else:
                print("  RAW RESPONSE (not a list):")
                print("  " + json.dumps(data, indent=2, default=str)[:2000])
        except json.JSONDecodeError:
            print("  Response is not JSON:")
            print("  " + resp.text[:500])
    elif resp.status_code == 402:
        print("  PAYMENT REQUIRED — your free credit may be exhausted.")
        print("  Check: https://console.apify.com/billing")
    elif resp.status_code == 404:
        print("  ACTOR NOT FOUND — the actor ID is wrong.")
    elif resp.status_code == 401:
        print("  UNAUTHORIZED — your API token is invalid.")
    else:
        print(f"  ERROR RESPONSE:")
        print(f"  {resp.text[:500]}")
except requests.exceptions.Timeout:
    print("  TIMEOUT — request took longer than 75 seconds.")
except Exception as e:
    print(f"  EXCEPTION: {type(e).__name__}: {e}")

print()
print("=" * 60)
print("TEST COMPLETE")
print("=" * 60)
