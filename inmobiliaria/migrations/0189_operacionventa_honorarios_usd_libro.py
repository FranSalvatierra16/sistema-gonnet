# Honorarios se cargan en USD; ARS = USD × cotización. Sync con libro del depto.

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0188_operacionventa'),
    ]

    operations = [
        migrations.AddField(
            model_name='operacionventa',
            name='honorarios_usd',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                help_text='Monto en dólares que le corresponde al vendedor.',
                max_digits=14,
                verbose_name='Honorarios al vendedor (USD)',
            ),
        ),
        migrations.AddField(
            model_name='operacionventa',
            name='gastos_escritura_usd',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                help_text='Se refleja en el libro del departamento.',
                max_digits=14,
                verbose_name='Gastos de escritura venta (USD)',
            ),
        ),
        migrations.AlterField(
            model_name='operacionventa',
            name='cotizacion_dolar',
            field=models.DecimalField(
                decimal_places=4,
                help_text='Pesos por cada dólar; se usa para pasar los honorarios a pesos.',
                max_digits=12,
                verbose_name='Cotización USD → ARS',
            ),
        ),
        migrations.AlterField(
            model_name='operacionventa',
            name='honorarios_ars',
            field=models.DecimalField(
                decimal_places=2,
                help_text='Resultado: honorarios USD × cotización (comisión en pesos).',
                max_digits=14,
                verbose_name='Honorarios al vendedor (ARS)',
            ),
        ),
    ]
