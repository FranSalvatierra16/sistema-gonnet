"""
Honorarios / ganancias de oficina desde liquidaciones.
- Comisión inmobiliaria: ingresa al crear la liquidación (fecha_creacion).
- Cochera y fondo de mantenimiento: ingresan el día de entrada del depto (fecha_desde / inicio reserva o contrato).
"""
from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from inmobiliaria.models import LiquidacionPropietario


def _parse_fecha(s):
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _fecha_entrada_liquidacion(liq):
    """Día de entrada del depto para cochera / fondo."""
    if liq.fecha_desde:
        return liq.fecha_desde
    reserva = getattr(liq, 'reserva', None)
    if reserva and reserva.fecha_inicio:
        return reserva.fecha_inicio
    contrato = getattr(liq, 'contrato', None)
    if contrato and contrato.fecha_inicio:
        return contrato.fecha_inicio
    if liq.fecha_creacion:
        fc = liq.fecha_creacion
        return timezone.localtime(fc).date() if timezone.is_aware(fc) else fc.date()
    return None


def _fecha_liquidacion(liq):
    if not liq.fecha_creacion:
        return None
    fc = liq.fecha_creacion
    return timezone.localtime(fc).date() if timezone.is_aware(fc) else fc.date()


def _operacion_label(liq):
    if liq.reserva_id:
        return f'Reserva #{liq.reserva_id}'
    if liq.contrato_id:
        return f'Contrato #{liq.contrato_id}'
    return '—'


def _filas_honorarios_desde_liquidaciones(liquidaciones):
    filas = []
    for liq in liquidaciones:
        prop = liq.propiedad
        prop_txt = (prop.direccion if prop else '—') or '—'
        if prop and (prop.piso or prop.departamento):
            extra = []
            if prop.piso:
                extra.append(f'Piso {prop.piso}')
            if prop.departamento:
                extra.append(f'Dpto {prop.departamento}')
            prop_txt = f'{prop_txt} ({", ".join(extra)})'

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
            'estado_liq': liq.get_estado_display(),
        }

        monto_inm = Decimal(str(liq.monto_inmobiliaria or 0))
        if monto_inm > Decimal('0.01'):
            filas.append({
                **base,
                'tipo': 'comision',
                'tipo_display': 'Comisión inmobiliaria',
                'fecha': _fecha_liquidacion(liq),
                'monto': monto_inm,
                'nota': 'Al liquidar',
            })

        f_entrada = _fecha_entrada_liquidacion(liq)
        monto_coch = Decimal(str(liq.monto_cochera or 0))
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
        if monto_fondo > Decimal('0.01'):
            filas.append({
                **base,
                'tipo': 'fondo',
                'tipo_display': 'Fondo de mantenimiento',
                'fecha': f_entrada,
                'monto': monto_fondo,
                'nota': 'Día de entrada',
            })

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
    out.sort(key=lambda x: (x.get('fecha') or date.min, x.get('tipo', ''), x.get('liquidacion_id', 0)), reverse=True)
    return out


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
    busqueda = (request.GET.get('q') or '').strip()

    fecha_desde = _parse_fecha(fecha_desde_s) or primer_dia_mes
    fecha_hasta = _parse_fecha(fecha_hasta_s) or hoy
    if fecha_desde > fecha_hasta:
        fecha_desde, fecha_hasta = fecha_hasta, fecha_desde

    qs = (
        LiquidacionPropietario.objects.filter(sucursal=request.user.sucursal)
        .exclude(estado='cancelada')
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

    # Traer liquidaciones que puedan aportar filas en el rango (creación o entrada)
    qs = qs.filter(
        Q(fecha_creacion__date__gte=fecha_desde, fecha_creacion__date__lte=fecha_hasta)
        | Q(fecha_desde__gte=fecha_desde, fecha_desde__lte=fecha_hasta)
        | Q(reserva__fecha_inicio__gte=fecha_desde, reserva__fecha_inicio__lte=fecha_hasta)
        | Q(contrato__fecha_inicio__gte=fecha_desde, contrato__fecha_inicio__lte=fecha_hasta)
    ).distinct()

    filas = _filtrar_filas_por_fecha(_filas_honorarios_desde_liquidaciones(qs), fecha_desde, fecha_hasta)

    if tipo_filtro in ('comision', 'cochera', 'fondo'):
        filas = [f for f in filas if f['tipo'] == tipo_filtro]

    total_general = sum((f['monto'] for f in filas), Decimal('0'))
    total_comision = sum((f['monto'] for f in filas if f['tipo'] == 'comision'), Decimal('0'))
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
            'busqueda': busqueda,
            'total_general': total_general,
            'total_comision': total_comision,
            'total_cochera': total_cochera,
            'total_fondo': total_fondo,
        },
    )
