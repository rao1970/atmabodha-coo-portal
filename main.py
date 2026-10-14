import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import razorpay

# Load environment variables
load_dotenv()

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "WuppuluriSecretKey2026")

# Direct authenticated SMTP credentials
SENDER_EMAIL = "raomurthy1@gmail.com"
SENDER_PASSWORD = "pcjlpskoviuabayg"

app = FastAPI(title="Wuppuluri Studios Payment Fulfillment")

# Initialize Razorpay Client
client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


def send_fulfillment_email(recipient_email: str):
    """Sends fulfillment email containing the Adi Shankaracharya - Atma Bodha package via direct SSL on port 465."""
    subject = (
        "Your Download: Adi Shankaracharya - Atma Bodha Audio & Study Guide"
    )

    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #b33939;">Thank you for your purchase from Srinivas Rao Wuppuluri Studios!</h2>
        <p>Your payment for <strong>Adi Shankaracharya - Atma Bodha Audio & Study Guide</strong> has been successfully confirmed.</p>
        
        <p>Access your complete audio files, synchronized verses, and study materials below:</p>
        
        <div style="margin: 25px 0;">
          <a href="https://drive.google.com/open?id=1pku6JAj9bmTBddsedXjA_yf7kC_dbmK6" 
             style="background-color: #27ae60; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; font-weight: bold; display: inline-block;">
             Download Study Guide & Audio
          </a>
        </div>
        
        <p>If you encounter any issues downloading your study files, reply directly to this email for support.</p>
        <br>
        <p>Warm regards,<br><strong>Srinivas Rao Wuppuluri Studios</strong></p>
      </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = recipient_email
    msg.attach(MIMEText(html_content, "html"))

    # Direct SSL connection to bypass ISP blocks on port 587
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, recipient_email, msg.as_string())


@app.post("/create-order")
async def create_order():
    """Generates a test payment link for Atma Bodha Audio & Study Guide."""
    try:
        payment_link = client.payment_link.create(
            {
                "amount": 29900,  # ₹299.00 in paise
                "currency": "INR",
                "accept_partial": False,
                "description": "Purchase: Adi Shankaracharya - Atma Bodha Audio & Study Guide",
                "customer": {
                    "name": "Srinivas Rao",
                    "email": "raomurthy1@gmail.com",
                    "contact": "+919826178093",
                },
                "notify": {"sms": False, "email": True},
                "reminder_enable": False,
            }
        )
        return {
            "status": "success",
            "payment_link_id": payment_link.get("id"),
            "payment_url": payment_link.get("short_url"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/razorpay-webhook")
async def razorpay_webhook(request: Request):
    """Listens for Razorpay webhook events, validates signature, and dispatches materials."""
    body_bytes = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")

    # 1. Verify Webhook Signature
    if not signature:
        raise HTTPException(
            status_code=400, detail="Missing X-Razorpay-Signature"
        )

    try:
        client.utility.verify_webhook_signature(
            body_bytes.decode("utf-8"), signature, WEBHOOK_SECRET
        )
    except Exception as e:
        print(f"[SECURITY] Webhook signature verification failed: {e}")
        return JSONResponse(
            status_code=400,
            content={"status": "failed", "reason": "invalid_signature"},
        )

    data: Dict[str, Any] = await request.json()
    event = data.get("event")
    print(f"[INFO] Webhook Event Received: {event}")

    # 2. Filter for Payment Success Events
    if event in ["payment_link.paid", "payment.captured"]:
        payload = data.get("payload", {})
        customer_email = None

        # Priority 1: Check Payment Link customer payload
        if "payment_link" in payload:
            customer_email = (
                payload.get("payment_link", {})
                .get("entity", {})
                .get("customer", {})
                .get("email")
            )

        # Priority 2: Check Payment entity (ignore placeholder void@razorpay.com)
        if not customer_email or "void@razorpay.com" in customer_email:
            payment_email = (
                payload.get("payment", {}).get("entity", {}).get("email")
            )
            if payment_email and "void@razorpay.com" not in payment_email:
                customer_email = payment_email

        # Priority 3: Fallback default recipient for sandbox test runs
        if not customer_email or "void@razorpay.com" in customer_email:
            customer_email = "raomurthy1@gmail.com"

        # 3. Deliver Fulfillment Email via direct SSL
        try:
            send_fulfillment_email(customer_email)
            print(f"[SUCCESS] Delivery email sent to {customer_email}")
        except Exception as err:
            print(f"[ERROR] Failed sending delivery email: {err}")

    return {"status": "ok"}