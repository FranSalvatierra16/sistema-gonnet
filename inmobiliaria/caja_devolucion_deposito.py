"""Devolución de depósito en garantía desde caja (egreso por operación/reserva)."""
from __future__ import annotations

import json
import re
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from inmobiliaria.decimal_utils import parse_decimal_monto
from inmobiliaria.models.caja import MovimientoCaja, TipoMovimientoCajaEnum


def es_concepto_devolucion_deposito(concepto_row=None, *, concepto_id: str = '', nombre: str = '') -> bool:
    """True si el concepto de caja es devolución de depósito en garantía (D.D.G.)."""
    if concepto_row is not None:
        concepto_id = str(getattr(concepto_row, 'id', '') or '')
        nombre = str(getattr(concepto_row, 'nombre', '') or '')
    texto = f'{concepto_id} {nombre}'.lower()
    return 'devoluc' in texto and (
        'deposit' in texto or 'depósit' in texto or 'garant' in texto or 'ddg' in texto
    )


def _parse_conceptos_movimiento(movimiento) -> list:
    raw = (getattr(movimiento, 'concepto_detalle', None) or '').strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and isinstance(parsed.get('conceptos'), list):
                return parsed['conceptos']
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    conc = (getattr(movimiento, 'concepto', None) or '').strip()
    if '|CONCEPTOS:' in conc:
        trozo = conc.split('|CONCEPTOS:', 1)[1]
        out = []
        for item in [x for x in trozo.split('|') if x.strip()]:
            parts = item.split(':')
            if len(parts) >= 3:
                out.append({'id': parts[0].strip(), 'nombre': parts[1].strip(), 'importe': parts[2].strip()})
        return out
    return []


def _movimiento_vinculado_reserva(movimiento, reserva_id: int) -> bool:
    rid = int(reserva_id)
    conc = (getattr(movimiento, 'concepto', None) or '')
    if re.search(rf'Operaci[oó]n\s*#?\s*{rid}\b', conc, re.IGNORECASE):
        return True
    if re.search(rf'Reserva\s*#?\s*{rid}\b', conc, re.IGNORECASE):
        return True
    if re.search(rf'Devoluci[oó]n dep[oó]sito operaci[oó]n\s*{rid}\b', conc, re.IGNORECASE):
        return True
    raw = (getattr(movimiento, 'concepto_detalle', None) or '')
    if raw and str(rid) in raw and (
        f'"devolucion_deposito_operacion_id": {rid}' in raw
        or f'"devolucion_deposito_operacion_id":{rid}' in raw
        or f'"reserva_id": {rid}' in raw
        or f'"reserva_id":{rid}' in raw
        or f'"operacion_id": {rid}' in raw
        or f'"operacion_id":{rid}' in raw
    ):
        return True
    return False


def movimientos_reserva(reserva, *, tipo=None):
    qs = MovimientoCaja.objects.filter(
        sucursal=reserva.sucursal,
        propiedad=reserva.propiedad,
        fecha_eliminacion__isnull=True,
    )
    if tipo:
        qs = qs.filter(tipo=tipo)
    rid = int(reserva.id)
    return [m for m in qs.order_by('-fecha', '-id') if _movimiento_vinculado_reserva(m, rid)]


def movimiento_tiene_concepto_10(movimiento) -> bool:
    for item in _parse_conceptos_movimiento(movimiento):
        cid = str(item.get('id') or item.get('codigo') or '').strip()
        if cid == '10':
            return True
    conc = (getattr(movimiento, 'concepto', None) or '').lower()
    if 'concepto 10' in conc or (
        'deposito' in conc or 'depósito' in conc
    ) and '|10:' in (getattr(movimiento, 'concepto', None) or ''):
        return True
    return False


def _ingresos_propiedad_en_ventana_reserva(reserva):
    hoy = timezone.now().date()
    desde = (reserva.fecha_inicio or hoy) - timedelta(days=60)
    hasta = (reserva.fecha_fin or hoy) + timedelta(days=60)
    return MovimientoCaja.objects.filter(
        sucursal=reserva.sucursal,
        propiedad=reserva.propiedad,
        tipo=TipoMovimientoCajaEnum.INGRESO,
        fecha_eliminacion__isnull=True,
        fecha__date__gte=desde,
        fecha__date__lte=hasta,
    ).order_by('-fecha', '-id')


def monto_deposito_cobrado_reserva(reserva) -> Decimal:
    total = Decimal('0')
    vistos: set[int] = set()
    for mov in movimientos_reserva(reserva, tipo=TipoMovimientoCajaEnum.INGRESO):
        vistos.add(int(mov.id))
        for item in _parse_conceptos_movimiento(mov):
            cid = str(item.get('id') or item.get('codigo') or '').strip()
            if cid != '10':
                continue
            total += parse_decimal_monto(item.get('importe'))
    if total > Decimal('0'):
        return total
    # Fallback: ingresos con concepto 10 en la propiedad cerca de las fechas de la reserva
    for mov in _ingresos_propiedad_en_ventana_reserva(reserva):
        if int(mov.id) in vistos:
            continue
        sub = Decimal('0')
        for item in _parse_conceptos_movimiento(mov):
            cid = str(item.get('id') or item.get('codigo') or '').strip()
            if cid != '10':
                continue
            sub += parse_decimal_monto(item.get('importe'))
        if sub > Decimal('0'):
            total += sub
    return total


def deposito_estado_reserva(reserva) -> str:
    if not reserva or not Decimal(str(reserva.deposito_garantia or 0)):
        return 'no_aplica'
    if monto_deposito_cobrado_reserva(reserva) > Decimal('0.05'):
        return 'pagado'
    for mov in movimientos_reserva(reserva, tipo=TipoMovimientoCajaEnum.INGRESO):
        if movimiento_tiene_concepto_10(mov):
            return 'pagado'
    return 'pendiente'


def ya_devolvio_deposito_reserva(reserva) -> bool:
    rid = int(reserva.id)
    qs = MovimientoCaja.objects.filter(
        sucursal=reserva.sucursal,
        tipo=TipoMovimientoCajaEnum.EGRESO,
        fecha_eliminacion__isnull=True,
    )
    patrones = (
        f'Devolución depósito operación {rid}',
        f'Devolucion deposito operacion {rid}',
        f'"devolucion_deposito_operacion_id": {rid}',
        f'"devolucion_deposito_operacion_id":{rid}',
    )
    q = Q()
    for p in patrones:
        q |= Q(concepto__icontains=p) | Q(concepto_detalle__icontains=p)
    if qs.filter(q).exists():
        return True
    return any(
        _movimiento_vinculado_reserva(m, rid) and es_concepto_devolucion_deposito(nombre=(m.concepto or ''))
        for m in qs.filter(propiedad=reserva.propiedad)
    )


def monto_devolucion_sugerido_reserva(reserva) -> Decimal:
    cobrado = monto_deposito_cobrado_reserva(reserva)
    if cobrado > Decimal('0'):
        return cobrado
    return Decimal(str(reserva.deposito_garantia or 0))


def datos_operacion_reserva_caja(reserva) -> dict:
    deposito_estado = deposito_estado_reserva(reserva)
    monto_sugerido = monto_devolucion_sugerido_reserva(reserva)
    ya_devuelto = ya_devolvio_deposito_reserva(reserva)
    cliente = getattr(reserva, 'cliente', None)
    cliente_txt = ''
    if cliente:
        ap = (getattr(cliente, 'apellido', None) or '').strip()
        nom = (getattr(cliente, 'nombre', None) or '').strip()
        cliente_txt = f'{ap}, {nom}'.strip(', ') if ap or nom else str(cliente)

    prop = reserva.propiedad
    mensajes = []
    if deposito_estado != 'pagado':
        mensajes.append('No se detectó el cobro del depósito (concepto 10) en caja para esta operación.')
    if ya_devuelto:
        mensajes.append('Ya existe un egreso de devolución de depósito para esta operación.')
    if monto_sugerido <= 0:
        mensajes.append('La operación no tiene monto de depósito a devolver.')

    return {
        'tipo': 'reserva',
        'id': int(reserva.id),
        'estado': reserva.estado,
        'fecha_desde': reserva.fecha_inicio.isoformat() if reserva.fecha_inicio else '',
        'fecha_hasta': reserva.fecha_fin.isoformat() if reserva.fecha_fin else '',
        'cliente': cliente_txt,
        'deposito_garantia': float(reserva.deposito_garantia or 0),
        'deposito_cobrado': float(monto_deposito_cobrado_reserva(reserva)),
        'deposito_estado': deposito_estado,
        'deposito_ya_devuelto': ya_devuelto,
        'monto_devolucion_sugerido': float(monto_sugerido),
        'puede_devolver': (
            deposito_estado == 'pagado'
            and not ya_devuelto
            and monto_sugerido > 0
        ),
        'mensaje': ' '.join(mensajes),
        'propiedad': {
            'id': prop.id,
            'direccion': prop.direccion or '',
            'ubicacion': getattr(prop, 'ubicacion', None) or '',
            'piso': (prop.piso or '').strip(),
            'departamento': (prop.departamento or '').strip(),
        },
    }


def validar_devolucion_deposito_caja(reserva, monto_total: Decimal) -> str | None:
    """None si OK; mensaje de error si no se puede registrar."""
    if not reserva:
        return 'Operación no encontrada.'
    if ya_devolvio_deposito_reserva(reserva):
        return f'Ya se registró la devolución del depósito de la operación #{reserva.id}.'
    if deposito_estado_reserva(reserva) != 'pagado':
        return (
            f'No se puede devolver el depósito de la operación #{reserva.id}: '
            'no figura cobrado en caja (concepto 10).'
        )
    sugerido = monto_devolucion_sugerido_reserva(reserva)
    if sugerido <= Decimal('0'):
        return 'La operación no tiene depósito a devolver.'
    if monto_total <= Decimal('0'):
        return 'El importe del egreso debe ser mayor a cero.'
    return None


def concepto_guardado_devolucion_deposito(reserva, detalles: str = '') -> str:
    base = f'Devolución depósito operación {reserva.id} - {(reserva.propiedad.direccion or "").strip()}'
    extra = (detalles or '').strip()
    txt = f'{base} — {extra}' if extra else base
    return txt[:200]


def payload_concepto_detalle_devolucion(reserva_id: int) -> str:
    return json.dumps({'devolucion_deposito_operacion_id': int(reserva_id)}, ensure_ascii=False)
