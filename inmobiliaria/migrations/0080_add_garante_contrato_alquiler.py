# Datos del garante en contrato de alquiler (invierno)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0079_add_propiedad_eliminada'),
    ]

    operations = [
        migrations.AddField(
            model_name='contratoalquiler',
            name='garante_nombre',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='contratoalquiler',
            name='garante_apellido',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='contratoalquiler',
            name='garante_dni',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='contratoalquiler',
            name='garante_celular',
            field=models.CharField(blank=True, max_length=30),
        ),
    ]
