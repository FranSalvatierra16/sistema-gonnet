from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0100_movimientocaja_datos_tarjeta_cheque'),
    ]

    operations = [
        migrations.AddField(
            model_name='propiedad',
            name='tipo_fichaje',
            field=models.CharField(
                choices=[('primer', 'Primer fichaje'), ('segundo', 'Segundo fichaje')],
                default='primer',
                help_text='Indica si la comisión por fichaje de la operación corresponde al primer o al segundo fichaje (según % del vendedor).',
                max_length=10,
                verbose_name='Tipo de fichaje',
            ),
        ),
        migrations.AddField(
            model_name='vendedor',
            name='comision_primer_fichaje',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Porcentaje cuando la propiedad está marcada como primer fichaje',
                max_digits=5,
                null=True,
                verbose_name='Comisión primer fichaje (%)',
            ),
        ),
        migrations.AddField(
            model_name='vendedor',
            name='comision_segundo_fichaje',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Porcentaje cuando la propiedad está marcada como segundo fichaje',
                max_digits=5,
                null=True,
                verbose_name='Comisión segundo fichaje (%)',
            ),
        ),
        migrations.AddField(
            model_name='vendedor',
            name='comision_alquiler_24_meses',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Aplica a reservas de alquiler largo (≈20 meses o más entre inicio y fin)',
                max_digits=5,
                null=True,
                verbose_name='Comisión alquiler largo / 24 meses (%)',
            ),
        ),
        migrations.AlterField(
            model_name='vendedor',
            name='comision',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Comisión general (%) usada como respaldo si no hay % específico por fichaje o 24 meses',
                max_digits=5,
                null=True,
            ),
        ),
    ]
