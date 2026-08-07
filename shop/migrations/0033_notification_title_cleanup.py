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

# (new message fragment with {id}, old message fragment)
MESSAGE_FIXES = (
    ('We have received your payment of {amount} for order #{id}. Thank you!', 'We have received your payment of {amount}. Thank you!'),
    ('We could not process your payment of {amount} for order #{id}. Please try again.', 'We could not process your payment of {amount}. Please try again.'),
    ('Your order #{id} has been confirmed and is being processed.', 'Your order has been confirmed and is being processed.'),
    ('Great news! Your order #{id} is on its way. Track it from My Orders.', 'Great news! Your order is on its way. Track it from My Orders.'),
    ('Your order #{id} is out for delivery and should reach you today.', 'Your order is out for delivery and should reach you today.'),
    ('Your order #{id} has been delivered. We hope you love it!', 'Your order has been delivered. We hope you love it!'),
    ('Your order #{id} has been cancelled.', 'Your order has been cancelled.'),
    ('Your refund for order #{id} has been initiated. It will reflect in 5-7 business days.', 'Your refund has been initiated. It will reflect in 5-7 business days.'),
    ('Your refund for order #{id} has been completed successfully.', 'Your refund has been completed successfully.'),
    ('Your return request for order #{id} has been approved. A pickup will be arranged shortly.', 'Your return request has been approved. A pickup will be arranged shortly.'),
    ('We regret to inform you that your return request for order #{id} was not approved.', 'We regret to inform you that your return request was not approved.'),
)

ORDER_ID_RE = re.compile(r'#(\d+)')
AMOUNT_RE = re.compile(r'Rs\.\s*[\d,]+')


def upgrade(apps, schema_editor):
    Notification = apps.get_model('shop', 'Notification')
    for n in Notification.objects.filter(notification_type__in=CANONICAL_TITLES):
        new_title = CANONICAL_TITLES[n.notification_type]
        changed = False
        if n.title != new_title:
            n.title = new_title
            changed = True
        match = ORDER_ID_RE.search(n.title) or ORDER_ID_RE.search(n.message)
        if match and f'#{match.group(1)}' not in n.message:
            order_id = match.group(1)
            amount = AMOUNT_RE.search(n.message)
            amount_str = amount.group(0) if amount else ''
            for new_frag, old_frag in MESSAGE_FIXES:
                new_frag = new_frag.replace('{amount}', amount_str).replace('{id}', order_id)
                if n.message == old_frag.replace('{amount}', amount_str) or \
                        n.message == old_frag or \
                        (old_frag in n.message and n.notification_type in ('order_cancelled',)):
                    n.message = n.message.replace(
                        old_frag.replace('{amount}', amount_str), new_frag, 1)
                    changed = True
                    break
        if changed:
            n.save(update_fields=['title', 'message'])


def downgrade(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0032_invoice'),
    ]

    operations = [
        migrations.RunPython(upgrade, downgrade),
    ]
