# Add es_principal field to HistorialDisponibilidad

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0045_movimientocaja_honorarios_movimientocaja_sellados'),
    ]

    operations = [
        migrations.AddField(
            model_name='historialdisponibilidad',
            name='es_principal',
            field=models.BooleanField(default=False, help_text='True si es una disponibilidad creada manualmente, False si es automática (fragmentación)'),
        ),
    ]
