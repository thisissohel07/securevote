import os
import random
import requests
from datetime import datetime, timedelta, timezone


def generate_otp() -> str:
    return f"{random.randint(100000, 999999)}"


def otp_expiry(minutes=5) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def send_email_otp(to_email, code, purpose):
    """
    Sends OTP via Resend API.
    """
    debug_mode = os.getenv("DEBUG_OTP", "false").lower() == "true"
    resend_api_key = os.getenv("RESEND_API_KEY")
    resend_from = os.getenv("RESEND_FROM", "onboarding@resend.dev")

    if not resend_api_key:
        raise Exception("RESEND_API_KEY is not configured.")

    subject = f"SecureVote OTP for {purpose.upper()}"
    body_text = (
        f"Your SecureVote OTP is: {code}\n\n"
        f"This OTP is valid for 5 minutes.\n\n"
        f"If you did not request it, ignore this email."
    )
    body_html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;padding:24px;border:1px solid #e5e7eb;border-radius:12px;">
      <h2 style="color:#1d4ed8;">SecureVote OTP</h2>
      <p style="font-size:16px;">Your OTP code for <strong>{purpose.upper()}</strong> is:</p>
      <div style="font-size:36px;font-weight:bold;letter-spacing:8px;color:#111827;padding:16px 0;">{code}</div>
      <p style="color:#6b7280;font-size:13px;">Valid for 5 minutes. Do not share this code with anyone.</p>
    </div>
    """

    print(f"[OTP] Sending OTP for {purpose} to {to_email}")

    if debug_mode:
        print(f"--- [DEBUG OTP] Email: {to_email}, Code: {code} ---")
        return

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": resend_from,
                "to": [to_email],
                "subject": subject,
                "html": body_html,
                "text": body_text,
            },
            timeout=10,
        )
        if response.status_code in (200, 201):
            print(f"[RESEND] OTP sent successfully to {to_email}")
            return
        else:
            print(f"[RESEND ERROR] Status {response.status_code}: {response.text}")
            raise Exception(f"Resend API error: {response.text}")
    except Exception as e:
        print(f"[RESEND ERROR] {e}")
        raise Exception(f"Email delivery failed: {e}")