"""Registro de eventos en el historial del inquilino."""

from decimal import Decimal


def _resolver_inquilino(*, inquilino=None, reserva=None, contrato=None):
    if inquilino is not None:
        return inquilino
    if reserva is not None and reserva.cliente_id:
        return reserva.cliente
    if contrato is not None and contrato.inquilino_id:
        return contrato.inquilino
    return None


def registrar_evento_historial_inquilino(
    *,
    tipo,
    inquilino=None,
    reserva=None,
    contrato=None,
    detalle='',
    usuario=None,
    precio_anterior=None,
    precio_nuevo=None,
    senia_anterior=None,
    senia_nueva=None,
    fecha_inicio_anterior=None,
    fecha_fin_anterior=None,
    fecha_inicio_nueva=None,
    fecha_fin_nueva=None,
    estado_anterior='',
    estado_nuevo='',
):
    inquilino = _resolver_inquilino(inquilino=inquilino, reserva=reserva, contrato=contrato)
    if inquilino is None:
        return None

    from inmobiliaria.models.historial_inquilino import HistorialInquilino

    return HistorialInquilino.objects.create(
        inquilino=inquilino,
        reserva=reserva,
        contrato=contrato,
        tipo=tipo,
        detalle=(detalle or '').strip(),
        precio_anterior=precio_anterior,
        precio_nuevo=precio_nuevo,
        senia_anterior=senia_anterior,
        senia_nueva=senia_nueva,
        fecha_inicio_anterior=fecha_inicio_anterior,
        fecha_fin_anterior=fecha_fin_anterior,
        fecha_inicio_nueva=fecha_inicio_nueva,
        fecha_fin_nueva=fecha_fin_nueva,
        estado_anterior=(estado_anterior or '').strip(),
        estado_nuevo=(estado_nuevo or '').strip(),
        usuario=usuario,
    )


def _decimal_igual(a, b):
    return Decimal(str(a or 0)).quantize(Decimal('0.01')) == Decimal(str(b or 0)).quantize(Decimal('0.01'))


def registrar_cambios_reserva_historial_inquilino(
    *,
    reserva,
    usuario=None,
    precio_anterior=None,
    senia_anterior=None,
    fecha_inicio_anterior=None,
    fecha_fin_anterior=None,
    estado_anterior=None,
    origen='',
):
    """Registra en el historial los cambios detectados en una reserva ya guardada."""
    if reserva is None or not reserva.cliente_id:
        return

    sufijo = f' ({origen})' if origen else ''

    if fecha_inicio_anterior is not None and fecha_fin_anterior is not None and (
        fecha_inicio_anterior != reserva.fecha_inicio or fecha_fin_anterior != reserva.fecha_fin
    ):
        registrar_evento_historial_inquilino(
            tipo='fechas_modificadas',
            reserva=reserva,
            usuario=usuario,
            fecha_inicio_anterior=fecha_inicio_anterior,
            fecha_fin_anterior=fecha_fin_anterior,
            fecha_inicio_nueva=reserva.fecha_inicio,
            fecha_fin_nueva=reserva.fecha_fin,
            detalle=f'Fechas actualizadas{sufijo}.',
        )

    if precio_anterior is not None and senia_anterior is not None and (
        not _decimal_igual(precio_anterior, reserva.precio_total)
        or not _decimal_igual(senia_anterior, reserva.senia)
    ):
        registrar_evento_historial_inquilino(
            tipo='montos_modificados',
            reserva=reserva,
            usuario=usuario,
            precio_anterior=precio_anterior,
            precio_nuevo=reserva.precio_total,
            senia_anterior=senia_anterior,
            senia_nueva=reserva.senia,
            detalle=f'Precio y/o seña actualizados{sufijo}.',
        )

    if estado_anterior is not None and estado_anterior != reserva.estado:
        registrar_evento_historial_inquilino(
            tipo='estado_modificado',
            reserva=reserva,
            usuario=usuario,
            estado_anterior=estado_anterior,
            estado_nuevo=reserva.estado,
            detalle=f'Estado de la operación actualizado{sufijo}.',
        )
