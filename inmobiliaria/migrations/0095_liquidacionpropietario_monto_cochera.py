from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0094_propiedad_piso_depto_ambientes_opcionales'),
    ]

    operations = [
        migrations.AddField(
            model_name='liquidacionpropietario',
            name='monto_cochera',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                help_text='Importe de cochera en la liquidación (opcional)',
                max_digits=12,
                verbose_name='Monto cochera',
            ),
        ),
    ]
