from django.db import migrations


def crear_categoria_vales(apps, schema_editor):
    Sucursal = apps.get_model('inmobiliaria', 'Sucursal')
    CategoriaGastoOficina = apps.get_model('inmobiliaria', 'CategoriaGastoOficina')

    for sucursal in Sucursal.objects.all():
        raiz = CategoriaGastoOficina.objects.filter(
            sucursal=sucursal,
            parent__isnull=True,
            nombre__iexact='Vales',
        ).first()
        if not raiz:
            orden = CategoriaGastoOficina.objects.filter(
                sucursal=sucursal,
                parent__isnull=True,
            ).count()
            raiz = CategoriaGastoOficina.objects.create(
                sucursal=sucursal,
                nombre='Vales',
                orden=orden,
                activa=True,
            )
        if not CategoriaGastoOficina.objects.filter(sucursal=sucursal, parent=raiz).exists():
            CategoriaGastoOficina.objects.create(
                sucursal=sucursal,
                parent=raiz,
                nombre='Productores',
                orden=0,
                activa=True,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0128_gasto_oficina_vendedor'),
    ]

    operations = [
        migrations.RunPython(crear_categoria_vales, migrations.RunPython.noop),
    ]
