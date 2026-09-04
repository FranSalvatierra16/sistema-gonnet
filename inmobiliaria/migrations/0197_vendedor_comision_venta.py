# Comisión por venta de propiedad en Vendedor

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0196_operacionventa_vendedores_fichaje'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendedor',
            name='comision_venta',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Peso relativo al repartir honorarios de una venta. Si hay varios productores, se divide según estos %.',
                max_digits=5,
                null=True,
                verbose_name='Comisión por venta de propiedad (%)',
            ),
        ),
    ]
