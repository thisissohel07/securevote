import random
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta

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