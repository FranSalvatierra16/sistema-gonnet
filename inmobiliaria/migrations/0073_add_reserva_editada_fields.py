# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0072_agregar_ventilador_aire_cable'),
    ]

    operations = [
        migrations.AddField(
            model_name='reserva',
            name='fecha_inicio_original',
            field=models.DateField(blank=True, null=True, verbose_name='Fecha inicio original'),
        ),
        migrations.AddField(
            model_name='reserva',
            name='fecha_fin_original',
            field=models.DateField(blank=True, null=True, verbose_name='Fecha fin original'),
        ),
        migrations.AddField(
            model_name='reserva',
            name='fue_editada',
            field=models.BooleanField(default=False, verbose_name='Fue editada'),
        ),
    ]
