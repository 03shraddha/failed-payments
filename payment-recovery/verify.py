import hmac
import hashlib
import logging

from config import RAZORPAY_WEBHOOK_SECRET

logger = logging.getLogger(__name__)


def verify_razorpay_signature(raw_body: bytes, signature_header: str) -> bool:
    """
    Validates the Razorpay webhook signature.

    Razorpay signs the raw request body with the webhook secret using HMAC-SHA256
    and sends the hex digest in the X-Razorpay-Signature header.

    Uses hmac.compare_digest for constant-time comparison to prevent timing attacks.
    Returns False (not raises) so the caller can decide the HTTP response.
    """
    if not signature_header:
        logger.warning("Signature verification failed: missing X-Razorpay-Signature header")
        return False

    expected = hmac.new(
        key=RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    match = hmac.compare_digest(expected, signature_header)
    if not match:
        logger.warning(
            "Signature verification failed: computed=%s..., received=%s...",
            expected[:8],
            signature_header[:8],
        )
    return match
