from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0180_propiedad_latitud_longitud'),
    ]

    operations = [
        migrations.AddField(
            model_name='costoscompralibropropiedad',
            name='valor_depto_vendido',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                max_digits=14,
                verbose_name='Valor depto vendido (USD)',
            ),
        ),
        migrations.AddField(
            model_name='costoscompralibropropiedad',
            name='honorarios_venta',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                max_digits=14,
                verbose_name='Honorarios pagados venta (USD)',
            ),
        ),
        migrations.AlterField(
            model_name='costoscompralibropropiedad',
            name='honorarios_pagados',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                max_digits=14,
                verbose_name='Honorarios pagados compra (USD)',
            ),
        ),
    ]
