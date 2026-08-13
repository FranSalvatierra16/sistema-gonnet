import datetime
from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0176_alquilermeses_ofrecible_desde'),
    ]

    operations = [
        migrations.AddField(
            model_name='cuentabancaria',
            name='fecha_saldo_inicial',
            field=models.DateField(
                default=datetime.date(2026, 6, 8),
                help_text='Fecha de corte del saldo inicial en el reporte (editable por cuenta).',
                verbose_name='Fecha del saldo inicial',
            ),
        ),
        migrations.AlterField(
            model_name='cuentabancaria',
            name='saldo_inicial',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                help_text='Saldo de corte para reportes de transferencias a esta cuenta.',
                max_digits=14,
                verbose_name='Saldo inicial',
            ),
        ),
    ]
