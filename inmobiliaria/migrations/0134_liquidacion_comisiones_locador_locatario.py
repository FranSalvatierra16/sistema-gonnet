from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0133_desactivar_categorias_legacy_oficina'),
    ]

    operations = [
        migrations.AddField(
            model_name='liquidacionpropietario',
            name='comision_locador',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                max_digits=12,
                verbose_name='Comisión locador',
                help_text='Primera operación contratos 9/24 meses: comisión a cargo del locador.',
            ),
        ),
        migrations.AddField(
            model_name='liquidacionpropietario',
            name='comision_locatario',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                max_digits=12,
                verbose_name='Comisión locatario',
                help_text='Primera operación contratos 9/24 meses: honorarios / comisión locatario.',
            ),
        ),
    ]
