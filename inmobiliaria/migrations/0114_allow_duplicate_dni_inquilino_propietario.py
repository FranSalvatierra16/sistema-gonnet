# Generated manually — permite el mismo DNI en más de un inquilino o propietario.

from django.db import migrations, models

import inmobiliaria.models.persona


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0113_propietario_datos_cuenta_bancaria'),
    ]

    operations = [
        migrations.AlterField(
            model_name='inquilino',
            name='dni',
            field=models.CharField(
                blank=True,
                max_length=8,
                null=True,
                validators=[inmobiliaria.models.persona.validate_dni],
            ),
        ),
        migrations.AlterField(
            model_name='propietario',
            name='dni',
            field=models.CharField(
                blank=True,
                max_length=8,
                null=True,
                validators=[inmobiliaria.models.persona.validate_dni],
            ),
        ),
    ]
