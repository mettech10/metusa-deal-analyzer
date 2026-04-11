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
LIVE_TIMEOUT_SECS = 30
BULK_PAGE_TIMEOUT_SECS = 45
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
    """SpareRoom search URL using the ``search_type=rooms&where=`` variant.

    This variant honours ``per=100`` and returns 100 organic + sponsored
    listings per page. The older ``search_by=postcode`` variant was found to
    cap results at ~10 per page and heavily over-index on sponsored listings,
    causing the area-code filter to strip everything and trigger the Rightmove
    fallback every time.

    ``location`` can be:
      - a full postcode ("M14 4AB") — district extracted for the query
      - a district ("M14", "LS6", "SE15")
      - a place name ("Manchester", "Leeds", "Birmingham")
    """
    # For postcode inputs, use just the district part in the query to keep
    # the radius wide enough to hit organic listings.
    raw = _sanitise(location, 40)
    first_token = raw.split()[0] if raw else ""
    query_loc = first_token if re.match(r"^[A-Za-z]{1,2}\d", first_token) else raw
    loc = query_loc.replace(" ", "+")
    return (
        f"https://www.spareroom.co.uk/flatshare/?search_type=rooms"
        f"&where={loc}&per=100&offset={offset}&mode=list"
        f"&rooms_for=0&rooms_offered=1"
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
  const cards = Array.from(document.querySelectorAll(
    'li[data-listing-id], article.panel-listing, article[class*="listing"], ' +
    'li.listing-result, li.panel-listing'
  ));
  if (cards.length === 0) {
    // Fallback: any anchor pointing at flatshare_detail
    const anchors = Array.from(document.querySelectorAll(
      'a[href*="flatshare_detail.pl"], a[href*="/flatshare/flatshare_detail"]'
    ));
    const seen = new Set();
    return anchors.map(a => {
      const card = a.closest('li, article, div') || a;
      if (seen.has(a.href)) return null;
      seen.add(a.href);
      const text = (card.innerText || '').trim();
      return {
        href: a.href || '',
        title: (a.innerText || '').trim().slice(0, 160),
        text: text.slice(0, 800),
        image: (card.querySelector('img') || {}).src || '',
      };
    }).filter(Boolean);
  }
  return cards.map(card => {
    const a = card.querySelector('a[href*="flatshare_detail"], a[href*="/flatshare/"]') ||
              card.querySelector('a');
    const img = card.querySelector('img');
    return {
      href: (a && a.href) || '',
      title: ((card.querySelector('h2, h3, .listingTitle, .listing-title') || a || {}).innerText || '').trim().slice(0, 160),
      text: ((card.innerText) || '').trim().slice(0, 1200),
      image: (img && (img.src || img.getAttribute('data-src'))) || '',
      listingId: card.getAttribute('data-listing-id') || '',
    };
  });
}
"""


def _parse_raw_cards(raw_cards: List[Dict[str, Any]], location: str) -> List[Dict[str, Any]]:
    """Turn the raw card objects pulled from the DOM into the canonical shape.

    Filters out SpareRoom sponsored/featured listings whose postcode area code
    doesn't match the searched location. SpareRoom injects paid listings from
    all over the UK at the top of every search, ignoring the 2-mile radius
    filter — we reject them here so HMO rent averages stay geographically
    accurate.

    The filter only runs when ``location`` is postcode-like (e.g. "M14", "LS6",
    "SE15"). For place-name searches like "Manchester" we can't derive an area
    code, so no filtering is applied.
    """
    out: List[Dict[str, Any]] = []
    seen_ids: set = set()

    # Area code of the searched location — empty string for place-name searches
    search_code = _area_code(location)
    rejected_wrong_area = 0

    for card in raw_cards:
        href = _abs_url(card.get("href", ""))
        listing_id = card.get("listingId") or _extract_listing_id(href) or ""
        if not listing_id or listing_id in seen_ids:
            continue
        seen_ids.add(listing_id)

        text = card.get("text") or ""
        title = _sanitise(card.get("title") or "Room to rent", 120)

        # Price — look for £xxx in the card text
        price_match = re.search(
            r"£\s*[\d,]+(?:\.\d+)?(?:\s*(?:pcm|pw|per\s*(?:month|week)))?",
            text,
            re.IGNORECASE,
        )
        rent_pcm = _parse_price_to_pcm(price_match.group(0)) if price_match else None

        # Room type — search the card text and title
        combined = f"{title} {text}".lower()
        room_type = _classify_room_type(combined)

        # Bills
        bills = _classify_bills(combined)

        # Available from — "Available now", "Available 15 Apr"
        avail_match = re.search(r"available\s+([a-z0-9 ]{1,20})", combined)
        available_from = avail_match.group(1).strip() if avail_match else None

        # Number of rooms in the household
        rooms_match = re.search(r"(\d+)\s*(?:bed)?rooms?", combined)
        num_rooms = int(rooms_match.group(1)) if rooms_match else None

        # Area label — first line of the card that looks like a postcode or place
        area = location.upper()
        pc_match = re.search(r"([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d?[A-Z]{0,2})", text)
        if pc_match:
            area = pc_match.group(1).strip()

        # ── Area-code filter: reject sponsored listings from other cities ──
        # Only runs for postcode searches. The old Apify actor suffered from
        # the same sponsored-listing noise; filtering here keeps HMO rent
        # averages tied to the actual searched area.
        if search_code:
            card_code = _area_code(area)
            if card_code and card_code != search_code:
                rejected_wrong_area += 1
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

    if rejected_wrong_area > 0:
        print(f"[SpareRoom] Filtered {rejected_wrong_area} sponsored/other-area "
              f"listings (search code={search_code!r})")

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

                raw_cards = page.evaluate(PARSE_JS) or []
                result["raw_cards_count"] = len(raw_cards)
                print(f"[SpareRoom] Extracted {len(raw_cards)} raw cards for {district}")

                listings = _parse_raw_cards(raw_cards, district)
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
