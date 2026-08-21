import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inmobiliaria', '0182_costoscompra_escritura_venta'),
    ]

    operations = [
        migrations.CreateModel(
            name='ObservacionCobroInquilino',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('concepto_caja_id', models.CharField(max_length=20, verbose_name='ID concepto de caja')),
                ('concepto_nombre', models.CharField(blank=True, default='', max_length=200, verbose_name='Nombre del concepto')),
                ('monto', models.DecimalField(decimal_places=2, max_digits=14)),
                ('moneda', models.CharField(choices=[('ARS', 'Pesos (ARS)'), ('USD', 'Dólares (USD)')], default='ARS', max_length=3)),
                ('detalle', models.CharField(blank=True, default='', max_length=400)),
                ('estado', models.CharField(choices=[('pendiente', 'Pendiente'), ('cobrado', 'Cobrado')], db_index=True, default='pendiente', max_length=20)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('cobrado_en', models.DateTimeField(blank=True, null=True)),
                ('contrato', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='observaciones_cobro', to='inmobiliaria.contratoalquiler')),
                ('creado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='observaciones_cobro_creadas', to=settings.AUTH_USER_MODEL)),
                ('movimiento_cobro', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='observaciones_cobro_inquilino', to='inmobiliaria.movimientocaja')),
                ('sucursal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='observaciones_cobro_inquilino', to='inmobiliaria.sucursal')),
            ],
            options={
                'verbose_name': 'Observación cobro inquilino',
                'verbose_name_plural': 'Observaciones cobro inquilino',
                'ordering': ['-creado_en', '-id'],
            },
        ),
    ]
