import asyncio
import logging

from twilio.rest import Client

from config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_FROM_NUMBER,
    BUSINESS_NAME,
)

logger = logging.getLogger(__name__)

# Module-level singleton — avoids re-creating the client on every webhook
_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def _normalize_phone(phone: str) -> str:
    """
    Normalizes Indian phone numbers to E.164 format (+91XXXXXXXXXX).

    Handles these cases:
      +91XXXXXXXXXX  → unchanged
      91XXXXXXXXXX   → prepend +
      XXXXXXXXXX     → prepend +91 (10-digit Indian mobile)
      anything else  → pass through and let Twilio validate
    """
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("+91"):
        return phone
    if phone.startswith("91") and len(phone) == 12:
        return "+" + phone
    if len(phone) == 10 and phone.isdigit():
        return "+91" + phone
    return phone  # unknown format — pass through


def _build_message(amount: float, reason: str, link: str) -> str:
    """
    Builds the SMS body. Truncates reason if the full message exceeds 160 chars
    (> 160 chars splits into 2 segments, which costs double and looks broken).
    """
    template = "Hi! Your payment of ₹{amount:.2f} failed ({reason}). Retry: {link} (24hrs) — {biz}"
    msg = template.format(amount=amount, reason=reason, link=link, biz=BUSINESS_NAME)

    if len(msg) <= 160:
        return msg

    # Truncate the reason field to fit within 160 chars
    overhead = len(msg) - len(reason)          # chars used by everything else
    max_reason = 160 - overhead - 3            # -3 for the "..."
    truncated = reason[:max_reason] + "..."
    return template.format(amount=amount, reason=truncated, link=link, biz=BUSINESS_NAME)


def _send_sms_sync(phone: str, amount: float, reason: str, link: str, custom_text: str | None = None) -> None:
    """Synchronous Twilio call — run via asyncio.to_thread to avoid blocking the event loop."""
    normalized = _normalize_phone(phone)
    body = custom_text if custom_text else _build_message(amount, reason, link)

    message = _client.messages.create(
        body=body,
        from_=TWILIO_FROM_NUMBER,
        to=normalized,
    )
    logger.info("SMS sent: SID=%s to=%s chars=%d", message.sid, normalized, len(body))


async def send_sms(
    phone: str | None,
    amount: float,
    reason: str,
    link: str,
    custom_text: str | None = None,
) -> None:
    """
    Async entry point called from main.py via asyncio.gather.
    Skips gracefully if phone is missing.
    """
    if not phone:
        logger.warning("SMS skipped: no phone number in webhook payload")
        return

    await asyncio.to_thread(_send_sms_sync, phone, amount, reason, link, custom_text)
