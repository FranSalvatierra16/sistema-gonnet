# Generated manually to rename movimiento_caja field to movimiento

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0023_add_fecha_operacion_to_contrato'),
    ]

    operations = [
        migrations.RenameField(
            model_name='cuotamensual',
            old_name='movimiento_caja',
            new_name='movimiento',
        ),
    ] 