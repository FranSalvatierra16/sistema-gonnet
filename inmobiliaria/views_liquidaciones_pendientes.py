"""Listado de liquidaciones en estado pendiente (ya creadas, aún no pagadas)."""
import logging
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from inmobiliaria.busqueda_persona import q_busqueda_persona
from inmobiliaria.busqueda_propiedad import q_busqueda_propiedad
from inmobiliaria.models import LiquidacionPropietario

logger = logging.getLogger(__name__)


def _parse_fecha(valor):
    try:
        return datetime.strptime(str(valor or '')[:10], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _rango_request(request):
    hoy = timezone.localdate()
    desde = _parse_fecha(request.GET.get('fecha_desde')) or hoy.replace(day=1)
    hasta = _parse_fecha(request.GET.get('fecha_hasta')) or date(
        hoy.year, hoy.month, monthrange(hoy.year, hoy.month)[1]
    )
    if hasta < desde:
        desde, hasta = hasta, desde
    return desde, hasta


def _decimal(valor):
    try:
        return Decimal(str(valor or 0))
    except Exception:
        return Decimal('0')


def _etiqueta_propiedad(prop):
    if not prop:
        return '—'
    partes = [f'#{prop.id}']
    dir_txt = (prop.direccion or '').strip()
    if dir_txt:
        partes[0] = f'{dir_txt} (#{prop.id})'
    return partes[0]


def _descripcion_liquidacion(liq):
    if liq.reserva_id:
        return f'Reserva #{liq.reserva_id}'
    if liq.contrato_id:
        return f'Contrato #{liq.contrato_id}'
    ops = liq.operaciones_incluidas or []
    if ops:
        bits = []
        for o in ops[:3]:
            if not isinstance(o, dict):
                continue
            tipo = (o.get('tipo') or '').strip()
            try:
                oid = int(o.get('id'))
            except (TypeError, ValueError):
                continue
            if tipo == 'reserva':
                bits.append(f'Reserva #{oid}')
            elif tipo.startswith('contrato'):
                bits.append(f'Contrato/cuota #{oid}')
            else:
                bits.append(f'{tipo or "op"} #{oid}')
        if bits:
            extra = f' (+{len(ops) - 3})' if len(ops) > 3 else ''
            return ', '.join(bits) + extra
    return '—'


def _periodo_liq(liq):
    fi = liq.fecha_desde
    ff = liq.fecha_hasta or fi
    if fi:
        return fi, ff
    reserva = getattr(liq, 'reserva', None)
    if reserva and reserva.fecha_inicio:
        return reserva.fecha_inicio, reserva.fecha_fin or reserva.fecha_inicio
    fc = liq.fecha_creacion
    if fc:
        d = fc.date() if hasattr(fc, 'date') else fc
        return d, d
    return None, None


def _pasa_filtro_periodo(liq, desde, hasta):
    """Mes liquidado: inicio del período dentro del rango elegido."""
    fi, ff = _periodo_liq(liq)
    if not fi:
        return False, fi, ff
    if fi < desde or fi > hasta:
        return False, fi, ff
    return True, fi, ff


def _tipo_key_liq(liq):
    key = getattr(liq, 'tipo_operacion_key', None) or ''
    if key:
        return key
    if liq.reserva_id:
        return 'dia'
    if liq.contrato_id:
        return 'contrato'
    return ''


@login_required
def liquidaciones_pendientes(request):
    """
    Liquidaciones ya creadas en estado pendiente (a pagar al propietario).
    No lista operaciones sin liquidación: eso confundía con altas de ayer.
    """
    from inmobiliaria.liquidacion_operacion import enriquecer_info_operacion_liquidaciones

    sucursal = request.user.sucursal
    desde, hasta = _rango_request(request)
    q = (request.GET.get('q') or '').strip()
    tipo_filtro = (request.GET.get('tipo') or '').strip()

    qs = (
        LiquidacionPropietario.objects.filter(
            sucursal=sucursal,
            estado='pendiente',
        )
        .select_related(
            'propietario',
            'propiedad',
            'reserva',
            'contrato',
        )
        .order_by('fecha_desde', 'id')
    )

    if q:
        from inmobiliaria.models import Propiedad

        ids_prop = Propiedad.objects.filter(q_busqueda_propiedad(q)).values('id')
        q_filtro = (
            Q(propiedad_id__in=ids_prop)
            | q_busqueda_persona(q, incluir_id=False, prefix='propietario__')
        )
        if q.isdigit():
            q_filtro |= Q(id=int(q)) | Q(reserva_id=int(q)) | Q(contrato_id=int(q))
        qs = qs.filter(q_filtro)

    liquidaciones = list(qs[:2000])
    enriquecer_info_operacion_liquidaciones(liquidaciones)

    filas = []
    for liq in liquidaciones:
        ok, fi, ff = _pasa_filtro_periodo(liq, desde, hasta)
        if not ok:
            continue

        tipo_key = _tipo_key_liq(liq)
        if tipo_filtro == 'reserva' and not (liq.reserva_id or tipo_key in ('dia',)):
            continue
        if tipo_filtro == 'contrato' and (tipo_key == 'dia' or (liq.reserva_id and not liq.contrato_id)):
            continue

        prop = liq.propiedad
        propietario = liq.propietario
        nombre_propietario = (
            f'{propietario.apellido}, {propietario.nombre}' if propietario else '—'
        )
        moneda = (liq.moneda or 'ARS').upper()
        monto = _decimal(liq.monto_a_pagar)
        filas.append({
            'liquidacion_id': liq.id,
            'propiedad_id': prop.id if prop else None,
            'propiedad_label': _etiqueta_propiedad(prop),
            'propietario': nombre_propietario,
            'tipo': tipo_key,
            'tipo_display': getattr(liq, 'tipo_operacion_display', None) or '',
            'descripcion': _descripcion_liquidacion(liq),
            'n_liq': f'#{liq.id}',
            'fecha_inicio': fi,
            'fecha_fin': ff,
            'moneda': moneda,
            'monto_propietario': monto,
            'url_detalle': reverse('inmobiliaria:detalle_liquidacion', args=[liq.id]),
        })

    totales = {}
    for f in filas:
        t = totales.setdefault(f['moneda'], {'cantidad': 0, 'monto_propietario': Decimal('0')})
        t['cantidad'] += 1
        t['monto_propietario'] += f['monto_propietario']

    return render(
        request,
        'inmobiliaria/liquidaciones/pendientes.html',
        {
            'filas': filas,
            'totales': sorted(totales.items()),
            'cantidad_propiedades': len({f['propiedad_id'] for f in filas if f['propiedad_id']}),
            'fecha_desde': desde.isoformat(),
            'fecha_hasta': hasta.isoformat(),
            'q': q,
            'tipo_filtro': tipo_filtro,
        },
    )
