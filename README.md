# Failed Payment Recovery

Automatically recovers failed Razorpay payments by sending SMS, email, and Slack alerts with a fresh payment link — all triggered via webhook.

---

## What It Does

When a payment fails on Razorpay:

| Step | What happens |
|------|-------------|
| 1 | Razorpay sends a webhook to this server |
| 2 | Server verifies the webhook signature (HMAC-SHA256) |
| 3 | Generates a fresh Razorpay payment link (valid 24 hours) |
| 4 | Simultaneously sends SMS, Email, and a Slack alert |

**Notifications sent in parallel:**
- **SMS** (via Twilio) to the customer's phone
- **Email** (via Gmail SMTP) to the customer's email
- **Slack alert** to your `#payment-ops` channel

A browser-based **demo UI** is available at `/demo` to simulate all three scenarios without touching real Razorpay data.

---

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/03shraddha/failed-payments.git
cd failed-payments/payment-recovery

# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Then open `.env` and set each value:

```env
# ── Razorpay ────────────────────────────────────────────────────────────────
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxx
RAZORPAY_KEY_SECRET=your_key_secret_here
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret_here

# ── Twilio (SMS) ─────────────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_twilio_auth_token_here
TWILIO_FROM_NUMBER=+1xxxxxxxxxx

# ── Gmail (Email) ────────────────────────────────────────────────────────────
GMAIL_FROM_ADDRESS=yourname@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

# ── Slack ────────────────────────────────────────────────────────────────────
SLACK_BOT_TOKEN=xoxb-xxxxxxxxxxxx-xxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxx
SLACK_CHANNEL=#payment-ops

# ── Business ─────────────────────────────────────────────────────────────────
BUSINESS_NAME=Your Business Name

# ── OpenAI (optional) ────────────────────────────────────────────────────────
# If set, the demo UI generates AI-personalised recovery messages.
# Leave blank to use the built-in templates instead.
OPENAI_API_KEY=sk-...
```

> **Your `.env` is listed in `.gitignore` and will never be committed.**

---

### How to get each credential

#### Razorpay
1. Log in to [dashboard.razorpay.com](https://dashboard.razorpay.com)
2. **API Keys** → Generate a key pair → copy `Key ID` and `Key Secret`
3. **Webhooks** → Add webhook → set URL to `https://your-domain/webhook/payment-failed`, select the `payment.failed` event, and set a **Secret** — this becomes `RAZORPAY_WEBHOOK_SECRET`

#### Twilio (SMS)
1. Sign up at [twilio.com](https://www.twilio.com)
2. From the Console dashboard copy **Account SID** and **Auth Token**
3. Buy a phone number → copy it as `TWILIO_FROM_NUMBER` (E.164 format, e.g. `+16065190553`)

#### Gmail (Email)
1. Enable **2-Step Verification** on your Google account
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Create an app password for "Mail" → copy the 16-character code as `GMAIL_APP_PASSWORD`
4. Set `GMAIL_FROM_ADDRESS` to the Gmail address you generated the password for

#### Slack
1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → From scratch
2. Under **OAuth & Permissions** → add these Bot Token Scopes: `chat:write`, `chat:write.public`
3. Install the app to your workspace → copy the **Bot User OAuth Token** (`xoxb-...`) as `SLACK_BOT_TOKEN`
4. Set `SLACK_CHANNEL` to the channel you want alerts in (e.g. `#payment-ops`)

---

### 3. Run the server

```bash
venv\Scripts\uvicorn main:app --reload   # Windows
# uvicorn main:app --reload              # macOS / Linux
```

Server starts at `http://localhost:8000`.

To expose it to Razorpay webhooks locally, use [ngrok](https://ngrok.com):
```bash
ngrok http 8000
```
Then set the ngrok HTTPS URL as your Razorpay webhook URL.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/health` | Health check — returns `{"status": "ok"}` |
| `POST` | `/webhook/payment-failed` | Razorpay webhook receiver |
| `GET`  | `/demo` | Browser-based simulation UI |
| `POST` | `/demo/simulate` | Runs a real simulation (SMS + Email + Slack) |

---

## Demo UI

Open `http://localhost:8000/demo` in your browser. Choose a scenario (UPI Timeout, Card Declined, Net Banking), optionally enter your own phone number, and click **Run Simulation**. It fires real SMS, email, and Slack messages so you can verify the full flow without a live Razorpay event.

---

## Project Structure

```
payment-recovery/
├── main.py               # FastAPI app + webhook handler
├── config.py             # All env vars loaded here
├── razorpay_client.py    # Creates fresh payment links via Razorpay API
├── verify.py             # HMAC-SHA256 webhook signature verification
├── demo_ui.py            # /demo page + /demo/simulate endpoint
├── actions/
│   ├── sms.py            # Twilio SMS dispatch
│   ├── email.py          # Gmail SMTP dispatch
│   ├── slack.py          # Slack SDK alert
│   ├── slack_mcp.py      # Alternative: Slack via MCP + Claude tool use
│   └── message_generator.py  # OpenAI GPT-4o-mini personalised messages
├── demo/
│   ├── send_webhook.py   # CLI script to simulate a webhook locally
│   └── test_signature.py # Verify HMAC signing works
├── .env.example          # Template — copy to .env and fill in
├── .gitignore            # .env and logs are excluded
└── requirements.txt      # All dependencies
```

---

## Tech Stack

| Layer | Technology | Role |
|-------|-----------|------|
| Web framework | **FastAPI** | Handles webhook + demo endpoints |
| Payment gateway | **Razorpay** | Webhooks + payment link generation |
| SMS | **Twilio** | Customer SMS notifications |
| Email | **Gmail SMTP** | Customer email notifications |
| Alerting | **Slack SDK** | Internal `#payment-ops` alerts |
| AI messages | **OpenAI GPT-4o-mini** | Personalised recovery messages (optional) |
| Alt Slack path | **Anthropic Claude + MCP** | MCP-based Slack dispatch (optional) |

---

## Overview

This system addresses a specific revenue leak: when a payment fails on Razorpay, customers are typically left on a generic error screen with no guided path to retry. The drop-off rate at that point is high. This server intercepts the `payment.failed` webhook event and immediately dispatches a coordinated recovery sequence — a fresh payment link delivered over SMS, email, and an internal Slack alert — all within a single webhook lifecycle.

The entry point is a single POST endpoint (`/webhook/payment-failed`). It verifies the request, extracts customer and order data from the Razorpay payload, generates a new 24-hour payment link, and fans out three notifications in parallel. The `/demo` UI provides a self-contained simulation of all three failure scenarios (UPI timeout, card decline, net banking failure) using real credentials but synthetic order data — useful for testing integrations without a live failed payment.

---

## Narrative

### Parallel dispatch within webhook SLA

The starting constraint was delivery reliability within a tight SLA. Razorpay expects webhook responses within 10 seconds; any downstream API call — Twilio, Gmail, Slack — that blocks sequentially would exhaust that budget under normal network conditions. The solution was `asyncio.gather` with `return_exceptions=True`, which dispatches all three notification channels in parallel and isolates individual failures. A Slack alert still fires even if the SMS fails; an email still sends even if Slack is down.

### Signature verification on raw bytes

The second decision was where to verify identity. Reading the raw request bytes before any JSON parsing was deliberate — HMAC-SHA256 signatures are computed over the exact wire bytes Razorpay sent. Re-serialising parsed JSON and verifying that would silently break on any whitespace or key-ordering difference. The raw bytes are buffered first, verified, then parsed.

### Payment link as a recoverable dependency

Payment link generation was treated as a recoverable dependency rather than a hard requirement. If the Razorpay API call to create a new link fails (timeout, invalid order, API error), the system falls back to a well-formed `rzp.io` short URL constructed from the order ID. Downstream actions always receive a valid link — they never need to handle a null.

### AI messaging isolated to demo

The third layer added was AI-personalised messaging via OpenAI. Rather than coupling it to the main webhook path, it was isolated to the demo UI, where latency is acceptable and the fallback to static templates is transparent. The production webhook path uses direct templates that are deterministic and fast.

### MCP-based Slack as a drop-in alternative

A parallel implementation of the Slack action (`slack_mcp.py`) was built to explore the MCP pattern — spawning the official Slack MCP server as a subprocess, listing its tools, and letting Claude decide to call `slack_post_message` via tool use rather than hardcoded SDK calls. Both implementations share the same function signature, making them drop-in replaceable.

### SMS delivery and carrier-level DND (India)

SMS delivery surfaced a late-stage constraint specific to the Indian market: Twilio trial accounts restrict outbound SMS to verified numbers only, and even on paid plans, carrier-level DND filtering silently accepts the API request (HTTP 201) while dropping the message. The initial implementation logged "SMS sent" on a 201 response, masking these failures entirely. The revised version polls the message status after dispatch and raises explicitly on `undelivered` or `failed`, so the demo UI reflects actual delivery state rather than API acceptance.

---

## Technical Reflection

### Constraints encountered

| Problem | Root cause | Fix applied |
|---------|-----------|-------------|
| Blocking I/O in async handlers | Twilio + Slack `WebClient` are synchronous | Wrapped all three actions in `asyncio.to_thread` |
| Event loop blocked on Slack MCP calls | `Anthropic()` (sync) instantiated inside async function | Switched to `AsyncAnthropic()` with `await` |

### Potential failure points under scale

| Area | Risk | Mitigation needed |
|------|------|-------------------|
| Twilio + Slack clients | Module-level singletons with connection pools that exhaust under sustained parallel load | Add connection limits |
| Gmail SMTP | Opens a new connection per email — does not pool | Put a queue in front of it |
| Webhook idempotency | No deduplication check — Razorpay retries on non-2xx cause duplicate links + messages | Add a deduplication layer keyed on `payment_id` |
| Config loading | All env vars loaded at import time via `os.environ[...]` — missing var raises `KeyError` at startup, app cannot start with incomplete config | Acceptable fail-fast behaviour; no graceful degradation path |

### Long-term maintenance considerations

| Component | Concern |
|-----------|---------|
| `message_generator.py` | Prompt hardcodes business name and product category from `BUSINESS_NAME` — both system and user prompt need updating together if context changes |
| `message_generator.py` | Model pinned to `gpt-4o-mini` — OpenAI deprecations require a manual update |
| `slack_mcp.py` | Spawns an `npx` subprocess per call, adding Node.js as a runtime dependency and 2–3 seconds of cold-start latency — architecturally interesting but not suitable for production at any volume; `slack.py` is the production path |
| `/demo/simulate` endpoint | No authentication — any caller who discovers the endpoint on a public deployment can trigger real SMS and email sends against live credentials; gate behind a secret token or remove before public deployment |
