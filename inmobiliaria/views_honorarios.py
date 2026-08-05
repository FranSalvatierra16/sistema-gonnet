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
    Comisión inmobiliaria: Fecha op. de la reserva (alta), no el día de entrada.
    Contratos: día de inicio del contrato.
    """
    reserva = getattr(liq, 'reserva', None) or reserva_desde_liquidacion(liq)
    if reserva is not None:
        return _fecha_operacion_reserva_honorarios(reserva)
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


def _fila_comisiones_locador_locatario(base, f_entrada, monto_locador, monto_locatario):
    """Una sola fila con comisión locador y locatario de la misma operación."""
    monto_loc = Decimal(str(monto_locador or 0)).quantize(Decimal('0.01'))
    monto_locat = Decimal(str(monto_locatario or 0)).quantize(Decimal('0.01'))
    if abs(monto_loc) <= Decimal('0.01') and abs(monto_locat) <= Decimal('0.01'):
        return None
    return {
        **base,
        'tipo': 'comisiones_locador_locatario',
        'tipo_display': 'Comisiones locador / locatario',
        'fecha': f_entrada,
        'monto_locador': monto_loc,
        'monto_locatario': monto_locat,
        'monto': (monto_loc + monto_locat).quantize(Decimal('0.01')),
        'nota': 'Día de entrada',
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
    """
    from inmobiliaria.views import _liquidacion_operacion_principal_contrato
    from inmobiliaria.views_caratulas import _comisiones_cobradas_contrato

    filas = []
    qs = ContratoAlquiler.objects.filter(
        sucursal=sucursal,
        estado_confirmacion_caratula='confirmada',
    ).exclude(estado='rescindido').select_related('propiedad', 'propiedad__propietario', 'inquilino')

    if fecha_desde:
        qs = qs.filter(fecha_inicio__gte=fecha_desde)
    if fecha_hasta:
        qs = qs.filter(fecha_inicio__lte=fecha_hasta)

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
        if not f_entrada:
            continue

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

        fila = _fila_comisiones_locador_locatario(base, f_entrada, com_loc, com_locat)
        if fila:
            filas.append(fila)

    return filas


def _filas_honorarios_cochera_fondo_desde_reservas(
    sucursal,
    fecha_desde,
    fecha_hasta,
    busqueda='',
):
    """
    Cochera (oficina + inquilino) y fondo desde montos de carátula.

    Si ya hay liquidaciones, solo muestra lo que aún no se liquidó en esas filas
    (evita duplicar y permite ver cochera inquilino cargada después).
    """
    from inmobiliaria.liquidacion_operacion import liquidaciones_activas_reserva
    from inmobiliaria.models import Reserva

    filas = []
    qs = (
        Reserva.objects.filter(
            sucursal=sucursal,
            eliminada=False,
        )
        .exclude(estado='cancelada')
        .select_related('propiedad', 'propiedad__propietario')
    )
    if fecha_desde:
        qs = qs.filter(fecha_inicio__gte=fecha_desde)
    if fecha_hasta:
        qs = qs.filter(fecha_inicio__lte=fecha_hasta)
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

    for reserva in qs.iterator(chunk_size=100):
        f_entrada = reserva.fecha_inicio
        if not f_entrada:
            continue
        try:
            coch_total = reserva.cochera_oficina_total_liquidacion()
        except Exception:
            coch_total = (
                Decimal(str(reserva.liq_monto_cochera or 0))
                + Decimal(str(getattr(reserva, 'liq_monto_cochera_inquilino', None) or 0))
            ).quantize(Decimal('0.01'))
        fondo_total = Decimal(str(reserva.liq_monto_fondo or 0)).quantize(Decimal('0.01'))
        if coch_total <= Decimal('0.01') and fondo_total <= Decimal('0.01'):
            continue

        liqs = liquidaciones_activas_reserva(reserva)
        coch_ya = sum(
            (Decimal(str(getattr(liq, 'monto_cochera', None) or 0)) for liq in liqs),
            Decimal('0'),
        ).quantize(Decimal('0.01'))
        fondo_ya = sum(
            (
                Decimal(str(getattr(liq, 'monto_fondo_mantenimiento', None) or 0))
                for liq in liqs
            ),
            Decimal('0'),
        ).quantize(Decimal('0.01'))
        coch = (coch_total - coch_ya).quantize(Decimal('0.01'))
        fondo = (fondo_total - fondo_ya).quantize(Decimal('0.01'))
        if coch < 0:
            coch = Decimal('0.00')
        if fondo < 0:
            fondo = Decimal('0.00')
        if coch <= Decimal('0.01') and fondo <= Decimal('0.01'):
            continue

        prop = reserva.propiedad
        propietario = getattr(prop, 'propietario', None) if prop else None
        caratula_ok = (
            getattr(reserva, 'estado_confirmacion_caratula', None) or 'pendiente'
        ) == 'confirmada'
        nota = (
            'Carátula (sin liquidar)'
            if not liqs
            else 'Carátula (pendiente de liquidar en cochera/fondo)'
        )
        if not caratula_ok:
            nota = f'{nota} — carátula pendiente de confirmar'
        base = {
            'liquidacion_id': None,
            'liquidacion_url': reverse('inmobiliaria:caratula_reserva', args=[reserva.id]),
            'propiedad': _propiedad_txt(prop),
            'propietario': (
                f'{propietario.apellido}, {propietario.nombre}'
                if propietario
                else '—'
            ),
            'operacion': f'Reserva #{reserva.id}',
            'operacion_kind': 'reserva',
            'operacion_pk': reserva.id,
            'categoria_operacion': 'dia',
            'tipo_operacion_display': ETIQUETAS_TIPO_OPERACION.get('dia', 'Por día'),
            'estado_liq': 'Sin liquidar' if not liqs else 'Parcial / carátula',
        }
        if coch > Decimal('0.01'):
            filas.append({
                **base,
                'tipo': 'cochera',
                'tipo_display': 'Cochera',
                'fecha': f_entrada,
                'monto': coch,
                'nota': nota,
            })
        if fondo > Decimal('0.01'):
            filas.append({
                **base,
                'tipo': 'fondo',
                'tipo_display': 'Fondo de mantenimiento',
                'fecha': f_entrada,
                'monto': fondo,
                'nota': nota,
            })
    return filas


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
    """Ingresos históricos: carátula confirmada vigente, liquidación cancelada u operación ya anulada."""
    if getattr(liq, 'estado', None) == 'cancelada':
        return True
    anulada, _ = _operacion_anulada_desde_liquidacion(liq)
    if anulada:
        return True
    return _liquidacion_caratula_confirmada(liq)


def _filas_reversion_honorarios_liquidacion(liq, base):
    """Asientos negativos al anular operación con carátula confirmada."""
    anulada, when_dt = _operacion_anulada_desde_liquidacion(liq)
    if not anulada:
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
            monto_inm = Decimal(str(liq.monto_inmobiliaria or 0))
            # Preferir override de carátula si existe (corrige liquidaciones desfasadas).
            res = getattr(liq, 'reserva', None)
            if res is not None and getattr(res, 'liq_monto_inmobiliaria', None) is not None:
                monto_inm = Decimal(str(res.liq_monto_inmobiliaria)).quantize(Decimal('0.01'))
            if monto_inm > Decimal('0.01'):
                filas.append({
                    **base,
                    'tipo': 'comision',
                    'tipo_display': 'Comisión inmobiliaria',
                    'fecha': _fecha_ingreso_honorarios_comision(liq),
                    'monto': monto_inm,
                    'nota': 'Día de la operación',
                })

            f_entrada = _fecha_entrada_liquidacion(liq)
            monto_coch = Decimal(str(liq.monto_cochera or 0))
            if res is not None and getattr(res, 'liq_monto_cochera', None) is not None:
                monto_coch = Decimal(str(res.liq_monto_cochera or 0)).quantize(Decimal('0.01'))
                coch_inq = Decimal(str(getattr(res, 'liq_monto_cochera_inquilino', None) or 0))
                monto_coch = (monto_coch + coch_inq).quantize(Decimal('0.01'))
            if monto_coch > Decimal('0.01'):
                filas.append({
                    **base,
                    'tipo': 'cochera',
                    'tipo_display': 'Cochera',
                    'fecha': f_entrada,
                    'monto': monto_coch,
                    'nota': 'Día de entrada',
                })

            monto_fondo = Decimal(str(liq.monto_fondo_mantenimiento or 0))
            if res is not None and getattr(res, 'liq_monto_fondo', None) is not None:
                monto_fondo = Decimal(str(res.liq_monto_fondo or 0)).quantize(Decimal('0.01'))
            if monto_fondo > Decimal('0.01'):
                filas.append({
                    **base,
                    'tipo': 'fondo',
                    'tipo_display': 'Fondo de mantenimiento',
                    'fecha': f_entrada,
                    'monto': monto_fondo,
                    'nota': 'Día de entrada',
                })

            monto_com_loc = Decimal(str(liq.comision_locador or 0))
            monto_com_locat = Decimal(str(liq.comision_locatario or 0))
            fila = _fila_comisiones_locador_locatario(base, f_entrada, monto_com_loc, monto_com_locat)
            if fila:
                filas.append(fila)

        filas.extend(_filas_reversion_honorarios_liquidacion(liq, base))

    return filas


def _filtrar_filas_por_fecha(filas, fecha_desde, fecha_hasta):
    out = []
    for f in filas:
        fd = f.get('fecha')
        if not fd:
            continue
        if fecha_desde and fd < fecha_desde:
            continue
        if fecha_hasta and fd > fecha_hasta:
            continue
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


@login_required
def honorarios_oficina(request):
    """
    Listado de ganancias que ingresan a la oficina, filtrable por fecha.
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
        qs = qs.filter(
            Q(propiedad__direccion__icontains=busqueda)
            | Q(propietario__nombre__icontains=busqueda)
            | Q(propietario__apellido__icontains=busqueda)
            | Q(id__icontains=busqueda)
        )

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
    filas_car_cochera = _filas_honorarios_cochera_fondo_desde_reservas(
        request.user.sucursal,
        fecha_desde,
        fecha_hasta,
        busqueda=busqueda,
    )
    filas = _filtrar_filas_por_fecha(
        filas_liq + filas_car + filas_car_cochera + filas_legacy,
        fecha_desde,
        fecha_hasta,
    )
    filas = _filtrar_filas_por_operacion(filas, operacion_filtro)

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

    total_general = sum((f['monto'] for f in filas), Decimal('0'))
    total_comision = sum((f['monto'] for f in filas if f['tipo'] == 'comision'), Decimal('0'))
    total_comision_locador = sum(
        (
            (
                f.get('monto_locador')
                if f.get('tipo') == 'comisiones_locador_locatario'
                else (f['monto'] if f.get('tipo') == 'comision_locador' else Decimal('0'))
            )
            for f in filas
        ),
        Decimal('0'),
    )
    total_comision_locatario = sum(
        (
            (
                f.get('monto_locatario')
                if f.get('tipo') == 'comisiones_locador_locatario'
                else (f['monto'] if f.get('tipo') == 'comision_locatario' else Decimal('0'))
            )
            for f in filas
        ),
        Decimal('0'),
    )
    total_cochera = sum((f['monto'] for f in filas if f['tipo'] == 'cochera'), Decimal('0'))
    total_fondo = sum((f['monto'] for f in filas if f['tipo'] == 'fondo'), Decimal('0'))

    return render(
        request,
        'inmobiliaria/honorarios/lista.html',
        {
            'filas': filas,
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'fecha_desde_s': fecha_desde.strftime('%Y-%m-%d'),
            'fecha_hasta_s': fecha_hasta.strftime('%Y-%m-%d'),
            'tipo_filtro': tipo_filtro,
            'operacion_filtro': operacion_filtro,
            'busqueda': busqueda,
            'total_general': total_general,
            'total_comision': total_comision,
            'total_comision_locador': total_comision_locador,
            'total_comision_locatario': total_comision_locatario,
            'total_cochera': total_cochera,
            'total_fondo': total_fondo,
        },
    )
