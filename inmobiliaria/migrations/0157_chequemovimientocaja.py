from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


def backfill_cheques(apps, schema_editor):
    MovimientoCaja = apps.get_model('inmobiliaria', 'MovimientoCaja')
    ChequeMovimientoCaja = apps.get_model('inmobiliaria', 'ChequeMovimientoCaja')
    qs = MovimientoCaja.objects.filter(monto_cheque__gt=0)
    for mov in qs.iterator():
        if ChequeMovimientoCaja.objects.filter(movimiento_id=mov.id).exists():
            continue
        ChequeMovimientoCaja.objects.create(
            movimiento_id=mov.id,
            monto=mov.monto_cheque or Decimal('0'),
            numero=(mov.cheque_numero or '')[:32],
            banco=(mov.cheque_banco or '')[:100],
            fecha_vencimiento=mov.cheque_fecha_vencimiento,
            orden=0,
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0156_reserva_ocultar_historial_inquilino'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChequeMovimientoCaja',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('monto', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('numero', models.CharField(blank=True, max_length=32)),
                ('banco', models.CharField(blank=True, max_length=100)),
                ('fecha_vencimiento', models.DateField(blank=True, null=True)),
                ('orden', models.PositiveSmallIntegerField(default=0)),
                (
                    'movimiento',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='cheques',
                        to='inmobiliaria.movimientocaja',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Cheque de movimiento',
                'verbose_name_plural': 'Cheques de movimiento',
                'db_table': 'inmobiliaria_chequemovimientocaja',
                'ordering': ['orden', 'id'],
            },
        ),
        migrations.RunPython(backfill_cheques, noop_reverse),
    ]
