"""Consulta de recibos (estilo sistema legacy: por fecha, número, propiedad, movimiento)."""
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from inmobiliaria.models import Recibo


def _parse_fecha(s):
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


def _nombre_cliente(reserva):
    if not reserva:
        return '—'
    cli = getattr(reserva, 'cliente', None)
    if not cli:
        return '—'
    ap = (getattr(cli, 'apellido', None) or '').strip()
    nom = (getattr(cli, 'nombre', None) or '').strip()
    if ap and nom:
        return f'{ap}, {nom}'.upper()
    return (ap or nom or '—').upper()


def _fila_recibo(recibo):
    reserva = recibo.reserva
    mov = recibo.movimiento_caja
    prop = recibo.propiedad
    cli = getattr(reserva, 'cliente', None) if reserva else None
    url_ver = None
    if mov and mov.id:
        url_ver = reverse('inmobiliaria:ver_recibo_movimiento', args=[mov.id])
    elif reserva and reserva.id:
        url_ver = reverse('inmobiliaria:ver_recibo', args=[reserva.id])
    url_caratula = None
    if reserva and reserva.id:
        url_caratula = reverse('inmobiliaria:caratula_reserva', args=[reserva.id])
    return {
        'id': recibo.id,
        'fecha': recibo.fecha_emision,
        'movimiento_id': mov.id if mov else None,
        'numero': (recibo.numero_recibo or '—').strip() or '—',
        'cliente_id': cli.id if cli else None,
        'cliente_nombre': _nombre_cliente(reserva),
        'propiedad': (prop.direccion if prop else '') or '—',
        'propiedad_id': prop.id if prop else None,
        'monto': recibo.monto_este_pago,
        'reserva_id': reserva.id if reserva else None,
        'url_ver': url_ver,
        'url_caratula': url_caratula,
    }


@login_required
def lista_recibos(request):
    """
    Consulta de recibos de la sucursal, con pestañas:
    fecha | número | propiedad | movimiento
    """
    sucursal = getattr(request.user, 'sucursal', None)
    if not sucursal:
        return HttpResponseForbidden('Tu usuario no tiene sucursal asignada.')

    modo = (request.GET.get('modo') or 'fecha').strip().lower()
    if modo not in ('fecha', 'numero', 'propiedad', 'movimiento'):
        modo = 'fecha'

    q = (request.GET.get('q') or '').strip()
    raw_desde = (request.GET.get('fecha_desde') or '').strip()
    raw_hasta = (request.GET.get('fecha_hasta') or '').strip()

    today = timezone.localdate()
    if modo == 'fecha' and not raw_desde and not raw_hasta and not q:
        raw_desde = today.replace(day=1).isoformat()
        raw_hasta = today.isoformat()

    fecha_desde = _parse_fecha(raw_desde)
    fecha_hasta = _parse_fecha(raw_hasta)
    if fecha_desde and fecha_hasta and fecha_hasta < fecha_desde:
        fecha_desde, fecha_hasta = fecha_hasta, fecha_desde
        raw_desde, raw_hasta = fecha_desde.isoformat(), fecha_hasta.isoformat()

    qs = (
        Recibo.objects.filter(propiedad__sucursal=sucursal)
        .select_related(
            'movimiento_caja',
            'reserva',
            'reserva__cliente',
            'propiedad',
            'empleado',
        )
        .order_by('-fecha_emision', '-id')
    )

    if modo == 'fecha':
        if fecha_desde:
            qs = qs.filter(fecha_emision__date__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha_emision__date__lte=fecha_hasta)
        if q:
            qs = qs.filter(
                Q(numero_recibo__icontains=q)
                | Q(reserva__cliente__apellido__icontains=q)
                | Q(reserva__cliente__nombre__icontains=q)
                | Q(propiedad__direccion__icontains=q)
            )
    elif modo == 'numero':
        if q:
            qs = qs.filter(numero_recibo__icontains=q)
        else:
            qs = qs.none()
    elif modo == 'propiedad':
        if q:
            q_prop = (
                Q(propiedad__direccion__icontains=q)
                | Q(propiedad__titulo__icontains=q)
                | Q(propiedad__ubicacion__icontains=q)
            )
            if q.isdigit():
                q_prop |= Q(propiedad_id=int(q))
            qs = qs.filter(q_prop)
        else:
            qs = qs.none()
    elif modo == 'movimiento':
        if q.isdigit():
            qs = qs.filter(movimiento_caja_id=int(q))
        else:
            qs = qs.none()

    paginator = Paginator(qs, 50)
    page_num = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page_num)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages or 1)

    filas = [_fila_recibo(r) for r in page_obj.object_list]

    return render(
        request,
        'inmobiliaria/recibos/lista.html',
        {
            'modo': modo,
            'q': q,
            'fecha_desde': raw_desde,
            'fecha_hasta': raw_hasta,
            'filas': filas,
            'page_obj': page_obj,
            'total': paginator.count,
        },
    )
