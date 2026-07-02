"""
Honorarios / ganancias de oficina desde liquidaciones.
- Comisión inmobiliaria: ingresa al crear la liquidación (fecha_creacion).
- Cochera, fondo y comisiones locador/locatario: día de entrada del depto (inicio reserva o contrato).
"""
from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from inmobiliaria.liquidacion_operacion import (
    contrato_desde_liquidacion,
    info_operacion_liquidacion,
    reserva_desde_liquidacion,
)
from inmobiliaria.models import LiquidacionPropietario


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
    Día de entrada del inquilino al depto (operación), no el inicio del período liquidado.
    En contratos 24 meses / invierno, la liquidación puede tener fecha_desde = mes de la cuota
    (ej. 01/07) aunque el contrato empiece antes (ej. 01/06).
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
    reserva = reserva_desde_liquidacion(liq)
    if reserva:
        return f'Reserva #{reserva.id}'
    contrato = contrato_desde_liquidacion(liq)
    if contrato:
        return f'Contrato #{contrato.id}'
    return '—'


def _estado_confirmacion_operacion_liquidacion(liq):
    """Estado de carátula de la reserva o contrato vinculado a la liquidación."""
    reserva = getattr(liq, 'reserva', None)
    if reserva is not None:
        return getattr(reserva, 'estado_confirmacion_caratula', None) or 'pendiente'
    contrato = getattr(liq, 'contrato', None)
    if contrato is not None:
        return getattr(contrato, 'estado_confirmacion_caratula', None) or 'pendiente'
    reserva = reserva_desde_liquidacion(liq)
    if reserva is not None:
        return getattr(reserva, 'estado_confirmacion_caratula', None) or 'pendiente'
    contrato = contrato_desde_liquidacion(liq)
    if contrato is not None:
        return getattr(contrato, 'estado_confirmacion_caratula', None) or 'pendiente'
    return None


def _liquidacion_caratula_confirmada(liq):
    """Solo ingresan honorarios de operaciones con carátula confirmada."""
    estado = _estado_confirmacion_operacion_liquidacion(liq)
    return estado == 'confirmada'


def _filas_honorarios_desde_liquidaciones(liquidaciones):
    filas = []
    for liq in liquidaciones:
        if not _liquidacion_caratula_confirmada(liq):
            continue
        prop = liq.propiedad
        prop_txt = (prop.direccion if prop else '—') or '—'
        if prop and (prop.piso or prop.departamento):
            extra = []
            if prop.piso:
                extra.append(f'Piso {prop.piso}')
            if prop.departamento:
                extra.append(f'Dpto {prop.departamento}')
            prop_txt = f'{prop_txt} ({", ".join(extra)})'

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
            'categoria_operacion': categoria_op,
            'tipo_operacion_display': tipo_op_display,
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

        monto_com_loc = Decimal(str(liq.comision_locador or 0))
        if monto_com_loc > Decimal('0.01'):
            filas.append({
                **base,
                'tipo': 'comision_locador',
                'tipo_display': 'Comisión locador',
                'fecha': f_entrada,
                'monto': monto_com_loc,
                'nota': 'Día de entrada',
            })

        monto_com_locat = Decimal(str(liq.comision_locatario or 0))
        if monto_com_locat > Decimal('0.01'):
            filas.append({
                **base,
                'tipo': 'comision_locatario',
                'tipo_display': 'Comisión locatario',
                'fecha': f_entrada,
                'monto': monto_com_locat,
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
    filas = _filtrar_filas_por_operacion(filas, operacion_filtro)

    if tipo_filtro in ('comision', 'cochera', 'fondo', 'comision_locador', 'comision_locatario'):
        filas = [f for f in filas if f['tipo'] == tipo_filtro]

    total_general = sum((f['monto'] for f in filas), Decimal('0'))
    total_comision = sum((f['monto'] for f in filas if f['tipo'] == 'comision'), Decimal('0'))
    total_comision_locador = sum(
        (f['monto'] for f in filas if f['tipo'] == 'comision_locador'), Decimal('0')
    )
    total_comision_locatario = sum(
        (f['monto'] for f in filas if f['tipo'] == 'comision_locatario'), Decimal('0')
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
