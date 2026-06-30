from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0146_estado_confirmacion_caratula'),
    ]

    operations = [
        migrations.AddField(
            model_name='vendedor',
            name='comision_primer_fichaje_invierno',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Sobre honorarios en contratos/reservas invierno (9 meses). Si está vacío, usa el % de primer fichaje general.',
                max_digits=5,
                null=True,
                verbose_name='Comisión primer fichaje invierno (%)',
            ),
        ),
        migrations.AddField(
            model_name='vendedor',
            name='comision_segundo_fichaje_invierno',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Sobre honorarios en invierno. Si está vacío, usa segundo fichaje general o primer fichaje invierno.',
                max_digits=5,
                null=True,
                verbose_name='Comisión segundo fichaje invierno (%)',
            ),
        ),
        migrations.AddField(
            model_name='vendedor',
            name='comision_primer_fichaje_24_meses',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Sobre honorarios en contratos/reservas de 24 meses. Si está vacío, usa el % de primer fichaje general.',
                max_digits=5,
                null=True,
                verbose_name='Comisión primer fichaje 24 meses (%)',
            ),
        ),
        migrations.AddField(
            model_name='vendedor',
            name='comision_segundo_fichaje_24_meses',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Sobre honorarios en 24 meses. Si está vacío, usa segundo fichaje general o primer fichaje 24 meses.',
                max_digits=5,
                null=True,
                verbose_name='Comisión segundo fichaje 24 meses (%)',
            ),
        ),
        migrations.AlterField(
            model_name='vendedor',
            name='comision_primer_fichaje',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Porcentaje sobre honorarios cuando la propiedad está marcada como primer fichaje (alquiler por día).',
                max_digits=5,
                null=True,
                verbose_name='Comisión primer fichaje (%)',
            ),
        ),
        migrations.AlterField(
            model_name='vendedor',
            name='comision_segundo_fichaje',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Porcentaje sobre honorarios cuando la propiedad está marcada como segundo fichaje (alquiler por día).',
                max_digits=5,
                null=True,
                verbose_name='Comisión segundo fichaje (%)',
            ),
        ),
        migrations.AlterField(
            model_name='vendedor',
            name='comision_invierno',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Sobre honorarios en invierno / 9 meses (productor de la operación).',
                max_digits=5,
                null=True,
                verbose_name='Comisión alquiler invierno (%)',
            ),
        ),
        migrations.AlterField(
            model_name='vendedor',
            name='comision_alquiler_24_meses',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Sobre honorarios en contratos/reservas de 24 meses o largo plazo (productor).',
                max_digits=5,
                null=True,
                verbose_name='Comisión alquiler largo / 24 meses (%)',
            ),
        ),
    ]
