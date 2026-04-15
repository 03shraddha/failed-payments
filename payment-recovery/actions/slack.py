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


def _win_back_text(method: str, sms_sent: bool, email_sent: bool) -> str:
    """Returns method-specific recovery suggestions as a Slack mrkdwn string."""
    channels = []
    if sms_sent:
        channels.append("SMS")
    if email_sent:
        channels.append("Email")
    delivery = " and ".join(channels) + " ✓" if channels else "no channels"

    suggestions = {
        "upi": [
            "Offer a 10% discount on retry",
            f"Recovery link sent via {delivery}",
            "Follow up in 2 hrs if link unopened",
        ],
        "card": [
            "Offer a 10% discount and suggest retrying with a different card",
            f"Recovery link sent via {delivery}",
            "Follow up in 2 hrs if link unopened",
        ],
        "netbanking": [
            "Suggest switching to UPI or card for faster checkout",
            f"Recovery link sent via {delivery}",
            "Follow up in 2 hrs if link unopened",
        ],
    }
    bullets = suggestions.get(method.lower(), suggestions["upi"])
    lines = "\n".join(f"• {b}" for b in bullets)
    return f"*Win them back:*\n{lines}"


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
    # Strip any em dashes from the reason before displaying
    clean_reason = reason.replace("\u2014", ",").replace(" - ", ", ").strip()

    blocks = [
        # Source attribution: looks like an internal ops bot post
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "🏪 *Merchant Ops* · #payment-ops · automated alert",
                }
            ],
        },
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🔴 Failed Payment: Action Required", "emoji": True},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Amount:*\n₹{amount:.2f}"},
                {"type": "mrkdwn", "text": f"*Method:*\n{method.upper()}"},
                {"type": "mrkdwn", "text": f"*Payment ID:*\n`{payment_id}`"},
                {"type": "mrkdwn", "text": f"*Order ID:*\n`{order_id}`"},
                {"type": "mrkdwn", "text": f"*Customer Phone:*\n{_mask_phone(phone)}"},
                {"type": "mrkdwn", "text": f"*Customer Email:*\n{_mask_email(email)}"},
            ],
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Failure Reason:* {clean_reason}"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": _win_back_text(method, sms_sent, email_sent)},
        },
        {"type": "divider"},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📨 Open Recovery Link", "emoji": True},
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
            text=f"Payment failed ₹{amount:.2f} via {method}: {reason}",
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
