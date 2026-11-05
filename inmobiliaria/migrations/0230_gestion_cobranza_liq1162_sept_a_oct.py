"""
Colón: Comisión Gestión Cobranzas de liquidación #1162 (Av. Colon 1766 4° E)
pasó con fecha 30/09/2026; debe figurar en octubre.
"""
from calendar import monthrange
from datetime import date, datetime, time

from django.db import migrations
from django.db.models import Q
from django.utils import timezone


ANIO = 2026
LIQ_ID = 1162


def _a_octubre(d):
    if not d:
        return date(ANIO, 10, 1)
    if d.month == 10 and d.year == ANIO:
        return d
    ultimo = monthrange(ANIO, 10)[1]
    # Conserva el día si cabe; si venía del 30/09 → 30/10.
    return date(ANIO, 10, min(d.day, ultimo))


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

    qs = GastoPropietario.objects.filter(
        sucursal_id=suc.id,
        liquidacion_id=LIQ_ID,
    ).filter(
        Q(concepto_caja_id='19')
        | Q(descripcion__icontains='gestion cobran')
        | Q(descripcion__icontains='gestión cobran')
    )

    for g in qs:
        cid = str(getattr(g, 'concepto_caja_id', None) or '').strip()
        desc = (getattr(g, 'descripcion', None) or '').lower()
        if cid != '19' and 'gestion cobran' not in desc and 'gestión cobran' not in desc:
            continue

        fe = g.fecha_gasto
        if not fe and g.fecha_creacion:
            fc = g.fecha_creacion
            fe = fc.date() if hasattr(fc, 'date') else fc
        if not fe or fe.year != ANIO or fe.month != 9:
            continue

        nueva = _a_octubre(fe)
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
            if d_local.month == 9 and d_local.year == ANIO:
                t = local.time() if hasattr(local, 'time') else time(16, 29)
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


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0229_gestion_cobranza_colon_oct_a_nov'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
