from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0181_costoscompra_venta'),
    ]

    operations = [
        migrations.AddField(
            model_name='costoscompralibropropiedad',
            name='gastos_escritura_venta',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                max_digits=14,
                verbose_name='Gastos de escritura venta (USD)',
            ),
        ),
        migrations.AlterField(
            model_name='costoscompralibropropiedad',
            name='gastos_escritura',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                max_digits=14,
                verbose_name='Gastos de escritura compra (USD)',
            ),
        ),
    ]
