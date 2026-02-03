# Generated manually - evita "numeric field overflow" al guardar precios (ajuste_porcentaje era 5,2)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0073_add_reserva_editada_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='precio',
            name='ajuste_porcentaje',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=7, verbose_name='Ajuste (%)'),
        ),
    ]
