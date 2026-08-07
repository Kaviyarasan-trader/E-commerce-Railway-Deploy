"""Invoice generation and PDF rendering for KaviBazaar.

`generate_invoice_for_order()` creates the Invoice snapshot the moment an
order becomes successful. The snapshot (line_items JSON + totals) is what the
PDF is rendered from, so the invoice always reflects the exact details at the
time of purchase even if product prices change later.
"""

import io
import logging
import os

from django.conf import settings

from .models import Invoice

logger = logging.getLogger(__name__)

STORE_NAME = "KaviBazaar"
STORE_TAGLINE = "Your trusted shopping destination"
STORE_EMAIL = "kavibazaar@gmail.com"
STORE_PHONE = "+91 63740 00374"

GOLD = '#F9B800'          # bright warm gold (reference 251,184,7)
GOLD_SOFT = '#C99400'     # muted gold for small labels
BG = '#242424'            # invoice body charcoal (reference ~#242424)
BG_HEADER = '#242424'     # header zone (reference has no separate band colour)
BG_FOOTER = '#242424'     # footer band (reference RGB ~58,58,58)
ROW_ALT = '#383838'       # alternating table row (reference RGB ~56-60)
TEXT = '#F2F2F2'          # primary near-white text
TEXT_SUB = '#C9C9C9'      # secondary text
MUTED = '#9A9A9A'         # muted labels
LINE = '#4A4A4A'          # subtle separators
INK_ON_GOLD = '#241C00'   # dark text on gold pills

TERMS_AND_CONDITIONS = (
    "1. This invoice confirms that your payment has been received and the "
    "order is confirmed.<br/>"
    "2. Goods once sold are eligible for exchange or return as per the "
    "store's return policy.<br/>"
    "3. For any support, please quote your order id and contact us at "
    f"{STORE_EMAIL} or {STORE_PHONE}."
)


def _money(value):
    """Format a float as a Rs. amount string."""
    try:
        return f"Rs. {float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return "Rs. 0.00"


def _payment_method_for(order):
    payments = list(order.payments.all())
    for p in payments:
        if (p.payment_gateway or '').upper() == 'COD':
            return 'Cash on Delivery'
    for p in payments:
        if p.status == 'SUCCESS':
            return 'Razorpay'
    if order.razorpay_order_id or order.razorpay_pay_id:
        return 'Razorpay'
    return 'Cash on Delivery'


def _build_invoice_number(order):
    year = order.created_at.year if order.created_at else 2026
    return f"KB-{year}-{order.id:06d}"


def _build_snapshot(order):
    """Snapshot the exact order details at the time of purchase."""
    user = order.user
    customer_name = (user.get_full_name() or user.username).strip() or 'Customer'

    items = []
    subtotal = 0.0
    total_discount = 0.0

    for item in order.items.select_related('product'):
        product = item.product
        qty = item.quantity or 0
        unit_price = float(item.price or 0)
        if qty <= 0:
            qty = 1
        mrp = unit_price
        if product and product.original_price and float(product.original_price) > unit_price:
            mrp = float(product.original_price)
        amount = round(unit_price * qty, 2)
        discount = round((mrp - unit_price) * qty, 2)
        subtotal += mrp * qty
        total_discount += discount
        items.append({
            'name': product.name if product else f"Item #{item.id}",
            'image': product.product_image.url if (product and product.product_image) else '',
            'quantity': qty,
            'unit_price': round(unit_price, 2),
            'mrp': round(mrp, 2),
            'discount': round(discount, 2),
            'amount': round(amount, 2),
        })

    subtotal = round(subtotal, 2)
    total_discount = round(total_discount, 2)
    paid = round(float(order.total_amount or 0), 2)
    delivery_charge = round(max(0.0, paid - (subtotal - total_discount)), 2)

    return {
        'customer_name': customer_name,
        'customer_email': (user.email or '').strip(),
        'customer_phone': (order.phone or '').strip(),
        'delivery_address': (order.address or '').strip(),
        'order_date': order.created_at,
        'payment_method': _payment_method_for(order),
        'payment_status': (order.payment_status or '').strip(),
        'order_status': (order.status or '').strip(),
        'subtotal': subtotal,
        'total_discount': total_discount,
        'delivery_charge': delivery_charge,
        'tax_amount': 0.0,
        'grand_total': paid,
        'line_items': items,
    }


def generate_invoice_for_order(order):
    """Create (or return) the Invoice snapshot for a successful order.

    Idempotent: an order has at most one invoice. Never raises — callers wrap
    this in the checkout flow and must not be broken by invoice errors.
    """
    if not order or not order.id:
        return None
    existing = Invoice.objects.filter(order=order).first()
    if existing:
        return existing

    data = _build_snapshot(order)
    try:
        invoice = Invoice.objects.create(
            order=order,
            invoice_number=_build_invoice_number(order),
            customer_name=data['customer_name'],
            customer_email=data['customer_email'],
            customer_phone=data['customer_phone'],
            delivery_address=data['delivery_address'],
            order_date=data['order_date'],
            payment_method=data['payment_method'],
            payment_status=data['payment_status'],
            order_status=data['order_status'],
            subtotal=data['subtotal'],
            total_discount=data['total_discount'],
            delivery_charge=data['delivery_charge'],
            tax_amount=data['tax_amount'],
            grand_total=data['grand_total'],
            line_items=data['line_items'],
        )
        return invoice
    except Exception:
        logger.exception("Invoice creation failed for order %s", order.id)
        return None


# ── PDF rendering ─────────────────────────────────────────────────────

from PIL import Image as PILImage

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

PAGE_W, PAGE_H = A4

_DOC_LEFT_MARGIN = 12.5 * mm
_DOC_RIGHT_MARGIN = 12.5 * mm
_DOC_TOP_MARGIN = 8 * mm

_HEADER_HEIGHT = 205
_FOOTER_HEIGHT = 100

_DOC_BOTTOM_MARGIN = _FOOTER_HEIGHT + 4 * mm

# typography: Segoe UI for body, Bahnschrift for display headings (modern
# premium sans-serif), fall back to Helvetica when unavailable
_FONT = 'Helvetica'
_FONT_B = 'Helvetica-Bold'
_FONT_T = 'Helvetica-Bold'
try:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    _windir = os.environ.get('WINDIR') or r'C:\Windows'
    _segoe = os.path.join(_windir, 'Fonts', 'segoeui.ttf')
    _segoe_b = os.path.join(_windir, 'Fonts', 'segoeuib.ttf')
    _bahn = os.path.join(_windir, 'Fonts', 'bahnschrift.ttf')
    if os.path.exists(_segoe):
        pdfmetrics.registerFont(TTFont('KaviSegoe', _segoe))
        _FONT = 'KaviSegoe'
    if os.path.exists(_segoe_b):
        pdfmetrics.registerFont(TTFont('KaviSegoeB', _segoe_b))
        _FONT_B = 'KaviSegoeB'
    if os.path.exists(_bahn):
        pdfmetrics.registerFont(TTFont('KaviBahn', _bahn))
        _FONT_T = 'KaviBahn'
except Exception:
    pass

# product table column widths (No | Item | Price | Qty | Total), 185mm total
_TBL_COLS = [11 * mm, 72 * mm, 36 * mm, 16 * mm, 50 * mm]
_TBL_PAD = 8

# Shared two-column layout used by the info block and the terms/summary
# block below the items table. A real gap column (not 0pt) is required so
# the left column's wrapped text never touches the right column's content.
_COL_GAP = 16
_COL_LEFT_W = 288
_COL_RIGHT_W = 220.4


def _logo_data():
    """Load the official KaviBazaar logo as RGBA PNG bytes (alpha preserved).

    Returns ``(png_bytes, px_width, px_height)`` or ``None``. The uploaded
    logo is shipped as an opaque white square, so the derived
    ``official_logo_transparent.png`` (white background removed, artwork
    untouched) is preferred so it blends into the dark header.
    """
    for name in ('official_logo_transparent.png', 'official_logo.png',
                 'kavibazaar_badge.png', 'favicon.png'):
        candidate = os.path.join(str(settings.STATIC_ROOT), 'shop', name)
        if not os.path.exists(candidate):
            candidate = os.path.join(str(settings.BASE_DIR), 'static', 'shop', name)
        if not os.path.exists(candidate):
            continue
        try:
            img = PILImage.open(candidate)
            img.load()
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            return buf.getvalue(), img.size[0], img.size[1]
        except Exception:
            continue
    return None


def _styles():
    s = {}

    def P(name, font, size, leading, color, align=TA_LEFT):
        return ParagraphStyle(name, fontName=font, fontSize=size, leading=leading,
                              textColor=colors.HexColor(color), alignment=align)

    s['sec_h'] = P('sec_h', _FONT_B, 9.5, 12, GOLD)
    s['lbl'] = P('lbl', _FONT_B, 6.5, 9, GOLD_SOFT)
    s['val'] = P('val', _FONT_B, 16, 20, TEXT)
    s['val_sm'] = P('val_sm', _FONT, 9.5, 13, TEXT)
    s['pair'] = P('pair', _FONT_B, 8, 14, GOLD_SOFT)
    s['addr'] = P('addr', _FONT, 9.5, 13, TEXT_SUB)
    s['name'] = P('name', _FONT_B, 9.5, 12, TEXT)
    s['th'] = P('th', _FONT_B, 8.5, 11, INK_ON_GOLD, align=TA_CENTER)
    s['thl'] = P('thl', _FONT_B, 8.5, 11, INK_ON_GOLD, align=TA_LEFT)
    s['thr'] = P('thr', _FONT_B, 8.5, 11, INK_ON_GOLD, align=TA_RIGHT)
    s['c'] = P('c', _FONT, 9, 12, TEXT, align=TA_CENTER)
    s['cr'] = P('cr', _FONT, 9, 12, TEXT, align=TA_RIGHT)
    s['sum_l'] = P('sum_l', _FONT, 8.5, 13, TEXT_SUB)
    s['sum_v'] = P('sum_v', _FONT_B, 9.5, 13, TEXT, align=TA_RIGHT)
    s['sum_neg'] = P('sum_neg', _FONT_B, 9.5, 13, GOLD, align=TA_RIGHT)
    s['grand_l'] = P('grand_l', _FONT_B, 11, 14, INK_ON_GOLD)
    s['grand_v'] = P('grand_v', _FONT_B, 15, 18, INK_ON_GOLD, align=TA_RIGHT)
    s['tc'] = P('tc', _FONT, 8, 12, TEXT_SUB)
    s['sign'] = P('sign', _FONT, 7.5, 10, MUTED, align=TA_RIGHT)
    s['sign_name'] = P('sign_name', _FONT_B, 9, 12, TEXT, align=TA_RIGHT)
    return s


class _Pill(Flowable):
    """Rounded gold bar with horizontally laid out text cells."""

    def __init__(self, width, height, fill, cells, radius=None):
        Flowable.__init__(self)
        self.width = width
        self.height = height
        self.fill = fill
        self.cells = cells  # list of (x, ParagraphStyle, text)
        self.radius = radius if radius is not None else min(width, height) / 2.0

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(colors.HexColor(self.fill))
        c.roundRect(0, 0, self.width, self.height, self.radius, stroke=0, fill=1)
        for x, style, text in self.cells:
            c.setFont(style.fontName, style.fontSize)
            c.setFillColor(style.textColor)
            baseline = self.height / 2.0 - style.fontSize * 0.30
            a = style.alignment
            if a == TA_RIGHT:
                c.drawRightString(x, baseline, text)
            elif a == TA_CENTER:
                c.drawCentredString(x, baseline, text)
            else:
                c.drawString(x, baseline, text)


class _HeaderBand(Flowable):
    """Reference-style dark header: logo + brand + tagline, and a large gold
    INVOICE title with metadata."""

    def __init__(self, width, height, logo_reader, logo_px_w, logo_px_h,
                 brand, tagline, invoice_number, issued_date):
        Flowable.__init__(self)
        self.width = width
        self.height = height
        self._logo = logo_reader
        self._logo_px_w = logo_px_w
        self._logo_px_h = logo_px_h
        self._brand = brand
        self._tagline = tagline
        self._number = invoice_number
        self._date = issued_date

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        c = self.canv
        h = self.height

        # full-bleed dark header zone
        left_bleed = _DOC_LEFT_MARGIN
        right_bleed = _DOC_RIGHT_MARGIN
        top_bleed = _DOC_TOP_MARGIN
        bleed_x = -left_bleed
        bleed_w = self.width + left_bleed + right_bleed
        c.setFillColor(colors.HexColor(BG_HEADER))
        c.rect(bleed_x, 0, bleed_w, h + top_bleed, stroke=0, fill=1)

        # logo top-left
        logo_h = 58
        if self._logo is not None:
            logo_w = logo_h
            c.drawImage(self._logo, 0, h - 36 - logo_h,
                        width=logo_w, height=logo_h, mask=None)

        # brand + tagline lower-left, under the logo block (reference position)
        text_x = 2
        c.setFont(_FONT_T, 20)
        c.setFillColor(colors.HexColor(TEXT))
        c.drawString(text_x, h - 136, self._brand)
        if self._tagline:
            c.setFont(_FONT_B, 7.5)
            c.setFillColor(colors.HexColor(MUTED))
            c.drawString(text_x, h - 151, self._tagline.upper())

        # gold INVOICE word, mid-right (reference position ~PDF y 104-121)
        right_x = self.width
        c.setFont(_FONT_T, 24)
        c.setFillColor(colors.HexColor(GOLD))
        c.drawRightString(right_x, h - 99, 'INVOICE')

        # invoice metadata right-aligned below the word
        c.setFont(_FONT_B, 7.5)
        c.setFillColor(colors.HexColor(GOLD_SOFT))
        c.drawRightString(right_x, h - 121, 'INVOICE NO.')
        c.setFont(_FONT_B, 10.5)
        c.setFillColor(colors.HexColor(TEXT))
        c.drawRightString(right_x, h - 133, self._number)

        c.setFont(_FONT_B, 7.5)
        c.setFillColor(colors.HexColor(GOLD_SOFT))
        c.drawRightString(right_x, h - 146, 'INVOICE DATE')
        c.setFont(_FONT_B, 10.5)
        c.setFillColor(colors.HexColor(TEXT))
        c.drawRightString(right_x, h - 158, self._date)


def _render_header(st, story, invoice):
    """Full-width dark header: logo + brand left, INVOICE + metadata right."""
    reader = None
    pw = ph = 0
    data = _logo_data()
    if data:
        reader = ImageReader(io.BytesIO(data[0]))
        pw, ph = data[1], data[2]
    issued = invoice.issued_date.strftime('%d %b %Y') if invoice.issued_date else '—'
    band = _HeaderBand(
        width=PAGE_W - _DOC_LEFT_MARGIN - _DOC_RIGHT_MARGIN,
        height=_HEADER_HEIGHT,
        logo_reader=reader,
        logo_px_w=pw,
        logo_px_h=ph,
        brand=STORE_NAME,
        tagline=STORE_TAGLINE,
        invoice_number=invoice.invoice_number,
        issued_date=issued,
    )
    story.append(band)
    story.append(Spacer(1, 8))


def _text_block(st, inner, width):
    tbl = Table([[inner]], colWidths=[width])
    tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return tbl


def _render_info(st, story, invoice):
    """Open text info area: INVOICE TO left, PAYMENT + ORDER DETAILS right.
    No cards, no borders — matching the reference's clean layout."""
    date_fmt = invoice.order_date.strftime('%d %b %Y, %I:%M %p') if invoice.order_date else '—'
    addr_lines = [line.strip() for line in invoice.delivery_address.splitlines() if line.strip()]
    addr_text = '<br/>'.join(addr_lines) if addr_lines else '—'

    left_inner = [
        Paragraph('INVOICE TO', st['sec_h']),
        Spacer(1, 7),
        Paragraph(invoice.customer_name or '—', st['val']),
        Spacer(1, 12),
        Paragraph(f"PHONE&nbsp;&nbsp;&nbsp;&nbsp;<font color=\"{TEXT}\">{invoice.customer_phone or '—'}</font>", st['pair']),
        Spacer(1, 6),
        Paragraph(f"EMAIL&nbsp;&nbsp;&nbsp;&nbsp;<font color=\"{TEXT}\">{invoice.customer_email or '—'}</font>", st['pair']),
        Spacer(1, 10),
        Paragraph('DELIVERY ADDRESS', st['lbl']),
        Spacer(1, 2),
        Paragraph(addr_text, st['addr']),
    ]
    left = _text_block(st, left_inner, _COL_LEFT_W)
    right_inner = [
        Paragraph('PAYMENT METHOD', st['sec_h']),
        Spacer(1, 7),
        Paragraph(f"METHOD&nbsp;&nbsp;&nbsp;&nbsp;<font color=\"{TEXT}\">{invoice.payment_method or '—'}</font>", st['pair']),
        Spacer(1, 6),
        Paragraph(f"STATUS&nbsp;&nbsp;&nbsp;&nbsp;<font color=\"{TEXT}\">{invoice.payment_status or '—'}</font>", st['pair']),
        Spacer(1, 16),
        Paragraph('ORDER DETAILS', st['sec_h']),
        Spacer(1, 7),
        Paragraph(f"ORDER ID&nbsp;&nbsp;&nbsp;&nbsp;<font color=\"{TEXT}\">#{invoice.order.id}</font>", st['pair']),
        Spacer(1, 6),
        Paragraph(f"ORDER DATE&nbsp;&nbsp;&nbsp;&nbsp;<font color=\"{TEXT}\">{date_fmt}</font>", st['pair']),
        Spacer(1, 6),
        Paragraph(f"STATUS&nbsp;&nbsp;&nbsp;&nbsp;<font color=\"{TEXT}\">{invoice.order_status or '—'}</font>", st['pair']),
    ]
    right = _text_block(st, right_inner, _COL_RIGHT_W)

    row = Table([[left, '', right]], colWidths=[_COL_LEFT_W, _COL_GAP, _COL_RIGHT_W])
    row.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(row)
    story.append(Spacer(1, 22))


def _render_items(st, story, invoice):
    """Full-width table: gold rounded header pill + alternating dark rows."""
    widths = _TBL_COLS
    pad = _TBL_PAD

    def col_cells():
        acc = 0.0
        out = []
        for i, w in enumerate(widths):
            if i == 0:
                out.append((acc + w / 2.0, st['th'], 'NO.'))
            elif i == 1:
                out.append((acc + pad, st['thl'], 'ITEM / PRODUCT DESCRIPTION'))
            elif i == 2:
                out.append((acc + w - pad, st['thr'], 'PRICE'))
            elif i == 3:
                out.append((acc + w / 2.0, st['th'], 'QTY'))
            else:
                out.append((acc + w - pad, st['thr'], 'TOTAL'))
            acc += w
        return out

    pill = _Pill(sum(widths), 30, GOLD, col_cells())

    rows = [[pill, '', '', '', '']]
    spans = [('SPAN', (0, 0), (4, 0))]
    for i, item in enumerate(invoice.line_items, 1):
        name = (item.get('name') or '').strip()
        unit = float(item.get('unit_price') or 0)
        mrp = float(item.get('mrp') or 0)
        disc = float(item.get('discount') or 0)
        qty = item.get('quantity') or 0
        amount = float(item.get('amount') or 0)

        sub = []
        if mrp > unit:
            sub.append(f"<strike>{_money(mrp)}</strike>")
        if disc > 0:
            sub.append(f'<font color="{GOLD}"><b>-{_money(disc)}</b></font>')
        if sub:
            desc = Paragraph(
                f"<b>{name}</b><br/><font color='{MUTED}' size='6.5'>{'&nbsp;&nbsp;&middot;&nbsp;&nbsp;'.join(sub)}</font>",
                st['name'],
            )
        else:
            desc = Paragraph(f"<b>{name}</b>", st['name'])

        rows.append([
            Paragraph(str(i), st['c']),
            desc,
            Paragraph(_money(unit), st['cr']),
            Paragraph(str(qty), st['c']),
            Paragraph(_money(amount), st['cr']),
        ])

    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), pad),
        ('RIGHTPADDING', (0, 0), (-1, -1), pad),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [BG, ROW_ALT]),
        ('LEFTPADDING', (0, 0), (4, 0), 0),
        ('RIGHTPADDING', (0, 0), (4, 0), 0),
        ('TOPPADDING', (0, 0), (4, 0), 0),
        ('BOTTOMPADDING', (0, 0), (4, 0), 0),
    ] + spans))
    story.append(table)
    story.append(Spacer(1, 24))


def _render_bottom(st, story, invoice):
    """TERMS & CONDITIONS left; PRICE SUMMARY + gold Grand Total pill right."""
    mrp_total = round(float(invoice.subtotal or 0), 2)
    discount = round(float(invoice.total_discount or 0), 2)
    delivery = round(float(invoice.delivery_charge or 0), 2)
    tax = round(float(invoice.tax_amount or 0), 2)
    grand = round(float(invoice.grand_total or 0), 2)

    left_inner = [
        Paragraph('TERMS & CONDITIONS', st['sec_h']),
        Spacer(1, 6),
        Paragraph(TERMS_AND_CONDITIONS, st['tc']),
    ]
    left = _text_block(st, left_inner, _COL_LEFT_W)

    sum_rows = [
        [Paragraph('Subtotal', st['sum_l']), Paragraph(_money(mrp_total), st['sum_v'])],
        [Paragraph('Discount', st['sum_l']),
         Paragraph(("-" + _money(discount)) if discount > 0 else "Rs. 0.00", st['sum_neg'])],
        [Paragraph('Tax / GST', st['sum_l']), Paragraph(_money(tax), st['sum_v'])],
        [Paragraph('Shipping', st['sum_l']), Paragraph(_money(delivery), st['sum_v'])],
    ]
    sum_tbl = Table(sum_rows, colWidths=[_COL_RIGHT_W - 120, 120])
    sum_tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor(LINE)),
    ]))

    grand_pill = _Pill(_COL_RIGHT_W, 30, GOLD, [
        (16, st['grand_l'], 'GRAND TOTAL'),
        (_COL_RIGHT_W - 16, st['grand_v'], _money(grand)),
    ])

    sig_line = Table([['']], colWidths=[120])
    sig_line.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, 0), 0.7, colors.HexColor(GOLD_SOFT)),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    sig_wrap = Table([[sig_line]], colWidths=[_COL_RIGHT_W])
    sig_wrap.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    right_inner = [
        Paragraph('PRICE SUMMARY', st['sec_h']),
        Spacer(1, 6),
        sum_tbl,
        Spacer(1, 10),
        grand_pill,
        Spacer(1, 14),
        sig_wrap,
        Paragraph('Kaviyarasan R', st['sign_name']),
        Paragraph('Authorised Signatory', st['sign']),
    ]
    right = _text_block(st, right_inner, _COL_RIGHT_W)

    row = Table([[left, '', right]], colWidths=[_COL_LEFT_W, _COL_GAP, _COL_RIGHT_W])
    row.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(row)


def _draw_footer_band(canv):
    """Full-bleed dark footer band: thank-you + contact + a prominent gold
    slanted shape bottom-right (flush with the page edges, like the
    reference)."""
    band_h = _FOOTER_HEIGHT
    canv.saveState()
    canv.setFillColor(colors.HexColor(BG_FOOTER))
    canv.rect(0, 0, PAGE_W, band_h, stroke=0, fill=1)

    cx = PAGE_W / 2.0
    canv.setFont(_FONT_B, 11.5)
    canv.setFillColor(colors.HexColor(GOLD))
    canv.drawCentredString(cx, band_h - 26, 'Thank you for your business')
    canv.setFont(_FONT, 8)
    canv.setFillColor(colors.HexColor(TEXT_SUB))
    canv.drawCentredString(cx, band_h - 44, f'{STORE_EMAIL}   |   {STORE_PHONE}')
    canv.setFont(_FONT, 6.5)
    canv.setFillColor(colors.HexColor(MUTED))
    canv.drawCentredString(cx, band_h - 60,
                           'This is a system-generated invoice and does not require a physical signature.')

    # prominent gold slanted shape, bottom-right (left end is a diagonal cut)
    p = canv.beginPath()
    p.moveTo(PAGE_W - 317, 0)
    p.lineTo(PAGE_W - 317 + 79, 18)
    p.lineTo(PAGE_W, 18)
    p.lineTo(PAGE_W, 0)
    p.close()
    canv.setFillColor(colors.HexColor(GOLD))
    canv.drawPath(p, stroke=0, fill=1)
    canv.restoreState()


def _footer_on_page(canv, doc):
    """Draw the dark page background then the footer band on every page."""
    canv.setFillColor(colors.HexColor(BG))
    canv.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
    _draw_footer_band(canv)


def render_invoice_pdf(invoice):
    """Render a PDF for an Invoice snapshot. Returns bytes."""
    if invoice is None:
        raise ValueError("No invoice to render")

    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=_DOC_LEFT_MARGIN,
        rightMargin=_DOC_RIGHT_MARGIN,
        topMargin=_DOC_TOP_MARGIN,
        bottomMargin=_DOC_BOTTOM_MARGIN,
        title=f"Invoice {invoice.invoice_number}",
        author=STORE_NAME,
    )
    frame = Frame(
        _DOC_LEFT_MARGIN,
        _DOC_BOTTOM_MARGIN,
        PAGE_W - _DOC_LEFT_MARGIN - _DOC_RIGHT_MARGIN,
        PAGE_H - _DOC_TOP_MARGIN - _DOC_BOTTOM_MARGIN,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        id='main',
    )
    template = PageTemplate(id='main', frames=[frame], onPage=_footer_on_page)
    doc.addPageTemplates([template])
    st = _styles()
    story = []

    _render_header(st, story, invoice)
    _render_info(st, story, invoice)
    _render_items(st, story, invoice)
    _render_bottom(st, story, invoice)

    doc.build(story)
    return buf.getvalue()