import asyncio
import json
import logging
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request

from actions.email import send_email
from actions.slack import post_slack
from actions.sms import send_sms
from demo_ui import router as demo_router
from razorpay_client import create_payment_link
from verify import verify_razorpay_signature

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Failed Payment Recovery", version="1.0.0")
app.include_router(demo_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook/payment-failed")
async def payment_failed_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(default=None),
):
    # ── 1. Read raw bytes FIRST ──────────────────────────────────────────────
    # Must happen before any JSON parsing. FastAPI caches the bytes on the
    # request object so we can re-read them later, but we need them now for
    # HMAC verification. Never verify against re-serialized JSON — byte order
    # and whitespace must match exactly what Razorpay signed.
    raw_body: bytes = await request.body()

    # ── 2. Verify HMAC-SHA256 signature ─────────────────────────────────────
    if not verify_razorpay_signature(raw_body, x_razorpay_signature or ""):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    # ── 3. Parse JSON from the already-buffered bytes ────────────────────────
    try:
        payload: dict = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse webhook body: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # ── 4. Extract payment fields ─────────────────────────────────────────────
    # Razorpay payload shape: { "payload": { "payment": { "entity": {...} } } }
    entity: dict = (
        payload
        .get("payload", {})
        .get("payment", {})
        .get("entity", {})
    )

    payment_id: str   = entity.get("id", "unknown")
    order_id: str     = entity.get("order_id", "unknown")
    amount_paise: int = int(entity.get("amount", 0))
    amount: float     = amount_paise / 100.0
    contact: str | None = entity.get("contact")   # phone, may be absent
    email: str | None   = entity.get("email")      # may be absent
    method: str       = entity.get("method", "unknown")

    # error_description is a plain string in most Razorpay versions,
    # but can be a nested dict in some edge cases — handle both.
    raw_err = entity.get("error_description", "Payment failed")
    if isinstance(raw_err, dict):
        reason: str = raw_err.get("description", "Payment failed")
    else:
        reason = str(raw_err)

    logger.info(
        "Received payment.failed: id=%s order=%s amount=₹%.2f method=%s",
        payment_id, order_id, amount, method,
    )

    # ── 5. Generate a fresh payment link ─────────────────────────────────────
    fresh_link: str = await create_payment_link(
        order_id=order_id,
        amount_paise=amount_paise,
        contact=contact,
        email=email,
        description=f"Retry payment for order {order_id}",
    )

    # ── 6. Fan-out: SMS + Email + Slack in parallel ───────────────────────────
    # return_exceptions=True means one failure never cancels the other two.
    # Each action is independently try/caught inside its own module as well.
    sms_task   = send_sms(contact, amount, reason, fresh_link)
    email_task = send_email(email, amount, reason, fresh_link)
    # Slack needs to know which actions fired so it can display the status line
    slack_task = post_slack(
        payment_id=payment_id,
        order_id=order_id,
        amount=amount,
        reason=reason,
        phone=contact,
        email=email,
        method=method,
        link=fresh_link,
        sms_sent=bool(contact),
        email_sent=bool(email),
    )

    results = await asyncio.gather(sms_task, email_task, slack_task, return_exceptions=True)

    # ── 7. Log individual action failures (non-fatal) ─────────────────────────
    action_names = ["SMS", "Email", "Slack"]
    for name, result in zip(action_names, results):
        if isinstance(result, Exception):
            logger.error("%s action failed: %r", name, result)

    return {"status": "ok", "payment_id": payment_id, "recovery_link": fresh_link}
