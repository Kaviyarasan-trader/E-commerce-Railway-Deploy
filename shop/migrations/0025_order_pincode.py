# Generated manually to add Order.pincode and re-estimate delivery dates.

import datetime
import re
from django.db import migrations, models

STORE_PINCODE = '600001'


def normalize_pincode(value):
    if not value:
        return ''
    return ''.join(ch for ch in str(value) if ch.isdigit())[:6]


def extract_pincode(text):
    if not text:
        return ''
    match = re.search(r'\b[1-9]\d{5}\b', str(text))
    return match.group(0) if match else ''


def estimate_delivery_days(pincode):
    pin = normalize_pincode(pincode)
    if len(pin) == 6:
        if pin[:3] == STORE_PINCODE[:3]:
            return 2
        if pin[:2] == STORE_PINCODE[:2]:
            return 3
        return 5
    return 4


def add_business_days(start, days):
    result = start
    added = 0
    while added < days:
        result += datetime.timedelta(days=1)
        if result.weekday() < 5:
            added += 1
    return result


def backfill_pincode_and_redate(apps, schema_editor):
    Order = apps.get_model('shop', 'Order')
    for order in Order.objects.all():
        pin = normalize_pincode(order.pincode) or extract_pincode(order.address)
        fields = []
        if pin and order.pincode != pin:
            order.pincode = pin
            fields.append('pincode')
        if pin and order.expected_delivery_date:
            days = estimate_delivery_days(pin)
            base = order.created_at or datetime.datetime.now(datetime.timezone.utc)
            new_date = add_business_days(base, days).date()
            if new_date != order.expected_delivery_date:
                order.expected_delivery_date = new_date
                fields.append('expected_delivery_date')
        if fields:
            order.save(update_fields=fields)


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0024_order_expected_delivery_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='pincode',
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
        migrations.RunPython(backfill_pincode_and_redate, migrations.RunPython.noop),
    ]
