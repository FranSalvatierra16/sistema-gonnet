"""
Corrige 0229/0231: solo debían pasar a noviembre las liquidaciones de las fotos.

1) Todo lo demás de gestión cobranza Colón que quedó en noviembre vuelve a octubre.
2) Las de las fotos se aseguran en noviembre.
"""
from calendar import monthrange
from datetime import date, datetime, time

from django.db import migrations
from django.db.models import Q
from django.utils import timezone


ANIO = 2026

# Solo las de las fotos (octubre → noviembre).
LIQ_IDS_NOVIEMBRE = frozenset({
    # Primera foto
    1307, 1308, 1309, 1310, 1312, 1313, 1317, 1318, 1325, 1328, 1330,
    1334, 1335, 1336, 1337, 1338, 1339, 1340, 1343, 1345, 1347, 1348,
    1362, 1363, 1364,
    # Foto siguiente (resto octubre)
    1365, 1366, 1367, 1368, 1369, 1371, 1373, 1375, 1376, 1377,
    1537, 1539, 1545,
})


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


def _cambiar_mes(d, mes):
    if not d or d.year != ANIO:
        return d
    ultimo = monthrange(ANIO, mes)[1]
    return date(ANIO, mes, min(d.day, ultimo))


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
        if d_local.year == ANIO and d_local.month in (10, 11):
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

    qs = (
        GastoPropietario.objects.filter(
            Q(sucursal_id=suc.id) | Q(liquidacion__sucursal_id=suc.id)
        )
        .filter(
            Q(concepto_caja_id='19')
            | Q(descripcion__icontains='gestion cobran')
            | Q(descripcion__icontains='gestión cobran')
        )
        .distinct()
    )

    for g in qs.iterator(chunk_size=200):
        if not _es_gestion(g):
            continue
        fe = _fecha_efectiva(g)
        if not fe or fe.year != ANIO:
            continue

        liq = g.liquidacion_id
        en_foto = liq in LIQ_IDS_NOVIEMBRE

        if en_foto:
            # Deben quedar en noviembre.
            if fe.month == 11:
                continue
            if fe.month == 10:
                _actualizar(GastoPropietario, g, _cambiar_mes(fe, 11))
            continue

        # No estaban en las fotos: si quedaron en noviembre por 0229/0231, volver a octubre.
        if fe.month == 11:
            _actualizar(GastoPropietario, g, _cambiar_mes(fe, 10))


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0231_gestion_cobranza_colon_oct_a_nov_resto'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
