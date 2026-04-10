"""
Generates personalised recovery messages using OpenAI GPT-4o-mini.

Called before SMS/email dispatch so every customer gets a message that
feels hand-written for Shraddha's Anti Tarnish Jewellery Shop.
Falls back to plain templates if the API key is missing or the call fails.
"""

import logging
from dataclasses import dataclass

from config import OPENAI_API_KEY, BUSINESS_NAME

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = f"""You are a warm, friendly customer support assistant for
{BUSINESS_NAME}, an online store selling anti-tarnish jewellery for women.

Your tone is caring, reassuring, and personal — like a helpful friend who
happens to run a jewellery shop. Keep messages concise and action-oriented.
Never be robotic or overly formal. Use simple language.

The shop sells pieces that don't tarnish, so customers can wear them daily
without worry — highlight the emotional connection (a gift, daily wear,
something special) when appropriate."""


@dataclass
class RecoveryMessages:
    sms: str       # 1 SMS-length paragraph (≤160 chars ideally)
    email_subject: str
    email_body: str   # 2-3 short paragraphs, plain text


def _clean(text: str) -> str:
    """Strip em/en dashes and lowercase the string."""
    return text.replace("—", ",").replace("–", ",").strip()


def _fallback(amount: float, reason: str, link: str) -> RecoveryMessages:
    """Used when OpenAI is unavailable."""
    return RecoveryMessages(
        sms=(
            f"Hi! Your payment of Rs.{amount:.0f} at {BUSINESS_NAME} didn't go through. "
            f"No worries, retry here: {link}"
        ),
        email_subject=f"your order payment didn't go through, here's your retry link",
        email_body=(
            f"Hi there,\n\n"
            f"Your payment of Rs.{amount:.2f} couldn't be processed. "
            f"Reason: {reason}\n\n"
            f"We've created a fresh payment link just for you:\n{link}\n\n"
            f"This link is valid for 24 hours. If you need any help, just reply to this email!\n\n"
            f"With love,\n{BUSINESS_NAME}"
        ),
    )


async def generate_recovery_messages(
    amount: float,
    reason: str,
    link: str,
    method: str = "unknown",
) -> RecoveryMessages:
    """
    Calls OpenAI to generate personalised SMS + email content.
    Returns a RecoveryMessages dataclass. Never raises - falls back gracefully.
    """
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set: using fallback messages")
        return _fallback(amount, reason, link)

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=OPENAI_API_KEY)

        user_prompt = f"""A customer's payment just failed at our jewellery shop.

Details:
- Amount: Rs.{amount:.2f}
- Payment method: {method}
- Failure reason: {reason}
- Retry link: {link}

Please write TWO recovery messages:

1. SMS (max 160 characters, warm and direct, include the retry link):
   Start with "SMS:" on its own line.

2. Email (subject line + 2-3 short paragraphs):
   Start with "EMAIL SUBJECT:" on its own line, then "EMAIL BODY:" on its own line.
   - Address the customer warmly
   - Mention the amount and failure reason briefly (don't make them feel bad)
   - Encourage them to retry - the jewellery piece is waiting for them
   - Sign off warmly from {BUSINESS_NAME}
   - Include the retry link naturally in the body"""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=400,
            temperature=0.7,
        )

        raw = response.choices[0].message.content or ""
        return _parse_openai_response(raw, amount, reason, link)

    except Exception as exc:
        logger.error("OpenAI message generation failed: %r - using fallback", exc)
        return _fallback(amount, reason, link)


def _parse_openai_response(raw: str, amount: float, reason: str, link: str) -> RecoveryMessages:
    """Extract SMS / email subject / email body from the GPT response."""
    sms = ""
    email_subject = ""
    email_body_lines: list[str] = []

    lines = raw.strip().splitlines()
    mode = None

    for line in lines:
        stripped = line.strip()
        upper = stripped.upper()

        if upper.startswith("SMS:"):
            mode = "sms"
            rest = stripped[4:].strip()
            if rest:
                sms = rest
            continue
        if upper.startswith("EMAIL SUBJECT:"):
            mode = "subject"
            rest = stripped[14:].strip()
            if rest:
                email_subject = rest
            continue
        if upper.startswith("EMAIL BODY:"):
            mode = "body"
            continue

        if mode == "sms" and not sms:
            sms = stripped
        elif mode == "subject" and not email_subject:
            email_subject = stripped
        elif mode == "body":
            email_body_lines.append(line)

    email_body = "\n".join(email_body_lines).strip()

    # Safety fallbacks for any missing parts
    if not sms:
        sms = f"Hi! Your Rs.{amount:.0f} payment didn't go through. Retry: {link}"
    if not email_subject:
        email_subject = "your payment didn't go through, retry here"
    if not email_body:
        email_body = f"Your payment of Rs.{amount:.2f} failed. Reason: {reason}\n\nRetry: {link}"

    # Strip em/en dashes from AI output and lowercase the subject
    return RecoveryMessages(
        sms=_clean(sms),
        email_subject=_clean(email_subject).lower(),
        email_body=email_body.replace("—", ",").replace("–", ","),
    )
