"""Búsqueda unificada de operaciones desde Nuevo movimiento de caja."""
from __future__ import annotations

from decimal import Decimal

from inmobiliaria.caja_devolucion_deposito import (
    concepto_devolucion_deposito_catalogo,
    datos_operacion_reserva_caja,
)
from inmobiliaria.models.caja import MovimientoCaja, TipoMovimientoCajaEnum


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


def buscar_operacion_caja(sucursal, numero: int, *, tipo_comprobante_hint: str = '') -> tuple[dict | None, str | None]:
    """
    Busca reserva, contrato o liquidación por número en la sucursal.
    Devuelve (payload_json_ready, error_msg).
    """
    from inmobiliaria.models import ContratoAlquiler, Reserva
    from inmobiliaria.models.liquidacion import LiquidacionPropietario

    pk = int(numero)
    hint = (tipo_comprobante_hint or '').strip().lower()
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

    orden_hint = {
        'liquidacion': ['liquidacion', 'reserva', 'contrato'],
        'recibo': ['reserva', 'contrato', 'liquidacion'],
        'otro': ['reserva', 'contrato', 'liquidacion'],
    }
    preferidos = orden_hint.get(hint, ['reserva', 'contrato', 'liquidacion'])
    elegido = None
    for pref in preferidos:
        for tipo, obj in candidatos:
            if tipo == pref:
                elegido = (tipo, obj)
                break
        if elegido:
            break
    if not elegido:
        elegido = candidatos[0]

    tipo, obj = elegido
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

    detalle = f'Operación #{oid}'
    if cliente:
        detalle += f' — {cliente}'
    if tipo_op == 'contrato':
        detalle += f' — Contrato {operacion.get("duracion_meses") or ""} meses'.replace('  meses', ' meses')
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
