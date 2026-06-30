from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0143_reserva_montos_liquidacion_caratula'),
    ]

    operations = [
        migrations.AddField(
            model_name='propiedad',
            name='es_propiedad_oficina',
            field=models.BooleanField(
                default=False,
                help_text='Propiedad de la inmobiliaria (oficina). En invierno y 24 meses aplica el % «propiedad oficina» del vendedor.',
                verbose_name='Propiedad oficina',
            ),
        ),
        migrations.AddField(
            model_name='vendedor',
            name='comision_invierno_propiedad_oficina',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Invierno en propiedades marcadas como «propiedad oficina».',
                max_digits=5,
                null=True,
                verbose_name='Comisión invierno — propiedad oficina (%)',
            ),
        ),
        migrations.AddField(
            model_name='vendedor',
            name='comision_alquiler_24_meses_propiedad_oficina',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='24 meses / largo plazo en propiedades marcadas como «propiedad oficina».',
                max_digits=5,
                null=True,
                verbose_name='Comisión 24 meses — propiedad oficina (%)',
            ),
        ),
    ]
