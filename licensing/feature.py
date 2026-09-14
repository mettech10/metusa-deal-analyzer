"""Feature flag for POST /v1/licensing/check.

Flag name: licensing_checker_v1
Env: LICENSING_CHECKER_V1 (true/false). Default true so the shipped endpoint
is on; set false to disable without undeploying.
"""

from __future__ import annotations

import os

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def licensing_checker_v1_enabled() -> bool:
    raw = os.environ.get("LICENSING_CHECKER_V1", "true").strip().lower()
    if raw in _FALSE:
        return False
    if raw in _TRUE:
        return True
    return True
