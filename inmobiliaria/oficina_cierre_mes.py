"""Cierre del mes de oficina: deja fijos el detalle de deptos, productores y el cierre."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.db import transaction


class _PropRef:
    def __init__(self, pk):
        self.id = pk


def _a_json(val):
    if isinstance(val, Decimal):
        return {'$d': str(val)}
    if isinstance(val, datetime):
        return {'$dt': val.isoformat()}
    if isinstance(val, date):
        return {'$dte': val.isoformat()}
    if isinstance(val, dict):
        return {str(k): _a_json(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_a_json(v) for v in val]
    if val is None or isinstance(val, (str, int, float, bool)):
        return val
    pk = getattr(val, 'pk', None)
    if pk is not None and hasattr(val, '_meta'):
        return {'$id': pk}
    return None


def _desde_json(val):
    if isinstance(val, dict):
        if set(val.keys()) == {'$d'}:
            return Decimal(val['$d'])
        if set(val.keys()) == {'$dte'}:
            return date.fromisoformat(val['$dte'])
        if set(val.keys()) == {'$dt'}:
            return datetime.fromisoformat(val['$dt'])
        if set(val.keys()) == {'$id'}:
            return _PropRef(val['$id'])
        return {k: _desde_json(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_desde_json(v) for v in val]
    return val


def cierre_oficina_mes(sucursal, anio, mes):
    from inmobiliaria.models import CierreOficinaMes

    if not sucursal:
        return None
    return (
        CierreOficinaMes.objects.filter(sucursal=sucursal, anio=anio, mes=mes)
        .select_related('usuario_cierre')
        .first()
    )


def _preparar_reporte_deptos(reporte):
    out = dict(reporte)
    filas = []
    for fila in reporte.get('filas') or []:
        g = dict(fila)
        prop = g.pop('propiedad', None)
        g['propiedad_id'] = getattr(prop, 'pk', None) or getattr(prop, 'id', None)
        filas.append(g)
    out['filas'] = filas
    return out


def _restaurar_reporte_deptos(data):
    reporte = _desde_json(data or {})
    for fila in reporte.get('filas') or []:
        pid = fila.get('propiedad_id')
        if pid is not None and not isinstance(fila.get('propiedad'), _PropRef):
            fila['propiedad'] = _PropRef(pid)
    return reporte


def _preparar_resumen(resumen):
    data = dict(resumen)
    data.pop('sucursal', None)
    return data


@transaction.atomic
def cerrar_oficina_mes(sucursal, anio, mes, usuario=None):
    """Foto del cierre y de departamentos, y cierra la liquidación de productores."""
    from inmobiliaria.models import CierreOficinaMes
    from inmobiliaria.oficina_liquidacion_productores import cerrar_liquidacion_productores
    from inmobiliaria.oficina_reporte_deptos import construir_reporte_mensual_deptos_oficina
    from inmobiliaria.oficina_resumen import construir_resumen_cierre

    existente = cierre_oficina_mes(sucursal, anio, mes)
    if existente:
        cerrar_liquidacion_productores(sucursal, anio, mes, usuario=usuario)
        return existente, False

    cerrar_liquidacion_productores(sucursal, anio, mes, usuario=usuario)
    resumen = construir_resumen_cierre(sucursal, anio, mes)
    reporte = construir_reporte_mensual_deptos_oficina(sucursal, anio, mes)
    cierre = CierreOficinaMes.objects.create(
        sucursal=sucursal,
        anio=anio,
        mes=mes,
        resumen=_a_json(_preparar_resumen(resumen)),
        reporte_deptos=_a_json(_preparar_reporte_deptos(reporte)),
        usuario_cierre=usuario if getattr(usuario, 'pk', None) else None,
    )
    return cierre, True


@transaction.atomic
def reabrir_oficina_mes(sucursal, anio, mes):
    from inmobiliaria.models import CierreOficinaMes
    from inmobiliaria.oficina_liquidacion_productores import reabrir_liquidacion_productores

    borrados, _ = CierreOficinaMes.objects.filter(
        sucursal=sucursal, anio=anio, mes=mes
    ).delete()
    reabrir_liquidacion_productores(sucursal, anio, mes)
    return borrados > 0


def resumen_desde_cierre(cierre, sucursal):
    data = _desde_json(cierre.resumen or {})
    data['sucursal'] = sucursal
    return data


def reporte_deptos_desde_cierre(cierre):
    return _restaurar_reporte_deptos(cierre.reporte_deptos or {})
