"""Compliance reminder email via Brevo (same pattern as lib/brevo-email.ts).

Env-gated, fail-soft:
  BREVO_API_KEY         required to actually send (platform secret)
  BREVO_SENDER_EMAIL    default noreply@metalyzi.co.uk
  BREVO_REPLY_TO_EMAIL  default sender / hello@metalyzi.co.uk

If the key is missing, we log a warning and return skipped=True — dispatch
still advances the stub so the weekly overdue cadence does not stall.
"""

from __future__ import annotations

import html
import logging
import os
from typing import Optional

import requests

from compliance.catalogue import get_catalogue_item

logger = logging.getLogger("compliance.email")

BREVO_SMTP_URL = "https://api.brevo.com/v3/smtp/email"
DEFAULT_SENDER = "noreply@metalyzi.co.uk"
DEFAULT_SITE = "https://metalyzi.co.uk"


def brevo_configured() -> bool:
    return bool((os.environ.get("BREVO_API_KEY") or "").strip())


def provider_status() -> dict:
    return {
        "provider": "brevo",
        "configured": brevo_configured(),
        "sender": os.environ.get("BREVO_SENDER_EMAIL") or DEFAULT_SENDER,
    }


def lookup_user_email(user_id: str) -> Optional[str]:
    """Resolve the landlord email from Supabase Auth (service role). Fail-soft."""
    if not user_id:
        return None
    url = (
        os.environ.get("SUPABASE_URL")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        or ""
    ).rstrip("/")
    key = (
        os.environ.get("SUPABASE_SERVICE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    )
    if not url or not key:
        return None
    try:
        resp = requests.get(
            f"{url}/auth/v1/admin/users/{user_id}",
            headers={"Authorization": f"Bearer {key}", "apikey": key},
            timeout=8,
        )
        if resp.status_code != 200:
            logger.warning(
                "[compliance] user email lookup failed %s for %s",
                resp.status_code, user_id,
            )
            return None
        email = (resp.json() or {}).get("email")
        return str(email).strip() if email else None
    except requests.RequestException as exc:
        logger.warning("[compliance] user email lookup error: %s", exc)
        return None


def _offset_label(reminder: dict) -> str:
    code = reminder.get("offsetCode") or reminder.get("offset_code") or ""
    labels = {
        "t_minus_90": "90 days before expiry",
        "t_minus_60": "60 days before expiry",
        "t_minus_30": "30 days before expiry",
        "t_minus_14": "14 days before expiry",
        "t_minus_7": "7 days before expiry",
        "t_zero": "due today",
        "overdue": "overdue",
        "overdue_weekly": "still overdue (weekly reminder)",
    }
    return labels.get(code, code or "compliance reminder")


def _reminder_html(obligation: dict, reminder: dict) -> str:
    item = get_catalogue_item(obligation.get("code") or "") or {}
    name = html.escape(item.get("name") or obligation.get("code") or "Certificate")
    code = html.escape(str(obligation.get("code") or ""))
    expires = html.escape(str(obligation.get("expiresOn") or obligation.get("expires_on") or "unknown"))
    when = html.escape(_offset_label(reminder))
    site = os.environ.get("NEXT_PUBLIC_SITE_URL") or DEFAULT_SITE
    cockpit = html.escape(f"{site.rstrip('/')}/compliance")
    return f"""<!DOCTYPE html>
<html lang="en">
<body style="margin:0;padding:0;background:#0f0f0f;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f0f0f;padding:40px 16px;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#1a1a1a;border-radius:12px;border:1px solid #2a2a2a;">
        <tr><td style="padding:36px;">
          <p style="margin:0 0 8px;font-size:13px;font-weight:600;color:#D4AF37;letter-spacing:0.4px;text-transform:uppercase;">Metalyzi Compliance</p>
          <h1 style="margin:0 0 16px;font-size:22px;color:#ffffff;">{name}</h1>
          <p style="margin:0 0 20px;font-size:15px;color:#9ca3af;line-height:1.6;">
            This is a {when} reminder for catalogue code <strong style="color:#d1d5db;">{code}</strong>.
            Expiry date on file: <strong style="color:#d1d5db;">{expires}</strong>.
          </p>
          <p style="margin:0 0 28px;font-size:14px;color:#9ca3af;line-height:1.6;">
            Upload fresh evidence in the Compliance Cockpit so the status engine can return this obligation to valid.
          </p>
          <a href="{cockpit}" style="display:inline-block;background:#ffffff;color:#0f0f0f;font-size:14px;font-weight:700;padding:12px 28px;border-radius:8px;text-decoration:none;">Open Compliance Cockpit</a>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _send_brevo(to_email: str, subject: str, html_content: str) -> dict:
    api_key = (os.environ.get("BREVO_API_KEY") or "").strip()
    sender = os.environ.get("BREVO_SENDER_EMAIL") or DEFAULT_SENDER
    reply_to = os.environ.get("BREVO_REPLY_TO_EMAIL") or sender
    try:
        resp = requests.post(
            BREVO_SMTP_URL,
            json={
                "sender": {"name": "Metalyzi", "email": sender},
                "replyTo": {"email": reply_to},
                "to": [{"email": to_email}],
                "subject": subject,
                "htmlContent": html_content,
            },
            headers={"api-key": api_key, "Content-Type": "application/json"},
            timeout=15,
        )
        body = resp.text[:400]
        if resp.status_code in (200, 201, 202):
            message_id = None
            try:
                message_id = (resp.json() or {}).get("messageId")
            except ValueError:
                message_id = None
            logger.info("[compliance] Brevo sent reminder to %s id=%s", to_email, message_id)
            return {
                "ok": True,
                "delivered": True,
                "stubbed": False,
                "skipped": False,
                "provider": "brevo",
                "messageId": message_id,
            }
        logger.warning("[compliance] Brevo send failed %s: %s", resp.status_code, body)
        return {
            "ok": False,
            "delivered": False,
            "stubbed": False,
            "skipped": False,
            "provider": "brevo",
            "message": f"Brevo HTTP {resp.status_code}",
        }
    except requests.RequestException as exc:
        logger.warning("[compliance] Brevo network error: %s", exc)
        return {
            "ok": False,
            "delivered": False,
            "stubbed": False,
            "skipped": False,
            "provider": "brevo",
            "message": f"Brevo network error: {exc}",
        }


def send_reminder_email(
    *,
    user_id: str,
    obligation: dict,
    reminder: dict,
    to_email: Optional[str] = None,
) -> dict:
    """Send a compliance reminder, or skip fail-soft when mail is not configured.

    in_app channel is never emailed — the FE owns that surface.
    """
    channel = (reminder.get("channel") or "email").lower()
    if channel == "in_app":
        logger.info("[compliance] skipping email for in_app reminder %s", reminder.get("id"))
        return {
            "ok": True,
            "delivered": False,
            "stubbed": False,
            "skipped": True,
            "provider": None,
            "message": "in_app channel is left to the frontend",
        }

    recipient = (to_email or "").strip() or lookup_user_email(user_id)
    code = obligation.get("code") or "obligation"
    offset = reminder.get("offsetCode") or reminder.get("offset_code")
    item = get_catalogue_item(code) or {}
    subject = f"Compliance reminder: {item.get('name') or code} ({_offset_label(reminder)})"

    if not brevo_configured():
        logger.warning(
            "[compliance] BREVO_API_KEY not set — skipping send to user=%s "
            "obligation=%s offset=%s to=%s",
            user_id, obligation.get("id"), offset, recipient or "(unknown)",
        )
        return {
            "ok": True,
            "delivered": False,
            "stubbed": False,
            "skipped": True,
            "provider": "brevo",
            "message": (
                "Email not sent — BREVO_API_KEY is not set on the Flask backend. "
                "Set BREVO_API_KEY, BREVO_SENDER_EMAIL, BREVO_REPLY_TO_EMAIL "
                "(same secrets as lib/brevo-email.ts)."
            ),
        }

    if not recipient:
        logger.warning(
            "[compliance] no recipient email for user=%s obligation=%s — skip",
            user_id, obligation.get("id"),
        )
        return {
            "ok": True,
            "delivered": False,
            "stubbed": False,
            "skipped": True,
            "provider": "brevo",
            "message": "No recipient email (Supabase user lookup returned none)",
        }

    return _send_brevo(recipient, subject, _reminder_html(obligation, reminder))
