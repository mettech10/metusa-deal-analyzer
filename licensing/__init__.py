"""Metalyzi Licensing Checker (P0–P2).

England-only foundations for POST /v1/licensing/check:

- Postcode → local authority via postcodes.io (ONSPD-backed)
- Mandatory HMO + sui generis planning rules (England statute)
- Article 4 lookup against planning.data.gov.uk (partial coverage)
- Curated additional / selective licensing schemes (~25 priority LAs)

Out of scope: UPRN (P4), CON29, Wales/Scotland/NI rule engines.
"""

from licensing.engine import run_licensing_check

__all__ = ["run_licensing_check"]
