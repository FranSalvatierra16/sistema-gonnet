from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0158_movimientocaja_cotizacion_dolar'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contratoalquiler',
            name='vendedor',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='contratos',
                to='inmobiliaria.vendedor',
            ),
        ),
    ]
