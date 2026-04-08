"""
Utility: generate a valid signature for manual curl testing.

Usage:
    python demo/test_signature.py

Prints the curl command you can paste directly into your terminal.
"""

import hashlib
import hmac
import json
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

secret = os.getenv("RAZORPAY_WEBHOOK_SECRET")
if not secret:
    print("Error: RAZORPAY_WEBHOOK_SECRET not set in .env")
    sys.exit(1)

body_dict = {
    "entity": "event",
    "event": "payment.failed",
    "payload": {
        "payment": {
            "entity": {
                "id": "pay_test_manual_001",
                "order_id": "order_test_manual_001",
                "amount": 50000,
                "currency": "INR",
                "status": "failed",
                "method": "card",
                "email": "test@example.com",
                "contact": "+919876543210",
                "error_description": "Card declined by bank",
                "created_at": int(time.time()),
            }
        }
    },
}

# Compact JSON — whitespace matters for signature verification
body_str = json.dumps(body_dict, separators=(",", ":"), ensure_ascii=False)
body_bytes = body_str.encode("utf-8")

sig = hmac.new(
    key=secret.encode("utf-8"),
    msg=body_bytes,
    digestmod=hashlib.sha256,
).hexdigest()

print("=== Signature ===")
print(sig)
print()
print("=== Curl command ===")
print(
    f"curl -X POST http://localhost:8000/webhook/payment-failed \\\n"
    f'  -H "Content-Type: application/json" \\\n'
    f'  -H "X-Razorpay-Signature: {sig}" \\\n'
    f"  -d '{body_str}'"
)
