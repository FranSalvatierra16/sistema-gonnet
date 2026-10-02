from django.db import migrations


def mover_a_pago_iibb(apps, schema_editor):
    CategoriaGastoOficina = apps.get_model('inmobiliaria', 'CategoriaGastoOficina')
    GastoOficina = apps.get_model('inmobiliaria', 'GastoOficina')

    origen = CategoriaGastoOficina.objects.filter(
        parent__nombre__iexact='Ingresos',
        nombre__iexact='Gastos bancarios',
    )
    for cat in origen:
        destino = (
            CategoriaGastoOficina.objects.filter(
                sucursal_id=cat.sucursal_id,
                activa=True,
                parent__nombre__iexact='Gastos contables e impuestos',
                nombre__iexact='Pago IIBB',
            )
            .order_by('id')
            .first()
        )
        if not destino:
            continue
        GastoOficina.objects.filter(
            categoria=cat,
            observaciones__icontains='Vinculado automáticamente',
        ).update(categoria=destino)


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0210_tasacion'),
    ]

    operations = [
        migrations.RunPython(mover_a_pago_iibb, migrations.RunPython.noop),
    ]
