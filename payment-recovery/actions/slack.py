import asyncio
import logging

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from config import SLACK_BOT_TOKEN, SLACK_CHANNEL

logger = logging.getLogger(__name__)

# Module-level singleton
_client = WebClient(token=SLACK_BOT_TOKEN)


def _mask_phone(phone: str | None) -> str:
    """
    Shows only the last 4 digits.
    +919876543210  →  ****3210
    """
    if not phone:
        return "N/A"
    digits = phone.replace("+", "").replace(" ", "").replace("-", "")
    return f"****{digits[-4:]}" if len(digits) >= 4 else "****"


def _mask_email(email: str | None) -> str:
    """
    Shows first character + domain only.
    john.doe@gmail.com  →  j***@gmail.com
    """
    if not email or "@" not in email:
        return "N/A"
    local, domain = email.split("@", 1)
    return f"{local[0]}***@{domain}"


def _post_slack_sync(
    payment_id: str,
    order_id: str,
    amount: float,
    reason: str,
    phone: str | None,
    email: str | None,
    method: str,
    link: str,
    sms_sent: bool,
    email_sent: bool,
) -> None:
    """Synchronous Slack post: run via asyncio.to_thread."""
    sms_status   = "SMS ✓"  if sms_sent   else "SMS ✗"
    email_status = "Email ✓" if email_sent else "Email ✗"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🔴 Payment Failed", "emoji": True},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Amount:*\n₹{amount:.2f}"},
                {"type": "mrkdwn", "text": f"*Method:*\n{method.upper()}"},
                {"type": "mrkdwn", "text": f"*Pay ID:*\n`{payment_id}`"},
                {"type": "mrkdwn", "text": f"*Order ID:*\n`{order_id}`"},
                {"type": "mrkdwn", "text": f"*Phone:*\n{_mask_phone(phone)}"},
                {"type": "mrkdwn", "text": f"*Email:*\n{_mask_email(email)}"},
            ],
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Reason:* {reason}"},
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Actions taken: {sms_status}  |  {email_status}",
                }
            ],
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Open Recovery Link", "emoji": True},
                    "url": link,
                    "style": "primary",
                }
            ],
        },
    ]

    try:
        _client.chat_postMessage(
            channel=SLACK_CHANNEL,
            # Fallback text shown in mobile push notifications and screen readers
            text=f"Payment failed ₹{amount:.2f} via {method} — {reason}",
            blocks=blocks,
        )
        logger.info("Slack alert posted for payment_id=%s", payment_id)
    except SlackApiError as exc:
        # Re-raise so the caller's gather loop can log it
        raise RuntimeError(f"Slack API error: {exc.response['error']}") from exc


async def post_slack(
    payment_id: str,
    order_id: str,
    amount: float,
    reason: str,
    phone: str | None,
    email: str | None,
    method: str,
    link: str,
    sms_sent: bool = True,
    email_sent: bool = True,
) -> None:
    """Async entry point called from main.py via asyncio.gather."""
    await asyncio.to_thread(
        _post_slack_sync,
        payment_id, order_id, amount, reason,
        phone, email, method, link,
        sms_sent, email_sent,
    )
