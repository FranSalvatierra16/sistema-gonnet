# Generated manually to avoid indentation errors

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0044_cambiar_estado_ocupado_a_alquilado'),
    ]

    operations = [
        migrations.AddField(
            model_name='contratoalquiler',
            name='honorarios',
            field=models.DecimalField(blank=True, decimal_places=2, default=0, help_text='Monto de honorarios configurado', max_digits=10),
        ),
        migrations.AddField(
            model_name='contratoalquiler',
            name='sellados',
            field=models.DecimalField(blank=True, decimal_places=2, default=0, help_text='Monto de sellados configurado', max_digits=10),
        ),
    ]
