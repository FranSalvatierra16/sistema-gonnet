from django.db import migrations, models


def marcar_movimientos_de_gastos_reciclables(apps, schema_editor):
    GastoOficina = apps.get_model('inmobiliaria', 'GastoOficina')
    MovimientoCaja = apps.get_model('inmobiliaria', 'MovimientoCaja')
    ids = list(
        GastoOficina.objects.filter(reciclable=True, movimiento_caja__isnull=False)
        .values_list('movimiento_caja_id', flat=True)
    )
    if ids:
        MovimientoCaja.objects.filter(id__in=ids).update(reciclable=True)


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0219_liquidacion_productores_cierre'),
    ]

    operations = [
        migrations.AddField(
            model_name='movimientocaja',
            name='reciclable',
            field=models.BooleanField(
                default=False,
                help_text='Se informa aparte en el cierre (no cambia los totales).',
                verbose_name='Gasto reciclable',
            ),
        ),
        migrations.RunPython(marcar_movimientos_de_gastos_reciclables, migrations.RunPython.noop),
    ]
