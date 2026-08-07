import re

from django.db import migrations

CANONICAL_TITLES = {
    'order_placed': 'Order Placed Successfully',
    'payment_success': 'Payment Successful',
    'payment_failed': 'Payment Failed',
    'order_confirmed': 'Order Confirmed',
    'order_shipped': 'Order Shipped',
    'out_for_delivery': 'Out for Delivery',
    'order_delivered': 'Order Delivered',
    'order_cancelled': 'Order Cancelled',
    'order_refunded': 'Refund Initiated',
    'refund_completed': 'Refund Completed',
    'return_approved': 'Return Request Approved',
    'return_rejected': 'Return Request Rejected',
}

ID_RE = re.compile(r'#\d+')


def strip_order_ids(text):
    """Remove internal order IDs (e.g. '#197') from user-facing text."""
    if not text:
        return text
    text = re.sub(r'\s*for order\s*#\d+', '', text)
    text = re.sub(r'\s*#\d+\s*', ' ', text)
    return re.sub(r'\s{2,}', ' ', text).strip()


def upgrade(apps, schema_editor):
    Notification = apps.get_model('shop', 'Notification')
    for n in Notification.objects.filter(notification_type__in=CANONICAL_TITLES):
        new_title = CANONICAL_TITLES[n.notification_type]
        changed = False
        if n.title != new_title:
            n.title = new_title
            changed = True
        if n.message and ID_RE.search(n.message):
            n.message = strip_order_ids(n.message)
            changed = True
        if changed:
            n.save(update_fields=['title', 'message'])


def downgrade(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0033_notification_title_cleanup'),
    ]

    operations = [
        migrations.RunPython(upgrade, downgrade),
    ]
