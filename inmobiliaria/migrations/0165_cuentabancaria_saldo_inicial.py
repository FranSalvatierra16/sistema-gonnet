from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0164_disponibilidad_forzar_disponible'),
    ]

    operations = [
        migrations.AddField(
            model_name='cuentabancaria',
            name='saldo_inicial',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                help_text='Saldo de partida para reportes: el acumulado arranca desde este monto.',
                max_digits=14,
                verbose_name='Saldo inicial',
            ),
        ),
    ]
