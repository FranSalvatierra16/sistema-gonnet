from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0136_recalc_liquidacion_sin_cochera_propietario'),
    ]

    operations = [
        migrations.AddField(
            model_name='reserva',
            name='numero_carpeta',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Número de carpeta física (consultorio). Opcional en alquiler por día.',
                max_length=8,
                verbose_name='Nº carpeta',
            ),
        ),
        migrations.AddField(
            model_name='contratoalquiler',
            name='numero_carpeta',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Número de carpeta física para contratos invierno / 24 meses.',
                max_length=8,
                verbose_name='Nº carpeta',
            ),
        ),
    ]
