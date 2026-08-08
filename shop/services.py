import base64
import logging

import requests
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.mail.backends.console import EmailBackend
from django.core.mail.message import EmailMessage
from django.utils.html import escape

logger = logging.getLogger(__name__)

OTP_VALID_MINUTES = getattr(settings, 'OTP_VALID_MINUTES', 5)

_LOGO_B64_CACHE = None


def _kavibazaar_logo_url():
    """Absolute public HTTPS URL to the KaviBazaar logo (served by WhiteNoise).

    Gmail does not render base64 data URIs in images, so production emails use
    the live Railway static URL derived from SITE_DOMAIN / RAILWAY_PUBLIC_DOMAIN.
    """
    domain = (getattr(settings, 'SITE_DOMAIN', '') or '').strip().rstrip('/')
    if not domain:
        return None
    return 'https://%s/static/shop/kavibazaar_logo.png' % domain


def _kavibazaar_logo_data_uri():
    """Base64 data URI fallback only for local dev (no public domain)."""
    global _LOGO_B64_CACHE
    if _LOGO_B64_CACHE is None:
        try:
            path = finders.find('shop/kavibazaar_logo.png')
            if path:
                with open(path, 'rb') as fh:
                    _LOGO_B64_CACHE = base64.b64encode(fh.read()).decode('ascii')
            else:
                _LOGO_B64_CACHE = ''
        except Exception:
            _LOGO_B64_CACHE = ''
    if _LOGO_B64_CACHE:
        return 'data:image/png;base64,' + _LOGO_B64_CACHE
    return None


def _build_otp_html(otp):
    code = escape(str(otp))
    logo_uri = _kavibazaar_logo_url() or _kavibazaar_logo_data_uri()
    if logo_uri:
        brand_block = (
            '<img src="%s" alt="KaviBazaar" width="200" '
            'style="display:block; margin:0 auto; width:200px; max-width:75%%; height:auto; '
            'border:0; outline:none; text-decoration:none;" />'
        ) % logo_uri
    else:
        brand_block = (
            '<div style="font-family:Arial, Helvetica, sans-serif; font-size:22px; '
            'font-weight:700; color:#0b1220; text-align:center;">KaviBazaar</div>'
        )
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="background-color:#f7f4ee;">'
        '<tr><td align="center" style="padding:32px 16px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="max-width:520px; background:#ffffff; border:1px solid #e8e2d5; border-radius:14px;">'
        '<tr><td height="4" style="height:4px; background:#c9a24b; border-radius:14px 14px 0 0; '
        'font-size:0; line-height:0;">&nbsp;</td></tr>'
        '<tr><td align="center" style="padding:30px 24px 6px 24px;">' + brand_block + '</td></tr>'
        '<tr><td align="center" style="padding:16px 24px 22px 24px; border-bottom:1px solid #f0e9db;">'
        '<p style="font-family:Arial, Helvetica, sans-serif; font-size:15px; color:#374151; '
        'line-height:1.6; margin:0; text-align:center;">Your verification code is:</p>'
        '</td></tr>'
        '<tr><td align="center" style="padding:26px 24px 8px 24px;">'
        '<div style="font-family:Arial, Helvetica, sans-serif; display:inline-block; '
        'font-size:32px; font-weight:700; letter-spacing:10px; color:#1c1300; '
        'background:#faf5e7; border:1px solid #e8d5a0; border-radius:10px; '
        'padding:14px 22px;">' + code + '</div></td></tr>'
        '<tr><td align="center" style="padding:16px 24px 30px 24px;">'
        '<p style="font-family:Arial, Helvetica, sans-serif; font-size:14px; color:#6b7280; '
        'line-height:1.6; margin:0; text-align:center;">This OTP is valid for a limited time. '
        'Please do not share this OTP with anyone.</p></td></tr>'
        '</table></td></tr></table>'
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


def _send_otp_via_console(email, otp):
    """Local-development only fallback - prints to console, never uses SMTP."""
    try:
        msg = EmailMessage(
            "Your KaviBazaar OTP",
            f"Your OTP is {otp}.\nIt is valid for {OTP_VALID_MINUTES} minutes. Do not share it with anyone.",
            settings.EMAIL_HOST_USER or 'no-reply@kavibazaar.local',
            [email],
        )
        connection = EmailBackend(fail_silently=False)
        return connection.send_messages([msg]) == 1
    except Exception as e:
        logger.error("OTP email could not be printed to console for %s: %s", email, e)
        return False


def send_otp_email(email, otp, purpose="login"):
    # OTP emails use ONLY the Brevo REST API (Railway blocks outbound SMTP).
    if settings.BREVO_API_KEY:
        return _send_via_brevo(settings.BREVO_API_KEY, email, otp)
    if not settings.DEBUG:
        logger.error("OTP email was NOT sent: Brevo is not configured in production.")
        return False
    logger.warning("Brevo not configured; printing OTP email to console (local dev only).")
    return _send_otp_via_console(email, otp)
