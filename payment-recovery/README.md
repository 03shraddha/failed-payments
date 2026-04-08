# Failed Payment Recovery

Automatically recovers failed Razorpay payments by sending SMS, email, and Slack alerts with a fresh payment link — all triggered via webhook.

## What It Does

When a payment fails on Razorpay:
1. Razorpay sends a webhook to this server
2. The server verifies the webhook signature (HMAC-SHA256)
3. Generates a fresh Razorpay payment link (valid 24 hours)
4. Simultaneously sends:
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

- **FastAPI** — web framework
- **Razorpay** — payment gateway & webhooks
- **Twilio** — SMS notifications
- **Gmail SMTP** — email notifications
- **Slack SDK** — Slack alerts
- **OpenAI GPT-4o-mini** — AI-personalised recovery messages (optional)
- **Anthropic Claude + MCP** — alternative MCP-based Slack dispatch (optional)
