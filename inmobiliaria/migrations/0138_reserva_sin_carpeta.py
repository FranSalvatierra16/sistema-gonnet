from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0137_numero_carpeta_operacion'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='reserva',
            name='numero_carpeta',
        ),
        migrations.AlterField(
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
