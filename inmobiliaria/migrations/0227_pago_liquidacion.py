import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0226_ajuste_liquidacion_no_pagar'),
    ]

    operations = [
        migrations.CreateModel(
            name='PagoLiquidacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('monto', models.DecimalField(decimal_places=2, max_digits=12)),
                ('fecha', models.DateTimeField(auto_now_add=True)),
                ('liquidacion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pagos', to='inmobiliaria.liquidacionpropietario')),
                ('movimiento_caja', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pagos_liquidacion', to='inmobiliaria.movimientocaja')),
            ],
            options={
                'verbose_name': 'Pago de liquidación',
                'verbose_name_plural': 'Pagos de liquidación',
                'ordering': ['fecha', 'id'],
            },
        ),
    ]
