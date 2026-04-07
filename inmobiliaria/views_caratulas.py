"""
Consulta de carátulas: listado y detalle de operaciones (reservas por día, invierno, 24 meses).
"""
import re
from datetime import datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Prefetch, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from inmobiliaria.models import (
    ComisionVendedor,
    ContratoAlquiler,
    CuotaMensual,
    MovimientoCaja,
    Recibo,
    Reserva,
)
from inmobiliaria.models.caja import TipoMovimientoCajaEnum


def _puede_ver_caratulas(user):
    return bool(getattr(user, 'is_superuser', False) or getattr(user, 'nivel', None) == 4)


def _caratula_nombre_cliente(cliente):
    if not cliente:
        return '—'
    ap = (getattr(cliente, 'apellido', None) or '').strip()
    nom = (getattr(cliente, 'nombre', None) or '').strip()
    s = f'{ap}, {nom}'.strip(', ').strip()
    return s if s else '—'


def _tipo_reserva(propiedad):
    if not propiedad:
        return 'Por día'
    if getattr(propiedad, 'tipo_cliente', None) == 'ESTUDIANTE':
        return 'Estudiante'
    return 'Por día'


@login_required
def lista_caratulas(request):
    """Tabla tipo consultorio: tipo, número, fecha, carátula, dirección, piso/depto, ficha."""
    if not _puede_ver_caratulas(request.user):
        return HttpResponseForbidden()
    sucursal = getattr(request.user, 'sucursal', None)
    q = request.GET.get('q', '').strip()
    fecha_desde = request.GET.get('fecha_desde', '').strip()
    fecha_hasta = request.GET.get('fecha_hasta', '').strip()
    tipo_filtro = request.GET.get('tipo', '').strip()

    if not sucursal:
        paginator_empty = Paginator([], 40)
        return render(
            request,
            'inmobiliaria/caratulas/lista.html',
            {
                'error': 'Tu usuario no tiene sucursal asignada.',
                'filas': paginator_empty.page(1),
                'q': q,
                'fecha_desde': request.GET.get('fecha_desde', '').strip(),
                'fecha_hasta': request.GET.get('fecha_hasta', '').strip(),
                'tipo_filtro': tipo_filtro,
            },
        )

    reservas = (
        Reserva.objects.filter(sucursal=sucursal, eliminada=False)
        .select_related('cliente', 'propiedad', 'propiedad__propietario', 'vendedor')
        .order_by('-fecha_creacion', '-id')
    )

    if tipo_filtro == 'invierno':
        reservas = reservas.none()
    elif tipo_filtro == '24meses':
        reservas = reservas.none()
    elif tipo_filtro == 'estudiante':
        reservas = reservas.filter(propiedad__tipo_cliente='ESTUDIANTE')
    elif tipo_filtro == 'dia':
        reservas = reservas.exclude(propiedad__tipo_cliente='ESTUDIANTE')

    if q:
        reservas = reservas.filter(
            Q(propiedad__direccion__icontains=q)
            | Q(propiedad__id__icontains=q)
            | Q(cliente__nombre__icontains=q)
            | Q(cliente__apellido__icontains=q)
        )

    if fecha_desde:
        try:
            d = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
            reservas = reservas.filter(fecha_creacion__date__gte=d)
        except ValueError:
            pass
    if fecha_hasta:
        try:
            d = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
            reservas = reservas.filter(fecha_creacion__date__lte=d)
        except ValueError:
            pass

    contratos = ContratoAlquiler.objects.filter(sucursal=sucursal).select_related(
        'propiedad', 'inquilino', 'vendedor'
    )
    if tipo_filtro == 'invierno':
        contratos = contratos.filter(duracion_meses=9)
    elif tipo_filtro == '24meses':
        contratos = contratos.filter(duracion_meses=24)
    elif tipo_filtro in ('dia', 'estudiante'):
        contratos = contratos.none()

    contratos = contratos.order_by('-fecha_creacion', '-id')

    if q:
        contratos = contratos.filter(
            Q(propiedad__direccion__icontains=q)
            | Q(propiedad__id__icontains=q)
            | Q(inquilino__nombre__icontains=q)
            | Q(inquilino__apellido__icontains=q)
        )
    if fecha_desde:
        try:
            d = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
            contratos = contratos.filter(fecha_operacion__gte=d)
        except ValueError:
            pass
    if fecha_hasta:
        try:
            d = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
            contratos = contratos.filter(fecha_operacion__lte=d)
        except ValueError:
            pass

    filas = []

    for r in reservas:
        tipo = _tipo_reserva(r.propiedad)
        p = r.propiedad
        piso_dto = ''
        if p:
            pi = (p.piso or '').strip() or '—'
            dep = (p.departamento or '').strip() or '—'
            piso_dto = f'{pi} / {dep}'
        filas.append(
            {
                'kind': 'reserva',
                'pk': r.id,
                'tipo': tipo,
                'numero': r.id,
                'fecha': r.fecha_creacion.date() if r.fecha_creacion else r.fecha_inicio,
                'caratula': _caratula_nombre_cliente(r.cliente),
                'direccion': p.direccion if p else '—',
                'piso_dto': piso_dto,
                'ficha': p.id if p else '—',
                'estado': r.get_estado_display() if hasattr(r, 'get_estado_display') else r.estado,
                'sort': r.fecha_creacion or r.fecha_inicio,
            }
        )

    for c in contratos:
        if c.duracion_meses == 9:
            tipo_c = 'Invierno'
        elif c.duracion_meses == 24:
            tipo_c = '24 meses'
        else:
            tipo_c = f'Contrato ({c.duracion_meses} meses)'
        p = c.propiedad
        piso_dto = ''
        if p:
            pi = (p.piso or '').strip() or '—'
            dep = (p.departamento or '').strip() or '—'
            piso_dto = f'{pi} / {dep}'
        filas.append(
            {
                'kind': 'contrato',
                'pk': c.id,
                'tipo': tipo_c,
                'numero': c.id,
                'fecha': c.fecha_operacion,
                'caratula': _caratula_nombre_cliente(c.inquilino),
                'direccion': p.direccion if p else '—',
                'piso_dto': piso_dto,
                'ficha': p.id if p else '—',
                'estado': c.get_estado_display() if hasattr(c, 'get_estado_display') else c.estado,
                'sort': c.fecha_creacion,
            }
        )

    filas.sort(key=lambda x: x['sort'] or x['fecha'], reverse=True)

    paginator = Paginator(filas, 40)
    page = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages or 1)

    return render(
        request,
        'inmobiliaria/caratulas/lista.html',
        {
            'filas': page_obj,
            'q': q,
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'tipo_filtro': tipo_filtro,
        },
    )


@login_required
def caratula_reserva(request, reserva_id):
    if not _puede_ver_caratulas(request.user):
        return HttpResponseForbidden()
    reserva = get_object_or_404(
        Reserva.objects.select_related('cliente', 'propiedad', 'propiedad__propietario', 'vendedor')
        .prefetch_related(
            Prefetch('recibos', queryset=Recibo.objects.order_by('-fecha_emision')),
            Prefetch(
                'comisiones_vendedor',
                queryset=ComisionVendedor.objects.select_related('vendedor').exclude(estado='cancelada'),
            ),
        ),
        pk=reserva_id,
    )
    if reserva.sucursal_id != getattr(request.user, 'sucursal_id', None) and not getattr(
        request.user, 'is_superuser', False
    ):
        return HttpResponseForbidden()

    movimientos = []
    if reserva.propiedad_id:
        movs_qs = (
            MovimientoCaja.objects.filter(
                propiedad_id=reserva.propiedad_id,
                sucursal_id=reserva.sucursal_id,
            )
            .order_by('-fecha')
        )
        for mov in movs_qs[:200]:
            if mov.concepto and re.search(rf'Operaci[oó]n\s+{reserva.id}\b', mov.concepto, re.IGNORECASE):
                movimientos.append(mov)

    recibos = list(reserva.recibos.all())
    comisiones = list(reserva.comisiones_vendedor.all())

    total_mov = sum(
        Decimal(str(m.monto_efectivo or 0))
        + Decimal(str(m.monto_cheque or 0))
        + Decimal(str(m.monto_tarjeta or 0))
        + Decimal(str(m.monto_deposito or 0))
        for m in movimientos
    )

    ctx = {
        'reserva': reserva,
        'propiedad': reserva.propiedad,
        'tipo_operacion': _tipo_reserva(reserva.propiedad),
        'movimientos': movimientos,
        'recibos': recibos,
        'comisiones': comisiones,
        'total_movimientos': total_mov,
        'saldo_reserva': (reserva.precio_total or Decimal('0')) - (reserva.senia or Decimal('0')),
    }
    return render(request, 'inmobiliaria/caratulas/detalle_reserva.html', ctx)


@login_required
def caratula_contrato(request, contrato_id):
    if not _puede_ver_caratulas(request.user):
        return HttpResponseForbidden()
    contrato = get_object_or_404(
        ContratoAlquiler.objects.select_related('propiedad', 'propiedad__propietario', 'inquilino', 'vendedor').prefetch_related(
            Prefetch('cuotas', queryset=CuotaMensual.objects.order_by('fecha_vencimiento')),
        ),
        pk=contrato_id,
    )
    if contrato.sucursal_id != getattr(request.user, 'sucursal_id', None) and not getattr(
        request.user, 'is_superuser', False
    ):
        return HttpResponseForbidden()

    movimientos = []
    if contrato.propiedad_id:
        movs_qs = MovimientoCaja.objects.filter(
            propiedad_id=contrato.propiedad_id,
            sucursal_id=contrato.sucursal_id,
            tipo=TipoMovimientoCajaEnum.INGRESO,
        ).order_by('-fecha')
        for mov in movs_qs[:300]:
            if mov.concepto and re.search(rf'Contrato\s*#\s*{contrato.id}\b', mov.concepto, re.IGNORECASE):
                movimientos.append(mov)

    total_mov = sum(
        Decimal(str(m.monto_efectivo or 0))
        + Decimal(str(m.monto_cheque or 0))
        + Decimal(str(m.monto_tarjeta or 0))
        + Decimal(str(m.monto_deposito or 0))
        for m in movimientos
    )

    cuotas = list(contrato.cuotas.all()) if hasattr(contrato, 'cuotas') else []

    if contrato.duracion_meses == 9:
        tipo_label = 'Invierno (9 meses)'
    elif contrato.duracion_meses == 24:
        tipo_label = '24 meses'
    else:
        tipo_label = f'Contrato {contrato.duracion_meses} meses'

    ctx = {
        'contrato': contrato,
        'propiedad': contrato.propiedad,
        'tipo_label': tipo_label,
        'movimientos': movimientos,
        'total_movimientos': total_mov,
        'cuotas': cuotas,
    }
    return render(request, 'inmobiliaria/caratulas/detalle_contrato.html', ctx)
