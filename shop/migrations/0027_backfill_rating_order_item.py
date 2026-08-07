from django.db import migrations


def backfill_order_item(apps, schema_editor):
    ProductRating = apps.get_model('shop', 'ProductRating')
    OrderItem = apps.get_model('shop', 'OrderItem')
    for pr in ProductRating.objects.filter(order_item__isnull=True):
        oi = (
            OrderItem.objects
            .filter(product=pr.product, order__user=pr.user)
            .order_by('-order__delivered_at', '-order__updated_at')
            .first()
        )
        if oi:
            pr.order_item = oi
            pr.save(update_fields=['order_item'])


def reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0026_add_order_item_to_rating'),
    ]

    operations = [
        migrations.RunPython(backfill_order_item, reverse),
    ]
