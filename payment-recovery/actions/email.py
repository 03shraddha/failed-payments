import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import (
    GMAIL_FROM_ADDRESS,
    GMAIL_APP_PASSWORD,
    GMAIL_SMTP_HOST,
    GMAIL_SMTP_PORT,
    BUSINESS_NAME,
)

logger = logging.getLogger(__name__)


def _build_email(
    to_address: str,
    amount: float,
    reason: str,
    link: str,
    custom_subject: str | None = None,
    custom_body: str | None = None,
) -> MIMEMultipart:
    subject = custom_subject or f"Your payment of Rs.{amount:.2f} didn't go through"

    plain = custom_body or f"""Hi there,

Your payment of Rs.{amount:.2f} didn't go through.

Reason: {reason}

Retry here: {link}

This link expires in 24 hours.

With love,
{BUSINESS_NAME}"""

    # ── Pretty minimal HTML email ──────────────────────────────────────────
    # Converts the plain-text body into HTML paragraphs for the HTML part.
    body_html = "".join(
        f"<p style='margin:0 0 16px;line-height:1.6;'>{p.strip()}</p>"
        for p in plain.split("\n\n")
        if p.strip()
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:#f9f9f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">

  <!-- Outer wrapper -->
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background:#f9f9f7;padding:40px 16px;">
    <tr>
      <td align="center">

        <!-- Card -->
        <table width="100%" cellpadding="0" cellspacing="0" border="0"
               style="max-width:520px;background:#ffffff;border-radius:16px;
                      overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);">

          <!-- Top accent bar -->
          <tr>
            <td style="height:4px;background:linear-gradient(90deg,#012652,#0D94FB);"></td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:36px 40px 32px;">

              <!-- Icon + heading -->
              <p style="margin:0 0 6px;font-size:28px;">💎</p>
              <h1 style="margin:0 0 24px;font-size:20px;font-weight:700;
                         color:#012652;letter-spacing:-0.3px;">
                Payment didn't go through
              </h1>

              <!-- AI-generated or default body -->
              <div style="color:#374151;font-size:15px;">
                {body_html}
              </div>

              <!-- CTA button -->
              <table cellpadding="0" cellspacing="0" border="0" style="margin:28px 0 0;">
                <tr>
                  <td style="border-radius:10px;background:#012652;">
                    <a href="{link}"
                       style="display:inline-block;padding:13px 28px;
                              color:#ffffff;font-size:15px;font-weight:600;
                              text-decoration:none;letter-spacing:-0.1px;">
                      Retry Payment &rarr;
                    </a>
                  </td>
                </tr>
              </table>

              <p style="margin:18px 0 0;font-size:12px;color:#9CA3AF;">
                Link expires in 24 hours &nbsp;·&nbsp; Reply to this email for help
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 40px;background:#F9FAFB;
                       border-top:1px solid #F3F4F6;">
              <p style="margin:0;font-size:12px;color:#9CA3AF;">
                Sent by <strong style="color:#6B7280;">{BUSINESS_NAME}</strong>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_FROM_ADDRESS
    msg["To"] = to_address
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    return msg


def _send_email_sync(
    to_address: str,
    amount: float,
    reason: str,
    link: str,
    custom_subject: str | None = None,
    custom_body: str | None = None,
) -> None:
    msg = _build_email(to_address, amount, reason, link, custom_subject, custom_body)

    with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(GMAIL_FROM_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_FROM_ADDRESS, to_address, msg.as_string())

    logger.info("Recovery email sent to %s", to_address)


async def send_email(
    to_address: str | None,
    amount: float,
    reason: str,
    link: str,
    custom_subject: str | None = None,
    custom_body: str | None = None,
) -> None:
    if not to_address:
        logger.warning("Email skipped: no email address in webhook payload")
        return

    await asyncio.to_thread(
        _send_email_sync, to_address, amount, reason, link, custom_subject, custom_body
    )
