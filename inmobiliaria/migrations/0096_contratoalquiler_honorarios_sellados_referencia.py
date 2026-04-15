# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0095_liquidacionpropietario_monto_cochera'),
    ]

    operations = [
        migrations.AddField(
            model_name='contratoalquiler',
            name='honorarios_referencia',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Monto informado al crear el contrato; precarga en operación principal.',
                max_digits=10,
                verbose_name='Honorarios (referencia)',
            ),
        ),
        migrations.AddField(
            model_name='contratoalquiler',
            name='sellados_referencia',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Monto informado al crear el contrato; precarga en operación principal.',
                max_digits=10,
                verbose_name='Sellados (referencia)',
            ),
        ),
    ]
