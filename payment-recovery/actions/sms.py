import asyncio
import logging
import time

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_FROM_NUMBER,
    BUSINESS_NAME,
)

logger = logging.getLogger(__name__)

# Module-level singleton: avoids re-creating the client on every webhook
_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Twilio terminal statuses: anything in FAILED means delivery won't happen
_DELIVERED = {"delivered"}
_FAILED    = {"failed", "undelivered"}
_TERMINAL  = _DELIVERED | _FAILED | {"canceled"}


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
    return phone  # unknown format - pass through


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


def _poll_status(sid: str, max_wait: int = 8) -> str:
    """
    Polls Twilio for the message status until it reaches a terminal state
    or max_wait seconds elapse. Returns the final status string.

    Twilio statuses: queued → sending → sent → delivered
                                              → undelivered / failed
    """
    deadline = time.time() + max_wait
    while time.time() < deadline:
        msg = _client.messages(sid).fetch()
        status = msg.status
        logger.info("Twilio message %s status: %s", sid, status)
        if status in _TERMINAL:
            return status
        time.sleep(1)
    return "unknown"  # timed out waiting - not necessarily failed


def _send_sms_sync(phone: str, amount: float, reason: str, link: str, custom_text: str | None = None) -> None:
    """Synchronous Twilio call: run via asyncio.to_thread to avoid blocking the event loop."""
    normalized = _normalize_phone(phone)
    body = custom_text if custom_text else _build_message(amount, reason, link)

    try:
        message = _client.messages.create(
            body=body,
            from_=TWILIO_FROM_NUMBER,
            to=normalized,
        )
    except TwilioRestException as exc:
        # Error code 21608 = unverified number on trial account
        if exc.code == 21608:
            raise RuntimeError(
                f"SMS to {normalized} failed: number not verified on Twilio trial account. "
                "Verify it at console.twilio.com/phone-numbers/verified"
            ) from exc
        raise RuntimeError(f"Twilio API error {exc.code}: {exc.msg}") from exc

    logger.info("SMS accepted: SID=%s to=%s chars=%d", message.sid, normalized, len(body))

    # Poll for actual delivery: surfaces silent failures (DND, carrier blocks)
    final_status = _poll_status(message.sid)

    if final_status in _FAILED:
        raise RuntimeError(
            f"SMS to {normalized} was not delivered (status={final_status}). "
            "Possible causes: Indian DND registry, carrier block, or trial account restriction."
        )

    logger.info("SMS delivery status for %s: %s", message.sid, final_status)


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
