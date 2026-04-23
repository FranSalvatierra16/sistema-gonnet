from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0106_mescomisionpagadovendedor'),
    ]

    operations = [
        migrations.AlterField(
            model_name='vendedor',
            name='comision',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Porcentaje para alquiler por día (operación estándar). Respaldo si no aplica % de fichaje, invierno ni alquiler largo / 24 meses.',
                max_digits=5,
                null=True,
                verbose_name='Comisión por día (%)',
            ),
        ),
    ]
