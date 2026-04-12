"""
SpareRoom scraper — Bright Data Browser API edition.

Replaces the Apify ``memo23/spareroom-scraper`` actor (see app.py
``scrape_spareroom_with_apify``). Produces dicts in the EXACT same shape so
the existing ``/api/comparables`` endpoint keeps working with a one-line swap.

Two modes:
  LIVE  — on-demand per postcode, single page, 30s hard timeout, returns
          results in-process. Used by ``/api/comparables`` and the new
          ``/api/scraper/live`` endpoint.
  BULK  — iterates many UK postcode districts, paginates up to N pages each,
          UPSERTS rows into ``spareroom_listings``, logs progress to
          ``scrape_logs``. Skips any district scraped in the last 13 days.
          Used by the cron-triggered ``/api/scraper/trigger-bulk`` endpoint.

Shape returned by ``scrape_live`` (per listing dict) — MUST match Apify output:
    {
      'title': str,            # ≤120 chars
      'rentPcm': int | None,   # normalised to monthly £
      'roomType': str,         # 'single' | 'double' | 'en-suite' | 'studio'
      'billsIncluded': bool | None,
      'area': str,             # ≤60 chars
      'distanceKm': float | None,
      'listingUrl': str,
      'imageUrl': str,
      'source': 'spareroom',
    }
"""

import os
import re
import time
import random
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from brightdata_browser import BrightDataBrowser, PLAYWRIGHT_AVAILABLE

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
except ImportError:
    class PlaywrightTimeout(Exception):  # type: ignore
        pass

# Supabase client (lazy import so the module still loads if the env is missing)
try:
    from supabase import create_client, Client as SupabaseClient
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    SupabaseClient = None  # type: ignore
    print("[SpareRoom] supabase package not installed — bulk persistence disabled")


# ── Config ───────────────────────────────────────────────────────────────────
LIVE_TIMEOUT_SECS = 60
BULK_PAGE_TIMEOUT_SECS = 60
BULK_SKIP_DAYS = 13
DEFAULT_CONCURRENCY = int(os.environ.get("SCRAPER_CONCURRENCY", "5") or 5)
DEFAULT_DELAY_MS = int(os.environ.get("SCRAPER_DELAY_MS", "1500") or 1500)


# ── Helpers ──────────────────────────────────────────────────────────────────
def _sanitise(text: Any, max_len: int = 500) -> str:
    """Collapse whitespace, strip control chars, truncate. Safe for DB writes."""
    if text is None:
        return ""
    s = str(text)
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > max_len:
        s = s[:max_len].rstrip()
    return s


def _parse_price_to_pcm(price_text: str) -> Optional[int]:
    """Normalise a SpareRoom price string to £/month.

    SpareRoom shows prices as "£650 pcm", "£150 pw", "£3,250 per month", etc.
    Weekly prices convert to monthly via ``* 52 / 12``.
    """
    if not price_text:
        return None
    text = str(price_text).lower().replace(",", "")
    m = re.search(r"£\s*(\d+(?:\.\d+)?)", text)
    if not m:
        return None
    try:
        val = int(float(m.group(1)))
    except (ValueError, TypeError):
        return None
    if val <= 0:
        return None

    weekly = any(token in text for token in [" pw", "p/w", "per week", "weekly", "/week", " pw)"])
    if weekly:
        return round(val * 52 / 12)
    return val


def _classify_room_type(raw: str) -> str:
    text = (raw or "").lower()
    if "studio" in text:
        return "studio"
    if "en-suite" in text or "ensuite" in text or "en suite" in text:
        return "en-suite"
    if "single" in text:
        return "single"
    return "double"


def _classify_bills(raw: str) -> Optional[bool]:
    text = (raw or "").lower()
    if "bills inc" in text or "bills included" in text or "inc. bills" in text:
        return True
    if "bills exc" in text or "bills excluded" in text or "exc. bills" in text:
        return False
    return None


def _abs_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        return f"https:{href}"
    if href.startswith("/"):
        return f"https://www.spareroom.co.uk{href}"
    return f"https://www.spareroom.co.uk/{href}"


def _extract_listing_id(url: str) -> Optional[str]:
    """SpareRoom ad URLs look like /flatshare/flatshare_detail.pl?flatshare_id=18044172"""
    if not url:
        return None
    m = re.search(r"flatshare_id[=/](\d+)", url)
    if m:
        return m.group(1)
    m = re.search(r"/(\d{6,})(?:[/?]|$)", url)
    if m:
        return m.group(1)
    return None


def _area_code(district_or_postcode: str) -> str:
    """Extract the alpha area code from a postcode district or full postcode.

    Used to filter out sponsored/featured SpareRoom listings from other cities:
        "M14"       -> "M"        (Manchester)
        "M14 5RE"   -> "M"        (Manchester)
        "SE15"      -> "SE"       (South East London)
        "LS6"       -> "LS"       (Leeds)
        "Manchester"-> ""         (place name — no filtering)
    """
    if not district_or_postcode:
        return ""
    m = re.match(r"\s*([A-Za-z]{1,2})\d", district_or_postcode.strip())
    return m.group(1).upper() if m else ""


def _build_search_url(location: str, offset: int = 0) -> str:
    """SpareRoom search URL.

    Important: Bright Data's Scraping Browser enforces robots.txt on SpareRoom
    and the ``search_type=rooms&where=`` variant is DISALLOWED (returns a
    "brob" error). The ``search_by=postcode`` variant IS allowed by robots.txt
    so we use that for postcode-like inputs. Place-name inputs use a third
    variant (``flatshares/<city>``) which is also robots-allowed.

    ``location`` can be:
      - a full postcode ("M14 4AB") — district extracted for the query
      - a district ("M14", "LS6", "SE15")
      - a place name ("Manchester", "Leeds")
    """
    raw = _sanitise(location, 40)
    first_token = raw.split()[0] if raw else ""
    is_postcode_like = bool(re.match(r"^[A-Za-z]{1,2}\d", first_token))

    if is_postcode_like:
        loc = first_token.replace(" ", "+")
        # 5-mile radius: the original 2 miles returned 0 genuine results in
        # less dense areas (postcode search would fall back to nationwide
        # "Featured/Boosted" ads, which we then rejected, leaving the page
        # empty). 5 miles is a reasonable HMO comparable range.
        # NOTE: do NOT add per=100 — it triggers Bright Data's robots.txt
        # enforcement ("brob" error) even though the base URL is allowed.
        return (
            f"https://www.spareroom.co.uk/flatshare/?search_by=postcode"
            f"&search={loc}&miles_from_max=5&rooms_for=0&rooms_offered=1"
            f"&mode=list&offset={offset}"
        )

    # Place-name branch — use the /flatshares/<city> path which is
    # robots-allowed, rather than /flatshare/?search_type=rooms&where=...
    # (the latter is blocked by robots.txt → Bright Data "brob" error).
    city_slug = raw.lower().replace(" ", "-")
    return (
        f"https://www.spareroom.co.uk/flatshares/{city_slug}"
        f"?mode=list&offset={offset}"
    )


def _hash_listing_key(listing_id: str, location: str) -> str:
    return hashlib.sha256(f"{listing_id}:{location}".encode()).hexdigest()[:32]


# ── Supabase client factory ──────────────────────────────────────────────────
_supa_client: Optional[Any] = None


def _get_supabase() -> Optional[Any]:
    """Lazy-init a service-role Supabase client. Returns None if unconfigured."""
    global _supa_client
    if _supa_client is not None:
        return _supa_client
    if not SUPABASE_AVAILABLE:
        return None
    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("[SpareRoom] Supabase env vars missing — persistence disabled")
        return None
    try:
        _supa_client = create_client(url, key)
        return _supa_client
    except Exception as e:  # noqa: BLE001
        print(f"[SpareRoom] Supabase init error: {e}")
        return None


# ── Parser (runs inside page.evaluate for robustness) ────────────────────────
# SpareRoom's list view markup is server-rendered (good for us): each listing
# is an <article class="panel panel-listing"> or similar. We extract everything
# client-side via JS to survive layout tweaks without re-deploying python.
PARSE_JS = r"""
() => {
  // Promoted / paid-ad badge text. "New today" is EXCLUDED — it's shown
  // on genuine new listings, not just promoted ones, so treating it as
  // paid would reject legit comps.
  const PROMO_TEXT_RE = /\b(boosted|featured|sponsored|promoted|bold[-\s]?ad)\b/i;

  // fad_click.pl URLs are SpareRoom's paid-ad redirect endpoint — if a
  // card's primary link points here, it's a paid ad no matter what the
  // text says.
  const isPaidHref = (href) => /\/(?:flatshare|ad)\/fad_click\.pl/i.test(href || '');

  const normaliseId = (href) => {
    if (!href) return '';
    const m = href.match(/flatshare_id=(\d+)/) || href.match(/fad_id=(\d+)/);
    return m ? m[1] : href;  // stable key for dedupe
  };

  const extract = (card, anchor) => {
    const a = anchor ||
              card.querySelector('a[href*="flatshare_detail"], a[href*="fad_click.pl"], a[href*="/flatshare/"]') ||
              card.querySelector('a');
    const img = card.querySelector('img');
    const text = (card.innerText || '').trim();
    const href = (a && a.href) || '';

    // ── Promoted / featured detection ────────────────────────────────
    // 1. Definitive: href points to fad_click.pl (paid-ad redirect)
    // 2. Class names on the card itself (NOT descendants — too noisy)
    // 3. Card inner text contains a promo badge word
    let isPromoted = false;
    let promoReason = '';
    if (isPaidHref(href)) {
      isPromoted = true;
      promoReason = 'fad_click_url';
    } else {
      const ownClass = (card.className || '').toLowerCase();
      if (/bold[-_]?ad|boost|featur|promo|sponsor/.test(ownClass)) {
        isPromoted = true;
        promoReason = 'class:' + ownClass.slice(0, 40);
      } else if (PROMO_TEXT_RE.test(text)) {
        isPromoted = true;
        promoReason = 'text_badge';
      }
    }

    // ── Explicit location element ────────────────────────────────────
    let locationText = '';
    const locEl = card.querySelector(
      '.listingLocation, .listing-location, .location, ' +
      '[class*="ocation"], [class*="rea-name"], [class*="ostcode"]'
    );
    if (locEl) locationText = (locEl.innerText || '').trim();

    return {
      href: href,
      title: ((card.querySelector('h2, h3, .listingTitle, .listing-title') || a || {}).innerText || '').trim().slice(0, 160),
      text: text.slice(0, 1200),
      image: (img && (img.src || img.getAttribute('data-src'))) || '',
      listingId: card.getAttribute('data-listing-id') || normaliseId(href),
      locationText: locationText.slice(0, 120),
      isPromoted: isPromoted,
      promoReason: promoReason,
      dedupeKey: normaliseId(href),
    };
  };

  // Pass 1: structured card containers.
  // Prefer children of the main .listing-results container — everything
  // outside of it (the "Featured at top" strip, sidebar recommendations,
  // etc.) is noise we want to drop. Fall back to broader selectors only
  // when the main list is empty/missing.
  const mainList = document.querySelector('.listing-results, ul.listing-results, ol.listing-results');
  let cardsRaw;
  if (mainList) {
    cardsRaw = Array.from(mainList.querySelectorAll(
      'li[data-listing-id], li.listing-result, li.panel-listing, ' +
      'article.panel-listing, article[class*="listing"]'
    ));
    // Also include direct <li> children that wrap anchors to flatshare_detail
    if (cardsRaw.length === 0) {
      cardsRaw = Array.from(mainList.querySelectorAll('li')).filter(
        li => li.querySelector('a[href*="flatshare_detail.pl"]')
      );
    }
  } else {
    cardsRaw = Array.from(document.querySelectorAll(
      'li[data-listing-id], article.panel-listing, article[class*="listing"], ' +
      'li.listing-result, li.panel-listing'
    ));
  }

  // Pass 2: anchor fallback — always run, then merge for maximum coverage
  const anchors = Array.from(document.querySelectorAll(
    'a[href*="flatshare_detail.pl"]'
  ));

  const results = [];
  const seenKeys = new Set();
  const pushUnique = (obj) => {
    const k = obj.dedupeKey || obj.href;
    if (!k || seenKeys.has(k)) return;
    seenKeys.add(k);
    results.push(obj);
  };

  cardsRaw.forEach(c => pushUnique(extract(c, null)));
  anchors.forEach(a => {
    const card = a.closest('li, article, div') || a;
    pushUnique(extract(card, a));
  });

  return results;
}
"""

DIAG_JS = r"""
() => {
  const body = (document.body && document.body.innerText) || '';
  const html = (document.documentElement && document.documentElement.outerHTML) || '';
  const mainList = document.querySelector('.listing-results, ul.listing-results, ol.listing-results');
  const mainAnchors = mainList
    ? Array.from(mainList.querySelectorAll('a[href*="flatshare_detail.pl"]'))
    : [];
  const allAnchors = Array.from(document.querySelectorAll('a[href*="flatshare_detail.pl"]'));

  // Cookie-consent / login-wall detection
  const cookieBtn = document.querySelector(
    '#onetrust-accept-btn-handler, [id*="cookie-accept"], [id*="accept-cookie"], ' +
    'button[class*="cookie-accept"], button[class*="accept-all"], ' +
    'button[data-testid*="accept"]'
  );
  const hasLoginWall = /please\s+sign\s+in|log\s*in\s+to\s+view|create\s+an?\s+account/i.test(body);
  const hasCookieBanner = /we\s+use\s+cookies|cookie\s+preferences|accept\s+cookies|manage\s+cookies/i.test(body);

  // Grab a snapshot of the first .listing-results child's outerHTML so
  // we can see what SpareRoom is actually rendering (trimmed to 800 chars).
  let mainListHtmlPreview = '';
  if (mainList) {
    const firstLi = mainList.querySelector('li');
    if (firstLi) mainListHtmlPreview = (firstLi.outerHTML || '').slice(0, 800);
  }

  // Also grab a body text snippet from offset 500-2500 so we can see
  // what's on the page past the usual header/nav chrome.
  const bodySnippet = body.slice(500, 2500);

  // Scan raw HTML for any flatshare_id occurrences (even in data-*
  // attributes, script tags, JSON blobs). Use a plain regex loop
  // rather than matchAll for broader JS engine compatibility.
  let uniqueHtmlIds = [];
  let jsonBlobCount = 0;
  let hiddenResults = 0;
  try {
    const idRe = /flatshare_id[=:][^0-9]{0,3}(\d{6,})/gi;
    const found = new Set();
    let m;
    while ((m = idRe.exec(html)) !== null) {
      found.add(m[1]);
      if (found.size > 200) break;  // safety cap
    }
    uniqueHtmlIds = Array.from(found);
    const jsonRe = /"listings?"\s*:\s*\[/gi;
    while ((m = jsonRe.exec(html)) !== null) {
      jsonBlobCount++;
      if (jsonBlobCount > 20) break;
    }
    hiddenResults = document.querySelectorAll(
      '[style*="display:none"] .listing-result, [style*="display: none"] .listing-result, ' +
      '[hidden] .listing-result, .hidden .listing-result'
    ).length;
  } catch (e) {
    uniqueHtmlIds = ['SCAN_ERR:' + (e.message || '').slice(0, 80)];
  }

  return {
    cards_selector_count: document.querySelectorAll(
      'li[data-listing-id], article.panel-listing, article[class*="listing"], ' +
      'li.listing-result, li.panel-listing'
    ).length,
    anchors_count: allAnchors.length,
    main_list_anchors: mainAnchors.length,
    main_list_present: !!mainList,
    main_list_li_count: mainList ? mainList.querySelectorAll('li').length : 0,
    paid_anchors_count: document.querySelectorAll('a[href*="fad_click.pl"]').length,
    body_text_len: body.length,
    html_len: html.length,
    unique_flatshare_ids_in_html: uniqueHtmlIds.length,
    first_html_ids: uniqueHtmlIds.slice(0, 15),
    json_blob_count: jsonBlobCount,
    hidden_results_count: hiddenResults,
    title: document.title || '',
    has_no_results_msg: /no\s+results|0\s+results|couldn't find|no matches|widen your search|try a different/i.test(body),
    has_login_wall: hasLoginWall,
    has_cookie_banner: hasCookieBanner,
    cookie_btn_present: !!cookieBtn,
    cookie_btn_selector: cookieBtn ? (cookieBtn.id || cookieBtn.className || 'found').slice(0, 80) : '',
    main_list_classes: Array.from(document.querySelectorAll('ul, ol'))
      .map(el => el.className || '')
      .filter(c => /list|result|panel/i.test(c))
      .slice(0, 10),
    results_count_badge: (body.match(/(\d[\d,]*)\s+results?/i) || [])[0] || '',
    main_list_html_preview: mainListHtmlPreview,
    body_snippet: bodySnippet,
  };
}
"""

SCROLL_JS = r"""
async () => {
  // Accept cookie consent if present — SpareRoom's OneTrust banner can
  // block the results list from rendering.
  const cookieBtn = document.querySelector(
    '#onetrust-accept-btn-handler, [id*="cookie-accept"], [id*="accept-cookie"], ' +
    'button[class*="accept-all"], button[class*="cookie-accept"]'
  );
  if (cookieBtn) {
    try { cookieBtn.click(); } catch(e) {}
    await new Promise(r => setTimeout(r, 500));
  }

  // Dismiss any overlay that might cover the main list
  document.querySelectorAll(
    '[class*="modal"][class*="open"], [class*="overlay"][class*="show"]'
  ).forEach(el => {
    const close = el.querySelector('[class*="close"], button[aria-label*="close" i]');
    if (close) { try { close.click(); } catch(e) {} }
  });

  // SpareRoom lazy-loads additional cards as you scroll past the first
  // "featured at top" bucket. Scroll in chunks with pauses so everything
  // below the fold hydrates before we extract.
  const step = Math.max(600, window.innerHeight);
  for (let y = 0; y < 8000; y += step) {
    window.scrollTo(0, y);
    await new Promise(r => setTimeout(r, 500));
  }
  window.scrollTo(0, 0);
  await new Promise(r => setTimeout(r, 500));
}
"""


_POSTCODE_RE = re.compile(
    r"\b([A-Z]{1,2}\d{1,2}[A-Z]?)(?:\s*\d[A-Z]{2})?\b"
)


def _parse_raw_cards(
    raw_cards: List[Dict[str, Any]],
    location: str,
    stats: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Turn the raw card objects pulled from the DOM into the canonical shape.

    Filters out SpareRoom sponsored/featured listings whose postcode area code
    doesn't match the searched location. SpareRoom injects paid listings from
    all over the UK at the top of every search, ignoring the 2-mile radius
    filter — we reject them here so HMO rent averages stay geographically
    accurate.

    Two rejection passes:
      1. Promoted / bold-ad / boosted / featured / sponsored badge → drop
         unconditionally. These are never useful comps.
      2. Postcode area mismatch (e.g. card says "PE3" when we searched "M14")
         → drop. Only applies when ``location`` is postcode-like.

    For place-name searches like "Manchester" we can't derive an area code,
    so only the promoted filter runs.
    """
    out: List[Dict[str, Any]] = []
    seen_ids: set = set()

    # Area code of the searched location — empty string for place-name searches
    search_code = _area_code(location)
    rejected_wrong_area = 0
    rejected_promoted = 0
    rejected_no_id = 0
    rejected_dupes = 0
    rejection_samples: List[Dict[str, Any]] = []

    def _sample(reason: str, card: Dict[str, Any]) -> None:
        if len(rejection_samples) < 6:
            rejection_samples.append({
                "reason": reason,
                "href": (card.get("href") or "")[:160],
                "title": (card.get("title") or "")[:80],
                "locationText": (card.get("locationText") or "")[:60],
                "isPromoted": bool(card.get("isPromoted")),
                "text_preview": (card.get("text") or "")[:140],
            })

    for card in raw_cards:
        # ── Pass 1: promoted / bold-ad drop ─────────────────────────────
        if card.get("isPromoted"):
            rejected_promoted += 1
            _sample("promoted", card)
            continue

        href = _abs_url(card.get("href", ""))
        listing_id = card.get("listingId") or _extract_listing_id(href) or ""
        if not listing_id:
            rejected_no_id += 1
            _sample("no_id", card)
            continue
        if listing_id in seen_ids:
            rejected_dupes += 1
            continue
        seen_ids.add(listing_id)

        text = card.get("text") or ""
        title = _sanitise(card.get("title") or "Room to rent", 120)
        location_text = card.get("locationText") or ""

        # Price — look for £xxx in the card text
        price_match = re.search(
            r"£\s*[\d,]+(?:\.\d+)?(?:\s*(?:pcm|pw|per\s*(?:month|week)))?",
            text,
            re.IGNORECASE,
        )
        rent_pcm = _parse_price_to_pcm(price_match.group(0)) if price_match else None

        # Room type + bills — search the card text and title
        combined = f"{title} {text}".lower()
        room_type = _classify_room_type(combined)
        bills = _classify_bills(combined)

        # Available from — "Available now", "Available 15 Apr"
        avail_match = re.search(r"available\s+([a-z0-9 ]{1,20})", combined)
        available_from = avail_match.group(1).strip() if avail_match else None

        # Number of rooms in the household
        rooms_match = re.search(r"(\d+)\s*(?:bed)?rooms?", combined)
        num_rooms = int(rooms_match.group(1)) if rooms_match else None

        # ── Area label extraction ──────────────────────────────────────
        # Priority:
        #   1. Dedicated location element scraped by PARSE_JS (most accurate)
        #   2. First UK postcode outcode in the card text
        #   3. Fall back to the searched location (last resort)
        area = ""
        pc_match = _POSTCODE_RE.search(location_text.upper())
        if pc_match:
            area = pc_match.group(0).strip()
        else:
            pc_match = _POSTCODE_RE.search(text.upper())
            if pc_match:
                area = pc_match.group(0).strip()
        if not area:
            # No postcode found — use the location label text if we have one,
            # otherwise fall back to the searched location
            area = location_text.strip().upper() or location.upper()

        # ── Pass 2: area-code filter ───────────────────────────────────
        # Only runs when we searched by postcode. Keeps HMO rent averages
        # tied to the actual searched neighbourhood.
        if search_code:
            card_code = _area_code(area)
            if card_code and card_code != search_code:
                rejected_wrong_area += 1
                _sample(f"wrong_area:{card_code}!={search_code}", card)
                print(f"[SpareRoom]   skip {listing_id}: area={area!r} "
                      f"(code={card_code!r}) != search={search_code!r}")
                continue

        out.append({
            "title": title,
            "rentPcm": rent_pcm,
            "roomType": room_type,
            "billsIncluded": bills,
            "area": _sanitise(area, 60),
            "distanceKm": None,
            "listingUrl": href,
            "imageUrl": _sanitise(card.get("image") or "", 500),
            "source": "spareroom",
            # Extra fields used by bulk mode / DB insert only:
            "_listingId": listing_id,
            "_availableFrom": available_from,
            "_numberOfRooms": num_rooms,
        })

    total_seen = len(raw_cards)
    if stats is not None:
        stats.update({
            "total_raw": total_seen,
            "kept": len(out),
            "rejected_promoted": rejected_promoted,
            "rejected_wrong_area": rejected_wrong_area,
            "rejected_no_id": rejected_no_id,
            "rejected_dupes": rejected_dupes,
            "search_code": search_code,
            "rejection_samples": rejection_samples,
        })
    if rejected_promoted or rejected_wrong_area or rejected_no_id or rejected_dupes:
        print(f"[SpareRoom] Parse stats: {total_seen} raw → {len(out)} kept | "
              f"promoted={rejected_promoted} wrong_area={rejected_wrong_area} "
              f"no_id={rejected_no_id} dupes={rejected_dupes} "
              f"(search code={search_code!r})")

    return out


# ── Public API ───────────────────────────────────────────────────────────────
class SpareRoomScraper:
    """SpareRoom scraper powered by Bright Data's Browser API.

    Callers should instantiate once per request (live) or once per bulk run.
    The class holds no state between calls.
    """

    # -- LIVE MODE ------------------------------------------------------------
    def scrape_live(
        self,
        postcode: str,
        max_results: int = 12,
    ) -> List[Dict[str, Any]]:
        """Fetch SpareRoom listings for a single postcode, right now.

        Used by ``/api/comparables`` to replace ``scrape_spareroom_with_apify``.
        30-second hard ceiling. Returns a list of listing dicts in the canonical
        shape — EMPTY list on any failure (caller's existing fallback handles it).
        """
        debug = self.scrape_live_debug(postcode, max_results=max_results)
        return debug.get("listings", [])

    def scrape_live_debug(
        self,
        postcode: str,
        max_results: int = 12,
    ) -> Dict[str, Any]:
        """Same as scrape_live but returns full intermediate state.

        Used by the /api/scraper/debug endpoint so we can see where results
        are being lost without needing to read Render logs. Return shape:
            {
              listings:        [...canonical dicts...],
              raw_cards_count: int,
              filtered_count:  int,
              elapsed_ms:      int,
              url:             str,
              page_title:      str,
              page_url:        str (after any redirects),
              error:           str | None,
            }
        """
        district = self._district_from_postcode(postcode)
        url = _build_search_url(district, offset=0)
        print(f"[SpareRoom] LIVE scrape {district} — {url}")

        result: Dict[str, Any] = {
            "listings": [],
            "raw_cards_count": 0,
            "filtered_count": 0,
            "elapsed_ms": 0,
            "url": url,
            "page_title": "",
            "page_url": "",
            "error": None,
            "parse_stats": {},
            "raw_sample": [],
            "dom_diag": {},
        }

        if not PLAYWRIGHT_AVAILABLE:
            result["error"] = "playwright unavailable"
            return result

        t0 = time.time()

        try:
            with BrightDataBrowser(timeout_ms=LIVE_TIMEOUT_SECS * 1000) as bd:
                ctx = bd.get_context()
                if ctx is None:
                    result["error"] = "browser context unavailable"
                    return result

                page = ctx.new_page()
                page.set_default_timeout(LIVE_TIMEOUT_SECS * 1000)

                try:
                    page.goto(url, wait_until="domcontentloaded",
                              timeout=LIVE_TIMEOUT_SECS * 1000)
                except PlaywrightTimeout:
                    result["error"] = f"timeout loading {district}"
                    result["elapsed_ms"] = int((time.time() - t0) * 1000)
                    return result

                # Allow lazy images / JS hydration a moment to settle, but
                # don't block on networkidle — SpareRoom has long-polling XHRs.
                try:
                    page.wait_for_load_state("load", timeout=8000)
                except PlaywrightTimeout:
                    pass

                # Capture post-redirect page URL + title for diagnostics
                try:
                    result["page_title"] = (page.title() or "")[:200]
                    result["page_url"] = page.url or ""
                except Exception:
                    pass

                # Accept cookie consent via real Playwright click (more
                # reliable than JS click — triggers the site's real event
                # handlers). Best-effort; ignore if the button isn't there.
                for sel in (
                    "#onetrust-accept-btn-handler",
                    "button#onetrust-accept-btn-handler",
                    "button[class*='accept-all']",
                    "button[aria-label*='accept' i]",
                ):
                    try:
                        btn = page.locator(sel).first
                        if btn and btn.is_visible(timeout=500):
                            btn.click(timeout=2000)
                            print(f"[SpareRoom] Accepted cookies via {sel}")
                            page.wait_for_timeout(1000)
                            break
                    except Exception:
                        continue

                # Wait for any in-flight XHRs to settle (SpareRoom fetches
                # the real results list via an XHR that only fires after
                # cookie consent is accepted).
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except PlaywrightTimeout:
                    pass

                # Scroll to trigger lazy-load of results below the featured
                # section, then give the DOM a moment to settle.
                try:
                    page.evaluate(SCROLL_JS)
                    page.wait_for_timeout(800)
                except Exception as _scroll_err:  # noqa: BLE001
                    print(f"[SpareRoom] scroll warn: {_scroll_err}")

                # DOM diagnostics first — tells us what's on the page
                try:
                    result["dom_diag"] = page.evaluate(DIAG_JS) or {}
                except Exception as _diag_err:  # noqa: BLE001
                    result["dom_diag"] = {"error": str(_diag_err)[:200]}

                raw_cards = page.evaluate(PARSE_JS) or []
                result["raw_cards_count"] = len(raw_cards)
                print(f"[SpareRoom] Extracted {len(raw_cards)} raw cards for {district}")

                # Capture a small sample of raw cards for the debug endpoint
                result["raw_sample"] = [
                    {
                        "href": (c.get("href") or "")[:160],
                        "title": (c.get("title") or "")[:80],
                        "locationText": (c.get("locationText") or "")[:60],
                        "isPromoted": bool(c.get("isPromoted")),
                        "promoReason": c.get("promoReason") or "",
                        "listingId": c.get("listingId") or "",
                        "text_preview": (c.get("text") or "")[:200],
                    }
                    for c in raw_cards[:8]
                ]

                stats: Dict[str, Any] = {}
                listings = _parse_raw_cards(raw_cards, district, stats=stats)
                result["parse_stats"] = stats
                result["filtered_count"] = len(listings)
                if len(listings) > max_results:
                    listings = listings[:max_results]

                # Strip internal underscore keys — live callers only need the
                # canonical Apify-compatible shape.
                for r in listings:
                    for k in list(r.keys()):
                        if k.startswith("_"):
                            r.pop(k, None)

                result["listings"] = listings

        except Exception as e:  # noqa: BLE001
            result["error"] = f"{type(e).__name__}: {str(e)[:300]}"
            result["elapsed_ms"] = int((time.time() - t0) * 1000)
            print(f"[SpareRoom] LIVE error for {district}: {result['error']}")
            return result

        result["elapsed_ms"] = int((time.time() - t0) * 1000)
        print(f"[SpareRoom] LIVE {district}: {len(result['listings'])} rooms "
              f"({result['raw_cards_count']} raw, {result['filtered_count']} after filter) "
              f"in {result['elapsed_ms']}ms")
        return result

    # -- BULK MODE ------------------------------------------------------------
    def scrape_bulk(
        self,
        locations: List[str],
        max_pages_per_location: int = 3,
        per_page: int = 100,
        delay_ms: int = DEFAULT_DELAY_MS,
    ) -> Dict[str, Any]:
        """Iterate many locations, upsert into Supabase, log to scrape_logs.

        Skips any location whose most recent ``scrape_logs`` entry is newer
        than ``BULK_SKIP_DAYS`` days (13 days). Errors in one location never
        stop the overall run — every location gets its own try/except.
        """
        supa = _get_supabase()
        if supa is None:
            print("[SpareRoom] BULK: Supabase unavailable — running in dry-run mode")

        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        summary = {
            "runId": run_id,
            "started": datetime.now(timezone.utc).isoformat(),
            "locations": len(locations),
            "scraped": 0,
            "skipped": 0,
            "errors": 0,
            "listingsTotal": 0,
            "byLocation": {},
        }

        for location in locations:
            loc_key = _sanitise(location, 40)
            if self._recently_scraped(supa, loc_key):
                summary["skipped"] += 1
                summary["byLocation"][loc_key] = {"status": "skipped", "count": 0}
                print(f"[SpareRoom] BULK skip {loc_key} — last scrape within {BULK_SKIP_DAYS}d")
                continue

            t0 = time.time()
            loc_results: List[Dict[str, Any]] = []
            error_msg: Optional[str] = None

            try:
                with BrightDataBrowser(timeout_ms=BULK_PAGE_TIMEOUT_SECS * 1000) as bd:
                    ctx = bd.get_context()
                    if ctx is None:
                        raise RuntimeError("browser context unavailable")

                    for page_num in range(max_pages_per_location):
                        offset = page_num * per_page
                        url = _build_search_url(loc_key, offset=offset)
                        page = ctx.new_page()
                        page.set_default_timeout(BULK_PAGE_TIMEOUT_SECS * 1000)

                        try:
                            page.goto(url, wait_until="domcontentloaded",
                                      timeout=BULK_PAGE_TIMEOUT_SECS * 1000)
                            try:
                                page.wait_for_load_state("load", timeout=8000)
                            except PlaywrightTimeout:
                                pass

                            raw_cards = page.evaluate(PARSE_JS) or []
                            parsed = _parse_raw_cards(raw_cards, loc_key)
                            loc_results.extend(parsed)
                            print(f"[SpareRoom] BULK {loc_key} page {page_num+1}: "
                                  f"{len(parsed)} rooms")

                            if len(parsed) < 20:
                                # Last page — SpareRoom usually returns 20-100 per page
                                break
                        finally:
                            try:
                                page.close()
                            except Exception:
                                pass

                        # Polite random delay between pages
                        time.sleep(random.uniform(delay_ms / 1000, delay_ms / 1000 * 2))

                # Dedupe by listing id within this location
                seen: set = set()
                deduped = []
                for r in loc_results:
                    lid = r.get("_listingId")
                    if not lid or lid in seen:
                        continue
                    seen.add(lid)
                    deduped.append(r)
                loc_results = deduped

                # Persist
                if supa is not None and loc_results:
                    self._upsert_listings(supa, loc_key, loc_results)

                summary["scraped"] += 1
                summary["listingsTotal"] += len(loc_results)
                summary["byLocation"][loc_key] = {
                    "status": "ok",
                    "count": len(loc_results),
                    "elapsed_ms": int((time.time() - t0) * 1000),
                }
                self._log_run(supa, loc_key, run_id, "ok", len(loc_results), None)

            except Exception as e:  # noqa: BLE001
                error_msg = f"{type(e).__name__}: {str(e)[:300]}"
                summary["errors"] += 1
                summary["byLocation"][loc_key] = {"status": "error", "error": error_msg}
                print(f"[SpareRoom] BULK error {loc_key}: {error_msg}")
                self._log_run(supa, loc_key, run_id, "error", 0, error_msg)

            # Inter-location delay with jitter
            time.sleep(random.uniform(1.0, 3.0))

        summary["finished"] = datetime.now(timezone.utc).isoformat()
        print(f"[SpareRoom] BULK finished: {summary['scraped']} ok, "
              f"{summary['skipped']} skipped, {summary['errors']} errors, "
              f"{summary['listingsTotal']} listings total")
        return summary

    # -- DB helpers -----------------------------------------------------------
    def _recently_scraped(self, supa: Optional[Any], location: str) -> bool:
        if supa is None:
            return False
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=BULK_SKIP_DAYS)).isoformat()
            resp = (
                supa.table("scrape_logs")
                .select("id,scraped_at")
                .eq("location", location)
                .eq("status", "ok")
                .gte("scraped_at", cutoff)
                .limit(1)
                .execute()
            )
            return bool(resp.data)
        except Exception as e:  # noqa: BLE001
            print(f"[SpareRoom] recently_scraped check failed: {e}")
            return False

    def _upsert_listings(
        self,
        supa: Any,
        location: str,
        listings: List[Dict[str, Any]],
    ) -> None:
        try:
            rows = []
            now = datetime.now(timezone.utc).isoformat()
            for r in listings:
                listing_id = r.get("_listingId") or _extract_listing_id(r.get("listingUrl", ""))
                if not listing_id:
                    continue
                rows.append({
                    "listing_id": listing_id,
                    "location": location,
                    "title": r.get("title"),
                    "rent_pcm": r.get("rentPcm"),
                    "room_type": r.get("roomType"),
                    "bills_included": r.get("billsIncluded"),
                    "area": r.get("area"),
                    "available_from": r.get("_availableFrom"),
                    "number_of_rooms": r.get("_numberOfRooms"),
                    "listing_url": r.get("listingUrl"),
                    "image_url": r.get("imageUrl"),
                    "scraped_at": now,
                })
            if not rows:
                return
            supa.table("spareroom_listings").upsert(
                rows, on_conflict="listing_id"
            ).execute()
            print(f"[SpareRoom] Upserted {len(rows)} listings for {location}")
        except Exception as e:  # noqa: BLE001
            print(f"[SpareRoom] upsert error: {e}")

    def _log_run(
        self,
        supa: Optional[Any],
        location: str,
        run_id: str,
        status: str,
        count: int,
        error: Optional[str],
    ) -> None:
        if supa is None:
            return
        try:
            supa.table("scrape_logs").insert({
                "run_id": run_id,
                "location": location,
                "status": status,
                "listings_found": count,
                "error_message": error,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:  # noqa: BLE001
            print(f"[SpareRoom] log_run error: {e}")

    # -- utils ----------------------------------------------------------------
    @staticmethod
    def _district_from_postcode(postcode: str) -> str:
        parts = (postcode or "").upper().strip().split()
        if not parts:
            return ""
        return parts[0]


# ── module-level convenience for app.py ──────────────────────────────────────
def scrape_spareroom_live(postcode: str, max_results: int = 12) -> List[Dict[str, Any]]:
    """Drop-in replacement for ``scrape_spareroom_with_apify``.

    Same signature, same return shape. Swap the import and you're done.
    """
    return SpareRoomScraper().scrape_live(postcode=postcode, max_results=max_results)
