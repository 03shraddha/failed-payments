import time
import logging
import httpx

from config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_API_BASE

logger = logging.getLogger(__name__)


async def create_payment_link(
    order_id: str,
    amount_paise: int,
    contact: str | None,
    email: str | None,
    description: str = "Retry payment",
) -> str:
    """
    Creates a fresh Razorpay payment link for a failed order.

    Returns the short_url on success.
    Falls back to https://rzp.io/i/{order_id} on any failure — so downstream
    actions always have a valid link to include.

    Timeout is 8s to stay within the 10s total webhook SLA.
    """
    fallback_url = f"https://rzp.io/i/{order_id}"

    payload: dict = {
        "amount": amount_paise,          # Razorpay always works in paise
        "currency": "INR",
        "description": description,
        # Unix timestamp — must be at least 15 minutes in the future
        "expire_by": int(time.time()) + 86400,   # 24 hours from now
        "reference_id": order_id,
        "notify": {
            # Don't double-notify via Razorpay — we handle comms ourselves
            "sms": False,
            "email": False,
        },
        "reminder_enable": False,
    }

    # Attach customer details only when available
    customer: dict = {}
    if contact:
        customer["contact"] = contact
    if email:
        customer["email"] = email
    if customer:
        payload["customer"] = customer

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                f"{RAZORPAY_API_BASE}/payment_links",
                json=payload,
                auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET),
            )
            response.raise_for_status()
            data = response.json()

        short_url: str | None = data.get("short_url")
        if not short_url:
            raise ValueError(f"No short_url in Razorpay response: {data}")

        logger.info("Created payment link: %s (order=%s)", short_url, order_id)
        return short_url

    except Exception as exc:
        logger.error(
            "Failed to create payment link for order %s: %s — using fallback",
            order_id,
            exc,
        )
        return fallback_url
