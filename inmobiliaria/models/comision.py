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


def vendedor_fichaje_desde_propiedad(prop, sucursal=None):
    """
    Vendedor que fichó la propiedad; la comisión fichaje es suya, no del productor.

    Si se indica ``sucursal`` (de la reserva/contrato), solo aplica si el fichador
    pertenece a esa misma sucursal: no se comisiona fichaje cross-sucursal
    (ej. productor de Colón en una operación de Corrientes).

    Si el fichador cargado es de otra sucursal pero existe un homónimo
    (mismo apellido/nombre) en la sucursal de la operación, se usa ese
    (caso típico: misma persona duplicada por sucursal, p. ej. Ponti #22 vs #7).
    """
    if not prop:
        return None
    fichado = getattr(prop, 'fichado_por', None)
    if fichado is None:
        return None
    if sucursal is not None:
        sid = getattr(sucursal, 'id', None)
        if sid is None and not hasattr(sucursal, 'id'):
            try:
                sid = int(sucursal)
            except (TypeError, ValueError):
                sid = None
        if sid is not None and getattr(fichado, 'sucursal_id', None) not in (None, sid):
            from inmobiliaria.models.persona import Vendedor

            apellido = (getattr(fichado, 'apellido', None) or '').strip()
            nombre = (getattr(fichado, 'nombre', None) or '').strip()
            if apellido or nombre:
                alt = (
                    Vendedor.objects.filter(sucursal_id=sid)
                    .filter(apellido__iexact=apellido, nombre__iexact=nombre)
                    .order_by('id')
                    .first()
                )
                if alt:
                    return alt
            return None
    return fichado


def q_comision_operacion_de_sucursal(sucursal):
    """Comisiones cuya reserva/contrato pertenece a la sucursal."""
    from django.db.models import Q

    if not sucursal:
        return Q(pk__in=[])
    return Q(reserva__sucursal=sucursal) | Q(contrato__sucursal=sucursal)


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
    """Día de ingreso al departamento (inicio de la estadía)."""
    from datetime import datetime, time

    f = getattr(reserva, 'fecha_inicio', None)
    if not f:
        return timezone.now()
    dt = datetime.combine(f, time.min)
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _fecha_operacion_alta_reserva(reserva):
    """
    Fecha de la operación = cuando se cargó la reserva («Fecha op.» en carátulas).
    """
    fc = getattr(reserva, 'fecha_creacion', None)
    if fc:
        if timezone.is_naive(fc):
            return timezone.make_aware(fc, timezone.get_current_timezone())
        return fc
    return _fecha_operacion_entrada_reserva(reserva)


def _fecha_operacion_comision_reserva(reserva, movimiento_caja):
    """
    Por día: fecha de la operación (alta / Fecha op.), no el día de entrada ni el cobro.
    Se acredita al confirmar la carátula; el listado usa esta fecha.
    """
    if reserva:
        return _fecha_operacion_alta_reserva(reserva)
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
    Clasifica la reserva para reglas de comisión.

    Las reservas (módulo alquiler por día) usan siempre comisión «por día»
    y fichaje sobre el importe de locación. Invierno / 24 meses corresponden
    a contratos, no a estadías cargadas como reserva — aunque la propiedad
    tenga «habilitar invierno» y la estadía dure ≥ 14 días.
    """
    return 'dia'


def pct_comision_normal_alquiler_dia(vendedor):
    """% comisión 'normal' (alquiler por día): campo comision o default de sucursal."""
    if vendedor.comision is not None:
        return vendedor.comision
    default = getattr(vendedor.sucursal, 'porcentaje_comision_default', None)
    if default is not None:
        return default
    return Decimal('0')


def _pct_operacion_dia_o_fallback_despues_fichaje(vendedor, hubo_regla_fichaje=False):
    """
    % para la línea «operación por día» sobre el total de la reserva.

    Solo usa el % del productor o el default de sucursal. Si no hay ninguno,
    no comisiona (no se inventa 1%).
    """
    pct = pct_comision_normal_alquiler_dia(vendedor)
    if pct is not None and pct > 0:
        return pct
    return Decimal('0')


def _cancelar_o_borrar_comisiones_qs(qs):
    """Pendientes se borran; acreditadas/pagadas se cancelan (historial).

    No cancela líneas que ya tienen devolución por anulación: esas deben seguir
    como confirmada/pagada para que el mes del cobro no pierda el crédito
    (el descuento vive en la línea de reversión).
    """
    for c in list(qs):
        if getattr(c, 'estado', None) == 'pendiente':
            c.delete()
            continue
        marca = _marca_observacion_reversion_comision(c.pk)
        if ComisionVendedor.objects.filter(
            rol_comision=ROL_COMISION_REVERSION,
            observaciones=marca,
        ).exclude(estado='cancelada').exists():
            continue
        ComisionVendedor.objects.filter(pk=c.pk).update(estado='cancelada')


def _monto_base_fichaje_reserva(reserva, honorarios_hint=None):
    """
    Base de comisión por fichaje en la reserva.

    - Alquiler por día: importe de locación (precio_total), p. ej. $700.000.
    - Invierno / 24 meses: honorarios de oficina
      (liq_monto_inmobiliaria → honorarios del cobro → reparto inmobiliaria).
    """
    if not reserva:
        return Decimal('0')

    try:
        precio = Decimal(str(getattr(reserva, 'precio_total', None) or 0))
    except (TypeError, ValueError, ArithmeticError):
        precio = Decimal('0')

    tipo_op = clasificar_tipo_operacion_reserva(reserva)
    if tipo_op == 'dia':
        if precio > 0:
            return precio.quantize(Decimal('0.01'))
        return Decimal('0')

    # Invierno / 24 meses: sobre honorarios de oficina.
    inm = getattr(reserva, 'liq_monto_inmobiliaria', None)
    if inm is not None:
        try:
            val = Decimal(str(inm))
            if val > 0:
                return val.quantize(Decimal('0.01'))
        except (TypeError, ValueError, ArithmeticError):
            pass

    hint = Decimal('0')
    if honorarios_hint is not None:
        try:
            hint = Decimal(str(honorarios_hint or 0))
        except (TypeError, ValueError, ArithmeticError):
            hint = Decimal('0')

    if hint > 0 and (precio <= 0 or hint != precio):
        return hint.quantize(Decimal('0.01'))

    try:
        from inmobiliaria.neto_propietario_movimiento import reparto_liquidacion_reserva_por_dia

        total, prop, inm_calc, _hay = reparto_liquidacion_reserva_por_dia(reserva)
        total, prop, inm_calc, _coch, _fondo = reserva.montos_liquidacion_efectivos(
            total, prop, inm_calc
        )
        inm_calc = Decimal(str(inm_calc or 0))
        if inm_calc > 0:
            return inm_calc.quantize(Decimal('0.01'))
    except Exception:
        pass

    if precio > 0:
        return (precio * Decimal('0.30')).quantize(Decimal('0.01'))
    return Decimal('0')


def _sincronizar_comisiones_fichaje_reserva(reserva):
    """
    Alinea líneas de fichaje al fichador actual de la propiedad.
    Deja una sola línea activa por reserva (no una por cada cobro de caja).
    """
    if not reserva:
        return
    prop = getattr(reserva, 'propiedad', None)
    tipo_fichaje = getattr(prop, 'tipo_fichaje', None) or 'primer' if prop else 'primer'
    vend_fichaje = (
        vendedor_fichaje_desde_propiedad(prop, sucursal=getattr(reserva, 'sucursal', None))
        if prop
        else None
    )
    tipo_op = clasificar_tipo_operacion_reserva(reserva)
    pct_fichaje = None
    if vend_fichaje:
        pct_fichaje = vend_fichaje.porcentaje_fichaje_efectivo(tipo_fichaje, tipo_op)

    qs = ComisionVendedor.objects.filter(
        reserva=reserva,
        rol_comision=ROL_COMISION_FICHAJE,
    ).exclude(estado='cancelada')

    activo = bool(vend_fichaje and pct_fichaje is not None and pct_fichaje > 0)
    if not activo:
        _cancelar_o_borrar_comisiones_qs(qs)
        return

    _cancelar_o_borrar_comisiones_qs(qs.exclude(vendedor_id=vend_fichaje.id))

    # Una sola línea de fichaje por operación (evitar duplicados por cobros parciales).
    qs_ok = list(
        ComisionVendedor.objects.filter(
            reserva=reserva,
            vendedor_id=vend_fichaje.id,
            rol_comision=ROL_COMISION_FICHAJE,
        ).exclude(estado='cancelada').order_by('id')
    )
    if not qs_ok:
        return

    keep = qs_ok[0]
    extras = qs_ok[1:]
    base = _monto_base_fichaje_reserva(reserva)
    if base <= 0:
        # Conservar la base más chica razonable (suele ser honorarios, no el cobro entero).
        bases = [
            Decimal(str(c.monto_total_operacion or 0))
            for c in qs_ok
            if Decimal(str(c.monto_total_operacion or 0)) > 0
        ]
        base = min(bases) if bases else Decimal(str(keep.monto_total_operacion or 0))
    if base > 0:
        nuevo_monto = (base * Decimal(str(pct_fichaje)) / Decimal('100')).quantize(Decimal('0.01'))
        updates = []
        if keep.monto_total_operacion != base:
            keep.monto_total_operacion = base
            updates.append('monto_total_operacion')
        if keep.monto_comision != nuevo_monto:
            keep.monto_comision = nuevo_monto
            updates.append('monto_comision')
        if keep.porcentaje_comision != pct_fichaje:
            keep.porcentaje_comision = pct_fichaje
            updates.append('porcentaje_comision')
        if updates:
            keep.save(update_fields=updates)
    if extras:
        _cancelar_o_borrar_comisiones_qs(
            ComisionVendedor.objects.filter(pk__in=[c.pk for c in extras])
        )


def _crear_o_actualizar_linea_fichaje_reserva(
    reserva, movimiento_caja, honorarios_monto, creadas=None,
):
    """
    Garantiza una única comisión de fichaje por reserva (upsert + limpia duplicados).
    """
    if not reserva:
        return None
    _sincronizar_comisiones_fichaje_reserva(reserva)

    prop = getattr(reserva, 'propiedad', None)
    tipo_fichaje = getattr(prop, 'tipo_fichaje', None) or 'primer' if prop else 'primer'
    vend_fichaje = vendedor_fichaje_desde_propiedad(
        prop, sucursal=getattr(reserva, 'sucursal', None)
    )
    if not vend_fichaje:
        return None
    tipo_op = clasificar_tipo_operacion_reserva(reserva)
    pct_fichaje = vend_fichaje.porcentaje_fichaje_efectivo(tipo_fichaje, tipo_op)
    if pct_fichaje is None or pct_fichaje <= 0:
        return None

    base = _monto_base_fichaje_reserva(reserva, honorarios_monto)
    if base <= 0:
        return None

    cat_lbl = _etiqueta_categoria_fichaje(tipo_op)
    base_lbl = 'locación' if tipo_op == 'dia' else 'honorarios'
    c = ComisionVendedor.crear_comision_linea(
        vendedor=vend_fichaje,
        reserva=reserva,
        movimiento_caja=movimiento_caja,
        monto_base=base,
        porcentaje_comision=pct_fichaje,
        concepto=(
            f'Op. {reserva.id} — comisión fichaje ({tipo_fichaje}, {cat_lbl}) sobre {base_lbl}'
        ),
        rol_comision=ROL_COMISION_FICHAJE,
    )
    if c and creadas is not None and c not in creadas:
        creadas.append(c)
    # Por si quedaron duplicados legacy con distinto movimiento_caja.
    _sincronizar_comisiones_fichaje_reserva(reserva)
    return c


def _crear_linea_operacion_por_dia(
    vendedor, reserva, movimiento_caja, honorarios_monto, creadas, pct_override=None,
    participacion_pct=None,
):
    """
    Comisión de operación «por día»: % comisión por día sobre la parte de la reserva
    que le corresponde al productor (participación).
    Fórmula: precio_total × (participación/100) × (% comisión por día/100).
    Aplica piso de comisión mínima por operación (repartido por participación).
    Solo una línea por reserva (no se duplica en pagos parciales).
    """
    pct = pct_override if pct_override is not None else pct_comision_normal_alquiler_dia(vendedor)
    if pct is None or pct <= 0:
        # Sin %: no debe quedar línea inventada (p. ej. fallback 1% viejo o productor Oficina).
        _cancelar_o_borrar_comisiones_qs(
            ComisionVendedor.objects.filter(
                vendedor=vendedor,
                reserva=reserva,
                rol_comision=ROL_COMISION_OP_DIA,
            ).exclude(estado='cancelada')
        )
        return
    base = reserva.precio_total or Decimal('0')
    if base <= 0:
        base = honorarios_monto or Decimal('0')
    base = base_comision_con_participacion(base, participacion_pct)
    if base <= 0:
        return
    nuevo_monto = (base * Decimal(str(pct)) / Decimal('100')).quantize(Decimal('0.01'))
    nuevo_monto = monto_comision_productor_con_minimo(
        nuevo_monto,
        participacion_pct,
        sucursal=getattr(reserva, 'sucursal', None),
    )
    existente = ComisionVendedor.objects.filter(
        vendedor=vendedor,
        reserva=reserva,
        rol_comision=ROL_COMISION_OP_DIA,
    ).exclude(estado='cancelada').first()
    if existente:
        if _comision_acreditada(existente):
            updates_acred = []
            # No pisar fecha_operacion si ya tiene valor (editable en carátula).
            if existente.fecha_operacion is None:
                existente.fecha_operacion = _fecha_operacion_comision_reserva(
                    reserva, movimiento_caja
                )
                updates_acred.append('fecha_operacion')
            if movimiento_caja and not existente.movimiento_caja_id:
                existente.movimiento_caja = movimiento_caja
                updates_acred.append('movimiento_caja')
            if updates_acred:
                existente.save(update_fields=updates_acred)
            if creadas is not None and existente not in creadas:
                creadas.append(existente)
            return
        updates = []
        # No pisar fecha_operacion si ya tiene valor (editable en carátula).
        if existente.fecha_operacion is None:
            existente.fecha_operacion = _fecha_operacion_comision_reserva(
                reserva, movimiento_caja
            )
            updates.append('fecha_operacion')
        if existente.monto_total_operacion != base:
            existente.monto_total_operacion = base
            updates.append('monto_total_operacion')
        if existente.monto_comision != nuevo_monto:
            existente.monto_comision = nuevo_monto
            updates.append('monto_comision')
        if existente.porcentaje_comision != pct:
            existente.porcentaje_comision = pct
            updates.append('porcentaje_comision')
        if updates:
            existente.save(update_fields=updates)
        if creadas is not None and existente not in creadas:
            creadas.append(existente)
        return
    c = ComisionVendedor.crear_comision_linea(
        vendedor=vendedor,
        reserva=reserva,
        movimiento_caja=movimiento_caja,
        monto_base=base,
        porcentaje_comision=pct,
        concepto=(
            f'Op. {reserva.id} — comisión alquiler por día '
            f'(part. {participacion_pct if participacion_pct is not None else 100}% del total)'
        ),
        rol_comision=ROL_COMISION_OP_DIA,
    )
    if c:
        if c.monto_comision != nuevo_monto and not _comision_acreditada(c):
            c.monto_comision = nuevo_monto
            c.save(update_fields=['monto_comision'])
        creadas.append(c)


def registrar_comisiones_honorarios_movimiento_reserva(reserva, movimiento_caja, honorarios_monto):
    """
    Registra sobre una base monetaria (honorarios del movimiento o precio de la reserva):
    - Comisión por primer/segundo fichaje del vendedor que fichó la propiedad.
    - Por cada productor de la operación: % según tipo (día / invierno / 24 meses).

    ``movimiento_caja`` puede ser None (p. ej. operación marcada pagada sin cobro
    vinculado en caja); en ese caso las líneas quedan sin movimiento asociado.
    """
    if (
        not reserva
        or honorarios_monto is None
        or honorarios_monto <= 0
    ):
        return []

    productores = iter_productores_reserva(reserva)
    if not productores:
        return []

    if getattr(reserva, 'eliminada', False) or getattr(reserva, 'estado', None) == 'cancelada':
        return []

    _sincronizar_comisiones_fichaje_reserva(reserva)

    prop = reserva.propiedad
    creadas = []
    part_map = mapa_participacion_productores(reserva=reserva)

    tipo_fichaje = getattr(prop, 'tipo_fichaje', None) or 'primer'
    vend_fichaje = vendedor_fichaje_desde_propiedad(
        prop, sucursal=getattr(reserva, 'sucursal', None)
    )
    tipo_op = clasificar_tipo_operacion_reserva(reserva)
    pct_fichaje = None
    if vend_fichaje:
        pct_fichaje = vend_fichaje.porcentaje_fichaje_efectivo(tipo_fichaje, tipo_op)

    hubo_regla_fichaje = pct_fichaje is not None and pct_fichaje > 0
    if hubo_regla_fichaje and vend_fichaje:
        _crear_o_actualizar_linea_fichaje_reserva(
            reserva, movimiento_caja, honorarios_monto, creadas=creadas,
        )

    for vend in productores:
        part = part_map.get(vend.id, Decimal('100'))
        base_parte = base_comision_con_participacion(honorarios_monto, part)
        pct_op_dia = _pct_operacion_dia_o_fallback_despues_fichaje(vend, hubo_regla_fichaje)
        pct_op_dia_kw = pct_op_dia if pct_op_dia and pct_op_dia > 0 else None

        if tipo_op == 'dia':
            _crear_linea_operacion_por_dia(
                vend, reserva, movimiento_caja, honorarios_monto, creadas,
                pct_override=pct_op_dia_kw,
                participacion_pct=part,
            )

        elif tipo_op == 'invierno':
            pct = pct_comision_invierno_vendedor(vend, prop)
            suf_of = ' (prop. oficina)' if propiedad_es_oficina(prop) else ''
            if pct is not None and pct > 0 and base_parte > 0:
                c = ComisionVendedor.crear_comision_linea(
                    vendedor=vend,
                    reserva=reserva,
                    movimiento_caja=movimiento_caja,
                    monto_base=base_parte,
                    porcentaje_comision=pct,
                    concepto=(
                        f'Op. {reserva.id} — comisión invierno{suf_of} '
                        f'(sobre honorarios, part. {part}%)'
                    ),
                    rol_comision=ROL_COMISION_OP_INVIERNO,
                )
                if c:
                    _aplicar_piso_comision_productor(
                        c, part, getattr(reserva, 'sucursal', None)
                    )
                    creadas.append(c)
            else:
                _crear_linea_operacion_por_dia(
                    vend, reserva, movimiento_caja, honorarios_monto, creadas,
                    pct_override=pct_op_dia_kw,
                    participacion_pct=part,
                )

        elif tipo_op == '24':
            pct = pct_comision_24_meses_vendedor(vend, prop)
            suf_of = ' (prop. oficina)' if propiedad_es_oficina(prop) else ''
            if pct is not None and pct > 0 and base_parte > 0:
                c = ComisionVendedor.crear_comision_linea(
                    vendedor=vend,
                    reserva=reserva,
                    movimiento_caja=movimiento_caja,
                    monto_base=base_parte,
                    porcentaje_comision=pct,
                    concepto=(
                        f'Op. {reserva.id} — comisión alquiler 24 meses{suf_of} '
                        f'(sobre honorarios, part. {part}%)'
                    ),
                    rol_comision=ROL_COMISION_OP_24,
                )
                if c:
                    _aplicar_piso_comision_productor(
                        c, part, getattr(reserva, 'sucursal', None)
                    )
                    creadas.append(c)
            else:
                _crear_linea_operacion_por_dia(
                    vend, reserva, movimiento_caja, honorarios_monto, creadas,
                    pct_override=pct_op_dia_kw,
                    participacion_pct=part,
                )

    return creadas


def _monto_total_movimiento_caja(movimiento_caja):
    if not movimiento_caja:
        return Decimal('0')
    if hasattr(movimiento_caja, 'monto_total'):
        try:
            return Decimal(str(movimiento_caja.monto_total or 0))
        except (TypeError, ValueError, ArithmeticError):
            pass
    try:
        return (
            Decimal(str(getattr(movimiento_caja, 'monto_efectivo', 0) or 0))
            + Decimal(str(getattr(movimiento_caja, 'monto_cheque', 0) or 0))
            + Decimal(str(getattr(movimiento_caja, 'monto_tarjeta', 0) or 0))
            + Decimal(str(getattr(movimiento_caja, 'monto_deposito', 0) or 0))
        )
    except (TypeError, ValueError, ArithmeticError):
        return Decimal('0')


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
    vend_fichaje = vendedor_fichaje_desde_propiedad(
        prop, sucursal=getattr(reserva, 'sucursal', None)
    )
    tipo_op = clasificar_tipo_operacion_reserva(reserva)
    pct_fichaje = None
    if vend_fichaje:
        pct_fichaje = vend_fichaje.porcentaje_fichaje_efectivo(tipo_fichaje, tipo_op)
    hubo_fichaje = pct_fichaje is not None and pct_fichaje > 0 and vend_fichaje is not None

    if honorarios_monto > 0:
        return registrar_comisiones_honorarios_movimiento_reserva(
            reserva, movimiento_caja, honorarios_monto
        )

    creadas = []
    # Sin honorarios desglosados: fichaje una sola vez (base carátula / no el cobro entero)
    # y comisión por día sobre el total de la operación.
    if tipo_op == 'dia':
        if hubo_fichaje:
            base_fichaje = _monto_base_fichaje_reserva(reserva, None)
            if base_fichaje > 0:
                _crear_o_actualizar_linea_fichaje_reserva(
                    reserva, movimiento_caja, None, creadas=creadas,
                )
            else:
                _sincronizar_comisiones_fichaje_reserva(reserva)
        part_map = mapa_participacion_productores(reserva=reserva)
        for vend in iter_productores_reserva(reserva):
            _crear_linea_operacion_por_dia(
                vend,
                reserva,
                movimiento_caja,
                Decimal('0'),
                creadas,
                participacion_pct=part_map.get(vend.id, Decimal('100')),
            )
        return creadas

    # Invierno / 24 meses: comisiones del productor y fichaje solo sobre honorarios.
    if honorarios_monto > 0:
        return registrar_comisiones_honorarios_movimiento_reserva(
            reserva, movimiento_caja, honorarios_monto
        )
    _sincronizar_comisiones_fichaje_reserva(reserva)
    return creadas


def asegurar_comisiones_reserva(reserva, movimientos_caja=None, honorarios_monto=None):
    """
    Asegura comisiones de una reserva. Idempotente.

    Si hay movimientos de ingreso, usa cada uno (como al abrir la carátula con cobros).
    Si no hay movimientos (pago marcado sin caja vinculada), genera productor/fichaje
    sobre el precio_total en alquileres por día.
    """
    if not reserva or not iter_productores_reserva(reserva):
        return []

    if getattr(reserva, 'eliminada', False) or getattr(reserva, 'estado', None) == 'cancelada':
        return []

    _sincronizar_comisiones_fichaje_reserva(reserva)

    movs = []
    for mov in movimientos_caja or []:
        tipo = (getattr(mov, 'tipo', None) or '').strip().upper()
        if tipo in ('EG', 'EGRESO', 'E'):
            continue
        movs.append(mov)

    if movs:
        creadas = []
        vistos = set()
        for mov in movs:
            for c in asegurar_comisiones_movimiento_reserva(
                reserva, mov, honorarios_monto=honorarios_monto
            ):
                if c.id not in vistos:
                    vistos.add(c.id)
                    creadas.append(c)
        return creadas

    try:
        if honorarios_monto is not None:
            base = Decimal(str(honorarios_monto or 0))
        else:
            base = Decimal(str(reserva.precio_total or 0))
    except (TypeError, ValueError, ArithmeticError):
        base = Decimal('0')

    if base <= 0:
        return []

    tipo_op = clasificar_tipo_operacion_reserva(reserva)
    if tipo_op == 'dia':
        # Misma base que un cobro sin honorarios cargados: total de la operación.
        return registrar_comisiones_honorarios_movimiento_reserva(reserva, None, base)

    # Invierno / 24 meses: sin honorarios explícitos no inventamos base.
    if honorarios_monto is not None and base > 0:
        return registrar_comisiones_honorarios_movimiento_reserva(reserva, None, base)
    return []


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

    El fichaje se registra aunque no haya productores asignados (es del fichador).
    """
    if (
        not contrato
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
    vend_fichaje = vendedor_fichaje_desde_propiedad(
        prop, sucursal=getattr(contrato, 'sucursal', None)
    )
    cat = (
        contrato.categoria_tipo_operacion()
        if hasattr(contrato, 'categoria_tipo_operacion')
        else '24'
    )
    qs_fichaje = ComisionVendedor.objects.filter(
        contrato=contrato,
        rol_comision=ROL_COMISION_FICHAJE,
        estado='pendiente',
    )
    if vend_fichaje:
        qs_fichaje.exclude(vendedor=vend_fichaje).delete()
    else:
        qs_fichaje.delete()
    pct_fichaje = None
    if vend_fichaje:
        pct_fichaje = vend_fichaje.porcentaje_fichaje_efectivo(tipo_fichaje, cat)
    if not (pct_fichaje is not None and pct_fichaje > 0 and vend_fichaje):
        ComisionVendedor.objects.filter(
            contrato=contrato,
            rol_comision=ROL_COMISION_FICHAJE,
            estado='pendiente',
        ).delete()
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
        if c and not _comision_acreditada(c):
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
        elif c:
            creadas.append(c)

    if cat not in ('invierno', '24'):
        return creadas

    if not iter_productores_contrato(contrato):
        return creadas

    part_map = mapa_participacion_productores(contrato=contrato)
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
        part = part_map.get(vend.id, Decimal('100'))
        base_parte = base_comision_con_participacion(honorarios_monto, part)
        if base_parte <= 0:
            continue
        c = ComisionVendedor.crear_comision_linea_contrato(
            vendedor=vend,
            contrato=contrato,
            movimiento_caja=movimiento_caja,
            monto_base=base_parte,
            porcentaje_comision=pct,
            concepto=(
                f'Contrato {contrato.id} — comisión {label} '
                f'(sobre honorarios, part. {part}%)'
            ),
            rol_comision=rol,
            fecha_operacion=fecha_op,
        )
        if c and not _comision_acreditada(c):
            nuevo_monto = (
                Decimal(str(base_parte)) * Decimal(str(pct)) / Decimal('100')
            ).quantize(Decimal('0.01'))
            nuevo_monto = monto_comision_productor_con_minimo(
                nuevo_monto, part, sucursal=getattr(contrato, 'sucursal', None)
            )
            updates = []
            if c.monto_total_operacion != base_parte:
                c.monto_total_operacion = base_parte
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
        elif c:
            creadas.append(c)

    return creadas


def asegurar_comisiones_contrato(contrato, honorarios_monto=None, movimiento_caja=None):
    """Registra comisiones de fichaje/productor para un contrato. Idempotente."""
    if not contrato:
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


def _comision_acreditada(comision):
    """Confirmada o pagada: no se borra ni se recalcula el monto."""
    return getattr(comision, 'estado', None) in ('confirmada', 'pagada')


def _eliminar_comisiones_productor_reserva(reserva, vendedor_id=None):
    """Quita comisiones de productor (no fichaje). Pendientes se borran; acreditadas se cancelan."""
    qs = ComisionVendedor.objects.filter(
        reserva=reserva,
        rol_comision__in=ROLES_COMISION_PRODUCTOR,
    ).exclude(estado='cancelada')
    if vendedor_id is not None:
        qs = qs.filter(vendedor_id=vendedor_id)
    _cancelar_o_borrar_comisiones_qs(qs)


def _eliminar_comisiones_productor_contrato(contrato, vendedor_id=None):
    """Quita comisiones de productor (no fichaje). Pendientes se borran; acreditadas se cancelan."""
    qs = ComisionVendedor.objects.filter(
        contrato=contrato,
        rol_comision__in=ROLES_COMISION_PRODUCTOR,
    ).exclude(estado='cancelada')
    if vendedor_id is not None:
        qs = qs.filter(vendedor_id=vendedor_id)
    _cancelar_o_borrar_comisiones_qs(qs)


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
    nuevo = primero or None
    if contrato.vendedor_id == nuevo:
        return
    contrato.vendedor_id = nuevo
    contrato.save(update_fields=['vendedor_id'])


def asegurar_filas_productores_reserva(reserva):
    if OperacionProductor.objects.filter(reserva=reserva).exists():
        return
    if reserva.vendedor_id:
        OperacionProductor.objects.create(
            reserva=reserva,
            vendedor_id=reserva.vendedor_id,
            orden=0,
            porcentaje_participacion=Decimal('100'),
        )
        return
    _recuperar_productores_desde_comisiones(reserva=reserva)


def asegurar_filas_productores_contrato(contrato):
    if OperacionProductor.objects.filter(contrato=contrato).exists():
        return
    if contrato.vendedor_id:
        OperacionProductor.objects.create(
            contrato=contrato,
            vendedor_id=contrato.vendedor_id,
            orden=0,
            porcentaje_participacion=Decimal('100'),
        )
        return
    _recuperar_productores_desde_comisiones(contrato=contrato)


def _recuperar_productores_desde_comisiones(*, reserva=None, contrato=None):
    """
    Si la operación quedó sin productores pero hay comisiones de productor
    (confirmadas/pendientes), vuelve a armar las filas OperacionProductor.
    Evita carátulas con «Sin productores» / comisión $0 cuando la comisión ya existe.
    """
    if reserva:
        qs = ComisionVendedor.objects.filter(reserva=reserva)
        sync = _sincronizar_vendedor_principal_reserva
        crear = lambda vid, orden: OperacionProductor.objects.create(
            reserva=reserva,
            vendedor_id=vid,
            orden=orden,
            porcentaje_participacion=Decimal('0'),
        )
        kwargs_redist = {'reserva': reserva}
    elif contrato:
        qs = ComisionVendedor.objects.filter(contrato=contrato)
        sync = _sincronizar_vendedor_principal_contrato
        crear = lambda vid, orden: OperacionProductor.objects.create(
            contrato=contrato,
            vendedor_id=vid,
            orden=orden,
            porcentaje_participacion=Decimal('0'),
        )
        kwargs_redist = {'contrato': contrato}
    else:
        return

    vids = list(
        qs.filter(rol_comision__in=ROLES_COMISION_PRODUCTOR)
        .exclude(estado='cancelada')
        .exclude(vendedor_id__isnull=True)
        .order_by('id')
        .values_list('vendedor_id', flat=True)
        .distinct()
    )
    if not vids:
        return
    # Mantener orden de aparición
    vistos = set()
    ordenados = []
    for vid in vids:
        if vid not in vistos:
            vistos.add(vid)
            ordenados.append(vid)
    for i, vid in enumerate(ordenados):
        crear(vid, i)
    redistribuir_participaciones_iguales(**kwargs_redist)
    if reserva:
        sync(reserva)
    else:
        sync(contrato)


def _qs_productores_operacion(*, reserva=None, contrato=None):
    if reserva:
        return OperacionProductor.objects.filter(reserva=reserva).order_by('orden', 'id')
    if contrato:
        return OperacionProductor.objects.filter(contrato=contrato).order_by('orden', 'id')
    return OperacionProductor.objects.none()


def redistribuir_participaciones_iguales(*, reserva=None, contrato=None):
    """Parte la operación en partes iguales entre los productores (resto al último)."""
    from decimal import ROUND_DOWN

    ops = list(_qs_productores_operacion(reserva=reserva, contrato=contrato))
    n = len(ops)
    if n == 0:
        return
    if n == 1:
        if ops[0].porcentaje_participacion != Decimal('100'):
            ops[0].porcentaje_participacion = Decimal('100')
            ops[0].save(update_fields=['porcentaje_participacion'])
        return
    cada = (Decimal('100') / Decimal(n)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    assigned = Decimal('0')
    for i, op in enumerate(ops):
        pct = (Decimal('100') - assigned) if i == n - 1 else cada
        if op.porcentaje_participacion != pct:
            op.porcentaje_participacion = pct
            op.save(update_fields=['porcentaje_participacion'])
        assigned += pct


def mapa_participacion_productores(*, reserva=None, contrato=None):
    """vendedor_id → Decimal % participación (default 100 si falta fila)."""
    asegurar = asegurar_filas_productores_reserva if reserva else asegurar_filas_productores_contrato
    obj = reserva or contrato
    if obj:
        asegurar(obj)
    out = {}
    for op in _qs_productores_operacion(reserva=reserva, contrato=contrato).select_related('vendedor'):
        out[op.vendedor_id] = Decimal(str(op.porcentaje_participacion or 0))
    return out


def base_comision_con_participacion(base_monto, participacion_pct):
    """Parte de la base que corresponde al productor según su % de participación."""
    base = Decimal(str(base_monto or 0))
    pct = Decimal(str(participacion_pct if participacion_pct is not None else 100))
    if base <= 0 or pct <= 0:
        return Decimal('0')
    return (base * pct / Decimal('100')).quantize(Decimal('0.01'))


COMISION_MINIMA_OPERACION_DEFAULT = Decimal('10000.00')


def comision_minima_operacion_de_sucursal(sucursal) -> Decimal:
    """Mínimo total de comisión productor por operación (configurable en sucursal)."""
    if sucursal is None:
        return COMISION_MINIMA_OPERACION_DEFAULT
    val = getattr(sucursal, 'comision_minima_operacion', None)
    if val is None:
        return COMISION_MINIMA_OPERACION_DEFAULT
    try:
        return Decimal(str(val))
    except (TypeError, ValueError, ArithmeticError):
        return COMISION_MINIMA_OPERACION_DEFAULT


def monto_comision_productor_con_minimo(
    monto_calculado, participacion_pct, sucursal=None, minimo=None,
):
    """
    Aplica piso de comisión de productor por línea.

    El mínimo (default $10.000) es por productor / línea de comisión por día
    (u otro rol de productor). Si el % da más, se paga lo del %.
    ``minimo=0`` desactiva el piso.

    ``participacion_pct`` se conserva en la firma por compatibilidad; el piso
    ya no se prorratea (antes 50/50 → $5.000 c/u).
    """
    try:
        monto = Decimal(str(monto_calculado or 0)).quantize(Decimal('0.01'))
    except (TypeError, ValueError, ArithmeticError):
        monto = Decimal('0.00')

    if minimo is None:
        minimo = comision_minima_operacion_de_sucursal(sucursal)
    else:
        try:
            minimo = Decimal(str(minimo))
        except (TypeError, ValueError, ArithmeticError):
            minimo = COMISION_MINIMA_OPERACION_DEFAULT

    if minimo <= 0:
        return monto

    piso = minimo.quantize(Decimal('0.01'))
    return monto if monto >= piso else piso


def _aplicar_piso_comision_productor(comision, participacion_pct, sucursal, *, forzar=False):
    """Ajusta monto_comision al piso si la línea es de productor.

    Por defecto no toca confirmadas/pagadas. Con ``forzar=True`` también
    actualiza confirmadas (p. ej. backfill del mínimo $10.000).
    """
    if not comision:
        return comision, False
    if not forzar and _comision_acreditada(comision):
        return comision, False
    if forzar and getattr(comision, 'estado', None) == 'pagada':
        return comision, False
    rol = (getattr(comision, 'rol_comision', None) or '').strip()
    if rol == ROL_COMISION_FICHAJE:
        return comision, False
    calc = Decimal(str(comision.monto_comision or 0))
    nuevo = monto_comision_productor_con_minimo(
        calc, participacion_pct, sucursal=sucursal
    )
    if nuevo != calc:
        comision.monto_comision = nuevo
        comision.save(update_fields=['monto_comision'])
        return comision, True
    return comision, False


def aplicar_piso_comisiones_productor_existentes(
    *,
    solo_por_dia=True,
    incluir_confirmadas=True,
    solo_confirmadas=False,
    sucursal_id=None,
    vendedor_id=None,
    monto_desde=None,
    dry_run=False,
):
    """
    Backfill: sube al piso las comisiones de productor por debajo del mínimo.

    - No toca fichaje ni pagadas ni invierno/24 (salvo ``solo_por_dia=False``).
    - Por defecto roles ``operacion_dia`` y ``general`` (histórico = por día).
    - ``solo_confirmadas=True``: no toca pendientes.
    - ``monto_desde``: ignora montos menores o iguales (evita basura tipo $0,04).
    """
    if solo_por_dia:
        roles = (ROL_COMISION_OP_DIA, ROL_COMISION_GENERAL)
    else:
        roles = ROLES_COMISION_PRODUCTOR
    if solo_confirmadas:
        estados = ['confirmada']
    else:
        estados = ['pendiente']
        if incluir_confirmadas:
            estados.append('confirmada')

    qs = (
        ComisionVendedor.objects.filter(
            rol_comision__in=roles,
            estado__in=estados,
        )
        .select_related('reserva', 'reserva__sucursal', 'contrato', 'contrato__sucursal', 'vendedor')
        .order_by('id')
    )
    if sucursal_id:
        qs = qs.filter(
            models.Q(reserva__sucursal_id=sucursal_id)
            | models.Q(contrato__sucursal_id=sucursal_id)
            | models.Q(vendedor__sucursal_id=sucursal_id, reserva__isnull=True, contrato__isnull=True)
        )
    if vendedor_id:
        qs = qs.filter(vendedor_id=vendedor_id)
    if monto_desde is not None:
        qs = qs.filter(monto_comision__gt=monto_desde)

    cambios = []
    cache_part = {}
    for c in qs.iterator(chunk_size=200):
        key = None
        sucursal = None
        if c.reserva_id:
            key = ('r', c.reserva_id)
            sucursal = getattr(c.reserva, 'sucursal', None) or getattr(
                getattr(c, 'vendedor', None), 'sucursal', None
            )
        elif c.contrato_id:
            key = ('c', c.contrato_id)
            sucursal = getattr(c.contrato, 'sucursal', None) or getattr(
                getattr(c, 'vendedor', None), 'sucursal', None
            )
        else:
            sucursal = getattr(getattr(c, 'vendedor', None), 'sucursal', None)

        if key not in cache_part:
            if key and key[0] == 'r':
                cache_part[key] = mapa_participacion_productores(reserva=c.reserva)
            elif key and key[0] == 'c':
                cache_part[key] = mapa_participacion_productores(contrato=c.contrato)
            else:
                cache_part[key] = {}

        part = cache_part[key].get(c.vendedor_id, Decimal('100'))
        minimo = comision_minima_operacion_de_sucursal(sucursal)
        if minimo <= 0:
            continue
        calc = Decimal(str(c.monto_comision or 0))
        nuevo = monto_comision_productor_con_minimo(
            calc, part, sucursal=sucursal, minimo=minimo
        )
        if nuevo <= calc:
            continue
        cambios.append({
            'id': c.id,
            'vendedor_id': c.vendedor_id,
            'reserva_id': c.reserva_id,
            'contrato_id': c.contrato_id,
            'estado': c.estado,
            'rol': c.rol_comision,
            'participacion': part,
            'antes': calc,
            'despues': nuevo,
            'minimo_op': minimo,
        })
        if not dry_run:
            c.monto_comision = nuevo
            c.save(update_fields=['monto_comision'])

    return cambios


def set_productores_operacion(ids_vendedores, *, reserva=None, contrato=None, redistribuir=True):
    """
    Reemplaza los productores de la operación por la lista de IDs (orden = índice).
    El primero queda como vendedor principal. Por defecto reparte % en partes iguales.
    """
    ids = []
    for raw in ids_vendedores or []:
        try:
            vid = int(raw)
        except (TypeError, ValueError):
            continue
        if vid and vid not in ids:
            ids.append(vid)
    if not ids:
        return False, 'Indicá al menos un productor.'

    sucursal_id = None
    if reserva:
        sucursal_id = reserva.sucursal_id
        OperacionProductor.objects.filter(reserva=reserva).delete()
        for i, vid in enumerate(ids):
            vend, err = _validar_vendedor_productor_operacion(vid, sucursal_id=sucursal_id)
            if err:
                return False, err
            OperacionProductor.objects.create(
                reserva=reserva,
                vendedor=vend,
                orden=i,
                porcentaje_participacion=Decimal('100'),
            )
        _sincronizar_vendedor_principal_reserva(reserva)
        if redistribuir:
            redistribuir_participaciones_iguales(reserva=reserva)
        return True, None

    if contrato:
        sucursal_id = contrato.sucursal_id
        OperacionProductor.objects.filter(contrato=contrato).delete()
        for i, vid in enumerate(ids):
            vend, err = _validar_vendedor_productor_operacion(vid, sucursal_id=sucursal_id)
            if err:
                return False, err
            OperacionProductor.objects.create(
                contrato=contrato,
                vendedor=vend,
                orden=i,
                porcentaje_participacion=Decimal('100'),
            )
        _sincronizar_vendedor_principal_contrato(contrato)
        if redistribuir:
            redistribuir_participaciones_iguales(contrato=contrato)
        return True, None

    return False, 'Operación no válida.'


def actualizar_participaciones_operacion(participaciones, *, reserva=None, contrato=None):
    """
    participaciones: dict {vendedor_id: pct} o lista de (vendedor_id, pct).
    Deben sumar 100 (±0.05).
    """
    if isinstance(participaciones, dict):
        items = list(participaciones.items())
    else:
        items = list(participaciones or [])
    if not items:
        return False, 'No hay participaciones para guardar.'

    parsed = []
    total = Decimal('0')
    for vid_raw, pct_raw in items:
        try:
            vid = int(vid_raw)
            pct = Decimal(str(pct_raw).replace(',', '.'))
        except (TypeError, ValueError, ArithmeticError):
            return False, 'Porcentaje o ID de productor inválido.'
        if pct < 0 or pct > 100:
            return False, 'Los porcentajes deben estar entre 0 y 100.'
        parsed.append((vid, pct))
        total += pct

    if abs(total - Decimal('100')) > Decimal('0.05'):
        return False, f'Los porcentajes deben sumar 100% (ahora suman {total}%).'

    qs = _qs_productores_operacion(reserva=reserva, contrato=contrato)
    ids_ops = set(qs.values_list('vendedor_id', flat=True))
    ids_in = {vid for vid, _ in parsed}
    if ids_in != ids_ops:
        return False, 'Los productores no coinciden con los de la operación.'

    for vid, pct in parsed:
        qs.filter(vendedor_id=vid).update(porcentaje_participacion=pct.quantize(Decimal('0.01')))
    return True, None


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
    asegurar_comisiones_reserva(reserva, movimientos_caja=movimientos_caja)


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
    OperacionProductor.objects.create(
        reserva=reserva,
        vendedor=vend,
        orden=orden,
        porcentaje_participacion=Decimal('0'),
    )
    redistribuir_participaciones_iguales(reserva=reserva)
    _sincronizar_vendedor_principal_reserva(reserva)
    resincronizar_comisiones_productor_reserva(reserva, movimientos_caja)
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
    redistribuir_participaciones_iguales(reserva=reserva)
    _sincronizar_vendedor_principal_reserva(reserva)
    resincronizar_comisiones_productor_reserva(reserva, movimientos_caja)
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
    OperacionProductor.objects.create(
        contrato=contrato,
        vendedor=vend,
        orden=orden,
        porcentaje_participacion=Decimal('0'),
    )
    redistribuir_participaciones_iguales(contrato=contrato)
    _sincronizar_vendedor_principal_contrato(contrato)
    resincronizar_comisiones_productor_contrato(
        contrato,
        honorarios_monto=honorarios_monto,
        movimiento_caja=movimiento_caja,
    )
    return True, None


def quitar_productor_contrato(contrato, vendedor_id, honorarios_monto=None, movimiento_caja=None):
    from django.db import IntegrityError, transaction

    if not contrato:
        return False, 'Contrato no válido.'
    try:
        vid = int(vendedor_id)
    except (TypeError, ValueError):
        return False, 'ID de productor inválido.'
    try:
        with transaction.atomic():
            deleted, _ = OperacionProductor.objects.filter(
                contrato=contrato, vendedor_id=vid
            ).delete()
            if not deleted:
                return False, 'Ese productor no está en la operación.'
            _eliminar_comisiones_productor_contrato(contrato, vendedor_id=vid)
            redistribuir_participaciones_iguales(contrato=contrato)
            _sincronizar_vendedor_principal_contrato(contrato)
    except IntegrityError:
        return (
            False,
            'No se pudo quitar el productor (el contrato no acepta quedar sin productor). '
            'Agregá primero otro productor o avisá a sistemas.',
        )
    except Exception as exc:
        return False, f'No se pudo quitar el productor: {exc}'
    if honorarios_monto is not None:
        resincronizar_comisiones_productor_contrato(
            contrato,
            honorarios_monto=honorarios_monto,
            movimiento_caja=movimiento_caja,
        )
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
    """Comisiones pendientes acreditables solo si la carátula de la operación está confirmada."""
    from django.db.models import Q

    return (
        Q(reserva__isnull=True, contrato__isnull=True)
        | Q(reserva__estado_confirmacion_caratula='confirmada')
        | Q(contrato__estado_confirmacion_caratula='confirmada')
    )


def _filtro_operacion_vigente_comision():
    """Operación no anulada/rescindida (sin exigir carátula confirmada)."""
    from django.db.models import Q

    return (
        ~Q(reserva__estado='cancelada')
        & ~Q(reserva__eliminada=True)
        & ~Q(contrato__estado='rescindido')
    )


def _marca_observacion_reversion_comision(comision_id):
    return f'reversion_comision_id={comision_id}'


def revertir_comisiones_operacion_anulada(*, reserva=None, contrato=None):
    """
    Al anular/cancelar una operación:
    - Pendientes: se cancelan (nunca se acreditaron).
    - Confirmadas/pagadas: se dejan como están (siguen sumando en el mes original)
      y se crea una línea negativa de devolución con fecha = día de la anulación,
      para que el descuento impacte en el mes en que se anula (no en el mes del cobro).
    No toca movimientos de caja.
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
    ahora = timezone.now()
    for comision in qs.select_related('vendedor'):
        if comision.estado in ('confirmada', 'pagada'):
            marca = _marca_observacion_reversion_comision(comision.pk)
            if ComisionVendedor.objects.filter(observaciones=marca).exclude(
                estado='cancelada'
            ).exists():
                continue
            monto = Decimal(str(comision.monto_comision or 0))
            if monto != 0:
                ref = (comision.concepto_operacion or '').strip() or 'comisión'
                op_ref = (
                    f'reserva #{comision.reserva_id}'
                    if comision.reserva_id
                    else f'contrato #{comision.contrato_id}'
                )
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
                    fecha_operacion=ahora,
                    estado='confirmada',
                    observaciones=marca,
                )
                creadas += 1
            # La comisión original se mantiene (confirmada/pagada) para no alterar el mes
            # en que se acreditó; el descuento va en la línea de devolución de hoy.
        else:
            # Pendientes u otros estados no acreditados: cancelar.
            ComisionVendedor.objects.filter(pk=comision.pk).update(estado='cancelada')
    return creadas


def restaurar_comisiones_operacion_recuperada(*, reserva=None, contrato=None):
    """
    Revierte el efecto de ``revertir_comisiones_operacion_anulada`` al recuperar la operación.
    Cancela las líneas de devolución. Reactiva comisiones que se habían cancelado por
    estar pendientes al anular (las confirmadas/pagadas nunca se cancelaron).
    """
    if not reserva and not contrato:
        return 0

    qs_rev = ComisionVendedor.objects.filter(rol_comision=ROL_COMISION_REVERSION)
    if reserva is not None:
        qs_rev = qs_rev.filter(reserva=reserva)
    else:
        qs_rev = qs_rev.filter(contrato=contrato)

    restauradas = 0
    for rev in qs_rev:
        obs = (rev.observaciones or '').strip()
        orig_id = None
        if obs.startswith('reversion_comision_id='):
            try:
                orig_id = int(obs.split('=', 1)[1].strip())
            except (TypeError, ValueError):
                orig_id = None
        if rev.estado != 'cancelada':
            ComisionVendedor.objects.filter(pk=rev.pk).update(estado='cancelada')
        if orig_id:
            # Solo reactivar si quedó cancelada (era pendiente al anular).
            updated = ComisionVendedor.objects.filter(pk=orig_id, estado='cancelada').update(
                estado='pendiente'
            )
            restauradas += int(updated or 0)
    return restauradas


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
    porcentaje_participacion = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('100'),
        verbose_name='% participación en la operación',
        help_text=(
            'Porcentaje de la operación que corresponde a este productor '
            '(ej. 50 si hay dos a partes iguales). Sobre esa parte se aplica su % de comisión.'
        ),
    )

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
        """
        Comisiones acreditadas o pagadas (y devoluciones por anulación).
        Las confirmadas/pagadas siguen sumando aunque la reserva se haya anulado después,
        para no alterar el mes en que se acreditaron; el descuento va en la línea de
        reversión fechada el día de la anulación.

        También suman las líneas en estado cancelada que tienen devolución asociada:
        a veces un recálculo marca cancelada la original aunque ya exista la reversión;
        si no las contáramos, el mes del descuento quedaría con el negativo huérfano
        (p. ej. +38.000 reales − 36.000 de una anulación = 2.000 en lugar de 38.000).

        No se exige carátula confirmada: si ya están acreditadas (confirmada/pagada),
        deben aparecer aunque la carátula haya quedado o vuelto a pendiente.
        """
        from django.db.models import CharField, Exists, OuterRef, Q, Value
        from django.db.models.functions import Cast, Concat

        operaciones_vigentes = _filtro_operacion_vigente_comision()
        # Históricas: operación ya anulada pero la comisión quedó acreditada/pagada.
        historicas_acreditadas = (
            Q(estado__in=('confirmada', 'pagada'))
            & ~Q(rol_comision=ROL_COMISION_REVERSION)
            & (
                Q(reserva__estado='cancelada')
                | Q(reserva__eliminada=True)
                | Q(contrato__estado='rescindido')
            )
        )
        tuvo_devolucion = Exists(
            self.model.objects.filter(
                rol_comision=ROL_COMISION_REVERSION,
                observaciones=Concat(
                    Value('reversion_comision_id='),
                    Cast(OuterRef('pk'), CharField()),
                ),
            )
        )
        creditadas = Q(estado__in=('confirmada', 'pagada')) & (
            Q(rol_comision=ROL_COMISION_REVERSION)
            | operaciones_vigentes
            | historicas_acreditadas
        )
        # Original cancelada con su línea de devolución: sigue contando el crédito del mes.
        originales_con_devolucion = (
            Q(estado='cancelada')
            & ~Q(rol_comision=ROL_COMISION_REVERSION)
            & tuvo_devolucion
        )
        return self.filter(creditadas | originales_con_devolucion)

    def visibles_en_historial(self):
        """Historial: acreditaciones, devoluciones, créditos históricos y pendientes de carátula confirmada."""
        from django.db.models import CharField, Exists, OuterRef, Q, Value
        from django.db.models.functions import Cast, Concat

        operaciones_vigentes = _filtro_operacion_vigente_comision()
        pendientes_visibles = (
            Q(estado='pendiente')
            & _filtro_caratula_confirmada_comision()
            & operaciones_vigentes
        )
        historicas_acreditadas = (
            Q(estado__in=('confirmada', 'pagada'))
            & ~Q(rol_comision=ROL_COMISION_REVERSION)
            & (
                Q(reserva__estado='cancelada')
                | Q(reserva__eliminada=True)
                | Q(contrato__estado='rescindido')
            )
        )
        tuvo_devolucion = Exists(
            self.model.objects.filter(
                rol_comision=ROL_COMISION_REVERSION,
                observaciones=Concat(
                    Value('reversion_comision_id='),
                    Cast(OuterRef('pk'), CharField()),
                ),
            )
        )
        acreditadas_visibles = Q(estado__in=('confirmada', 'pagada')) & (
            Q(rol_comision=ROL_COMISION_REVERSION)
            | operaciones_vigentes
            | historicas_acreditadas
        )
        return self.filter(
            pendientes_visibles
            | acreditadas_visibles
            | (Q(estado='cancelada') & tuvo_devolucion)
        )

    def ordenadas_para_listado_historial(self):
        """
        Misma fecha de operación: primero línea de fichaje, luego por día / invierno / 24 / general,
        devoluciones y créditos anulados al final del grupo.
        """
        from django.db.models import Case, IntegerField, When

        return self.annotate(
            _orden_grupo_rol=Case(
                When(rol_comision=ROL_COMISION_FICHAJE, then=0),
                When(rol_comision=ROL_COMISION_OP_DIA, then=1),
                When(rol_comision=ROL_COMISION_OP_INVIERNO, then=2),
                When(rol_comision=ROL_COMISION_OP_24, then=3),
                When(rol_comision=ROL_COMISION_GENERAL, then=4),
                When(rol_comision=ROL_COMISION_REVERSION, then=90),
                When(estado='cancelada', then=80),
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

    def label_estado_historial(self):
        """Etiqueta legible en historial (acreditación, devolución o anulación)."""
        if self._rol_comision_normalizado() == ROL_COMISION_REVERSION:
            return 'Devolución'
        if self.estado == 'cancelada':
            return 'Acreditada · anulada'
        if self.estado == 'confirmada':
            return 'Confirmada'
        if self.estado == 'pagada':
            return 'Pagada'
        if self.estado == 'pendiente':
            return 'Pendiente'
        return (self.estado or '—').title()

    def clase_badge_estado_historial(self):
        if self._rol_comision_normalizado() == ROL_COMISION_REVERSION:
            return 'badge-danger'
        if self.estado == 'cancelada':
            return 'badge-secondary'
        if self.estado == 'confirmada':
            return 'badge-success'
        if self.estado == 'pagada':
            return 'badge-primary'
        if self.estado == 'pendiente':
            return 'badge-warning'
        return 'badge-secondary'

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
        No recalcula monto de líneas ya confirmadas/pagadas (evita pisar el mínimo aplicado).
        """
        if porcentaje_comision is None or porcentaje_comision <= 0:
            return None
        if monto_base is None or monto_base <= 0:
            return None

        if getattr(reserva, 'eliminada', False) or getattr(reserva, 'estado', None) == 'cancelada':
            return None

        # Una línea activa por vendedor + reserva + rol (el movimiento es metadata).
        comision_existente = cls.objects.filter(
            vendedor=vendedor,
            reserva=reserva,
            rol_comision=rol_comision,
        ).exclude(estado='cancelada').first()

        if comision_existente:
            updates = []
            if movimiento_caja and not comision_existente.movimiento_caja_id:
                comision_existente.movimiento_caja = movimiento_caja
                updates.append('movimiento_caja')
            # No pisar fecha_operacion si ya tiene valor (editable en carátula).
            if comision_existente.fecha_operacion is None:
                comision_existente.fecha_operacion = _fecha_operacion_comision_reserva(
                    reserva, movimiento_caja
                )
                updates.append('fecha_operacion')
            # Confirmadas/pagadas: no tocar montos ni % (el piso $10.000 ya puede estar aplicado).
            if _comision_acreditada(comision_existente):
                if updates:
                    comision_existente.save(update_fields=updates)
                return comision_existente

            nuevo = (Decimal(str(monto_base)) * Decimal(str(porcentaje_comision))) / Decimal('100')
            nuevo = nuevo.quantize(Decimal('0.01'))
            if rol_comision in ROLES_COMISION_PRODUCTOR:
                nuevo = monto_comision_productor_con_minimo(
                    nuevo,
                    Decimal('100'),
                    sucursal=getattr(reserva, 'sucursal', None),
                )
            if comision_existente.monto_total_operacion != monto_base:
                comision_existente.monto_total_operacion = monto_base
                updates.append('monto_total_operacion')
            if comision_existente.monto_comision != nuevo:
                comision_existente.monto_comision = nuevo
                updates.append('monto_comision')
            if comision_existente.porcentaje_comision != porcentaje_comision:
                comision_existente.porcentaje_comision = porcentaje_comision
                updates.append('porcentaje_comision')
            if updates:
                comision_existente.save(update_fields=updates)
            return comision_existente

        monto_comision = (Decimal(str(monto_base)) * Decimal(str(porcentaje_comision))) / Decimal('100')
        monto_comision = monto_comision.quantize(Decimal('0.01'))
        if rol_comision in ROLES_COMISION_PRODUCTOR:
            monto_comision = monto_comision_productor_con_minimo(
                monto_comision,
                Decimal('100'),
                sucursal=getattr(reserva, 'sucursal', None),
            )
        return cls.objects.create(
            vendedor=vendedor,
            reserva=reserva,
            movimiento_caja=movimiento_caja,
            monto_total_operacion=monto_base,
            porcentaje_comision=porcentaje_comision,
            monto_comision=monto_comision,
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
        monto_comision = monto_comision.quantize(Decimal('0.01'))
        if rol_comision in ROLES_COMISION_PRODUCTOR:
            monto_comision = monto_comision_productor_con_minimo(
                monto_comision,
                Decimal('100'),
                sucursal=getattr(contrato, 'sucursal', None),
            )
        return cls.objects.create(
            vendedor=vendedor,
            contrato=contrato,
            movimiento_caja=movimiento_caja,
            monto_total_operacion=monto_base,
            porcentaje_comision=porcentaje_comision,
            monto_comision=monto_comision,
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
        if op.get('tipo') == 'division':
            for parte in op.get('operaciones') or []:
                if not isinstance(parte, dict):
                    continue
                if (parte.get('tipo') or '').strip().lower() != 'reserva' or not parte.get('id'):
                    continue
                try:
                    ids.add(int(parte['id']))
                except (TypeError, ValueError):
                    pass
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
    Tras confirmar la carátula: acredita comisiones pendientes de esa operación.
    La fecha_operacion sigue siendo el día de la operación; no se exige que ya haya pasado.
    """
    if not reserva and not contrato:
        return 0
    qs = ComisionVendedor.objects.filter(estado='pendiente').exclude(estado='cancelada')
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
    También marca la carátula como confirmada para que las comisiones aparezcan en el listado.
    """
    if not liquidacion or getattr(liquidacion, 'estado', None) == 'cancelada':
        return 0
    total = 0
    reserva_ids = _reserva_ids_desde_liquidacion(liquidacion)
    if reserva_ids:
        from inmobiliaria.models.propiedad import Reserva

        Reserva.objects.filter(
            pk__in=reserva_ids,
        ).exclude(estado_confirmacion_caratula='confirmada').update(
            estado_confirmacion_caratula='confirmada'
        )
        total += ComisionVendedor.objects.filter(
            reserva_id__in=reserva_ids,
            estado='pendiente',
        ).update(estado='confirmada')
    if liquidacion.contrato_id:
        from inmobiliaria.models.contrato import ContratoAlquiler

        ContratoAlquiler.objects.filter(
            pk=liquidacion.contrato_id,
        ).exclude(estado_confirmacion_caratula='confirmada').update(
            estado_confirmacion_caratula='confirmada'
        )
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
