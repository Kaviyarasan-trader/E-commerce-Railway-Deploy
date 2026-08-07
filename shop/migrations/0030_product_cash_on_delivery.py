from django.db import migrations, models


def reset_cod_to_no(apps, schema_editor):
    Product = apps.get_model('shop', 'Product')
    Product.objects.all().update(cash_on_delivery=False)


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0029_product_cod_available'),
    ]

    operations = [
        migrations.RenameField(
            model_name='product',
            old_name='cod_available',
            new_name='cash_on_delivery',
        ),
        migrations.AlterField(
            model_name='product',
            name='cash_on_delivery',
            field=models.BooleanField(default=False, help_text='Cash on Delivery available for this product'),
        ),
        migrations.RunPython(reset_cod_to_no, migrations.RunPython.noop),
    ]
