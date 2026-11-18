from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0235_separar_disponibilidad_ficha_100870'),
    ]

    operations = [
        migrations.AddField(
            model_name='contratoalquiler',
            name='hora_salida',
            field=models.TimeField(
                blank=True,
                help_text='Hora pactada/cargada para la salida (invierno / 24 meses).',
                null=True,
                verbose_name='Hora de salida',
            ),
        ),
        migrations.AddField(
            model_name='contratoalquiler',
            name='quien_hace_salida',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Texto libre: quién realiza la salida (no está ligado a un usuario).',
                max_length=120,
                verbose_name='Quién hace la salida',
            ),
        ),
    ]
