# Generated manually for OperacionVenta

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inmobiliaria', '0187_movimientocaja_concepto_textfield'),
    ]

    operations = [
        migrations.CreateModel(
            name='OperacionVenta',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_venta', models.DateField(default=django.utils.timezone.localdate, verbose_name='Fecha de venta')),
                ('precio_usd', models.DecimalField(decimal_places=2, max_digits=14, verbose_name='Precio de venta (USD)')),
                ('cotizacion_dolar', models.DecimalField(decimal_places=4, help_text='Pesos por cada dólar al momento de cargar los honorarios.', max_digits=12, verbose_name='Cotización USD → ARS')),
                ('honorarios_ars', models.DecimalField(decimal_places=2, help_text='Monto en pesos que vos elegís para el vendedor.', max_digits=14, verbose_name='Honorarios al vendedor (ARS)')),
                ('comprador_nombre', models.CharField(blank=True, default='', max_length=255, verbose_name='Comprador')),
                ('escribania', models.CharField(blank=True, default='', max_length=255, verbose_name='Escribanía')),
                ('observaciones', models.TextField(blank=True, default='', verbose_name='Observaciones')),
                ('estado', models.CharField(choices=[('confirmada', 'Confirmada'), ('anulada', 'Anulada')], default='confirmada', max_length=20, verbose_name='Estado')),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('comision', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='operacion_venta', to='inmobiliaria.comisionvendedor', verbose_name='Comisión generada')),
                ('creado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='operaciones_venta_creadas', to=settings.AUTH_USER_MODEL)),
                ('propiedad', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='operaciones_venta', to='inmobiliaria.propiedad', verbose_name='Propiedad')),
                ('sucursal', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='operaciones_venta', to='inmobiliaria.sucursal', verbose_name='Sucursal')),
                ('vendedor', models.ForeignKey(help_text='Quien realizó la venta (recibe los honorarios).', on_delete=django.db.models.deletion.PROTECT, related_name='operaciones_venta', to=settings.AUTH_USER_MODEL, verbose_name='Vendedor / productor')),
            ],
            options={
                'verbose_name': 'Operación de venta',
                'verbose_name_plural': 'Operaciones de venta',
                'ordering': ['-fecha_venta', '-id'],
            },
        ),
    ]
