"""Open Banking provider interface.

MTD Pack v1 does not connect to Open Banking. The stub is the supported
implementation so a real provider can be swapped in later without API churn.
"""

from __future__ import annotations

from typing import Any, Protocol


class OpenBankingProvider(Protocol):
    def status(self) -> dict[str, Any]:
        ...

    def sync(self, *, org_id: str, business_id: str) -> dict[str, Any]:
        ...


class StubOpenBankingProvider:
    """v1 placeholder — no bank connections, no transaction pull."""

    provider_id = "stub"

    def status(self) -> dict[str, Any]:
        return {
            "available": False,
            "enabled": False,
            "provider": None,
            "version": "mtd-pack-v1",
            "reason": "Open Banking is out of scope for Metalyzi MTD Pack v1",
        }

    def sync(self, *, org_id: str, business_id: str) -> dict[str, Any]:
        raise OpenBankingNotAvailable(
            "Open Banking sync is not available in MTD Pack v1"
        )


class OpenBankingNotAvailable(RuntimeError):
    pass
