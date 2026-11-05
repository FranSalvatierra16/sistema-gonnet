"""
Colón: pasa Comisión Gestión Cobranzas (concepto 19) de octubre 2026 a noviembre
(mismo día), para que figuren en el mes 11 (caja / liquidación productores).
"""
from calendar import monthrange
from datetime import date, datetime, time

from django.db import migrations
from django.db.models import Q
from django.utils import timezone


ANIO = 2026


def _mover_a_noviembre(d):
    if not d or d.month != 10 or d.year != ANIO:
        return d
    ultimo = monthrange(d.year, 11)[1]
    return date(d.year, 11, min(d.day, ultimo))


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
        GastoPropietario.objects.filter(sucursal_id=suc.id)
        .filter(
            Q(concepto_caja_id='19')
            | Q(descripcion__icontains='gestion cobran')
            | Q(descripcion__icontains='gestión cobran')
        )
        .filter(
            Q(fecha_gasto__gte=desde, fecha_gasto__lte=hasta)
            | Q(
                fecha_gasto__isnull=True,
                fecha_creacion__date__gte=desde,
                fecha_creacion__date__lte=hasta,
            )
        )
    )

    for g in qs.iterator(chunk_size=200):
        cid = str(getattr(g, 'concepto_caja_id', None) or '').strip()
        desc = (getattr(g, 'descripcion', None) or '').lower()
        if cid != '19' and 'gestion cobran' not in desc and 'gestión cobran' not in desc:
            continue

        fe = g.fecha_gasto
        if not fe and g.fecha_creacion:
            fc = g.fecha_creacion
            fe = fc.date() if hasattr(fc, 'date') else fc
        nueva = _mover_a_noviembre(fe)
        if not fe or not nueva or nueva == fe:
            continue

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
            if d_local.month == 10 and d_local.year == ANIO:
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


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0228_comisionvendedor_porcentaje_max_digits'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
