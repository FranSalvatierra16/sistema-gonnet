from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0088_liquidacion_operaciones_incluidas'),
    ]

    operations = [
        migrations.AddField(
            model_name='sucursal',
            name='porcentaje_comision_default',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Porcentaje por defecto para operaciones de esta sucursal. Si el vendedor tiene % propio, se usa el del vendedor.',
                max_digits=5,
                null=True,
                verbose_name='Comisión vendedores (%)',
            ),
        ),
    ]
