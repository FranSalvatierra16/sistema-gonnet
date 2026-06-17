from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0130_movimientocaja_fecha_transferencia'),
    ]

    operations = [
        migrations.AlterField(
            model_name='movimientocaja',
            name='fecha',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
