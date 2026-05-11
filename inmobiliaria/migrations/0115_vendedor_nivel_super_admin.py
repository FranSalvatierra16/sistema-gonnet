# Choices nivel 5 — Super administrador (sin cambio de columna en BD).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0114_allow_duplicate_dni_inquilino_propietario'),
    ]

    operations = [
        migrations.AlterField(
            model_name='vendedor',
            name='nivel',
            field=models.IntegerField(
                choices=[
                    (1, 'Básico'),
                    (2, 'Intermedio'),
                    (3, 'Avanzado'),
                    (4, 'Administrador'),
                    (5, 'Super administrador'),
                ],
                default=1,
                help_text='Nivel del vendedor para determinar sus permisos',
            ),
        ),
    ]
