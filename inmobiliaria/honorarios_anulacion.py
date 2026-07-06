"""
Honorarios de oficina para operaciones anuladas cuya liquidación fue eliminada
(antes de conservar liquidaciones canceladas al anular desde carátula).
"""
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from inmobiliaria.liquidacion_operacion import reserva_desde_liquidacion
from inmobiliaria.models import LiquidacionPropietario, Reserva


def liquidaciones_reserva_cualquier_estado(reserva):
    """Todas las liquidaciones ligadas a la reserva (incluye canceladas)."""
    rid = int(reserva.pk)
    sucursal = getattr(reserva, 'sucursal', None)
    candidatas = list(LiquidacionPropietario.objects.filter(reserva_id=rid))
    vistos = {liq.pk for liq in candidatas}
    qs_extra = LiquidacionPropietario.objects.exclude(pk__in=vistos)
    if sucursal is not None:
        qs_extra = qs_extra.filter(sucursal=sucursal)
    for liq in qs_extra.only('id', 'operaciones_incluidas').iterator(chunk_size=200):
        for op in liq.operaciones_incluidas or []:
            if not isinstance(op, dict):
                continue
            if (op.get('tipo') or '').lower() != 'reserva':
                continue
            try:
                if int(op.get('id')) == rid:
                    candidatas.append(liq)
                    vistos.add(liq.pk)
                    break
            except (TypeError, ValueError):
                continue
    return candidatas


def reserva_esta_anulada(reserva):
    if not reserva:
        return False
    if getattr(reserva, 'eliminada', False):
        return True
    return (getattr(reserva, 'estado', None) or '').strip() == 'cancelada'


def montos_honorarios_desde_reserva(reserva):
    """Montos de honorarios inferidos desde la reserva (carátula / liquidación eliminada)."""
    total = Decimal(str(reserva.precio_total or 0))
    if total <= Decimal('0.01'):
        return None

    propiedad = getattr(reserva, 'propiedad', None)
    pct = getattr(propiedad, 'porcentaje_propietario', None) if propiedad else None
    if pct is None or pct <= 0:
        pct = Decimal('70')
    else:
        pct = Decimal(str(pct))

    prop = (total * pct / Decimal('100')).quantize(Decimal('0.01'))
    inm = (total - prop).quantize(Decimal('0.01'))
    total, prop, inm, coch, fondo = reserva.montos_liquidacion_efectivos(total, prop, inm)

    return {
        'monto_inmobiliaria': inm,
        'monto_cochera': coch,
        'monto_fondo': fondo,
        'monto_propietario': prop,
        'monto_total': total,
    }


def reserva_anulada_requiere_reversion_legacy(reserva):
    """
    Reserva anulada sin liquidación en BD que debió haber generado honorarios.
    Evita reversión en reservas eliminadas sin liquidar nunca.
    """
    if not reserva_esta_anulada(reserva):
        return False
    if liquidaciones_reserva_cualquier_estado(reserva):
        return False

    montos = montos_honorarios_desde_reserva(reserva)
    if not montos:
        return False
    if montos['monto_inmobiliaria'] <= Decimal('0.01') and montos['monto_cochera'] <= Decimal('0.01') and montos['monto_fondo'] <= Decimal('0.01'):
        return False

    if reserva.liq_monto_inmobiliaria is not None or reserva.liq_monto_propietario is not None:
        return True
    if getattr(reserva, 'usuario_eliminacion_id', None):
        return True
    if getattr(reserva, 'fecha_eliminacion', None):
        return True
    return False


def ids_reservas_cubiertas_por_liquidaciones(liquidaciones):
    """Reservas que ya aportan filas vía liquidación (positivas o reversión)."""
    cubiertas = set()
    for liq in liquidaciones:
        if liq.reserva_id:
            cubiertas.add(int(liq.reserva_id))
        reserva = reserva_desde_liquidacion(liq)
        if reserva is not None:
            cubiertas.add(int(reserva.id))
    return cubiertas


def _fecha_reversion_reserva(reserva):
    when = getattr(reserva, 'fecha_eliminacion', None)
    if when is not None:
        if timezone.is_aware(when):
            return timezone.localtime(when).date()
        if hasattr(when, 'date'):
            return when.date()
        return when
    return timezone.localdate()


def _inferir_fecha_liquidacion_reserva(reserva):
    """Fecha del ingreso original (liquidación eliminada): movimiento de caja anulado o fallback."""
    from inmobiliaria.models.caja import MovimientoCaja, TipoMovimientoCajaEnum

    propiedad_id = getattr(reserva, 'propiedad_id', None)
    rid = int(reserva.pk)
    if propiedad_id:
        movs = MovimientoCaja.all_objects.filter(
            propiedad_id=propiedad_id,
            tipo=TipoMovimientoCajaEnum.EGRESO,
            fecha_eliminacion__isnull=False,
        ).order_by('-fecha_eliminacion', '-fecha')
        for mov in movs[:30]:
            texto = f'{mov.concepto or ""} {mov.concepto_detalle or ""} {mov.numero_liquidacion or ""}'
            if str(rid) in texto:
                fc = mov.fecha
                if fc:
                    return timezone.localtime(fc).date() if timezone.is_aware(fc) else fc.date()

    if getattr(reserva, 'fecha_eliminacion', None):
        when = reserva.fecha_eliminacion
        fc = timezone.localtime(when) if timezone.is_aware(when) else when
        return fc.date() if hasattr(fc, 'date') else reserva.fecha_inicio
    return reserva.fecha_inicio


def filas_honorarios_reserva_anulada_legacy(reserva, propiedad_txt_fn, fila_comisiones_fn):
    """
    Filas positivas (liquidación eliminada) + negativas (anulación) para reservas legacy.
    propiedad_txt_fn / fila_comisiones_fn: helpers del módulo de honorarios (evita duplicar plantilla).
    """
    if not reserva_anulada_requiere_reversion_legacy(reserva):
        return []

    from inmobiliaria.models.comision import clasificar_tipo_operacion_reserva
    from django.urls import reverse

    montos = montos_honorarios_desde_reserva(reserva)
    if not montos:
        return []

    prop = getattr(reserva, 'propiedad', None)
    propietario = getattr(prop, 'propietario', None) if prop else None
    cat = clasificar_tipo_operacion_reserva(reserva) or 'dia'

    base = {
        'liquidacion_id': None,
        'liquidacion_url': reverse('inmobiliaria:caratula_reserva', args=[reserva.id]),
        'propiedad': propiedad_txt_fn(prop),
        'propietario': (
            f'{propietario.apellido}, {propietario.nombre}'
            if propietario
            else '—'
        ),
        'operacion': f'Reserva #{reserva.id}',
        'operacion_kind': 'reserva',
        'operacion_pk': reserva.id,
        'categoria_operacion': cat,
        'tipo_operacion_display': cat,
        'estado_liq': 'Operación anulada',
    }

    filas = []
    fecha_liq = _inferir_fecha_liquidacion_reserva(reserva)
    fecha_rev = _fecha_reversion_reserva(reserva)

    inm = montos['monto_inmobiliaria']
    if inm > Decimal('0.01'):
        filas.append({
            **base,
            'tipo': 'comision',
            'tipo_display': 'Comisión inmobiliaria',
            'fecha': fecha_liq,
            'monto': inm,
            'nota': 'Al liquidar',
        })
        filas.append({
            **base,
            'tipo': 'comision',
            'tipo_display': 'Comisión inmobiliaria (anulación)',
            'fecha': fecha_rev,
            'monto': (-inm).quantize(Decimal('0.01')),
            'nota': 'Anulación operación',
            'es_reversion': True,
        })

    coch = montos['monto_cochera']
    fondo = montos['monto_fondo']
    f_entrada = reserva.fecha_inicio or fecha_liq
    if coch > Decimal('0.01'):
        filas.append({
            **base,
            'tipo': 'cochera',
            'tipo_display': 'Cochera',
            'fecha': f_entrada,
            'monto': coch,
            'nota': 'Día de entrada',
        })
        filas.append({
            **base,
            'tipo': 'cochera',
            'tipo_display': 'Cochera (anulación)',
            'fecha': fecha_rev,
            'monto': (-coch).quantize(Decimal('0.01')),
            'nota': 'Anulación operación',
            'es_reversion': True,
        })

    if fondo > Decimal('0.01'):
        filas.append({
            **base,
            'tipo': 'fondo',
            'tipo_display': 'Fondo de mantenimiento',
            'fecha': f_entrada,
            'monto': fondo,
            'nota': 'Día de entrada',
        })
        filas.append({
            **base,
            'tipo': 'fondo',
            'tipo_display': 'Fondo de mantenimiento (anulación)',
            'fecha': fecha_rev,
            'monto': (-fondo).quantize(Decimal('0.01')),
            'nota': 'Anulación operación',
            'es_reversion': True,
        })

    return filas


def queryset_reservas_anuladas_legacy(sucursal, fecha_desde, fecha_hasta, busqueda=''):
    """Reservas anuladas que pueden aportar filas legacy (ingreso o anulación en el rango)."""
    qs = Reserva.objects.filter(sucursal=sucursal).filter(
        Q(eliminada=True) | Q(estado='cancelada')
    ).select_related('propiedad', 'propiedad__propietario')

    if fecha_desde or fecha_hasta:
        fd = fecha_desde
        fh = fecha_hasta
        q_fecha = Q()
        if fd and fh:
            q_fecha = (
                Q(fecha_eliminacion__date__gte=fd, fecha_eliminacion__date__lte=fh)
                | Q(fecha_inicio__gte=fd, fecha_inicio__lte=fh)
            )
        elif fd:
            q_fecha = Q(fecha_eliminacion__date__gte=fd) | Q(fecha_inicio__gte=fd)
        elif fh:
            q_fecha = Q(fecha_eliminacion__date__lte=fh) | Q(fecha_inicio__lte=fh)
        qs = qs.filter(q_fecha)

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

    return qs
