import logging
import requests
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

OTP_VALID_MINUTES = getattr(settings, 'OTP_VALID_MINUTES', 5)


def _send_via_sendgrid(api_key, email, otp, purpose):
    try:
        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "personalizations": [
                    {
                        "to": [{"email": email}],
                        "subject": f"KaviBazaar {purpose.title()} OTP",
                    }
                ],
                "from": {"email": settings.EMAIL_HOST_USER or "kavibazaar@gmail.com"},
                "content": [
                    {
                        "type": "text/plain",
                        "value": (
                            f"Your OTP is {otp}.\n"
                            f"It is valid for {OTP_VALID_MINUTES} minutes. Do not share it with anyone."
                        ),
                    }
                ],
            },
            timeout=15,
        )
        if resp.status_code == 202:
            return True
        logger.error("SendGrid OTP email rejected for %s (status %s)", email, resp.status_code)
        return False
    except Exception as e:
        logger.error("SendGrid OTP email could not be sent to %s: %s", email, e)
        return False


def send_otp_email(email, otp, purpose="login"):
    if settings.SENDGRID_API_KEY:
        return _send_via_sendgrid(settings.SENDGRID_API_KEY, email, otp, purpose)
    try:
        send_mail(
            f"KaviBazaar {purpose.title()} OTP",
            f"Your OTP is {otp}.\nIt is valid for {OTP_VALID_MINUTES} minutes. Do not share it with anyone.",
            settings.EMAIL_HOST_USER or 'no-reply@kavibazaar.local',
            [email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        logger.error("OTP email could not be sent to %s: %s", email, e)
        return False
