"""Offline ingest helper: query planning.data.gov.uk Article 4 for a postcode.

Does not store geometries. Prints classified hits so curators can see whether
Planning Data covers a given LA. Used as:

    python scripts/ingest_article4.py M14 6LT
    python scripts/ingest_article4.py --lat 51.7520 --lng -1.2577
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from licensing.article4 import ingest_article4_for_point  # noqa: E402
from licensing.geo import GeoError, resolve_postcode  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Article 4 point ingest (planning.data.gov.uk)")
    parser.add_argument("postcode", nargs="*", help="Full UK postcode, e.g. OX1 1BP")
    parser.add_argument("--lat", type=float, default=None)
    parser.add_argument("--lng", type=float, default=None)
    args = parser.parse_args(argv)

    if args.lat is not None and args.lng is not None:
        lat, lng = args.lat, args.lng
        label = f"{lat},{lng}"
    else:
        raw = " ".join(args.postcode).strip()
        if not raw:
            parser.error("Provide a postcode or --lat and --lng")
        try:
            loc = resolve_postcode(raw)
        except GeoError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
            return 1
        lat, lng = loc.latitude, loc.longitude
        label = loc.postcode
        if lat is None or lng is None:
            print(json.dumps({"ok": False, "error": "no coordinates"}), file=sys.stderr)
            return 1

    result = ingest_article4_for_point(lat, lng)
    print(json.dumps({"label": label, "latitude": lat, "longitude": lng, **result.to_dict()}, indent=2))
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
