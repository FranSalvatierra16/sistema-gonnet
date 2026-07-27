from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0165_cuentabancaria_saldo_inicial'),
    ]

    operations = [
        migrations.AddField(
            model_name='reserva',
            name='liq_monto_cochera_inquilino',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                help_text='Monto extra de cochera (no entra en el reparto del total). Se suma a cochera de oficina al liquidar.',
                max_digits=12,
                verbose_name='Cochera inquilino (liquidación)',
            ),
        ),
    ]
