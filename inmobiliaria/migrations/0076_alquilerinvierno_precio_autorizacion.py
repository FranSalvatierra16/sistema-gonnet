# Generated migration: add precio_autorizacion to AlquilerInvierno

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0075_fix_ventapropiedad_id_sequence'),
    ]

    operations = [
        migrations.AddField(
            model_name='alquilerinvierno',
            name='precio_autorizacion',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=12,
                null=True,
                verbose_name='Precio de autorización'
            ),
        ),
    ]
