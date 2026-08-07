import logging
import requests
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

OTP_VALID_MINUTES = getattr(settings, 'OTP_VALID_MINUTES', 5)


def _send_via_sendgrid(api_key, email, otp, purpose):
    from_email = (
        settings.SENDGRID_FROM_EMAIL
        or settings.EMAIL_HOST_USER
        or 'no-reply@kavibazaar.local'
    )
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
                "from": {"email": from_email},
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
            logger.info("SendGrid OTP email accepted for %s (status 202)", email)
            return True
        error_detail = ''
        try:
            errors = (resp.json() or {}).get('errors') or []
            error_detail = '; '.join(
                str(e.get('message', '')) for e in errors
                if isinstance(e, dict) and e.get('message')
            )
        except Exception:
            error_detail = ''
        if error_detail:
            logger.error(
                "SendGrid OTP email rejected for %s (status %s): %s",
                email, resp.status_code, error_detail,
            )
        else:
            logger.error("SendGrid OTP email rejected for %s (status %s)", email, resp.status_code)
        return False
    except Exception as e:
        logger.error("SendGrid OTP email could not be sent to %s: %s", email, e)
        return False


def send_otp_email(email, otp, purpose="login"):
    if settings.SENDGRID_API_KEY:
        return _send_via_sendgrid(settings.SENDGRID_API_KEY, email, otp, purpose)
    # Gmail SMTP is only for local development. Production must use SendGrid
    # (Railway blocks outbound SMTP), so never fall back to SMTP when DEBUG=False.
    if not settings.DEBUG:
        logger.error("OTP email was NOT sent: SendGrid is not configured in production.")
        return False
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
