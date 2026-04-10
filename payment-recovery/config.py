import os
from dotenv import load_dotenv

load_dotenv()

# --- Razorpay ---
RAZORPAY_KEY_ID         = os.environ["RAZORPAY_KEY_ID"]
RAZORPAY_KEY_SECRET     = os.environ["RAZORPAY_KEY_SECRET"]
RAZORPAY_WEBHOOK_SECRET = os.environ["RAZORPAY_WEBHOOK_SECRET"]
RAZORPAY_API_BASE       = "https://api.razorpay.com/v1"

# --- Twilio ---
TWILIO_ACCOUNT_SID  = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN   = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_FROM_NUMBER  = os.environ["TWILIO_FROM_NUMBER"]

# --- Gmail ---
GMAIL_FROM_ADDRESS  = os.environ["GMAIL_FROM_ADDRESS"]
GMAIL_APP_PASSWORD  = os.environ["GMAIL_APP_PASSWORD"]
GMAIL_SMTP_HOST     = "smtp.gmail.com"
GMAIL_SMTP_PORT     = 587

# --- Slack ---
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_CHANNEL   = os.environ["SLACK_CHANNEL"]

# --- OpenAI ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# --- Business ---
# Optional: falls back to a generic name if not set
BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Our Store")
