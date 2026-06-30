"""
Consulta de carátulas: listado y detalle de operaciones (reservas por día, invierno, 24 meses).
"""
import logging
import re
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Prefetch, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from inmobiliaria.models import (
    ComisionVendedor,
    ContratoAlquiler,
    CuotaMensual,
    LiquidacionPropietario,
    MovimientoCaja,
    Recibo,
    Reserva,
)
from inmobiliaria.models.caja import TipoMovimientoCajaEnum

logger = logging.getLogger(__name__)

CARATULA_CARPETA_DEFAULT_KEY = 'caratulas_carpeta_default'
CARATULA_CARPETA_OVERRIDES_KEY = 'caratulas_carpeta_overrides'
CARATULA_COMISIONES_OVERRIDES_KEY = 'caratulas_comisiones_overrides'

_CONCEPTO_HONORARIOS_LABELS = {
    '1': 'Alquiler (1er mes)',
    '10': 'Depósito en garantía',
    '15': 'Gastos adicionales',
    '25': 'Honorarios',
    '26': 'Sellados',
    '85': 'Participación locador',
    '1000': 'Alquiler mensual',
    '29': 'Adelanto',
}

LISTA_CARATULAS_QUERY_KEYS = (
    'q', 'operacion', 'fecha_desde', 'fecha_hasta', 'tipo', 'liquidacion', 'todo', 'page',
)


def _params_lista_caratulas_desde_get(get, extra=None):
    """Parámetros GET del listado de carátulas (filtros + paginación)."""
    params = {}
    for key in LISTA_CARATULAS_QUERY_KEYS:
        val = get.get(key, '')
        if isinstance(val, str):
            val = val.strip()
        if val:
            params[key] = val
    if extra:
        for key, val in extra.items():
            if val not in (None, ''):
                params[key] = val
    return params


def _query_string_lista_caratulas(
    q='',
    operacion='',
    fecha_desde='',
    fecha_hasta='',
    tipo_filtro='',
    liquidacion_filtro='',
    periodo_completo=False,
    page=None,
):
    params = {}
    q = (q or '').strip()
    operacion = (operacion or '').strip()
    tipo_filtro = (tipo_filtro or '').strip()
    liquidacion_filtro = (liquidacion_filtro or '').strip()
    fecha_desde = (fecha_desde or '').strip()
    fecha_hasta = (fecha_hasta or '').strip()
    if q:
        params['q'] = q
    if operacion:
        params['operacion'] = operacion
    if tipo_filtro:
        params['tipo'] = tipo_filtro
    if liquidacion_filtro:
        params['liquidacion'] = liquidacion_filtro
    if periodo_completo:
        params['todo'] = '1'
    if fecha_desde:
        params['fecha_desde'] = fecha_desde
    if fecha_hasta:
        params['fecha_hasta'] = fecha_hasta
    if page:
        params['page'] = str(page)
    return urlencode(params)


def _url_lista_caratulas(**kwargs):
    qs = _query_string_lista_caratulas(**kwargs)
    base = reverse('inmobiliaria:lista_caratulas')
    return f'{base}?{qs}' if qs else base


def _url_lista_caratulas_desde_request(request):
    params = _params_lista_caratulas_desde_get(request.GET)
    base = reverse('inmobiliaria:lista_caratulas')
    qs = urlencode(params)
    return f'{base}?{qs}' if qs else base


def _redirect_caratula_con_filtros(view_name, pk, request):
    url = reverse(view_name, args=[pk])
    qs = urlencode(_params_lista_caratulas_desde_get(request.GET))
    if qs:
        url = f'{url}?{qs}'
    return redirect(url)


def _normalizar_carpeta(raw):
    val = (raw or '').strip()
    if not val:
        return '0'
    solo_num = re.sub(r'[^0-9]', '', val)
    if not solo_num:
        return '0'
    return solo_num[:8]


def _carpeta_default_actual(request):
    return _normalizar_carpeta(request.session.get(CARATULA_CARPETA_DEFAULT_KEY, '0'))


def _set_carpeta_default(request, carpeta):
    request.session[CARATULA_CARPETA_DEFAULT_KEY] = _normalizar_carpeta(carpeta)
    request.session.modified = True


def _set_carpeta_override(request, kind, op_id, carpeta):
    key = f'{kind}:{op_id}'
    overrides = dict(request.session.get(CARATULA_CARPETA_OVERRIDES_KEY, {}))
    overrides[key] = _normalizar_carpeta(carpeta)
    request.session[CARATULA_CARPETA_OVERRIDES_KEY] = overrides
    request.session.modified = True


def _persistir_carpeta_operacion(kind, op_id, carpeta):
    val = _normalizar_carpeta(carpeta)
    if kind == 'contrato':
        ContratoAlquiler.objects.filter(pk=op_id).update(numero_carpeta=val)
    return val


def _leer_carpeta_db(kind, op_id=None, reserva=None, contrato=None):
    if kind == 'contrato':
        obj = contrato
        if obj is None and op_id:
            obj = ContratoAlquiler.objects.filter(pk=op_id).only('numero_carpeta').first()
        if obj and (getattr(obj, 'numero_carpeta', None) or '').strip():
            val = _normalizar_carpeta(obj.numero_carpeta)
            return val if val != '0' else None
    return None


def _carpeta_guardada_operacion(contrato=None, op_id=None):
    """Nº carpeta persistido en la operación (solo BD). None si no tiene asignado."""
    return _leer_carpeta_db('contrato', op_id, contrato=contrato)


def _carpeta_para_operacion(request, kind, op_id, reserva=None, contrato=None, fallback=None):
    db_val = _leer_carpeta_db(kind, op_id, reserva=reserva, contrato=contrato)
    if db_val:
        return db_val
    key = f'{kind}:{op_id}'
    overrides = dict(request.session.get(CARATULA_CARPETA_OVERRIDES_KEY, {}))
    if key in overrides:
        return _normalizar_carpeta(overrides.get(key))
    if fallback is not None:
        return _normalizar_carpeta(fallback)
    return _carpeta_default_actual(request)



def _nombre_cliente_papel(persona):
    if not persona:
        return '—'
    ap = (getattr(persona, 'apellido', None) or '').strip().upper()
    nom = (getattr(persona, 'nombre', None) or '').strip().upper()
    if ap and nom:
        return f'{ap}, {nom}'
    return (ap or nom or '—')


def _nombre_propietario_papel(propi):
    """Nombre del propietario para impresión (misma legibilidad que dirección / cliente)."""
    if not propi:
        return '—'
    ap = (propi.apellido or '').strip().upper()
    nom = (propi.nombre or '').strip().upper()
    if ap and nom:
        return f'{ap}, {nom}'
    return (ap or nom or '—')


def _nombre_productor_papel(vendedor):
    """Solo nombre del productor (sin apellido, legajo ni ID)."""
    if not vendedor:
        return '—'
    nom = (getattr(vendedor, 'nombre', None) or '').strip().upper()
    return nom or '—'


def _propiedad_desc_corta(prop):
    if not prop:
        return '—'
    amb = getattr(prop, 'ambientes', None)
    tin = (getattr(prop, 'tipo_inmueble', None) or 'depto').replace('_', ' ').upper()
    amb_txt = f'{amb} AMB. ' if amb else ''
    return f'{amb_txt}{tin} {(prop.direccion or "").strip()[:55]}'.strip().upper()


def _etiqueta_propiedad_lista(prop):
    """Título/nombre de la propiedad + línea secundaria (dirección / ubicación) para listados."""
    if not prop:
        return '—', ''
    tit = (getattr(prop, 'titulo', None) or '').strip()
    direc = (prop.direccion or '').strip()
    ubic = (getattr(prop, 'ubicacion', None) or '').strip()
    if tit:
        sub = ' · '.join([p for p in (direc, ubic) if p])
        return tit, sub
    if direc:
        sub = ubic if ubic and ubic.lower() != direc.lower() else ''
        return direc, sub
    return ubic or '—', ''


def _direccion_piso_depto_papel(prop):
    if not prop:
        return '—'
    parts = [(prop.direccion or '').strip().upper()]
    fid = getattr(prop, 'id', None)
    if fid:
        parts.append(f'({fid})')
    pi = (prop.piso or '').strip()
    dep = (prop.departamento or '').strip()
    if pi or dep:
        parts.append(f'PISO:{pi or "—"} DPTO.:{dep or "—"}')
    return ' '.join(parts)


def _movimientos_reserva_qs(reserva):
    if not reserva.propiedad_id:
        return MovimientoCaja.objects.none()
    return (
        MovimientoCaja.objects.filter(
            propiedad_id=reserva.propiedad_id,
            sucursal_id=reserva.sucursal_id,
        )
        .select_related('recibo')
        .order_by('fecha', 'id')
    )


def _movimientos_contrato_qs(contrato):
    if not contrato.propiedad_id:
        return MovimientoCaja.objects.none()
    return (
        MovimientoCaja.objects.filter(
            propiedad_id=contrato.propiedad_id,
            sucursal_id=contrato.sucursal_id,
        )
        .select_related('recibo')
        .order_by('fecha', 'id')
    )


def _operacion_en_concepto(concepto, operacion_id):
    if not concepto:
        return False
    return bool(
        re.search(rf'Operaci[oó]n\s*#?\s*{operacion_id}\b', concepto, re.IGNORECASE)
    )


def _numero_recibo_desde_movimiento(m):
    if not m:
        return '—'
    try:
        r = getattr(m, 'recibo', None)
        if r:
            n = (getattr(r, 'numero_recibo', None) or '').strip()
            if n:
                return n
    except Exception:
        pass
    nl = (getattr(m, 'numero_liquidacion', None) or '').strip()
    if nl:
        return nl
    return f'M-{int(m.id):06d}'


def _numero_recibo_desde_recibo(r):
    if not r:
        return '—'
    n = (getattr(r, 'numero_recibo', None) or '').strip()
    if n:
        return n
    mov = getattr(r, 'movimiento_caja', None)
    return _numero_recibo_desde_movimiento(mov) if mov else '—'


def _recibos_legacy_items(movs, recibos):
    """Lista ordenada de recibos únicos con movimiento/recibo asociado."""
    items = []
    vistos = set()
    for r in sorted(recibos, key=lambda x: x.fecha_emision or datetime.min):
        n = _numero_recibo_desde_recibo(r)
        if n and n != '—' and n not in vistos:
            items.append({
                'numero': n,
                'movimiento': getattr(r, 'movimiento_caja', None),
                'recibo': r,
            })
            vistos.add(n)
    for m in sorted(movs, key=lambda x: (x.fecha, x.id)):
        n = _numero_recibo_desde_movimiento(m)
        if n and n != '—' and n not in vistos:
            items.append({
                'numero': n,
                'movimiento': m,
                'recibo': getattr(m, 'recibo', None),
            })
            vistos.add(n)
    return items


def _url_recibo_legacy_item(item, sucursal, *, reserva=None):
    if not item:
        return None
    mov = item.get('movimiento')
    if mov:
        from inmobiliaria.views import _url_recibo_para_movimiento

        return _url_recibo_para_movimiento(mov, sucursal)
    if reserva is not None:
        return reverse('inmobiliaria:ver_recibo', args=[reserva.id])
    return None


def _recibos_legacy_par(movs, recibos, *, sucursal=None, reserva=None):
    """Números y URLs de recibo para el bloque legado de carátula."""
    items = _recibos_legacy_items(movs, recibos)
    loc = items[0]['numero'] if items else '0000-00000000'
    locat = items[1]['numero'] if len(items) > 1 else loc
    url_loc = _url_recibo_legacy_item(items[0], sucursal, reserva=reserva) if items else None
    url_locat = _url_recibo_legacy_item(
        items[1] if len(items) > 1 else items[0],
        sucursal,
        reserva=reserva,
    ) if items else None
    return loc, locat, url_loc, url_locat


def _filas_contabilizacion_desde_movimientos(movs):
    """Filas estilo libro: fecha, recibo, detalle, salidas, entradas (ARS formateados)."""
    filas = []
    for m in movs:
        try:
            mt = Decimal(str(m.monto_total))
        except (ArithmeticError, TypeError, ValueError):
            mt = Decimal('0')
        if mt == 0 and not (m.concepto or '').strip():
            continue
        det = (m.concepto or '').strip()[:100] or 'Movimiento de caja'
        recibo_num = _numero_recibo_desde_movimiento(m)
        is_ingreso = m.tipo == TipoMovimientoCajaEnum.INGRESO
        filas.append(
            {
                'fecha': m.fecha,
                'recibo': recibo_num,
                'detalle': det,
                'salidas': '' if is_ingreso else _formato_importe_us(mt),
                'entradas': _formato_importe_us(mt) if is_ingreso else '',
            }
        )
    return filas


def _filas_contabilizacion_desde_recibos(recibos):
    filas = []
    for r in sorted(recibos, key=lambda x: x.fecha_emision or datetime.min):
        try:
            mt = Decimal(str(r.monto_este_pago or 0))
        except (ArithmeticError, TypeError, ValueError):
            mt = Decimal('0')
        det = 'PAGO RESERVA / OPERACIÓN'
        if r.observaciones:
            det = (r.observaciones or '')[:100]
        filas.append(
            {
                'fecha': r.fecha_emision,
                'recibo': _numero_recibo_desde_recibo(r),
                'detalle': det,
                'salidas': '',
                'entradas': _formato_importe_us(mt),
            }
        )
    return filas


def _contabilizacion_para_reserva(reserva, recibos):
    movs = []
    for mov in _movimientos_reserva_qs(reserva)[:250]:
        if _operacion_en_concepto(mov.concepto, reserva.id):
            movs.append(mov)
    if movs:
        return _filas_contabilizacion_desde_movimientos(movs)
    return _filas_contabilizacion_desde_recibos(recibos)


def _contabilizacion_para_contrato(contrato):
    movs = []
    for mov in _movimientos_contrato_qs(contrato)[:300]:
        if mov.tipo != TipoMovimientoCajaEnum.INGRESO:
            continue
        if mov.concepto and re.search(rf'Contrato\s*#\s*{contrato.id}\b', mov.concepto, re.IGNORECASE):
            movs.append(mov)
    return _filas_contabilizacion_desde_movimientos(movs)


def _puede_ver_caratulas(user):
    nivel = getattr(user, 'nivel', None)
    return bool(getattr(user, 'is_superuser', False) or (nivel is not None and nivel >= 4))


def _puede_editar_caratula(user):
    """Edición de montos/estado en carátula (administración)."""
    return _puede_ver_caratulas(user)


def _guardar_caratula_reserva(request, reserva):
    """Persiste montos, fechas y estado de una reserva desde la carátula."""
    from django.contrib import messages
    from inmobiliaria.decimal_utils import parse_decimal_monto

    if not _puede_editar_caratula(request.user):
        messages.error(request, 'No tenés permiso para editar esta carátula.')
        return False

    try:
        fecha_inicio = datetime.strptime(
            (request.POST.get('fecha_inicio') or '').strip(), '%Y-%m-%d'
        ).date()
        fecha_fin = datetime.strptime(
            (request.POST.get('fecha_fin') or '').strip(), '%Y-%m-%d'
        ).date()
    except ValueError:
        messages.error(request, 'Las fechas desde/hasta no son válidas.')
        return False

    if fecha_fin <= fecha_inicio:
        messages.error(request, 'La fecha hasta debe ser posterior a la fecha desde.')
        return False

    def _parse_time(raw, default):
        texto = (raw or '').strip()
        if not texto:
            return default
        for fmt in ('%H:%M:%S', '%H:%M'):
            try:
                return datetime.strptime(texto, fmt).time()
            except ValueError:
                continue
        raise ValueError('Hora inválida')

    try:
        hora_ingreso = _parse_time(request.POST.get('hora_ingreso'), reserva.hora_ingreso)
        hora_egreso = _parse_time(request.POST.get('hora_egreso'), reserva.hora_egreso)
        precio_total = parse_decimal_monto(request.POST.get('precio_total', '0'))
        senia = parse_decimal_monto(request.POST.get('senia', '0'))
        deposito = parse_decimal_monto(request.POST.get('deposito_garantia', '0'))
        comision_locatario = parse_decimal_monto(request.POST.get('comision_locatario', '0'))
    except ValueError as exc:
        messages.error(request, str(exc))
        return False

    if min(precio_total, senia, deposito, comision_locatario) < 0:
        messages.error(request, 'Los montos no pueden ser negativos.')
        return False

    estado = (request.POST.get('estado') or reserva.estado).strip()
    estados_validos = {c[0] for c in Reserva._meta.get_field('estado').choices}
    if estado not in estados_validos:
        messages.error(request, 'Estado de operación inválido.')
        return False

    fechas_cambiaron = (
        reserva.fecha_inicio != fecha_inicio or reserva.fecha_fin != fecha_fin
    )

    reserva.fecha_inicio = fecha_inicio
    reserva.fecha_fin = fecha_fin
    reserva.hora_ingreso = hora_ingreso
    reserva.hora_egreso = hora_egreso
    reserva.precio_total = precio_total.quantize(Decimal('0.01'))
    reserva.senia = senia.quantize(Decimal('0.01'))
    reserva.deposito_garantia = deposito.quantize(Decimal('0.01'))
    reserva.cuota_pendiente = max(
        Decimal('0'), precio_total - senia
    ).quantize(Decimal('0.01'))
    reserva.estado = estado

    def _parse_liq_monto_opcional(campo):
        raw = (request.POST.get(campo) or '').strip()
        if not raw:
            return None
        val = parse_decimal_monto(raw)
        if val < 0:
            raise ValueError('Los montos de liquidación no pueden ser negativos.')
        return val.quantize(Decimal('0.01'))

    try:
        if 'liq_monto_propietario' in request.POST:
            reserva.liq_monto_propietario = _parse_liq_monto_opcional('liq_monto_propietario')
            reserva.liq_monto_inmobiliaria = _parse_liq_monto_opcional('liq_monto_inmobiliaria')
            reserva.liq_monto_cochera = _parse_liq_monto_opcional('liq_monto_cochera') or Decimal('0')
            reserva.liq_monto_fondo = _parse_liq_monto_opcional('liq_monto_fondo') or Decimal('0')
    except ValueError as exc:
        messages.error(request, str(exc))
        return False

    reserva.save()

    if fechas_cambiaron:
        try:
            reserva.actualizar_historial_disponibilidad()
        except Exception:
            logger.exception(
                'guardar_caratula_reserva: error al actualizar historial reserva_id=%s',
                reserva.id,
            )

    comisiones = list(
        ComisionVendedor.objects.filter(reserva=reserva).exclude(estado='cancelada')
    )
    if comisiones:
        total_actual = sum(Decimal(str(c.monto_comision or 0)) for c in comisiones)
        if len(comisiones) == 1:
            c = comisiones[0]
            c.monto_comision = comision_locatario.quantize(Decimal('0.01'))
            if c.monto_total_operacion and Decimal(str(c.monto_total_operacion)) > 0:
                c.porcentaje_comision = (
                    comision_locatario / Decimal(str(c.monto_total_operacion)) * Decimal('100')
                ).quantize(Decimal('0.01'))
            c.save(update_fields=['monto_comision', 'porcentaje_comision'])
        elif total_actual > 0:
            for c in comisiones:
                share = Decimal(str(c.monto_comision or 0)) / total_actual
                c.monto_comision = (comision_locatario * share).quantize(Decimal('0.01'))
                c.save(update_fields=['monto_comision'])
        elif comision_locatario > 0:
            c = comisiones[0]
            c.monto_comision = comision_locatario.quantize(Decimal('0.01'))
            c.save(update_fields=['monto_comision'])
    elif comision_locatario > 0 and reserva.vendedor_id:
        ComisionVendedor.objects.create(
            vendedor=reserva.vendedor,
            reserva=reserva,
            monto_total_operacion=precio_total,
            porcentaje_comision=Decimal('0'),
            monto_comision=comision_locatario.quantize(Decimal('0.01')),
            concepto_operacion=f'Operación {reserva.id}',
        )

    messages.success(request, 'Carátula actualizada correctamente.')
    return True


def _nivel_usuario_caratulas(user):
    if getattr(user, 'is_superuser', False):
        return 5
    try:
        return int(getattr(user, 'nivel', 0) or 0)
    except (TypeError, ValueError):
        return 0


def _volver_imprimir_caratula(request, *, reserva_id=None, contrato_id=None):
    """URL y etiqueta del botón Volver en vista de impresión de carátula."""
    from inmobiliaria.views import _validar_url_volver_recibo, _url_volver_desde_imprimir_caratula

    explicit = _validar_url_volver_recibo((request.GET.get('next') or '').strip(), request)
    if explicit:
        return explicit, 'Volver'
    if _nivel_usuario_caratulas(request.user) >= 4:
        if reserva_id:
            return reverse('inmobiliaria:caratula_reserva', args=[reserva_id]), 'Volver a la carátula'
        if contrato_id:
            return reverse('inmobiliaria:caratula_contrato', args=[contrato_id]), 'Volver a la carátula'
    return reverse('inmobiliaria:dashboard'), 'Volver al menú'


def _resumen_liquidacion_caratula(*, reserva=None, contrato=None, liquidacion=None, sucursal=None):
    """
    Cuadro estilo «crear liquidación»: total operación, propietario (depto), oficina, cochera, gastos, neto.
    Si hay liquidación guardada usa esos montos; si no, sugiere según la operación pendiente.
    """
    if liquidacion:
        gastos_qs = liquidacion.gastos.filter(aceptado=True).order_by('fecha_gasto', 'id')
        gastos_filas = [
            {'descripcion': (g.descripcion or 'Gasto').strip(), 'monto': g.monto}
            for g in gastos_qs
        ]
        monto_prop = Decimal(str(liquidacion.monto_propietario or 0))
        monto_coch = Decimal(str(liquidacion.monto_cochera or 0))
        filas_pago = []
        if monto_prop > 0:
            filas_pago.append({'concepto': 'Monto al propietario (depto)', 'monto': monto_prop})
        monto_fondo = Decimal(str(liquidacion.monto_fondo_mantenimiento or 0))
        monto_gastos = Decimal(str(liquidacion.monto_gastos or 0))
        monto_a_pagar = monto_prop - monto_gastos - monto_fondo
        return {
            'tiene_datos': True,
            'desde_liquidacion': True,
            'liquidacion_id': liquidacion.id,
            'estado_liquidacion': liquidacion.get_estado_display(),
            'liquidacion_pendiente': liquidacion.estado == 'pendiente',
            'moneda': getattr(liquidacion, 'moneda', 'ARS') or 'ARS',
            'monto_total': liquidacion.monto_total_operacion,
            'monto_propietario': liquidacion.monto_propietario,
            'monto_inmobiliaria': liquidacion.monto_inmobiliaria,
            'monto_cochera': monto_coch,
            'monto_fondo': monto_fondo,
            'monto_gastos': monto_gastos,
            'monto_a_pagar': monto_a_pagar,
            'subtotal_propietario': monto_prop,
            'total_descontado': monto_gastos + monto_fondo,
            'filas_pago': filas_pago,
            'gastos_filas': gastos_filas,
        }

    if not sucursal:
        return {'tiene_datos': False}

    from inmobiliaria.views import _operaciones_gastos_pendientes_data

    propiedad = None
    if reserva is not None:
        propiedad = reserva.propiedad
    elif contrato is not None:
        propiedad = contrato.propiedad

    if not propiedad:
        return {'tiene_datos': False}

    data = _operaciones_gastos_pendientes_data(propiedad, sucursal)
    op_match = None
    for op in data.get('operaciones') or []:
        if reserva is not None and op.get('tipo') == 'reserva':
            try:
                if int(op.get('id')) == reserva.id:
                    op_match = op
                    break
            except (TypeError, ValueError):
                continue
        if contrato is not None:
            if op.get('tipo') == 'contrato_cuota':
                try:
                    if (
                        int(op.get('contrato_id') or 0) == contrato.id
                        and op.get('incluible') is not False
                    ):
                        op_match = op
                        break
                except (TypeError, ValueError):
                    continue
            elif op.get('tipo') == 'contrato':
                try:
                    if int(op.get('id')) == contrato.id:
                        op_match = op
                        break
                except (TypeError, ValueError):
                    continue

    if not op_match and reserva is not None and reserva.precio_total:
        total = Decimal(str(reserva.precio_total))
        pct = getattr(propiedad, 'porcentaje_propietario', None)
        if pct is None or pct <= 0:
            pct = Decimal('70')
        else:
            pct = Decimal(str(pct))
        prop = (total * pct / Decimal('100')).quantize(Decimal('0.01'))
        inm = (total - prop).quantize(Decimal('0.01'))
        op_match = {
            'descripcion': f'Reserva #{reserva.id}',
            'monto_total': str(total),
            'monto_propietario': str(prop),
            'monto_inmobiliaria': str(inm),
        }

    if not op_match:
        return {'tiene_datos': False}

    total = Decimal(str(op_match.get('monto_total') or 0))
    prop = Decimal(str(op_match.get('monto_propietario') or 0))
    inm = Decimal(str(op_match.get('monto_inmobiliaria') or 0))
    if inm <= 0 and total > prop:
        inm = (total - prop).quantize(Decimal('0.01'))

    coch = Decimal('0')
    fondo = Decimal('0')
    if reserva is not None:
        total, prop, inm, coch, fondo = reserva.montos_liquidacion_efectivos(total, prop, inm)

    return {
        'tiene_datos': True,
        'desde_liquidacion': False,
        'liquidacion_id': None,
        'estado_liquidacion': None,
        'moneda': (op_match.get('moneda') or getattr(contrato, 'moneda', 'ARS') or 'ARS'),
        'monto_total': total,
        'monto_propietario': prop,
        'monto_inmobiliaria': inm,
        'monto_cochera': coch,
        'monto_fondo': fondo,
        'monto_gastos': Decimal('0'),
        'monto_a_pagar': (prop - fondo).quantize(Decimal('0.01')),
        'subtotal_propietario': prop,
        'total_descontado': fondo,
        'filas_pago': [
            {
                'concepto': (op_match.get('descripcion') or 'Operación').strip(),
                'monto': prop,
            }
        ],
        'gastos_filas': [],
    }


def _ctx_liquidacion_operacion(*, reserva=None, contrato=None):
    """Enlace a crear o ver liquidación del propietario para esta operación."""
    ctx = {
        'liquidacion_operacion': None,
        'url_liquidacion_operacion': None,
        'url_liquidacion_pendiente': None,
        'etiqueta_liquidacion_operacion': 'Liquidar operación',
        'etiqueta_liquidacion_pendiente': None,
        'resumen_liquidacion': {'tiene_datos': False},
    }
    if reserva is not None:
        liq = (
            LiquidacionPropietario.objects.filter(reserva=reserva)
            .exclude(estado='cancelada')
            .order_by('-id')
            .first()
        )
        if liq:
            ctx['liquidacion_operacion'] = liq
            ctx['url_liquidacion_operacion'] = reverse(
                'inmobiliaria:detalle_liquidacion', args=[liq.id]
            )
            ctx['etiqueta_liquidacion_operacion'] = f'Ver liquidación #{liq.id}'
        else:
            ctx['url_liquidacion_operacion'] = reverse(
                'inmobiliaria:crear_liquidacion_reserva', args=[reserva.id]
            )
        ctx['resumen_liquidacion'] = _resumen_liquidacion_caratula(
            reserva=reserva,
            liquidacion=ctx['liquidacion_operacion'],
            sucursal=reserva.sucursal,
        )
    elif contrato is not None:
        liq_pendiente = (
            LiquidacionPropietario.objects.filter(contrato=contrato, estado='pendiente')
            .order_by('-id')
            .first()
        )
        resumen_ctr = _resumen_liquidacion_contrato_caratula(contrato, contrato.sucursal)
        proxima = resumen_ctr.get('proxima_cuota_liquidar')
        estado_op_princ = _estado_liquidacion_operacion_principal_caratula(contrato, contrato.sucursal)

        if liq_pendiente:
            ctx['liquidacion_operacion'] = liq_pendiente
            ctx['url_liquidacion_pendiente'] = reverse(
                'inmobiliaria:detalle_liquidacion', args=[liq_pendiente.id]
            )
            ctx['etiqueta_liquidacion_pendiente'] = (
                f'Ver liquidación pendiente #{liq_pendiente.id}'
            )

        if estado_op_princ.get('liq_estado') == 'pendiente' and estado_op_princ.get('url_liquidar'):
            ctx['url_liquidacion_operacion'] = estado_op_princ['url_liquidar']
            ctx['etiqueta_liquidacion_operacion'] = 'Liquidar operación principal'
        elif proxima and proxima.url_liquidar:
            ctx['url_liquidacion_operacion'] = proxima.url_liquidar
            if proxima.es_anticipada_liquidable:
                ctx['etiqueta_liquidacion_operacion'] = (
                    f'Liquidar cuota {proxima.numero_cuota}/{contrato.duracion_meses} (anticipada)'
                )
            else:
                ctx['etiqueta_liquidacion_operacion'] = (
                    f'Liquidar cuota {proxima.numero_cuota}/{contrato.duracion_meses}'
                )
        elif liq_pendiente:
            ctx['url_liquidacion_operacion'] = ctx['url_liquidacion_pendiente']
            ctx['etiqueta_liquidacion_operacion'] = ctx['etiqueta_liquidacion_pendiente']
        else:
            ultima = (
                LiquidacionPropietario.objects.filter(contrato=contrato)
                .exclude(estado='cancelada')
                .order_by('-id')
                .first()
            )
            if ultima and resumen_ctr.get('completo'):
                ctx['liquidacion_operacion'] = ultima
                ctx['url_liquidacion_operacion'] = reverse(
                    'inmobiliaria:detalle_liquidacion', args=[ultima.id]
                )
                ctx['etiqueta_liquidacion_operacion'] = f'Ver liquidación #{ultima.id}'
            elif ultima:
                ctx['liquidacion_operacion'] = ultima
                ctx['url_liquidacion_operacion'] = reverse(
                    'inmobiliaria:crear_liquidacion_contrato', args=[contrato.id]
                )
                ctx['etiqueta_liquidacion_operacion'] = (
                    f'Ver liq. #{ultima.id} · {resumen_ctr["cuotas_liquidadas"]}/'
                    f'{resumen_ctr["total_cuotas"]} meses liquidados'
                )
            else:
                ctx['url_liquidacion_operacion'] = reverse(
                    'inmobiliaria:crear_liquidacion_contrato', args=[contrato.id]
                )
                prox = resumen_ctr.get('proxima_cuota_liquidar')
                if prox:
                    ctx['etiqueta_liquidacion_operacion'] = (
                        f'Liquidar cuota {prox.numero_cuota}/{contrato.duracion_meses}'
                    )
                else:
                    ctx['etiqueta_liquidacion_operacion'] = 'Nueva liquidación'
        ctx['resumen_liquidacion_contrato'] = resumen_ctr
        ctx['resumen_liquidacion'] = _resumen_liquidacion_caratula(
            contrato=contrato,
            liquidacion=ctx['liquidacion_operacion'],
            sucursal=contrato.sucursal,
        )
    return ctx


def _caratula_nombre_cliente(cliente):
    if not cliente:
        return '—'
    ap = (getattr(cliente, 'apellido', None) or '').strip()
    nom = (getattr(cliente, 'nombre', None) or '').strip()
    s = f'{ap}, {nom}'.strip(', ').strip()
    return s if s else '—'


def _tipo_reserva(propiedad):
    if not propiedad:
        return 'Alquiler por día'
    if getattr(propiedad, 'tipo_cliente', None) == 'ESTUDIANTE':
        return 'Estudiante'
    return 'Alquiler por día'


def _formato_miles_ar(val):
    try:
        if val is None:
            return '0'
        n = int(Decimal(str(val)))
        return f'{n:,}'.replace(',', '.')
    except (ValueError, TypeError, ArithmeticError):
        return '0'


def _formato_ficha_legacy(pk):
    if pk is None or pk == '':
        return '—'
    s = str(pk).strip().replace('.', '').replace(',', '')
    if s.isdigit():
        return _formato_miles_ar(int(s))
    return str(pk)


def _formato_importe_us(val):
    """Miles con coma y dos decimales (ej. 320,000.00 como en sistema viejo)."""
    try:
        d = Decimal(str(val or 0)).quantize(Decimal('0.01'))
    except Exception:
        return '0.00'
    neg = d < 0
    d = abs(d)
    whole, frac = f'{d:.2f}'.split('.')
    whole_fmt = f'{int(whole):,}'
    out = f'{whole_fmt}.{frac}'
    return ('-' if neg else '') + out


def _caratula_rotulo_prop_cli(prop, persona_cli):
    letra = '—'
    if prop and getattr(prop, 'propietario', None):
        ap = (prop.propietario.apellido or '').strip()
        if ap:
            letra = ap[0].upper()
    ap_cli = '—'
    if persona_cli:
        x = (persona_cli.apellido or '').strip().upper()
        if x:
            ap_cli = x
    if letra == '—' and ap_cli == '—':
        return '—'
    return f'{letra} - {ap_cli}'


def _tipo_movimiento_codigo_reserva(prop):
    if prop and getattr(prop, 'tipo_cliente', None) == 'ESTUDIANTE':
        return 'invierno'
    return 'alquiler'


def _tipo_movimiento_codigo_contrato(contrato):
    if hasattr(contrato, 'codigo_tipo_movimiento_caratula'):
        return contrato.codigo_tipo_movimiento_caratula()
    dm = contrato.duracion_meses or 0
    if dm == 9:
        return 'invierno'
    if dm >= 9:
        return 'meses_24'
    if dm == 6:
        return 'meses_6'
    return 'otros'


def _tipo_label_contrato_caratula(contrato):
    if hasattr(contrato, 'etiqueta_tipo_operacion_caratula'):
        return contrato.etiqueta_tipo_operacion_caratula()
    dm = int(contrato.duracion_meses or 0)
    if dm == 9:
        return 'Invierno (9 meses)'
    if dm == 24:
        return '24 meses'
    if dm >= 9:
        return f'24 meses — plan {dm} meses'
    return f'Contrato {dm} meses'


def _mapa_liquidacion_por_cuota_contrato(contrato):
    """cuota_id → última liquidación que la incluyó."""
    out = {}
    if not contrato or not contrato.propiedad_id:
        return out
    cuota_ids = set(contrato.cuotas.values_list('id', flat=True))
    for liq in (
        LiquidacionPropietario.objects.filter(propiedad_id=contrato.propiedad_id)
        .exclude(estado='cancelada')
        .order_by('id')
        .only('id', 'estado', 'operaciones_incluidas')
    ):
        for op in liq.operaciones_incluidas or []:
            if not isinstance(op, dict):
                continue
            tlo = (op.get('tipo') or '').lower()
            ids_cuota = []
            if tlo == 'contrato_cuota':
                try:
                    ids_cuota.append(int(op['id']))
                except (TypeError, ValueError):
                    pass
            for raw in op.get('cuotas_ids') or op.get('cuota_ids') or []:
                try:
                    ids_cuota.append(int(raw))
                except (TypeError, ValueError):
                    pass
            for cid in ids_cuota:
                if cid in cuota_ids:
                    out[cid] = liq
    return out


def _cuotas_liquidables_contrato(contrato, sucursal):
    """
    Cuotas que corresponden a liquidar del contrato.
    Incluye cobradas no liquidadas y cuotas anticipadas del plan (cualquier duración).
    """
    from inmobiliaria.views import (
        _cuotas_excluidas_por_liquidaciones_contrato,
        _cuotas_liquidables_para_contrato,
    )

    if not contrato or not contrato.propiedad_id:
        return set()
    cuotas_excluidas = _cuotas_excluidas_por_liquidaciones_contrato(contrato.propiedad)
    out = set()
    for cuota, _monto, _parcial, _anticipada in _cuotas_liquidables_para_contrato(
        contrato, cuotas_excluidas, sucursal
    ):
        out.add(cuota.id)

    return out


def _cuotas_pendientes_liquidar_contrato(contrato, sucursal):
    """IDs de cuotas incluibles en crear liquidación (aún no liquidadas)."""
    return _cuotas_liquidables_contrato(contrato, sucursal)


def _contrato_al_dia_liquidacion_cobros(contrato):
    """True si todas las cuotas ya cobradas figuran en alguna liquidación."""
    mapa = _mapa_liquidacion_por_cuota_contrato(contrato)
    cobradas = contrato.cuotas.filter(estado__in=['pagada', 'pagada_con_mora'])
    if not cobradas.exists():
        return False
    return all(c.id in mapa for c in cobradas)


def _ultima_liquidacion_contrato_id(contrato):
    mapa = _mapa_liquidacion_por_cuota_contrato(contrato)
    if not mapa:
        return None
    return max(liq.id for liq in mapa.values())


def _enriquecer_cuotas_liquidacion(cuotas_list, contrato, sucursal, movimientos=None):
    from inmobiliaria.cuotas_imputacion import (
        cuota_ids_mismo_recibo,
        mapa_movimientos_recibo_por_cuota_id,
    )

    mapa_liq = _mapa_liquidacion_por_cuota_contrato(contrato)
    liquidables = _cuotas_liquidables_contrato(contrato, sucursal)
    movs = list(movimientos or [])
    if movs and not any(getattr(c, 'recibos_cobro', None) for c in cuotas_list):
        recibos_map = mapa_movimientos_recibo_por_cuota_id(cuotas_list, movs)
        for c in cuotas_list:
            c.recibos_cobro = recibos_map.get(int(c.id), [])

    cuotas_by_id = {int(c.id): c for c in cuotas_list}
    grupos_liquidar: dict[tuple, int] = {}

    for c in cuotas_list:
        liq = mapa_liq.get(c.id)
        if liq:
            c.liq_estado = 'liquidada'
            c.liquidacion_id = liq.id
            c.liquidacion_estado = liq.get_estado_display()
            c.liquidacion_url = reverse('inmobiliaria:detalle_liquidacion', args=[liq.id])
            c.url_liquidar = None
            c.liquidacion_bloqueo_id = None
            c.es_anticipada_liquidable = False
            c.mostrar_btn_liquidar = False
            c.liq_es_grupo_recibo = False
            c.liq_grupo_recibo_etiqueta = ''
            c.liq_grupo_meses = ''
        elif c.id in liquidables:
            c.es_anticipada_liquidable = c.estado in ('pendiente', 'vencida')
            grupo_ids = cuota_ids_mismo_recibo(
                c,
                cuotas_list,
                movs,
                solo_ids=liquidables,
            )
            if c.es_anticipada_liquidable:
                grupo_ids = [int(c.id)]
            c.liq_cuotas_grupo_ids = grupo_ids
            c.liq_es_grupo_recibo = len(grupo_ids) > 1
            if c.liq_es_grupo_recibo:
                nums = [int(cuotas_by_id[cid].numero_cuota) for cid in grupo_ids]
                c.liq_grupo_meses = '–'.join(str(n) for n in sorted(nums))
                c.liq_grupo_recibo_etiqueta = f"Meses {c.liq_grupo_meses} (mismo recibo)"
            else:
                c.liq_grupo_meses = ''
                c.liq_grupo_recibo_etiqueta = ''
            grupo_key = tuple(sorted(grupo_ids))
            if grupo_key not in grupos_liquidar:
                grupos_liquidar[grupo_key] = min(
                    grupo_ids,
                    key=lambda cid: int(cuotas_by_id[cid].numero_cuota),
                )
            c.liq_estado = 'pendiente'
            c.liquidacion_id = None
            c.liquidacion_estado = ''
            c.liquidacion_url = None
            c.liquidacion_bloqueo_id = None
            qs_cuotas = ','.join(str(x) for x in sorted(grupo_ids))
            c.url_liquidar = (
                reverse('inmobiliaria:crear_liquidacion_contrato', args=[contrato.id])
                + f'?cuotas={qs_cuotas}'
            )
            c.mostrar_btn_liquidar = int(c.id) == grupos_liquidar[grupo_key]
        else:
            c.liq_estado = 'espera'
            c.liquidacion_id = None
            c.liquidacion_estado = ''
            c.liquidacion_url = None
            c.url_liquidar = None
            c.liquidacion_bloqueo_id = None
            c.es_anticipada_liquidable = False
            c.mostrar_btn_liquidar = False
            c.liq_es_grupo_recibo = False
            c.liq_grupo_recibo_etiqueta = ''
            c.liq_grupo_meses = ''
        c.es_operacion_principal = False


def _estado_liquidacion_operacion_principal_caratula(contrato, sucursal):
    """Estado de liquidación de honorarios / operación principal (no es una cuota mensual)."""
    from inmobiliaria.views import (
        _fila_operacion_principal_liquidacion,
        _liquidacion_operacion_principal_contrato,
    )

    ctx = {
        'liq_estado': 'espera',
        'liquidacion_id': None,
        'liquidacion_estado': '',
        'liquidacion_url': None,
        'url_liquidar': None,
        'liquidacion_bloqueo_id': None,
    }
    if not contrato or not contrato.propiedad_id:
        return ctx

    liq = _liquidacion_operacion_principal_contrato(contrato)
    if liq:
        ctx.update(
            {
                'liq_estado': 'liquidada',
                'liquidacion_id': liq.id,
                'liquidacion_estado': liq.get_estado_display(),
                'liquidacion_url': reverse('inmobiliaria:detalle_liquidacion', args=[liq.id]),
            }
        )
        return ctx

    if not _fila_operacion_principal_liquidacion(contrato, contrato.propiedad):
        return ctx

    ctx.update(
        {
            'liq_estado': 'pendiente',
            'url_liquidar': (
                reverse('inmobiliaria:crear_liquidacion_contrato', args=[contrato.id])
                + '?principal=1'
            ),
        }
    )
    return ctx


def _resumen_liquidacion_contrato_caratula(contrato, sucursal):
    """Conteo de cuotas liquidadas vs pendientes de liquidar."""
    cuotas = list(contrato.cuotas.all().order_by('numero_cuota'))
    _enriquecer_cuotas_liquidacion(cuotas, contrato, sucursal)
    liquidadas = sum(1 for c in cuotas if c.liq_estado == 'liquidada')
    pendientes = sum(1 for c in cuotas if c.liq_estado == 'pendiente')
    proxima = next((c for c in cuotas if getattr(c, 'mostrar_btn_liquidar', False)), None)
    if proxima is None:
        proxima = next((c for c in cuotas if c.liq_estado == 'pendiente'), None)
    return {
        'total_cuotas': len(cuotas),
        'cuotas_liquidadas': liquidadas,
        'cuotas_pendientes_liquidar': pendientes,
        'proxima_cuota_liquidar': proxima,
        'completo': pendientes == 0 and liquidadas > 0,
    }


def _liquidacion_contrato(contrato):
    if not contrato:
        return None
    return (
        LiquidacionPropietario.objects.filter(contrato=contrato)
        .exclude(estado='cancelada')
        .order_by('-id')
        .first()
    )


def _comisiones_override_caratula(request, contrato_id):
    overrides = dict(request.session.get(CARATULA_COMISIONES_OVERRIDES_KEY, {}))
    raw = overrides.get(str(contrato_id)) or {}
    out = {}
    for key in ('comision_locador', 'comision_locatario'):
        if raw.get(key) is not None:
            try:
                out[key] = Decimal(str(raw[key])).quantize(Decimal('0.01'))
            except (ArithmeticError, TypeError, ValueError):
                pass
    return out or None


def _set_comisiones_override_caratula(request, contrato_id, comision_locador, comision_locatario):
    overrides = dict(request.session.get(CARATULA_COMISIONES_OVERRIDES_KEY, {}))
    overrides[str(contrato_id)] = {
        'comision_locador': str(comision_locador.quantize(Decimal('0.01'))),
        'comision_locatario': str(comision_locatario.quantize(Decimal('0.01'))),
    }
    request.session[CARATULA_COMISIONES_OVERRIDES_KEY] = overrides
    request.session.modified = True


def _comisiones_cobradas_contrato(contrato, movimientos=None, liquidacion=None, override=None):
    """Participación (85) y honorarios (25) de la operación principal del contrato."""
    from inmobiliaria.views import (
        _comisiones_sugeridas_primera_cuota_contrato,
        _honorarios_cobrados_en_movimiento_contrato,
        _participacion_cobrada_en_movimiento_contrato,
    )

    locador = Decimal('0')
    locatario = Decimal('0')
    movs = list(movimientos or [])
    if not movs and contrato.propiedad_id:
        movs = [
            m
            for m in _movimientos_contrato_qs(contrato)[:300]
            if m.tipo == TipoMovimientoCajaEnum.INGRESO
            and m.concepto
            and re.search(rf'Contrato\s*#\s*{contrato.id}\b', m.concepto, re.IGNORECASE)
        ]
    for mov in movs:
        locador += _participacion_cobrada_en_movimiento_contrato(mov)
        locatario += _honorarios_cobrados_en_movimiento_contrato(mov)
    locador = locador.quantize(Decimal('0.01'))
    locatario = locatario.quantize(Decimal('0.01'))

    if liquidacion is None:
        liquidacion = _liquidacion_contrato(contrato)
    if liquidacion:
        liq_loc = Decimal(str(getattr(liquidacion, 'comision_locador', None) or 0))
        liq_locat = Decimal(str(getattr(liquidacion, 'comision_locatario', None) or 0))
        if liq_loc > Decimal('0.05'):
            locador = liq_loc.quantize(Decimal('0.01'))
        if liq_locat > Decimal('0.05'):
            locatario = liq_locat.quantize(Decimal('0.01'))
    elif override:
        if override.get('comision_locador') is not None:
            locador = Decimal(str(override['comision_locador'])).quantize(Decimal('0.01'))
        if override.get('comision_locatario') is not None:
            locatario = Decimal(str(override['comision_locatario'])).quantize(Decimal('0.01'))

    if getattr(contrato, 'operacion_principal', False):
        sugeridas = _comisiones_sugeridas_primera_cuota_contrato(contrato)
        if locador <= Decimal('0.05'):
            locador = Decimal(str(sugeridas.get('comision_locador') or 0)).quantize(Decimal('0.01'))
        if locatario <= Decimal('0.05'):
            locatario = Decimal(str(sugeridas.get('comision_locatario') or 0)).quantize(Decimal('0.01'))

    return locador, locatario


def _filas_honorarios_caratula_contrato(contrato, movimientos=None):
    """Líneas de conceptos cobrados en la operación principal (primer ingreso del contrato)."""
    from inmobiliaria.decimal_utils import parse_decimal_monto
    from inmobiliaria.views import _movimiento_json_conceptos_parsed

    movs_op = sorted(
        [
            m
            for m in (movimientos or [])
            if m.tipo == TipoMovimientoCajaEnum.INGRESO
        ],
        key=lambda x: (x.fecha or datetime.min, x.id),
    )
    if not movs_op and contrato.propiedad_id:
        movs_op = sorted(
            [
                m
                for m in _movimientos_contrato_qs(contrato)[:300]
                if m.tipo == TipoMovimientoCajaEnum.INGRESO
                and m.concepto
                and re.search(rf'Contrato\s*#\s*{contrato.id}\b', m.concepto, re.IGNORECASE)
            ],
            key=lambda x: (x.fecha or datetime.min, x.id),
        )
    if not movs_op:
        return []

    mov = movs_op[0]
    _, conceptos = _movimiento_json_conceptos_parsed(mov)
    recibo = _numero_recibo_desde_movimiento(mov)
    fecha = mov.fecha
    filas = []

    if conceptos:
        for c in conceptos:
            cid = str(c.get('id', c.get('codigo', ''))).strip()
            nombre = (c.get('nombre') or _CONCEPTO_HONORARIOS_LABELS.get(cid) or f'Concepto {cid}').strip()
            imp = parse_decimal_monto(c.get('importe', 0))
            if imp <= Decimal('0.05'):
                continue
            filas.append(
                {
                    'recibo': recibo,
                    'fecha': fecha,
                    'codigo': cid,
                    'concepto': nombre,
                    'importe': imp.quantize(Decimal('0.01')),
                }
            )
    else:
        part = Decimal('0')
        hon = Decimal('0')
        from inmobiliaria.views import (
            _honorarios_cobrados_en_movimiento_contrato,
            _participacion_cobrada_en_movimiento_contrato,
        )

        part = _participacion_cobrada_en_movimiento_contrato(mov)
        hon = _honorarios_cobrados_en_movimiento_contrato(mov)
        if part > Decimal('0.05'):
            filas.append(
                {
                    'recibo': recibo,
                    'fecha': fecha,
                    'codigo': '85',
                    'concepto': _CONCEPTO_HONORARIOS_LABELS['85'],
                    'importe': part,
                }
            )
        if hon > Decimal('0.05'):
            filas.append(
                {
                    'recibo': recibo,
                    'fecha': fecha,
                    'codigo': '25',
                    'concepto': _CONCEPTO_HONORARIOS_LABELS['25'],
                    'importe': hon,
                }
            )

    return filas


def _pct_productor_contrato_caratula(contrato):
    """Porcentajes del vendedor para calcular comisión del productor sobre honorarios."""
    from inmobiliaria.models.comision import porcentaje_fichaje_vendedor

    if not contrato or not contrato.vendedor_id:
        return {}

    vend = contrato.vendedor
    prop = contrato.propiedad
    tipo_fichaje = getattr(prop, 'tipo_fichaje', None) or 'primer'
    vend_fichaje = _vendedor_fichaje_contrato_caratula(contrato)
    pct_fichaje = porcentaje_fichaje_vendedor(vend_fichaje, tipo_fichaje)
    dm = int(contrato.duracion_meses or 0)
    cat = (
        contrato.categoria_tipo_operacion()
        if hasattr(contrato, 'categoria_tipo_operacion')
        else ('invierno' if dm == 9 else ('24' if dm >= 9 else 'otro'))
    )
    if cat == 'invierno':
        pct_tipo = vend.comision_invierno
        label_tipo = 'Invierno'
    elif cat == '24':
        pct_tipo = vend.comision_alquiler_24_meses
        label_tipo = '24 meses' if dm == 24 else 'Largo plazo'
    else:
        pct_tipo = None
        label_tipo = ''

    fecha_entrada = getattr(contrato, 'fecha_entrada_departamento', None) or contrato.fecha_inicio

    return {
        'tipo_fichaje': tipo_fichaje,
        'pct_fichaje': float(pct_fichaje) if pct_fichaje is not None else None,
        'fichador': _nombre_productor_papel(vend_fichaje),
        'pct_tipo': float(pct_tipo) if pct_tipo is not None else None,
        'label_tipo': label_tipo,
        'categoria': cat,
        'productor': _nombre_productor_papel(vend),
        'fecha_entrada': fecha_entrada.isoformat() if fecha_entrada else None,
        'fecha_entrada_display': fecha_entrada.strftime('%d/%m/%Y') if fecha_entrada else '—',
    }


def _ctx_honorarios_comisiones_caratula_contrato(
    contrato, movimientos=None, liquidacion=None, override=None
):
    from inmobiliaria.decimal_utils import format_monto_argentino
    from inmobiliaria.views import _liquidacion_operacion_principal_contrato

    if liquidacion is None:
        liquidacion = _liquidacion_operacion_principal_contrato(contrato)

    comision_locador, comision_locatario = _comisiones_cobradas_contrato(
        contrato, movimientos, liquidacion=liquidacion, override=override
    )
    comisiones_vendedor = _comisiones_vendedor_contrato_caratula(contrato, comision_locatario)
    comisiones_fichaje = [cv for cv in comisiones_vendedor if cv.get('rol') == 'fichaje']
    comisiones_productor = [cv for cv in comisiones_vendedor if cv.get('rol') != 'fichaje']
    comision_fichaje_total = sum(
        (Decimal(str(cv.get('monto') or 0)) for cv in comisiones_fichaje),
        Decimal('0'),
    ).quantize(Decimal('0.01'))
    comision_productor_total = sum(
        (
            Decimal(str(cv.get('monto') or 0))
            for cv in comisiones_vendedor
            if cv.get('rol') != 'fichaje'
        ),
        Decimal('0'),
    ).quantize(Decimal('0.01'))

    pct = _pct_productor_contrato_caratula(contrato)
    fichador_nombre = ''
    if comisiones_fichaje:
        fichador_nombre = comisiones_fichaje[0].get('vendedor_nombre') or ''
    elif pct.get('fichador'):
        fichador_nombre = pct['fichador']

    import json as _json

    return {
        'filas_honorarios': _filas_honorarios_caratula_contrato(contrato, movimientos),
        'comision_locador': comision_locador,
        'comision_locatario': comision_locatario,
        'comision_locador_fmt': format_monto_argentino(comision_locador),
        'comision_locatario_fmt': format_monto_argentino(comision_locatario),
        'comisiones_total': (comision_locador + comision_locatario).quantize(Decimal('0.01')),
        'comisiones_total_fmt': format_monto_argentino(comision_locador + comision_locatario),
        'comisiones_vendedor': comisiones_vendedor,
        'comisiones_fichaje': comisiones_fichaje,
        'comisiones_productor': comisiones_productor,
        'comision_fichaje_total': comision_fichaje_total,
        'comision_fichaje_total_fmt': format_monto_argentino(comision_fichaje_total),
        'comision_productor_total': comision_productor_total,
        'comision_productor_total_fmt': format_monto_argentino(comision_productor_total),
        'fichador_nombre': fichador_nombre,
        'pct_productor': pct,
        'pct_productor_json': _json.dumps(pct),
        'liquidacion_id': getattr(liquidacion, 'id', None),
        'puede_guardar_comisiones': liquidacion is not None,
    }


def _vendedor_fichaje_contrato_caratula(contrato):
    """Vendedor del fichaje: ficha de la propiedad o comisión fichaje ya registrada."""
    from inmobiliaria.models.comision import ROL_COMISION_FICHAJE, vendedor_fichaje_desde_propiedad

    prop = getattr(contrato, 'propiedad', None) if contrato else None
    vend = vendedor_fichaje_desde_propiedad(prop) if prop else None
    if vend:
        return vend
    com = (
        ComisionVendedor.objects.filter(
            contrato=contrato,
            rol_comision=ROL_COMISION_FICHAJE,
        )
        .exclude(estado='cancelada')
        .select_related('vendedor')
        .order_by('-id')
        .first()
    )
    return com.vendedor if com and com.vendedor_id else None


def _label_fichaje_contrato(tipo_fichaje):
    tf = (tipo_fichaje or 'primer').strip().lower()
    if tf == 'segundo':
        return 'COMIS. VENDEDOR (SEGUNDO FICHAJE)'
    return 'COMIS. VENDEDOR (PRIMER FICHAJE)'


def _agregar_linea_fichaje_contrato_caratula(lineas, contrato, honorarios_monto):
    from inmobiliaria.models.comision import ROL_COMISION_FICHAJE, porcentaje_fichaje_vendedor

    if any(l.get('rol') == ROL_COMISION_FICHAJE for l in lineas):
        return
    prop = contrato.propiedad
    tipo_fichaje = getattr(prop, 'tipo_fichaje', None) or 'primer'
    vend_fichaje = _vendedor_fichaje_contrato_caratula(contrato)
    pct_fichaje = porcentaje_fichaje_vendedor(vend_fichaje, tipo_fichaje)
    if not vend_fichaje or pct_fichaje is None or pct_fichaje <= 0:
        com = (
            ComisionVendedor.objects.filter(
                contrato=contrato,
                rol_comision=ROL_COMISION_FICHAJE,
            )
            .exclude(estado='cancelada')
            .select_related('vendedor')
            .order_by('-id')
            .first()
        )
        if not com or not com.vendedor_id:
            return
        vend_fichaje = com.vendedor
        pct_fichaje = com.porcentaje_comision or porcentaje_fichaje_vendedor(
            vend_fichaje, tipo_fichaje
        )
        if pct_fichaje is None or pct_fichaje <= 0:
            return
    monto = (honorarios_monto * Decimal(str(pct_fichaje)) / Decimal('100')).quantize(Decimal('0.01'))
    lineas.insert(
        0,
        {
            'label': _label_fichaje_contrato(tipo_fichaje),
            'monto': monto,
            'monto_fmt': _formato_importe_us(monto),
            'porcentaje': pct_fichaje,
            'rol': ROL_COMISION_FICHAJE,
            'vendedor_nombre': _nombre_productor_papel(vend_fichaje),
            'vendedor_id': vend_fichaje.id,
        },
    )


def _comisiones_vendedor_contrato_caratula(contrato, honorarios_monto):
    """
    Líneas de comisión sobre honorarios: fichaje al vendedor que fichó la propiedad
    (puede ser distinto del productor del contrato); invierno / 24 meses al productor.
    """
    from inmobiliaria.models.comision import (
        ROL_COMISION_FICHAJE,
        porcentaje_fichaje_vendedor,
    )

    if not contrato or honorarios_monto <= Decimal('0.05'):
        return []

    prop = contrato.propiedad
    lineas = []
    tipo_fichaje = getattr(prop, 'tipo_fichaje', None) or 'primer'

    vend_fichaje = _vendedor_fichaje_contrato_caratula(contrato)
    pct_fichaje = porcentaje_fichaje_vendedor(vend_fichaje, tipo_fichaje)
    if vend_fichaje and pct_fichaje is not None and pct_fichaje > 0:
        monto = (honorarios_monto * Decimal(str(pct_fichaje)) / Decimal('100')).quantize(
            Decimal('0.01')
        )
        lineas.append(
            {
                'label': _label_fichaje_contrato(tipo_fichaje),
                'monto': monto,
                'monto_fmt': _formato_importe_us(monto),
                'porcentaje': pct_fichaje,
                'rol': ROL_COMISION_FICHAJE,
                'vendedor_nombre': _nombre_productor_papel(vend_fichaje),
                'vendedor_id': vend_fichaje.id,
            }
        )
    else:
        _agregar_linea_fichaje_contrato_caratula(lineas, contrato, honorarios_monto)

    if not contrato.vendedor_id:
        return lineas

    vend = contrato.vendedor
    cat = (
        contrato.categoria_tipo_operacion()
        if hasattr(contrato, 'categoria_tipo_operacion')
        else ('invierno' if int(contrato.duracion_meses or 0) == 9 else '24')
    )
    if cat == 'invierno':
        pct = vend.comision_invierno
        label = 'COMIS. VENDEDOR (INVIERNO)'
    elif cat == '24':
        pct = vend.comision_alquiler_24_meses
        dm = int(contrato.duracion_meses or 0)
        label = 'COMIS. VENDEDOR (24 MESES)' if dm == 24 else 'COMIS. VENDEDOR (LARGO PLAZO)'
    else:
        return lineas

    if pct is not None and pct > 0:
        monto = (honorarios_monto * Decimal(str(pct)) / Decimal('100')).quantize(Decimal('0.01'))
        lineas.append(
            {
                'label': label,
                'monto': monto,
                'monto_fmt': _formato_importe_us(monto),
                'porcentaje': pct,
                'rol': 'productor',
                'vendedor_nombre': _nombre_productor_papel(vend),
                'vendedor_id': vend.id,
            }
        )
    return lineas


def _dni_formato_legado(dni):
    if not dni:
        return '0'
    digits = ''.join(c for c in str(dni) if c.isdigit())
    if len(digits) >= 7:
        return _formato_miles_ar(int(digits))
    return str(dni).strip() or '0'


def _domicilio_una_linea(persona):
    if not persona:
        return '—'
    parts = [
        (getattr(persona, 'domicilio', None) or '').strip(),
        (getattr(persona, 'localidad', None) or '').strip(),
        (getattr(persona, 'provincia', None) or '').strip(),
    ]
    s = ', '.join(p for p in parts if p)
    return s if s else '—'


def _propietario_legado(propi):
    """Formato legado: línea 1 = id | apellido nombre; línea 2 = domicilio | CP | localidad."""
    if not propi:
        return {
            'id_fmt': '0',
            'rotulo': '—',
            'ubic': '—',
            'linea1': '—',
            'linea2': '—',
            'nombre_display': '—',
        }
    id_fmt = _formato_miles_ar(propi.id)
    ap = (propi.apellido or '').strip().upper()
    nom = (propi.nombre or '').strip().upper()
    nombre = f'{ap} {nom}'.strip() or '—'
    linea1 = f'{id_fmt} | {nombre}'
    nombre_display = _nombre_propietario_papel(propi)
    dom = (propi.domicilio or '').strip().upper()
    cp = (getattr(propi, 'codigo_postal', None) or '').strip()
    loc = (propi.localidad or '').strip().upper()
    prov = (propi.provincia or '').strip().upper()
    partes = [p for p in (dom, cp, loc or prov) if p]
    linea2 = ' | '.join(partes) if partes else '—'
    rotulo = (ap[:1] if ap else '—')
    return {
        'id_fmt': id_fmt,
        'rotulo': rotulo,
        'ubic': linea2,
        'linea1': linea1,
        'linea2': linea2,
        'nombre_display': nombre_display,
    }


def _turista_legado(cli):
    if not cli:
        return {'dni': '0', 'nombre': '—', 'dom': '—', 'linea1': '—'}
    ap = (cli.apellido or '').strip().upper()
    nom = (cli.nombre or '').strip().upper()
    nombre_fmt = f'{ap} {nom}'.strip() or '—'
    dni_fmt = _dni_formato_legado(cli.dni)
    return {
        'dni': dni_fmt,
        'nombre': nombre_fmt,
        'dom': _domicilio_una_linea(cli).upper(),
        'linea1': f'{dni_fmt} | {nombre_fmt}',
    }


def _origen_operacion_sucursal(sucursal):
    if not sucursal:
        return '1 OFICINA'
    sid = getattr(sucursal, 'id', '') or '1'
    nom = (getattr(sucursal, 'nombre', None) or 'OFICINA').strip().upper()
    return f'{sid} | {nom}'[:48]


def _prop_piso_depto_campos(prop):
    """Piso y depto por separado para formato legado con | entre columnas."""
    if not prop:
        return ('—', '—')
    pi = (prop.piso or '').strip().upper() or '—'
    dep = (prop.departamento or '').strip().upper() or '—'
    return (pi, dep)


def _build_legacy_reserva(
    reserva,
    recibos,
    comisiones,
    saldo_reserva,
    tipo_operacion_str,
    movimientos=None,
):
    prop = reserva.propiedad
    cli = reserva.cliente
    propi = getattr(prop, 'propietario', None) if prop else None
    vend = reserva.vendedor

    recibo_loc, recibo_locat, url_recibo_loc, url_recibo_locat = _recibos_legacy_par(
        movimientos or [],
        recibos,
        sucursal=reserva.sucursal,
        reserva=reserva,
    )

    comision_total = sum(Decimal(str(c.monto_comision or 0)) for c in comisiones)

    pi_disp, dep_disp = _prop_piso_depto_campos(prop)
    piso_dto = '—'
    if prop:
        pi = (prop.piso or '').strip()
        dep = (prop.departamento or '').strip()
        piso_dto = f'{pi}{dep}' if pi and dep else (pi or dep or '—')

    llave_cod = '0'
    if prop:
        raw = (getattr(prop, 'llave', None) or '').strip()
        llave_cod = raw if raw else '0'

    productor = _nombre_productor_papel(vend)

    terceros = _formato_miles_ar(vend.id) if vend else '0'

    dias_estadia = 1
    if reserva.fecha_fin and reserva.fecha_inicio:
        dias_estadia = max(1, (reserva.fecha_fin - reserva.fecha_inicio).days)
    loc_mensual = Decimal('0')
    if reserva.precio_total:
        try:
            loc_mensual = (Decimal(str(reserva.precio_total)) / Decimal(dias_estadia)).quantize(
                Decimal('0.01')
            )
        except (ArithmeticError, ValueError, TypeError):
            loc_mensual = Decimal('0')

    tr = _turista_legado(cli)

    return {
        'numero_original': '0',
        'numero_operacion': _formato_miles_ar(reserva.id),
        'fecha_registro': reserva.fecha_creacion,
        'tipo_mov': _tipo_movimiento_codigo_reserva(prop),
        'ficha_prop': _formato_ficha_legacy(prop.id) if prop else '—',
        'dir_prop': (prop.direccion or '—').upper() if prop else '—',
        'piso_depto': piso_dto,
        'prop_piso': pi_disp,
        'prop_depto': dep_disp,
        'codigo_llave': llave_cod,
        'propietario': _propietario_legado(propi),
        'turista': tr,
        'garante_id': tr['dni'],
        'garante_linea': tr['linea1'],
        'caratula_rotulo': _caratula_rotulo_prop_cli(prop, cli),
        'importe_locacion': _formato_importe_us(reserva.precio_total),
        'senia': _formato_importe_us(reserva.senia),
        'refuerzo': '0.00',
        'fecha_refuerzo': '',
        'deposito': _formato_importe_us(reserva.deposito_garantia),
        'saldo': _formato_importe_us(saldo_reserva),
        'comision_locador': _formato_importe_us(0),
        'comision_locatario': _formato_importe_us(comision_total),
        'comisiones_total': _formato_importe_us(comision_total),
        'comisiones_vendedor': [],
        'comision_productor_total': _formato_importe_us(0),
        'recibo_locador': recibo_loc,
        'recibo_locatario': recibo_locat,
        'url_recibo_locador': url_recibo_loc,
        'url_recibo_locatario': url_recibo_locat,
        'productor': productor,
        'terceros': terceros,
        'origen_operacion': _origen_operacion_sucursal(reserva.sucursal),
        'estado_txt': reserva.get_estado_display(),
        'locacion_mensual': _formato_importe_us(loc_mensual),
        'carpeta': '—',
        'tipo_operacion_str': tipo_operacion_str,
    }


def _ctx_completar_pago_reserva(reserva):
    saldo = Decimal(str(reserva.cuota_pendiente or 0))
    if saldo <= 0:
        saldo = (Decimal(str(reserva.precio_total or 0)) - Decimal(str(reserva.senia or 0)))
    puede = saldo > Decimal('0.005')
    return {
        'saldo_pendiente_pago': saldo,
        'puede_completar_pago': puede,
        'url_completar_pago': (
            reverse('inmobiliaria:finalizar_reserva_nueva', args=[reserva.id]) if puede else None
        ),
        'etiqueta_completar_pago': (
            'Completar pago' if (reserva.senia or 0) > 0 else 'Finalizar reserva'
        ),
    }


def _build_legacy_contrato(contrato, cuotas, tipo_label, carpeta_override=None, movimientos=None, liquidacion=None, override=None):
    prop = contrato.propiedad
    inq = contrato.inquilino
    propi = getattr(prop, 'propietario', None) if prop else None
    vend = contrato.vendedor

    garantes = list(contrato.garantes.all()[:1])
    tr_inq = _turista_legado(inq)
    if garantes:
        g0 = garantes[0]
        garante_id = _dni_formato_legado(g0.dni)
        garante_linea = _turista_legado(g0)['linea1']
    elif contrato.garante_dni:
        garante_id = _dni_formato_legado(contrato.garante_dni)
        ap_g = (contrato.garante_apellido or '').strip().upper()
        nom_g = (contrato.garante_nombre or '').strip().upper()
        nom_g_fmt = f'{ap_g} {nom_g}'.strip() or '—'
        garante_linea = f'{garante_id} | {nom_g_fmt}'
    else:
        garante_id = tr_inq['dni']
        garante_linea = tr_inq['linea1']

    total_contrato = (contrato.precio_mensual or Decimal(0)) * Decimal(contrato.duracion_meses or 0)
    saldo_cuotas = sum(
        Decimal(str(c.monto_total or 0)) for c in cuotas if getattr(c, 'estado', '') == 'pendiente'
    )

    pi_disp, dep_disp = _prop_piso_depto_campos(prop)
    piso_dto = '—'
    if prop:
        pi = (prop.piso or '').strip()
        dep = (prop.departamento or '').strip()
        piso_dto = f'{pi}{dep}' if pi and dep else (pi or dep or '—')

    llave_cod = '0'
    if prop:
        raw = (getattr(prop, 'llave', None) or '').strip()
        llave_cod = raw if raw else '0'

    productor = _nombre_productor_papel(vend)
    terceros = _formato_miles_ar(vend.id) if vend else '0'

    meses_contrato = int(contrato.duracion_meses or 0)
    recibo_loc, recibo_locat, url_recibo_loc, url_recibo_locat = _recibos_legacy_par(
        movimientos or [],
        [],
        sucursal=contrato.sucursal,
    )

    comision_locador, comision_locatario = _comisiones_cobradas_contrato(
        contrato, movimientos, liquidacion=liquidacion, override=override
    )
    comisiones_vendedor = _comisiones_vendedor_contrato_caratula(contrato, comision_locatario)
    comisiones_fichaje = [cv for cv in comisiones_vendedor if cv.get('rol') == 'fichaje']
    comisiones_total = (comision_locador + comision_locatario).quantize(Decimal('0.01'))
    comision_fichaje_total = sum(
        (Decimal(str(cv.get('monto') or 0)) for cv in comisiones_fichaje),
        Decimal('0'),
    ).quantize(Decimal('0.01'))
    comision_productor_total = sum(
        (
            Decimal(str(cv.get('monto') or 0))
            for cv in comisiones_vendedor
            if cv.get('rol') != 'fichaje'
        ),
        Decimal('0'),
    ).quantize(Decimal('0.01'))
    fichador_nombre = comisiones_fichaje[0].get('vendedor_nombre', '') if comisiones_fichaje else ''

    return {
        'numero_original': '0',
        'numero_operacion': _formato_miles_ar(contrato.id),
        # Fecha de cabecera como en legado (día de operación), no alta en sistema
        'fecha_registro': contrato.fecha_operacion,
        'tipo_mov': _tipo_movimiento_codigo_contrato(contrato),
        'ficha_prop': _formato_ficha_legacy(prop.id) if prop else '—',
        'dir_prop': (prop.direccion or '—').upper() if prop else '—',
        'piso_depto': piso_dto,
        'prop_piso': pi_disp,
        'prop_depto': dep_disp,
        'codigo_llave': llave_cod,
        'propietario': _propietario_legado(propi),
        'turista': tr_inq,
        'garante_id': garante_id,
        'garante_linea': garante_linea,
        'caratula_rotulo': _caratula_rotulo_prop_cli(prop, inq),
        'importe_locacion': _formato_importe_us(total_contrato),
        'senia': _formato_importe_us(0),
        'refuerzo': '0.00',
        'fecha_refuerzo': '',
        'deposito': _formato_importe_us(contrato.deposito_garantia),
        'saldo': _formato_importe_us(saldo_cuotas),
        'comision_locador': _formato_importe_us(comision_locador),
        'comision_locatario': _formato_importe_us(comision_locatario),
        'comisiones_total': _formato_importe_us(comisiones_total),
        'comisiones_vendedor': comisiones_vendedor,
        'comision_productor_total': _formato_importe_us(comision_productor_total),
        'comision_fichaje_total': _formato_importe_us(comision_fichaje_total),
        'fichador_nombre': fichador_nombre,
        'recibo_locador': recibo_loc,
        'recibo_locatario': recibo_locat,
        'url_recibo_locador': url_recibo_loc,
        'url_recibo_locatario': url_recibo_locat,
        'productor': productor,
        'terceros': terceros,
        'origen_operacion': _origen_operacion_sucursal(contrato.sucursal),
        'estado_txt': contrato.get_estado_display(),
        'locacion_mensual': _formato_importe_us(contrato.precio_mensual),
        'carpeta': _normalizar_carpeta(carpeta_override) if carpeta_override else '—',
        'tipo_operacion_str': tipo_label,
    }


def _tokens_busqueda_caratulas(q):
    """Palabras para buscar persona (soporta 'Apellido, Nombre' o varias palabras)."""
    if not (q or '').strip():
        return []
    tokens = []
    for part in re.split(r'[,;]+', q):
        for t in part.split():
            t = t.strip()
            if len(t) >= 2:
                tokens.append(t)
    if not tokens:
        t = q.strip()
        if t:
            tokens = [t]
    return tokens


def _q_busqueda_persona_caratulas(prefix, tokens):
    """Búsqueda por nombre/apellido; con varias palabras, cada una debe coincidir en algún campo."""
    if not tokens:
        return Q()
    combined = Q()
    for tok in tokens:
        one = (
            Q(**{f'{prefix}__nombre__icontains': tok})
            | Q(**{f'{prefix}__apellido__icontains': tok})
        )
        combined &= one
    return combined


def _q_busqueda_texto_caratulas(q, tokens):
    """Dirección, título, propietario, inquilino/cliente."""
    q_obj = (
        Q(propiedad__direccion__icontains=q)
        | Q(propiedad__ubicacion__icontains=q)
        | Q(propiedad__titulo__icontains=q)
        | Q(propiedad__propietario__nombre__icontains=q)
        | Q(propiedad__propietario__apellido__icontains=q)
        | Q(propiedad__propietario__dni__icontains=q)
        | Q(propiedad__propietario__cuit__icontains=q)
        | Q(propiedad__propietario__email__icontains=q)
    )
    if tokens:
        q_obj |= _q_busqueda_persona_caratulas('propiedad__propietario', tokens)
    if q.isdigit():
        try:
            q_obj |= Q(propiedad__id=int(q))
        except (TypeError, ValueError):
            pass
    return q_obj


def _fecha_operacion_reserva(reserva):
    fc = getattr(reserva, 'fecha_creacion', None)
    if fc:
        try:
            return timezone.localtime(fc).date()
        except Exception:
            return fc.date() if hasattr(fc, 'date') else reserva.fecha_inicio
    return reserva.fecha_inicio


def _instante_operacion_reserva(reserva):
    """Momento en que se cargó la reserva (para orden cronológico)."""
    fc = getattr(reserva, 'fecha_creacion', None)
    if fc:
        try:
            return timezone.localtime(fc)
        except Exception:
            pass
        if timezone.is_aware(fc):
            return fc
        return timezone.make_aware(fc, timezone.get_current_timezone())
    fi = getattr(reserva, 'fecha_inicio', None)
    if fi:
        return timezone.make_aware(
            datetime.combine(fi, datetime.min.time()),
            timezone.get_current_timezone(),
        )
    return timezone.localtime(timezone.now())


def _instante_operacion_contrato(contrato):
    """Momento de alta en sistema; desempate por fecha_operacion y nº."""
    fc = getattr(contrato, 'fecha_creacion', None)
    if fc:
        try:
            return timezone.localtime(fc)
        except Exception:
            pass
        if timezone.is_aware(fc):
            return fc
        return timezone.make_aware(fc, timezone.get_current_timezone())
    fo = getattr(contrato, 'fecha_operacion', None)
    if fo:
        return timezone.make_aware(
            datetime.combine(fo, datetime.min.time()),
            timezone.get_current_timezone(),
        )
    return timezone.localtime(timezone.now())


@login_required
def lista_caratulas(request):
    """Tabla tipo consultorio: tipo, número, fecha, carátula, dirección, piso/depto, ficha."""
    if not _puede_ver_caratulas(request.user):
        return HttpResponseForbidden()
    if request.method == 'POST' and request.POST.get('action') == 'set_carpeta_default':
        _set_carpeta_default(request, request.POST.get('carpeta_default'))
        redirect_to = request.POST.get('redirect_to', '').strip() or reverse('inmobiliaria:lista_caratulas')
        return redirect(redirect_to)
    sucursal = getattr(request.user, 'sucursal', None)
    q = request.GET.get('q', '').strip()
    operacion = request.GET.get('operacion', '').strip()
    tipo_filtro = request.GET.get('tipo', '').strip()
    liquidacion_filtro = request.GET.get('liquidacion', '').strip()
    today = timezone.localdate().isoformat()
    raw_desde = request.GET.get('fecha_desde', '').strip()
    raw_hasta = request.GET.get('fecha_hasta', '').strip()
    periodo_completo = request.GET.get('todo') == '1'

    if periodo_completo:
        fecha_desde = raw_desde
        fecha_hasta = raw_hasta
    elif raw_desde == '' and raw_hasta == '':
        fecha_desde = fecha_hasta = today
    else:
        fecha_desde = raw_desde
        fecha_hasta = raw_hasta

    if not sucursal:
        paginator_empty = Paginator([], 40)
        lista_filtros_qs = _query_string_lista_caratulas(
            q=q,
            operacion=operacion,
            fecha_desde=fecha_desde if not periodo_completo else '',
            fecha_hasta=fecha_hasta if not periodo_completo else '',
            tipo_filtro=tipo_filtro,
            liquidacion_filtro=liquidacion_filtro,
            periodo_completo=periodo_completo,
        )
        return render(
            request,
            'inmobiliaria/caratulas/lista.html',
            {
                'error': 'Tu usuario no tiene sucursal asignada.',
                'filas': paginator_empty.page(1),
                'q': q,
                'operacion': operacion,
                'fecha_desde': fecha_desde if not periodo_completo else '',
                'fecha_hasta': fecha_hasta if not periodo_completo else '',
                'tipo_filtro': tipo_filtro,
                'liquidacion_filtro': liquidacion_filtro,
                'periodo_completo': periodo_completo,
                'carpeta_default': _carpeta_default_actual(request),
                'lista_filtros_qs': lista_filtros_qs,
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

    operacion_num = None
    if operacion:
        solo_num = re.sub(r'[^0-9]', '', operacion)
        if solo_num:
            try:
                operacion_num = int(solo_num.lstrip('0') or '0')
            except (TypeError, ValueError):
                operacion_num = None
        reservas = reservas.filter(id=operacion_num) if operacion_num is not None else reservas.none()

    busqueda_por_numero = operacion_num is not None or (bool(q) and q.isdigit())
    omitir_filtro_fechas = periodo_completo or busqueda_por_numero

    if q:
        tokens = _tokens_busqueda_caratulas(q)
        q_res = _q_busqueda_texto_caratulas(q, tokens)
        q_res |= _q_busqueda_persona_caratulas('cliente', tokens)
        if q.isdigit():
            try:
                q_res |= Q(id=int(q))
            except (TypeError, ValueError):
                pass
        reservas = reservas.filter(q_res)

    dr_desde = None
    dr_hasta = None
    if not omitir_filtro_fechas:
        if fecha_desde:
            try:
                dr_desde = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
            except ValueError:
                pass
        if fecha_hasta:
            try:
                dr_hasta = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
            except ValueError:
                pass
        if dr_desde and dr_hasta and dr_hasta < dr_desde:
            dr_desde, dr_hasta = dr_hasta, dr_desde
        if dr_desde and dr_hasta:
            reservas = reservas.filter(
                fecha_creacion__date__gte=dr_desde,
                fecha_creacion__date__lte=dr_hasta,
            )
        elif dr_desde:
            reservas = reservas.filter(fecha_creacion__date__gte=dr_desde)
        elif dr_hasta:
            reservas = reservas.filter(fecha_creacion__date__lte=dr_hasta)

    contratos = ContratoAlquiler.objects.filter(sucursal=sucursal).select_related(
        'propiedad', 'inquilino', 'vendedor'
    )
    if tipo_filtro == 'invierno':
        contratos = contratos.filter(
            Q(duracion_meses=9) | Q(precio_segundo_cuatrimestre__gt=0)
        )
    elif tipo_filtro == '24meses':
        contratos = (
            contratos.exclude(duracion_meses=9)
            .exclude(precio_segundo_cuatrimestre__gt=0)
            .filter(duracion_meses__gte=9)
        )
    elif tipo_filtro in ('dia', 'estudiante'):
        contratos = contratos.none()

    if operacion:
        contratos = contratos.filter(id=operacion_num) if operacion_num is not None else contratos.none()

    contratos = contratos.order_by('-fecha_creacion', '-id')

    if q:
        tokens = _tokens_busqueda_caratulas(q)
        q_ctr = _q_busqueda_texto_caratulas(q, tokens)
        q_ctr |= _q_busqueda_persona_caratulas('inquilino', tokens)
        if q.isdigit():
            try:
                q_ctr |= Q(id=int(q))
            except (TypeError, ValueError):
                pass
        contratos = contratos.filter(q_ctr)
    if not omitir_filtro_fechas:
        if dr_desde and dr_hasta:
            contratos = contratos.filter(
                fecha_operacion__gte=dr_desde,
                fecha_operacion__lte=dr_hasta,
            )
        elif dr_desde:
            contratos = contratos.filter(fecha_operacion__gte=dr_desde)
        elif dr_hasta:
            contratos = contratos.filter(fecha_operacion__lte=dr_hasta)

    reserva_ids = list(reservas.values_list('id', flat=True))
    contrato_ids = list(contratos.values_list('id', flat=True))

    liq_por_reserva = {}
    if reserva_ids:
        for row in (
            LiquidacionPropietario.objects.filter(reserva_id__in=reserva_ids)
            .exclude(estado='cancelada')
            .order_by('-id')
            .values('reserva_id', 'id')
        ):
            if row['reserva_id'] not in liq_por_reserva:
                liq_por_reserva[row['reserva_id']] = row['id']

    filas = []

    for r in reservas:
        tipo = _tipo_reserva(r.propiedad)
        p = r.propiedad
        piso_dto = ''
        if p:
            pi = (p.piso or '').strip() or '—'
            dep = (p.departamento or '').strip() or '—'
            piso_dto = f'{pi} / {dep}'
        plinea, psub = _etiqueta_propiedad_lista(p)
        liquidacion_id = liq_por_reserva.get(r.id)
        tiene_liquidacion = liquidacion_id is not None
        if liquidacion_filtro == 'pendiente' and tiene_liquidacion:
            continue
        if liquidacion_filtro == 'liquidada' and not tiene_liquidacion:
            continue
        filas.append(
            {
                'kind': 'reserva',
                'pk': r.id,
                'tipo': tipo,
                'tipo_display': f'Reserva · {tipo}',
                'numero': r.id,
                'numero_display': f'OP {r.id}',
                'fecha': _fecha_operacion_reserva(r),
                'fecha_operacion': _fecha_operacion_reserva(r),
                'sort_instante': _instante_operacion_reserva(r),
                'caratula': _caratula_nombre_cliente(r.cliente),
                'propiedad_linea': plinea,
                'propiedad_sub': psub,
                'direccion': p.direccion if p else '—',
                'piso_dto': piso_dto,
                'ficha': p.id if p else '—',
                'estado': r.get_estado_display() if hasattr(r, 'get_estado_display') else r.estado,
                'carpeta': '—',
                'tiene_liquidacion': tiene_liquidacion,
                'liquidacion_id': liquidacion_id,
            }
        )

    for c in contratos:
        carpeta_hist = _carpeta_guardada_operacion(contrato=c)
        tipo_c = _tipo_label_contrato_caratula(c)
        p = c.propiedad
        piso_dto = ''
        if p:
            pi = (p.piso or '').strip() or '—'
            dep = (p.departamento or '').strip() or '—'
            piso_dto = f'{pi} / {dep}'
        clinea, csub = _etiqueta_propiedad_lista(p)
        liquidacion_id = _ultima_liquidacion_contrato_id(c)
        tiene_liquidacion = _contrato_al_dia_liquidacion_cobros(c)
        if liquidacion_filtro == 'pendiente' and tiene_liquidacion:
            continue
        if liquidacion_filtro == 'liquidada' and not tiene_liquidacion:
            continue
        filas.append(
            {
                'kind': 'contrato',
                'pk': c.id,
                'tipo': tipo_c,
                'tipo_display': f'Contrato · {tipo_c}',
                'numero': c.id,
                'numero_display': f'CT {c.id}',
                'fecha': c.fecha_operacion,
                'fecha_operacion': c.fecha_operacion,
                'sort_instante': _instante_operacion_contrato(c),
                'caratula': _caratula_nombre_cliente(c.inquilino),
                'propiedad_linea': clinea,
                'propiedad_sub': csub,
                'direccion': p.direccion if p else '—',
                'piso_dto': piso_dto,
                'ficha': p.id if p else '—',
                'estado': c.get_estado_display() if hasattr(c, 'get_estado_display') else c.estado,
                'carpeta': carpeta_hist or '—',
                'tiene_liquidacion': tiene_liquidacion,
                'liquidacion_id': liquidacion_id,
            }
        )

    # Cronológico: orden en que se fueron cargando (primera operación del día arriba).
    filas.sort(
        key=lambda x: (
            x.get('sort_instante') or timezone.localtime(timezone.now()),
            x.get('numero') or 0,
        )
    )

    total_filas = len(filas)

    paginator = Paginator(filas, 40)
    page = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages or 1)

    lista_filtros_qs = _query_string_lista_caratulas(
        q=q,
        operacion=operacion,
        fecha_desde=fecha_desde if not periodo_completo else '',
        fecha_hasta=fecha_hasta if not periodo_completo else '',
        tipo_filtro=tipo_filtro,
        liquidacion_filtro=liquidacion_filtro,
        periodo_completo=periodo_completo,
    )
    lista_ver_qs = _query_string_lista_caratulas(
        q=q,
        operacion=operacion,
        fecha_desde=fecha_desde if not periodo_completo else '',
        fecha_hasta=fecha_hasta if not periodo_completo else '',
        tipo_filtro=tipo_filtro,
        liquidacion_filtro=liquidacion_filtro,
        periodo_completo=periodo_completo,
        page=page_obj.number if page_obj.number > 1 else None,
    )

    return render(
        request,
        'inmobiliaria/caratulas/lista.html',
        {
            'filas': page_obj,
            'q': q,
            'operacion': operacion,
            'fecha_desde': fecha_desde if not periodo_completo else '',
            'fecha_hasta': fecha_hasta if not periodo_completo else '',
            'tipo_filtro': tipo_filtro,
            'liquidacion_filtro': liquidacion_filtro,
            'periodo_completo': periodo_completo,
            'busqueda_por_numero': busqueda_por_numero,
            'carpeta_default': _carpeta_default_actual(request),
            'total_filas': total_filas,
            'lista_filtros_qs': lista_filtros_qs,
            'lista_ver_qs': lista_ver_qs,
        },
    )


@login_required
def caratula_reserva(request, reserva_id):
    if not _puede_ver_caratulas(request.user):
        return HttpResponseForbidden()
    reserva = get_object_or_404(
        Reserva.objects.select_related(
            'cliente', 'propiedad', 'propiedad__propietario', 'vendedor', 'sucursal'
        )
        .prefetch_related(
            Prefetch(
                'recibos',
                queryset=Recibo.objects.select_related('movimiento_caja').order_by('-fecha_emision'),
            ),
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

    if request.method == 'POST' and request.POST.get('action') == 'save_caratula_reserva':
        if _guardar_caratula_reserva(request, reserva):
            return _redirect_caratula_con_filtros('inmobiliaria:caratula_reserva', reserva_id, request)
        reserva.refresh_from_db()

    movimientos = []
    if reserva.propiedad_id:
        movs_qs = (
            MovimientoCaja.objects.filter(
                propiedad_id=reserva.propiedad_id,
                sucursal_id=reserva.sucursal_id,
            )
            .select_related('recibo')
            .order_by('-fecha')
        )
        for mov in movs_qs[:200]:
            if _operacion_en_concepto(mov.concepto, reserva.id):
                movimientos.append(mov)

    recibos = list(reserva.recibos.all())
    comisiones = list(reserva.comisiones_vendedor.all())

    if not comisiones and movimientos and reserva.vendedor_id:
        from inmobiliaria.models.comision import asegurar_comisiones_movimiento_reserva

        for mov in movimientos:
            asegurar_comisiones_movimiento_reserva(reserva, mov)
        comisiones = list(
            ComisionVendedor.objects.filter(reserva=reserva)
            .exclude(estado='cancelada')
            .select_related('vendedor')
        )

    total_mov = sum(
        Decimal(str(m.monto_efectivo or 0))
        + Decimal(str(m.monto_cheque or 0))
        + Decimal(str(m.monto_tarjeta or 0))
        + Decimal(str(m.monto_deposito or 0))
        for m in movimientos
    )

    saldo_reserva = (reserva.precio_total or Decimal('0')) - (reserva.senia or Decimal('0'))
    tipo_op = _tipo_reserva(reserva.propiedad)
    comision_total = sum(Decimal(str(c.monto_comision or 0)) for c in comisiones)
    from inmobiliaria.decimal_utils import format_monto_argentino

    ctx = {
        'reserva': reserva,
        'propiedad': reserva.propiedad,
        'tipo_operacion': tipo_op,
        'movimientos': movimientos,
        'recibos': recibos,
        'comisiones': comisiones,
        'total_movimientos': total_mov,
        'saldo_reserva': saldo_reserva,
        'puede_editar_caratula': _puede_editar_caratula(request.user),
        'reserva_estado_choices': Reserva._meta.get_field('estado').choices,
        'edit_montos': {
            'precio_total': format_monto_argentino(reserva.precio_total),
            'senia': format_monto_argentino(reserva.senia),
            'deposito': format_monto_argentino(reserva.deposito_garantia),
            'comision_locatario': format_monto_argentino(comision_total),
        },
        'caratula_legacy': _build_legacy_reserva(
            reserva,
            recibos,
            comisiones,
            saldo_reserva,
            tipo_op,
            movimientos=movimientos,
        ),
        **_ctx_liquidacion_operacion(reserva=reserva),
        **_ctx_completar_pago_reserva(reserva),
        'volver_lista_url': _url_lista_caratulas_desde_request(request),
    }
    rl = ctx['resumen_liquidacion']
    ctx['edit_montos_liquidacion'] = {
        'monto_propietario': format_monto_argentino(rl.get('monto_propietario') or 0),
        'monto_inmobiliaria': format_monto_argentino(rl.get('monto_inmobiliaria') or 0),
        'monto_cochera': format_monto_argentino(rl.get('monto_cochera') or 0),
        'monto_fondo': format_monto_argentino(rl.get('monto_fondo') or 0),
    }
    ctx['puede_editar_liquidacion_resumen'] = bool(
        ctx['puede_editar_caratula']
        and rl.get('tiene_datos')
        and not rl.get('desde_liquidacion')
    )
    ctx['form_caratula_reserva_id'] = 'form-editar-caratula-reserva'
    return render(request, 'inmobiliaria/caratulas/detalle_reserva.html', ctx)


@login_required
def caratula_contrato(request, contrato_id):
    if not _puede_ver_caratulas(request.user):
        return HttpResponseForbidden()

    contrato = get_object_or_404(
        ContratoAlquiler.objects.select_related(
            'propiedad', 'propiedad__propietario', 'propiedad__fichado_por', 'inquilino', 'vendedor', 'sucursal'
        ).prefetch_related(
            Prefetch(
                'cuotas',
                queryset=CuotaMensual.objects.select_related('movimiento').order_by('fecha_vencimiento'),
            ),
            'garantes',
        ),
        pk=contrato_id,
    )
    if contrato.sucursal_id != getattr(request.user, 'sucursal_id', None) and not getattr(
        request.user, 'is_superuser', False
    ):
        return HttpResponseForbidden()

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'set_carpeta_contrato':
            _persistir_carpeta_operacion('contrato', contrato_id, request.POST.get('carpeta'))
            return _redirect_caratula_con_filtros('inmobiliaria:caratula_contrato', contrato_id, request)
        if action == 'save_comisiones_caratula':
            from django.contrib import messages
            from inmobiliaria.decimal_utils import parse_decimal_monto

            com_loc = parse_decimal_monto(request.POST.get('comision_locador', '0'))
            com_locat = parse_decimal_monto(request.POST.get('comision_locatario', '0'))
            if com_loc < 0:
                com_loc = Decimal('0')
            if com_locat < 0:
                com_locat = Decimal('0')
            liq = _liquidacion_contrato(contrato)
            if liq:
                liq.comision_locador = com_loc.quantize(Decimal('0.01'))
                liq.comision_locatario = com_locat.quantize(Decimal('0.01'))
                liq.save(update_fields=['comision_locador', 'comision_locatario'])
                overrides = dict(request.session.get(CARATULA_COMISIONES_OVERRIDES_KEY, {}))
                overrides.pop(str(contrato_id), None)
                request.session[CARATULA_COMISIONES_OVERRIDES_KEY] = overrides
                request.session.modified = True
                from inmobiliaria.models.comision import asegurar_comisiones_contrato

                movs_op = sorted(
                    [
                        m
                        for m in _movimientos_contrato_qs(contrato)[:50]
                        if m.tipo == TipoMovimientoCajaEnum.INGRESO
                        and m.concepto
                        and re.search(
                            rf'Contrato\s*#\s*{contrato.id}\b', m.concepto, re.IGNORECASE
                        )
                    ],
                    key=lambda x: (x.fecha, x.id),
                )
                asegurar_comisiones_contrato(
                    contrato,
                    honorarios_monto=com_locat,
                    movimiento_caja=movs_op[0] if movs_op else None,
                )
                messages.success(request, 'Comisiones guardadas en la liquidación.')
            else:
                _set_comisiones_override_caratula(request, contrato_id, com_loc, com_locat)
                messages.success(request, 'Comisiones guardadas para esta carátula.')
            return _redirect_caratula_con_filtros('inmobiliaria:caratula_contrato', contrato_id, request)

    movimientos = []
    if contrato.propiedad_id:
        from inmobiliaria.cuotas_imputacion import movimientos_ingreso_contrato

        movimientos = movimientos_ingreso_contrato(contrato)

    total_mov = sum(
        Decimal(str(m.monto_efectivo or 0))
        + Decimal(str(m.monto_cheque or 0))
        + Decimal(str(m.monto_tarjeta or 0))
        + Decimal(str(m.monto_deposito or 0))
        for m in movimientos
    )

    cuotas_list = list(contrato.cuotas.all()) if hasattr(contrato, 'cuotas') else []
    if cuotas_list:
        from inmobiliaria.cuotas_imputacion import mapa_movimientos_recibo_por_cuota_id

        recibos_por_cuota = mapa_movimientos_recibo_por_cuota_id(cuotas_list, movimientos)
        for c in cuotas_list:
            c.recibos_cobro = recibos_por_cuota.get(int(c.id), [])

    _enriquecer_cuotas_liquidacion(cuotas_list, contrato, contrato.sucursal, movimientos=movimientos)

    tipo_label = _tipo_label_contrato_caratula(contrato)
    carpeta_guardada = _carpeta_guardada_operacion(contrato=contrato)
    carpeta_actual = carpeta_guardada if carpeta_guardada is not None else _carpeta_default_actual(request)
    from inmobiliaria.views import _liquidacion_operacion_principal_contrato

    liquidacion_hon = _liquidacion_operacion_principal_contrato(contrato)
    override = _comisiones_override_caratula(request, contrato.id)
    honorarios_ctx = _ctx_honorarios_comisiones_caratula_contrato(
        contrato,
        movimientos,
        liquidacion=liquidacion_hon,
        override=override,
    )
    honorarios_ctx.update(
        _estado_liquidacion_operacion_principal_caratula(contrato, contrato.sucursal)
    )

    if honorarios_ctx.get('comision_locatario', 0) > Decimal('0.05'):
        from inmobiliaria.models.comision import asegurar_comisiones_contrato

        movs_op = sorted(movimientos, key=lambda x: (x.fecha, x.id)) if movimientos else []
        asegurar_comisiones_contrato(
            contrato,
            honorarios_monto=honorarios_ctx['comision_locatario'],
            movimiento_caja=movs_op[0] if movs_op else None,
        )
        honorarios_ctx = _ctx_honorarios_comisiones_caratula_contrato(
            contrato,
            movimientos,
            liquidacion=liquidacion_hon,
            override=override,
        )
        honorarios_ctx.update(
            _estado_liquidacion_operacion_principal_caratula(contrato, contrato.sucursal)
        )

    caratula_legacy = _build_legacy_contrato(
        contrato,
        cuotas_list,
        tipo_label,
        carpeta_override=carpeta_guardada,
        movimientos=movimientos,
        liquidacion=liquidacion_hon,
        override=override,
    )

    ctx = {
        'contrato': contrato,
        'propiedad': contrato.propiedad,
        'tipo_label': tipo_label,
        'movimientos': movimientos,
        'total_movimientos': total_mov,
        'cuotas': cuotas_list,
        'honorarios_ctx': honorarios_ctx,
        'comisiones_vendedor': honorarios_ctx.get('comisiones_vendedor') or [],
        'caratula_legacy': caratula_legacy,
        'carpeta_actual': carpeta_actual,
        'carpeta_default': _carpeta_default_actual(request),
        **_ctx_liquidacion_operacion(contrato=contrato),
        'volver_lista_url': _url_lista_caratulas_desde_request(request),
    }
    return render(request, 'inmobiliaria/caratulas/detalle_contrato.html', ctx)


@login_required
def imprimir_caratula_reserva(request, reserva_id):
    """Vista sólo impresión: formato papel tipo libro de alquileres (todos los vendedores)."""
    reserva = get_object_or_404(
        Reserva.objects.select_related(
            'cliente', 'propiedad', 'propiedad__propietario', 'vendedor', 'sucursal'
        ).prefetch_related(
            Prefetch('recibos', queryset=Recibo.objects.order_by('fecha_emision')),
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

    recibos = list(reserva.recibos.all())
    comisiones = list(reserva.comisiones_vendedor.all())
    saldo_reserva = (reserva.precio_total or Decimal('0')) - (reserva.senia or Decimal('0'))
    tipo_op = _tipo_reserva(reserva.propiedad)
    movs_legacy = []
    for mov in _movimientos_reserva_qs(reserva)[:250]:
        if _operacion_en_concepto(mov.concepto, reserva.id):
            movs_legacy.append(mov)
    cl = _build_legacy_reserva(
        reserva,
        recibos,
        comisiones,
        saldo_reserva,
        tipo_op,
        movimientos=movs_legacy,
    )
    filas_contab = _contabilizacion_para_reserva(reserva, recibos)
    suc = reserva.sucursal
    ciudad_ref = 'MAR DEL PLATA'
    if suc:
        ciudad_ref = (getattr(suc, 'localidad', None) or getattr(suc, 'nombre', None) or ciudad_ref).strip().upper()

    fdoc = reserva.fecha_inicio
    if reserva.fecha_creacion:
        try:
            fdoc = timezone.localdate(reserva.fecha_creacion)
        except Exception:
            fdoc = reserva.fecha_creacion.date() if hasattr(reserva.fecha_creacion, 'date') else reserva.fecha_inicio

    volver_url, volver_label = _volver_imprimir_caratula(request, reserva_id=reserva_id)

    ctx = {
        'es_reserva': True,
        'volver_url': volver_url,
        'volver_label': volver_label,
        'rubro_title': 'ALQUILERES',
        'numero_display': f"Nº OP {_formato_miles_ar(reserva.id)}",
        'llave': cl['codigo_llave'],
        'fecha_documento': fdoc,
        'tipo_operacion': tipo_op,
        'propiedad_desc': _propiedad_desc_corta(reserva.propiedad),
        'ciudad_ref': ciudad_ref,
        'propietario_nombre': _nombre_propietario_papel(
            getattr(reserva.propiedad, 'propietario', None) if reserva.propiedad else None
        ),
        'cliente_nombre': _nombre_cliente_papel(reserva.cliente),
        'cl': cl,
        'fecha_desde': reserva.fecha_inicio,
        'fecha_hasta': reserva.fecha_fin,
        'hora_desde': reserva.hora_ingreso,
        'hora_hasta': reserva.hora_egreso,
        'filas_contab': filas_contab,
        'direccion_ficha': _direccion_piso_depto_papel(reserva.propiedad),
        'deposito_fmt': cl['deposito'],
        'operacion_id': reserva.id,
        'productor_nombre': _nombre_productor_papel(reserva.vendedor),
    }
    return render(request, 'inmobiliaria/caratulas/imprimir_caratula_papel.html', ctx)


@login_required
def imprimir_caratula_contrato(request, contrato_id):
    contrato = get_object_or_404(
        ContratoAlquiler.objects.select_related(
            'propiedad', 'propiedad__propietario', 'inquilino', 'vendedor', 'sucursal'
        ).prefetch_related(
            Prefetch('cuotas', queryset=CuotaMensual.objects.order_by('fecha_vencimiento')),
            'garantes',
        ),
        pk=contrato_id,
    )
    if contrato.sucursal_id != getattr(request.user, 'sucursal_id', None) and not getattr(
        request.user, 'is_superuser', False
    ):
        return HttpResponseForbidden()

    cuotas = list(contrato.cuotas.all()) if hasattr(contrato, 'cuotas') else []
    tipo_label = _tipo_label_contrato_caratula(contrato)
    movs_legacy = []
    for mov in _movimientos_contrato_qs(contrato)[:300]:
        if mov.tipo != TipoMovimientoCajaEnum.INGRESO:
            continue
        if mov.concepto and re.search(rf'Contrato\s*#\s*{contrato.id}\b', mov.concepto, re.IGNORECASE):
            movs_legacy.append(mov)
    cl = _build_legacy_contrato(
        contrato,
        cuotas,
        tipo_label,
        carpeta_override=_carpeta_guardada_operacion(contrato=contrato),
        movimientos=movs_legacy,
    )
    filas_contab = _contabilizacion_para_contrato(contrato)
    suc = contrato.sucursal
    ciudad_ref = 'MAR DEL PLATA'
    if suc:
        ciudad_ref = (getattr(suc, 'localidad', None) or getattr(suc, 'nombre', None) or ciudad_ref).strip().upper()

    fdoc = contrato.fecha_operacion or contrato.fecha_inicio
    if fdoc is None and getattr(contrato, 'fecha_creacion', None):
        try:
            fdoc = timezone.localdate(contrato.fecha_creacion)
        except Exception:
            fdoc = contrato.fecha_creacion.date() if hasattr(contrato.fecha_creacion, 'date') else timezone.localdate()

    volver_url, volver_label = _volver_imprimir_caratula(request, contrato_id=contrato_id)

    ctx = {
        'es_reserva': False,
        'volver_url': volver_url,
        'volver_label': volver_label,
        'rubro_title': 'CONTRATO DE LOCACIÓN',
        'numero_display': f"Nº CT {_formato_miles_ar(contrato.id)}",
        'llave': cl['codigo_llave'],
        'fecha_documento': fdoc,
        'tipo_operacion': tipo_label,
        'propiedad_desc': _propiedad_desc_corta(contrato.propiedad),
        'ciudad_ref': ciudad_ref,
        'propietario_nombre': _nombre_propietario_papel(
            getattr(contrato.propiedad, 'propietario', None) if contrato.propiedad else None
        ),
        'cliente_nombre': _nombre_cliente_papel(contrato.inquilino),
        'cl': cl,
        'fecha_desde': contrato.fecha_inicio,
        'fecha_hasta': contrato.fecha_fin,
        'hora_desde': None,
        'hora_hasta': None,
        'filas_contab': filas_contab,
        'direccion_ficha': _direccion_piso_depto_papel(contrato.propiedad),
        'deposito_fmt': cl['deposito'],
        'operacion_id': contrato.id,
        'productor_nombre': _nombre_productor_papel(contrato.vendedor),
    }
    return render(request, 'inmobiliaria/caratulas/imprimir_caratula_papel.html', ctx)
