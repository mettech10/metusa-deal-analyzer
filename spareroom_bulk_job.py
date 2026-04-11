"""
SpareRoom bulk scraper job — iterates UK HMO hotspot locations.

Invoked by:
  - /api/scraper/trigger-bulk endpoint (authed with SCRAPER_SECRET)
  - Render cron job (via the same endpoint)
  - CLI: ``python spareroom_bulk_job.py``

The 13-day skip check in ``SpareRoomScraper.scrape_bulk`` means this is safe
to run daily — each location will only actually scrape once every two weeks.

Location list is ordered by HMO investment popularity in the UK: northern
powerhouse cities first (high yield), then Midlands, South (including London
districts). Target ~60+ locations covering the major HMO demand areas.
"""

import os
import sys
from typing import List

from spareroom_scraper import SpareRoomScraper


# ── UK HMO hotspot locations ─────────────────────────────────────────────────
# Mix of postcode districts (fastest on SpareRoom's postcode search) and place
# names (fallback for locations without a clean district key).
UK_HMO_LOCATIONS: List[str] = [
    # ── North West ──
    "Manchester", "M14", "M15", "M16", "M20",     # Fallowfield/Withington/Rusholme student HMO belt
    "Salford", "M5", "M6",
    "Liverpool", "L7", "L8", "L15", "L17",        # Kensington, Toxteth, Wavertree
    "Preston", "PR1",
    "Bolton", "BL1",
    "Stockport", "SK1", "SK16",

    # ── Yorkshire ──
    "Leeds", "LS6", "LS2", "LS4",                 # Headingley student zone
    "Bradford", "BD7", "BD8",
    "Sheffield", "S1", "S10", "S11",              # Ecclesall Rd
    "Hull", "HU5",
    "York", "YO10",

    # ── North East ──
    "Newcastle", "NE1", "NE2", "NE4", "NE6",      # Heaton, Jesmond
    "Sunderland", "SR1", "SR2",
    "Middlesbrough", "TS1",

    # ── Midlands ──
    "Birmingham", "B5", "B15", "B16", "B29",      # Selly Oak student HMO
    "Coventry", "CV1", "CV4",
    "Nottingham", "NG7", "NG1",                   # Lenton
    "Derby", "DE1",
    "Leicester", "LE1", "LE2",
    "Stoke-on-Trent", "ST4",
    "Wolverhampton", "WV1",

    # ── South West ──
    "Bristol", "BS5", "BS6", "BS7",               # Easton, Montpelier
    "Plymouth", "PL4",
    "Exeter", "EX4",
    "Gloucester", "GL1",

    # ── South / South East ──
    "Southampton", "SO14", "SO17",                # Portswood
    "Portsmouth", "PO1", "PO4",                   # Southsea
    "Brighton", "BN1", "BN2",
    "Reading", "RG1",
    "Oxford", "OX4",

    # ── London districts (high rent, lower yield but high demand) ──
    "E1", "E2", "E8", "E17",                      # Bethnal Green, Hackney, Walthamstow
    "N4", "N7", "N15", "N16",                     # Finsbury Park, Stoke Newington
    "SE1", "SE4", "SE14", "SE15",                 # Borough, Brockley, New Cross, Peckham
    "SW2", "SW9", "SW16",                         # Brixton
    "W2", "W12", "W14",                           # Paddington, Shepherd's Bush
    "NW1", "NW5", "NW6",                          # Camden, Kentish Town, Kilburn

    # ── Wales ──
    "Cardiff", "CF24",
    "Swansea", "SA1",
    "Newport", "NP20",

    # ── Scotland ──
    "Glasgow", "G4", "G12",                       # West End
    "Edinburgh", "EH8", "EH9",                    # Marchmont, Newington
    "Aberdeen", "AB24",
    "Dundee", "DD1",
]


def run_bulk_scrape(
    locations: List[str] = None,
    max_pages_per_location: int = 2,
) -> dict:
    """Entry point for /api/scraper/trigger-bulk and the CLI."""
    locs = locations if locations is not None else UK_HMO_LOCATIONS
    print(f"[SpareRoom BULK] Starting run for {len(locs)} locations "
          f"(max {max_pages_per_location} pages each)")
    scraper = SpareRoomScraper()
    return scraper.scrape_bulk(
        locations=locs,
        max_pages_per_location=max_pages_per_location,
    )


if __name__ == "__main__":
    # CLI invocation: python spareroom_bulk_job.py [max_pages]
    max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    summary = run_bulk_scrape(max_pages_per_location=max_pages)
    import json
    print(json.dumps(summary, indent=2, default=str))
    sys.exit(0 if summary.get("errors", 0) == 0 else 1)
