# Generated by Django 4.2.7 on 2025-02-27 13:41

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0027_alter_disponibilidad_options'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConceptoMovimiento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=100)),
                ('tipo', models.CharField(choices=[('IN', 'Ingreso'), ('EG', 'Egreso')], default='IN', max_length=2)),
            ],
        ),
        migrations.CreateModel(
            name='MovimientoCaja',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateTimeField(auto_now_add=True)),
                ('monto', models.DecimalField(decimal_places=2, max_digits=10)),
                ('descripcion', models.TextField(blank=True)),
                ('comprobante', models.CharField(blank=True, max_length=100)),
                ('estado', models.CharField(choices=[('pendiente', 'Pendiente'), ('confirmado', 'Confirmado'), ('anulado', 'Anulado')], default='pendiente', max_length=10)),
                ('referencia', models.CharField(blank=True, max_length=100)),
                ('empleado', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('sucursal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='inmobiliaria.sucursal')),
                ('tipo', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='inmobiliaria.conceptomovimiento')),
            ],
        ),
        migrations.AlterModelOptions(
            name='historialdisponibilidad',
            options={'ordering': ['-fecha_actualizacion'], 'verbose_name': 'Historial de Disponibilidad', 'verbose_name_plural': 'Historial de Disponibilidades'},
        ),
        migrations.RemoveField(
            model_name='historialdisponibilidad',
            name='reserva',
        ),
        migrations.CreateModel(
            name='ValePersonal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateTimeField(auto_now_add=True)),
                ('monto', models.DecimalField(decimal_places=2, max_digits=10)),
                ('descripcion', models.TextField()),
                ('estado', models.CharField(default='pendiente', max_length=20)),
                ('motivo', models.TextField()),
                ('aprobado_por', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='vales_aprobados', to=settings.AUTH_USER_MODEL)),
                ('empleado', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vales_solicitados', to=settings.AUTH_USER_MODEL)),
                ('movimiento_caja', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='inmobiliaria.movimientocaja')),
                ('sucursal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='inmobiliaria.sucursal')),
            ],
        ),
        migrations.CreateModel(
            name='PagoAlquiler',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_pago', models.DateTimeField(auto_now_add=True)),
                ('monto', models.DecimalField(decimal_places=2, max_digits=10)),
                ('comision', models.DecimalField(decimal_places=2, max_digits=5)),
                ('notificado_propietario', models.BooleanField(default=False)),
                ('fecha_notificacion', models.DateTimeField(blank=True, null=True)),
                ('alquiler', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='inmobiliaria.alquilermeses')),
                ('movimiento_caja', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, to='inmobiliaria.movimientocaja')),
            ],
        ),
        migrations.CreateModel(
            name='ComisionVenta',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateTimeField(auto_now_add=True)),
                ('monto', models.DecimalField(decimal_places=2, max_digits=10)),
                ('porcentaje', models.DecimalField(decimal_places=2, max_digits=5)),
                ('pagada', models.BooleanField(default=False)),
                ('movimiento_caja', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='inmobiliaria.movimientocaja')),
                ('propiedad', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='inmobiliaria.propiedad')),
                ('vendedor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='comisiones', to=settings.AUTH_USER_MODEL)),
                ('venta', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='inmobiliaria.ventapropiedad')),
            ],
        ),
        migrations.CreateModel(
            name='Caja',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_apertura', models.DateTimeField(auto_now_add=True)),
                ('fecha_cierre', models.DateTimeField(blank=True, null=True)),
                ('saldo_inicial', models.DecimalField(decimal_places=2, max_digits=10)),
                ('saldo_final', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('estado', models.CharField(choices=[('abierta', 'Abierta'), ('cerrada', 'Cerrada')], default='abierta', max_length=10)),
                ('observaciones', models.TextField(blank=True)),
                ('saldo', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('fecha_actualizacion', models.DateTimeField(auto_now=True)),
                ('empleado_apertura', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cajas_abiertas', to=settings.AUTH_USER_MODEL)),
                ('empleado_cierre', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cajas_cerradas', to=settings.AUTH_USER_MODEL)),
                ('sucursal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='inmobiliaria.sucursal')),
            ],
        ),
    ]
