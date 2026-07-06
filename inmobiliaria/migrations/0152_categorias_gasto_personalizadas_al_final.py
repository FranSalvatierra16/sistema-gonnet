# Raíces personalizadas (ej. «Gastos Oscar») al final del árbol, no arriba con orden=0.

from django.db import migrations


def reubicar_raices_personalizadas(apps, schema_editor):
    CategoriaGastoOficina = apps.get_model('inmobiliaria', 'CategoriaGastoOficina')

    raices_cierre = {
        'sueldos',
        'gastos generales',
        'autos',
        'publicidad',
        'mantenimiento deptos',
        'comisiones vendedores',
        'vales',
        'gastos contables e impuestos',
        'ingresos',
    }
    raices_legacy = {'servicios', 'inmueble oficina', 'gastos contables'}

    sucursal_ids = (
        CategoriaGastoOficina.objects.filter(parent__isnull=True)
        .values_list('sucursal_id', flat=True)
        .distinct()
    )
    for sucursal_id in sucursal_ids:
        raices = list(
            CategoriaGastoOficina.objects.filter(
                sucursal_id=sucursal_id,
                parent__isnull=True,
            )
        )
        oficiales = [
            r
            for r in raices
            if (r.nombre or '').strip().lower() in raices_cierre
            or (r.nombre or '').strip().lower() in raices_legacy
        ]
        personalizadas = sorted(
            [r for r in raices if r not in oficiales],
            key=lambda x: x.id,
        )
        if not personalizadas:
            continue

        max_orden = max((r.orden for r in oficiales), default=-1)
        next_orden = max_orden + 1
        for raiz in personalizadas:
            if raiz.orden != next_orden:
                raiz.orden = next_orden
                raiz.save(update_fields=['orden'])
            next_orden += 1


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0151_liquidaciones_canceladas_reservas_anuladas'),
    ]

    operations = [
        migrations.RunPython(reubicar_raices_personalizadas, migrations.RunPython.noop),
    ]
