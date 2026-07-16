from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0160_reserva_moneda'),
    ]

    operations = [
        migrations.AddField(
            model_name='liquidacionpropietario',
            name='cotizacion_dolar',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Cotización ARS por USD del día al crear la liquidación (opcional).',
                max_digits=14,
                null=True,
                verbose_name='Cotización del dólar',
            ),
        ),
        migrations.AlterField(
            model_name='movimientocaja',
            name='cotizacion_dolar',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Cotización ARS por USD del día al cargar el movimiento (opcional, ARS o USD).',
                max_digits=14,
                null=True,
            ),
        ),
    ]
