from django.db import migrations, models
import django.db.models.deletion


def forwards_migrar_transferencia_legacy(apps, schema_editor):
    MovimientoCaja = apps.get_model('inmobiliaria', 'MovimientoCaja')
    TransferenciaMovimientoCaja = apps.get_model('inmobiliaria', 'TransferenciaMovimientoCaja')
    qs = MovimientoCaja.objects.filter(monto_deposito__gt=0)
    for mov in qs.iterator(chunk_size=500):
        if TransferenciaMovimientoCaja.objects.filter(movimiento_id=mov.id).exists():
            continue
        TransferenciaMovimientoCaja.objects.create(
            movimiento_id=mov.id,
            monto=mov.monto_deposito or 0,
            destino=(mov.destino_deposito or '')[:50],
            fecha=mov.fecha_transferencia,
            referencia='',
            orden=0,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0237_cupontarjetamovimientocaja'),
    ]

    operations = [
        migrations.CreateModel(
            name='TransferenciaMovimientoCaja',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('monto', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('destino', models.CharField(blank=True, help_text='cuenta_X, galicia, mp, etc.', max_length=50)),
                ('fecha', models.DateField(blank=True, help_text='Fecha real del banco para este cupón/transferencia.', null=True, verbose_name='Fecha de transferencia')),
                ('referencia', models.CharField(blank=True, help_text='Nº de cupón / referencia opcional', max_length=64)),
                ('orden', models.PositiveSmallIntegerField(default=0)),
                ('movimiento', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='transferencias',
                    to='inmobiliaria.movimientocaja',
                )),
            ],
            options={
                'verbose_name': 'Transferencia de movimiento',
                'verbose_name_plural': 'Transferencias de movimiento',
                'db_table': 'inmobiliaria_transferenciamovimientocaja',
                'ordering': ['orden', 'id'],
            },
        ),
        migrations.RunPython(forwards_migrar_transferencia_legacy, migrations.RunPython.noop),
    ]
