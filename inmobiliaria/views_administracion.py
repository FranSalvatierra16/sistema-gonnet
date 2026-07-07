"""Pantallas de administración: resumen y listado de operaciones."""
from collections import defaultdict
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from inmobiliaria.models import ContratoAlquiler, Reserva

ETIQUETAS_TIPO = {
    'dia': 'Por día',
    'estudiante': 'Estudiante',
    'invierno': 'Invierno (9 meses)',
    '24': '24 meses',
    '6': '6 meses',
    'otro': 'Otro contrato',
}

CONTEO_ORDEN = ('dia', 'estudiante', 'invierno', '24', '6', 'otro')


def _puede_administracion_operaciones(user):
    nivel = getattr(user, 'nivel', None)
    return bool(getattr(user, 'is_superuser', False) or (nivel is not None and nivel >= 4))


def _parse_fecha(s):
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


def _categoria_reserva(reserva):
    """Tipo operativo de una reserva (siempre alquiler por día o estudiante; no contrato 9/24 meses)."""
    prop = reserva.propiedad
    if prop and getattr(prop, 'tipo_cliente', None) == 'ESTUDIANTE':
        return 'estudiante'
    return 'dia'


def _categoria_contrato(contrato):
    """
    Misma regla que carátulas y liquidaciones: invierno/estudiante, 6 meses, o alquiler largo
    (menú 24 meses aunque el plan sea 30, 36, etc.).
    """
    if hasattr(contrato, 'categoria_tipo_operacion'):
        return contrato.categoria_tipo_operacion()
    meses = int(contrato.duracion_meses or 0)
    if meses == 9:
        return 'invierno'
    if meses == 6:
        return '6'
    if meses >= 9:
        return '24'
    return 'otro'


def _etiqueta_tipo_contrato(contrato, categoria):
    if hasattr(contrato, 'etiqueta_tipo_operacion_caratula'):
        return contrato.etiqueta_tipo_operacion_caratula()
    return ETIQUETAS_TIPO.get(categoria, categoria)


def _coincide_tipo_filtro(categoria, tipo_filtro):
    if not tipo_filtro:
        return True
    if tipo_filtro == '24meses':
        return categoria == '24'
    if tipo_filtro == '6meses':
        return categoria == '6'
    return categoria == tipo_filtro


def _nombre_persona(persona):
    if not persona:
        return '—'
    ap = (getattr(persona, 'apellido', None) or '').strip()
    nom = (getattr(persona, 'nombre', None) or '').strip()
    if ap and nom:
        return f'{ap}, {nom}'
    return ap or nom or '—'


def _estado_display_reserva(reserva):
    """Estado visible en listados (solo lectura; sync al cobrar o en comando de reparación)."""
    from decimal import Decimal

    from inmobiliaria.caja_devolucion_deposito import etiqueta_estado_reserva

    return etiqueta_estado_reserva(reserva, Decimal(str(reserva.senia or 0)))


@login_required
def administracion_listado_operaciones(request):
    """
    Listado de todas las operaciones de la sucursal con filtro por fechas y tipo.
    Cuenta cuántas operaciones se registraron en el período (fecha de alta).
    """
    if not _puede_administracion_operaciones(request.user):
        return HttpResponseForbidden()

    sucursal = getattr(request.user, 'sucursal', None)
    tipo_filtro = (request.GET.get('tipo') or '').strip()
    q = (request.GET.get('q') or '').strip()
    periodo_completo = request.GET.get('todo') == '1'

    today = timezone.localdate()
    raw_desde = (request.GET.get('fecha_desde') or '').strip()
    raw_hasta = (request.GET.get('fecha_hasta') or '').strip()

    if periodo_completo:
        fecha_desde_s = raw_desde
        fecha_hasta_s = raw_hasta
    elif not raw_desde and not raw_hasta:
        fecha_desde_s = today.replace(day=1).isoformat()
        fecha_hasta_s = today.isoformat()
    else:
        fecha_desde_s = raw_desde
        fecha_hasta_s = raw_hasta

    dr_desde = _parse_fecha(fecha_desde_s)
    dr_hasta = _parse_fecha(fecha_hasta_s)
    if dr_desde and dr_hasta and dr_hasta < dr_desde:
        dr_desde, dr_hasta = dr_hasta, dr_desde
        fecha_desde_s, fecha_hasta_s = dr_desde.isoformat(), dr_hasta.isoformat()

    contexto_vacio = {
        'q': q,
        'tipo_filtro': tipo_filtro,
        'fecha_desde': fecha_desde_s if not periodo_completo else '',
        'fecha_hasta': fecha_hasta_s if not periodo_completo else '',
        'periodo_completo': periodo_completo,
        'operaciones': Paginator([], 50).page(1),
        'total_operaciones': 0,
        'conteos_tipo': [],
        'conteos_tipo_dict': {},
        'error': None,
    }

    if not sucursal:
        contexto_vacio['error'] = 'Tu usuario no tiene sucursal asignada.'
        return render(request, 'inmobiliaria/administracion/listado_operaciones.html', contexto_vacio)

    from inmobiliaria.caja_devolucion_deposito import (
        queryset_contratos_con_operacion,
        queryset_reservas_con_operacion,
    )

    reservas_qs = queryset_reservas_con_operacion(
        Reserva.objects.filter(sucursal=sucursal, eliminada=False)
        .select_related('propiedad', 'propiedad__propietario', 'cliente', 'vendedor')
        .order_by('-fecha_creacion', '-id')
    )
    contratos_qs = queryset_contratos_con_operacion(
        ContratoAlquiler.objects.filter(sucursal=sucursal)
        .select_related('propiedad', 'propiedad__propietario', 'inquilino', 'vendedor')
        .order_by('-fecha_creacion', '-id')
    )

    if not periodo_completo:
        if dr_desde:
            reservas_qs = reservas_qs.filter(fecha_creacion__date__gte=dr_desde)
            contratos_qs = contratos_qs.filter(fecha_creacion__date__gte=dr_desde)
        if dr_hasta:
            reservas_qs = reservas_qs.filter(fecha_creacion__date__lte=dr_hasta)
            contratos_qs = contratos_qs.filter(fecha_creacion__date__lte=dr_hasta)

    if q:
        q_res = (
            Q(propiedad__direccion__icontains=q)
            | Q(propiedad__ubicacion__icontains=q)
            | Q(propiedad__titulo__icontains=q)
            | Q(cliente__nombre__icontains=q)
            | Q(cliente__apellido__icontains=q)
            | Q(vendedor__nombre__icontains=q)
            | Q(vendedor__apellido__icontains=q)
        )
        q_ctr = (
            Q(propiedad__direccion__icontains=q)
            | Q(propiedad__ubicacion__icontains=q)
            | Q(propiedad__titulo__icontains=q)
            | Q(inquilino__nombre__icontains=q)
            | Q(inquilino__apellido__icontains=q)
            | Q(vendedor__nombre__icontains=q)
            | Q(vendedor__apellido__icontains=q)
        )
        if q.isdigit():
            try:
                num = int(q)
                q_res |= Q(id=num) | Q(propiedad_id=num)
                q_ctr |= Q(id=num) | Q(propiedad_id=num)
            except (TypeError, ValueError):
                pass
        reservas_qs = reservas_qs.filter(q_res)
        contratos_qs = contratos_qs.filter(q_ctr)

    filas = []
    conteos = defaultdict(int)

    for reserva in reservas_qs.iterator(chunk_size=200):
        cat = _categoria_reserva(reserva)
        conteos[cat] += 1
        if not _coincide_tipo_filtro(cat, tipo_filtro):
            continue
        prop = reserva.propiedad
        filas.append({
            'kind': 'reserva',
            'pk': reserva.id,
            'numero': reserva.id,
            'tipo': ETIQUETAS_TIPO.get(cat, cat),
            'tipo_key': cat,
            'fecha_registro': reserva.fecha_creacion,
            'fecha_inicio': reserva.fecha_inicio,
            'fecha_fin': reserva.fecha_fin,
            'cliente': _nombre_persona(reserva.cliente),
            'propiedad': (prop.direccion if prop else '—') or '—',
            'propiedad_id': prop.id if prop else None,
            'vendedor': _nombre_persona(reserva.vendedor),
            'estado': _estado_display_reserva(reserva),
            'url_detalle': reverse('inmobiliaria:caratula_reserva', args=[reserva.id]),
            'sort': reserva.fecha_creacion,
        })

    for contrato in contratos_qs.iterator(chunk_size=200):
        cat = _categoria_contrato(contrato)
        conteos[cat] += 1
        if not _coincide_tipo_filtro(cat, tipo_filtro):
            continue
        prop = contrato.propiedad
        filas.append({
            'kind': 'contrato',
            'pk': contrato.id,
            'numero': contrato.id,
            'tipo': _etiqueta_tipo_contrato(contrato, cat),
            'tipo_key': cat,
            'fecha_registro': contrato.fecha_creacion,
            'fecha_inicio': contrato.fecha_inicio,
            'fecha_fin': contrato.fecha_fin,
            'cliente': _nombre_persona(contrato.inquilino),
            'propiedad': (prop.direccion if prop else '—') or '—',
            'propiedad_id': prop.id if prop else None,
            'vendedor': _nombre_persona(contrato.vendedor),
            'estado': contrato.get_estado_display() if hasattr(contrato, 'get_estado_display') else contrato.estado,
            'url_detalle': reverse('inmobiliaria:caratula_contrato', args=[contrato.id]),
            'sort': contrato.fecha_creacion,
        })

    total_sin_filtro_tipo = sum(conteos.values())
    total_filtrado = len(filas)
    filas.sort(key=lambda x: x['sort'] or x['fecha_registro'], reverse=True)

    conteos_tipo = [
        {
            'key': key,
            'label': ETIQUETAS_TIPO.get(key, key),
            'cantidad': conteos.get(key, 0),
        }
        for key in CONTEO_ORDEN
        if conteos.get(key, 0) > 0
    ]

    paginator = Paginator(filas, 50)
    page_num = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page_num)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages or 1)

    return render(
        request,
        'inmobiliaria/administracion/listado_operaciones.html',
        {
            'q': q,
            'tipo_filtro': tipo_filtro,
            'fecha_desde': fecha_desde_s if not periodo_completo else '',
            'fecha_hasta': fecha_hasta_s if not periodo_completo else '',
            'periodo_completo': periodo_completo,
            'operaciones': page_obj,
            'total_operaciones': total_filtrado if tipo_filtro else total_sin_filtro_tipo,
            'total_periodo': total_sin_filtro_tipo,
            'conteos_tipo': conteos_tipo,
            'conteos_tipo_dict': dict(conteos),
            'error': None,
        },
    )
