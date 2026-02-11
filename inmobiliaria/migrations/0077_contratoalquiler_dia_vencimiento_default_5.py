# Vencimientos siempre el día 5 por defecto

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0076_alquilerinvierno_precio_autorizacion'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contratoalquiler',
            name='dia_vencimiento',
            field=models.PositiveIntegerField(default=5, help_text='Día del mes para vencimiento de cuotas (1-28)'),
        ),
    ]
