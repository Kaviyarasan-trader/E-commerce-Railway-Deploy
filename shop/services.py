import logging
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

OTP_VALID_MINUTES = getattr(settings, 'OTP_VALID_MINUTES', 5)


def send_otp_email(email, otp, purpose="login"):
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
