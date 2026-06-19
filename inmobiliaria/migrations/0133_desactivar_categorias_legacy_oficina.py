from django.db import migrations


def desactivar_legacy_todas_sucursales(apps, schema_editor):
    Sucursal = apps.get_model('inmobiliaria', 'Sucursal')
    from inmobiliaria.oficina_gastos import (
        asegurar_estructura_cierre_oficina,
        desactivar_categorias_legacy_oficina,
    )

    for sucursal in Sucursal.objects.all():
        asegurar_estructura_cierre_oficina(sucursal)
        desactivar_categorias_legacy_oficina(sucursal)


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0132_categoria_gasto_vendedor_cierre_oficina'),
    ]

    operations = [
        migrations.RunPython(desactivar_legacy_todas_sucursales, migrations.RunPython.noop),
    ]
