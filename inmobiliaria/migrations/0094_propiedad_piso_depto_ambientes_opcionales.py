# Piso, departamento y ambientes opcionales (ej. lotes / terrenos en venta)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0093_propiedad_llave_charfield'),
    ]

    operations = [
        migrations.AlterField(
            model_name='propiedad',
            name='piso',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Opcional (ej. lotes o terrenos sin piso). Número o descripción (PB, 1, 15…)',
                max_length=10,
                verbose_name='Piso',
            ),
        ),
        migrations.AlterField(
            model_name='propiedad',
            name='departamento',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Opcional. Número o letra de departamento si aplica',
                max_length=10,
                verbose_name='Departamento',
            ),
        ),
        migrations.AlterField(
            model_name='propiedad',
            name='ambientes',
            field=models.IntegerField(
                blank=True,
                help_text='Opcional (ej. lotes sin definición de ambientes)',
                null=True,
                verbose_name='Ambientes',
            ),
        ),
    ]
