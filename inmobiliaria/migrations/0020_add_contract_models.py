# Generated manually for contract models

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0019_fix_foreign_key_issue'),
    ]

    operations = [
        migrations.CreateModel(
            name='TipoOperacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
            options={
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='ContratoAlquiler',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_inicio', models.DateField()),
                ('fecha_fin', models.DateField()),
                ('duracion_meses', models.PositiveIntegerField()),
                ('precio_mensual', models.DecimalField(decimal_places=2, max_digits=10)),
                ('deposito_garantia', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('gastos_adicionales', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('estado', models.CharField(choices=[('activo', 'Activo'), ('finalizado', 'Finalizado'), ('rescindido', 'Rescindido')], default='activo', max_length=20)),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('inquilino', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contratos', to='inmobiliaria.inquilino')),
                ('propiedad', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contratos', to='inmobiliaria.propiedad')),
                ('sucursal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='inmobiliaria.sucursal')),
                ('vendedor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contratos', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Contrato de Alquiler',
                'verbose_name_plural': 'Contratos de Alquiler',
                'ordering': ['-fecha_creacion'],
            },
        ),
        migrations.CreateModel(
            name='CuotaMensual',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero_cuota', models.PositiveIntegerField()),
                ('fecha_vencimiento', models.DateField()),
                ('fecha_pago', models.DateTimeField(blank=True, null=True)),
                ('monto_base', models.DecimalField(decimal_places=2, max_digits=10)),
                ('recargo_mora', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('descuento', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('monto_total', models.DecimalField(decimal_places=2, max_digits=10)),
                ('estado', models.CharField(choices=[('pendiente', 'Pendiente'), ('pagada', 'Pagada'), ('vencida', 'Vencida'), ('pagada_con_mora', 'Pagada con Mora')], default='pendiente', max_length=20)),
                ('contrato', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cuotas', to='inmobiliaria.contratoalquiler')),
                ('movimiento', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='inmobiliaria.movimientocaja')),
            ],
            options={
                'verbose_name': 'Cuota Mensual',
                'verbose_name_plural': 'Cuotas Mensuales',
                'ordering': ['numero_cuota'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='cuotamensual',
            unique_together={('contrato', 'numero_cuota')},
        ),
    ] 