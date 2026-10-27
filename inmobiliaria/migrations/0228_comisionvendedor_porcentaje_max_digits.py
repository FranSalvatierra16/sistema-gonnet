# Amplía % de comisión: en ventas el ratio comisión/honorarios puede superar 999,99.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0227_pago_liquidacion'),
    ]

    operations = [
        migrations.AlterField(
            model_name='comisionvendedor',
            name='porcentaje_comision',
            field=models.DecimalField(
                decimal_places=2,
                help_text='En ventas puede superar 100 si la comisión es mayor a los honorarios de oficina.',
                max_digits=10,
                verbose_name='Porcentaje de Comisión (%)',
            ),
        ),
    ]
