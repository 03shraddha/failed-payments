"""
Demo: Simulate a Razorpay payment.failed webhook
-------------------------------------------------
This script fires a realistic failed-payment webhook at your local server.
It generates a valid HMAC-SHA256 signature so the server accepts it.

Usage:
    # Make sure server is running first:
    #   uvicorn main:app --reload --port 8000

    python demo/send_webhook.py --phone +919876543210

    # Override server URL:
    python demo/send_webhook.py --phone +919876543210 --url http://localhost:8000

    # Test missing phone (SMS should be skipped):
    python demo/send_webhook.py --scenario no_phone

    # Test missing email (Email should be skipped):
    python demo/send_webhook.py --scenario no_email

    # Test card decline instead of UPI timeout:
    python demo/send_webhook.py --scenario card_decline
"""

import argparse
import hashlib
import hmac
import json
import os
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Realistic demo scenarios
# ---------------------------------------------------------------------------

SCENARIOS = {
    "upi_timeout": {
        "description": "Priya's UPI payment timed out - most common failure in India",
        "payload": {
            "entity": "event",
            "account_id": "acc_demo123",
            "event": "payment.failed",
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_demo_upi_001",
                        "entity": "payment",
                        "amount": 249900,       # ₹2,499 - online course purchase
                        "currency": "INR",
                        "status": "failed",
                        "order_id": "order_demo_upi_001",
                        "method": "upi",
                        "email": "priya.sharma@gmail.com",
                        "contact": "+919876543210",
                        "description": "Python Masterclass - Full Course",
                        "error_code": "BAD_REQUEST_ERROR",
                        "error_description": "Payment was not completed due to a UPI timeout. The transaction was not processed.",
                        "error_source": "customer",
                        "error_step": "payment_authorization",
                        "error_reason": "payment_timeout",
                        "created_at": int(time.time()),
                    }
                }
            },
        },
    },
    "card_decline": {
        "description": "Rohan's card was declined - insufficient funds",
        "payload": {
            "entity": "event",
            "account_id": "acc_demo123",
            "event": "payment.failed",
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_demo_card_001",
                        "entity": "payment",
                        "amount": 99900,        # ₹999 - monthly subscription
                        "currency": "INR",
                        "status": "failed",
                        "order_id": "order_demo_card_001",
                        "method": "card",
                        "email": "rohan.mehta@outlook.com",
                        "contact": "+918765432109",
                        "description": "Pro Plan - Monthly Subscription",
                        "error_code": "BAD_REQUEST_ERROR",
                        "error_description": "Your payment was declined by the bank. Please try a different payment method or contact your bank.",
                        "error_source": "bank",
                        "error_step": "payment_authorization",
                        "error_reason": "insufficient_funds",
                        "created_at": int(time.time()),
                    }
                }
            },
        },
    },
    "netbanking_failure": {
        "description": "Ananya's net banking session expired mid-payment",
        "payload": {
            "entity": "event",
            "account_id": "acc_demo123",
            "event": "payment.failed",
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_demo_nb_001",
                        "entity": "payment",
                        "amount": 499900,       # ₹4,999 - annual plan
                        "currency": "INR",
                        "status": "failed",
                        "order_id": "order_demo_nb_001",
                        "method": "netbanking",
                        "email": "ananya.iyer@yahoo.com",
                        "contact": "+917654321098",
                        "description": "Enterprise Plan - Annual",
                        "error_code": "GATEWAY_ERROR",
                        "error_description": "Net banking session expired. Please retry with a fresh session.",
                        "error_source": "gateway",
                        "error_step": "payment_authentication",
                        "error_reason": "session_expired",
                        "created_at": int(time.time()),
                    }
                }
            },
        },
    },
    "no_phone": {
        "description": "UPI failure where customer phone is missing (SMS should be skipped)",
        "payload": {
            "entity": "event",
            "account_id": "acc_demo123",
            "event": "payment.failed",
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_demo_nophone_001",
                        "entity": "payment",
                        "amount": 149900,
                        "currency": "INR",
                        "status": "failed",
                        "order_id": "order_demo_nophone_001",
                        "method": "upi",
                        "email": "test.nophone@gmail.com",
                        "contact": None,        # ← missing phone
                        "description": "Test - No Phone",
                        "error_code": "BAD_REQUEST_ERROR",
                        "error_description": "UPI timeout",
                        "error_source": "customer",
                        "error_step": "payment_authorization",
                        "error_reason": "payment_timeout",
                        "created_at": int(time.time()),
                    }
                }
            },
        },
    },
    "no_email": {
        "description": "Card decline where customer email is missing (email should be skipped)",
        "payload": {
            "entity": "event",
            "account_id": "acc_demo123",
            "event": "payment.failed",
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_demo_noemail_001",
                        "entity": "payment",
                        "amount": 79900,
                        "currency": "INR",
                        "status": "failed",
                        "order_id": "order_demo_noemail_001",
                        "method": "card",
                        "email": None,          # ← missing email
                        "contact": "+919999999999",
                        "description": "Test - No Email",
                        "error_code": "BAD_REQUEST_ERROR",
                        "error_description": "Card declined",
                        "error_source": "bank",
                        "error_step": "payment_authorization",
                        "error_reason": "payment_declined",
                        "created_at": int(time.time()),
                    }
                }
            },
        },
    },
}


def sign_payload(secret: str, body: bytes) -> str:
    """Generate the HMAC-SHA256 hex signature Razorpay would attach."""
    return hmac.new(
        key=secret.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()


def send_demo_webhook(
    server_url: str,
    webhook_secret: str,
    scenario_name: str,
    phone_override: str | None = None,
) -> None:
    import copy
    scenario = copy.deepcopy(SCENARIOS[scenario_name])

    # Allow overriding the phone so Twilio trial accounts can use a verified number
    if phone_override:
        scenario["payload"]["payload"]["payment"]["entity"]["contact"] = phone_override
    print(f"\n{'='*60}")
    print(f"Scenario : {scenario_name}")
    print(f"Story    : {scenario['description']}")
    print(f"Server   : {server_url}/webhook/payment-failed")
    print(f"{'='*60}")

    # Serialize to compact JSON - no spaces - matching what Razorpay sends
    body: bytes = json.dumps(
        scenario["payload"], separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")

    signature = sign_payload(webhook_secret, body)
    print(f"Signature: {signature[:16]}... (truncated)")

    # Show the payment details
    entity = scenario["payload"]["payload"]["payment"]["entity"]
    amount = entity["amount"] / 100
    print(f"\nPayment details:")
    print(f"  Amount : Rs.{amount:.2f}")
    print(f"  Method : {entity['method']}")
    print(f"  Phone  : {entity.get('contact') or 'MISSING'}")
    print(f"  Email  : {entity.get('email') or 'MISSING'}")
    print(f"  Reason : {entity['error_description']}")

    print(f"\nSending webhook...")

    try:
        response = httpx.post(
            f"{server_url}/webhook/payment-failed",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": signature,
            },
            timeout=30.0,
        )
        print(f"\nStatus : {response.status_code}")
        print(f"Response: {response.json()}")

        if response.status_code == 200:
            print("\nOK Webhook accepted. Check:")
            if entity.get("contact"):
                print(f"  SMS -> {entity['contact']}")
            else:
                print("  SMS -> skipped (no phone)")
            if entity.get("email"):
                print(f"  Email -> {entity['email']}")
            else:
                print("  Email -> skipped (no email)")
            print("  Slack -> #payment-ops")
        else:
            print(f"\nFAILED Webhook rejected: {response.text}")

    except httpx.ConnectError:
        print(f"\nERROR Could not connect to {server_url}")
        print("  Make sure the server is running:")
        print("  uvicorn main:app --reload --port 8000")


def main():
    parser = argparse.ArgumentParser(description="Send a demo failed-payment webhook")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Server URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--scenario",
        default="upi_timeout",
        choices=list(SCENARIOS.keys()),
        help="Which scenario to simulate (default: upi_timeout)",
    )
    parser.add_argument(
        "--phone",
        default=None,
        help="Override customer phone number in the scenario (use your Twilio-verified number)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available scenarios",
    )
    args = parser.parse_args()

    if args.list:
        print("Available scenarios:")
        for name, s in SCENARIOS.items():
            print(f"  {name:<20} - {s['description']}")
        return

    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET")
    if not secret:
        print("Error: RAZORPAY_WEBHOOK_SECRET not set in .env")
        print("Copy .env.example → .env and fill in your webhook secret.")
        sys.exit(1)

    send_demo_webhook(
        server_url=args.url,
        webhook_secret=secret,
        scenario_name=args.scenario,
        phone_override=args.phone,
    )


if __name__ == "__main__":
    main()
