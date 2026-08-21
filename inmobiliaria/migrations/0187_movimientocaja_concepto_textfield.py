from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0186_observacioncobro_gasto_propietario'),
    ]

    operations = [
        migrations.AlterField(
            model_name='movimientocaja',
            name='concepto',
            field=models.TextField(blank=True),
        ),
    ]
