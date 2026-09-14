"""Compatibility shim — real send lives in compliance.email (Brevo adapter)."""

from compliance.email import send_reminder_email

__all__ = ["send_reminder_email"]
