"""
/demo  : browser-based simulation UI for the payment recovery system.

GET  /demo          → serves the HTML page
POST /demo/simulate → runs a real simulation (SMS + email + Slack) and returns JSON
"""

import asyncio
import copy
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from actions.email import send_email
from actions.message_generator import generate_recovery_messages
from actions.slack import post_slack
from actions.sms import send_sms
from config import GMAIL_FROM_ADDRESS
router = APIRouter()

# ---------------------------------------------------------------------------
# Demo scenarios: each contains the customer/payment data used for simulation
# ---------------------------------------------------------------------------
SCENARIOS: dict = {
    "upi_timeout": {
        "label": "UPI Timeout",
        "icon": "📱",
        "amount": 249900,
        "method": "upi",
        "email": "priya.sharma@gmail.com",
        "contact": "+919876543210",
        "order_id": "order_demo_upi_001",
        "payment_id": "pay_demo_upi_001",
        "error": "Payment was not completed due to a UPI timeout. The transaction was not processed.",
        "demo_link": "https://rzp.io/l/Kj7mPqR2",
    },
    "card_decline": {
        "label": "Card Declined",
        "icon": "💳",
        "amount": 99900,
        "method": "card",
        "email": "rohan.mehta@outlook.com",
        "contact": "+918765432109",
        "order_id": "order_demo_card_001",
        "payment_id": "pay_demo_card_001",
        "error": "Your payment was declined by the bank. Please try a different payment method or contact your bank.",
        "demo_link": "https://rzp.io/l/Hn4xWsT8",
    },
    "netbanking_failure": {
        "label": "Net Banking",
        "icon": "🏦",
        "amount": 499900,
        "method": "netbanking",
        "email": "ananya.iyer@yahoo.com",
        "contact": "+917654321098",
        "order_id": "order_demo_nb_001",
        "payment_id": "pay_demo_nb_001",
        "error": "Net banking session expired. Please retry with a fresh session.",
        "demo_link": "https://rzp.io/l/Bv9cLmY5",
    },
}


# ---------------------------------------------------------------------------
# Simulate endpoint
# ---------------------------------------------------------------------------
class SimulateRequest(BaseModel):
    scenario: str
    customer_phone: Optional[str] = None


@router.post("/demo/simulate")
async def simulate(req: SimulateRequest):
    if req.scenario not in SCENARIOS:
        return {"error": f"Unknown scenario: {req.scenario}"}

    s = copy.deepcopy(SCENARIOS[req.scenario])

    phone  = req.customer_phone.strip() if req.customer_phone else s["contact"]
    email  = GMAIL_FROM_ADDRESS  # always send to the configured address in demo
    amount = s["amount"] / 100.0
    reason = s["error"]
    method = s["method"]

    # 1. Create a Razorpay QR code — no contact form, just scan and pay
    from razorpay_client import create_qr_code
    qr_image_url, qr_id = await create_qr_code(
        amount_paise=s["amount"],
        description=f"retry payment · {s['label']} · Rs.{s['amount']//100}",
    )
    # Link points to our own checkout page — absolute URL so it works in email too
    import urllib.parse
    base = "http://localhost:8000"
    checkout_link = f"{base}/demo/checkout?qr={urllib.parse.quote(qr_image_url)}&amount={s['amount']//100}&label={urllib.parse.quote(s['label'])}"
    link = checkout_link

    # 2. Ask OpenAI to craft personalised jewellery-shop recovery messages
    msgs = await generate_recovery_messages(
        amount=amount,
        reason=reason,
        link=link,
        method=method,
    )

    # 3. Run SMS and email in parallel, capture individual results
    action_results: dict = {
        "ai_message": {
            "sms": msgs.sms,
            "email_subject": msgs.email_subject,
        }
    }

    async def _run(key: str, coro):
        try:
            await coro
            action_results[key] = {"status": "sent"}
        except Exception as exc:
            action_results[key] = {"status": "failed", "detail": str(exc)}

    await asyncio.gather(
        _run("sms",   send_sms(phone, amount, reason, link, custom_text=msgs.sms)),
        _run("email", send_email(email, amount, reason, link,
                                 custom_subject=msgs.email_subject,
                                 custom_body=msgs.email_body)),
        return_exceptions=True,
    )

    # 3. Slack gets the actual SMS/email outcome so the alert is accurate
    await _run(
        "slack",
        post_slack(
            payment_id=s["payment_id"],
            order_id=s["order_id"],
            amount=amount,
            reason=reason,
            phone=phone,
            email=email,
            method=method,
            link=link,
            sms_sent=action_results.get("sms", {}).get("status") == "sent",
            email_sent=action_results.get("email", {}).get("status") == "sent",
        ),
    )

    return {
        "payment_id": s["payment_id"],
        "order_id":   s["order_id"],
        "amount":     amount,
        "method":     method,
        "customer_phone": phone,
        "customer_email": email,
        "reason":     reason,
        "recovery_link": link,
        "actions":    action_results,
    }


# ---------------------------------------------------------------------------
# Demo HTML page
# ---------------------------------------------------------------------------
HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>failed payment recovery · live demo</title>
<link href="https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }

  html { scroll-snap-type: y mandatory; scroll-behavior: smooth; }

  body {
    font-family: 'Nunito Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    background: #F4F6FB;
    color: #012652;
    min-height: 100vh;
  }

  /* ── Nav ── */
  .nav {
    position: sticky; top: 0; z-index: 100;
    background: rgba(255,255,255,0.85);
    backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
    border-bottom: 1px solid rgba(0,0,0,0.06);
    height: 52px; padding: 0 28px;
    display: flex; align-items: center; gap: 10px;
  }
  .nav-logo { display: flex; align-items: center; gap: 8px; }
  .nav-rzp-dot {
    width: 24px; height: 24px; border-radius: 6px;
    background: #012652;
    display: flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: 900; color: #0D94FB;
    letter-spacing: -0.5px;
  }
  .nav-brand { font-size: 15px; font-weight: 700; color: #012652; letter-spacing: -0.02em; }
  .nav-sep { width: 1px; height: 16px; background: #E5E7EB; margin: 0 6px; }
  .nav-title { font-size: 14px; color: #6B7280; font-weight: 400; }
  .nav-live {
    margin-left: auto;
    display: flex; align-items: center; gap: 5px;
    font-size: 11px; font-weight: 600; color: #16A34A;
    background: #F0FDF4; border: 1px solid #BBF7D0;
    padding: 3px 10px; border-radius: 100px;
  }
  .nav-live-dot {
    width: 6px; height: 6px; background: #22C55E;
    border-radius: 50%; animation: pulse 2s infinite;
  }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }

  /* ── Hero (page 1) ── */
  .hero {
    background: #fff;
    padding: 0 24px;
    text-align: center;
    border-bottom: 1px solid #F3F4F6;
    min-height: calc(100vh - 52px);
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    scroll-snap-align: start;
  }
  .hero-chip {
    display: inline-flex; align-items: center; gap: 6px;
    background: #EFF6FF; color: #1D4ED8;
    border: 1px solid #BFDBFE;
    font-size: 14px; font-weight: 600;
    padding: 5px 14px; border-radius: 100px;
    margin-bottom: 32px; letter-spacing: 0.01em;
  }
  .hero h1 {
    font-size: clamp(44px, 7vw, 76px);
    font-weight: 800; letter-spacing: -0.04em;
    line-height: 1.05; color: #012652;
    margin-bottom: 24px;
  }
  .hero h1 em { font-style: normal; color: #0D94FB; }
  .hero-desc {
    font-size: 22px; color: #6B7280; font-weight: 400;
    max-width: 560px; margin: 0 auto 20px; line-height: 1.6;
  }
  .hero-sub {
    font-size: 17px; color: #9CA3AF;
    max-width: 500px; margin: 0 auto 64px; line-height: 1.6;
  }

  /* ── Webhook callout ── */
  .webhook-callout {
    display: inline-flex; align-items: flex-start; gap: 14px; text-align: left;
    background: #F8FAFF; border: 1px solid #E0E7FF;
    border-radius: 16px; padding: 20px 26px;
    max-width: 580px; margin: 0 auto 56px;
  }
  .wh-icon { font-size: 26px; flex-shrink: 0; margin-top: 1px; }
  .wh-title { font-size: 16px; font-weight: 700; color: #012652; margin-bottom: 6px; }
  .wh-body { font-size: 15px; color: #6B7280; line-height: 1.6; }
  .wh-body code {
    background: #EEF2FF; color: #4338CA;
    padding: 2px 6px; border-radius: 4px;
    font-family: 'SF Mono', Consolas, monospace; font-size: 13px;
  }

  /* ── Flow ── */
  .flow { display: flex; align-items: center; justify-content: center; gap: 0; flex-wrap: wrap; }
  .flow-node { display: flex; flex-direction: column; align-items: center; gap: 10px; }
  .flow-ball {
    width: 64px; height: 64px; border-radius: 18px;
    display: flex; align-items: center; justify-content: center; font-size: 28px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  }
  .fb-red   { background: #FFF1F0; }
  .fb-blue  { background: #EFF6FF; }
  .fb-green { background: #F0FDF4; }
  .flow-tag { font-size: 13px; font-weight: 600; color: #9CA3AF; letter-spacing: 0.03em; }
  .flow-arrow { color: #D1D5DB; font-size: 22px; margin: 0 16px; padding-bottom: 24px; }
  .flow-outs { display: flex; flex-direction: column; gap: 8px; }
  .flow-out-pill {
    display: flex; align-items: center; gap: 8px;
    background: #fff; border: 1px solid #E5E7EB;
    border-radius: 100px; padding: 8px 18px;
    font-size: 15px; font-weight: 500; color: #374151;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  }

  /* ── Stack bar ── */
  .stack-bar {
    background: #F9FAFB; border-top: 1px solid #F3F4F6; border-bottom: 1px solid #F3F4F6;
    padding: 20px 24px; text-align: center;
  }
  .stack-bar-label { font-size: 11px; font-weight: 600; color: #9CA3AF; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 14px; }
  .stack-chips { display: flex; align-items: center; justify-content: center; gap: 8px; flex-wrap: wrap; }
  .stack-chip {
    display: flex; align-items: center; gap: 6px;
    background: #fff; border: 1px solid #E5E7EB;
    border-radius: 100px; padding: 6px 14px;
    font-size: 13px; font-weight: 600; color: #374151;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
  }
  .chip-dot { width: 7px; height: 7px; border-radius: 50%; }
  .cd-rzp { background: #0D94FB; }
  .cd-twilio { background: #F22F46; }
  .cd-gmail { background: #EA4335; }
  .cd-slack { background: #611f69; }

  /* ── Why section (page 3) ── */
  .why-section {
    background: #fff; padding: 0 24px;
    min-height: 100vh;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    scroll-snap-align: start;
  }
  .why-inner { max-width: 800px; margin: 0 auto; padding: 80px 0; width: 100%; }
  .section-label { font-size: 13px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: #0D94FB; margin-bottom: 12px; }
  .section-title { font-size: clamp(32px, 5vw, 48px); font-weight: 800; color: #012652; letter-spacing: -0.03em; margin-bottom: 12px; line-height: 1.1; }
  .section-body { font-size: 20px; color: #6B7280; margin-bottom: 48px; line-height: 1.6; }
  .why-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
  .why-card {
    background: #F9FAFB; border: 1px solid #F3F4F6;
    border-radius: 20px; padding: 28px 26px;
    transition: box-shadow 0.2s;
  }
  .why-card:hover { box-shadow: 0 4px 20px rgba(1,38,82,0.08); }
  .why-emoji { font-size: 32px; margin-bottom: 14px; display: block; }
  .why-title { font-size: 18px; font-weight: 700; color: #012652; margin-bottom: 9px; letter-spacing: -0.01em; }
  .why-desc { font-size: 15px; color: #6B7280; line-height: 1.65; }
  .why-tag {
    display: inline-block; margin-top: 14px;
    background: #EFF6FF; color: #1D4ED8;
    font-size: 13px; font-weight: 600;
    padding: 4px 12px; border-radius: 6px;
  }

  /* ── Demo section (page 2) ── */
  .demo-section {
    background: #F9FAFB; padding: 0 24px;
    border-top: 1px solid #F3F4F6;
    min-height: 100vh;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    scroll-snap-align: start;
  }
  .demo-inner { max-width: 600px; margin: 0 auto; padding: 72px 0; width: 100%; }

  /* ── Card ── */
  .card {
    background: #fff; border-radius: 20px; padding: 32px;
    margin-bottom: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.04);
    border: 1px solid #F3F4F6;
  }
  .card-label {
    font-size: 13px; font-weight: 700; letter-spacing: 0.08em;
    text-transform: uppercase; color: #9CA3AF; margin-bottom: 22px;
  }

  /* ── Pills ── */
  .pills { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 24px; }
  .pill {
    padding: 10px 20px; border-radius: 100px;
    border: 1.5px solid #E5E7EB; background: #fff;
    font-size: 15px; font-weight: 600; color: #6B7280;
    cursor: pointer; transition: all 0.15s; font-family: inherit;
    white-space: nowrap;
  }
  .pill:hover { border-color: #0D94FB; color: #0D94FB; }
  .pill.active { background: #012652; border-color: #012652; color: #fff; }

  /* ── Field ── */
  .field { margin-bottom: 20px; }
  .field label { display: block; font-size: 15px; font-weight: 600; color: #374151; margin-bottom: 8px; }
  .field input {
    width: 100%; padding: 15px 17px;
    border: 1.5px solid #E5E7EB; border-radius: 12px;
    font-size: 17px; font-family: inherit; color: #111827;
    background: #F9FAFB; outline: none; transition: all 0.15s;
  }
  .field input:focus { border-color: #0D94FB; background: #fff; box-shadow: 0 0 0 3px rgba(13,148,251,0.1); }
  .field input::placeholder { color: #9CA3AF; }
  .field .hint { margin-top: 7px; font-size: 13px; color: #9CA3AF; line-height: 1.5; }

  /* ── Button ── */
  .btn {
    width: 100%; padding: 18px;
    background: #012652; color: #fff;
    border: none; border-radius: 14px;
    font-size: 17px; font-weight: 700; font-family: inherit;
    cursor: pointer; transition: all 0.15s;
    display: flex; align-items: center; justify-content: center; gap: 8px;
    letter-spacing: -0.01em;
  }
  .btn:hover { background: #013070; }
  .btn:active { transform: scale(0.98); }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .spinner {
    width: 16px; height: 16px;
    border: 2px solid rgba(255,255,255,0.25);
    border-top-color: #fff; border-radius: 50%;
    animation: spin 0.7s linear infinite; display: none;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Webhook log ── */
  .wh-log {
    background: #012652; border-radius: 14px;
    padding: 18px 20px; margin-bottom: 14px; display: none;
  }
  .wh-log.show { display: block; animation: fadeUp 0.25s ease; }
  .wh-log-title {
    font-size: 10px; font-weight: 700; color: rgba(255,255,255,0.3);
    letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 12px;
  }
  .log-row {
    font-family: 'SF Mono', Consolas, monospace;
    font-size: 12px; line-height: 1.9;
    display: flex; gap: 6px;
  }
  .lk { color: rgba(255,255,255,0.35); }
  .lv { color: #86EFAC; }
  .le { color: #FCA5A5; }

  /* ── Results ── */
  #results { display: none; }
  #results.show { display: block; animation: fadeUp 0.3s ease; }
  @keyframes fadeUp { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:translateY(0); } }

  .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 20px; }
  .info-cell { background: #F9FAFB; border-radius: 12px; padding: 14px 16px; border: 1px solid #F3F4F6; }
  .info-cell.full { grid-column: 1/-1; }
  .ic-label { font-size: 11px; font-weight: 700; color: #9CA3AF; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 4px; }
  .ic-value { font-size: 15px; font-weight: 600; color: #012652; word-break: break-all; }

  .action-list { display: flex; flex-direction: column; gap: 10px; margin-bottom: 20px; }
  .action-row {
    display: flex; align-items: center; gap: 14px;
    padding: 15px 17px; border-radius: 14px;
    background: #F9FAFB; border: 1px solid #F3F4F6;
  }
  .ar-icon { font-size: 22px; width: 36px; text-align: center; flex-shrink: 0; }
  .ar-body { flex: 1; min-width: 0; }
  .ar-name { font-size: 16px; font-weight: 700; color: #012652; }
  .ar-what { font-size: 13px; color: #6B7280; margin-top: 2px; }
  .ar-detail { font-size: 12px; color: #9CA3AF; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .badge { font-size: 12px; font-weight: 700; padding: 4px 12px; border-radius: 100px; flex-shrink: 0; }
  .b-sent    { background: #F0FDF4; color: #15803D; }
  .b-failed  { background: #FFF1F2; color: #BE123C; }
  .b-skipped { background: #F3F4F6; color: #6B7280; }

  .link-row {
    display: flex; align-items: center; gap: 14px;
    background: #F0F9FF; border: 1px solid #BAE6FD;
    border-radius: 14px; padding: 16px 18px;
  }
  .lr-icon { font-size: 22px; flex-shrink: 0; }
  .lr-body { flex: 1; min-width: 0; }
  .lr-label { font-size: 11px; font-weight: 700; color: #0369A1; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 4px; }
  .lr-url { font-size: 13px; color: #0D94FB; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .copy-btn {
    background: #0D94FB; color: #fff; border: none;
    border-radius: 8px; padding: 8px 16px;
    font-size: 13px; font-weight: 700; cursor: pointer;
    font-family: inherit; transition: opacity 0.15s; flex-shrink: 0;
  }
  .copy-btn:hover { opacity: 0.85; }

  .err-bar {
    background: #FFF1F2; border: 1px solid #FECDD3;
    border-radius: 10px; padding: 14px 16px;
    color: #BE123C; font-size: 15px; font-weight: 500;
    display: none; margin-top: 12px;
  }
</style>
</head>
<body>

<!-- Nav -->
<nav class="nav">
  <div class="nav-logo">
    <div class="nav-rzp-dot">R</div>
    <span class="nav-brand">Razorpay</span>
  </div>
  <div class="nav-sep"></div>
  <span class="nav-title">payment recovery</span>
  <div class="nav-live">
    <div class="nav-live-dot"></div>
    live demo
  </div>
</nav>

<!-- Hero (page 1) -->
<section class="hero">
  <div class="hero-chip">⚡ built on Razorpay webhooks</div>
  <h1>your customer's payment<br>just failed. <em>now what?</em></h1>
  <p class="hero-desc">you do nothing. the system handles it, in under 2 seconds.</p>
  <p class="hero-sub">the moment a payment fails, Razorpay pings this app. the customer gets an SMS, an email, and a fresh payment link. your team gets a Slack alert. zero manual work.</p>

  <!-- Webhook explainer -->
  <div class="webhook-callout">
    <div class="wh-icon">🔔</div>
    <div>
      <div class="wh-title">wait, what's a webhook?</div>
      <div class="wh-body">think of it like a doorbell. when a payment fails, Razorpay rings your app's doorbell with a <code>POST /webhook</code> call, with all the details. your app answers and takes action instantly. no polling. no delays.</div>
    </div>
  </div>

  <!-- Flow -->
  <div class="flow">
    <div class="flow-node">
      <div class="flow-ball fb-red">💸</div>
      <div class="flow-tag">payment fails</div>
    </div>
    <div class="flow-arrow">→</div>
    <div class="flow-node">
      <div class="flow-ball fb-blue">🔔</div>
      <div class="flow-tag">webhook fires</div>
    </div>
    <div class="flow-arrow">→</div>
    <div class="flow-node">
      <div class="flow-ball fb-green">🔗</div>
      <div class="flow-tag">new link created</div>
    </div>
    <div class="flow-arrow">→</div>
    <div class="flow-outs">
      <div class="flow-out-pill">📱 SMS to customer</div>
      <div class="flow-out-pill">✉️ email to customer</div>
      <div class="flow-out-pill">🔔 Slack alert for you</div>
    </div>
  </div>
</section>

<!-- Demo (page 2) -->
<section class="demo-section">
  <div class="demo-inner">
    <div class="section-label">try it live</div>
    <div class="section-title" style="margin-bottom:8px;">see it fire in real time.</div>
    <div class="section-body" style="margin-bottom:32px;">pick a scenario, enter a phone number, and watch SMS + email + Slack all trigger at once.</div>

    <div class="card">
      <div class="card-label">simulate a failed payment</div>
      <div class="pills">
        <button class="pill active" data-scenario="upi_timeout">📱 UPI timeout</button>
        <button class="pill" data-scenario="card_decline">💳 card declined</button>
        <button class="pill" data-scenario="netbanking_failure">🏦 net banking</button>
      </div>
      <div class="field">
        <label>customer phone number</label>
        <input type="tel" id="phoneInput" placeholder="+91 98765 43210">
        <div class="hint">use a Twilio-verified number to actually receive the SMS. leave blank to use the demo number.</div>
      </div>
      <button class="btn" id="simulateBtn" onclick="runSimulation()">
        <span class="spinner" id="spinner"></span>
        <span id="btnText">simulate failed payment</span>
      </button>
      <div class="err-bar" id="errBar"></div>
    </div>

    <!-- Webhook log -->
    <div class="wh-log" id="whLog">
      <div class="wh-log-title">webhook payload · what Razorpay sends</div>
      <div id="logLines"></div>
    </div>

    <!-- Results -->
    <div class="card" id="results">
      <div class="card-label">what just happened</div>
      <div class="info-grid" id="infoGrid"></div>
      <div id="aiMessage"></div>
      <div class="action-list" id="actionList"></div>
      <div id="linkRow"></div>
    </div>
  </div>
</section>

<!-- Stack bar -->
<div class="stack-bar">
  <div class="stack-bar-label">Built with</div>
  <div class="stack-chips">
    <div class="stack-chip"><span class="chip-dot cd-rzp"></span>Razorpay</div>
    <div class="stack-chip"><span class="chip-dot cd-twilio"></span>Twilio SMS</div>
    <div class="stack-chip"><span class="chip-dot cd-gmail"></span>Gmail</div>
    <div class="stack-chip"><span class="chip-dot cd-slack"></span>Slack</div>
    <div class="stack-chip">⚡ FastAPI</div>
  </div>
</div>

<!-- Why section -->
<section class="why-section">
  <div class="why-inner">
    <div class="section-label">why it matters</div>
    <div class="section-title">every failed payment is a<br>sale you're about to lose.</div>
    <div class="section-body">most businesses do nothing when a payment fails. the customer gets confused, gives up, and buys elsewhere. this system fights back, automatically.</div>
    <div class="why-grid">
      <div class="why-card">
        <span class="why-emoji">😤</span>
        <div class="why-title">they didn't change their mind</div>
        <div class="why-desc">a UPI timeout or card decline doesn't mean the customer left. something just broke. a quick SMS with a fresh link brings them back before they forget.</div>
        <span class="why-tag">📱 sms in under 5 seconds</span>
      </div>
      <div class="why-card">
        <span class="why-emoji">💌</span>
        <div class="why-title">email keeps it professional</div>
        <div class="why-desc">a clean email explains what happened in plain english, no confusing bank codes, with a big "retry payment" button. simple. friendly. effective.</div>
        <span class="why-tag">✉️ sent instantly</span>
      </div>
      <div class="why-card">
        <span class="why-emoji">🔗</span>
        <div class="why-title">no "go back to checkout"</div>
        <div class="why-desc">this generates a fresh Razorpay payment link valid for 24 hours. customer clicks, pays. no friction, no starting over from scratch.</div>
        <span class="why-tag">🔗 link valid 24 hours</span>
      </div>
      <div class="why-card">
        <span class="why-emoji">🔔</span>
        <div class="why-title">your team sees it, and knows what to do</div>
        <div class="why-desc">every failure posts to Slack with the amount, payment method, and reason. if the customer still doesn't pay after the SMS + email, your ops team can personally follow up, issue a refund, or flag a repeat failure pattern, before it becomes a complaint.</div>
        <span class="why-tag">🔔 #payment-ops alert</span>
      </div>
    </div>
  </div>
</section>

<script>
  let sel = 'upi_timeout';
  const sd = {
    upi_timeout:        { amount: 'Rs. 2,499', method: 'UPI',         err: 'UPI timed out, customer did not complete the payment' },
    card_decline:       { amount: 'Rs. 999',   method: 'Credit Card', err: 'Card declined by bank, insufficient funds' },
    netbanking_failure: { amount: 'Rs. 4,999', method: 'Net Banking', err: 'Net banking session expired mid-payment' },
  };

  document.querySelectorAll('.pill').forEach(p => p.addEventListener('click', () => {
    document.querySelectorAll('.pill').forEach(x => x.classList.remove('active'));
    p.classList.add('active');
    sel = p.dataset.scenario;
  }));

  async function runSimulation() {
    const btn = document.getElementById('simulateBtn');
    const sp  = document.getElementById('spinner');
    const bt  = document.getElementById('btnText');
    const err = document.getElementById('errBar');

    btn.disabled = true; sp.style.display = 'block'; bt.textContent = 'sending...';
    err.style.display = 'none';
    document.getElementById('results').classList.remove('show');
    document.getElementById('whLog').classList.remove('show');

    const phone = document.getElementById('phoneInput').value.trim();
    const s = sd[sel];

    // Show webhook log
    document.getElementById('logLines').innerHTML = [
      `<div class="log-row"><span class="lk">event: </span><span class="lv">"payment.failed"</span></div>`,
      `<div class="log-row"><span class="lk">amount: </span><span class="lv">"${s.amount}"</span></div>`,
      `<div class="log-row"><span class="lk">method: </span><span class="lv">"${s.method}"</span></div>`,
      `<div class="log-row"><span class="lk">error:  </span><span class="le">"${s.err}"</span></div>`,
      `<div class="log-row"><span class="lk">contact:</span><span class="lv">"${phone || '+91XXXXXXXXXX'}"</span></div>`,
    ].join('');
    document.getElementById('whLog').classList.add('show');

    try {
      const res  = await fetch('/demo/simulate', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ scenario: sel, customer_phone: phone || null }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      render(data);
    } catch(e) {
      err.textContent = 'Error: ' + e.message;
      err.style.display = 'block';
    } finally {
      btn.disabled = false; sp.style.display = 'none'; bt.textContent = 'simulate failed payment';
    }
  }

  function render(d) {
    const ml = { upi:'UPI', card:'credit / debit card', netbanking:'net banking' };
    document.getElementById('infoGrid').innerHTML = `
      <div class="info-cell"><div class="ic-label">Amount</div><div class="ic-value">Rs. ${d.amount.toFixed(2)}</div></div>
      <div class="info-cell"><div class="ic-label">Method</div><div class="ic-value">${ml[d.method]||d.method}</div></div>
      <div class="info-cell"><div class="ic-label">Customer Phone</div><div class="ic-value">${d.customer_phone||'n/a'}</div></div>
      <div class="info-cell"><div class="ic-label">Customer Email</div><div class="ic-value">${d.customer_email||'n/a'}</div></div>
      <div class="info-cell full"><div class="ic-label">Why it failed</div><div class="ic-value" style="font-weight:400;font-size:13px;color:#6B7280;">${d.reason}</div></div>
    `;

    // Show AI-generated message if present
    const ai = d.actions.ai_message;
    if (ai) {
      document.getElementById('aiMessage').innerHTML = `
        <div style="background:#F0F7FF;border:1px solid #BFDBFE;border-radius:12px;padding:16px 20px;margin-bottom:16px;">
          <div style="font-size:11px;font-weight:700;color:#0D94FB;letter-spacing:0.05em;text-transform:uppercase;margin-bottom:10px;">
            ✦ openai-generated recovery message
          </div>
          <div style="font-size:13px;color:#1E3A5F;line-height:1.6;margin-bottom:8px;">
            <span style="font-weight:600;">sms:</span> ${ai.sms}
          </div>
          <div style="font-size:13px;color:#1E3A5F;line-height:1.6;">
            <span style="font-weight:600;">email subject:</span> ${ai.email_subject}
          </div>
        </div>`;
    }

    const am = {
      sms:   { icon:'📱', name:'sms to customer',   what:'sent AI-crafted text with retry link',      detail: d.customer_phone },
      email: { icon:'✉️',  name:'email to customer', what:'sent AI-crafted recovery email',            detail: d.customer_email },
      slack: { icon:'🔔', name:'slack alert',        what:'posted to #payment-ops with full details',  detail: '#payment-ops' },
    };
    // Filter out ai_message — it's metadata, not an action
    document.getElementById('actionList').innerHTML = Object.entries(d.actions)
      .filter(([k]) => k !== 'ai_message')
      .map(([k, r]) => {
      const m = am[k] || { icon:'?', name:k, what:'', detail:'' };
      const label = r.status === 'sent' ? 'sent' : r.status === 'failed' ? 'failed' : 'skipped';
      const bc    = r.status === 'sent' ? 'b-sent' : r.status === 'failed' ? 'b-failed' : 'b-skipped';
      const det   = r.status === 'failed' ? r.detail : m.detail || '';
      return `<div class="action-row">
        <div class="ar-icon">${m.icon}</div>
        <div class="ar-body">
          <div class="ar-name">${m.name}</div>
          <div class="ar-what">${m.what}</div>
          ${det ? `<div class="ar-detail">${det}</div>` : ''}
        </div>
        <div class="badge ${bc}">${label}</div>
      </div>`;
    }).join('');

    document.getElementById('linkRow').innerHTML = `
      <div class="link-row">
        <div class="lr-icon">🔗</div>
        <div class="lr-body">
          <div class="lr-label">recovery link sent to customer</div>
          <div class="lr-url">${d.recovery_link}</div>
        </div>
        <button class="copy-btn" onclick="doCopy('${d.recovery_link}',event)">copy</button>
      </div>`;

    document.getElementById('results').classList.add('show');
    document.getElementById('results').scrollIntoView({ behavior:'smooth', block:'nearest' });
  }

  function doCopy(url, e) {
    navigator.clipboard.writeText(url).then(() => {
      e.target.textContent = 'copied!';
      setTimeout(() => e.target.textContent = 'copy', 1500);
    });
  }
</script>
</body>
</html>"""


@router.get("/demo", response_class=HTMLResponse)
async def demo_page():
    return HTML


@router.get("/demo/checkout", response_class=HTMLResponse)
async def checkout_page(qr: str = "", amount: str = "", label: str = ""):
    """Shows a clean QR code page — no contact form, just scan and pay."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>scan to pay · rzp-demo</title>
<link href="https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family: 'Nunito Sans', -apple-system, sans-serif;
    background: #F4F6FB; min-height: 100vh;
    display: flex; align-items: center; justify-content: center;
    padding: 24px;
  }}
  .card {{
    background: #fff; border-radius: 24px; padding: 40px 36px;
    box-shadow: 0 4px 32px rgba(1,38,82,0.10);
    max-width: 380px; width: 100%; text-align: center;
  }}
  .brand {{ font-size: 13px; font-weight: 700; color: #9CA3AF; letter-spacing: 0.05em; margin-bottom: 24px; }}
  .amount {{ font-size: 42px; font-weight: 800; color: #012652; letter-spacing: -0.04em; margin-bottom: 4px; }}
  .label {{ font-size: 14px; color: #6B7280; margin-bottom: 28px; }}
  .qr-wrap {{
    background: #F9FAFB; border: 1px solid #F3F4F6;
    border-radius: 20px; padding: 20px; margin-bottom: 24px;
    display: flex; align-items: center; justify-content: center;
  }}
  .qr-wrap img {{ width: 220px; height: 220px; border-radius: 8px; }}
  .hint {{ font-size: 13px; color: #9CA3AF; line-height: 1.6; }}
  .hint strong {{ color: #374151; }}
  .rzp-badge {{
    display: inline-flex; align-items: center; gap: 6px;
    margin-top: 28px; font-size: 12px; color: #9CA3AF;
  }}
  .rzp-dot {{ width: 8px; height: 8px; background: #0D94FB; border-radius: 50%; }}
</style>
</head>
<body>
<div class="card">
  <div class="brand">rzp-demo · payment recovery</div>
  <div class="amount">₹{amount}</div>
  <div class="label">{label} · retry payment</div>
  <div class="qr-wrap">
    {"<img src='" + qr + "' alt='UPI QR code' />" if qr else "<div style='color:#9CA3AF;font-size:14px;'>QR unavailable</div>"}
  </div>
  <div class="hint">
    <strong>scan with any UPI app</strong><br>
    Google Pay · PhonePe · Paytm · BHIM · any bank app
  </div>
  <div class="rzp-badge">
    <div class="rzp-dot"></div>
    powered by razorpay
  </div>
</div>
</body>
</html>"""
