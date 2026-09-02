"""
Honorarios / ganancias de oficina desde liquidaciones.
- Comisión inmobiliaria (reservas por día): Fecha op. (alta de la reserva).
- Cochera, fondo y comisiones locador/locatario: día de entrada al depto.
- Contratos: fecha de inicio del contrato.
"""
import re
from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from inmobiliaria.liquidacion_operacion import (
    ETIQUETAS_TIPO_OPERACION,
    contrato_desde_liquidacion,
    info_operacion_liquidacion,
    reserva_desde_liquidacion,
)
from inmobiliaria.models import ContratoAlquiler, LiquidacionPropietario


def _categoria_operacion_liquidacion(liq):
    """Clave de tipo de operación: dia | invierno | estudiante | 24 | otro."""
    return (info_operacion_liquidacion(liq).get('tipo_key') or '').strip()


def _etiqueta_operacion_liquidacion(liq):
    return info_operacion_liquidacion(liq).get('tipo_display') or '—'


def _parse_fecha(s):
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _fecha_entrada_liquidacion(liq):
    """
    Día de entrada del inquilino al depto (inicio estadía / contrato).
    Usado para cochera, fondo y comisiones locador/locatario.
    """
    reserva = getattr(liq, 'reserva', None) or reserva_desde_liquidacion(liq)
    if reserva and reserva.fecha_inicio:
        return reserva.fecha_inicio
    contrato = getattr(liq, 'contrato', None) or contrato_desde_liquidacion(liq)
    if contrato and contrato.fecha_inicio:
        return contrato.fecha_inicio
    if liq.fecha_desde:
        return liq.fecha_desde
    if liq.fecha_creacion:
        fc = liq.fecha_creacion
        return timezone.localtime(fc).date() if timezone.is_aware(fc) else fc.date()
    return None


def _fecha_operacion_reserva_honorarios(reserva):
    """
    Fecha de la operación en carátulas («Fecha op.»): alta de la reserva.
    No confundir con el día de entrada (fecha_inicio).
    """
    if not reserva:
        return None
    fc = getattr(reserva, 'fecha_creacion', None)
    if fc:
        return _datetime_a_fecha_local(fc)
    return getattr(reserva, 'fecha_inicio', None)


def _fecha_liquidacion(liq):
    if not liq.fecha_creacion:
        return None
    fc = liq.fecha_creacion
    return timezone.localtime(fc).date() if timezone.is_aware(fc) else fc.date()


def _datetime_a_fecha_local(dt):
    if not dt:
        return None
    if timezone.is_aware(dt):
        return timezone.localtime(dt).date()
    if hasattr(dt, 'date'):
        return dt.date()
    return dt


def _operacion_en_concepto_movimiento(concepto, operacion_id):
    if not concepto:
        return False
    return bool(re.search(rf'Operaci[oó]n\s*#?\s*{operacion_id}\b', concepto, re.IGNORECASE))


def _fecha_primer_ingreso_reserva(reserva):
    from inmobiliaria.models import MovimientoCaja
    from inmobiliaria.models.caja import TipoMovimientoCajaEnum

    if not reserva or not getattr(reserva, 'propiedad_id', None):
        return None
    qs = MovimientoCaja.objects.filter(
        propiedad_id=reserva.propiedad_id,
        sucursal_id=reserva.sucursal_id,
        tipo=TipoMovimientoCajaEnum.INGRESO,
    ).order_by('fecha', 'id')
    rid = int(reserva.pk)
    for mov in qs:
        if _operacion_en_concepto_movimiento(mov.concepto, rid):
            return _datetime_a_fecha_local(mov.fecha)
    return None


def _fecha_primer_ingreso_contrato(contrato):
    from inmobiliaria.cuotas_imputacion import movimientos_ingreso_contrato

    if not contrato:
        return None
    movs = sorted(movimientos_ingreso_contrato(contrato), key=lambda m: (m.fecha, m.id))
    if movs:
        return _datetime_a_fecha_local(movs[0].fecha)
    return None


def _fecha_acreditacion_comision_operacion(*, reserva=None, contrato=None):
    """Fecha en que se acreditó la comisión del productor (proxy del cobro)."""
    from inmobiliaria.models import ComisionVendedor
    from inmobiliaria.models.comision import ROL_COMISION_FICHAJE, ROL_COMISION_REVERSION

    qs = ComisionVendedor.objects.exclude(rol_comision=ROL_COMISION_REVERSION).exclude(
        rol_comision=ROL_COMISION_FICHAJE
    )
    if reserva is not None:
        qs = qs.filter(reserva=reserva)
    elif contrato is not None:
        qs = qs.filter(contrato=contrato)
    else:
        return None
    com = qs.order_by('fecha_operacion', 'id').first()
    if com and com.fecha_operacion:
        return _datetime_a_fecha_local(com.fecha_operacion)
    return None


def _fecha_ingreso_honorarios_comision(liq):
    """
    Comisión inmobiliaria / honorarios de oficina: fecha de acreditación de la
    operación (la misma que comisiones). Si no hay, Fecha op. (alta) o entrada.
    """
    from inmobiliaria.models.comision import fecha_acreditacion_compartida_operacion

    reserva = getattr(liq, 'reserva', None) or reserva_desde_liquidacion(liq)
    if reserva is not None:
        fa = fecha_acreditacion_compartida_operacion(reserva=reserva)
        if fa:
            return fa
        return _fecha_operacion_reserva_honorarios(reserva)
    contrato = getattr(liq, 'contrato', None) or contrato_desde_liquidacion(liq)
    if contrato is not None:
        fa = fecha_acreditacion_compartida_operacion(contrato=contrato)
        if fa:
            return fa
    return _fecha_entrada_liquidacion(liq)


def _fecha_ingreso_honorarios_oficina(liq):
    """
    Fecha de acreditación compartida para honorarios, cochera y fondo.
    Misma que la de comisiones vendedor de la operación.
    """
    from inmobiliaria.models.comision import fecha_acreditacion_compartida_operacion

    reserva = getattr(liq, 'reserva', None) or reserva_desde_liquidacion(liq)
    if reserva is not None:
        fa = fecha_acreditacion_compartida_operacion(reserva=reserva)
        if fa:
            return fa
        return _fecha_operacion_reserva_honorarios(reserva) or _fecha_entrada_liquidacion(liq)
    contrato = getattr(liq, 'contrato', None) or contrato_desde_liquidacion(liq)
    if contrato is not None:
        fa = fecha_acreditacion_compartida_operacion(contrato=contrato)
        if fa:
            return fa
    return _fecha_entrada_liquidacion(liq)


def _operacion_label(liq):
    if liq.reserva_id:
        return f'Reserva #{liq.reserva_id}'
    if liq.contrato_id:
        return f'Contrato #{liq.contrato_id}'
    reserva = reserva_desde_liquidacion(liq)
    if reserva:
        return f'Reserva #{reserva.id}'
    contrato = contrato_desde_liquidacion(liq)
    if contrato:
        return f'Contrato #{contrato.id}'
    return '—'


def _referencia_operacion_liquidacion(liq):
    reserva = getattr(liq, 'reserva', None) or reserva_desde_liquidacion(liq)
    if reserva is not None:
        return 'reserva', reserva.id
    contrato = getattr(liq, 'contrato', None) or contrato_desde_liquidacion(liq)
    if contrato is not None:
        return 'contrato', contrato.id
    return None, None


def _propiedad_txt(prop):
    if not prop:
        return '—'
    prop_txt = (prop.direccion or '—') or '—'
    if prop.piso or prop.departamento:
        extra = []
        if prop.piso:
            extra.append(f'Piso {prop.piso}')
        if prop.departamento:
            extra.append(f'Dpto {prop.departamento}')
        prop_txt = f'{prop_txt} ({", ".join(extra)})'
    return prop_txt


def _keys_comisiones_contrato_cubiertas(filas):
    """Operaciones que ya aportaron fila de comisiones locador/locatario."""
    cubiertos = set()
    for f in filas:
        if f.get('tipo') != 'comisiones_locador_locatario':
            continue
        kind = f.get('operacion_kind')
        pk = f.get('operacion_pk')
        if kind and pk:
            cubiertos.add((kind, pk))
    return cubiertos


def _fila_comisiones_locador_locatario(base, fecha, monto_locador, monto_locatario, nota=None):
    """Una sola fila con comisión locador y locatario de la misma operación."""
    monto_loc = Decimal(str(monto_locador or 0)).quantize(Decimal('0.01'))
    monto_locat = Decimal(str(monto_locatario or 0)).quantize(Decimal('0.01'))
    if abs(monto_loc) <= Decimal('0.01') and abs(monto_locat) <= Decimal('0.01'):
        return None
    return {
        **base,
        'tipo': 'comisiones_locador_locatario',
        'tipo_display': base.get('tipo_display') or 'Comisiones locador / locatario',
        'fecha': fecha,
        'monto_locador': monto_loc,
        'monto_locatario': monto_locat,
        'monto': (monto_loc + monto_locat).quantize(Decimal('0.01')),
        'nota': nota or base.get('nota') or 'Día de entrada',
    }


def _categoria_contrato_honorarios(contrato):
    if hasattr(contrato, 'categoria_tipo_operacion'):
        return contrato.categoria_tipo_operacion()
    meses = int(getattr(contrato, 'duracion_meses', None) or 0)
    if meses == 9:
        return 'invierno'
    if meses >= 9:
        return '24'
    return 'otro'


def _filas_honorarios_desde_caratulas_confirmadas(
    sucursal,
    fecha_desde,
    fecha_hasta,
    cubiertos_comisiones,
    busqueda='',
):
    """
    Comisiones locador/locatario de carátulas confirmadas aún sin liquidación al propietario.
    Usa los mismos importes que el cuadro de comisiones de la carátula.
    Fecha de la fila: acreditación (si hay) → día de entrada.
    """
    from inmobiliaria.views import _liquidacion_operacion_principal_contrato
    from inmobiliaria.views_caratulas import _comisiones_cobradas_contrato
    from inmobiliaria.models.comision import fecha_acreditacion_compartida_operacion

    filas = []
    qs = ContratoAlquiler.objects.filter(
        sucursal=sucursal,
        estado_confirmacion_caratula='confirmada',
    ).exclude(estado='rescindido').select_related('propiedad', 'propiedad__propietario', 'inquilino')

    # Prefetch por acreditación o entrada (no solo entrada: si no, cae en el mes equivocado).
    rango = Q()
    if fecha_desde and fecha_hasta:
        rango = (
            Q(fecha_inicio__gte=fecha_desde, fecha_inicio__lte=fecha_hasta)
            | Q(
                comisiones_vendedor__fecha_operacion__date__gte=fecha_desde,
                comisiones_vendedor__fecha_operacion__date__lte=fecha_hasta,
            )
        )
    elif fecha_desde:
        rango = (
            Q(fecha_inicio__gte=fecha_desde)
            | Q(comisiones_vendedor__fecha_operacion__date__gte=fecha_desde)
        )
    elif fecha_hasta:
        rango = (
            Q(fecha_inicio__lte=fecha_hasta)
            | Q(comisiones_vendedor__fecha_operacion__date__lte=fecha_hasta)
        )
    if rango:
        qs = qs.filter(rango).distinct()

    if busqueda:
        q_bus = (
            Q(propiedad__direccion__icontains=busqueda)
            | Q(propiedad__propietario__nombre__icontains=busqueda)
            | Q(propiedad__propietario__apellido__icontains=busqueda)
        )
        if busqueda.isdigit():
            try:
                q_bus |= Q(id=int(busqueda))
            except (TypeError, ValueError):
                pass
        qs = qs.filter(q_bus)

    for contrato in qs:
        op_key = ('contrato', contrato.id)
        liq_op = _liquidacion_operacion_principal_contrato(contrato)
        com_loc, com_locat = _comisiones_cobradas_contrato(contrato, liquidacion=liq_op)
        f_entrada = contrato.fecha_inicio
        f_acred = fecha_acreditacion_compartida_operacion(contrato=contrato)
        fecha_fila = f_acred or f_entrada
        if not fecha_fila:
            continue
        if fecha_desde and fecha_fila < fecha_desde:
            continue
        if fecha_hasta and fecha_fila > fecha_hasta:
            continue
        nota = 'Fecha de acreditación' if f_acred else 'Día de entrada'

        prop = contrato.propiedad
        propietario = getattr(prop, 'propietario', None) if prop else None
        cat = _categoria_contrato_honorarios(contrato)
        base = {
            'liquidacion_id': liq_op.id if liq_op else None,
            'liquidacion_url': (
                reverse('inmobiliaria:detalle_liquidacion', args=[liq_op.id])
                if liq_op
                else reverse('inmobiliaria:caratula_contrato', args=[contrato.id])
            ),
            'propiedad': _propiedad_txt(prop),
            'propietario': (
                f'{propietario.apellido}, {propietario.nombre}'
                if propietario
                else '—'
            ),
            'operacion': f'Contrato #{contrato.id}',
            'operacion_kind': 'contrato',
            'operacion_pk': contrato.id,
            'categoria_operacion': cat,
            'tipo_operacion_display': ETIQUETAS_TIPO_OPERACION.get(cat, cat),
            'estado_liq': liq_op.get_estado_display() if liq_op else 'Sin liquidar',
        }

        if op_key in cubiertos_comisiones:
            continue

        fila = _fila_comisiones_locador_locatario(
            base, fecha_fila, com_loc, com_locat, nota=nota
        )
        if fila:
            filas.append(fila)

    return filas


def _filas_honorarios_oficina_desde_caratulas_reserva(
    sucursal,
    fecha_desde,
    fecha_hasta,
    busqueda='',
):
    """
    Comisión inmobiliaria + cochera + fondo de TODA reserva con carátula confirmada.

    Usa los mismos montos que el cuadro de la carátula
    (``montos_reparto_reserva_para_caratula`` + cochera inquilino).
    Una fila por tipo e importe; no depende de que ``liq_monto_*`` esté seteado.

    Fecha del ingreso: acreditación de comisión (si está) → Fecha op. (alta) →
    entrada. No se incluye por fecha de entrada cuando la operación es de otro mes.
    """
    from inmobiliaria.liquidacion_operacion import (
        liquidaciones_activas_reserva,
        montos_reparto_reserva_para_caratula,
        _categoria_reserva,
    )
    from inmobiliaria.models import Reserva
    from inmobiliaria.models.comision import fecha_acreditacion_compartida_operacion

    filas = []
    qs = (
        Reserva.objects.filter(
            sucursal=sucursal,
            eliminada=False,
            estado_confirmacion_caratula='confirmada',
        )
        .exclude(estado='cancelada')
        .select_related('propiedad', 'propiedad__propietario', 'cliente')
    )
    # Prefiltro por fechas de operación / acreditación (no por día de entrada).
    rango = Q()
    if fecha_desde and fecha_hasta:
        rango = (
            Q(fecha_creacion__date__gte=fecha_desde, fecha_creacion__date__lte=fecha_hasta)
            | Q(
                comisiones_vendedor__fecha_operacion__date__gte=fecha_desde,
                comisiones_vendedor__fecha_operacion__date__lte=fecha_hasta,
            )
            | Q(fecha_inicio__gte=fecha_desde, fecha_inicio__lte=fecha_hasta)
        )
    elif fecha_desde:
        rango = (
            Q(fecha_creacion__date__gte=fecha_desde)
            | Q(comisiones_vendedor__fecha_operacion__date__gte=fecha_desde)
            | Q(fecha_inicio__gte=fecha_desde)
        )
    elif fecha_hasta:
        rango = (
            Q(fecha_creacion__date__lte=fecha_hasta)
            | Q(comisiones_vendedor__fecha_operacion__date__lte=fecha_hasta)
            | Q(fecha_inicio__lte=fecha_hasta)
        )
    if rango:
        qs = qs.filter(rango).distinct()
    if busqueda:
        q_bus = (
            Q(propiedad__direccion__icontains=busqueda)
            | Q(propiedad__propietario__nombre__icontains=busqueda)
            | Q(propiedad__propietario__apellido__icontains=busqueda)
            | Q(cliente__nombre__icontains=busqueda)
            | Q(cliente__apellido__icontains=busqueda)
        )
        if busqueda.isdigit():
            try:
                q_bus |= Q(id=int(busqueda))
            except (TypeError, ValueError):
                pass
        qs = qs.filter(q_bus)

    for reserva in qs.iterator(chunk_size=80):
        f_entrada = reserva.fecha_inicio
        f_acred = fecha_acreditacion_compartida_operacion(reserva=reserva)
        f_op = _fecha_operacion_reserva_honorarios(reserva)
        # Una sola fecha de negocio: no “traer” operaciones de otro mes por la entrada.
        fecha_fila = f_acred or f_op or f_entrada
        if not fecha_fila:
            continue
        if fecha_desde and fecha_fila < fecha_desde:
            continue
        if fecha_hasta and fecha_fila > fecha_hasta:
            continue

        _total, _prop, inm, coch, fondo = montos_reparto_reserva_para_caratula(reserva)
        inm = Decimal(str(inm or 0)).quantize(Decimal('0.01'))
        coch = Decimal(str(coch or 0)).quantize(Decimal('0.01'))
        fondo = Decimal(str(fondo or 0)).quantize(Decimal('0.01'))
        coch_inq = Decimal(
            str(getattr(reserva, 'liq_monto_cochera_inquilino', None) or 0)
        ).quantize(Decimal('0.01'))
        coch_total = (coch + coch_inq).quantize(Decimal('0.01'))

        if inm <= Decimal('0.01') and coch_total <= Decimal('0.01') and fondo <= Decimal('0.01'):
            continue

        if f_acred:
            nota = 'Carátula confirmada (fecha acreditación)'
        elif f_op:
            nota = 'Carátula confirmada (fecha operación)'
        else:
            nota = 'Carátula confirmada'

        liqs = liquidaciones_activas_reserva(reserva)
        try:
            cat = (_categoria_reserva(reserva) or 'dia').strip() or 'dia'
        except Exception:
            cat = 'dia'
        prop = reserva.propiedad
        propietario = getattr(prop, 'propietario', None) if prop else None
        ultima = liqs[-1] if liqs else None
        base = {
            'liquidacion_id': ultima.id if ultima else None,
            'liquidacion_url': (
                reverse('inmobiliaria:detalle_liquidacion', args=[ultima.id])
                if ultima
                else reverse('inmobiliaria:caratula_reserva', args=[reserva.id])
            ),
            'propiedad': _propiedad_txt(prop),
            'propietario': (
                f'{propietario.apellido}, {propietario.nombre}'
                if propietario
                else '—'
            ),
            'operacion': f'Reserva #{reserva.id}',
            'operacion_kind': 'reserva',
            'operacion_pk': reserva.id,
            'categoria_operacion': cat,
            'tipo_operacion_display': ETIQUETAS_TIPO_OPERACION.get(cat, cat),
            'estado_liq': (
                ultima.get_estado_display() if ultima else 'Sin liquidar'
            ),
        }
        if inm > Decimal('0.01'):
            filas.append({
                **base,
                'tipo': 'comision',
                'tipo_display': 'Comisión inmobiliaria',
                'fecha': fecha_fila,
                'monto': inm,
                'nota': nota,
            })
        if coch_total > Decimal('0.01'):
            filas.append({
                **base,
                'tipo': 'cochera',
                'tipo_display': 'Cochera',
                'fecha': fecha_fila,
                'monto': coch_total,
                'nota': nota,
            })
        if fondo > Decimal('0.01'):
            filas.append({
                **base,
                'tipo': 'fondo',
                'tipo_display': 'Fondo de mantenimiento',
                'fecha': fecha_fila,
                'monto': fondo,
                'nota': nota,
            })
    return filas


def _desglose_honorarios_oficina_contrato(contrato):
    """
    Comisión inmobiliaria de contratos (invierno / 24 meses) = locador + locatario,
    mismos importes que el cuadro de comisiones de la carátula.

    Fallback si aún no hay esas comisiones: concepto 25 / liquidación.
    Devuelve (monto_locador, monto_locatario, total_inmobiliaria).
    """
    from inmobiliaria.views import _liquidacion_operacion_principal_contrato
    from inmobiliaria.views_caratulas import (
        _comisiones_cobradas_contrato,
        _filas_honorarios_caratula_contrato,
    )

    liq = _liquidacion_operacion_principal_contrato(contrato)
    loc, locat = _comisiones_cobradas_contrato(contrato, liquidacion=liq)
    loc = Decimal(str(loc or 0)).quantize(Decimal('0.01'))
    locat = Decimal(str(locat or 0)).quantize(Decimal('0.01'))
    total = (loc + locat).quantize(Decimal('0.01'))
    if total > Decimal('0.01'):
        return loc, locat, total

    hon = Decimal('0')
    for fila in _filas_honorarios_caratula_contrato(contrato):
        if str(fila.get('codigo') or '').strip() == '25':
            hon += Decimal(str(fila.get('importe') or 0))
    if hon > Decimal('0.01'):
        return Decimal('0.00'), Decimal('0.00'), hon.quantize(Decimal('0.01'))
    if liq:
        inm = Decimal(str(getattr(liq, 'monto_inmobiliaria', 0) or 0))
        if inm > Decimal('0.01'):
            return Decimal('0.00'), Decimal('0.00'), inm.quantize(Decimal('0.01'))
    return Decimal('0.00'), Decimal('0.00'), Decimal('0.00')


def _monto_honorarios_oficina_contrato(contrato):
    """Honorarios de oficina del contrato = locador + locatario (o concepto 25)."""
    _loc, _locat, total = _desglose_honorarios_oficina_contrato(contrato)
    return total


def _filas_honorarios_oficina_desde_caratulas_contrato(
    sucursal,
    fecha_desde,
    fecha_hasta,
    busqueda='',
):
    """
    Comisión inmobiliaria de contratos (invierno / 24 meses) con carátula confirmada.
    Misma fecha que comisiones: acreditación → día de entrada.
    """
    from inmobiliaria.models.comision import fecha_acreditacion_compartida_operacion

    filas = []
    qs = (
        ContratoAlquiler.objects.filter(
            sucursal=sucursal,
            estado_confirmacion_caratula='confirmada',
        )
        .exclude(estado='rescindido')
        .select_related('propiedad', 'propiedad__propietario', 'inquilino')
    )
    rango = Q()
    if fecha_desde and fecha_hasta:
        rango = (
            Q(fecha_inicio__gte=fecha_desde, fecha_inicio__lte=fecha_hasta)
            | Q(
                comisiones_vendedor__fecha_operacion__date__gte=fecha_desde,
                comisiones_vendedor__fecha_operacion__date__lte=fecha_hasta,
            )
        )
    elif fecha_desde:
        rango = (
            Q(fecha_inicio__gte=fecha_desde)
            | Q(comisiones_vendedor__fecha_operacion__date__gte=fecha_desde)
        )
    elif fecha_hasta:
        rango = (
            Q(fecha_inicio__lte=fecha_hasta)
            | Q(comisiones_vendedor__fecha_operacion__date__lte=fecha_hasta)
        )
    if rango:
        qs = qs.filter(rango).distinct()
    if busqueda:
        q_bus = (
            Q(propiedad__direccion__icontains=busqueda)
            | Q(propiedad__propietario__nombre__icontains=busqueda)
            | Q(propiedad__propietario__apellido__icontains=busqueda)
            | Q(inquilino__nombre__icontains=busqueda)
            | Q(inquilino__apellido__icontains=busqueda)
        )
        if busqueda.isdigit():
            try:
                q_bus |= Q(id=int(busqueda))
            except (TypeError, ValueError):
                pass
        qs = qs.filter(q_bus)

    for contrato in qs:
        f_entrada = contrato.fecha_inicio
        f_acred = fecha_acreditacion_compartida_operacion(contrato=contrato)
        fecha_fila = f_acred or f_entrada
        if not fecha_fila:
            continue
        if fecha_desde and fecha_fila < fecha_desde:
            continue
        if fecha_hasta and fecha_fila > fecha_hasta:
            continue

        loc, locat, inm = _desglose_honorarios_oficina_contrato(contrato)
        if inm <= Decimal('0.01'):
            continue

        from inmobiliaria.views import _liquidacion_operacion_principal_contrato

        liq_op = _liquidacion_operacion_principal_contrato(contrato)
        prop = contrato.propiedad
        propietario = getattr(prop, 'propietario', None) if prop else None
        cat = _categoria_contrato_honorarios(contrato)
        if loc > Decimal('0.01') or locat > Decimal('0.01'):
            nota = (
                'Locador + locatario (fecha acreditación)'
                if f_acred
                else 'Locador + locatario (día de entrada)'
            )
        else:
            nota = (
                'Carátula confirmada (fecha acreditación)'
                if f_acred
                else 'Carátula confirmada (día de entrada)'
            )
        base = {
            'liquidacion_id': liq_op.id if liq_op else None,
            'liquidacion_url': (
                reverse('inmobiliaria:detalle_liquidacion', args=[liq_op.id])
                if liq_op
                else reverse('inmobiliaria:caratula_contrato', args=[contrato.id])
            ),
            'propiedad': _propiedad_txt(prop),
            'propietario': (
                f'{propietario.apellido}, {propietario.nombre}'
                if propietario
                else '—'
            ),
            'operacion': f'Contrato #{contrato.id}',
            'operacion_kind': 'contrato',
            'operacion_pk': contrato.id,
            'categoria_operacion': cat,
            'tipo_operacion_display': ETIQUETAS_TIPO_OPERACION.get(cat, cat),
            'estado_liq': liq_op.get_estado_display() if liq_op else 'Sin liquidar',
        }
        fila = {
            **base,
            'tipo': 'comision',
            'tipo_display': 'Comisión inmobiliaria',
            'fecha': fecha_fila,
            'monto': inm,
            'nota': nota,
        }
        if loc > Decimal('0.01') or locat > Decimal('0.01'):
            fila['monto_locador'] = loc
            fila['monto_locatario'] = locat
            fila['desglose_locador_locatario'] = True
        filas.append(fila)
    return filas


def _filas_honorarios_cochera_fondo_desde_reservas(
    sucursal,
    fecha_desde,
    fecha_hasta,
    busqueda='',
):
    """Compat: delega al listado unificado de oficina desde carátulas."""
    return _filas_honorarios_oficina_desde_caratulas_reserva(
        sucursal, fecha_desde, fecha_hasta, busqueda=busqueda
    )


def _fecha_reversion_honorarios(liq, when_dt=None):
    """Fecha del asiento negativo por anulación."""
    if when_dt is not None:
        fd = _datetime_a_fecha_local(when_dt)
        if fd:
            return fd
    reserva = getattr(liq, 'reserva', None) or reserva_desde_liquidacion(liq)
    if reserva is not None and getattr(reserva, 'fecha_eliminacion', None):
        fd = _datetime_a_fecha_local(reserva.fecha_eliminacion)
        if fd:
            return fd
    if liq.fecha_procesamiento and getattr(liq, 'estado', None) == 'cancelada':
        fd = _datetime_a_fecha_local(liq.fecha_procesamiento)
        if fd:
            return fd
    return timezone.localdate()


def _operacion_anulada_desde_liquidacion(liq):
    """True si la operación vinculada fue anulada o la liquidación quedó cancelada."""
    reserva = getattr(liq, 'reserva', None) or reserva_desde_liquidacion(liq)
    if reserva is not None:
        if getattr(reserva, 'eliminada', False):
            return True, getattr(reserva, 'fecha_eliminacion', None)
        if (getattr(reserva, 'estado', None) or '').strip() == 'cancelada':
            return True, getattr(reserva, 'fecha_eliminacion', None)
    contrato = getattr(liq, 'contrato', None) or contrato_desde_liquidacion(liq)
    if contrato is not None and (getattr(contrato, 'estado', None) or '').strip() == 'rescindido':
        return True, None
    if getattr(liq, 'estado', None) == 'cancelada':
        return True, liq.fecha_procesamiento
    return False, None


def _incluir_liquidacion_honorarios_positivos(liq):
    """
    Ingreso en el listado solo si la carátula estuvo confirmada.
    (Si después se anuló, se mantiene el flag confirmada y aparece + la fila roja.)
    """
    return _liquidacion_tuvo_caratula_confirmada(liq)


def _filas_reversion_honorarios_liquidacion(liq, base):
    """Asientos negativos al anular operación con carátula confirmada."""
    anulada, when_dt = _operacion_anulada_desde_liquidacion(liq)
    if not anulada:
        return []
    # Sin confirmación previa no hubo ingreso de oficina → no hay anulación que listar.
    if not _liquidacion_tuvo_caratula_confirmada(liq):
        return []

    fecha_rev = _fecha_reversion_honorarios(liq, when_dt)
    filas = []
    nota = 'Anulación operación'

    monto_inm = Decimal(str(liq.monto_inmobiliaria or 0))
    res = getattr(liq, 'reserva', None)
    if res is not None and getattr(res, 'liq_monto_inmobiliaria', None) is not None:
        monto_inm = Decimal(str(res.liq_monto_inmobiliaria)).quantize(Decimal('0.01'))
    if monto_inm > Decimal('0.01'):
        filas.append({
            **base,
            'tipo': 'comision',
            'tipo_display': 'Comisión inmobiliaria (anulación)',
            'fecha': fecha_rev,
            'monto': (-monto_inm).quantize(Decimal('0.01')),
            'nota': nota,
            'es_reversion': True,
        })

    f_entrada = _fecha_entrada_liquidacion(liq)
    monto_coch = Decimal(str(liq.monto_cochera or 0))
    if res is not None and getattr(res, 'liq_monto_cochera', None) is not None:
        monto_coch = (
            Decimal(str(res.liq_monto_cochera or 0))
            + Decimal(str(getattr(res, 'liq_monto_cochera_inquilino', None) or 0))
        ).quantize(Decimal('0.01'))
    if monto_coch > Decimal('0.01'):
        filas.append({
            **base,
            'tipo': 'cochera',
            'tipo_display': 'Cochera (anulación)',
            'fecha': fecha_rev,
            'monto': (-monto_coch).quantize(Decimal('0.01')),
            'nota': nota,
            'es_reversion': True,
        })

    monto_fondo = Decimal(str(liq.monto_fondo_mantenimiento or 0))
    if res is not None and getattr(res, 'liq_monto_fondo', None) is not None:
        monto_fondo = Decimal(str(res.liq_monto_fondo or 0)).quantize(Decimal('0.01'))
    if monto_fondo > Decimal('0.01'):
        filas.append({
            **base,
            'tipo': 'fondo',
            'tipo_display': 'Fondo de mantenimiento (anulación)',
            'fecha': fecha_rev,
            'monto': (-monto_fondo).quantize(Decimal('0.01')),
            'nota': nota,
            'es_reversion': True,
        })

    monto_com_loc = Decimal(str(liq.comision_locador or 0))
    monto_com_locat = Decimal(str(liq.comision_locatario or 0))
    fila = _fila_comisiones_locador_locatario(
        {
            **base,
            'tipo_display': 'Comisiones locador / locatario (anulación)',
            'nota': nota,
            'es_reversion': True,
        },
        fecha_rev,
        -monto_com_loc if monto_com_loc > Decimal('0.01') else Decimal('0'),
        -monto_com_locat if monto_com_locat > Decimal('0.01') else Decimal('0'),
    )
    if fila and (monto_com_loc > Decimal('0.01') or monto_com_locat > Decimal('0.01')):
        filas.append(fila)

    return filas


def _caratula_confirmada_vigente_reserva(reserva):
    if not reserva:
        return False
    if getattr(reserva, 'eliminada', False):
        return False
    if (getattr(reserva, 'estado', None) or '').strip() == 'cancelada':
        return False
    return (getattr(reserva, 'estado_confirmacion_caratula', None) or 'pendiente') == 'confirmada'


def _caratula_confirmada_vigente_contrato(contrato):
    if not contrato:
        return False
    if (getattr(contrato, 'estado', None) or '').strip() == 'rescindido':
        return False
    return (getattr(contrato, 'estado_confirmacion_caratula', None) or 'pendiente') == 'confirmada'


def _operacion_tuvo_caratula_confirmada(reserva=None, contrato=None):
    """
    True si la carátula llegó a confirmarse (aunque después se anule/elimine).
    Sin confirmación no hay honorarios de oficina ni fila de anulación.
    """
    if reserva is not None:
        return (getattr(reserva, 'estado_confirmacion_caratula', None) or '').strip() == 'confirmada'
    if contrato is not None:
        return (getattr(contrato, 'estado_confirmacion_caratula', None) or '').strip() == 'confirmada'
    return False


def _liquidacion_tuvo_caratula_confirmada(liq):
    """Misma regla sobre la reserva/contrato de la liquidación."""
    reserva = getattr(liq, 'reserva', None) or reserva_desde_liquidacion(liq)
    if reserva is not None:
        return _operacion_tuvo_caratula_confirmada(reserva=reserva)
    contrato = getattr(liq, 'contrato', None) or contrato_desde_liquidacion(liq)
    if contrato is not None:
        return _operacion_tuvo_caratula_confirmada(contrato=contrato)
    return False


def _estado_confirmacion_operacion_liquidacion(liq):
    """Estado de carátula de la reserva o contrato vinculado a la liquidación."""
    reserva = getattr(liq, 'reserva', None)
    if reserva is not None:
        if not _caratula_confirmada_vigente_reserva(reserva):
            return 'pendiente'
        return getattr(reserva, 'estado_confirmacion_caratula', None) or 'pendiente'
    contrato = getattr(liq, 'contrato', None)
    if contrato is not None:
        if not _caratula_confirmada_vigente_contrato(contrato):
            return 'pendiente'
        return getattr(contrato, 'estado_confirmacion_caratula', None) or 'pendiente'
    reserva = reserva_desde_liquidacion(liq)
    if reserva is not None:
        if not _caratula_confirmada_vigente_reserva(reserva):
            return 'pendiente'
        return getattr(reserva, 'estado_confirmacion_caratula', None) or 'pendiente'
    contrato = contrato_desde_liquidacion(liq)
    if contrato is not None:
        if not _caratula_confirmada_vigente_contrato(contrato):
            return 'pendiente'
        return getattr(contrato, 'estado_confirmacion_caratula', None) or 'pendiente'
    return None


def _liquidacion_caratula_confirmada(liq):
    """Solo ingresan honorarios de operaciones con carátula confirmada."""
    estado = _estado_confirmacion_operacion_liquidacion(liq)
    return estado == 'confirmada'


def _filas_honorarios_desde_liquidaciones(liquidaciones):
    filas = []
    # Si la carátula define el monto de oficina, emitirlo una sola vez por operación.
    # Si no, cada liquidación aporta su propio importe (liquidaciones parciales).
    override_oficina_emitido = set()  # (op_kind, op_pk, tipo)

    for liq in liquidaciones:
        prop = liq.propiedad
        prop_txt = _propiedad_txt(prop)
        op_kind, op_pk = _referencia_operacion_liquidacion(liq)

        categoria_op = _categoria_operacion_liquidacion(liq)
        tipo_op_display = _etiqueta_operacion_liquidacion(liq)

        base = {
            'liquidacion_id': liq.id,
            'liquidacion_url': reverse('inmobiliaria:detalle_liquidacion', args=[liq.id]),
            'propiedad': prop_txt,
            'propietario': (
                f'{liq.propietario.apellido}, {liq.propietario.nombre}'
                if liq.propietario_id
                else '—'
            ),
            'operacion': _operacion_label(liq),
            'operacion_kind': op_kind,
            'operacion_pk': op_pk,
            'categoria_operacion': categoria_op,
            'tipo_operacion_display': tipo_op_display,
            'estado_liq': liq.get_estado_display(),
        }

        if _incluir_liquidacion_honorarios_positivos(liq):
            res = getattr(liq, 'reserva', None) or reserva_desde_liquidacion(liq)
            contrato_liq = getattr(liq, 'contrato', None) or contrato_desde_liquidacion(liq)
            f_acred = _fecha_ingreso_honorarios_oficina(liq)
            f_entrada = _fecha_entrada_liquidacion(liq)

            # Reserva/contrato con carátula confirmada: comisión/cochera/fondo
            # los lista el armado desde carátula (mismos montos que el cuadro).
            oficina_desde_caratula = bool(
                (res is not None and _caratula_confirmada_vigente_reserva(res))
                or (
                    contrato_liq is not None
                    and _caratula_confirmada_vigente_contrato(contrato_liq)
                )
            )

            # --- Comisión inmobiliaria ---
            monto_inm = Decimal(str(liq.monto_inmobiliaria or 0))
            key_inm = (op_kind, op_pk, 'comision')
            if oficina_desde_caratula:
                monto_inm = Decimal('0')
            elif res is not None and getattr(res, 'liq_monto_inmobiliaria', None) is not None:
                if key_inm in override_oficina_emitido:
                    monto_inm = Decimal('0')
                else:
                    monto_inm = Decimal(str(res.liq_monto_inmobiliaria)).quantize(Decimal('0.01'))
            elif key_inm in override_oficina_emitido:
                monto_inm = Decimal('0')
            if monto_inm > Decimal('0.01'):
                filas.append({
                    **base,
                    'tipo': 'comision',
                    'tipo_display': 'Comisión inmobiliaria',
                    'fecha': f_acred,
                    'monto': monto_inm,
                    'nota': 'Fecha de acreditación',
                })
                if res is not None and getattr(res, 'liq_monto_inmobiliaria', None) is not None:
                    override_oficina_emitido.add(key_inm)

            # --- Cochera ---
            monto_coch = Decimal(str(liq.monto_cochera or 0))
            if oficina_desde_caratula:
                monto_coch = Decimal('0')
            if monto_coch > Decimal('0.01'):
                filas.append({
                    **base,
                    'tipo': 'cochera',
                    'tipo_display': 'Cochera',
                    'fecha': f_acred,
                    'monto': monto_coch,
                    'nota': 'Fecha de acreditación',
                })

            # --- Fondo ---
            monto_fondo = Decimal(str(liq.monto_fondo_mantenimiento or 0))
            if oficina_desde_caratula:
                monto_fondo = Decimal('0')
            if monto_fondo > Decimal('0.01'):
                filas.append({
                    **base,
                    'tipo': 'fondo',
                    'tipo_display': 'Fondo de mantenimiento',
                    'fecha': f_acred,
                    'monto': monto_fondo,
                    'nota': 'Fecha de acreditación',
                })

            monto_com_loc = Decimal(str(liq.comision_locador or 0))
            monto_com_locat = Decimal(str(liq.comision_locatario or 0))
            from inmobiliaria.models.comision import fecha_acreditacion_compartida_operacion
            fa_com = None
            if res is not None:
                fa_com = fecha_acreditacion_compartida_operacion(reserva=res)
            if fa_com is None:
                ctr = getattr(liq, 'contrato', None) or contrato_desde_liquidacion(liq)
                if ctr is not None:
                    fa_com = fecha_acreditacion_compartida_operacion(contrato=ctr)
            f_com = fa_com or f_entrada
            nota_com = 'Fecha de acreditación' if fa_com else 'Día de entrada'
            fila = _fila_comisiones_locador_locatario(
                base, f_com, monto_com_loc, monto_com_locat, nota=nota_com
            )
            if fila:
                filas.append(fila)

        filas.extend(_filas_reversion_honorarios_liquidacion(liq, base))

    return filas


def _como_fecha(valor):
    """Normaliza date/datetime para comparar sin TypeError."""
    if not valor:
        return None
    if isinstance(valor, datetime):
        return _datetime_a_fecha_local(valor)
    if isinstance(valor, date):
        return valor
    return _datetime_a_fecha_local(valor)


def _filtrar_filas_por_fecha(filas, fecha_desde, fecha_hasta):
    out = []
    for f in filas:
        fd = _como_fecha(f.get('fecha'))
        if not fd:
            continue
        if fecha_desde and fd < fecha_desde:
            continue
        if fecha_hasta and fd > fecha_hasta:
            continue
        f = {**f, 'fecha': fd}
        out.append(f)
    out.sort(
        key=lambda x: (
            x.get('fecha') or date.min,
            x.get('tipo', ''),
            x.get('liquidacion_id') or 0,
            x.get('operacion_pk') or 0,
        ),
        reverse=True,
    )
    return out


def _filtrar_filas_por_operacion(filas, operacion_filtro):
    """Filtra por tipo de operación: 24meses | invierno | dia."""
    if not operacion_filtro:
        return filas
    if operacion_filtro == '24meses':
        keys = {'24'}
    elif operacion_filtro == 'invierno':
        keys = {'invierno', 'estudiante'}
    elif operacion_filtro == 'dia':
        keys = {'dia'}
    else:
        return filas
    return [f for f in filas if f.get('categoria_operacion') in keys]


def _q_busqueda_honorarios_liquidacion(busqueda):
    """Filtro de búsqueda: dirección, persona, nº liquidación / reserva / contrato / propiedad."""
    q_bus = (
        Q(propiedad__direccion__icontains=busqueda)
        | Q(propietario__nombre__icontains=busqueda)
        | Q(propietario__apellido__icontains=busqueda)
        | Q(id__icontains=busqueda)
    )
    if busqueda.isdigit():
        try:
            n = int(busqueda)
        except (TypeError, ValueError):
            n = None
        if n is not None:
            q_bus |= (
                Q(id=n)
                | Q(reserva_id=n)
                | Q(contrato_id=n)
                | Q(propiedad_id=n)
            )
    return q_bus


def _filtrar_filas_por_busqueda(filas, busqueda):
    """Respaldo: filtrar filas ya armadas por texto / nº de operación o liquidación."""
    if not busqueda:
        return filas
    b = busqueda.strip().casefold()
    if not b:
        return filas
    out = []
    for f in filas:
        partes = [
            str(f.get('propiedad') or ''),
            str(f.get('propietario') or ''),
            str(f.get('operacion') or ''),
            str(f.get('liquidacion_id') or ''),
            str(f.get('operacion_pk') or ''),
            str(f.get('tipo_display') or ''),
        ]
        if b in ' '.join(partes).casefold():
            out.append(f)
            continue
        if busqueda.isdigit():
            try:
                n = int(busqueda)
            except (TypeError, ValueError):
                n = None
            if n is not None and (
                f.get('liquidacion_id') == n
                or f.get('operacion_pk') == n
            ):
                out.append(f)
    return out


def _ops_comision_con_desglose(filas):
    keys = set()
    for f in filas:
        if f.get('tipo') != 'comision' or not f.get('desglose_locador_locatario'):
            continue
        kind = f.get('operacion_kind')
        pk = f.get('operacion_pk')
        if kind and pk:
            keys.add((kind, pk))
    return keys


def _ocultar_locador_duplicado_de_inmobiliaria(filas):
    """Si inmobiliaria ya es locador+locatario, no listar de nuevo esas comisiones."""
    ops = _ops_comision_con_desglose(filas)
    if not ops:
        return filas
    out = []
    for f in filas:
        if f.get('tipo') == 'comisiones_locador_locatario':
            key = (f.get('operacion_kind'), f.get('operacion_pk'))
            if key in ops:
                continue
        out.append(f)
    return out


def _totales_honorarios_oficina(filas):
    """
    Totales de badges. Comisión inmobiliaria de contratos ya incluye locador+locatario:
    no se suman otra vez al total del período.
    """
    ops_loc = {
        (f.get('operacion_kind'), f.get('operacion_pk'))
        for f in filas
        if f.get('tipo') == 'comisiones_locador_locatario'
        and f.get('operacion_kind')
        and f.get('operacion_pk')
    }
    ops_inmob = {
        (f.get('operacion_kind'), f.get('operacion_pk'))
        for f in filas
        if f.get('tipo') == 'comision'
        and f.get('operacion_kind')
        and f.get('operacion_pk')
    }

    total_comision = sum(
        (f['monto'] for f in filas if f.get('tipo') == 'comision'),
        Decimal('0'),
    )
    total_cochera = sum(
        (f['monto'] for f in filas if f.get('tipo') == 'cochera'),
        Decimal('0'),
    )
    total_fondo = sum(
        (f['monto'] for f in filas if f.get('tipo') == 'fondo'),
        Decimal('0'),
    )

    total_locador = Decimal('0')
    total_locatario = Decimal('0')
    for f in filas:
        tipo = f.get('tipo')
        if tipo == 'comisiones_locador_locatario':
            total_locador += Decimal(str(f.get('monto_locador') or 0))
            total_locatario += Decimal(str(f.get('monto_locatario') or 0))
        elif tipo == 'comision' and f.get('desglose_locador_locatario'):
            key = (f.get('operacion_kind'), f.get('operacion_pk'))
            if key in ops_loc:
                continue
            total_locador += Decimal(str(f.get('monto_locador') or 0))
            total_locatario += Decimal(str(f.get('monto_locatario') or 0))
        elif tipo == 'comision_locador':
            total_locador += Decimal(str(f.get('monto') or 0))
        elif tipo == 'comision_locatario':
            total_locatario += Decimal(str(f.get('monto') or 0))

    total_general = Decimal('0')
    for f in filas:
        if f.get('tipo') == 'comisiones_locador_locatario':
            key = (f.get('operacion_kind'), f.get('operacion_pk'))
            if key in ops_inmob:
                continue
        total_general += Decimal(str(f.get('monto') or 0))

    return {
        'total_general': total_general,
        'total_comision': total_comision,
        'total_comision_locador': total_locador,
        'total_comision_locatario': total_locatario,
        'total_cochera': total_cochera,
        'total_fondo': total_fondo,
    }


def _contexto_honorarios_oficina(request, *, solo_oficina=False):
    """
    Arma el contexto del listado de honorarios.
    Si solo_oficina=True, limita a comisión inmobiliaria + cochera + fondo
    (salvo que el usuario ya haya elegido un tipo concreto en GET).
    """
    hoy = timezone.localdate()
    primer_dia_mes = hoy.replace(day=1)

    fecha_desde_s = (request.GET.get('fecha_desde') or '').strip()
    fecha_hasta_s = (request.GET.get('fecha_hasta') or '').strip()
    tipo_filtro = (request.GET.get('tipo') or '').strip()
    operacion_filtro = (request.GET.get('operacion') or '').strip()
    busqueda = (request.GET.get('q') or '').strip()

    fecha_desde = _parse_fecha(fecha_desde_s) or primer_dia_mes
    fecha_hasta = _parse_fecha(fecha_hasta_s) or hoy
    if fecha_desde > fecha_hasta:
        fecha_desde, fecha_hasta = fecha_hasta, fecha_desde

    qs = (
        LiquidacionPropietario.objects.filter(sucursal=request.user.sucursal)
        .select_related('propietario', 'propiedad', 'reserva', 'contrato')
        .order_by('-fecha_creacion')
    )

    if busqueda:
        qs = qs.filter(_q_busqueda_honorarios_liquidacion(busqueda))

    # Traer liquidaciones que puedan aportar filas en el rango (ingreso o reversión por anulación)
    qs = qs.filter(
        Q(fecha_creacion__date__gte=fecha_desde, fecha_creacion__date__lte=fecha_hasta)
        | Q(fecha_desde__gte=fecha_desde, fecha_desde__lte=fecha_hasta)
        | Q(reserva__fecha_inicio__gte=fecha_desde, reserva__fecha_inicio__lte=fecha_hasta)
        | Q(reserva__fecha_creacion__date__gte=fecha_desde, reserva__fecha_creacion__date__lte=fecha_hasta)
        | Q(contrato__fecha_inicio__gte=fecha_desde, contrato__fecha_inicio__lte=fecha_hasta)
        | Q(
            fecha_procesamiento__date__gte=fecha_desde,
            fecha_procesamiento__date__lte=fecha_hasta,
            estado='cancelada',
        )
        | Q(
            reserva__fecha_eliminacion__date__gte=fecha_desde,
            reserva__fecha_eliminacion__date__lte=fecha_hasta,
        )
        | Q(
            reserva__comisiones_vendedor__fecha_operacion__date__gte=fecha_desde,
            reserva__comisiones_vendedor__fecha_operacion__date__lte=fecha_hasta,
        )
        | Q(
            contrato__comisiones_vendedor__fecha_operacion__date__gte=fecha_desde,
            contrato__comisiones_vendedor__fecha_operacion__date__lte=fecha_hasta,
        )
    ).distinct()

    filas_liq = _filtrar_filas_por_fecha(_filas_honorarios_desde_liquidaciones(qs), fecha_desde, fecha_hasta)
    cubiertos_comisiones = _keys_comisiones_contrato_cubiertas(filas_liq)

    from inmobiliaria.honorarios_anulacion import (
        filas_honorarios_reserva_anulada_legacy,
        ids_reservas_cubiertas_por_liquidaciones,
        queryset_reservas_anuladas_legacy,
    )

    reservas_cubiertas = ids_reservas_cubiertas_por_liquidaciones(qs)
    filas_legacy = []
    for reserva in queryset_reservas_anuladas_legacy(
        request.user.sucursal, fecha_desde, fecha_hasta, busqueda=busqueda
    ):
        if reserva.id in reservas_cubiertas:
            continue
        filas_legacy.extend(
            filas_honorarios_reserva_anulada_legacy(
                reserva, _propiedad_txt, _fila_comisiones_locador_locatario
            )
        )
    filas_legacy = _filtrar_filas_por_fecha(filas_legacy, fecha_desde, fecha_hasta)

    filas_car = _filas_honorarios_desde_caratulas_confirmadas(
        request.user.sucursal,
        fecha_desde,
        fecha_hasta,
        cubiertos_comisiones,
        busqueda=busqueda,
    )
    filas_car_cochera = _filas_honorarios_oficina_desde_caratulas_reserva(
        request.user.sucursal,
        fecha_desde,
        fecha_hasta,
        busqueda=busqueda,
    )
    filas_car_contrato = _filas_honorarios_oficina_desde_caratulas_contrato(
        request.user.sucursal,
        fecha_desde,
        fecha_hasta,
        busqueda=busqueda,
    )
    filas = _filtrar_filas_por_fecha(
        filas_liq + filas_car + filas_car_cochera + filas_car_contrato + filas_legacy,
        fecha_desde,
        fecha_hasta,
    )
    filas = _filtrar_filas_por_operacion(filas, operacion_filtro)
    filas = _filtrar_filas_por_busqueda(filas, busqueda)

    if tipo_filtro == 'comision_locador':
        filas = [
            f for f in filas
            if f.get('tipo') == 'comisiones_locador_locatario'
            and abs(f.get('monto_locador') or Decimal('0')) > Decimal('0.01')
        ]
    elif tipo_filtro == 'comision_locatario':
        filas = [
            f for f in filas
            if f.get('tipo') == 'comisiones_locador_locatario'
            and abs(f.get('monto_locatario') or Decimal('0')) > Decimal('0.01')
        ]
    elif tipo_filtro in ('comision', 'cochera', 'fondo'):
        filas = [f for f in filas if f['tipo'] == tipo_filtro]
    elif solo_oficina:
        # Impresión: honorario de oficina + cochera + fondo (sin locador/locatario).
        filas = [f for f in filas if f.get('tipo') in ('comision', 'cochera', 'fondo')]
    else:
        # Todos: inmobiliaria de contratos ya es locador+locatario; no duplicar filas.
        filas = _ocultar_locador_duplicado_de_inmobiliaria(filas)

    totales = _totales_honorarios_oficina(filas)
    querystring = request.GET.urlencode()

    return {
        'filas': filas,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'fecha_desde_s': fecha_desde.strftime('%Y-%m-%d'),
        'fecha_hasta_s': fecha_hasta.strftime('%Y-%m-%d'),
        'tipo_filtro': tipo_filtro,
        'operacion_filtro': operacion_filtro,
        'busqueda': busqueda,
        **totales,
        'querystring': querystring,
        'sucursal': getattr(request.user, 'sucursal', None),
        'solo_oficina': solo_oficina and not tipo_filtro,
    }


@login_required
def honorarios_oficina(request):
    """
    Listado de ganancias que ingresan a la oficina, filtrable por fecha.
    """
    return render(
        request,
        'inmobiliaria/honorarios/lista.html',
        _contexto_honorarios_oficina(request),
    )


@login_required
def honorarios_oficina_imprimir(request):
    """
    Versión para imprimir: honorario de oficina, fondo y cochera del período filtrado.
    """
    return render(
        request,
        'inmobiliaria/honorarios/imprimir.html',
        _contexto_honorarios_oficina(request, solo_oficina=True),
    )
