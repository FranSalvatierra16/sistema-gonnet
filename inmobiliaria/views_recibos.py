"""Consulta de recibos (estilo sistema legacy: por fecha, número, propiedad, movimiento)."""
from datetime import datetime
from decimal import Decimal
import re

from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from inmobiliaria.models import MovimientoCaja, Recibo, Reserva
from inmobiliaria.models.caja import TipoMovimientoCajaEnum

_RE_OP = re.compile(r'Operaci[oó]n\s*#?\s*(\d+)', re.I)


def _parse_fecha(s):
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


def _nombre_persona(persona):
    if not persona:
        return '—'
    ap = (getattr(persona, 'apellido', None) or '').strip()
    nom = (getattr(persona, 'nombre', None) or '').strip()
    if ap and nom:
        return f'{ap}, {nom}'.upper()
    return (ap or nom or '—').upper()


def _monto_movimiento(mov):
    return (
        Decimal(str(mov.monto_efectivo or 0))
        + Decimal(str(mov.monto_cheque or 0))
        + Decimal(str(mov.monto_tarjeta or 0))
        + Decimal(str(mov.monto_deposito or 0))
    )


def _reserva_id_desde_concepto(texto):
    if not texto:
        return None
    m = _RE_OP.search(texto)
    return int(m.group(1)) if m else None


def _fila_desde_movimiento(mov, recibo=None, reserva=None, contrato=None):
    prop = mov.propiedad
    cli = None
    url_caratula = None
    reserva_id = None
    cliente_id = None

    if recibo and recibo.reserva_id:
        reserva = reserva or recibo.reserva
    if not reserva:
        rid = _reserva_id_desde_concepto(
            f'{mov.concepto or ""} {getattr(mov, "concepto_detalle", "") or ""}'
        )
        if rid:
            reserva = Reserva.objects.filter(id=rid).select_related('cliente').first()

    if reserva:
        reserva_id = reserva.id
        cli = reserva.cliente
        url_caratula = reverse('inmobiliaria:caratula_reserva', args=[reserva.id])
    elif contrato:
        cli = getattr(contrato, 'inquilino', None)
        url_caratula = reverse('inmobiliaria:caratula_contrato', args=[contrato.id])

    if cli:
        cliente_id = cli.id

    numero = (recibo.numero_recibo if recibo else None) or (mov.numero_liquidacion or '').strip() or '—'
    monto = recibo.monto_este_pago if recibo and recibo.monto_este_pago is not None else _monto_movimiento(mov)
    fecha = recibo.fecha_emision if recibo and recibo.fecha_emision else mov.fecha

    return {
        'id': recibo.id if recibo else f'm{mov.id}',
        'fecha': fecha,
        'movimiento_id': mov.id,
        'numero': numero,
        'cliente_id': cliente_id,
        'cliente_nombre': _nombre_persona(cli),
        'propiedad': (prop.direccion if prop else '') or '—',
        'propiedad_id': prop.id if prop else None,
        'monto': monto,
        'reserva_id': reserva_id,
        # Siempre el movimiento concreto (no ver_recibo de la reserva, que solo muestra el último).
        'url_ver': reverse('inmobiliaria:ver_recibo_movimiento', args=[mov.id]),
        'url_caratula': url_caratula,
    }


@login_required
def lista_recibos(request):
    """
    Consulta de recibos de la sucursal, con pestañas:
    fecha | número | propiedad | movimiento

    Fuente: movimientos de ingreso con número de recibo (numero_liquidacion),
    enriquecidos con la tabla Recibo cuando existe (no solo el primero).
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
        MovimientoCaja.objects.filter(
            sucursal=sucursal,
            tipo=TipoMovimientoCajaEnum.INGRESO,
            fecha_eliminacion__isnull=True,
        )
        .exclude(Q(numero_liquidacion='') | Q(numero_liquidacion__isnull=True))
        .select_related('propiedad', 'propiedad__propietario', 'empleado')
        .order_by('-fecha', '-id')
    )

    if modo == 'fecha':
        if fecha_desde:
            qs = qs.filter(fecha__date__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha__date__lte=fecha_hasta)
        if q:
            qs = qs.filter(
                Q(numero_liquidacion__icontains=q)
                | Q(concepto__icontains=q)
                | Q(propiedad__direccion__icontains=q)
                | Q(propiedad__titulo__icontains=q)
            )
    elif modo == 'numero':
        if q:
            qs = qs.filter(numero_liquidacion__icontains=q)
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
            qs = qs.filter(id=int(q))
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

    movs = list(page_obj.object_list)
    mov_ids = [m.id for m in movs]
    recibos_por_mov = {
        r.movimiento_caja_id: r
        for r in Recibo.objects.filter(movimiento_caja_id__in=mov_ids).select_related(
            'reserva', 'reserva__cliente', 'propiedad'
        )
    }

    # Prefetch reservas referenciadas en concepto (las que no tienen Recibo).
    reserva_ids = set()
    for m in movs:
        if m.id in recibos_por_mov:
            continue
        rid = _reserva_id_desde_concepto(f'{m.concepto or ""} {getattr(m, "concepto_detalle", "") or ""}')
        if rid:
            reserva_ids.add(rid)
    reservas_map = {
        r.id: r
        for r in Reserva.objects.filter(id__in=reserva_ids).select_related('cliente')
    }

    filas = []
    for m in movs:
        recibo = recibos_por_mov.get(m.id)
        reserva = None
        if recibo and recibo.reserva_id:
            reserva = recibo.reserva
        else:
            rid = _reserva_id_desde_concepto(f'{m.concepto or ""} {getattr(m, "concepto_detalle", "") or ""}')
            if rid:
                reserva = reservas_map.get(rid)
        filas.append(_fila_desde_movimiento(m, recibo=recibo, reserva=reserva))

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
