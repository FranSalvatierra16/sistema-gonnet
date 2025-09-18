# Generated manually for receipt numbering system

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0041_alter_caja_options_alter_caja_unique_together'),
    ]

    operations = [
        migrations.AddField(
            model_name='sucursal',
            name='prefijo_recibo',
            field=models.CharField(blank=True, help_text='Prefijo de 4 dígitos para numeración de recibos (ej: 0004)', max_length=4, null=True),
        ),
        migrations.AddField(
            model_name='sucursal',
            name='ultimo_numero_recibo',
            field=models.PositiveIntegerField(default=40000000, help_text='Último número de recibo generado (8 dígitos)'),
        ),
        migrations.AddField(
            model_name='sucursal',
            name='usar_numeracion_automatica',
            field=models.BooleanField(default=False, help_text='Activar numeración automática de recibos'),
        ),
    ]
