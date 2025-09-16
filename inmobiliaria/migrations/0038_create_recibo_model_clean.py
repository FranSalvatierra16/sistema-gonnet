# Generated manually to fix migration issues
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0037_add_fichado_por_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='Recibo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero_recibo', models.CharField(max_length=20, unique=True)),
                ('fecha_emision', models.DateTimeField(auto_now_add=True)),
                ('precio_total_operacion', models.DecimalField(decimal_places=2, help_text='Precio total de la operación', max_digits=10)),
                ('monto_este_pago', models.DecimalField(decimal_places=2, help_text='Monto pagado en este recibo', max_digits=10)),
                ('total_pagado_antes', models.DecimalField(decimal_places=2, default=0, help_text='Total pagado antes de este recibo', max_digits=10)),
                ('saldo_pendiente', models.DecimalField(decimal_places=2, help_text='Saldo que queda por pagar después de este recibo', max_digits=10)),
                ('conceptos_detalle', models.JSONField(default=dict, help_text='Detalles de los conceptos pagados en este recibo')),
                ('observaciones', models.TextField(blank=True)),
                ('empleado', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('movimiento_caja', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='recibo', to='inmobiliaria.movimientocaja')),
                ('propiedad', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recibos', to='inmobiliaria.propiedad')),
                ('reserva', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recibos', to='inmobiliaria.reserva')),
            ],
            options={
                'verbose_name': 'Recibo',
                'verbose_name_plural': 'Recibos',
                'db_table': 'inmobiliaria_recibo',
                'ordering': ['-fecha_emision'],
            },
        ),
    ]
