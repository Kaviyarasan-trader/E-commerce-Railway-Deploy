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
            '<img src="%s" alt="KaviBazaar" width="180" '
            'style="display:block; margin:0 auto; width:180px; max-width:70%%; height:auto; '
            'border:0; outline:none; text-decoration:none;" />'
        ) % logo_uri
    else:
        brand_block = (
            '<div style="font-family:Arial, Helvetica, sans-serif; font-size:24px; '
            'font-weight:700; letter-spacing:2px; color:#f3ce6a; text-align:center;">KAVIBAZAAR</div>'
        )
    return (
        '<!DOCTYPE html><html lang="en"><head>'
        '<meta charset="utf-8">'
        '<meta name="color-scheme" content="dark">'
        '<meta name="supported-color-schemes" content="dark">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        '<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">'
        '<title>Your KaviBazaar OTP</title>'
        '<style>'
        '@media (prefers-color-scheme: dark) { .kb-body, .kb-card { background-color:#0d0d0f !important; } }'
        '[data-ogsc] .kb-body, [data-ogsc] .kb-card { background-color:#0d0d0f !important; }'
        '</style>'
        '</head>'
        '<body class="kb-body" style="margin:0; padding:0; background-color:#0d0d0f; '
        '-webkit-text-size-adjust:100%; -ms-text-size-adjust:100%;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'bgcolor="#0d0d0f" style="width:100%; background-color:#0d0d0f;">'
        '<tr><td align="center" style="padding:36px 16px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="max-width:524px; width:100%; background-color:#6f5a24; '
        'background-image:linear-gradient(155deg,#7a5f24 0%,#d9b64a 45%,#f4dc8a 55%,#7a5f24 100%); '
        'border-radius:22px; box-shadow:0 14px 44px rgba(0,0,0,0.6);">'
        '<tr><td align="center" style="padding:2px; border-radius:22px;">'
        '<table role="presentation" class="kb-card" width="100%" cellpadding="0" cellspacing="0" '
        'border="0" style="max-width:520px; width:100%; background-color:#151519; border-radius:20px;">'
        '<tr><td align="center" style="padding:38px 24px 4px 24px;">' + brand_block + '</td></tr>'
        '<tr><td align="center" style="padding:18px 24px 2px 24px;">'
        '<div style="font-family:Arial, Helvetica, sans-serif; font-size:11px; font-weight:700; '
        'letter-spacing:4px; color:#d4af37; text-align:center;">SECURE VERIFICATION</div>'
        '</td></tr>'
        '<tr><td align="center" style="padding:22px 28px 0 28px;">'
        '<p style="font-family:Arial, Helvetica, sans-serif; font-size:15px; color:#c9c9d2; '
        'line-height:1.6; margin:0; text-align:center;">Your verification code is:</p>'
        '</td></tr>'
        '<tr><td align="center" style="padding:20px 28px 4px 28px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="max-width:390px; width:100%;">'
        '<tr><td align="center" bgcolor="#1e1e24" style="background-color:#1e1e24; '
        'border:1px solid #54411a; border-radius:14px; padding:20px 14px; '
        'box-shadow:inset 0 1px 0 rgba(255,255,255,0.05), 0 6px 20px rgba(0,0,0,0.45);">'
        '<div style="font-family:Arial, Helvetica, sans-serif; font-size:34px; font-weight:700; '
        'letter-spacing:10px; color:#f3ce6a; text-align:center; line-height:1.15;">' + code + '</div>'
        '</td></tr>'
        '</table>'
        '</td></tr>'
        '<tr><td align="center" style="padding:22px 28px 0 28px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        '<td height="1" bgcolor="#2b2b31" style="height:1px; font-size:0; line-height:0; '
        'background-color:#2b2b31;">&nbsp;</td>'
        '</tr></table>'
        '</td></tr>'
        '<tr><td align="center" style="padding:24px 28px 30px 28px;">'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
        '<td align="center" width="40" height="40" bgcolor="#1e1e24" style="width:40px; height:40px; '
        'background-color:#1e1e24; border:1px solid #54411a; border-radius:50%; '
        'text-align:center; vertical-align:middle; line-height:40px;">'
        '<span aria-hidden="true" style="font-size:18px; line-height:40px;">&#128274;</span>'
        '</td>'
        '</tr></table>'
        '<p style="font-family:Arial, Helvetica, sans-serif; font-size:14px; color:#d6d6de; '
        'line-height:1.6; margin:14px 0 0 0; text-align:center; font-weight:600;">'
        'This code expires shortly.</p>'
        '<p style="font-family:Arial, Helvetica, sans-serif; font-size:14px; color:#8f8f99; '
        'line-height:1.6; margin:4px 0 0 0; text-align:center;">'
        'Never share this code with anyone.</p>'
        '</td></tr>'
        '<tr><td align="center" style="padding:0 28px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        '<td height="1" bgcolor="#2b2b31" style="height:1px; font-size:0; line-height:0; '
        'background-color:#2b2b31;">&nbsp;</td>'
        '</tr></table>'
        '</td></tr>'
        '<tr><td align="center" style="padding:20px 28px 30px 28px;">'
        '<p style="font-family:Arial, Helvetica, sans-serif; font-size:12px; color:#8f8f99; '
        'line-height:1.6; margin:0; text-align:center;">&copy; KaviBazaar</p>'
        '<p style="font-family:Arial, Helvetica, sans-serif; font-size:12px; color:#6f6f78; '
        'line-height:1.6; margin:4px 0 0 0; text-align:center;">'
        'This is an automated message. Please do not reply.</p>'
        '</td></tr>'
        '</table>'
        '</td></tr>'
        '</table>'
        '</td></tr>'
        '</table>'
        '</body></html>'
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
