import random
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
import os
import requests

def send_email_otp(smtp_host, smtp_port, smtp_user, smtp_pass,
                   from_email, to_email, otp, purpose):

    provider = os.getenv("OTP_PROVIDER", "smtp").lower()

    subject = f"SecureVote OTP ({purpose})"
    body = f"""
Hello,

Your SecureVote OTP for {purpose} is:

{otp}

This OTP will expire in 5 minutes.

SecureVote Team
"""

    # ✅ RESEND METHOD (Works on free hosting)
    if provider == "resend":
        api_key = os.getenv("RESEND_API_KEY")
        if not api_key:
            raise Exception("RESEND_API_KEY not set")

        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "from": from_email or "onboarding@resend.dev",
                "to": [to_email],
                "subject": subject,
                "text": body
            }
        )

        if response.status_code >= 400:
            raise Exception(f"Resend Error: {response.text}")

        return

    # ❌ SMTP fallback (local only)
    import smtplib
    from email.mime.text import MIMEText

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email

    with smtplib.SMTP(smtp_host, int(smtp_port)) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_email, [to_email], msg.as_string())
def generate_otp() -> str:
    return f"{random.randint(100000, 999999)}"

def otp_expiry(minutes=5) -> str:
    return (datetime.utcnow() + timedelta(minutes=minutes)).isoformat()

def utc_now() -> str:
    return datetime.utcnow().isoformat()

def send_email_otp(host, port, user, password, from_email, to_email, code, purpose):
    subject = f"SecureVote OTP for {purpose.upper()}"
    body = f"Your SecureVote OTP is: {code}\n\nThis OTP is valid for 5 minutes.\n\nIf you did not request it, ignore this email."

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email

    server = smtplib.SMTP(host, int(port))
    server.starttls()
    server.login(user, password)
    server.sendmail(from_email, [to_email], msg.as_string())
    server.quit()