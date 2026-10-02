from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0209_cuadro_honorarios_columna_vigencia'),
    ]

    operations = [
        migrations.CreateModel(
            name='Tasacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('propiedad_nombre', models.CharField(max_length=255, verbose_name='Propiedad')),
                ('fecha', models.DateField(default=django.utils.timezone.localdate, verbose_name='Fecha')),
                ('moneda', models.CharField(choices=[('ARS', 'Pesos'), ('USD', 'Dólares')], default='ARS', max_length=3)),
                ('monto', models.DecimalField(decimal_places=2, help_text='En la moneda elegida.', max_digits=14, verbose_name='Monto de la tasación')),
                ('cotizacion_dolar', models.DecimalField(blank=True, decimal_places=4, max_digits=12, null=True, verbose_name='Cotización USD → ARS')),
                ('monto_ars', models.DecimalField(decimal_places=2, max_digits=14, verbose_name='Monto en pesos')),
                ('tipo_comision', models.CharField(choices=[('porcentaje', 'Porcentaje'), ('monto', 'Monto fijo')], default='porcentaje', max_length=12)),
                ('porcentaje_comision', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='Comisión (%)')),
                ('comision_monto', models.DecimalField(blank=True, decimal_places=2, help_text='En la moneda de la tasación.', max_digits=14, null=True, verbose_name='Comisión fija')),
                ('comision_ars', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14, verbose_name='Comisión del productor (ARS)')),
                ('cliente_nombre', models.CharField(blank=True, default='', max_length=255, verbose_name='Solicitante')),
                ('observaciones', models.TextField(blank=True, default='')),
                ('estado', models.CharField(choices=[('confirmada', 'Confirmada'), ('anulada', 'Anulada')], default='confirmada', max_length=20)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('comision', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tasacion', to='inmobiliaria.comisionvendedor')),
                ('creado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tasaciones_creadas', to=settings.AUTH_USER_MODEL)),
                ('sucursal', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='tasaciones', to='inmobiliaria.sucursal')),
                ('vendedor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='tasaciones', to=settings.AUTH_USER_MODEL, verbose_name='Productor')),
            ],
            options={
                'verbose_name': 'Tasación',
                'verbose_name_plural': 'Tasaciones',
                'ordering': ['-fecha', '-id'],
            },
        ),
    ]
