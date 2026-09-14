"""Compliance reminder email — STUB.

TODO: Send via Brevo transactional email using BREVO_API_KEY /
BREVO_SENDER_EMAIL (see EMAIL_SETUP.md). Template should include:
property address (once the cockpit UI supplies it), obligation name,
expiry date, and a link into the Compliance Cockpit.

Do not silently pretend mail was delivered in production logs: callers
record `stubbed: true` on the reminder dispatch result.
"""

import logging
from typing import Optional

logger = logging.getLogger("compliance.email")


def send_reminder_email(
    *,
    user_id: str,
    obligation: dict,
    reminder: dict,
    to_email: Optional[str] = None,
) -> dict:
    """No-op email sender for the MVP.

    Returns a structured result so the dispatcher can mark the stub `sent`
    without coupling to a provider. Swap this function's body for Brevo
    (or SES) when wiring production mail.
    """
    code = obligation.get("code")
    offset = reminder.get("offsetCode") or reminder.get("offset_code")
    scheduled = reminder.get("scheduledFor") or reminder.get("scheduled_for")
    logger.info(
        "[compliance] TODO email stub: would send %s reminder for %s "
        "(obligation=%s user=%s scheduled=%s to=%s)",
        offset,
        code,
        obligation.get("id"),
        user_id,
        scheduled,
        to_email or "(unknown)",
    )
    return {
        "ok": True,
        "stubbed": True,
        # TODO: replace with Brevo message id once email is wired.
        "provider": None,
        "message": (
            "Email not sent — send_reminder_email is a stub. "
            "TODO: wire Brevo transactional template."
        ),
    }
