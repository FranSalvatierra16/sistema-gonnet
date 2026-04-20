from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0098_reset_caja_colon_corrientes_cero'),
    ]

    operations = [
        migrations.AddField(
            model_name='liquidacionpropietario',
            name='monto_fondo_mantenimiento',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                help_text='Importe de fondo de mantenimiento en la liquidación (opcional)',
                max_digits=12,
                verbose_name='Fondo de mantenimiento',
            ),
        ),
    ]
