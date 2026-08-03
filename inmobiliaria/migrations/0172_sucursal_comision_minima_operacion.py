from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0171_costoscompralibropropiedad'),
    ]

    operations = [
        migrations.AddField(
            model_name='sucursal',
            name='comision_minima_operacion',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('10000.00'),
                help_text=(
                    'Importe mínimo total de comisión de productor por operación. '
                    'Si hay varios productores, se reparte según su % de participación '
                    '(p. ej. $10.000 al 50/50 → $5.000 c/u). 0 = sin mínimo.'
                ),
                max_digits=12,
                verbose_name='Comisión mínima por operación',
            ),
        ),
    ]
