from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0179_costoscompra_observaciones'),
    ]

    operations = [
        migrations.AddField(
            model_name='propiedad',
            name='latitud',
            field=models.DecimalField(
                blank=True,
                decimal_places=7,
                help_text='Coordenada para el mapa del portal. Se completa sola a partir de la dirección.',
                max_digits=10,
                null=True,
                verbose_name='Latitud',
            ),
        ),
        migrations.AddField(
            model_name='propiedad',
            name='longitud',
            field=models.DecimalField(
                blank=True,
                decimal_places=7,
                help_text='Coordenada para el mapa del portal. Se completa sola a partir de la dirección.',
                max_digits=10,
                null=True,
                verbose_name='Longitud',
            ),
        ),
    ]
