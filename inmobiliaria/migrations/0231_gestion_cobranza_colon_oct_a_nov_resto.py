"""
Colón: resto de Comisión Gestión Cobranzas aún en octubre → noviembre 2026.

Incluye las liquidaciones visibles en el listado (#1364–#1545, etc.) por si
quedaron fuera de 0229 (p. ej. sucursal nula en el gasto).
"""
from calendar import monthrange
from datetime import date, datetime, time

from django.db import migrations
from django.db.models import Q
from django.utils import timezone


ANIO = 2026

# Liquidaciones de la foto (21–28/10) + margen por si hay más del mismo lote.
LIQ_IDS = (
    1364, 1365, 1366, 1367, 1368, 1369, 1371, 1373, 1375, 1376, 1377,
    1537, 1539, 1545,
)


def _mover_a_noviembre(d):
    if not d or d.year != ANIO or d.month != 10:
        return d
    ultimo = monthrange(d.year, 11)[1]
    return date(d.year, 11, min(d.day, ultimo))


def _es_gestion(g):
    cid = str(getattr(g, 'concepto_caja_id', None) or '').strip()
    if cid == '19':
        return True
    desc = (getattr(g, 'descripcion', None) or '').lower()
    return 'gestion cobran' in desc or 'gestión cobran' in desc


def _fecha_efectiva(g):
    if g.fecha_gasto:
        return g.fecha_gasto
    fc = g.fecha_creacion
    if not fc:
        return None
    return fc.date() if hasattr(fc, 'date') else fc


def _actualizar(GastoPropietario, g, nueva):
    updates = {'fecha_gasto': nueva}
    fc = g.fecha_creacion
    if fc:
        local = fc
        if timezone.is_aware(fc):
            try:
                local = timezone.localtime(fc)
            except Exception:
                local = fc
        d_local = local.date() if hasattr(local, 'date') else local
        if d_local.year == ANIO and d_local.month == 10:
            t = local.time() if hasattr(local, 'time') else time(12, 0)
            nuevo_dt = datetime.combine(nueva, t)
            if timezone.is_aware(fc):
                try:
                    nuevo_dt = timezone.make_aware(
                        nuevo_dt, timezone.get_current_timezone()
                    )
                except Exception:
                    pass
            updates['fecha_creacion'] = nuevo_dt
    GastoPropietario.objects.filter(pk=g.pk).update(**updates)


def forwards(apps, schema_editor):
    Sucursal = apps.get_model('inmobiliaria', 'Sucursal')
    GastoPropietario = apps.get_model('inmobiliaria', 'GastoPropietario')

    suc = (
        Sucursal.objects.filter(nombre__icontains='Colon')
        .order_by('id')
        .first()
    )
    if not suc:
        return

    desde = date(ANIO, 10, 1)
    hasta = date(ANIO, 10, 31)

    qs = (
        GastoPropietario.objects.filter(
            Q(sucursal_id=suc.id) | Q(liquidacion__sucursal_id=suc.id)
        )
        .filter(
            Q(concepto_caja_id='19')
            | Q(descripcion__icontains='gestion cobran')
            | Q(descripcion__icontains='gestión cobran')
            | Q(liquidacion_id__in=LIQ_IDS)
        )
        .filter(
            Q(fecha_gasto__gte=desde, fecha_gasto__lte=hasta)
            | Q(
                fecha_gasto__isnull=True,
                fecha_creacion__date__gte=desde,
                fecha_creacion__date__lte=hasta,
            )
            | Q(liquidacion_id__in=LIQ_IDS)
        )
        .distinct()
    )

    for g in qs.iterator(chunk_size=200):
        if not _es_gestion(g) and g.liquidacion_id not in LIQ_IDS:
            continue
        if not _es_gestion(g):
            continue
        fe = _fecha_efectiva(g)
        if not fe or fe.year != ANIO or fe.month != 10:
            continue
        nueva = _mover_a_noviembre(fe)
        if not nueva or nueva == fe:
            continue
        _actualizar(GastoPropietario, g, nueva)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0230_gestion_cobranza_liq1162_sept_a_oct'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
