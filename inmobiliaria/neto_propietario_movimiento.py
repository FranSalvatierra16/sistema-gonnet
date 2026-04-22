"""
Neto al propietario por movimiento de caja (ingreso), alineado con liquidaciones:
- Si hay LiquidacionPropietario vinculada (no cancelada), se usa su monto_a_pagar.
- Si no: reparto como en operaciones pendientes — precio_toma / precio_por_dia sobre el
  monto del movimiento, o porcentaje_propietario de la propiedad (si no hay toma válida, 70%).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from django.utils import timezone

from inmobiliaria.models.caja import TipoMovimientoCajaEnum
from inmobiliaria.models.propiedad import Precio


def obtener_tipo_precio_para_fecha(d: date) -> str:
    """Misma lógica que en views (operaciones pendientes / liquidaciones)."""
    if d.month == 1:
        return 'QUINCENA_1_ENERO' if d.day <= 15 else 'QUINCENA_2_ENERO'
    if d.month == 2:
        return 'QUINCENA_1_FEBRERO' if d.day <= 15 else 'QUINCENA_2_FEBRERO'
    if d.month == 3:
        return 'QUINCENA_1_MARZO' if d.day <= 15 else 'QUINCENA_2_MARZO'
    if d.month == 7:
        return 'VACACIONES_INVIERNO'
    if d.month == 12:
        return 'QUINCENA_1_DICIEMBRE' if d.day <= 15 else 'QUINCENA_2_DICIEMBRE'
    return 'TEMPORADA_BAJA'


def monto_medios_movimiento_decimal(mov) -> Decimal:
    return (
        Decimal(str(mov.monto_efectivo or 0))
        + Decimal(str(mov.monto_cheque or 0))
        + Decimal(str(mov.monto_tarjeta or 0))
        + Decimal(str(mov.monto_deposito or 0))
    )


def _q(v: Decimal) -> Decimal:
    return v.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


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
    tipo = obtener_tipo_precio_para_fecha(fecha_d)
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

    pct = getattr(prop, 'porcentaje_propietario', None)
    pct_dec = Decimal('70')
    if pct is not None:
        try:
            pnum = Decimal(str(pct))
            if pnum > 0:
                pct_dec = pnum
        except (InvalidOperation, TypeError, ValueError):
            pct_dec = Decimal('70')
    return _q(m_total * pct_dec / Decimal('100'))


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
