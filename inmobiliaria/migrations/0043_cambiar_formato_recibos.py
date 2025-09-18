# Generated manually for receipt format change

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0042_agregar_numeracion_recibos'),
    ]

    operations = [
        # Primero eliminar el campo existente
        migrations.RemoveField(
            model_name='sucursal',
            name='prefijo_recibo',
        ),
        
        # Recrear el campo con el nuevo tipo
        migrations.AddField(
            model_name='sucursal',
            name='prefijo_recibo',
            field=models.PositiveIntegerField(blank=True, help_text='Número identificador para numeración de recibos (ej: 1, 2, 100)', null=True),
        ),
        
        # Actualizar el campo del contador con nuevo valor por defecto
        migrations.AlterField(
            model_name='sucursal',
            name='ultimo_numero_recibo',
            field=models.PositiveIntegerField(default=1, help_text='Último número de recibo generado (contador secuencial)'),
        ),
    ]
