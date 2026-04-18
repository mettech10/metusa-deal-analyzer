"""
Bright Data Browser API client — headless Chromium over CDP WebSocket.

Replacement for the failing Apify SpareRoom actor. Bright Data's Scraping
Browser is a managed Chromium instance that ships with anti-bot bypass,
residential IPs, and CAPTCHA solving baked in. We connect to it over the
Chrome DevTools Protocol (CDP) using Playwright's ``connect_over_cdp``.

Pattern matches ``playwright_scraper.py``:
  - module-level ``try/except ImportError`` guard
  - single class wrapping browser lifecycle
  - module-level helper functions for the rest of the app to call
  - no new browser library — we reuse the Playwright install already in use
    by ``playwright_scraper.py`` for Zoopla scraping

Env vars (see ``.env.example``):
  BRIGHTDATA_API_KEY         - raw customer API token (for /status checks)
  BRIGHTDATA_USERNAME        - format: brd-customer-hl_XXXXXXXX-zone-<zone>
  BRIGHTDATA_PASSWORD        - zone password from Bright Data dashboard
  BRIGHTDATA_ZONE            - zone name, defaults to "scraping_browser"
  BRIGHTDATA_HOST            - CDP endpoint host, defaults to brd.superproxy.io
  BRIGHTDATA_PORT            - CDP endpoint port, defaults to 9222
"""

import os
import time
import urllib.parse
from typing import Optional, Tuple

try:
    from playwright.sync_api import sync_playwright, Browser, BrowserContext, Playwright
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("[BrightData] Playwright not available — scraper will be disabled")


# ── Chrome 120 on macOS, matches playwright_scraper.py ───────────────────────
CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
VIEWPORT = {"width": 1280, "height": 800}


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _build_ws_url() -> Optional[str]:
    """Assemble the Bright Data Browser API WebSocket URL.

    Returns None if required credentials are missing — callers should
    treat that as "scraper unavailable" and fall back gracefully.

    If BRIGHTDATA_COUNTRY is set (e.g. "gb"), it's appended to the
    username as -country-<code>. This forces Bright Data's residential
    proxy to exit from the specified country — critical for SpareRoom
    which shows a locale-chooser modal blocking the search form when
    accessed from a non-UK IP.
    """
    username = _env("BRIGHTDATA_USERNAME")
    password = _env("BRIGHTDATA_PASSWORD")
    host = _env("BRIGHTDATA_HOST", "brd.superproxy.io")
    port = _env("BRIGHTDATA_PORT", "9222")
    # Default to UK exit — SpareRoom shows a country-chooser modal that blocks
    # the search form when accessed from a non-UK IP. Override with
    # BRIGHTDATA_COUNTRY env var if needed (e.g. for non-UK sites).
    country = _env("BRIGHTDATA_COUNTRY", "gb").strip().lower()

    if not username or not password:
        return None

    # Append -country-<code> if set and not already present
    if country and "-country-" not in username:
        username = f"{username}-country-{country}"
        print(f"[BrightData] Forcing exit country: {country}")

    user_enc = urllib.parse.quote(username, safe="")
    pass_enc = urllib.parse.quote(password, safe="")
    return f"wss://{user_enc}:{pass_enc}@{host}:{port}"


class BrightDataBrowser:
    """Lifecycle wrapper for a single Bright Data Scraping Browser session.

    Usage:
        with BrightDataBrowser() as bd:
            ctx = bd.get_context()
            page = ctx.new_page()
            page.goto("https://www.spareroom.co.uk/...")
            html = page.content()
    """

    def __init__(self, timeout_ms: int = 30000):
        self.timeout_ms = timeout_ms
        self._pw: Optional["Playwright"] = None
        self._browser: Optional["Browser"] = None
        self._context: Optional["BrowserContext"] = None
        self.last_error: Optional[str] = None
        self.ws_host: str = ""

    # ── context manager ──────────────────────────────────────────────────
    def __enter__(self) -> "BrightDataBrowser":
        self.get_browser()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close_browser()

    # ── public api ───────────────────────────────────────────────────────
    def get_browser(self) -> Optional["Browser"]:
        """Connect to Bright Data and return a Playwright Browser instance.

        Retries with exponential backoff (1s, 2s, 4s) on transient errors.
        Returns None if Playwright is unavailable or credentials are missing.
        """
        if not PLAYWRIGHT_AVAILABLE:
            print("[BrightData] Playwright unavailable — cannot connect")
            return None

        ws_url = _build_ws_url()
        if not ws_url:
            self.last_error = "Missing BRIGHTDATA_USERNAME/PASSWORD"
            print("[BrightData] Missing BRIGHTDATA_USERNAME/PASSWORD — cannot connect")
            return None

        # Record host for diagnostics (without credentials)
        try:
            from urllib.parse import urlparse
            p = urlparse(ws_url)
            self.ws_host = f"{p.hostname}:{p.port}"
        except Exception:
            pass

        last_err: Optional[Exception] = None
        for attempt, delay in enumerate([1, 2, 4], start=1):
            try:
                print(f"[BrightData] Connecting (attempt {attempt}/3) to {self.ws_host}...")
                self._pw = sync_playwright().start()
                self._browser = self._pw.chromium.connect_over_cdp(
                    ws_url,
                    timeout=self.timeout_ms,
                )
                print(f"[BrightData] Connected — browser version: "
                      f"{self._browser.version}")
                return self._browser
            except Exception as e:  # noqa: BLE001 — retry on any transient error
                last_err = e
                err_str = f"{type(e).__name__}: {str(e)[:300]}"
                self.last_error = err_str
                print(f"[BrightData] Connect failed (attempt {attempt}): {err_str}")
                self._cleanup_partial()
                if attempt < 3:
                    print(f"[BrightData] Retrying in {delay}s...")
                    time.sleep(delay)

        print(f"[BrightData] All 3 attempts failed. Last error: {last_err}")
        return None

    def get_context(self) -> Optional["BrowserContext"]:
        """Return a configured BrowserContext, creating the browser if needed.

        The context is cached so multiple pages within a single scrape share
        cookies and fingerprint. Matches the anti-detection settings used by
        playwright_scraper.py for consistency.
        """
        if self._context is not None:
            return self._context

        if self._browser is None:
            if self.get_browser() is None:
                return None

        try:
            # IMPORTANT: Bright Data's Scraping Browser manages its own
            # fingerprint (UA, webdriver flag, plugins, canvas hash, etc.)
            # automatically. Overriding these with our own values BREAKS
            # their anti-bot protection and causes target sites (like
            # SpareRoom) to fall back to a "bot teaser" response.
            #
            # We deliberately DO NOT pass user_agent or add_init_script.
            # Only locale/timezone/viewport — purely presentational hints
            # that don't conflict with BD's fingerprint management.
            self._context = self._browser.new_context(
                viewport=VIEWPORT,
                locale="en-GB",
                timezone_id="Europe/London",
            )
            return self._context
        except Exception as e:  # noqa: BLE001
            print(f"[BrightData] new_context failed: {type(e).__name__}: {e}")
            return None

    def close_browser(self) -> None:
        """Tear down the browser and Playwright runtime. Idempotent."""
        try:
            if self._context is not None:
                try:
                    self._context.close()
                except Exception:
                    pass
                self._context = None

            if self._browser is not None:
                try:
                    self._browser.close()
                except Exception:
                    pass
                self._browser = None

            if self._pw is not None:
                try:
                    self._pw.stop()
                except Exception:
                    pass
                self._pw = None
        except Exception as e:  # noqa: BLE001
            print(f"[BrightData] close_browser error: {e}")

    def _cleanup_partial(self) -> None:
        """Clean up a partial connection attempt before retrying."""
        try:
            if self._browser is not None:
                try:
                    self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self._pw is not None:
                try:
                    self._pw.stop()
                except Exception:
                    pass
                self._pw = None
        except Exception:
            pass


# ── module-level helpers ─────────────────────────────────────────────────────
def get_browser(timeout_ms: int = 30000) -> Optional["Browser"]:
    """Convenience: return a bare Browser instance. Caller owns cleanup.

    Prefer using ``BrightDataBrowser`` as a context manager for cleanup safety.
    """
    bd = BrightDataBrowser(timeout_ms=timeout_ms)
    return bd.get_browser()


def close_browser(browser: Optional["Browser"]) -> None:
    """Convenience: close a Browser returned by ``get_browser``."""
    if browser is None:
        return
    try:
        browser.close()
    except Exception as e:  # noqa: BLE001
        print(f"[BrightData] close_browser error: {e}")


def scraper_health_check() -> dict:
    """Verify Bright Data connectivity for /api/scraper/health.

    Returns a dict with:
        connected:    bool      — did we actually open a browser session
        message:      str       — human-readable status
        playwright:   bool      — is Playwright importable
        credentials:  bool      — are username/password set
        zone:         str       — which zone we targeted
        latency_ms:   int|None  — round-trip time for connect+close
    """
    result = {
        "connected": False,
        "message": "",
        "playwright": PLAYWRIGHT_AVAILABLE,
        "credentials": bool(_env("BRIGHTDATA_USERNAME") and _env("BRIGHTDATA_PASSWORD")),
        "zone": _env("BRIGHTDATA_ZONE", "scraping_browser"),
        "latency_ms": None,
    }

    if not PLAYWRIGHT_AVAILABLE:
        result["message"] = "Playwright not installed"
        return result

    if not result["credentials"]:
        result["message"] = "BRIGHTDATA_USERNAME / BRIGHTDATA_PASSWORD not set"
        return result

    start = time.time()
    bd = BrightDataBrowser(timeout_ms=15000)
    try:
        browser = bd.get_browser()
        if browser is None:
            result["message"] = bd.last_error or "Connect failed"
            result["ws_host"] = bd.ws_host
            # Parse and expose which zone is embedded in the username
            username = _env("BRIGHTDATA_USERNAME", "")
            import re as _re
            m = _re.search(r"-zone-([A-Za-z0-9_-]+)", username)
            result["zone_in_username"] = m.group(1) if m else ""
            result["has_country_suffix"] = "-country-" in username
            return result

        # Touch the browser to confirm the session is alive
        version = browser.version
        result["connected"] = True
        result["message"] = f"connected — chromium {version}"
        result["latency_ms"] = int((time.time() - start) * 1000)
        return result
    except Exception as e:  # noqa: BLE001
        result["message"] = f"{type(e).__name__}: {str(e)[:300]}"
        return result
    finally:
        bd.close_browser()
