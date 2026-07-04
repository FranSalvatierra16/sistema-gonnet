from django.db import models
from django.utils import timezone
from decimal import Decimal
from .persona import Vendedor
from .propiedad import Reserva
from .caja import MovimientoCaja

# Roles para varias líneas de comisión por movimiento (p. ej. honorarios)
ROL_COMISION_GENERAL = 'general'
ROL_COMISION_FICHAJE = 'fichaje'
ROL_COMISION_OP_DIA = 'operacion_dia'
ROL_COMISION_OP_INVIERNO = 'operacion_invierno'
ROL_COMISION_OP_24 = 'operacion_24_meses'
ROL_COMISION_REVERSION = 'reversion_anulacion'

ROLES_COMISION_PRODUCTOR = (
    ROL_COMISION_GENERAL,
    ROL_COMISION_OP_DIA,
    ROL_COMISION_OP_INVIERNO,
    ROL_COMISION_OP_24,
)


def vendedor_fichaje_desde_propiedad(prop):
    """Vendedor que fichó la propiedad; la comisión fichaje es suya, no del productor de la operación."""
    if not prop:
        return None
    fichado = getattr(prop, 'fichado_por', None)
    if fichado is None:
        return None
    return fichado


def propiedad_es_oficina(prop):
    return bool(prop and getattr(prop, 'es_propiedad_oficina', False))


def pct_comision_invierno_vendedor(vendedor, prop):
    """% invierno del productor; si la propiedad es de oficina, usa el % específico."""
    if propiedad_es_oficina(prop):
        pct_of = getattr(vendedor, 'comision_invierno_propiedad_oficina', None)
        if pct_of is not None and pct_of > 0:
            return pct_of
    return vendedor.comision_invierno


def pct_comision_24_meses_vendedor(vendedor, prop):
    """% 24 meses del productor; si la propiedad es de oficina, usa el % específico."""
    if propiedad_es_oficina(prop):
        pct_of = getattr(vendedor, 'comision_alquiler_24_meses_propiedad_oficina', None)
        if pct_of is not None and pct_of > 0:
            return pct_of
    return vendedor.comision_alquiler_24_meses


def _fecha_operacion_entrada_reserva(reserva):
    """Fecha de acreditación en reservas invierno/24: día de ingreso al departamento."""
    from datetime import datetime, time

    f = getattr(reserva, 'fecha_inicio', None)
    if not f:
        return timezone.now()
    dt = datetime.combine(f, time.min)
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _fecha_operacion_comision_reserva(reserva, movimiento_caja):
    """
    Por día: fecha del cobro (seña). Invierno / 24 meses: fecha de ingreso (fecha_inicio).
    """
    if reserva and clasificar_tipo_operacion_reserva(reserva) in ('invierno', '24'):
        return _fecha_operacion_entrada_reserva(reserva)
    return movimiento_caja.fecha if movimiento_caja else timezone.now()


def porcentaje_fichaje_vendedor(vendedor, tipo_fichaje=None, categoria_operacion=None):
    """
    % de comisión fichaje sobre honorarios.
    categoria_operacion: 'dia' | 'invierno' | '24' | None (equivale a día / genérico).
    """
    if not vendedor:
        return None
    tipo = (tipo_fichaje or 'primer').strip().lower()
    es_segundo = tipo == 'segundo'
    cat = (categoria_operacion or 'dia').strip().lower()
    if cat in ('24', 'largo', 'meses_24', '24_meses'):
        cat = '24'
    elif cat in ('6', 'meses_6'):
        cat = '24'
    elif cat in ('invierno', '9'):
        cat = 'invierno'
    if cat in ('invierno', '9'):
        if es_segundo:
            pct = getattr(vendedor, 'comision_segundo_fichaje_invierno', None)
            if pct is not None and pct > 0:
                return pct
            pct = getattr(vendedor, 'comision_primer_fichaje_invierno', None)
            if pct is not None and pct > 0:
                return pct
        else:
            pct = getattr(vendedor, 'comision_primer_fichaje_invierno', None)
            if pct is not None and pct > 0:
                return pct
    elif cat in ('24', 'largo'):
        if es_segundo:
            pct = getattr(vendedor, 'comision_segundo_fichaje_24_meses', None)
            if pct is not None and pct > 0:
                return pct
            pct = getattr(vendedor, 'comision_primer_fichaje_24_meses', None)
            if pct is not None and pct > 0:
                return pct
        else:
            pct = getattr(vendedor, 'comision_primer_fichaje_24_meses', None)
            if pct is not None and pct > 0:
                return pct
    if es_segundo:
        pct = getattr(vendedor, 'comision_segundo_fichaje', None)
        if pct is not None and pct > 0:
            return pct
        pct = getattr(vendedor, 'comision_primer_fichaje', None)
        if pct is not None and pct > 0:
            return pct
        return None
    pct = getattr(vendedor, 'comision_primer_fichaje', None)
    if pct is not None and pct > 0:
        return pct
    return None


def _etiqueta_categoria_fichaje(categoria_operacion):
    cat = (categoria_operacion or 'dia').strip().lower()
    if cat == 'invierno':
        return 'invierno'
    if cat in ('24', 'largo'):
        return '24 meses'
    return 'por día'


def rol_comision_al_crear_linea_unica(vendedor, reserva):
    """
    Rol alineado con el % que realmente devuelve porcentaje_comision_para_reserva()
    (pago sin honorarios desglosados). Evita marcar «fichaje» solo porque exista % de
    fichaje en la ficha si en esta reserva aplica el % de comisión por día.
    """
    if not reserva or not getattr(reserva, 'propiedad_id', None):
        return ROL_COMISION_GENERAL

    pct = vendedor.porcentaje_comision_para_reserva(reserva)
    if pct is None or pct <= 0:
        return ROL_COMISION_GENERAL

    prop = reserva.propiedad
    try:
        dias = (reserva.fecha_fin - reserva.fecha_inicio).days
    except (TypeError, AttributeError):
        dias = 0

    es_alquiler_largo = dias >= 600
    if es_alquiler_largo:
        pct_24 = pct_comision_24_meses_vendedor(vendedor, prop)
        if pct_24 is not None and pct_24 > 0 and pct == pct_24:
            return ROL_COMISION_OP_24

    if (
        dias < 600
        and dias >= 14
        and getattr(prop, 'habilitar_invierno', False)
    ):
        try:
            mes_ini = reserva.fecha_inicio.month
        except AttributeError:
            mes_ini = 0
        if mes_ini in (4, 5, 6, 7, 8, 9, 10):
            pct_inv = pct_comision_invierno_vendedor(vendedor, prop)
            if pct_inv is not None and pct_inv > 0 and pct == pct_inv:
                return ROL_COMISION_OP_INVIERNO

    tipo = getattr(prop, 'tipo_fichaje', None) or 'primer'
    if (
        tipo == 'segundo'
        and vendedor.comision_segundo_fichaje is not None
        and vendedor.comision_segundo_fichaje > 0
        and pct == vendedor.comision_segundo_fichaje
    ):
        return ROL_COMISION_FICHAJE
    if (
        tipo == 'primer'
        and vendedor.comision_primer_fichaje is not None
        and vendedor.comision_primer_fichaje > 0
        and pct == vendedor.comision_primer_fichaje
    ):
        return ROL_COMISION_FICHAJE

    return ROL_COMISION_OP_DIA


def clasificar_tipo_operacion_reserva(reserva):
    """
    Clasifica la reserva para reglas de comisión: alquiler largo (24), invierno o por día.
    Criterios alineados con porcentaje_comision_para_reserva / invierno en Vendedor.
    """
    prop = reserva.propiedad
    try:
        dias = (reserva.fecha_fin - reserva.fecha_inicio).days
    except (TypeError, AttributeError):
        dias = 0
    if dias >= 600:
        return '24'
    if (
        dias < 600
        and dias >= 14
        and getattr(prop, 'habilitar_invierno', False)
    ):
        try:
            mes_ini = reserva.fecha_inicio.month
        except AttributeError:
            mes_ini = 0
        if mes_ini in (4, 5, 6, 7, 8, 9, 10):
            return 'invierno'
    return 'dia'


def pct_comision_normal_alquiler_dia(vendedor):
    """% comisión 'normal' (alquiler por día): campo comision o default de sucursal."""
    if vendedor.comision is not None:
        return vendedor.comision
    default = getattr(vendedor.sucursal, 'porcentaje_comision_default', None)
    if default is not None:
        return default
    return Decimal('0')


def _pct_operacion_dia_o_fallback_despues_fichaje(vendedor, hubo_regla_fichaje):
    """
    % para la línea «operación por día» sobre el total de la reserva (desacoplado del % fichaje).

    Si ya corre comisión por fichaje sobre honorarios y el vendedor no tiene % de comisión por día cargado,
    se usa el default de sucursal o 1% para no perder la comisión por la reserva en sí.
    """
    pct = pct_comision_normal_alquiler_dia(vendedor)
    if pct is not None and pct > 0:
        return pct
    if hubo_regla_fichaje:
        d = getattr(vendedor.sucursal, 'porcentaje_comision_default', None)
        if d is not None and d > 0:
            return d
        return Decimal('1')
    return Decimal('0')


def _crear_linea_operacion_por_dia(
    vendedor, reserva, movimiento_caja, honorarios_monto, creadas, pct_override=None
):
    """
    Comisión de operación «por día»: % comisión por día (campo comisión / default sucursal) sobre el total
    de la reserva; si no hay precio_total cargado, usa el monto de honorarios de este pago.
    Solo una línea por reserva (no se duplica en pagos parciales).
    """
    pct = pct_override if pct_override is not None else pct_comision_normal_alquiler_dia(vendedor)
    if pct is None or pct <= 0:
        return
    existente = ComisionVendedor.objects.filter(
        vendedor=vendedor,
        reserva=reserva,
        rol_comision=ROL_COMISION_OP_DIA,
    ).exclude(estado='cancelada').first()
    if existente:
        if creadas is not None and existente not in creadas:
            creadas.append(existente)
        return
    base = reserva.precio_total or Decimal('0')
    if base <= 0:
        base = honorarios_monto or Decimal('0')
    if base <= 0:
        return
    c = ComisionVendedor.crear_comision_linea(
        vendedor=vendedor,
        reserva=reserva,
        movimiento_caja=movimiento_caja,
        monto_base=base,
        porcentaje_comision=pct,
        concepto=f'Op. {reserva.id} — comisión alquiler por día (sobre total reserva)',
        rol_comision=ROL_COMISION_OP_DIA,
    )
    if c:
        creadas.append(c)


def registrar_comisiones_honorarios_movimiento_reserva(reserva, movimiento_caja, honorarios_monto):
    """
    Cuando en el movimiento hay honorarios (concepto 25), registra:
    - Comisión por primer/segundo fichaje del vendedor que fichó la propiedad.
    - Por cada productor de la operación: % según tipo (día / invierno / 24 meses).
    """
    if (
        not reserva
        or not movimiento_caja
        or honorarios_monto is None
        or honorarios_monto <= 0
    ):
        return []

    productores = iter_productores_reserva(reserva)
    if not productores:
        return []

    if getattr(reserva, 'eliminada', False) or getattr(reserva, 'estado', None) == 'cancelada':
        return []

    prop = reserva.propiedad
    creadas = []

    tipo_fichaje = getattr(prop, 'tipo_fichaje', None) or 'primer'
    vend_fichaje = vendedor_fichaje_desde_propiedad(prop)
    tipo_op = clasificar_tipo_operacion_reserva(reserva)
    pct_fichaje = porcentaje_fichaje_vendedor(vend_fichaje, tipo_fichaje, categoria_operacion=tipo_op)

    hubo_regla_fichaje = pct_fichaje is not None and pct_fichaje > 0
    if hubo_regla_fichaje and vend_fichaje:
        cat_lbl = _etiqueta_categoria_fichaje(tipo_op)
        c = ComisionVendedor.crear_comision_linea(
            vendedor=vend_fichaje,
            reserva=reserva,
            movimiento_caja=movimiento_caja,
            monto_base=honorarios_monto,
            porcentaje_comision=pct_fichaje,
            concepto=(
                f'Op. {reserva.id} — comisión fichaje ({tipo_fichaje}, {cat_lbl}) sobre honorarios'
            ),
            rol_comision=ROL_COMISION_FICHAJE,
        )
        if c:
            creadas.append(c)

    for vend in productores:
        pct_op_dia = _pct_operacion_dia_o_fallback_despues_fichaje(vend, hubo_regla_fichaje)
        pct_op_dia_kw = pct_op_dia if pct_op_dia and pct_op_dia > 0 else None

        if tipo_op == 'dia':
            _crear_linea_operacion_por_dia(
                vend, reserva, movimiento_caja, honorarios_monto, creadas, pct_override=pct_op_dia_kw
            )

        elif tipo_op == 'invierno':
            pct = pct_comision_invierno_vendedor(vend, prop)
            suf_of = ' (prop. oficina)' if propiedad_es_oficina(prop) else ''
            if pct is not None and pct > 0:
                c = ComisionVendedor.crear_comision_linea(
                    vendedor=vend,
                    reserva=reserva,
                    movimiento_caja=movimiento_caja,
                    monto_base=honorarios_monto,
                    porcentaje_comision=pct,
                    concepto=f'Op. {reserva.id} — comisión invierno{suf_of} (sobre honorarios)',
                    rol_comision=ROL_COMISION_OP_INVIERNO,
                )
                if c:
                    creadas.append(c)
            else:
                _crear_linea_operacion_por_dia(
                    vend, reserva, movimiento_caja, honorarios_monto, creadas, pct_override=pct_op_dia_kw
                )

        elif tipo_op == '24':
            pct = pct_comision_24_meses_vendedor(vend, prop)
            suf_of = ' (prop. oficina)' if propiedad_es_oficina(prop) else ''
            if pct is not None and pct > 0:
                c = ComisionVendedor.crear_comision_linea(
                    vendedor=vend,
                    reserva=reserva,
                    movimiento_caja=movimiento_caja,
                    monto_base=honorarios_monto,
                    porcentaje_comision=pct,
                    concepto=f'Op. {reserva.id} — comisión alquiler 24 meses{suf_of} (sobre honorarios)',
                    rol_comision=ROL_COMISION_OP_24,
                )
                if c:
                    creadas.append(c)
            else:
                _crear_linea_operacion_por_dia(
                    vend, reserva, movimiento_caja, honorarios_monto, creadas, pct_override=pct_op_dia_kw
                )

    return creadas


def asegurar_comisiones_movimiento_reserva(reserva, movimiento_caja, honorarios_monto=None):
    """
    Registra comisiones faltantes para un movimiento de caja de una reserva. Idempotente.
    """
    if not reserva or not movimiento_caja or not iter_productores_reserva(reserva):
        return []

    if getattr(reserva, 'eliminada', False) or getattr(reserva, 'estado', None) == 'cancelada':
        return []

    if honorarios_monto is None:
        honorarios_monto = Decimal(str(getattr(movimiento_caja, 'honorarios', 0) or 0))
    else:
        honorarios_monto = Decimal(str(honorarios_monto or 0))

    prop = reserva.propiedad
    tipo_fichaje = getattr(prop, 'tipo_fichaje', None) or 'primer'
    vend_fichaje = vendedor_fichaje_desde_propiedad(prop)
    tipo_op = clasificar_tipo_operacion_reserva(reserva)
    pct_fichaje = porcentaje_fichaje_vendedor(vend_fichaje, tipo_fichaje, categoria_operacion=tipo_op)
    hubo_fichaje = pct_fichaje is not None and pct_fichaje > 0 and vend_fichaje is not None

    try:
        monto_mov_dec = Decimal(str(movimiento_caja.monto_total))
    except (TypeError, ValueError, ArithmeticError):
        monto_mov_dec = Decimal('0')

    if honorarios_monto > 0:
        return registrar_comisiones_honorarios_movimiento_reserva(
            reserva, movimiento_caja, honorarios_monto
        )

    if hubo_fichaje and tipo_op == 'dia' and monto_mov_dec > 0:
        return registrar_comisiones_honorarios_movimiento_reserva(
            reserva, movimiento_caja, monto_mov_dec
        )

    creadas = []
    if tipo_op == 'dia':
        for vend in iter_productores_reserva(reserva):
            _crear_linea_operacion_por_dia(vend, reserva, movimiento_caja, Decimal('0'), creadas)
        return creadas

    # Invierno / 24 meses: comisiones del productor y fichaje solo sobre honorarios.
    if honorarios_monto > 0:
        return registrar_comisiones_honorarios_movimiento_reserva(
            reserva, movimiento_caja, honorarios_monto
        )
    return creadas


def _fecha_operacion_entrada_contrato(contrato):
    """Fecha de acreditación: día de ingreso al departamento (posesión)."""
    from datetime import datetime, time

    f = getattr(contrato, 'fecha_inicio', None)
    if not f:
        return timezone.now()
    dt = datetime.combine(f, time.min)
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def registrar_comisiones_honorarios_contrato(contrato, honorarios_monto, movimiento_caja=None):
    """
    Comisiones del productor y fichaje sobre la base de comisiones del contrato
    (comisión locador + comisión locatario en 24 meses / invierno).
    fecha_operacion = día de entrada (fecha_inicio del contrato).
    """
    if (
        not contrato
        or not iter_productores_contrato(contrato)
        or honorarios_monto is None
        or honorarios_monto <= 0
    ):
        return []

    if getattr(contrato, 'estado', None) == 'rescindido':
        return []

    prop = contrato.propiedad
    creadas = []
    fecha_op = _fecha_operacion_entrada_contrato(contrato)

    tipo_fichaje = getattr(prop, 'tipo_fichaje', None) or 'primer'
    vend_fichaje = vendedor_fichaje_desde_propiedad(prop)
    cat = (
        contrato.categoria_tipo_operacion()
        if hasattr(contrato, 'categoria_tipo_operacion')
        else '24'
    )
    if vend_fichaje:
        ComisionVendedor.objects.filter(
            contrato=contrato,
            rol_comision=ROL_COMISION_FICHAJE,
        ).exclude(estado='cancelada').exclude(vendedor=vend_fichaje).delete()
    pct_fichaje = None
    if vend_fichaje:
        pct_fichaje = vend_fichaje.porcentaje_fichaje_efectivo(tipo_fichaje, cat)
    if pct_fichaje is not None and pct_fichaje > 0 and vend_fichaje:
        cat_lbl = _etiqueta_categoria_fichaje(cat)
        c = ComisionVendedor.crear_comision_linea_contrato(
            vendedor=vend_fichaje,
            contrato=contrato,
            movimiento_caja=movimiento_caja,
            monto_base=honorarios_monto,
            porcentaje_comision=pct_fichaje,
            concepto=(
                f'Contrato {contrato.id} — comisión fichaje ({tipo_fichaje}, {cat_lbl}) sobre honorarios'
            ),
            rol_comision=ROL_COMISION_FICHAJE,
            fecha_operacion=fecha_op,
        )
        if c:
            nuevo_monto = (
                Decimal(str(honorarios_monto)) * Decimal(str(pct_fichaje)) / Decimal('100')
            ).quantize(Decimal('0.01'))
            updates = []
            if c.monto_total_operacion != honorarios_monto:
                c.monto_total_operacion = honorarios_monto
                updates.append('monto_total_operacion')
            if c.monto_comision != nuevo_monto:
                c.monto_comision = nuevo_monto
                updates.append('monto_comision')
            if c.porcentaje_comision != pct_fichaje:
                c.porcentaje_comision = pct_fichaje
                updates.append('porcentaje_comision')
            if updates:
                c.save(update_fields=updates)
            creadas.append(c)

    if cat not in ('invierno', '24'):
        return creadas

    for vend in iter_productores_contrato(contrato):
        if cat == 'invierno':
            pct = pct_comision_invierno_vendedor(vend, prop)
            rol = ROL_COMISION_OP_INVIERNO
            label = 'invierno'
            if propiedad_es_oficina(prop):
                label = 'invierno (prop. oficina)'
        else:
            pct = pct_comision_24_meses_vendedor(vend, prop)
            rol = ROL_COMISION_OP_24
            label = '24 meses'
            if propiedad_es_oficina(prop):
                label = '24 meses (prop. oficina)'

        if pct is None or pct <= 0:
            continue
        c = ComisionVendedor.crear_comision_linea_contrato(
            vendedor=vend,
            contrato=contrato,
            movimiento_caja=movimiento_caja,
            monto_base=honorarios_monto,
            porcentaje_comision=pct,
            concepto=f'Contrato {contrato.id} — comisión {label} (sobre honorarios)',
            rol_comision=rol,
            fecha_operacion=fecha_op,
        )
        if c:
            nuevo_monto = (
                Decimal(str(honorarios_monto)) * Decimal(str(pct)) / Decimal('100')
            ).quantize(Decimal('0.01'))
            updates = []
            if c.monto_total_operacion != honorarios_monto:
                c.monto_total_operacion = honorarios_monto
                updates.append('monto_total_operacion')
            if c.monto_comision != nuevo_monto:
                c.monto_comision = nuevo_monto
                updates.append('monto_comision')
            if c.porcentaje_comision != pct:
                c.porcentaje_comision = pct
                updates.append('porcentaje_comision')
            if updates:
                c.save(update_fields=updates)
            creadas.append(c)

    return creadas


def asegurar_comisiones_contrato(contrato, honorarios_monto=None, movimiento_caja=None):
    """Registra comisiones del productor para un contrato. Idempotente."""
    if not contrato or not iter_productores_contrato(contrato):
        return []
    if honorarios_monto is None:
        honorarios_monto = Decimal('0')
    else:
        honorarios_monto = Decimal(str(honorarios_monto or 0))
    if honorarios_monto <= 0:
        return []
    return registrar_comisiones_honorarios_contrato(
        contrato, honorarios_monto, movimiento_caja=movimiento_caja
    )


def _eliminar_comisiones_productor_reserva(reserva, vendedor_id=None):
    qs = ComisionVendedor.objects.filter(
        reserva=reserva,
        rol_comision__in=ROLES_COMISION_PRODUCTOR,
    )
    if vendedor_id is not None:
        qs = qs.filter(vendedor_id=vendedor_id)
    qs.delete()


def _eliminar_comisiones_productor_contrato(contrato, vendedor_id=None):
    qs = ComisionVendedor.objects.filter(
        contrato=contrato,
        rol_comision__in=ROLES_COMISION_PRODUCTOR,
    )
    if vendedor_id is not None:
        qs = qs.filter(vendedor_id=vendedor_id)
    qs.delete()


def _validar_vendedor_productor_operacion(vendedor_id, *, sucursal_id=None):
    from inmobiliaria.models.persona import Vendedor

    try:
        vid = int(vendedor_id)
    except (TypeError, ValueError):
        return None, 'Ingresá un ID de productor válido.'
    vend = Vendedor.objects.filter(pk=vid).first()
    if not vend:
        return None, 'No se encontró un vendedor con ese ID.'
    if sucursal_id and vend.sucursal_id != sucursal_id:
        return None, 'El vendedor no pertenece a la misma sucursal.'
    return vend, None


def _sincronizar_vendedor_principal_reserva(reserva):
    """Mantiene reserva.vendedor alineado al primer productor (compatibilidad)."""
    primero = (
        OperacionProductor.objects.filter(reserva=reserva)
        .order_by('orden', 'id')
        .values_list('vendedor_id', flat=True)
        .first()
    )
    if primero and reserva.vendedor_id != primero:
        reserva.vendedor_id = primero
        reserva.save(update_fields=['vendedor_id'])
    elif not primero and reserva.vendedor_id:
        reserva.vendedor_id = None
        reserva.save(update_fields=['vendedor_id'])


def _sincronizar_vendedor_principal_contrato(contrato):
    primero = (
        OperacionProductor.objects.filter(contrato=contrato)
        .order_by('orden', 'id')
        .values_list('vendedor_id', flat=True)
        .first()
    )
    if primero and contrato.vendedor_id != primero:
        contrato.vendedor_id = primero
        contrato.save(update_fields=['vendedor_id'])
    elif not primero and contrato.vendedor_id:
        contrato.vendedor_id = None
        contrato.save(update_fields=['vendedor_id'])


def asegurar_filas_productores_reserva(reserva):
    if OperacionProductor.objects.filter(reserva=reserva).exists():
        return
    if reserva.vendedor_id:
        OperacionProductor.objects.create(
            reserva=reserva,
            vendedor_id=reserva.vendedor_id,
            orden=0,
        )


def asegurar_filas_productores_contrato(contrato):
    if OperacionProductor.objects.filter(contrato=contrato).exists():
        return
    if contrato.vendedor_id:
        OperacionProductor.objects.create(
            contrato=contrato,
            vendedor_id=contrato.vendedor_id,
            orden=0,
        )


def iter_productores_reserva(reserva):
    if not reserva:
        return []
    asegurar_filas_productores_reserva(reserva)
    qs = OperacionProductor.objects.filter(reserva=reserva).select_related('vendedor').order_by(
        'orden', 'id'
    )
    if qs.exists():
        return [op.vendedor for op in qs]
    if reserva.vendedor_id:
        return [reserva.vendedor]
    return []


def iter_productores_contrato(contrato):
    if not contrato:
        return []
    asegurar_filas_productores_contrato(contrato)
    qs = OperacionProductor.objects.filter(contrato=contrato).select_related('vendedor').order_by(
        'orden', 'id'
    )
    if qs.exists():
        return [op.vendedor for op in qs]
    if contrato.vendedor_id:
        return [contrato.vendedor]
    return []


def lista_productores_operacion(*, reserva=None, contrato=None):
    if reserva:
        asegurar_filas_productores_reserva(reserva)
        return list(
            OperacionProductor.objects.filter(reserva=reserva)
            .select_related('vendedor')
            .order_by('orden', 'id')
        )
    if contrato:
        asegurar_filas_productores_contrato(contrato)
        return list(
            OperacionProductor.objects.filter(contrato=contrato)
            .select_related('vendedor')
            .order_by('orden', 'id')
        )
    return []


def resincronizar_comisiones_productor_reserva(reserva, movimientos_caja, vendedor_id=None):
    """Regenera comisiones de productor(es) tras cambios en la carátula."""
    if vendedor_id is not None:
        _eliminar_comisiones_productor_reserva(reserva, vendedor_id=vendedor_id)
    else:
        _eliminar_comisiones_productor_reserva(reserva)
    for mov in movimientos_caja or []:
        honorarios = getattr(mov, 'honorarios', None)
        asegurar_comisiones_movimiento_reserva(reserva, mov, honorarios_monto=honorarios)


def resincronizar_comisiones_productor_contrato(
    contrato, honorarios_monto=None, movimiento_caja=None, vendedor_id=None
):
    if vendedor_id is not None:
        _eliminar_comisiones_productor_contrato(contrato, vendedor_id=vendedor_id)
    else:
        _eliminar_comisiones_productor_contrato(contrato)
    if honorarios_monto is not None and Decimal(str(honorarios_monto or 0)) > Decimal('0.05'):
        asegurar_comisiones_contrato(
            contrato,
            honorarios_monto=honorarios_monto,
            movimiento_caja=movimiento_caja,
        )


def agregar_productor_reserva(reserva, vendedor_id, movimientos_caja=None):
    if not reserva:
        return False, 'Reserva no válida.'
    vend, err = _validar_vendedor_productor_operacion(
        vendedor_id, sucursal_id=reserva.sucursal_id
    )
    if err:
        return False, err
    asegurar_filas_productores_reserva(reserva)
    if OperacionProductor.objects.filter(reserva=reserva, vendedor=vend).exists():
        return False, 'Ese productor ya está en la operación.'
    orden = (
        OperacionProductor.objects.filter(reserva=reserva).order_by('-orden').values_list(
            'orden', flat=True
        ).first()
        or 0
    ) + 1
    OperacionProductor.objects.create(reserva=reserva, vendedor=vend, orden=orden)
    _sincronizar_vendedor_principal_reserva(reserva)
    resincronizar_comisiones_productor_reserva(reserva, movimientos_caja, vendedor_id=vend.id)
    return True, None


def quitar_productor_reserva(reserva, vendedor_id, movimientos_caja=None):
    if not reserva:
        return False, 'Reserva no válida.'
    try:
        vid = int(vendedor_id)
    except (TypeError, ValueError):
        return False, 'ID de productor inválido.'
    deleted, _ = OperacionProductor.objects.filter(reserva=reserva, vendedor_id=vid).delete()
    if not deleted:
        return False, 'Ese productor no está en la operación.'
    _eliminar_comisiones_productor_reserva(reserva, vendedor_id=vid)
    _sincronizar_vendedor_principal_reserva(reserva)
    return True, None


def agregar_productor_contrato(
    contrato, vendedor_id, honorarios_monto=None, movimiento_caja=None
):
    if not contrato:
        return False, 'Contrato no válido.'
    vend, err = _validar_vendedor_productor_operacion(
        vendedor_id, sucursal_id=contrato.sucursal_id
    )
    if err:
        return False, err
    asegurar_filas_productores_contrato(contrato)
    if OperacionProductor.objects.filter(contrato=contrato, vendedor=vend).exists():
        return False, 'Ese productor ya está en la operación.'
    orden = (
        OperacionProductor.objects.filter(contrato=contrato).order_by('-orden').values_list(
            'orden', flat=True
        ).first()
        or 0
    ) + 1
    OperacionProductor.objects.create(contrato=contrato, vendedor=vend, orden=orden)
    _sincronizar_vendedor_principal_contrato(contrato)
    resincronizar_comisiones_productor_contrato(
        contrato,
        honorarios_monto=honorarios_monto,
        movimiento_caja=movimiento_caja,
        vendedor_id=vend.id,
    )
    return True, None


def quitar_productor_contrato(contrato, vendedor_id):
    if not contrato:
        return False, 'Contrato no válido.'
    try:
        vid = int(vendedor_id)
    except (TypeError, ValueError):
        return False, 'ID de productor inválido.'
    deleted, _ = OperacionProductor.objects.filter(contrato=contrato, vendedor_id=vid).delete()
    if not deleted:
        return False, 'Ese productor no está en la operación.'
    _eliminar_comisiones_productor_contrato(contrato, vendedor_id=vid)
    _sincronizar_vendedor_principal_contrato(contrato)
    return True, None


def cambiar_productor_reserva(reserva, nuevo_vendedor_id, movimientos_caja=None):
    """Reemplaza todos los productores por uno solo (compatibilidad)."""
    if not reserva:
        return False, 'Reserva no válida.'
    OperacionProductor.objects.filter(reserva=reserva).delete()
    _eliminar_comisiones_productor_reserva(reserva)
    reserva.vendedor_id = None
    reserva.save(update_fields=['vendedor_id'])
    return agregar_productor_reserva(reserva, nuevo_vendedor_id, movimientos_caja)


def cambiar_productor_contrato(
    contrato, nuevo_vendedor_id, honorarios_monto=None, movimiento_caja=None
):
    """Reemplaza todos los productores por uno solo (compatibilidad)."""
    if not contrato:
        return False, 'Contrato no válido.'
    OperacionProductor.objects.filter(contrato=contrato).delete()
    _eliminar_comisiones_productor_contrato(contrato)
    contrato.vendedor_id = None
    contrato.save(update_fields=['vendedor_id'])
    return agregar_productor_contrato(
        contrato, nuevo_vendedor_id, honorarios_monto=honorarios_monto, movimiento_caja=movimiento_caja
    )


def _filtro_caratula_confirmada_comision():
    """Comisiones visibles/acreditables solo si la carátula de la operación está confirmada."""
    from django.db.models import Q

    return (
        Q(reserva__isnull=True, contrato__isnull=True)
        | Q(reserva__estado_confirmacion_caratula='confirmada')
        | Q(contrato__estado_confirmacion_caratula='confirmada')
    )


def _marca_observacion_reversion_comision(comision_id):
    return f'reversion_comision_id={comision_id}'


def revertir_comisiones_operacion_anulada(*, reserva=None, contrato=None):
    """
    Al anular/cancelar una operación: cancela comisiones pendientes.
    Si ya estaban acreditadas (confirmada/pagada), crea una línea negativa de devolución.
    """
    if not reserva and not contrato:
        return 0

    qs = ComisionVendedor.objects.exclude(estado='cancelada').exclude(
        rol_comision=ROL_COMISION_REVERSION
    )
    if reserva is not None:
        qs = qs.filter(reserva=reserva)
    else:
        qs = qs.filter(contrato=contrato)

    creadas = 0
    for comision in qs.select_related('vendedor'):
        if comision.estado in ('confirmada', 'pagada'):
            marca = _marca_observacion_reversion_comision(comision.pk)
            if ComisionVendedor.objects.filter(observaciones=marca).exists():
                ComisionVendedor.objects.filter(pk=comision.pk).update(estado='cancelada')
                continue
            monto = Decimal(str(comision.monto_comision or 0))
            if monto != 0:
                ref = (comision.concepto_operacion or '').strip() or 'comisión'
                op_ref = f'reserva #{comision.reserva_id}' if comision.reserva_id else f'contrato #{comision.contrato_id}'
                ComisionVendedor.objects.create(
                    vendedor=comision.vendedor,
                    reserva=comision.reserva,
                    contrato=comision.contrato,
                    movimiento_caja=None,
                    monto_total_operacion=comision.monto_total_operacion,
                    porcentaje_comision=comision.porcentaje_comision,
                    monto_comision=(-monto).quantize(Decimal('0.01')),
                    concepto_operacion=f'Devolución — anulación {op_ref} ({ref})'[:200],
                    rol_comision=ROL_COMISION_REVERSION,
                    fecha_operacion=timezone.now(),
                    estado='confirmada',
                    observaciones=marca,
                )
                creadas += 1
        ComisionVendedor.objects.filter(pk=comision.pk).update(estado='cancelada')
    return creadas


class OperacionProductor(models.Model):
    """Productores asignados a una operación (reserva o contrato); puede haber varios."""

    reserva = models.ForeignKey(
        Reserva,
        on_delete=models.CASCADE,
        related_name='productores_operacion',
        null=True,
        blank=True,
    )
    contrato = models.ForeignKey(
        'ContratoAlquiler',
        on_delete=models.CASCADE,
        related_name='productores_operacion',
        null=True,
        blank=True,
    )
    vendedor = models.ForeignKey(
        Vendedor,
        on_delete=models.CASCADE,
        related_name='operaciones_como_productor',
    )
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'Productor de operación'
        verbose_name_plural = 'Productores de operación'
        ordering = ['orden', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['reserva', 'vendedor'],
                condition=models.Q(reserva__isnull=False),
                name='uniq_operacion_productor_reserva',
            ),
            models.UniqueConstraint(
                fields=['contrato', 'vendedor'],
                condition=models.Q(contrato__isnull=False),
                name='uniq_operacion_productor_contrato',
            ),
        ]

    def __str__(self):
        op = f'reserva #{self.reserva_id}' if self.reserva_id else f'contrato #{self.contrato_id}'
        return f'Productor {self.vendedor_id} — {op}'


class ComisionVendedorQuerySet(models.QuerySet):
    """
    Comisiones que deben sumar en totales: no anuladas y cuya reserva sigue vigente.
    """

    def que_suman(self):
        """Comisiones acreditadas o pagadas (carátula confirmada al acreditar)."""
        from django.db.models import Q

        operaciones_vigentes = (
            _filtro_caratula_confirmada_comision()
            & ~Q(reserva__estado='cancelada')
            & ~Q(reserva__eliminada=True)
            & ~Q(contrato__estado='rescindido')
        )
        return self.filter(estado__in=('confirmada', 'pagada')).filter(
            Q(rol_comision=ROL_COMISION_REVERSION) | operaciones_vigentes
        )

    def visibles_en_historial(self):
        """Historial: operaciones vigentes o devoluciones por anulación."""
        from django.db.models import Q

        operaciones_vigentes = (
            _filtro_caratula_confirmada_comision()
            & ~Q(reserva__estado='cancelada')
            & ~Q(reserva__eliminada=True)
            & ~Q(contrato__estado='rescindido')
        )
        return self.filter(estado__in=('pendiente', 'confirmada', 'pagada')).filter(
            Q(rol_comision=ROL_COMISION_REVERSION) | operaciones_vigentes
        )

    def ordenadas_para_listado_historial(self):
        """
        Misma fecha de operación: primero línea de fichaje, luego por día / invierno / 24 / general,
        para que en el listado queden «juntas» las comisiones del mismo pago.
        """
        from django.db.models import Case, IntegerField, When

        return self.annotate(
            _orden_grupo_rol=Case(
                When(rol_comision=ROL_COMISION_FICHAJE, then=0),
                When(rol_comision=ROL_COMISION_OP_DIA, then=1),
                When(rol_comision=ROL_COMISION_OP_INVIERNO, then=2),
                When(rol_comision=ROL_COMISION_OP_24, then=3),
                When(rol_comision=ROL_COMISION_GENERAL, then=4),
                default=9,
                output_field=IntegerField(),
            )
        ).order_by('-fecha_operacion', '_orden_grupo_rol', 'id')


class ComisionVendedor(models.Model):
    """
    Modelo para registrar las comisiones ganadas por los vendedores en cada operación
    """
    vendedor = models.ForeignKey(
        Vendedor, 
        on_delete=models.CASCADE, 
        related_name='comisiones',
        verbose_name="Vendedor"
    )
    reserva = models.ForeignKey(
        Reserva, 
        on_delete=models.CASCADE, 
        related_name='comisiones_vendedor',
        verbose_name="Reserva",
        null=True,
        blank=True,
    )
    contrato = models.ForeignKey(
        'ContratoAlquiler',
        on_delete=models.CASCADE,
        related_name='comisiones_vendedor',
        verbose_name='Contrato',
        null=True,
        blank=True,
    )
    movimiento_caja = models.ForeignKey(
        MovimientoCaja,
        on_delete=models.CASCADE,
        related_name='comisiones_vendedor',
        verbose_name="Movimiento de Caja",
        null=True,
        blank=True
    )
    
    # Montos de la operación
    monto_total_operacion = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        verbose_name="Monto Total de la Operación"
    )
    porcentaje_comision = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        verbose_name="Porcentaje de Comisión (%)"
    )
    monto_comision = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        verbose_name="Monto de Comisión"
    )
    
    # Información adicional
    concepto_operacion = models.CharField(
        max_length=200,
        verbose_name="Concepto de la Operación"
    )
    rol_comision = models.CharField(
        max_length=32,
        default=ROL_COMISION_GENERAL,
        verbose_name='Rol de comisión',
        help_text='Permite varias líneas por movimiento (fichaje, operación día/invierno/24 meses).',
    )
    fecha_operacion = models.DateTimeField(
        default=timezone.now,
        verbose_name="Fecha de la Operación"
    )
    fecha_calculo = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Cálculo"
    )
    
    # Estado de la comisión
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('confirmada', 'Confirmada'),
        ('pagada', 'Pagada'),
        ('cancelada', 'Cancelada'),
    ]
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='pendiente',
        verbose_name="Estado"
    )
    
    # Observaciones
    observaciones = models.TextField(
        blank=True,
        verbose_name="Observaciones"
    )
    
    objects = ComisionVendedorQuerySet.as_manager()

    class Meta:
        verbose_name = "Comisión de Vendedor"
        verbose_name_plural = "Comisiones de Vendedores"
        ordering = ['-fecha_operacion']
        constraints = [
            models.UniqueConstraint(
                fields=['vendedor', 'reserva', 'movimiento_caja', 'rol_comision'],
                condition=models.Q(reserva__isnull=False),
                name='uniq_comision_vendedor_reserva_mov_rol',
            ),
            models.UniqueConstraint(
                fields=['vendedor', 'contrato', 'rol_comision'],
                condition=models.Q(contrato__isnull=False),
                name='uniq_comision_vendedor_contrato_rol',
            ),
        ]
    
    def __str__(self):
        return f"Comisión {self.id} - {self.vendedor.nombre_completo_vendedor()} - ${self.monto_comision}"

    def _rol_comision_normalizado(self):
        rol_raw = self.rol_comision or ROL_COMISION_GENERAL
        try:
            return (rol_raw.strip() if isinstance(rol_raw, str) else str(rol_raw).strip()) or ROL_COMISION_GENERAL
        except (AttributeError, TypeError):
            return ROL_COMISION_GENERAL

    def _clasificacion_fichaje_primer_segundo_o_dia(self):
        """
        Solo para rol fichaje: ('fichaje', 'primer'|'segundo') o ('por_dia', None) si en realidad es línea por día.
        """
        res = getattr(self, 'reserva', None)
        prop = getattr(res, 'propiedad', None) if res else None
        vend = getattr(self, 'vendedor', None)
        concepto_l = (self.concepto_operacion or '').lower()
        pct_linea = self.porcentaje_comision

        if 'honorarios' in concepto_l and 'fichaje' in concepto_l:
            tf = (getattr(prop, 'tipo_fichaje', None) or 'primer')
            if tf == 'segundo':
                return ('fichaje', 'segundo')
            return ('fichaje', 'primer')

        pct_fichaje = None
        if vend is not None and prop is not None:
            tipo_prop = getattr(prop, 'tipo_fichaje', None) or 'primer'
            cat_fich = 'dia'
            if getattr(self, 'contrato_id', None) and self.contrato_id:
                try:
                    cat_fich = self.contrato.categoria_tipo_operacion() or '24'
                except Exception:
                    cat_fich = '24'
            elif res:
                try:
                    cat_fich = clasificar_tipo_operacion_reserva(res)
                except Exception:
                    cat_fich = 'dia'
            pct_fichaje = porcentaje_fichaje_vendedor(vend, tipo_prop, categoria_operacion=cat_fich)
        if pct_fichaje is not None and pct_linea is not None and pct_linea == pct_fichaje:
            tf = (getattr(prop, 'tipo_fichaje', None) or 'primer')
            if tf == 'segundo':
                return ('fichaje', 'segundo')
            return ('fichaje', 'primer')
        return ('por_dia', None)

    def _categoria_desde_reserva_o_contrato(self):
        """Invierno, 24 meses o por día según la reserva/contrato vinculados."""
        if getattr(self, 'contrato_id', None) and self.contrato_id:
            try:
                cat = self.contrato.categoria_tipo_operacion()
            except Exception:
                cat = None
            if cat == 'invierno':
                return 'por_invierno'
            if cat == '24':
                return 'por_24_meses'
        if getattr(self, 'reserva_id', None) and self.reserva_id:
            try:
                tipo = clasificar_tipo_operacion_reserva(self.reserva)
            except Exception:
                tipo = 'dia'
            if tipo == 'invierno':
                return 'por_invierno'
            if tipo == '24':
                return 'por_24_meses'
            if tipo == 'dia':
                return 'por_dia'
        return None

    def _categoria_desde_concepto_operacion(self):
        """Respaldo para líneas históricas con rol «general» y concepto genérico «Operación N»."""
        concepto_l = (self.concepto_operacion or '').lower()
        if 'fichaje' in concepto_l:
            return 'por_fichaje'
        if 'por día' in concepto_l or 'por dia' in concepto_l or 'alquiler por d' in concepto_l:
            return 'por_dia'
        if 'invierno' in concepto_l:
            return 'por_invierno'
        if '24 meses' in concepto_l or 'largo plazo' in concepto_l or 'largo / 24' in concepto_l:
            return 'por_24_meses'
        return None

    def clasificacion_listado(self):
        """
        Retorna (categoria, subtipo) para badges y agrupación.
        categoria: por_dia | por_fichaje | por_invierno | por_24_meses | operacion
        subtipo: primer | segundo | None
        """
        rol = self._rol_comision_normalizado()
        if rol == ROL_COMISION_REVERSION:
            return ('devolucion', None)
        if rol == ROL_COMISION_OP_DIA:
            return ('por_dia', None)
        if rol == ROL_COMISION_OP_INVIERNO:
            return ('por_invierno', None)
        if rol == ROL_COMISION_OP_24:
            return ('por_24_meses', None)
        if rol == ROL_COMISION_GENERAL:
            cat = self._categoria_desde_reserva_o_contrato()
            if not cat:
                cat = self._categoria_desde_concepto_operacion()
            if cat == 'por_fichaje':
                kind, sub = self._clasificacion_fichaje_primer_segundo_o_dia()
                if kind == 'por_dia':
                    return ('por_dia', None)
                return ('por_fichaje', sub)
            if cat:
                return (cat, None)
            return ('operacion', None)
        if rol == ROL_COMISION_FICHAJE:
            kind, sub = self._clasificacion_fichaje_primer_segundo_o_dia()
            if kind == 'por_dia':
                return ('por_dia', None)
            return ('por_fichaje', sub)
        cat = self._categoria_desde_reserva_o_contrato()
        if not cat:
            cat = self._categoria_desde_concepto_operacion()
        if cat == 'por_fichaje':
            kind, sub = self._clasificacion_fichaje_primer_segundo_o_dia()
            if kind == 'por_dia':
                return ('por_dia', None)
            return ('por_fichaje', sub)
        if cat:
            return (cat, None)
        return ('operacion', None)

    @property
    def categoria_comision_filtro(self):
        """Clave para filtrar en listados: por_dia | por_fichaje | por_invierno | por_24_meses | operacion."""
        cat, _ = self.clasificacion_listado()
        return cat

    @property
    def id_agrupacion_listado(self):
        """Clave para agrupar en el template líneas del mismo movimiento de caja (fichaje + operación juntas)."""
        if self.movimiento_caja_id:
            return f'm:{self.movimiento_caja_id}'
        if getattr(self, 'contrato_id', None):
            return f'c:{self.contrato_id}'
        return f'r:{self.reserva_id or 0}'

    def texto_categoria_comision_badge(self):
        cat, _ = self.clasificacion_listado()
        return {
            'por_dia': 'Por día',
            'por_fichaje': 'Por fichaje',
            'por_invierno': 'Por invierno',
            'por_24_meses': 'Por 24 meses',
            'devolucion': 'Devolución',
            'operacion': 'Operación',
        }.get(cat, 'Operación')

    def texto_subcategoria_fichaje_badge(self):
        _, sub = self.clasificacion_listado()
        if sub == 'primer':
            return 'Primer fichaje'
        if sub == 'segundo':
            return 'Segundo fichaje'
        return ''

    def clase_badge_categoria_comision(self):
        cat, _ = self.clasificacion_listado()
        return {
            'por_dia': 'bg-primary',
            'por_fichaje': 'bg-info text-dark',
            'por_invierno': 'bg-secondary',
            'por_24_meses': 'bg-dark',
            'devolucion': 'bg-danger',
            'operacion': 'bg-light text-dark border',
        }.get(cat, 'bg-secondary')

    def etiqueta_tipo_comision(self):
        """
        Texto legible para listados y detalle (sinónimo de las categorías por día, fichaje, invierno, 24 meses).
        """
        cat, sub = self.clasificacion_listado()
        if cat == 'por_dia':
            return 'Comisión por día'
        if cat == 'por_fichaje':
            if sub == 'segundo':
                return 'Comisión por segundo fichaje'
            return 'Comisión por primer fichaje'
        if cat == 'por_invierno':
            return 'Comisión por invierno'
        if cat == 'por_24_meses':
            return 'Comisión por 24 meses'
        if cat == 'devolucion':
            return 'Devolución por anulación'
        return 'Comisión operación'

    def titulo_operacion_listado(self):
        """Nombre de la operación para listados: Propietario - Inquilino."""
        propietario = None
        inquilino = None
        contrato = getattr(self, 'contrato', None)
        reserva = getattr(self, 'reserva', None)
        if contrato:
            prop = getattr(contrato, 'propiedad', None)
            if prop:
                propietario = getattr(prop, 'propietario', None)
            inquilino = getattr(contrato, 'inquilino', None)
        elif reserva:
            prop = getattr(reserva, 'propiedad', None)
            if prop:
                propietario = getattr(prop, 'propietario', None)
            inquilino = getattr(reserva, 'cliente', None)
            if not inquilino:
                inquilino = getattr(reserva, 'inquilino', None)

        def _nombre(persona):
            if not persona:
                return ''
            if hasattr(persona, 'nombre_completo_display'):
                return (persona.nombre_completo_display() or '').strip()
            ap = (getattr(persona, 'apellido', None) or '').strip()
            nom = (getattr(persona, 'nombre', None) or '').strip()
            if ap and nom:
                return f'{ap}, {nom}'
            return ap or nom or ''

        prop_txt = _nombre(propietario)
        inq_txt = _nombre(inquilino)
        if prop_txt or inq_txt:
            return f'{prop_txt or "—"} - {inq_txt or "—"}'
        return (self.concepto_operacion or '').strip() or '—'

    def save(self, *args, **kwargs):
        # Calcular automáticamente el monto de comisión si no está definido
        if not self.monto_comision and self.monto_total_operacion and self.porcentaje_comision:
            self.monto_comision = (self.monto_total_operacion * self.porcentaje_comision) / Decimal('100')
        super().save(*args, **kwargs)
    
    @classmethod
    def crear_comision_linea(
        cls,
        vendedor,
        reserva,
        movimiento_caja,
        monto_base,
        porcentaje_comision,
        concepto,
        rol_comision=ROL_COMISION_GENERAL,
    ):
        """
        Crea una línea de comisión con base y % explícitos (p. ej. honorarios + rol fichaje).
        """
        if porcentaje_comision is None or porcentaje_comision <= 0:
            return None
        if monto_base is None or monto_base <= 0:
            return None

        if getattr(reserva, 'eliminada', False) or getattr(reserva, 'estado', None) == 'cancelada':
            return None

        comision_existente = cls.objects.filter(
            vendedor=vendedor,
            reserva=reserva,
            movimiento_caja=movimiento_caja,
            rol_comision=rol_comision,
        ).first()

        if comision_existente:
            return comision_existente

        return cls.objects.create(
            vendedor=vendedor,
            reserva=reserva,
            movimiento_caja=movimiento_caja,
            monto_total_operacion=monto_base,
            porcentaje_comision=porcentaje_comision,
            concepto_operacion=(concepto or f'Operación {reserva.id}')[:200],
            rol_comision=rol_comision,
            fecha_operacion=_fecha_operacion_comision_reserva(reserva, movimiento_caja),
            estado='pendiente',
        )

    @classmethod
    def crear_comision_linea_contrato(
        cls,
        vendedor,
        contrato,
        monto_base,
        porcentaje_comision,
        concepto,
        rol_comision=ROL_COMISION_GENERAL,
        movimiento_caja=None,
        fecha_operacion=None,
    ):
        """Línea de comisión de contrato (sin reserva). fecha_operacion = día de entrada."""
        if porcentaje_comision is None or porcentaje_comision <= 0:
            return None
        if monto_base is None or monto_base <= 0:
            return None
        if not contrato or getattr(contrato, 'estado', None) == 'rescindido':
            return None

        comision_existente = cls.objects.filter(
            vendedor=vendedor,
            contrato=contrato,
            rol_comision=rol_comision,
        ).first()
        if comision_existente:
            return comision_existente

        monto_comision = (Decimal(str(monto_base)) * Decimal(str(porcentaje_comision))) / Decimal('100')
        return cls.objects.create(
            vendedor=vendedor,
            contrato=contrato,
            movimiento_caja=movimiento_caja,
            monto_total_operacion=monto_base,
            porcentaje_comision=porcentaje_comision,
            monto_comision=monto_comision.quantize(Decimal('0.01')),
            concepto_operacion=(concepto or f'Contrato {contrato.id}')[:200],
            rol_comision=rol_comision,
            fecha_operacion=fecha_operacion or _fecha_operacion_entrada_contrato(contrato),
            estado='pendiente',
        )

    @classmethod
    def crear_comision(cls, vendedor, reserva, movimiento_caja, monto_total, concepto=""):
        """
        Una sola línea de comisión según tipo de reserva (sin desglose por honorarios).
        El rol refleja la misma regla que el % (fichaje, invierno, 24 meses o comisión por día).
        """
        pct = vendedor.porcentaje_comision_para_reserva(reserva)
        if pct is None or pct <= 0:
            return None

        if getattr(reserva, 'eliminada', False) or getattr(reserva, 'estado', None) == 'cancelada':
            return None

        rol = rol_comision_al_crear_linea_unica(vendedor, reserva)

        comision_existente = cls.objects.filter(
            vendedor=vendedor,
            reserva=reserva,
            movimiento_caja=movimiento_caja,
            rol_comision=rol,
        ).first()

        if comision_existente:
            return comision_existente

        return cls.crear_comision_linea(
            vendedor=vendedor,
            reserva=reserva,
            movimiento_caja=movimiento_caja,
            monto_base=monto_total,
            porcentaje_comision=pct,
            concepto=concepto or f'Operación {reserva.id}',
            rol_comision=rol,
        )
    
    def get_monto_comision_mensual(self, año, mes):
        """
        Obtiene el monto de comisión para un mes específico (no suma anuladas / reservas canceladas).
        """
        return (
            ComisionVendedor.objects.filter(
                vendedor=self.vendedor,
                fecha_operacion__year=año,
                fecha_operacion__month=mes,
            )
            .que_suman()
            .aggregate(total=models.Sum('monto_comision'))['total']
            or Decimal('0')
        )


def _reserva_ids_desde_liquidacion(liquidacion):
    """IDs de reserva vinculadas a una liquidación al propietario."""
    ids = set()
    if not liquidacion:
        return ids
    if liquidacion.reserva_id:
        ids.add(int(liquidacion.reserva_id))
    for op in liquidacion.operaciones_incluidas or []:
        if not isinstance(op, dict):
            continue
        if op.get('tipo') == 'reserva' and op.get('id'):
            try:
                ids.add(int(op['id']))
            except (TypeError, ValueError):
                pass
    if not ids and liquidacion.contrato_id and liquidacion.propiedad_id:
        contrato = liquidacion.contrato
        if contrato and contrato.fecha_inicio and contrato.fecha_fin:
            ids.update(
                Reserva.objects.filter(
                    propiedad_id=liquidacion.propiedad_id,
                    eliminada=False,
                )
                .exclude(estado='cancelada')
                .filter(
                    fecha_inicio__lte=contrato.fecha_fin,
                    fecha_fin__gte=contrato.fecha_inicio,
                )
                .values_list('id', flat=True)
            )
    return ids


def acreditar_comisiones_operacion_por_caratula(reserva=None, contrato=None):
    """
    Tras confirmar la carátula: acredita comisiones pendientes cuya fecha ya llegó.
    """
    from django.utils import timezone

    if not reserva and not contrato:
        return 0
    hoy = timezone.localdate()
    qs = ComisionVendedor.objects.filter(
        estado='pendiente',
        fecha_operacion__isnull=False,
        fecha_operacion__date__lte=hoy,
    ).exclude(estado='cancelada')
    if reserva:
        qs = qs.filter(reserva=reserva)
    else:
        qs = qs.filter(contrato=contrato)
    return qs.update(estado='confirmada')


def acreditar_comisiones_por_fecha_vencida(sucursal=None):
    """
    Acredita comisiones pendientes con fecha vencida solo si la carátula ya está confirmada.
    """
    from django.utils import timezone

    hoy = timezone.localdate()
    qs = ComisionVendedor.objects.filter(
        estado='pendiente',
        fecha_operacion__isnull=False,
        fecha_operacion__date__lte=hoy,
    ).filter(_filtro_caratula_confirmada_comision()).exclude(
        reserva__estado='cancelada'
    ).exclude(reserva__eliminada=True).exclude(contrato__estado='rescindido')
    if sucursal is not None:
        qs = qs.filter(vendedor__sucursal=sucursal)
    return qs.update(estado='confirmada')


def confirmar_comisiones_por_liquidacion(liquidacion):
    """
    Acredita comisiones de vendedor (pendiente → confirmada) al crear liquidación al propietario.
    """
    if not liquidacion or getattr(liquidacion, 'estado', None) == 'cancelada':
        return 0
    total = 0
    reserva_ids = _reserva_ids_desde_liquidacion(liquidacion)
    if reserva_ids:
        total += ComisionVendedor.objects.filter(
            reserva_id__in=reserva_ids,
            estado='pendiente',
        ).update(estado='confirmada')
    if liquidacion.contrato_id:
        total += ComisionVendedor.objects.filter(
            contrato_id=liquidacion.contrato_id,
            estado='pendiente',
        ).update(estado='confirmada')
    return total


def comisiones_operacion_qs(reserva=None, contrato=None):
    """Comisiones de vendedor vinculadas a una reserva o contrato (sin canceladas)."""
    qs = ComisionVendedor.objects.exclude(estado='cancelada')
    if reserva is not None:
        return qs.filter(reserva=reserva)
    if contrato is not None:
        return qs.filter(contrato=contrato)
    return qs.none()


def resumen_confirmacion_comisiones_operacion(reserva=None, contrato=None):
    """
    Estado de confirmación de comisiones para carátula / listado.
    Retorna dict: estado, label, badge_class, puede_confirmar, pendientes, confirmadas, total.
    """
    qs = comisiones_operacion_qs(reserva=reserva, contrato=contrato)
    total = qs.count()
    if total == 0:
        return {
            'estado': 'sin_comisiones',
            'label': 'Sin comisiones',
            'badge_class': 'bg-secondary',
            'puede_confirmar': False,
            'pendientes': 0,
            'confirmadas': 0,
            'total': 0,
        }
    pendientes = qs.filter(estado='pendiente').count()
    confirmadas = qs.filter(estado__in=('confirmada', 'pagada')).count()
    if pendientes > 0:
        return {
            'estado': 'pendiente',
            'label': 'Pendiente',
            'badge_class': 'bg-warning text-dark',
            'puede_confirmar': True,
            'pendientes': pendientes,
            'confirmadas': confirmadas,
            'total': total,
        }
    return {
        'estado': 'confirmada',
        'label': 'Confirmada',
        'badge_class': 'bg-success',
        'puede_confirmar': False,
        'pendientes': 0,
        'confirmadas': confirmadas,
        'total': total,
    }


def confirmar_comisiones_operacion(reserva=None, contrato=None):
    """Marca como confirmadas las comisiones pendientes de la operación."""
    return comisiones_operacion_qs(reserva=reserva, contrato=contrato).filter(
        estado='pendiente',
    ).update(estado='confirmada')


def mapa_estado_comisiones_lista_caratulas(reserva_ids, contrato_ids):
    """
    {reserva_id: resumen_dict} y {contrato_id: resumen_dict} para el listado de carátulas.
    """
    from django.db.models import Count, Q

    vacio = resumen_confirmacion_comisiones_operacion()
    mapa_res = {rid: dict(vacio) for rid in reserva_ids}
    mapa_ctr = {cid: dict(vacio) for cid in contrato_ids}

    if reserva_ids:
        for row in (
            ComisionVendedor.objects.filter(reserva_id__in=reserva_ids)
            .exclude(estado='cancelada')
            .values('reserva_id')
            .annotate(
                total=Count('id'),
                pendientes=Count('id', filter=Q(estado='pendiente')),
                confirmadas=Count('id', filter=Q(estado__in=('confirmada', 'pagada'))),
            )
        ):
            rid = row['reserva_id']
            if row['total'] == 0:
                continue
            if row['pendientes'] > 0:
                mapa_res[rid] = {
                    'estado': 'pendiente',
                    'label': 'Pendiente',
                    'badge_class': 'bg-warning text-dark',
                    'puede_confirmar': True,
                    'pendientes': row['pendientes'],
                    'confirmadas': row['confirmadas'],
                    'total': row['total'],
                }
            else:
                mapa_res[rid] = {
                    'estado': 'confirmada',
                    'label': 'Confirmada',
                    'badge_class': 'bg-success',
                    'puede_confirmar': False,
                    'pendientes': 0,
                    'confirmadas': row['confirmadas'],
                    'total': row['total'],
                }

    if contrato_ids:
        for row in (
            ComisionVendedor.objects.filter(contrato_id__in=contrato_ids)
            .exclude(estado='cancelada')
            .values('contrato_id')
            .annotate(
                total=Count('id'),
                pendientes=Count('id', filter=Q(estado='pendiente')),
                confirmadas=Count('id', filter=Q(estado__in=('confirmada', 'pagada'))),
            )
        ):
            cid = row['contrato_id']
            if row['total'] == 0:
                continue
            if row['pendientes'] > 0:
                mapa_ctr[cid] = {
                    'estado': 'pendiente',
                    'label': 'Pendiente',
                    'badge_class': 'bg-warning text-dark',
                    'puede_confirmar': True,
                    'pendientes': row['pendientes'],
                    'confirmadas': row['confirmadas'],
                    'total': row['total'],
                }
            else:
                mapa_ctr[cid] = {
                    'estado': 'confirmada',
                    'label': 'Confirmada',
                    'badge_class': 'bg-success',
                    'puede_confirmar': False,
                    'pendientes': 0,
                    'confirmadas': row['confirmadas'],
                    'total': row['total'],
                }

    return mapa_res, mapa_ctr


class MesComisionPagadoVendedor(models.Model):
    """
    Marca un mes calendario (año/mes) de un vendedor como liquidado/pagado al productor.
    Los totales «pendientes» del historial excluyen comisiones y vales de esos meses.
    """

    vendedor = models.ForeignKey(
        Vendedor,
        on_delete=models.CASCADE,
        related_name='meses_comision_pagados',
        verbose_name='Vendedor',
    )
    anio = models.PositiveIntegerField(verbose_name='Año')
    mes = models.PositiveSmallIntegerField(verbose_name='Mes', help_text='1–12')
    creado_en = models.DateTimeField(auto_now_add=True, verbose_name='Marcado el')

    class Meta:
        verbose_name = 'Mes comisiones/vales pagado (vendedor)'
        verbose_name_plural = 'Meses comisiones/vales pagados'
        unique_together = [('vendedor', 'anio', 'mes')]
        ordering = ['-anio', '-mes']

    def __str__(self):
        return f'{self.vendedor_id} {self.anio}-{self.mes:02d} pagado'

    def mes_key(self):
        return f'{self.anio:04d}-{self.mes:02d}'
