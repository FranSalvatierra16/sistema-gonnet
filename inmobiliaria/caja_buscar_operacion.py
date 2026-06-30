"""Búsqueda unificada de operaciones desde Nuevo movimiento de caja."""
from __future__ import annotations

import re
from decimal import Decimal

from inmobiliaria.caja_devolucion_deposito import (
    concepto_devolucion_deposito_catalogo,
    datos_operacion_reserva_caja,
)
from inmobiliaria.models.caja import MovimientoCaja, TipoMovimientoCajaEnum

_PREFIJO_TIPO_OPERACION = {
    'c': 'contrato',
    'contrato': 'contrato',
    'contr': 'contrato',
    'r': 'reserva',
    'reserva': 'reserva',
    'res': 'reserva',
    'l': 'liquidacion',
    'liquidacion': 'liquidacion',
    'liq': 'liquidacion',
}


def _normalizar_prefijo_tipo_operacion(pref: str) -> str | None:
    p = (pref or '').strip().lower()
    return _PREFIJO_TIPO_OPERACION.get(p)


def parse_numero_operacion_caja(raw: str) -> tuple[int | None, str | None, str | None]:
    """
    Interpreta el campo N° operación de caja.
    Devuelve (pk, tipo_hint, error). tipo_hint: reserva | contrato | liquidacion | None.

    Ejemplos: 300 | C300 | c-300 | contrato:300 | 300R | R300
    """
    s = (raw or '').strip()
    if not s:
        return None, None, 'Ingrese un número de operación'

    m = re.match(
        r'^(?P<pref>contrato|reserva|liquidacion|contr|res|liq|[crl])'
        r'\s*[:\-\#]?\s*(?P<num>\d+)$',
        s,
        re.IGNORECASE,
    )
    if m:
        tipo = _normalizar_prefijo_tipo_operacion(m.group('pref'))
        if tipo:
            return int(m.group('num')), tipo, None

    m = re.match(
        r'^(?P<num>\d+)\s*(?P<pref>contrato|reserva|liquidacion|contr|res|liq|[crl])$',
        s,
        re.IGNORECASE,
    )
    if m:
        tipo = _normalizar_prefijo_tipo_operacion(m.group('pref'))
        if tipo:
            return int(m.group('num')), tipo, None

    if s.isdigit():
        return int(s), None, None

    return None, None, (
        'Formato inválido. Usá el número (ej. 300) o un prefijo: '
        'C300 = contrato, R300 = reserva, L300 = liquidación.'
    )


def _resumen_candidato_operacion_caja(tipo: str, obj) -> dict:
    if tipo == 'reserva':
        op = _enriquecer_reserva(datos_operacion_reserva_caja(obj))
    elif tipo == 'contrato':
        op = datos_operacion_contrato_caja(obj)
    else:
        op = datos_operacion_liquidacion_caja(obj)
    prop = op.get('propiedad') or {}
    return {
        'tipo': tipo,
        'id': op.get('id'),
        'tipo_label': op.get('tipo_label') or tipo,
        'cliente': op.get('cliente') or op.get('propietario') or '',
        'propiedad': prop.get('direccion') or '',
        'fecha_desde': op.get('fecha_desde') or '',
        'fecha_hasta': op.get('fecha_hasta') or '',
    }


def _cliente_reserva(reserva) -> str:
    cli = getattr(reserva, 'cliente', None)
    if not cli:
        return ''
    ap = (getattr(cli, 'apellido', None) or '').strip()
    nom = (getattr(cli, 'nombre', None) or '').strip()
    return f'{ap}, {nom}'.strip(', ') if ap or nom else str(cli)


def _cliente_contrato(contrato) -> str:
    inq = getattr(contrato, 'inquilino', None)
    if not inq:
        return ''
    ap = (getattr(inq, 'apellido', None) or '').strip()
    nom = (getattr(inq, 'nombre', None) or '').strip()
    return f'{ap}, {nom}'.strip(', ') if ap or nom else str(inq)


def _propiedad_dict(prop) -> dict:
    if not prop:
        return {}
    return {
        'id': prop.id,
        'direccion': prop.direccion or '',
        'ubicacion': getattr(prop, 'ubicacion', None) or '',
        'piso': (prop.piso or '').strip(),
        'departamento': (prop.departamento or '').strip(),
    }


def _monto_deposito_cobrado_contrato(contrato) -> Decimal:
    from inmobiliaria.decimal_utils import parse_decimal_monto
    import json

    total = Decimal('0')
    movs = MovimientoCaja.objects.filter(
        sucursal=contrato.sucursal,
        propiedad=contrato.propiedad,
        tipo=TipoMovimientoCajaEnum.INGRESO,
        fecha_eliminacion__isnull=True,
        concepto__icontains=f'Contrato #{contrato.id}',
    )
    for mov in movs:
        raw = (getattr(mov, 'concepto_detalle', None) or '').strip()
        if raw:
            try:
                parsed = json.loads(raw)
                items = parsed.get('conceptos', parsed) if isinstance(parsed, dict) else parsed
                if isinstance(items, list):
                    for it in items:
                        cid = str(it.get('id') or it.get('codigo') or '').strip()
                        if cid == '10':
                            total += parse_decimal_monto(it.get('importe'))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
    return total


def _ya_devolvio_deposito_contrato(contrato) -> bool:
    cid = int(contrato.id)
    from django.db.models import Q

    q = (
        Q(concepto__icontains=f'Devolución depósito contrato {cid}')
        | Q(concepto__icontains=f'Devolucion deposito contrato {cid}')
        | Q(concepto_detalle__icontains=f'"devolucion_deposito_contrato_id": {cid}')
        | Q(concepto_detalle__icontains=f'"devolucion_deposito_contrato_id":{cid}')
    )
    return MovimientoCaja.objects.filter(
        sucursal=contrato.sucursal,
        propiedad=contrato.propiedad,
        tipo=TipoMovimientoCajaEnum.EGRESO,
        fecha_eliminacion__isnull=True,
    ).filter(q).exists()


def datos_operacion_contrato_caja(contrato) -> dict:
    deposito = Decimal(str(contrato.deposito_garantia or 0))
    cobrado = _monto_deposito_cobrado_contrato(contrato)
    ya_devuelto = _ya_devolvio_deposito_contrato(contrato)
    deposito_estado = 'no_aplica'
    if deposito > 0 or cobrado > 0:
        deposito_estado = 'pagado' if cobrado > Decimal('0.05') else 'pendiente'
    monto_sug = cobrado if cobrado > 0 else deposito
    mensajes = []
    if deposito_estado == 'pendiente' and deposito > 0:
        mensajes.append('No se detectó el cobro del depósito (concepto 10) en caja para este contrato.')
    if ya_devuelto:
        mensajes.append('Ya existe un egreso de devolución de depósito para este contrato.')
    vendedor = getattr(contrato, 'vendedor', None)
    vendedor_data = None
    if vendedor:
        vendedor_data = {
            'id': int(vendedor.id),
            'nombre': (getattr(vendedor, 'nombre', None) or '').strip(),
            'apellido': (getattr(vendedor, 'apellido', None) or '').strip(),
        }
    return {
        'tipo': 'contrato',
        'tipo_label': f'Contrato {contrato.duracion_meses} meses',
        'duracion_meses': int(contrato.duracion_meses or 0),
        'id': int(contrato.id),
        'estado': contrato.estado,
        'fecha_desde': contrato.fecha_inicio.isoformat() if contrato.fecha_inicio else '',
        'fecha_hasta': contrato.fecha_fin.isoformat() if contrato.fecha_fin else '',
        'cliente': _cliente_contrato(contrato),
        'deposito_garantia': float(deposito),
        'deposito_cobrado': float(cobrado),
        'deposito_estado': deposito_estado,
        'deposito_ya_devuelto': ya_devuelto,
        'monto_devolucion_sugerido': float(monto_sug),
        'puede_devolver': deposito_estado == 'pagado' and not ya_devuelto and monto_sug > 0,
        'mensaje': ' '.join(mensajes),
        'vendedor': vendedor_data,
        'propiedad': _propiedad_dict(contrato.propiedad),
        'precio_mensual': float(contrato.precio_mensual or 0),
        'moneda': getattr(contrato, 'moneda', 'ARS') or 'ARS',
    }


def datos_operacion_liquidacion_caja(liquidacion) -> dict:
    prop = liquidacion.propiedad
    propietario = liquidacion.propietario
    prop_txt = str(propietario) if propietario else ''
    deposito_extra = {}
    reserva = getattr(liquidacion, 'reserva', None)
    contrato = getattr(liquidacion, 'contrato', None)
    if reserva and not getattr(reserva, 'eliminada', False):
        dep = datos_operacion_reserva_caja(reserva)
        deposito_extra = {
            'deposito_garantia': dep.get('deposito_garantia', 0),
            'deposito_cobrado': dep.get('deposito_cobrado', 0),
            'deposito_estado': dep.get('deposito_estado', 'no_aplica'),
            'deposito_ya_devuelto': dep.get('deposito_ya_devuelto', False),
            'monto_devolucion_sugerido': dep.get('monto_devolucion_sugerido', 0),
            'puede_devolver': dep.get('puede_devolver', False),
            'operacion_vinculada_tipo': 'reserva',
            'operacion_vinculada_id': int(reserva.id),
        }
        if dep.get('mensaje'):
            deposito_extra['mensaje_deposito'] = dep['mensaje']
    elif contrato:
        dep = datos_operacion_contrato_caja(contrato)
        deposito_extra = {
            'deposito_garantia': dep.get('deposito_garantia', 0),
            'deposito_cobrado': dep.get('deposito_cobrado', 0),
            'deposito_estado': dep.get('deposito_estado', 'no_aplica'),
            'deposito_ya_devuelto': dep.get('deposito_ya_devuelto', False),
            'monto_devolucion_sugerido': dep.get('monto_devolucion_sugerido', 0),
            'puede_devolver': dep.get('puede_devolver', False),
            'operacion_vinculada_tipo': 'contrato',
            'operacion_vinculada_id': int(contrato.id),
        }
        if dep.get('mensaje'):
            deposito_extra['mensaje_deposito'] = dep['mensaje']

    return {
        'tipo': 'liquidacion',
        'tipo_label': 'Liquidación a propietario',
        'id': int(liquidacion.id),
        'estado': liquidacion.estado,
        'fecha_desde': liquidacion.fecha_desde.isoformat() if liquidacion.fecha_desde else '',
        'fecha_hasta': liquidacion.fecha_hasta.isoformat() if liquidacion.fecha_hasta else '',
        'cliente': prop_txt,
        'propietario': prop_txt,
        'cuenta_bancaria': (propietario.cuenta_bancaria or '').strip() if propietario else '',
        'monto_a_pagar': float(liquidacion.monto_a_pagar or 0),
        'monto_propietario': float(liquidacion.monto_propietario or 0),
        'monto_total_operacion': float(liquidacion.monto_total_operacion or 0),
        'deposito_garantia': deposito_extra.get('deposito_garantia', 0),
        'deposito_cobrado': deposito_extra.get('deposito_cobrado', 0),
        'deposito_estado': deposito_extra.get('deposito_estado', 'no_aplica'),
        'deposito_ya_devuelto': deposito_extra.get('deposito_ya_devuelto', False),
        'monto_devolucion_sugerido': deposito_extra.get('monto_devolucion_sugerido', 0),
        'puede_devolver': deposito_extra.get('puede_devolver', False),
        'operacion_vinculada_tipo': deposito_extra.get('operacion_vinculada_tipo', ''),
        'operacion_vinculada_id': deposito_extra.get('operacion_vinculada_id'),
        'mensaje': deposito_extra.get('mensaje_deposito', ''),
        'propiedad': _propiedad_dict(prop),
    }


def _enriquecer_reserva(op: dict) -> dict:
    op['tipo_label'] = 'Reserva · alquiler temporario'
    return op


def buscar_operacion_caja(
    sucursal,
    numero: int,
    *,
    tipo_comprobante_hint: str = '',
    tipo_operacion_hint: str = '',
) -> tuple[dict | None, str | None]:
    """
    Busca reserva, contrato o liquidación por número en la sucursal.
    Devuelve (payload_json_ready, error_msg).

    Si el mismo número existe como reserva y contrato, devuelve payload con
    ``ambiguo: True`` y la lista ``candidatos`` para que el usuario elija.
  Usá tipo_operacion_hint o prefijos C300 / R300 / L300 para forzar el tipo.
    """
    from inmobiliaria.models import ContratoAlquiler, Reserva
    from inmobiliaria.models.liquidacion import LiquidacionPropietario

    pk = int(numero)
    tipo_op = (tipo_operacion_hint or '').strip().lower()
    candidatos: list[tuple[str, object]] = []

    reserva = (
        Reserva.objects.select_related('propiedad', 'cliente')
        .filter(id=pk, sucursal=sucursal, eliminada=False)
        .first()
    )
    if reserva:
        candidatos.append(('reserva', reserva))

    contrato = (
        ContratoAlquiler.objects.select_related('propiedad', 'inquilino')
        .filter(id=pk, sucursal=sucursal)
        .first()
    )
    if contrato:
        candidatos.append(('contrato', contrato))

    liquidacion = (
        LiquidacionPropietario.objects.select_related(
            'propiedad', 'propietario', 'reserva', 'contrato'
        )
        .filter(id=pk, sucursal=sucursal)
        .first()
    )
    if liquidacion:
        candidatos.append(('liquidacion', liquidacion))

    if not candidatos:
        return None, f'No se encontró operación, contrato ni liquidación #{pk} en esta sucursal.'

    if tipo_op in ('reserva', 'contrato', 'liquidacion'):
        filtrados = [(t, o) for t, o in candidatos if t == tipo_op]
        if filtrados:
            candidatos = filtrados
        else:
            otros = ', '.join(t for t, _ in candidatos)
            return None, (
                f'No hay {tipo_op} #{pk} en esta sucursal '
                f'(pero sí existe como: {otros}). Probá otro prefijo (C / R / L).'
            )

    if len(candidatos) > 1:
        labels = {
            'reserva': 'reserva (por día)',
            'contrato': 'contrato (mensual)',
            'liquidacion': 'liquidación',
        }
        tipos_txt = ' y '.join(labels.get(t, t) for t, _ in candidatos)
        return {
            'success': False,
            'ambiguo': True,
            'numero': pk,
            'mensaje': (
                f'El número {pk} existe como {tipos_txt}. '
                f'Elegí cuál usar o buscá con prefijo (C{pk} = contrato, R{pk} = reserva).'
            ),
            'candidatos': [_resumen_candidato_operacion_caja(t, o) for t, o in candidatos],
        }, None

    tipo, obj = candidatos[0]
    if tipo == 'reserva':
        operacion = _enriquecer_reserva(datos_operacion_reserva_caja(obj))
    elif tipo == 'contrato':
        operacion = datos_operacion_contrato_caja(obj)
    else:
        operacion = datos_operacion_liquidacion_caja(obj)

    concepto_dev = concepto_devolucion_deposito_catalogo(sucursal)
    movimiento = _movimiento_desde_operacion(operacion, concepto_dev)
    return {
        'success': True,
        'operacion': operacion,
        'concepto_devolucion': concepto_dev,
        'movimiento': movimiento,
    }, None


def _movimiento_desde_operacion(operacion: dict, concepto_dev: dict) -> dict:
    tipo_op = operacion.get('tipo') or 'reserva'
    oid = operacion.get('id')
    cliente = operacion.get('cliente') or operacion.get('propietario') or ''

    if tipo_op == 'liquidacion':
        detalle = f'Pago liquidación #{oid} — {cliente}'
        if operacion.get('estado'):
            detalle += f' ({operacion["estado"]})'
        if operacion.get('cuenta_bancaria'):
            detalle += f'\nCuenta propietario: {operacion["cuenta_bancaria"]}'
        return {
            'tipo': 'EG',
            'tipo_comprobante': 'LQ',
            'numero_liquidacion': f'0000-{int(oid):08d}',
            'fecha_desde': operacion.get('fecha_desde') or '',
            'fecha_hasta': operacion.get('fecha_hasta') or '',
            'detalles': detalle,
            'propiedad': operacion.get('propiedad'),
            'monto_sugerido': operacion.get('monto_a_pagar') or 0,
            'imputacion': 'propietario',
            'concepto_devolucion': concepto_dev,
            **{k: operacion.get(k) for k in (
                'deposito_estado', 'deposito_ya_devuelto', 'puede_devolver',
                'monto_devolucion_sugerido', 'mensaje',
            )},
        }

    if tipo_op == 'contrato':
        detalle = f'Contrato #{oid}'
    else:
        detalle = f'Operación #{oid}'
    if cliente:
        detalle += f' — {cliente}'
    if tipo_op == 'contrato':
        detalle += f' — {operacion.get("duracion_meses") or ""} meses'.replace('  meses', ' meses')
    return {
        'tipo': 'EG',
        'tipo_comprobante': 'OT',
        'numero_liquidacion': '',
        'fecha_desde': operacion.get('fecha_desde') or '',
        'fecha_hasta': operacion.get('fecha_hasta') or '',
        'detalles': detalle,
        'propiedad': operacion.get('propiedad'),
        'monto_sugerido': operacion.get('monto_devolucion_sugerido') or 0,
        'imputacion': 'oficina',
        'concepto_devolucion': concepto_dev,
        'operacion_ref_tipo': tipo_op,
        'operacion_ref_id': oid,
        **{k: operacion.get(k) for k in (
            'deposito_estado', 'deposito_ya_devuelto', 'puede_devolver',
            'monto_devolucion_sugerido', 'mensaje',
        )},
    }
