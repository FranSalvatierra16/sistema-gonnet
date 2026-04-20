from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0101_propiedad_tipo_fichaje_vendedor_comisiones_fichaje'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendedor',
            name='comision_invierno',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Si la propiedad tiene invierno habilitado, la reserva dura menos de 20 meses y el inicio cae entre abr-oct (temporada típica sur), se usa este %',
                max_digits=5,
                null=True,
                verbose_name='Comisión alquiler invierno (%)',
            ),
        ),
    ]
