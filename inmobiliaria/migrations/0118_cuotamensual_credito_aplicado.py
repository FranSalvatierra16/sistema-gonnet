from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0117_drop_db_unique_dni_propietario_inquilino'),
    ]

    operations = [
        migrations.AddField(
            model_name='cuotamensual',
            name='credito_aplicado',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                max_digits=12,
                verbose_name='Crédito aplicado (excedente de pago anterior)',
                help_text='Importe que ya cubre un pago con excedente; reduce el saldo a cobrar de esta cuota.',
            ),
        ),
    ]
