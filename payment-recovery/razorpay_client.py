import time
import logging
import httpx

from config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_API_BASE

logger = logging.getLogger(__name__)


async def create_qr_code(
    amount_paise: int,
    description: str = "Retry payment",
) -> tuple[str, str]:
    """
    Creates a Razorpay QR code for the given amount.
    Returns (image_url, qr_id) — image_url is a direct PNG link to the QR code.
    Falls back to empty strings on failure.
    """
    payload = {
        "type": "upi_qr",
        "name": description,
        "usage": "single_use",
        "fixed_amount": True,
        "payment_amount": amount_paise,
        "description": description,
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                f"{RAZORPAY_API_BASE}/payments/qr-codes",
                json=payload,
                auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET),
            )
            response.raise_for_status()
            data = response.json()

        image_url = data.get("image_url", "")
        qr_id = data.get("id", "")
        logger.info("Created QR code: %s", qr_id)
        return image_url, qr_id

    except Exception as exc:
        logger.error("Failed to create QR code: %s", exc)
        return "", ""


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
    Falls back to https://rzp.io/i/{order_id} on any failure - so downstream
    actions always have a valid link to include.

    Timeout is 8s to stay within the 10s total webhook SLA.
    """
    fallback_url = f"https://rzp.io/i/{order_id}"

    payload: dict = {
        "amount": amount_paise,          # Razorpay always works in paise
        "currency": "INR",
        "description": description,
        # Unix timestamp: must be at least 15 minutes in the future
        "expire_by": int(time.time()) + 86400,   # 24 hours from now
        # Append timestamp so repeated demo runs don't clash (Razorpay rejects duplicate reference_ids)
        "reference_id": f"{order_id}_{int(time.time())}",
        "notify": {
            # Don't double-notify via Razorpay: we handle comms ourselves
            "sms": False,
            "email": False,
        },
        "reminder_enable": False,
    }

    # Attach customer details — name+contact+email causes Razorpay to pre-fill
    # the checkout form so the customer doesn't have to type their number
    customer: dict = {"name": "Customer"}
    if contact:
        customer["contact"] = contact
    if email:
        customer["email"] = email
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
            "Failed to create payment link for order %s: %s - using fallback",
            order_id,
            exc,
        )
        return fallback_url
