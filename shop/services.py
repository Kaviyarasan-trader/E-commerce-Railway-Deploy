import logging
import requests
from django.conf import settings
from django.core.mail import send_mail
from django.utils.html import escape

logger = logging.getLogger(__name__)

OTP_VALID_MINUTES = getattr(settings, 'OTP_VALID_MINUTES', 5)


def _build_otp_html(otp):
    code = escape(str(otp))
    return (
        '<div style="font-family:Arial, Helvetica, sans-serif; max-width:520px; '
        'margin:0 auto; padding:32px; background:#ffffff; border-radius:12px; '
        'border:1px solid #e5e7eb;">'
        '<div style="font-size:22px; font-weight:700; color:#0b1220; margin-bottom:20px;">'
        'KaviBazaar</div>'
        '<p style="font-size:15px; color:#374151; line-height:1.6; margin:0 0 16px;">'
        'Your verification code is:</p>'
        '<div style="font-size:30px; font-weight:700; letter-spacing:8px; color:#0b1220; '
        'padding:14px 18px; background:#f3f4f6; border-radius:8px; display:inline-block;">'
        + code + '</div>'
        '<p style="font-size:14px; color:#6b7280; line-height:1.6; margin:18px 0 0;">'
        'This OTP is valid for a limited time. Please do not share this OTP with anyone.</p>'
        '</div>'
    )


def _send_via_brevo(api_key, email, otp):
    from_email = (
        settings.BREVO_FROM_EMAIL
        or settings.EMAIL_HOST_USER
        or 'no-reply@kavibazaar.local'
    )
    from_name = settings.BREVO_FROM_NAME or 'KaviBazaar'
    try:
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "accept": "application/json",
                "api-key": api_key,
                "content-type": "application/json",
            },
            json={
                "sender": {"name": from_name, "email": from_email},
                "to": [{"email": email}],
                "subject": "Your KaviBazaar OTP",
                "htmlContent": _build_otp_html(otp),
            },
            timeout=15,
        )
        if 200 <= resp.status_code < 300:
            logger.info("Brevo OTP email accepted for %s (status %s)", email, resp.status_code)
            return True
        error_detail = ''
        try:
            message = (resp.json() or {}).get('message')
            if message:
                error_detail = str(message)
        except Exception:
            error_detail = ''
        if error_detail:
            logger.error(
                "Brevo OTP email rejected for %s (status %s): %s",
                email, resp.status_code, error_detail,
            )
        else:
            logger.error("Brevo OTP email rejected for %s (status %s)", email, resp.status_code)
        return False
    except Exception as e:
        logger.error("Brevo OTP email could not be sent to %s: %s", email, e)
        return False


def send_otp_email(email, otp, purpose="login"):
    if settings.BREVO_API_KEY:
        return _send_via_brevo(settings.BREVO_API_KEY, email, otp)
    # Gmail SMTP is only for local development. Production must use Brevo
    # (Railway blocks outbound SMTP), so never fall back to SMTP when DEBUG=False.
    if not settings.DEBUG:
        logger.error("OTP email was NOT sent: Brevo is not configured in production.")
        return False
    logger.warning(
        "Brevo not configured; falling back to EMAIL_BACKEND=%s (local dev only).",
        settings.EMAIL_BACKEND,
    )
    try:
        send_mail(
            "Your KaviBazaar OTP",
            f"Your OTP is {otp}.\nIt is valid for {OTP_VALID_MINUTES} minutes. Do not share it with anyone.",
            settings.EMAIL_HOST_USER or 'no-reply@kavibazaar.local',
            [email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        logger.error("OTP email could not be sent to %s: %s", email, e)
        return False
