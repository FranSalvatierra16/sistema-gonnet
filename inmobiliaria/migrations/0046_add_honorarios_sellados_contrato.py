# Add honorarios and sellados fields to ContratoAlquiler

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0045_movimientocaja_honorarios_movimientocaja_sellados'),
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
