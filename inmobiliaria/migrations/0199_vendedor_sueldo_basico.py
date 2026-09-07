from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0198_vendedor_comision_fichaje_venta'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendedor',
            name='sueldo_basico',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=None,
                help_text='Monto fijo mensual del productor. Se usa en la liquidación del mes junto con las comisiones.',
                max_digits=14,
                null=True,
                verbose_name='Sueldo básico',
            ),
        ),
        migrations.AddField(
            model_name='vendedor',
            name='basico_no_suma_si_comisiones_superan',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Como el caso Sebastián: si está marcado y las comisiones del mes '
                    'son mayores o iguales al sueldo básico, el total a pagar es solo comisiones '
                    '(el básico no se suma). Si no está marcado, siempre se suma básico + comisiones.'
                ),
                verbose_name='Si las comisiones superan el básico, no sumar el básico',
            ),
        ),
    ]
