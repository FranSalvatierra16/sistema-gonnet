# Comisión fichaje de venta en Vendedor

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0197_vendedor_comision_venta'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendedor',
            name='comision_fichaje_venta',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Porcentaje sobre los honorarios de productores de la venta (quien fichó la propiedad).',
                max_digits=5,
                null=True,
                verbose_name='Comisión fichaje de venta (%)',
            ),
        ),
        migrations.AlterField(
            model_name='vendedor',
            name='comision_venta',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Porcentaje sobre el valor de venta (USD). Si hay varios productores, cada uno cobra su %.',
                max_digits=5,
                null=True,
                verbose_name='Comisión por venta de propiedad (%)',
            ),
        ),
    ]
