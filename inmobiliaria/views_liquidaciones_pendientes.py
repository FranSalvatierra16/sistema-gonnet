"""Listado global de operaciones pendientes de liquidar al propietario (solo lectura)."""
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
from inmobiliaria.busqueda_propiedad import ordenar_propiedades, q_busqueda_propiedad
from inmobiliaria.cartera_sucursal import qs_cartera_sucursal
from inmobiliaria.models import ContratoAlquiler, Propiedad, Reserva

logger = logging.getLogger(__name__)

MAX_PROPIEDADES = 400

# Solo operaciones con cobro (pagada/confirmada). Sin plata = Reserva, no figura acá.
ESTADOS_RESERVA_OPERACION = ('pagada', 'confirmada')


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


def _propiedades_candidatas(sucursal, desde, hasta, q, tipo_filtro=''):
    """
    Propiedades con operaciones que pueden figurar en el rango.

    - Por día (reserva): entrada (fecha_inicio) dentro de [desde, hasta].
    - Contratos: el contrato toca el rango (mes a liquidar).
    - Sin tipo / otros: unión de ambos (con tope).
    """
    from inmobiliaria.caja_devolucion_deposito import queryset_reservas_con_operacion

    ids_reservas = queryset_reservas_con_operacion(
        Reserva.objects.filter(
            estado__in=ESTADOS_RESERVA_OPERACION,
            eliminada=False,
        )
    )
    if tipo_filtro == 'reserva':
        # Irina: por día se lista por fecha de entrada en el período elegido.
        ids_reservas = ids_reservas.filter(
            fecha_inicio__gte=desde,
            fecha_inicio__lte=hasta,
        )
    else:
        ids_reservas = ids_reservas.filter(
            fecha_inicio__lte=hasta,
            fecha_fin__gte=desde,
        )
    ids_reservas = ids_reservas.values('propiedad_id')

    ids_contratos = ContratoAlquiler.objects.filter(
        fecha_inicio__lte=hasta,
        fecha_fin__gte=desde,
    ).values('propiedad_id')

    if tipo_filtro == 'reserva':
        props = Propiedad.objects.filter(sucursal=sucursal, id__in=ids_reservas)
    elif tipo_filtro == 'contrato':
        props = Propiedad.objects.filter(sucursal=sucursal, id__in=ids_contratos)
    else:
        props = Propiedad.objects.filter(sucursal=sucursal).filter(
            Q(id__in=ids_reservas) | Q(id__in=ids_contratos)
        )

    props = props.exclude(es_propiedad_oficina=True)
    try:
        props = props.exclude(
            id__in=qs_cartera_sucursal(sucursal, sincronizar=False).values('propiedad_id')
        )
    except Exception:
        logger.exception('liquidaciones_pendientes: no se pudo excluir la cartera de oficina')

    ids_match_directo = None
    if q:
        q_prop = q_busqueda_propiedad(q) | q_busqueda_persona(
            q, incluir_id=False, prefix='propietario__'
        )
        ids_match_directo = set(props.filter(q_prop).values_list('id', flat=True))
        ids_por_inquilino = set(
            Reserva.objects.filter(q_busqueda_persona(q, incluir_id=False, prefix='cliente__'))
            .values_list('propiedad_id', flat=True)
        ) | set(
            ContratoAlquiler.objects.filter(
                q_busqueda_persona(q, incluir_id=False, prefix='inquilino__')
            ).values_list('propiedad_id', flat=True)
        )
        props = props.filter(id__in=ids_match_directo | ids_por_inquilino)

    props = list(props.select_related('propietario')[: MAX_PROPIEDADES + 1])
    truncado = len(props) > MAX_PROPIEDADES
    return ordenar_propiedades(props[:MAX_PROPIEDADES]), ids_match_directo, truncado


def _url_liquidar(op):
    tipo = op.get('tipo')
    try:
        if tipo == 'reserva':
            return reverse('inmobiliaria:crear_liquidacion_reserva', args=[int(op['id'])])
        if tipo in ('contrato_cuota', 'contrato_operacion_principal') and op.get('contrato_id'):
            return reverse('inmobiliaria:crear_liquidacion_contrato', args=[int(op['contrato_id'])])
    except (TypeError, ValueError, KeyError):
        pass
    return reverse('inmobiliaria:crear_liquidacion')


def _n_liq_display(op):
    """N° visible: liquidación parcial si hay, si no el de la operación/reserva/cuota."""
    liq_id = op.get('liquidacion_id')
    if liq_id:
        try:
            return f'#{int(liq_id)}'
        except (TypeError, ValueError):
            pass
    tipo = (op.get('tipo') or '').strip().lower()
    raw_id = op.get('id')
    try:
        oid = int(raw_id)
    except (TypeError, ValueError):
        return '—'
    if tipo == 'reserva':
        return f'Op. #{oid}'
    if tipo.startswith('contrato'):
        cid = op.get('contrato_id')
        try:
            return f'CT #{int(cid)}' if cid else f'#{oid}'
        except (TypeError, ValueError):
            return f'#{oid}'
    return f'#{oid}'


def _decimal(valor):
    try:
        return Decimal(str(valor or 0))
    except Exception:
        return Decimal('0')


def _op_pasa_filtro_fechas(op, tipo, desde, hasta):
    """
    Por día: fecha de entrada de la reserva dentro del rango.
    Contratos / otros: el período de la fila se solapa con el rango (mes a liquidar).
    """
    fi = _parse_fecha(op.get('fecha_inicio'))
    ff = _parse_fecha(op.get('fecha_fin')) or fi

    if tipo == 'reserva':
        fe = _parse_fecha(op.get('fecha_entrada')) or fi
        if not fe:
            return False, fi, ff
        if fe < desde or fe > hasta:
            return False, fi, ff
        return True, fi, ff

    if not fi or fi > hasta or (ff and ff < desde):
        return False, fi, ff
    return True, fi, ff


@login_required
def liquidaciones_pendientes(request):
    from inmobiliaria.views import _etiqueta_propiedad_liquidacion, _operaciones_gastos_pendientes_data

    sucursal = request.user.sucursal
    desde, hasta = _rango_request(request)
    q = (request.GET.get('q') or '').strip()
    tipo_filtro = (request.GET.get('tipo') or '').strip()
    solo_cobradas = request.GET.get('solo_cobradas') == '1'

    props, ids_match_directo, truncado = _propiedades_candidatas(
        sucursal, desde, hasta, q, tipo_filtro=tipo_filtro
    )

    contratos_rescindidos = set(
        ContratoAlquiler.objects.filter(
            propiedad__in=[p.id for p in props], estado='rescindido'
        ).values_list('id', flat=True)
    )
    q_norm = q.lower()

    filas = []
    errores = []
    for prop in props:
        try:
            data = _operaciones_gastos_pendientes_data(prop, sucursal, solo_operaciones=True)
        except Exception:
            logger.exception('liquidaciones_pendientes: error en propiedad %s', prop.id)
            errores.append(_etiqueta_propiedad_liquidacion(prop))
            continue

        propietario = prop.propietario
        nombre_propietario = (
            f'{propietario.apellido}, {propietario.nombre}' if propietario else '—'
        )
        etiqueta = _etiqueta_propiedad_liquidacion(prop)
        match_directo = ids_match_directo is None or prop.id in ids_match_directo

        for op in data.get('operaciones') or []:
            if op.get('incluible') is False:
                continue
            tipo = op.get('tipo') or ''
            anticipada = bool(op.get('anticipada'))
            if solo_cobradas and anticipada:
                continue
            if anticipada and op.get('contrato_id') in contratos_rescindidos:
                continue
            if tipo_filtro == 'reserva' and tipo != 'reserva':
                continue
            if tipo_filtro == 'contrato' and not tipo.startswith('contrato'):
                continue
            if tipo_filtro == 'otros' and (tipo == 'reserva' or tipo.startswith('contrato')):
                continue

            ok_fecha, fi, ff = _op_pasa_filtro_fechas(op, tipo, desde, hasta)
            if not ok_fecha:
                continue

            descripcion = op.get('descripcion') or ''
            if not match_directo and q_norm not in descripcion.lower():
                continue

            filas.append({
                'propiedad_id': prop.id,
                'propiedad_label': etiqueta,
                'propietario': nombre_propietario,
                'tipo': tipo,
                'tipo_display': op.get('tipo_display') or '',
                'descripcion': descripcion,
                'n_liq': _n_liq_display(op),
                'fecha_inicio': fi,
                'fecha_fin': ff,
                'fecha_entrada': _parse_fecha(op.get('fecha_entrada')) if tipo == 'reserva' else None,
                'moneda': (op.get('moneda') or 'ARS').upper(),
                'monto_total': _decimal(op.get('monto_total')),
                'monto_propietario': _decimal(op.get('monto_propietario')),
                'anticipada': anticipada,
                'parcial': bool(op.get('liquidacion_parcial')) or 'parcial' in descripcion.lower(),
                'url_liquidar': _url_liquidar(op),
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
            'cantidad_propiedades': len({f['propiedad_id'] for f in filas}),
            'fecha_desde': desde.isoformat(),
            'fecha_hasta': hasta.isoformat(),
            'q': q,
            'tipo_filtro': tipo_filtro,
            'solo_cobradas': solo_cobradas,
            'truncado': truncado,
            'max_propiedades': MAX_PROPIEDADES,
            'errores': errores,
        },
    )
