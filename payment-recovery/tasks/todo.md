# Failed Payment Recovery — Task Tracker

## Status: In Progress

### Completed
- [x] Project scaffold (directories, .gitignore)
- [x] requirements.txt
- [x] .env.example
- [x] config.py
- [x] verify.py (HMAC-SHA256 signature verification)
- [x] razorpay_client.py (async fresh payment link generation)
- [x] actions/sms.py (Twilio SMS)
- [x] actions/email.py (Gmail SMTP)
- [x] actions/slack.py (Slack Block Kit)
- [x] main.py (FastAPI webhook endpoint, asyncio.gather fan-out)

### Remaining
- [ ] MCP configuration (Twilio, Gmail, Slack)
- [ ] Demo scenario script (simulate a realistic failed payment)
- [ ] Fill in .env with real credentials and test end-to-end

## Test Checklist
- [ ] Valid webhook → 200, SMS/email/Slack all fire
- [ ] Invalid signature → 400
- [ ] Missing phone → SMS skipped, email + Slack still fire
- [ ] Missing email → email skipped, SMS + Slack still fire
- [ ] Razorpay link gen fails → fallback URL used, no crash
