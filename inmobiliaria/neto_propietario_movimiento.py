"""
Neto al propietario por movimiento de caja (ingreso), alineado con liquidaciones:
- Si hay LiquidacionPropietario vinculada (no cancelada), se usa su monto_a_pagar.
- Si no: reparto como en operaciones pendientes — precio_toma (o precio_dia_toma) /
  precio_por_dia sobre el monto del movimiento; sin toma válida, 70% propietario / 30% oficina.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone

from inmobiliaria.models.caja import TipoMovimientoCajaEnum
from inmobiliaria.models.propiedad import Precio
from inmobiliaria.precio_temporada_reserva import (
    rango_vacaciones_invierno_sucursal,
    tipo_precio_para_dia_reserva,
)

PCT_PROPIETARIO_SIN_TOMA = Decimal('70')


def obtener_tipo_precio_para_fecha(d, sucursal=None) -> str:
    """Misma lógica que en views (operaciones pendientes / liquidaciones)."""
    rango = rango_vacaciones_invierno_sucursal(sucursal)
    return tipo_precio_para_dia_reserva(d, rango)


def monto_medios_movimiento_decimal(mov) -> Decimal:
    return (
        Decimal(str(mov.monto_efectivo or 0))
        + Decimal(str(mov.monto_cheque or 0))
        + Decimal(str(mov.monto_tarjeta or 0))
        + Decimal(str(mov.monto_deposito or 0))
    )


def _q(v: Decimal) -> Decimal:
    return v.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _precio_toma_de_registro(precio) -> Decimal:
    """precio_toma; si está vacío, precio_dia_toma."""
    if not precio:
        return Decimal('0')
    pt = Decimal(str(precio.precio_toma or 0))
    if pt <= 0 and getattr(precio, 'precio_dia_toma', None):
        pt = Decimal(str(precio.precio_dia_toma or 0))
    return pt if pt > 0 else Decimal('0')


def reparto_liquidacion_reserva_por_dia(reserva):
    """
    Reparto sugerido para alquiler por día:

    - Propietario = suma de (precio_toma o precio_dia_toma) de cada día de la reserva.
    - Inmobiliaria = precio_total − propietario.
    - Si ningún día tiene toma: 70% propietario / 30% inmobiliaria.

    No usa ``propiedad.porcentaje_propietario`` (p. ej. el 85% por defecto de ficha).
    Retorna (total, monto_propietario, monto_inmobiliaria, hay_toma).
    """
    total = _q(Decimal(str(getattr(reserva, 'precio_total', None) or 0)))
    if total <= 0:
        return total, Decimal('0'), Decimal('0'), False

    propiedad = getattr(reserva, 'propiedad', None)
    fecha_inicio = getattr(reserva, 'fecha_inicio', None)
    fecha_fin = getattr(reserva, 'fecha_fin', None)
    if not propiedad or not fecha_inicio or not fecha_fin:
        prop = _q(total * PCT_PROPIETARIO_SIN_TOMA / Decimal('100'))
        return total, prop, _q(total - prop), False

    dias = (fecha_fin - fecha_inicio).days
    if dias <= 0:
        dias = 1

    sucursal = getattr(reserva, 'sucursal', None) or getattr(propiedad, 'sucursal', None)
    rango = rango_vacaciones_invierno_sucursal(sucursal)
    precios = {
        p.tipo_precio: p
        for p in Precio.objects.filter(propiedad=propiedad)
    }

    monto_propietario = Decimal('0')
    hay_toma = False
    for i in range(dias):
        fecha_actual = fecha_inicio + timedelta(days=i)
        tipo = tipo_precio_para_dia_reserva(fecha_actual, rango)
        toma = _precio_toma_de_registro(precios.get(tipo))
        if toma > 0:
            hay_toma = True
            monto_propietario += toma

    if hay_toma and monto_propietario > 0:
        prop = _q(monto_propietario)
        if prop > total:
            prop = total
        return total, prop, _q(total - prop), True

    prop = _q(total * PCT_PROPIETARIO_SIN_TOMA / Decimal('100'))
    return total, prop, _q(total - prop), False


def _fecha_movimiento(mov) -> date:
    fd = mov.fecha
    if isinstance(fd, datetime):
        if fd.tzinfo is not None:
            return timezone.localtime(fd).date()
        return fd.date()
    if isinstance(fd, date):
        return fd
    return date.today()


def primer_dia_mes_movimiento(mov) -> date:
    """Primer día del mes calendario del movimiento (misma zona horaria que el neto)."""
    d = _fecha_movimiento(mov)
    return date(d.year, d.month, 1)


def neto_propietario_movimiento(mov, liq_by_mov_id: dict, precios_por_propiedad: dict) -> Decimal:
    """
    mov: MovimientoCaja con propiedad cargada si aplica.
    liq_by_mov_id: id movimiento -> LiquidacionPropietario (opcional).
    precios_por_propiedad: propiedad_id -> lista de Precio.
    """
    if mov.tipo != TipoMovimientoCajaEnum.INGRESO:
        return Decimal('0')

    liq = liq_by_mov_id.get(mov.id)
    if liq is not None and getattr(liq, 'estado', '') != 'cancelada':
        return _q(Decimal(str(liq.monto_a_pagar or 0)))

    if not mov.propiedad_id:
        return Decimal('0')

    m_total = monto_medios_movimiento_decimal(mov)
    if m_total <= 0:
        return Decimal('0')

    prop = getattr(mov, 'propiedad', None)
    if prop is None:
        return Decimal('0')

    fecha_d = _fecha_movimiento(mov)
    _pk = str(mov.propiedad_id)
    precios_list = precios_por_propiedad.get(_pk) or []
    sucursal = getattr(mov, 'sucursal', None)
    tipo = obtener_tipo_precio_para_fecha(fecha_d, sucursal=sucursal)
    precio = None
    for p in precios_list:
        if p.tipo_precio == tipo:
            precio = p
            break
    if precio is None:
        for p in precios_list:
            if p.precio_por_dia:
                precio = p
                break

    if precio is not None:
        precio_por_dia = Decimal(str(precio.precio_por_dia or 0))
        if precio_por_dia > 0:
            pt = Decimal(str(precio.precio_toma or 0))
            if pt <= 0 and getattr(precio, 'precio_dia_toma', None):
                pt = Decimal(str(precio.precio_dia_toma or 0))
            if pt > 0:
                share = pt / precio_por_dia
                if share > 1:
                    share = Decimal('1')
                return _q(m_total * share)

    # Sin toma: siempre 70/30 (no usar porcentaje_propietario de la ficha).
    return _q(m_total * PCT_PROPIETARIO_SIN_TOMA / Decimal('100'))


def precios_por_propiedad_ids(propiedad_ids) -> dict:
    """propiedad_id (str, PK de Propiedad) -> lista de Precio."""
    ids = [str(x) for x in propiedad_ids if x is not None and str(x).strip() != '']
    if not ids:
        return {}
    out: dict[str, list] = {i: [] for i in ids}
    for pr in Precio.objects.filter(propiedad_id__in=ids):
        k = str(pr.propiedad_id)
        out.setdefault(k, []).append(pr)
    return out
