from django.db import migrations, models
import django.db.models.deletion


def forwards_migrar_cupon_legacy(apps, schema_editor):
    MovimientoCaja = apps.get_model('inmobiliaria', 'MovimientoCaja')
    CuponTarjetaMovimientoCaja = apps.get_model('inmobiliaria', 'CuponTarjetaMovimientoCaja')
    for mov in MovimientoCaja.objects.exclude(tarjeta_cupon='').iterator(chunk_size=500):
        if CuponTarjetaMovimientoCaja.objects.filter(movimiento_id=mov.id).exists():
            continue
        cupon = (mov.tarjeta_cupon or '').strip()
        if not cupon and not (mov.tarjeta_numero or '').strip() and not (mov.tarjeta_tipo or '').strip():
            continue
        CuponTarjetaMovimientoCaja.objects.create(
            movimiento_id=mov.id,
            monto=mov.monto_tarjeta or 0,
            cupon=cupon[:64],
            numero=(mov.tarjeta_numero or '')[:32],
            tipo=(mov.tarjeta_tipo or '')[:10],
            orden=0,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0236_contratoalquiler_hora_quien_salida'),
    ]

    operations = [
        migrations.CreateModel(
            name='CuponTarjetaMovimientoCaja',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('monto', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('cupon', models.CharField(blank=True, max_length=64)),
                ('numero', models.CharField(blank=True, help_text='Nº / referencia de tarjeta', max_length=32)),
                ('tipo', models.CharField(blank=True, choices=[('credito', 'Crédito'), ('debito', 'Débito')], default='', max_length=10)),
                ('orden', models.PositiveSmallIntegerField(default=0)),
                ('movimiento', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='cupones_tarjeta',
                    to='inmobiliaria.movimientocaja',
                )),
            ],
            options={
                'verbose_name': 'Cupón de tarjeta',
                'verbose_name_plural': 'Cupones de tarjeta',
                'db_table': 'inmobiliaria_cupontarjetamovimientocaja',
                'ordering': ['orden', 'id'],
            },
        ),
        migrations.RunPython(forwards_migrar_cupon_legacy, migrations.RunPython.noop),
    ]
