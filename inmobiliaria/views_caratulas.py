"""
Consulta de carátulas: listado y detalle de operaciones (reservas por día, invierno, 24 meses).
"""
import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
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


def _aware_day_start(d):
    """Inicio del día (aware) para filtrar DateTimeField sin usar __date (usa índice)."""
    naive = datetime.combine(d, datetime.min.time())
    if timezone.is_naive(naive):
        return timezone.make_aware(naive)
    return naive


def _aware_day_end_exclusive(d):
    """Inicio del día siguiente (aware), límite exclusivo del filtro."""
    return _aware_day_start(d + timedelta(days=1))


# Evita cargar miles de filas en memoria al listar carátulas sin filtro de texto.
LISTA_CARATULAS_MAX_FILAS = 2000

CARATULA_CARPETA_DEFAULT_KEY = 'caratulas_carpeta_default'
CARATULA_CARPETA_OVERRIDES_KEY = 'caratulas_carpeta_overrides'
CARATULA_COMISIONES_OVERRIDES_KEY = 'caratulas_comisiones_overrides'
CARATULA_MONTOS_CONTRATO_OVERRIDES_KEY = 'caratulas_montos_contrato_overrides'

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
    'q',
    'propiedad_id',
    'operacion',
    'fecha_desde',
    'fecha_hasta',
    'tipo',
    'liquidacion',
    'estado_caratula',
    'todo',
    'page',
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
    estado_caratula_filtro='',
    periodo_completo=False,
    page=None,
    propiedad_id='',
):
    params = {}
    q = (q or '').strip()
    operacion = (operacion or '').strip()
    tipo_filtro = (tipo_filtro or '').strip()
    liquidacion_filtro = (liquidacion_filtro or '').strip()
    estado_caratula_filtro = (estado_caratula_filtro or '').strip()
    fecha_desde = (fecha_desde or '').strip()
    fecha_hasta = (fecha_hasta or '').strip()
    propiedad_id = (propiedad_id or '').strip()
    if q:
        params['q'] = q
    if propiedad_id.isdigit():
        params['propiedad_id'] = propiedad_id
    if operacion:
        params['operacion'] = operacion
    if tipo_filtro:
        params['tipo'] = tipo_filtro
    if liquidacion_filtro:
        params['liquidacion'] = liquidacion_filtro
    if estado_caratula_filtro:
        params['estado_caratula'] = estado_caratula_filtro
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
    """Apellido y nombre del vendedor/productor/fichador para carátula."""
    if not vendedor:
        return '—'
    ap = (getattr(vendedor, 'apellido', None) or '').strip().upper()
    nom = (getattr(vendedor, 'nombre', None) or '').strip().upper()
    if ap and nom:
        return f'{ap}, {nom}'
    return ap or nom or '—'


def _nombres_productores_operacion(*, reserva=None, contrato=None) -> str:
    from inmobiliaria.models.comision import iter_productores_contrato, iter_productores_reserva

    if reserva:
        vends = iter_productores_reserva(reserva)
    elif contrato:
        vends = iter_productores_contrato(contrato)
    else:
        return '—'
    if not vends:
        return '—'
    return ' · '.join(_nombre_productor_papel(v) for v in vends)


def _fichador_nombre_caratula(prop, comisiones=None) -> str:
    """Nombre del fichador de la propiedad (todas las operaciones)."""
    from inmobiliaria.models.comision import ROL_COMISION_FICHAJE, vendedor_fichaje_desde_propiedad

    if comisiones:
        for c in comisiones:
            rol = (getattr(c, 'rol_comision', None) or '').strip()
            if rol in (ROL_COMISION_FICHAJE, 'fichaje'):
                vend = getattr(c, 'vendedor', None)
                if vend:
                    return _nombre_productor_papel(vend)
                nombre = (getattr(c, 'vendedor_nombre', None) or '').strip()
                if nombre:
                    return nombre.upper()
            # dicts de líneas de carátula
            if isinstance(c, dict) and c.get('rol') in (ROL_COMISION_FICHAJE, 'fichaje'):
                nombre = (c.get('vendedor_nombre') or '').strip()
                if nombre:
                    return nombre.upper()
                if c.get('vendedor_id'):
                    from inmobiliaria.models.persona import Vendedor

                    vend = Vendedor.objects.filter(pk=c['vendedor_id']).first()
                    if vend:
                        return _nombre_productor_papel(vend)

    vend = vendedor_fichaje_desde_propiedad(prop)
    if vend:
        return _nombre_productor_papel(vend)
    return '—'


def _ctx_productores_operacion(*, reserva=None, contrato=None, puede_editar=False):
    from decimal import Decimal

    from inmobiliaria.models.comision import (
        lista_productores_operacion,
        redistribuir_participaciones_iguales,
    )

    ops = lista_productores_operacion(reserva=reserva, contrato=contrato)
    if len(ops) > 1:
        total = sum(
            (Decimal(str(op.porcentaje_participacion or 0)) for op in ops),
            Decimal('0'),
        )
        # Si nunca se repartió (0/0) o quedó inconsistente, forzar partes iguales.
        if abs(total - Decimal('100')) > Decimal('0.05'):
            redistribuir_participaciones_iguales(reserva=reserva, contrato=contrato)
            ops = lista_productores_operacion(reserva=reserva, contrato=contrato)

    return {
        'productores_operacion': ops,
        'puede_editar_productores_caratula': bool(puede_editar),
    }


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
    linea1 = [(prop.direccion or '').strip().upper()]
    fid = getattr(prop, 'id', None)
    if fid:
        linea1.append(f'({fid})')
    pi = (prop.piso or '').strip()
    dep = (prop.departamento or '').strip()
    if pi or dep:
        linea1.append(f'PISO:{pi or "—"} DPTO.:{dep or "—"}')
    texto = ' '.join(linea1)
    amb = getattr(prop, 'ambientes', None)
    if amb is not None and str(amb).strip() != '':
        texto = f'{texto}\n{amb} AMB.'
    return texto


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


def _movimientos_devolucion_deposito_reserva(reserva, limit=30):
    """Egresos de devolución de depósito de esta operación (aunque falte propiedad)."""
    from inmobiliaria.caja_devolucion_deposito import (
        _egreso_es_devolucion_deposito_reserva,
        concepto_devolucion_deposito_catalogo,
    )

    rid = int(reserva.id)
    qs = (
        MovimientoCaja.objects.filter(
            sucursal_id=reserva.sucursal_id,
            tipo=TipoMovimientoCajaEnum.EGRESO,
            fecha_eliminacion__isnull=True,
        )
        .select_related('recibo')
        .order_by('fecha', 'id')
    )
    patrones = (
        f'Devolución depósito operación {rid}',
        f'Devolucion deposito operacion {rid}',
        f'"devolucion_deposito_operacion_id": {rid}',
        f'"devolucion_deposito_operacion_id":{rid}',
    )
    q = Q()
    for p in patrones:
        q |= Q(concepto__icontains=p) | Q(concepto_detalle__icontains=p)
    explicitos = list(qs.filter(q)[:limit])
    if explicitos:
        return explicitos
    if not reserva.propiedad_id:
        return []
    nombre_140 = concepto_devolucion_deposito_catalogo(reserva.sucursal).get('nombre') or ''
    out = []
    for mov in qs.filter(propiedad_id=reserva.propiedad_id).order_by('-fecha', '-id')[:100]:
        if _egreso_es_devolucion_deposito_reserva(mov, reserva, nombre_140):
            out.append(mov)
            if len(out) >= limit:
                break
    return list(reversed(out))


def _movimientos_operacion_reserva(reserva, limit=200):
    """Ingresos/egresos vinculados a la operación, incluida la devolución de depósito."""
    from inmobiliaria.caja_devolucion_deposito import _movimiento_vinculado_reserva

    rid = int(reserva.id)
    vistos = set()
    movimientos = []

    def _agregar(mov):
        mid = int(mov.id)
        if mid in vistos:
            return
        vistos.add(mid)
        movimientos.append(mov)

    # Filtrar en SQL por referencia a la operación (evita cortar por [:limit] de toda la propiedad).
    if reserva.propiedad_id:
        qs = _movimientos_reserva_qs(reserva)
        q_ref = (
            Q(concepto__icontains=f'Operación {rid}')
            | Q(concepto__icontains=f'Operacion {rid}')
            | Q(concepto__icontains=f'Operación #{rid}')
            | Q(concepto__icontains=f'Operacion #{rid}')
            | Q(concepto__icontains=f'Reserva {rid}')
            | Q(concepto__icontains=f'Reserva #{rid}')
            | Q(concepto__icontains=f'Devolución depósito operación {rid}')
            | Q(concepto__icontains=f'Devolucion deposito operacion {rid}')
            | Q(concepto_detalle__icontains=f'"devolucion_deposito_operacion_id": {rid}')
            | Q(concepto_detalle__icontains=f'"devolucion_deposito_operacion_id":{rid}')
            | Q(concepto_detalle__icontains=f'"reserva_id": {rid}')
            | Q(concepto_detalle__icontains=f'"reserva_id":{rid}')
            | Q(concepto_detalle__icontains=f'"operacion_id": {rid}')
            | Q(concepto_detalle__icontains=f'"operacion_id":{rid}')
        )
        for mov in qs.filter(q_ref).order_by('fecha', 'id')[:limit]:
            if (
                _operacion_en_concepto(mov.concepto, rid)
                or _movimiento_vinculado_reserva(mov, rid)
            ):
                _agregar(mov)

    for mov in _movimientos_devolucion_deposito_reserva(reserva):
        _agregar(mov)

    movimientos.sort(key=lambda m: (m.fecha or timezone.now(), m.id or 0))
    return movimientos[:limit]


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


def _puede_imprimir_caratula(user):
    """
    Tras cobrar (recibo → carátula), cualquier vendedor operativo puede imprimir.
    Consultar/editar el módulo de carátulas sigue en nivel 4+ (_puede_ver_caratulas).
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    try:
        nivel = int(getattr(user, 'nivel', 0) or 0)
    except (TypeError, ValueError):
        nivel = 0
    return nivel >= 1


def _es_super_admin(user):
    """Super administrador (nivel 5) o superusuario Django."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return getattr(user, 'nivel', None) == 5


def _puede_editar_caratula(user):
    """Edición de montos/estado en carátula (administración)."""
    return _puede_ver_caratulas(user)


def _ctx_estado_operacion_caratula(reserva=None, contrato=None, user=None):
    """Estado administrativo pendiente/confirmada de la carátula (no comisiones)."""
    obj = reserva or contrato
    if reserva and (getattr(reserva, 'eliminada', False) or getattr(reserva, 'estado', None) == 'cancelada'):
        quien = getattr(reserva, 'usuario_eliminacion', None)
        if quien is not None:
            ap = (getattr(quien, 'apellido', None) or '').strip()
            no = (getattr(quien, 'nombre', None) or '').strip()
            quien_txt = ', '.join(p for p in (ap, no) if p) or str(quien)
        else:
            quien_txt = ''
        return {
            'estado_operacion_caratula': 'eliminada',
            'operacion_caratula_confirmada': False,
            'operacion_rescindida': False,
            'operacion_eliminada': True,
            'operacion_caratula_label': 'Eliminada',
            'operacion_caratula_badge_class': 'bg-secondary',
            'puede_confirmar_operacion_caratula': False,
            'puede_desconfirmar_operacion_caratula': False,
            'puede_anular_operacion_caratula': False,
            'operacion_eliminacion_fecha': getattr(reserva, 'fecha_eliminacion', None),
            'operacion_eliminacion_usuario': quien_txt,
        }
    if getattr(obj, 'estado', None) == 'rescindido':
        return {
            'estado_operacion_caratula': 'rescindida',
            'operacion_caratula_confirmada': False,
            'operacion_rescindida': True,
            'operacion_eliminada': False,
            'operacion_caratula_label': 'Rescindido',
            'operacion_caratula_badge_class': 'bg-danger',
            'puede_confirmar_operacion_caratula': False,
            'puede_desconfirmar_operacion_caratula': False,
            'puede_anular_operacion_caratula': False,
            'operacion_eliminacion_fecha': None,
            'operacion_eliminacion_usuario': '',
        }
    estado = getattr(obj, 'estado_confirmacion_caratula', None) or 'pendiente'
    confirmada = estado == 'confirmada'
    puede_anular = bool(
        reserva is not None
        and user is not None
        and _puede_anular_operacion_reserva_caratula(reserva, user)
    )
    return {
        'estado_operacion_caratula': estado,
        'operacion_caratula_confirmada': confirmada,
        'operacion_rescindida': False,
        'operacion_eliminada': False,
        'operacion_caratula_label': 'Confirmada' if confirmada else 'Pendiente',
        'operacion_caratula_badge_class': 'bg-success' if confirmada else 'bg-warning text-dark',
        'puede_confirmar_operacion_caratula': bool(
            not confirmada and user is not None and _puede_editar_caratula(user)
        ),
        'puede_desconfirmar_operacion_caratula': bool(
            confirmada and user is not None and _puede_editar_caratula(user)
        ),
        'puede_anular_operacion_caratula': puede_anular,
        'operacion_eliminacion_fecha': None,
        'operacion_eliminacion_usuario': '',
    }


def _puede_anular_operacion_reserva_caratula(reserva, user):
    """Eliminar/anular operación (reserva) desde carátula (administración)."""
    if not reserva or not _puede_editar_caratula(user):
        return False
    if getattr(reserva, 'eliminada', False) or getattr(reserva, 'estado', None) == 'cancelada':
        return False
    return True


def _liquidaciones_vinculadas_reserva(reserva):
    """Liquidaciones activas ligadas a la reserva (FK directo o en operaciones_incluidas)."""
    rid = int(reserva.pk)
    sucursal = getattr(reserva, 'sucursal', None)
    candidatas = list(
        LiquidacionPropietario.objects.filter(reserva_id=rid).exclude(estado='cancelada')
    )
    vistos = {liq.pk for liq in candidatas}
    qs_extra = LiquidacionPropietario.objects.exclude(estado='cancelada').exclude(pk__in=vistos)
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


def _anular_liquidaciones_reserva_anulacion(reserva, eliminado_por):
    """
    Ya no se tocan liquidaciones ni egresos de caja al anular una operación.
    La caja se ajusta manualmente con contrasiento si corresponde.
    Se conserva la firma por compatibilidad; siempre retorna lista vacía.
    """
    return []


def _procesar_anular_operacion_reserva_caratula(request, reserva):
    from django.contrib import messages

    if not _puede_anular_operacion_reserva_caratula(reserva, request.user):
        messages.error(request, 'No se puede eliminar esta operación.')
        return False
    motivo = (request.POST.get('motivo_anulacion') or '').strip()
    if not motivo:
        messages.error(request, 'Indicá el motivo de la eliminación.')
        return False
    try:
        with transaction.atomic():
            # No se modifica la caja ni se cancelan liquidaciones automáticamente.
            reserva.cancelar_reserva()
            reserva.refresh_from_db()
            reserva.eliminada = True
            reserva.estado_confirmacion_caratula = 'pendiente'
            reserva.fecha_eliminacion = timezone.now()
            reserva.usuario_eliminacion = request.user
            reserva.save(
                update_fields=[
                    'eliminada',
                    'estado_confirmacion_caratula',
                    'fecha_eliminacion',
                    'usuario_eliminacion',
                ]
            )
        from inmobiliaria.historial_inquilino import registrar_evento_historial_inquilino

        registrar_evento_historial_inquilino(
            tipo='operacion_anulada',
            reserva=reserva,
            usuario=request.user,
            detalle=f'Anulada desde carátula. Motivo: {motivo}',
            precio_anterior=reserva.precio_total,
            senia_anterior=reserva.senia,
        )
        logger.info(
            'Reserva %s anulada desde carátula por usuario %s. Motivo: %s. '
            'Caja y liquidaciones intactas (contrasiento manual si corresponde).',
            reserva.pk,
            getattr(request.user, 'pk', None),
            motivo,
        )
        messages.success(
            request,
            'Operación eliminada. Las fechas vuelven a estar disponibles. '
            'La caja no se modificó (si hace falta, hacé un contrasiento). '
            'Las comisiones ya acreditadas siguen en el mes original; '
            'el descuento queda registrado el día de la anulación.',
        )
        return True
    except Exception as exc:
        logger.exception('Error al anular operación %s desde carátula', reserva.pk)
        messages.error(request, f'Error al anular la operación: {exc}')
        return False


def _procesar_confirmar_operacion_caratula(request, reserva=None, contrato=None):
    from django.contrib import messages

    if not _puede_editar_caratula(request.user):
        messages.error(request, 'No tenés permiso para confirmar la operación.')
        return False
    obj = reserva or contrato
    if not obj:
        return False
    if getattr(obj, 'estado_confirmacion_caratula', 'pendiente') == 'confirmada':
        messages.info(request, 'La operación ya estaba confirmada.')
        return True
    obj.estado_confirmacion_caratula = 'confirmada'
    obj.save(update_fields=['estado_confirmacion_caratula'])
    from inmobiliaria.models.comision import acreditar_comisiones_operacion_por_caratula

    acreditar_comisiones_operacion_por_caratula(reserva=reserva, contrato=contrato)
    messages.success(request, 'Carátula marcada como confirmada.')
    return True


def _procesar_desconfirmar_operacion_caratula(request, reserva=None, contrato=None):
    from django.contrib import messages

    if not _puede_editar_caratula(request.user):
        messages.error(request, 'No tenés permiso para desconfirmar la carátula.')
        return False
    obj = reserva or contrato
    if not obj:
        return False
    if (getattr(obj, 'estado_confirmacion_caratula', None) or 'pendiente') != 'confirmada':
        messages.info(request, 'La carátula ya estaba pendiente.')
        return True
    obj.estado_confirmacion_caratula = 'pendiente'
    obj.save(update_fields=['estado_confirmacion_caratula'])
    messages.success(request, 'Carátula desconfirmada (vuelve a pendiente).')
    return True


def _procesar_productores_caratula(request, reserva=None, contrato=None):
    from django.contrib import messages
    from inmobiliaria.models.comision import (
        actualizar_participaciones_operacion,
        agregar_productor_contrato,
        agregar_productor_reserva,
        quitar_productor_contrato,
        quitar_productor_reserva,
        resincronizar_comisiones_productor_contrato,
        resincronizar_comisiones_productor_reserva,
    )

    if not _puede_editar_caratula(request.user):
        messages.error(request, 'No tenés permiso para editar los productores.')
        return False

    action = (request.POST.get('action') or '').strip()
    raw_id = (request.POST.get('productor_id') or '').strip()

    if action == 'guardar_participaciones_caratula':
        participaciones = {}
        for key, val in request.POST.items():
            if not key.startswith('participacion_'):
                continue
            vid = key[len('participacion_') :].strip()
            if not vid:
                continue
            participaciones[vid] = val
        if not participaciones:
            messages.error(request, 'No se recibieron porcentajes de participación.')
            return False
        ok, err = actualizar_participaciones_operacion(
            participaciones, reserva=reserva, contrato=contrato
        )
        if not ok:
            messages.error(request, err or 'No se pudieron guardar las participaciones.')
            return False
        if reserva:
            resincronizar_comisiones_productor_reserva(
                reserva, _movimientos_operacion_reserva(reserva)
            )
        elif contrato:
            movimientos = []
            if contrato.propiedad_id:
                from inmobiliaria.cuotas_imputacion import movimientos_ingreso_contrato

                movimientos = movimientos_ingreso_contrato(contrato)
            from inmobiliaria.views import _liquidacion_operacion_principal_contrato

            liquidacion_hon = _liquidacion_operacion_principal_contrato(contrato)
            override = _comisiones_override_caratula(request, contrato.id)
            honorarios_ctx = _ctx_honorarios_comisiones_caratula_contrato(
                contrato,
                movimientos,
                liquidacion=liquidacion_hon,
                override=override,
            )
            movs_op = sorted(movimientos, key=lambda x: (x.fecha, x.id)) if movimientos else []
            resincronizar_comisiones_productor_contrato(
                contrato,
                honorarios_monto=honorarios_ctx.get('base_comisiones'),
                movimiento_caja=movs_op[0] if movs_op else None,
            )
        messages.success(
            request,
            'Participaciones actualizadas. Se recalcularon las comisiones de los productores.',
        )
        return True

    if action == 'agregar_productor_caratula':
        if not raw_id:
            messages.error(request, 'Ingresá el ID del productor a agregar.')
            return False
        if reserva:
            ok, err = agregar_productor_reserva(
                reserva,
                raw_id,
                movimientos_caja=_movimientos_operacion_reserva(reserva),
            )
        elif contrato:
            movimientos = []
            if contrato.propiedad_id:
                from inmobiliaria.cuotas_imputacion import movimientos_ingreso_contrato

                movimientos = movimientos_ingreso_contrato(contrato)
            from inmobiliaria.views import _liquidacion_operacion_principal_contrato

            liquidacion_hon = _liquidacion_operacion_principal_contrato(contrato)
            override = _comisiones_override_caratula(request, contrato.id)
            honorarios_ctx = _ctx_honorarios_comisiones_caratula_contrato(
                contrato,
                movimientos,
                liquidacion=liquidacion_hon,
                override=override,
            )
            movs_op = sorted(movimientos, key=lambda x: (x.fecha, x.id)) if movimientos else []
            ok, err = agregar_productor_contrato(
                contrato,
                raw_id,
                honorarios_monto=honorarios_ctx.get('base_comisiones'),
                movimiento_caja=movs_op[0] if movs_op else None,
            )
        else:
            return False
        if not ok:
            messages.error(request, err or 'No se pudo agregar el productor.')
            return False
        messages.success(request, 'Productor agregado. Se calcularon sus comisiones.')
        return True

    if action == 'quitar_productor_caratula':
        quitar_id = (request.POST.get('quitar_productor_id') or raw_id or '').strip()
        if not quitar_id:
            messages.error(request, 'Indicá qué productor quitar.')
            return False
        if reserva:
            ok, err = quitar_productor_reserva(
                reserva,
                quitar_id,
                movimientos_caja=_movimientos_operacion_reserva(reserva),
            )
        elif contrato:
            ok, err = quitar_productor_contrato(contrato, quitar_id)
        else:
            return False
        if not ok:
            messages.error(request, err or 'No se pudo quitar el productor.')
            return False
        messages.success(request, 'Productor quitado de la operación.')
        return True

    return False


def _comision_original_id_desde_reversion(comision):
    from inmobiliaria.models.comision import ROL_COMISION_REVERSION

    if comision._rol_comision_normalizado() != ROL_COMISION_REVERSION:
        return None
    obs = (comision.observaciones or '').strip()
    prefix = 'reversion_comision_id='
    if not obs.startswith(prefix):
        return None
    try:
        return int(obs[len(prefix) :])
    except (TypeError, ValueError):
        return None


def _enriquecer_comisiones_fechas_caratula(comisiones, comisiones_por_id=None):
    from inmobiliaria.models.comision import ROL_COMISION_REVERSION

    por_id = dict(comisiones_por_id or {})
    for c in comisiones:
        por_id.setdefault(c.id, c)

    faltantes = []
    for c in comisiones:
        if c._rol_comision_normalizado() != ROL_COMISION_REVERSION:
            continue
        orig_id = _comision_original_id_desde_reversion(c)
        if orig_id and orig_id not in por_id:
            faltantes.append(orig_id)
    if faltantes:
        for orig in ComisionVendedor.objects.filter(pk__in=faltantes).select_related('vendedor'):
            por_id[orig.id] = orig

    for c in comisiones:
        if c._rol_comision_normalizado() == ROL_COMISION_REVERSION:
            orig_id = _comision_original_id_desde_reversion(c)
            orig = por_id.get(orig_id) if orig_id else None
            c.fecha_acreditacion_caratula = orig.fecha_operacion if orig else None
            c.fecha_devolucion_caratula = c.fecha_operacion
            c.id_fecha_acreditacion = None
            c.id_fecha_devolucion = c.id
        else:
            c.fecha_acreditacion_caratula = c.fecha_operacion
            c.fecha_devolucion_caratula = None
            c.id_fecha_acreditacion = c.id
            c.id_fecha_devolucion = None
    return comisiones


def _comisiones_visibles_caratula_reserva(reserva):
    from inmobiliaria.models.comision import ROL_COMISION_REVERSION

    todas = list(
        ComisionVendedor.objects.filter(reserva=reserva)
        .select_related('vendedor')
        .order_by('id')
    )
    visibles = []
    originales_con_reversion = set()
    for c in todas:
        if c._rol_comision_normalizado() == ROL_COMISION_REVERSION:
            orig_id = _comision_original_id_desde_reversion(c)
            if orig_id:
                originales_con_reversion.add(orig_id)
    for c in todas:
        rol = c._rol_comision_normalizado()
        if rol == ROL_COMISION_REVERSION:
            visibles.append(c)
        elif c.estado == 'cancelada' and c.id in originales_con_reversion:
            visibles.append(c)
        elif c.estado != 'cancelada':
            visibles.append(c)

    return _enriquecer_comisiones_fechas_caratula(visibles, {c.id: c for c in todas})


def _actualizar_fecha_operacion_comision_caratula(comision, fecha):
    from datetime import time

    dt = datetime.combine(fecha, time.min)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    if comision.fecha_operacion != dt:
        comision.fecha_operacion = dt
        comision.save(update_fields=['fecha_operacion'])
        return True
    return False


def _procesar_guardar_fechas_comision_caratula(request, reserva=None, contrato=None):
    from datetime import datetime

    from django.contrib import messages
    from inmobiliaria.models.comision import (
        ROL_COMISION_FICHAJE,
        ROL_COMISION_REVERSION,
        asegurar_comisiones_contrato,
    )

    if not _puede_editar_caratula(request.user):
        messages.error(request, 'No tenés permiso para editar las fechas de acreditación.')
        return False

    if contrato:
        movimientos = []
        if contrato.propiedad_id:
            from inmobiliaria.cuotas_imputacion import movimientos_ingreso_contrato

            movimientos = movimientos_ingreso_contrato(contrato)
        from inmobiliaria.views import _liquidacion_operacion_principal_contrato

        liquidacion_hon = _liquidacion_operacion_principal_contrato(contrato)
        override = _comisiones_override_caratula(request, contrato.id)
        honorarios_ctx = _ctx_honorarios_comisiones_caratula_contrato(
            contrato,
            movimientos,
            liquidacion=liquidacion_hon,
            override=override,
        )
        honorarios = honorarios_ctx.get('base_comisiones') or Decimal('0')
        if honorarios > Decimal('0.05'):
            movs_op = sorted(movimientos, key=lambda x: (x.fecha, x.id)) if movimientos else []
            asegurar_comisiones_contrato(
                contrato,
                honorarios_monto=honorarios,
                movimiento_caja=movs_op[0] if movs_op else None,
            )

    actualizadas = 0
    for key, raw in request.POST.items():
        if not key.startswith('fecha_comision_'):
            continue
        try:
            comision_id = int(key.replace('fecha_comision_', ''))
        except (TypeError, ValueError):
            continue
        texto = (raw or '').strip()
        if not texto:
            continue
        try:
            fecha = datetime.strptime(texto, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, f'Fecha inválida para la comisión #{comision_id}.')
            return False

        qs = ComisionVendedor.objects.filter(pk=comision_id)
        if reserva:
            qs = qs.filter(reserva=reserva)
        elif contrato:
            qs = qs.filter(contrato=contrato)
        else:
            continue

        comision = qs.exclude(rol_comision=ROL_COMISION_FICHAJE).first()
        if not comision and contrato:
            comision = (
                ComisionVendedor.objects.filter(contrato=contrato)
                .exclude(rol_comision=ROL_COMISION_FICHAJE)
                .order_by('id')
                .first()
            )
        if not comision:
            continue

        if _actualizar_fecha_operacion_comision_caratula(comision, fecha):
            actualizadas += 1

    for key, raw in request.POST.items():
        if not key.startswith('fecha_devolucion_'):
            continue
        try:
            comision_id = int(key.replace('fecha_devolucion_', ''))
        except (TypeError, ValueError):
            continue
        texto = (raw or '').strip()
        if not texto:
            continue
        try:
            fecha = datetime.strptime(texto, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, f'Fecha inválida para la devolución #{comision_id}.')
            return False

        qs = ComisionVendedor.objects.filter(
            pk=comision_id,
            rol_comision=ROL_COMISION_REVERSION,
        )
        if reserva:
            qs = qs.filter(reserva=reserva)
        elif contrato:
            qs = qs.filter(contrato=contrato)
        else:
            continue

        comision = qs.first()
        if not comision:
            continue

        if _actualizar_fecha_operacion_comision_caratula(comision, fecha):
            actualizadas += 1

    if actualizadas == 0 and contrato:
        raw_prod = (request.POST.get('fecha_comision_productor') or '').strip()
        if raw_prod:
            try:
                fecha = datetime.strptime(raw_prod, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, 'Fecha inválida para la comisión del productor.')
                return False
            comision = (
                ComisionVendedor.objects.filter(contrato=contrato)
                .exclude(rol_comision=ROL_COMISION_FICHAJE)
                .order_by('id')
                .first()
            )
            if comision and _actualizar_fecha_operacion_comision_caratula(comision, fecha):
                actualizadas += 1

    if actualizadas:
        messages.success(
            request,
            f'Fechas actualizadas ({actualizadas} comisión{"es" if actualizadas != 1 else ""}).',
        )
    else:
        messages.info(request, 'No hubo cambios en las fechas.')
    return True


def _enriquecer_lineas_comision_fecha_db(lineas, db_map, fecha_default=None):
    """Agrega id y fecha de acreditación desde ComisionVendedor a líneas de preview de carátula."""
    from inmobiliaria.models.comision import ROL_COMISION_FICHAJE, ROLES_COMISION_PRODUCTOR

    for ln in lineas or []:
        rol = ln.get('rol')
        if rol == ROL_COMISION_FICHAJE or rol == 'fichaje':
            continue
        vid = ln.get('vendedor_id')
        db = db_map.get((rol, vid)) if vid else None
        if not db and vid is not None:
            for rol_prod in ROLES_COMISION_PRODUCTOR:
                db = db_map.get((rol_prod, vid))
                if db:
                    break
        if not db:
            for rol_prod in ROLES_COMISION_PRODUCTOR:
                db = db_map.get((rol_prod, vid))
                if db:
                    break
        if not db and vid is not None:
            for (r, v), c in db_map.items():
                if v == vid and r in ROLES_COMISION_PRODUCTOR:
                    db = c
                    break
        if db:
            ln['comision_id'] = db.id
            if db.fecha_operacion:
                local = timezone.localtime(db.fecha_operacion)
                ln['fecha_acreditacion_fmt'] = local.strftime('%d/%m/%Y')
                ln['fecha_acreditacion_input'] = local.strftime('%Y-%m-%d')
            elif fecha_default:
                if hasattr(fecha_default, 'date'):
                    fd = fecha_default.date()
                else:
                    fd = fecha_default
                ln['fecha_acreditacion_fmt'] = fd.strftime('%d/%m/%Y')
                ln['fecha_acreditacion_input'] = fd.strftime('%Y-%m-%d')
        elif fecha_default:
            if hasattr(fecha_default, 'date'):
                fd = fecha_default.date()
            else:
                fd = fecha_default
            ln['fecha_acreditacion_fmt'] = fd.strftime('%d/%m/%Y')
            ln['fecha_acreditacion_input'] = fd.strftime('%Y-%m-%d')
        else:
            ln['fecha_acreditacion_fmt'] = '—'
            ln['fecha_acreditacion_input'] = ''


def _base_monto_comisiones_caratula(comision_locador, comision_locatario):
    """Base para % de fichaje y productor en contratos 24 meses / invierno."""
    total = Decimal(str(comision_locador or 0)) + Decimal(str(comision_locatario or 0))
    return total.quantize(Decimal('0.01'))


def _normalizar_lineas_fichaje_caratula(lineas, contrato):
    """La comisión fichaje es siempre del vendedor que fichó la propiedad."""
    from inmobiliaria.models.comision import ROL_COMISION_FICHAJE

    vend = _vendedor_fichaje_contrato_caratula(contrato)
    if not vend:
        return
    nombre = _nombre_productor_papel(vend)
    for ln in lineas or []:
        if ln.get('rol') in (ROL_COMISION_FICHAJE, 'fichaje'):
            ln['vendedor_nombre'] = nombre
            ln['vendedor_id'] = vend.id


def _mapa_comisiones_db_caratula(*, reserva=None, contrato=None):
    qs = ComisionVendedor.objects.exclude(estado='cancelada')
    if reserva:
        qs = qs.filter(reserva=reserva)
    elif contrato:
        qs = qs.filter(contrato=contrato)
    else:
        return {}
    return {(c.rol_comision, c.vendedor_id): c for c in qs.order_by('id')}


def _guardar_caratula_reserva(request, reserva):
    """Persiste montos, fechas y estado de una reserva desde la carátula."""
    from django.contrib import messages
    from inmobiliaria.decimal_utils import parse_decimal_monto

    if not _puede_editar_caratula(request.user):
        messages.error(request, 'No tenés permiso para editar esta carátula.')
        return False
    if getattr(reserva, 'eliminada', False) or getattr(reserva, 'estado', None) == 'cancelada':
        messages.error(request, 'No se puede editar una operación eliminada.')
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

    precio_anterior = reserva.precio_total
    senia_anterior = reserva.senia
    estado_anterior = reserva.estado
    fecha_inicio_anterior = reserva.fecha_inicio
    fecha_fin_anterior = reserva.fecha_fin

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
            from inmobiliaria.liquidacion_operacion import liquidaciones_activas_reserva

            tiene_liqs = bool(liquidaciones_activas_reserva(reserva))
            if tiene_liqs and not _es_super_admin(request.user):
                messages.error(
                    request,
                    'Solo el super administrador puede corregir los montos del resumen '
                    'cuando la operación ya tiene liquidación.',
                )
                return False
            prop_liq = _parse_liq_monto_opcional('liq_monto_propietario')
            inm_liq = _parse_liq_monto_opcional('liq_monto_inmobiliaria')
            coch_liq = _parse_liq_monto_opcional('liq_monto_cochera') or Decimal('0')
            fondo_liq = _parse_liq_monto_opcional('liq_monto_fondo') or Decimal('0')
            coch_inq_liq = _parse_liq_monto_opcional('liq_monto_cochera_inquilino') or Decimal('0')
            suma_liq = (
                (prop_liq or Decimal('0'))
                + (inm_liq or Decimal('0'))
                + coch_liq
                + fondo_liq
            ).quantize(Decimal('0.01'))
            total_op = precio_total.quantize(Decimal('0.01'))
            if abs(suma_liq - total_op) > Decimal('0.05'):
                raise ValueError(
                    f'La suma de propietario + inmobiliaria + cochera + fondo '
                    f'(${suma_liq}) debe ser igual al total de la operación (${total_op}).'
                )
            reserva.liq_monto_propietario = prop_liq
            reserva.liq_monto_inmobiliaria = inm_liq
            reserva.liq_monto_cochera = coch_liq
            reserva.liq_monto_fondo = fondo_liq
            reserva.liq_monto_cochera_inquilino = coch_inq_liq
    except ValueError as exc:
        messages.error(request, str(exc))
        return False

    reserva.save()

    from inmobiliaria.historial_inquilino import registrar_cambios_reserva_historial_inquilino

    registrar_cambios_reserva_historial_inquilino(
        reserva=reserva,
        usuario=request.user,
        precio_anterior=precio_anterior,
        senia_anterior=senia_anterior,
        fecha_inicio_anterior=fecha_inicio_anterior,
        fecha_fin_anterior=fecha_fin_anterior,
        estado_anterior=estado_anterior,
        origen='carátula',
    )

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


def _guardar_caratula_contrato(request, contrato):
    """Persiste fechas, montos y estado del contrato desde la carátula."""
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

    try:
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

    estado = (request.POST.get('estado') or contrato.estado).strip()
    estados_validos = {c[0] for c in ContratoAlquiler._meta.get_field('estado').choices}
    if estado not in estados_validos:
        messages.error(request, 'Estado de operación inválido.')
        return False

    meses = int(contrato.duracion_meses or 0)
    if meses <= 0:
        messages.error(request, 'El contrato no tiene duración en meses válida.')
        return False

    fecha_inicio_anterior = contrato.fecha_inicio
    contrato.fecha_inicio = fecha_inicio
    contrato.fecha_fin = fecha_fin
    contrato.deposito_garantia = deposito.quantize(Decimal('0.01'))
    contrato.precio_mensual = (precio_total / Decimal(meses)).quantize(Decimal('0.01'))
    contrato.estado = estado
    contrato.save(update_fields=[
        'fecha_inicio', 'fecha_fin', 'deposito_garantia', 'precio_mensual', 'estado',
    ])

    if fecha_inicio != fecha_inicio_anterior:
        from inmobiliaria.views import _alinear_vencimientos_cuotas_contrato

        _alinear_vencimientos_cuotas_contrato(contrato)

    _set_montos_override_contrato_caratula(request, contrato.id, senia=senia)

    liq = _liquidacion_contrato(contrato)
    com_loc = parse_decimal_monto(request.POST.get('comision_locador', '0'))
    if com_loc <= 0 and liq and liq.comision_locador:
        com_loc = liq.comision_locador
    if com_loc < 0:
        com_loc = Decimal('0')
    # Solo tocar liquidación pendiente: no reescribir una ya cerrada/pagada.
    if liq and (liq.estado or '') == 'pendiente':
        liq.comision_locador = com_loc.quantize(Decimal('0.01'))
        liq.comision_locatario = comision_locatario.quantize(Decimal('0.01'))
        liq.save(update_fields=['comision_locador', 'comision_locatario'])
        _clear_comisiones_caratula_contrato(contrato)
        overrides = dict(request.session.get(CARATULA_COMISIONES_OVERRIDES_KEY, {}))
        overrides.pop(str(contrato.id), None)
        request.session[CARATULA_COMISIONES_OVERRIDES_KEY] = overrides
        request.session.modified = True
        from inmobiliaria.models.comision import asegurar_comisiones_contrato

        movimientos = []
        if contrato.propiedad_id:
            from inmobiliaria.cuotas_imputacion import movimientos_ingreso_contrato

            movimientos = movimientos_ingreso_contrato(contrato)
        movs_op = sorted(movimientos, key=lambda x: (x.fecha, x.id)) if movimientos else []
        base_comisiones = _base_monto_comisiones_caratula(com_loc, comision_locatario)
        asegurar_comisiones_contrato(
            contrato,
            honorarios_monto=base_comisiones,
            movimiento_caja=movs_op[0] if movs_op else None,
        )
    elif liq and (liq.estado or '') != 'pendiente':
        # Hay liquidación cerrada: no pisar montos ni regenerar comisiones pagadas.
        _set_comisiones_override_caratula(request, contrato.id, com_loc, comision_locatario)
        messages.info(
            request,
            'La liquidación ya no está pendiente: se guardaron fechas/montos de la carátula '
            'sin recalcular comisiones ni modificar la liquidación cerrada.',
        )
    elif comision_locatario > 0 or com_loc > 0:
        _set_comisiones_override_caratula(request, contrato.id, com_loc, comision_locatario)

    messages.success(request, 'Carátula de contrato actualizada.')
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
    # Contratos sin liquidación: no correr el pipeline pesado de gastos pendientes
    # (N+1 de movimientos por reserva/cuota). El resumen de cuotas ya cubre el estado.
    if contrato is not None and liquidacion is None and reserva is None:
        return {'tiene_datos': False}

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
        # Cochera y fondo son ingreso de oficina: no se descuentan del propietario.
        monto_a_pagar = (monto_prop - monto_gastos).quantize(Decimal('0.01'))
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
            'monto_cochera_inquilino': Decimal('0'),
            'monto_fondo': monto_fondo,
            'monto_gastos': monto_gastos,
            'monto_a_pagar': monto_a_pagar,
            'subtotal_propietario': monto_prop,
            'total_descontado': monto_gastos,
            'ingresos_oficina': (monto_coch + monto_fondo).quantize(Decimal('0.01')),
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

    # Reservas por día: siempre calcular toma×días / 70-30 (no depender del listado de pendientes).
    if reserva is not None and reserva.precio_total:
        from inmobiliaria.neto_propietario_movimiento import reparto_liquidacion_reserva_por_dia

        total, prop, inm, _hay_toma = reparto_liquidacion_reserva_por_dia(reserva)
        total, prop, inm, coch, fondo = reserva.montos_liquidacion_efectivos(total, prop, inm)
        coch_inq = Decimal(str(getattr(reserva, 'liq_monto_cochera_inquilino', None) or 0)).quantize(
            Decimal('0.01')
        )
        return {
            'tiene_datos': True,
            'desde_liquidacion': False,
            'liquidacion_id': None,
            'estado_liquidacion': None,
            'moneda': (getattr(reserva, 'moneda', None) or 'ARS'),
            'monto_total': total,
            'monto_propietario': prop,
            'monto_inmobiliaria': inm,
            'monto_cochera': coch,
            'monto_cochera_inquilino': coch_inq,
            'monto_fondo': fondo,
            'monto_gastos': Decimal('0'),
            'monto_a_pagar': prop.quantize(Decimal('0.01')),
            'subtotal_propietario': prop,
            'total_descontado': Decimal('0'),
            'ingresos_oficina': (coch + fondo + coch_inq).quantize(Decimal('0.01')),
            'filas_pago': [
                {
                    'concepto': f'Reserva #{reserva.id}',
                    'monto': prop,
                }
            ],
            'gastos_filas': [],
        }

    data = _operaciones_gastos_pendientes_data(propiedad, sucursal)
    op_match = None
    for op in data.get('operaciones') or []:
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

    if not op_match:
        return {'tiene_datos': False}

    total = Decimal(str(op_match.get('monto_total') or 0))
    prop = Decimal(str(op_match.get('monto_propietario') or 0))
    inm = Decimal(str(op_match.get('monto_inmobiliaria') or 0))
    if inm <= 0 and total > prop:
        inm = (total - prop).quantize(Decimal('0.01'))

    coch = Decimal('0')
    fondo = Decimal('0')

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
        'monto_cochera_inquilino': Decimal('0'),
        'monto_fondo': fondo,
        'monto_gastos': Decimal('0'),
        'monto_a_pagar': prop.quantize(Decimal('0.01')),
        'subtotal_propietario': prop,
        'total_descontado': Decimal('0'),
        'ingresos_oficina': (coch + fondo).quantize(Decimal('0.01')),
        'filas_pago': [
            {
                'concepto': (op_match.get('descripcion') or 'Operación').strip(),
                'monto': prop,
            }
        ],
        'gastos_filas': [],
    }


def _ctx_liquidacion_operacion(
    *,
    reserva=None,
    contrato=None,
    cuotas_enriquecidas=None,
    movimientos=None,
    estado_op_princ=None,
):
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
        from inmobiliaria.liquidacion_operacion import saldo_liquidacion_reserva

        saldo = saldo_liquidacion_reserva(reserva)
        liqs = saldo['liquidaciones']
        ultima = liqs[-1] if liqs else None
        if ultima:
            ctx['liquidacion_operacion'] = ultima
            ctx['url_liquidacion_operacion'] = reverse(
                'inmobiliaria:detalle_liquidacion', args=[ultima.id]
            )
            if saldo['completa']:
                ctx['etiqueta_liquidacion_operacion'] = f'Ver liquidación #{ultima.id}'
            else:
                ctx['url_liquidacion_operacion'] = reverse(
                    'inmobiliaria:crear_liquidacion_reserva', args=[reserva.id]
                )
                ctx['etiqueta_liquidacion_operacion'] = 'Liquidar parte pendiente'
                ctx['url_liquidacion_pendiente'] = reverse(
                    'inmobiliaria:detalle_liquidacion', args=[ultima.id]
                )
                ctx['etiqueta_liquidacion_pendiente'] = f'Ver última liq. #{ultima.id}'
        else:
            ctx['url_liquidacion_operacion'] = reverse(
                'inmobiliaria:crear_liquidacion_reserva', args=[reserva.id]
            )
        resumen = _resumen_liquidacion_caratula(
            reserva=reserva,
            liquidacion=ultima,
            sucursal=reserva.sucursal,
        )
        # Siempre enriquecer con estado de liquidaciones parciales
        if resumen.get('tiene_datos'):
            resumen['liquidaciones_parciales'] = [
                {
                    'id': liq.id,
                    'estado': liq.get_estado_display(),
                    'monto_propietario': liq.monto_propietario,
                    'monto_a_pagar': liq.monto_a_pagar,
                    'url': reverse('inmobiliaria:detalle_liquidacion', args=[liq.id]),
                }
                for liq in liqs
            ]
            resumen['monto_propietario_liquidado'] = saldo['liquidado']
            resumen['monto_propietario_pendiente'] = saldo['pendiente']
            resumen['monto_propietario_corresponde'] = saldo['corresponde']
            resumen['liquidacion_completa'] = saldo['completa']
            resumen['tiene_liquidaciones'] = saldo['tiene_liquidaciones']
            if saldo['tiene_liquidaciones']:
                resumen['desde_liquidacion'] = True
                resumen['liquidacion_id'] = ultima.id if ultima else None
                from inmobiliaria.liquidacion_operacion import montos_reparto_reserva_para_caratula

                total, prop, inm, coch, fondo = montos_reparto_reserva_para_caratula(reserva)
                coch_inq = Decimal(str(getattr(reserva, 'liq_monto_cochera_inquilino', None) or 0)).quantize(
                    Decimal('0.01')
                )
                resumen['monto_total'] = total
                resumen['monto_propietario'] = prop
                resumen['monto_inmobiliaria'] = inm
                resumen['monto_cochera'] = coch
                resumen['monto_cochera_inquilino'] = coch_inq
                resumen['monto_fondo'] = fondo
                resumen['ingresos_oficina'] = (coch + fondo + coch_inq).quantize(Decimal('0.01'))
                resumen['monto_propietario_corresponde'] = saldo['corresponde']
                resumen['subtotal_propietario'] = saldo['corresponde']

                if not saldo['completa']:
                    resumen['estado_liquidacion'] = (
                        f'Parcial — pendiente {saldo["pendiente"]}'
                    )
                    resumen['liquidacion_pendiente'] = True
                    filas_pago = [
                        {
                            'concepto': f'Liquidación #{liq.id}',
                            'monto': Decimal(str(liq.monto_propietario or 0)),
                        }
                        for liq in liqs
                        if Decimal(str(liq.monto_propietario or 0)) > 0
                    ]
                    if saldo['pendiente'] > 0:
                        filas_pago.append(
                            {
                                'concepto': f'Reserva #{reserva.id} (pendiente)',
                                'monto': saldo['pendiente'],
                            }
                        )
                    resumen['filas_pago'] = filas_pago
                    resumen['monto_a_pagar'] = saldo['pendiente']
                else:
                    resumen['liquidacion_pendiente'] = False
                    resumen['monto_a_pagar'] = Decimal('0.00')
                    # Mantener filas de lo liquidado (desde_liquidacion en _resumen)
                    if not resumen.get('filas_pago'):
                        resumen['filas_pago'] = [
                            {
                                'concepto': f'Liquidación #{liq.id}',
                                'monto': Decimal(str(liq.monto_propietario or 0)),
                            }
                            for liq in liqs
                            if Decimal(str(liq.monto_propietario or 0)) > 0
                        ]
        elif not resumen.get('tiene_datos'):
            # Sin liquidación usable: sugerido por operación.
            resumen = _resumen_liquidacion_caratula(
                reserva=reserva,
                liquidacion=None,
                sucursal=reserva.sucursal,
            )
        ctx['resumen_liquidacion'] = resumen
    elif contrato is not None:
        liq_pendiente = (
            LiquidacionPropietario.objects.filter(contrato=contrato, estado='pendiente')
            .order_by('-id')
            .first()
        )
        resumen_ctr = _resumen_liquidacion_contrato_caratula(
            contrato,
            contrato.sucursal,
            cuotas_list=cuotas_enriquecidas,
            movimientos=movimientos,
        )
        proxima = resumen_ctr.get('proxima_cuota_liquidar')
        if estado_op_princ is None:
            estado_op_princ = _estado_liquidacion_operacion_principal_caratula(
                contrato, contrato.sucursal
            )

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
    if dm >= 9:
        return '24 meses'
    return f'Contrato {dm} meses'


def _liquidaciones_propiedad_contrato(contrato):
    """Liquidaciones de la propiedad (cache en el contrato para reutilizar en la misma request)."""
    if not contrato or not contrato.propiedad_id:
        return []
    cached = getattr(contrato, '_cache_liqs_propiedad', None)
    if cached is not None:
        return cached
    liqs = list(
        LiquidacionPropietario.objects.filter(propiedad_id=contrato.propiedad_id)
        .exclude(estado='cancelada')
        .order_by('id')
        .only(
            'id',
            'estado',
            'operaciones_incluidas',
            'propiedad_id',
            'contrato_id',
            'reserva_id',
            'fecha_creacion',
            'fecha_procesamiento',
            'comision_locador',
            'comision_locatario',
        )
    )
    contrato._cache_liqs_propiedad = liqs
    return liqs


def _mapa_liquidacion_por_cuota_contrato(contrato):
    """cuota_id → última liquidación que la incluyó."""
    out = {}
    if not contrato or not contrato.propiedad_id:
        return out
    cached = getattr(contrato, '_cache_mapa_liq_cuota', None)
    if cached is not None:
        return cached
    if 'cuotas' in getattr(contrato, '_prefetched_objects_cache', {}):
        cuota_ids = {int(c.id) for c in contrato.cuotas.all()}
    else:
        cuota_ids = set(contrato.cuotas.values_list('id', flat=True))
    for liq in _liquidaciones_propiedad_contrato(contrato):
        for op in liq.operaciones_incluidas or []:
            if not isinstance(op, dict):
                continue
            tlo = (op.get('tipo') or '').lower()
            ids_cuota = []
            if tlo == 'contrato_cuota':
                try:
                    ids_cuota.append(int(op['id']))
                except (TypeError, ValueError, KeyError):
                    pass
            for raw in op.get('cuotas_ids') or op.get('cuota_ids') or []:
                try:
                    ids_cuota.append(int(raw))
                except (TypeError, ValueError):
                    pass
            for cid in ids_cuota:
                if cid in cuota_ids:
                    out[cid] = liq
    contrato._cache_mapa_liq_cuota = out
    return out


def _cuotas_liquidables_contrato(contrato, sucursal, movimientos=None):
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
    cache_key = '_cache_cuotas_liquidables_ids'
    if movimientos is not None and getattr(contrato, cache_key, None) is not None:
        return getattr(contrato, cache_key)
    cuotas_excluidas = _cuotas_excluidas_por_liquidaciones_contrato(contrato.propiedad)
    out = set()
    for cuota, _monto, _parcial, _anticipada in _cuotas_liquidables_para_contrato(
        contrato, cuotas_excluidas, sucursal, movimientos=movimientos
    ):
        out.add(cuota.id)
    if movimientos is not None:
        setattr(contrato, cache_key, out)
    return out


def _cuotas_pendientes_liquidar_contrato(contrato, sucursal):
    """IDs de cuotas incluibles en crear liquidación (aún no liquidadas)."""
    return _cuotas_liquidables_contrato(contrato, sucursal)


def _contrato_al_dia_liquidacion_cobros(contrato):
    """True si todas las cuotas ya cobradas figuran en alguna liquidación."""
    mapa = _mapa_liquidacion_por_cuota_contrato(contrato)
    # Usar prefetch en memoria (evitar .filter() que dispara N+1).
    if 'cuotas' in getattr(contrato, '_prefetched_objects_cache', {}):
        cobradas = [
            c
            for c in contrato.cuotas.all()
            if (c.estado or '') in ('pagada', 'pagada_con_mora')
        ]
    else:
        cobradas = list(contrato.cuotas.filter(estado__in=['pagada', 'pagada_con_mora']))
    if not cobradas:
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
        mapa_cuota_ids_por_movimiento,
        mapa_movimientos_recibo_por_cuota_id,
    )

    mapa_liq = _mapa_liquidacion_por_cuota_contrato(contrato)
    liquidables = _cuotas_liquidables_contrato(contrato, sucursal, movimientos=movimientos)
    movs = list(movimientos or [])
    if movs and not any(getattr(c, 'recibos_cobro', None) for c in cuotas_list):
        recibos_map = mapa_movimientos_recibo_por_cuota_id(cuotas_list, movs)
        for c in cuotas_list:
            c.recibos_cobro = recibos_map.get(int(c.id), [])

    cuotas_by_id = {int(c.id): c for c in cuotas_list}
    grupos_liquidar: dict[tuple, int] = {}
    # Un solo mapa de recibo→cuotas (antes se reconstruía por cada cuota liquidable)
    mapa_mov = mapa_cuota_ids_por_movimiento(cuotas_list, movs) if movs else {}

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
                mapa_mov=mapa_mov,
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


def _resumen_liquidacion_contrato_caratula(contrato, sucursal, cuotas_list=None, movimientos=None):
    """Conteo de cuotas liquidadas vs pendientes de liquidar."""
    if cuotas_list is not None and cuotas_list and hasattr(cuotas_list[0], 'liq_estado'):
        cuotas = list(cuotas_list)
    else:
        cuotas = list(cuotas_list) if cuotas_list is not None else list(
            contrato.cuotas.all().order_by('numero_cuota')
        )
        _enriquecer_cuotas_liquidacion(cuotas, contrato, sucursal, movimientos=movimientos)
    liquidadas = sum(1 for c in cuotas if getattr(c, 'liq_estado', None) == 'liquidada')
    pendientes = sum(1 for c in cuotas if getattr(c, 'liq_estado', None) == 'pendiente')
    proxima = next((c for c in cuotas if getattr(c, 'mostrar_btn_liquidar', False)), None)
    if proxima is None:
        proxima = next((c for c in cuotas if getattr(c, 'liq_estado', None) == 'pendiente'), None)
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
    try:
        contrato = ContratoAlquiler.objects.only(
            'caratula_comision_locador', 'caratula_comision_locatario'
        ).get(pk=contrato_id)
    except ContratoAlquiler.DoesNotExist:
        contrato = None
    if contrato is not None:
        out = {}
        if contrato.caratula_comision_locador is not None:
            out['comision_locador'] = contrato.caratula_comision_locador
        if contrato.caratula_comision_locatario is not None:
            out['comision_locatario'] = contrato.caratula_comision_locatario
        if out:
            return out

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


def _persist_comisiones_caratula_contrato(contrato, comision_locador, comision_locatario):
    contrato.caratula_comision_locador = comision_locador.quantize(Decimal('0.01'))
    contrato.caratula_comision_locatario = comision_locatario.quantize(Decimal('0.01'))
    contrato.save(update_fields=['caratula_comision_locador', 'caratula_comision_locatario'])


def _clear_comisiones_caratula_contrato(contrato):
    if (
        contrato.caratula_comision_locador is None
        and contrato.caratula_comision_locatario is None
    ):
        return
    contrato.caratula_comision_locador = None
    contrato.caratula_comision_locatario = None
    contrato.save(update_fields=['caratula_comision_locador', 'caratula_comision_locatario'])


def _set_comisiones_override_caratula(request, contrato_id, comision_locador, comision_locatario):
    contrato = ContratoAlquiler.objects.filter(pk=contrato_id).first()
    if contrato:
        _persist_comisiones_caratula_contrato(contrato, comision_locador, comision_locatario)
    overrides = dict(request.session.get(CARATULA_COMISIONES_OVERRIDES_KEY, {}))
    overrides[str(contrato_id)] = {
        'comision_locador': str(comision_locador.quantize(Decimal('0.01'))),
        'comision_locatario': str(comision_locatario.quantize(Decimal('0.01'))),
    }
    request.session[CARATULA_COMISIONES_OVERRIDES_KEY] = overrides
    request.session.modified = True


def _montos_override_contrato_caratula(request, contrato_id):
    overrides = dict(request.session.get(CARATULA_MONTOS_CONTRATO_OVERRIDES_KEY, {}))
    raw = overrides.get(str(contrato_id)) or {}
    out = {}
    for key in ('senia', 'refuerzo'):
        if raw.get(key) is not None:
            try:
                out[key] = Decimal(str(raw[key])).quantize(Decimal('0.01'))
            except (ArithmeticError, TypeError, ValueError):
                pass
    return out or None


def _set_montos_override_contrato_caratula(request, contrato_id, senia=None, refuerzo=None):
    overrides = dict(request.session.get(CARATULA_MONTOS_CONTRATO_OVERRIDES_KEY, {}))
    data = dict(overrides.get(str(contrato_id)) or {})
    if senia is not None:
        data['senia'] = str(senia.quantize(Decimal('0.01')))
    if refuerzo is not None:
        data['refuerzo'] = str(refuerzo.quantize(Decimal('0.01')))
    overrides[str(contrato_id)] = data
    request.session[CARATULA_MONTOS_CONTRATO_OVERRIDES_KEY] = overrides
    request.session.modified = True


def _senia_inferida_contrato_caratula(movimientos):
    """Monto de seña/reserva inicial inferido de movimientos de ingreso."""
    for mov in movimientos or []:
        concepto = (mov.concepto or '').lower()
        if 'reserva' not in concepto and 'seña' not in concepto and 'sena' not in concepto:
            continue
        try:
            mt = Decimal(str(mov.monto_total or 0))
        except (ArithmeticError, TypeError, ValueError):
            mt = Decimal('0')
        if mt > 0:
            return mt.quantize(Decimal('0.01'))
    return Decimal('0')


def _comisiones_cobradas_contrato(contrato, movimientos=None, liquidacion=None, override=None):
    """Participación (85) y honorarios (25) de la operación principal del contrato."""
    from inmobiliaria.views import (
        _comisiones_sugeridas_primera_cuota_contrato,
        _honorarios_operacion_principal_cobrados_contrato,
        _participacion_operacion_principal_cobrada_contrato,
    )

    movs = list(movimientos or [])
    locador = _participacion_operacion_principal_cobrada_contrato(
        contrato, movs if movs else None
    )
    locatario = _honorarios_operacion_principal_cobrados_contrato(
        contrato, movs if movs else None
    )

    if liquidacion is None:
        liquidacion = _liquidacion_contrato(contrato)
    if liquidacion:
        liq_loc = Decimal(str(getattr(liquidacion, 'comision_locador', None) or 0))
        liq_locat = Decimal(str(getattr(liquidacion, 'comision_locatario', None) or 0))
        if liq_loc > Decimal('0.05'):
            locador = liq_loc.quantize(Decimal('0.01'))
        if liq_locat > Decimal('0.05'):
            if (
                locatario > Decimal('0.05')
                and abs(liq_locat - (locatario * 2)) <= Decimal('0.02')
            ):
                locatario = locatario.quantize(Decimal('0.01'))
            else:
                locatario = liq_locat.quantize(Decimal('0.01'))
    else:
        car_loc = getattr(contrato, 'caratula_comision_locador', None)
        car_locat = getattr(contrato, 'caratula_comision_locatario', None)
        if car_loc is not None:
            locador = Decimal(str(car_loc)).quantize(Decimal('0.01'))
        if car_locat is not None:
            locatario = Decimal(str(car_locat)).quantize(Decimal('0.01'))
        if override:
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


def _vendedor_fichaje_contrato_caratula(contrato):
    """Vendedor que fichó la propiedad (comisión fichaje, distinta del productor)."""
    from inmobiliaria.models.comision import vendedor_fichaje_desde_propiedad

    prop = getattr(contrato, 'propiedad', None) if contrato else None
    return vendedor_fichaje_desde_propiedad(prop)


def _label_fichaje_contrato(tipo_fichaje, categoria=None):
    tf = (tipo_fichaje or 'primer').strip().lower()
    base = 'SEGUNDO FICHAJE' if tf == 'segundo' else 'PRIMER FICHAJE'
    cat = (categoria or '').strip().lower()
    if cat in ('invierno', '9'):
        return f'COMIS. VENDEDOR ({base} INVERNO)'
    if cat in ('24', 'largo', 'meses_24', '24_meses', '6', 'meses_6'):
        return f'COMIS. VENDEDOR ({base} 24 MESES)'
    return f'COMIS. VENDEDOR ({base})'


def _categoria_fichaje_contrato(contrato):
    if not contrato:
        return 'dia'
    if hasattr(contrato, 'categoria_tipo_operacion'):
        cat = contrato.categoria_tipo_operacion()
    else:
        dm = int(contrato.duracion_meses or 0)
        cat = 'invierno' if dm == 9 else ('24' if dm >= 9 else 'otro')
    cat = (cat or 'dia').strip().lower()
    if cat in ('6', 'meses_6'):
        return '24'
    return cat


def _pct_fichaje_desde_db_contrato(contrato, vend_fichaje=None):
    from inmobiliaria.models.comision import ROL_COMISION_FICHAJE

    qs = (
        ComisionVendedor.objects.filter(
            contrato=contrato,
            rol_comision=ROL_COMISION_FICHAJE,
        )
        .exclude(estado='cancelada')
        .select_related('vendedor')
        .order_by('-id')
    )
    if vend_fichaje:
        com = qs.filter(vendedor=vend_fichaje).first()
        if com and com.porcentaje_comision and com.porcentaje_comision > 0:
            return com.porcentaje_comision, com.vendedor
    com = qs.first()
    if com and com.porcentaje_comision and com.porcentaje_comision > 0:
        return com.porcentaje_comision, com.vendedor
    return None, None


def _resolver_fichaje_contrato_caratula(contrato):
    """% fichaje, vendedor fichador y metadatos para carátula de contrato."""
    from inmobiliaria.models.persona import Vendedor

    prop = getattr(contrato, 'propiedad', None) if contrato else None
    tipo_fichaje = getattr(prop, 'tipo_fichaje', None) or 'primer'
    cat = _categoria_fichaje_contrato(contrato)
    vend_fichaje = _vendedor_fichaje_contrato_caratula(contrato)

    pct = None
    vend = vend_fichaje
    if vend_fichaje:
        vend_fresh = (
            Vendedor.objects.filter(pk=vend_fichaje.pk).first() if vend_fichaje.pk else vend_fichaje
        )
        if vend_fresh:
            vend = vend_fresh
            pct = vend_fresh.porcentaje_fichaje_efectivo(tipo_fichaje, cat)

    if pct is None or pct <= 0:
        pct_db, vend_db = _pct_fichaje_desde_db_contrato(contrato, vend_fichaje)
        if pct_db and pct_db > 0:
            pct = pct_db
            if vend_db:
                vend = vend_db

    return {
        'pct': pct,
        'vend': vend,
        'tipo_fichaje': tipo_fichaje,
        'cat': cat,
    }


def _linea_fichaje_contrato_caratula(contrato, base_monto):
    from inmobiliaria.models.comision import ROL_COMISION_FICHAJE

    if not contrato or base_monto <= Decimal('0.05'):
        return None

    info = _resolver_fichaje_contrato_caratula(contrato)
    pct = info.get('pct')
    vend = info.get('vend')
    if not vend or pct is None or pct <= 0:
        return None

    monto = (base_monto * Decimal(str(pct)) / Decimal('100')).quantize(Decimal('0.01'))
    return {
        'label': _label_fichaje_contrato(info['tipo_fichaje'], info['cat']),
        'monto': monto,
        'monto_fmt': _formato_importe_us(monto),
        'porcentaje': pct,
        'rol': ROL_COMISION_FICHAJE,
        'vendedor_nombre': _nombre_productor_papel(vend),
        'vendedor_id': vend.id,
    }


def _pct_productor_contrato_caratula(contrato):
    """Porcentajes del vendedor para calcular comisión del productor sobre honorarios."""
    from inmobiliaria.models.comision import (
        iter_productores_contrato,
        pct_comision_24_meses_vendedor,
        pct_comision_invierno_vendedor,
        propiedad_es_oficina,
    )

    productores = iter_productores_contrato(contrato)
    if not contrato or not productores:
        return {}

    vend = productores[0]
    prop = contrato.propiedad
    fichaje_info = _resolver_fichaje_contrato_caratula(contrato)
    tipo_fichaje = fichaje_info['tipo_fichaje']
    cat = fichaje_info['cat']
    pct_fichaje = fichaje_info['pct']
    vend_fichaje = fichaje_info['vend']
    dm = int(contrato.duracion_meses or 0)
    if cat == 'invierno':
        pct_tipo = pct_comision_invierno_vendedor(vend, prop)
        label_tipo = 'Invierno (prop. oficina)' if propiedad_es_oficina(prop) else 'Invierno'
    elif cat == '24':
        pct_tipo = pct_comision_24_meses_vendedor(vend, prop)
        label_tipo = '24 meses (prop. oficina)' if propiedad_es_oficina(prop) else (
            '24 meses' if dm == 24 else 'Largo plazo'
        )
    else:
        pct_tipo = None
        label_tipo = ''

    productores_pct = []
    for v in productores:
        if cat == 'invierno':
            p = pct_comision_invierno_vendedor(v, prop)
        elif cat == '24':
            p = pct_comision_24_meses_vendedor(v, prop)
        else:
            p = None
        if p is not None and p > 0:
            productores_pct.append(
                {
                    'vendedor_id': v.id,
                    'nombre': _nombre_productor_papel(v),
                    'pct': float(p),
                    'label_tipo': label_tipo,
                }
            )

    fecha_entrada = getattr(contrato, 'fecha_entrada_departamento', None) or contrato.fecha_inicio

    return {
        'tipo_fichaje': tipo_fichaje,
        'pct_fichaje': float(pct_fichaje) if pct_fichaje is not None else None,
        'fichador': _nombre_productor_papel(vend_fichaje),
        'pct_tipo': float(pct_tipo) if pct_tipo is not None else None,
        'label_tipo': label_tipo,
        'categoria': cat,
        'productor': _nombres_productores_operacion(contrato=contrato),
        'productores_pct': productores_pct,
        'fecha_entrada': fecha_entrada.isoformat() if fecha_entrada else None,
        'fecha_entrada_display': fecha_entrada.strftime('%d/%m/%Y') if fecha_entrada else '—',
    }


def _ctx_honorarios_comisiones_caratula_contrato(
    contrato, movimientos=None, liquidacion=None, override=None, puede_editar_fechas=False
):
    from inmobiliaria.decimal_utils import format_monto_argentino
    from inmobiliaria.views import _liquidacion_operacion_principal_contrato

    if liquidacion is None:
        liquidacion = _liquidacion_operacion_principal_contrato(contrato)

    comision_locador, comision_locatario = _comisiones_cobradas_contrato(
        contrato, movimientos, liquidacion=liquidacion, override=override
    )
    base_comisiones = _base_monto_comisiones_caratula(comision_locador, comision_locatario)
    comisiones_vendedor = _comisiones_vendedor_contrato_caratula(contrato, base_comisiones)
    _normalizar_lineas_fichaje_caratula(comisiones_vendedor, contrato)
    comisiones_fichaje = [cv for cv in comisiones_vendedor if cv.get('rol') == 'fichaje']
    if not comisiones_fichaje:
        linea_fichaje = _linea_fichaje_contrato_caratula(contrato, base_comisiones)
        if linea_fichaje:
            comisiones_vendedor.insert(0, linea_fichaje)
            comisiones_fichaje = [linea_fichaje]
    comisiones_productor = [cv for cv in comisiones_vendedor if cv.get('rol') != 'fichaje']
    fecha_def = getattr(contrato, 'fecha_entrada_departamento', None) or contrato.fecha_inicio
    _enriquecer_lineas_comision_fecha_db(
        comisiones_productor,
        _mapa_comisiones_db_caratula(contrato=contrato),
        fecha_default=fecha_def,
    )
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
    fecha_def = getattr(contrato, 'fecha_entrada_departamento', None) or contrato.fecha_inicio
    pct['fecha_entrada_input'] = fecha_def.strftime('%Y-%m-%d') if fecha_def else ''
    pct['productor_lineas'] = [
        {
            'comision_id': cv.get('comision_id'),
            'fecha_input': cv.get('fecha_acreditacion_input', ''),
            'label': cv.get('label', ''),
            'pct': float(cv.get('porcentaje') or 0),
        }
        for cv in comisiones_productor
    ]
    pct['puede_editar_fechas'] = bool(puede_editar_fechas)
    fichador_nombre = pct.get('fichador') or ''
    if comisiones_fichaje and comisiones_fichaje[0].get('vendedor_nombre'):
        fichador_nombre = comisiones_fichaje[0].get('vendedor_nombre')
    elif not fichador_nombre:
        vend_fichaje = _vendedor_fichaje_contrato_caratula(contrato)
        if vend_fichaje:
            fichador_nombre = _nombre_productor_papel(vend_fichaje)
    if not (fichador_nombre or '').strip():
        fichador_nombre = _fichador_nombre_caratula(
            getattr(contrato, 'propiedad', None), comisiones_fichaje
        )
    if pct.get('pct_fichaje') is None and comisiones_fichaje:
        pct['pct_fichaje'] = float(comisiones_fichaje[0].get('porcentaje') or 0)

    import json as _json

    return {
        'filas_honorarios': _filas_honorarios_caratula_contrato(contrato, movimientos),
        'comision_locador': comision_locador,
        'comision_locatario': comision_locatario,
        'base_comisiones': base_comisiones,
        'base_comisiones_fmt': format_monto_argentino(base_comisiones),
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


def _comisiones_vendedor_contrato_caratula(contrato, base_monto):
    """
    Líneas de comisión sobre comisión locador + locatario: fichaje al vendedor que fichó
    la propiedad (puede ser distinto del productor); invierno / 24 meses al productor.
    Con varios productores, cada uno cobra sobre su % de participación de la base.
    """
    from inmobiliaria.models.comision import (
        ROL_COMISION_OP_24,
        ROL_COMISION_OP_INVIERNO,
        base_comision_con_participacion,
        iter_productores_contrato,
        mapa_participacion_productores,
        pct_comision_24_meses_vendedor,
        pct_comision_invierno_vendedor,
        propiedad_es_oficina,
    )

    if not contrato or base_monto <= Decimal('0.05'):
        return []

    prop = contrato.propiedad
    lineas = []
    cat = _categoria_fichaje_contrato(contrato)

    linea_fichaje = _linea_fichaje_contrato_caratula(contrato, base_monto)
    if linea_fichaje:
        lineas.append(linea_fichaje)

    productores = iter_productores_contrato(contrato)
    if not productores:
        return lineas

    if cat == 'invierno':
        rol_productor = ROL_COMISION_OP_INVIERNO
        label_base = 'COMIS. VENDEDOR (INVIERNO — PROP. OFICINA)' if propiedad_es_oficina(prop) else 'COMIS. VENDEDOR (INVIERNO)'
    elif cat == '24':
        rol_productor = ROL_COMISION_OP_24
        dm = int(contrato.duracion_meses or 0)
        if propiedad_es_oficina(prop):
            label_base = 'COMIS. VENDEDOR (24 MESES — PROP. OFICINA)' if dm == 24 else 'COMIS. VENDEDOR (LARGO PLAZO — PROP. OFICINA)'
        else:
            label_base = 'COMIS. VENDEDOR (24 MESES)' if dm == 24 else 'COMIS. VENDEDOR (LARGO PLAZO)'
    else:
        return lineas

    part_map = mapa_participacion_productores(contrato=contrato)
    for vend in productores:
        if cat == 'invierno':
            pct = pct_comision_invierno_vendedor(vend, prop)
        else:
            pct = pct_comision_24_meses_vendedor(vend, prop)
        if pct is not None and pct > 0:
            part = part_map.get(vend.id, Decimal('100'))
            base_parte = base_comision_con_participacion(base_monto, part)
            monto = (base_parte * Decimal(str(pct)) / Decimal('100')).quantize(Decimal('0.01'))
            n = len(productores)
            label = label_base
            if n > 1:
                label = f'{label_base} ({part}% op.)'
            lineas.append(
                {
                    'label': label,
                    'monto': monto,
                    'monto_fmt': _formato_importe_us(monto),
                    'porcentaje': pct,
                    'participacion': part,
                    'rol': rol_productor,
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
    from inmobiliaria.models.comision import ROL_COMISION_FICHAJE

    comision_fichaje_total = sum(
        Decimal(str(c.monto_comision or 0))
        for c in comisiones
        if getattr(c, 'rol_comision', None) == ROL_COMISION_FICHAJE
        or (hasattr(c, '_rol_comision_normalizado') and c._rol_comision_normalizado() == ROL_COMISION_FICHAJE)
    )
    comision_productor_total = comision_total - comision_fichaje_total

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

    from inmobiliaria.models.comision import iter_productores_reserva

    productores = iter_productores_reserva(reserva)
    if productores:
        productor = ' · '.join(_nombre_productor_papel(v) for v in productores)
        terceros = ' · '.join(_formato_miles_ar(v.id) for v in productores)
    else:
        productor = '—'
        terceros = '0'

    fichador_nombre = _fichador_nombre_caratula(prop, comisiones)

    # Locación mensual es solo para contratos (invierno / 24 meses).
    # En reservas por día no aplica: antes se mostraba precio÷días y confundía.

    tr = _turista_legado(cli)

    return {
        'numero_original': '0',
        'numero_operacion': _formato_miles_ar(reserva.id),
        'fecha_registro': _instante_operacion_reserva(reserva),
        'fecha_registro_con_hora': True,
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
        'moneda': getattr(reserva, 'moneda', None) or 'ARS',
        'simbolo_moneda': 'U$S' if (getattr(reserva, 'moneda', None) or 'ARS') == 'USD' else '$',
        'comisiones_vendedor': [],
        'comision_productor_total': _formato_importe_us(comision_productor_total),
        'comision_fichaje_total': _formato_importe_us(comision_fichaje_total),
        'fichador_nombre': fichador_nombre,
        'recibo_locador': recibo_loc,
        'recibo_locatario': recibo_locat,
        'url_recibo_locador': url_recibo_loc,
        'url_recibo_locatario': url_recibo_locat,
        'productor': productor,
        'terceros': terceros,
        'origen_operacion': _origen_operacion_sucursal(reserva.sucursal),
        'estado_txt': reserva.get_estado_display(),
        'locacion_mensual': '—',
        'muestra_locacion_mensual': False,
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


def _build_legacy_contrato(
    contrato,
    cuotas,
    tipo_label,
    carpeta_override=None,
    movimientos=None,
    liquidacion=None,
    override=None,
    montos_override=None,
):
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

    from inmobiliaria.decimal_utils import format_monto_argentino
    from inmobiliaria.models.comision import iter_productores_contrato

    productores = iter_productores_contrato(contrato)
    if productores:
        productor = ' · '.join(_nombre_productor_papel(v) for v in productores)
        terceros = ' · '.join(_formato_miles_ar(v.id) for v in productores)
    else:
        productor = '—'
        terceros = '0'

    meses_contrato = int(contrato.duracion_meses or 0)
    recibo_loc, recibo_locat, url_recibo_loc, url_recibo_locat = _recibos_legacy_par(
        movimientos or [],
        [],
        sucursal=contrato.sucursal,
    )

    comision_locador, comision_locatario = _comisiones_cobradas_contrato(
        contrato, movimientos, liquidacion=liquidacion, override=override
    )
    base_comisiones = _base_monto_comisiones_caratula(comision_locador, comision_locatario)
    comisiones_vendedor = _comisiones_vendedor_contrato_caratula(contrato, base_comisiones)
    _normalizar_lineas_fichaje_caratula(comisiones_vendedor, contrato)
    comisiones_fichaje = [cv for cv in comisiones_vendedor if cv.get('rol') == 'fichaje']
    comisiones_total = base_comisiones
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
    fichador_nombre = ''
    vend_fichaje = _vendedor_fichaje_contrato_caratula(contrato)
    if vend_fichaje:
        fichador_nombre = _nombre_productor_papel(vend_fichaje)
    elif comisiones_fichaje:
        fichador_nombre = comisiones_fichaje[0].get('vendedor_nombre', '')
    if not (fichador_nombre or '').strip():
        fichador_nombre = _fichador_nombre_caratula(prop, comisiones_fichaje)

    senia_val = Decimal('0')
    if montos_override and montos_override.get('senia') is not None:
        senia_val = montos_override['senia']
    else:
        senia_val = _senia_inferida_contrato_caratula(movimientos)

    return {
        'numero_original': '0',
        'numero_operacion': _formato_miles_ar(contrato.id),
        # Misma fecha de operación que el listado (con hora de alta si existe).
        'fecha_registro': _instante_operacion_contrato(contrato),
        'fecha_registro_con_hora': bool(getattr(contrato, 'fecha_creacion', None)),
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
        'senia': _formato_importe_us(senia_val),
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
        'locacion_mensual': format_monto_argentino(contrato.precio_mensual),
        'muestra_locacion_mensual': True,
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
    propiedad_id = (request.GET.get('propiedad_id') or '').strip()
    operacion = request.GET.get('operacion', '').strip()
    tipo_filtro = request.GET.get('tipo', '').strip()
    liquidacion_filtro = request.GET.get('liquidacion', '').strip()
    estado_caratula_filtro = request.GET.get('estado_caratula', '').strip()
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
            estado_caratula_filtro=estado_caratula_filtro,
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
                'estado_caratula_filtro': estado_caratula_filtro,
                'periodo_completo': periodo_completo,
                'carpeta_default': _carpeta_default_actual(request),
                'lista_filtros_qs': lista_filtros_qs,
                'puede_imprimir_caratula': _puede_imprimir_caratula(request.user),
            },
        )

    from inmobiliaria.caja_devolucion_deposito import (
        queryset_contratos_con_operacion,
        queryset_reservas_con_operacion,
    )

    reservas = queryset_reservas_con_operacion(
        Reserva.objects.filter(sucursal=sucursal)
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

    hay_busqueda = bool(q) or bool(operacion) or bool(propiedad_id)
    omitir_filtro_fechas = periodo_completo or hay_busqueda

    if propiedad_id.isdigit():
        reservas = reservas.filter(propiedad_id=int(propiedad_id))
    elif q:
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
                fecha_creacion__gte=_aware_day_start(dr_desde),
                fecha_creacion__lt=_aware_day_end_exclusive(dr_hasta),
            )
        elif dr_desde:
            reservas = reservas.filter(fecha_creacion__gte=_aware_day_start(dr_desde))
        elif dr_hasta:
            reservas = reservas.filter(fecha_creacion__lt=_aware_day_end_exclusive(dr_hasta))

    if estado_caratula_filtro == 'confirmada':
        reservas = reservas.filter(estado_confirmacion_caratula='confirmada')
    elif estado_caratula_filtro == 'pendiente':
        reservas = reservas.exclude(estado_confirmacion_caratula='confirmada')

    contratos = queryset_contratos_con_operacion(
        ContratoAlquiler.objects.filter(sucursal=sucursal).select_related(
            'propiedad', 'propiedad__propietario', 'inquilino', 'vendedor'
        )
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

    if propiedad_id.isdigit():
        contratos = contratos.filter(propiedad_id=int(propiedad_id))
    elif q:
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

    if estado_caratula_filtro == 'confirmada':
        contratos = contratos.filter(estado_confirmacion_caratula='confirmada')
    elif estado_caratula_filtro == 'pendiente':
        contratos = contratos.exclude(estado_confirmacion_caratula='confirmada')

    if periodo_completo and not hay_busqueda:
        reservas = reservas[:LISTA_CARATULAS_MAX_FILAS]
        contratos = contratos[:LISTA_CARATULAS_MAX_FILAS]

    contratos = contratos.prefetch_related('cuotas')

    # Materializar una sola vez (evita re-evaluar queryset en loops).
    reservas_list = list(reservas)
    contratos_list = list(contratos)

    reserva_ids = [r.id for r in reservas_list]

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

    # Batch de liquidaciones por propiedad (evita 1 query por contrato).
    prop_ids_contratos = {c.propiedad_id for c in contratos_list if c.propiedad_id}
    liqs_por_propiedad = {pid: [] for pid in prop_ids_contratos}
    if prop_ids_contratos:
        for liq in (
            LiquidacionPropietario.objects.filter(propiedad_id__in=prop_ids_contratos)
            .exclude(estado='cancelada')
            .order_by('id')
            .only(
                'id',
                'estado',
                'operaciones_incluidas',
                'propiedad_id',
                'contrato_id',
                'reserva_id',
                'fecha_creacion',
                'fecha_procesamiento',
                'comision_locador',
                'comision_locatario',
            )
        ):
            liqs_por_propiedad.setdefault(liq.propiedad_id, []).append(liq)
    for c in contratos_list:
        c._cache_liqs_propiedad = liqs_por_propiedad.get(c.propiedad_id, [])

    filas = []

    for r in reservas_list:
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
                'propietario_nombre': _nombre_propietario_papel(getattr(p, 'propietario', None) if p else None),
                'propiedad_linea': plinea,
                'propiedad_sub': psub,
                'direccion': p.direccion if p else '—',
                'piso_dto': piso_dto,
                'ficha': p.id if p else '—',
                'estado': (
                    'Eliminada'
                    if r.eliminada
                    else (r.get_estado_display() if hasattr(r, 'get_estado_display') else r.estado)
                ),
                'eliminada': bool(r.eliminada),
                'carpeta': '—',
                'tiene_liquidacion': tiene_liquidacion,
                'liquidacion_id': liquidacion_id,
                'estado_operacion_caratula': getattr(r, 'estado_confirmacion_caratula', 'pendiente') or 'pendiente',
            }
        )

    for c in contratos_list:
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
                'propietario_nombre': _nombre_propietario_papel(getattr(p, 'propietario', None) if p else None),
                'propiedad_linea': clinea,
                'propiedad_sub': csub,
                'direccion': p.direccion if p else '—',
                'piso_dto': piso_dto,
                'ficha': p.id if p else '—',
                'estado': c.get_estado_display() if hasattr(c, 'get_estado_display') else c.estado,
                'carpeta': carpeta_hist or '—',
                'tiene_liquidacion': tiene_liquidacion,
                'liquidacion_id': liquidacion_id,
                'estado_operacion_caratula': getattr(c, 'estado_confirmacion_caratula', 'pendiente') or 'pendiente',
            }
        )
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
        estado_caratula_filtro=estado_caratula_filtro,
        periodo_completo=periodo_completo,
        propiedad_id=propiedad_id,
    )
    lista_ver_qs = _query_string_lista_caratulas(
        q=q,
        operacion=operacion,
        fecha_desde=fecha_desde if not periodo_completo else '',
        fecha_hasta=fecha_hasta if not periodo_completo else '',
        tipo_filtro=tipo_filtro,
        liquidacion_filtro=liquidacion_filtro,
        estado_caratula_filtro=estado_caratula_filtro,
        periodo_completo=periodo_completo,
        page=page_obj.number if page_obj.number > 1 else None,
        propiedad_id=propiedad_id,
    )

    return render(
        request,
        'inmobiliaria/caratulas/lista.html',
        {
            'filas': page_obj,
            'q': q,
            'propiedad_id': propiedad_id if propiedad_id.isdigit() else '',
            'operacion': operacion,
            'fecha_desde': fecha_desde if not periodo_completo else '',
            'fecha_hasta': fecha_hasta if not periodo_completo else '',
            'tipo_filtro': tipo_filtro,
            'liquidacion_filtro': liquidacion_filtro,
            'estado_caratula_filtro': estado_caratula_filtro,
            'periodo_completo': periodo_completo,
            'busqueda_activa': hay_busqueda,
            'carpeta_default': _carpeta_default_actual(request),
            'total_filas': total_filas,
            'lista_filtros_qs': lista_filtros_qs,
            'lista_ver_qs': lista_ver_qs,
            'puede_imprimir_caratula': _puede_imprimir_caratula(request.user),
        },
    )


@login_required
def caratula_reserva(request, reserva_id):
    if not _puede_ver_caratulas(request.user):
        return HttpResponseForbidden()
    reserva = get_object_or_404(
        Reserva.objects.select_related(
            'cliente',
            'propiedad',
            'propiedad__propietario',
            'propiedad__fichado_por',
            'vendedor',
            'sucursal',
            'usuario_eliminacion',
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

    if request.method == 'POST' and request.POST.get('action') == 'confirmar_operacion_caratula':
        _procesar_confirmar_operacion_caratula(request, reserva=reserva)
        return _redirect_caratula_con_filtros('inmobiliaria:caratula_reserva', reserva_id, request)

    if request.method == 'POST' and request.POST.get('action') == 'desconfirmar_operacion_caratula':
        _procesar_desconfirmar_operacion_caratula(request, reserva=reserva)
        return _redirect_caratula_con_filtros('inmobiliaria:caratula_reserva', reserva_id, request)

    if request.method == 'POST' and request.POST.get('action') == 'anular_operacion_caratula':
        if _procesar_anular_operacion_reserva_caratula(request, reserva):
            return redirect(_url_lista_caratulas_desde_request(request))
        reserva.refresh_from_db()

    if request.method == 'POST' and request.POST.get('action') in (
        'agregar_productor_caratula',
        'quitar_productor_caratula',
        'guardar_participaciones_caratula',
    ):
        if _procesar_productores_caratula(request, reserva=reserva):
            return _redirect_caratula_con_filtros('inmobiliaria:caratula_reserva', reserva_id, request)
        reserva.refresh_from_db()

    if request.method == 'POST' and request.POST.get('action') == 'save_fechas_comision_caratula':
        if _procesar_guardar_fechas_comision_caratula(request, reserva=reserva):
            return _redirect_caratula_con_filtros('inmobiliaria:caratula_reserva', reserva_id, request)

    if request.method == 'POST' and request.POST.get('action') == 'save_caratula_reserva':
        if _guardar_caratula_reserva(request, reserva):
            return _redirect_caratula_con_filtros('inmobiliaria:caratula_reserva', reserva_id, request)
        reserva.refresh_from_db()

    movimientos = _movimientos_operacion_reserva(reserva)
    recibos = list(reserva.recibos.all())

    # Generar/actualizar comisiones aunque no haya movimientos vinculados en caja
    # (p. ej. operación marcada pagada sin cobro con "Operación {id}" en el concepto).
    from inmobiliaria.models.comision import asegurar_comisiones_reserva

    asegurar_comisiones_reserva(reserva, movimientos_caja=movimientos)
    comisiones = _comisiones_visibles_caratula_reserva(reserva)

    from inmobiliaria.models.comision import mapa_participacion_productores
    from inmobiliaria.caja_devolucion_deposito import ya_devolvio_deposito_reserva

    part_map = mapa_participacion_productores(reserva=reserva)
    for c in comisiones:
        c.participacion_operacion_caratula = part_map.get(getattr(c, 'vendedor_id', None))

    # El total de la carátula es lo cobrado (ingresos); la devolución de depósito es egreso aparte.
    total_mov = sum(
        (
            Decimal(str(m.monto_efectivo or 0))
            + Decimal(str(m.monto_cheque or 0))
            + Decimal(str(m.monto_tarjeta or 0))
            + Decimal(str(m.monto_deposito or 0))
        )
        for m in movimientos
        if (getattr(m, 'tipo', None) or '').strip().upper() != TipoMovimientoCajaEnum.EGRESO
    )
    deposito_ya_devuelto = ya_devolvio_deposito_reserva(reserva)

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
        'deposito_ya_devuelto': deposito_ya_devuelto,
        'saldo_reserva': saldo_reserva,
        'puede_editar_caratula': _puede_editar_caratula(request.user),
        'puede_imprimir_caratula': _puede_imprimir_caratula(request.user),
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
        **_ctx_estado_operacion_caratula(reserva=reserva, user=request.user),
        **_ctx_productores_operacion(
            reserva=reserva,
            puede_editar=_puede_editar_caratula(request.user),
        ),
    }
    rl = ctx['resumen_liquidacion']
    ctx['edit_montos_liquidacion'] = {
        'monto_propietario': format_monto_argentino(rl.get('monto_propietario') or 0),
        'monto_inmobiliaria': format_monto_argentino(rl.get('monto_inmobiliaria') or 0),
        'monto_cochera': format_monto_argentino(rl.get('monto_cochera') or 0),
        'monto_cochera_inquilino': format_monto_argentino(
            getattr(reserva, 'liq_monto_cochera_inquilino', None)
            if getattr(reserva, 'liq_monto_cochera_inquilino', None) is not None
            else (rl.get('monto_cochera_inquilino') or 0)
        ),
        'monto_fondo': format_monto_argentino(rl.get('monto_fondo') or 0),
    }
    es_super = _es_super_admin(request.user)
    ctx['puede_editar_liquidacion_resumen'] = bool(
        ctx['puede_editar_caratula']
        and rl.get('tiene_datos')
        and (not rl.get('desde_liquidacion') or es_super)
    )
    ctx['edicion_montos_solo_caratula'] = bool(
        es_super and rl.get('desde_liquidacion') and ctx['puede_editar_liquidacion_resumen']
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
        if action == 'confirmar_operacion_caratula':
            _procesar_confirmar_operacion_caratula(request, contrato=contrato)
            return _redirect_caratula_con_filtros('inmobiliaria:caratula_contrato', contrato_id, request)
        if action == 'desconfirmar_operacion_caratula':
            _procesar_desconfirmar_operacion_caratula(request, contrato=contrato)
            return _redirect_caratula_con_filtros('inmobiliaria:caratula_contrato', contrato_id, request)
        if action in (
            'agregar_productor_caratula',
            'quitar_productor_caratula',
            'guardar_participaciones_caratula',
        ):
            if _procesar_productores_caratula(request, contrato=contrato):
                return _redirect_caratula_con_filtros('inmobiliaria:caratula_contrato', contrato_id, request)
            contrato.refresh_from_db()
        if action == 'save_fechas_comision_caratula':
            if _procesar_guardar_fechas_comision_caratula(request, contrato=contrato):
                return _redirect_caratula_con_filtros('inmobiliaria:caratula_contrato', contrato_id, request)
        if action == 'save_caratula_contrato':
            if _guardar_caratula_contrato(request, contrato):
                return _redirect_caratula_con_filtros('inmobiliaria:caratula_contrato', contrato_id, request)
            contrato.refresh_from_db()
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
                _clear_comisiones_caratula_contrato(contrato)
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
                    honorarios_monto=_base_monto_comisiones_caratula(com_loc, com_locat),
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
        puede_editar_fechas=_puede_editar_caratula(request.user),
    )
    estado_op_princ = _estado_liquidacion_operacion_principal_caratula(contrato, contrato.sucursal)
    honorarios_ctx.update(estado_op_princ)

    # No escribir comisiones en GET: se aseguran al guardar / agregar productor.

    montos_override = _montos_override_contrato_caratula(request, contrato.id)
    caratula_legacy = _build_legacy_contrato(
        contrato,
        cuotas_list,
        tipo_label,
        carpeta_override=carpeta_guardada,
        movimientos=movimientos,
        liquidacion=liquidacion_hon,
        override=override,
        montos_override=montos_override,
    )

    from inmobiliaria.decimal_utils import format_monto_argentino

    total_contrato = (contrato.precio_mensual or Decimal('0')) * Decimal(contrato.duracion_meses or 0)
    senia_display = (
        montos_override.get('senia')
        if montos_override and montos_override.get('senia') is not None
        else _senia_inferida_contrato_caratula(movimientos)
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
        'puede_editar_caratula': _puede_editar_caratula(request.user),
        'puede_imprimir_caratula': _puede_imprimir_caratula(request.user),
        'edit_montos': {
            'precio_total': format_monto_argentino(total_contrato),
            'senia': format_monto_argentino(senia_display),
            'deposito': format_monto_argentino(contrato.deposito_garantia),
            'comision_locatario': format_monto_argentino(
                honorarios_ctx.get('comision_locatario') or 0
            ),
        },
        'reserva': contrato,
        'reserva_estado_choices': ContratoAlquiler._meta.get_field('estado').choices,
        'form_caratula_contrato_id': 'form-editar-caratula-contrato',
        **_ctx_liquidacion_operacion(
            contrato=contrato,
            cuotas_enriquecidas=cuotas_list,
            movimientos=movimientos,
            estado_op_princ=estado_op_princ,
        ),
        'volver_lista_url': _url_lista_caratulas_desde_request(request),
        **_ctx_estado_operacion_caratula(contrato=contrato, user=request.user),
        **_ctx_productores_operacion(
            contrato=contrato,
            puede_editar=_puede_editar_caratula(request.user),
        ),
    }
    return render(request, 'inmobiliaria/caratulas/detalle_contrato.html', ctx)


@login_required
def imprimir_caratula_reserva(request, reserva_id):
    """Vista sólo impresión: formato papel (vendedores operativos tras el recibo)."""
    if not _puede_imprimir_caratula(request.user):
        return HttpResponseForbidden('No tenés permiso para imprimir carátulas.')
    reserva = get_object_or_404(
        Reserva.objects.select_related(
            'cliente', 'propiedad', 'propiedad__propietario', 'propiedad__fichado_por', 'vendedor', 'sucursal'
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

    fdoc = _instante_operacion_reserva(reserva)
    fdoc_con_hora = bool(getattr(reserva, 'fecha_creacion', None))

    volver_url, volver_label = _volver_imprimir_caratula(request, reserva_id=reserva_id)

    ctx = {
        'es_reserva': True,
        'volver_url': volver_url,
        'volver_label': volver_label,
        'rubro_title': 'ALQUILERES',
        'numero_display': f"Nº OP {_formato_miles_ar(reserva.id)}",
        'llave': cl['codigo_llave'],
        'fecha_documento': fdoc,
        'fecha_documento_con_hora': fdoc_con_hora,
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
        'productor_nombre': _nombres_productores_operacion(reserva=reserva),
        'fichador_nombre': cl.get('fichador_nombre') or _fichador_nombre_caratula(
            reserva.propiedad, comisiones
        ),
    }
    return render(request, 'inmobiliaria/caratulas/imprimir_caratula_papel.html', ctx)


@login_required
def imprimir_caratula_contrato(request, contrato_id):
    if not _puede_imprimir_caratula(request.user):
        return HttpResponseForbidden('No tenés permiso para imprimir carátulas.')
    contrato = get_object_or_404(
        ContratoAlquiler.objects.select_related(
            'propiedad', 'propiedad__propietario', 'propiedad__fichado_por', 'inquilino', 'vendedor', 'sucursal'
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

    fdoc = _instante_operacion_contrato(contrato)
    fdoc_con_hora = bool(getattr(contrato, 'fecha_creacion', None))

    volver_url, volver_label = _volver_imprimir_caratula(request, contrato_id=contrato_id)

    ctx = {
        'es_reserva': False,
        'volver_url': volver_url,
        'volver_label': volver_label,
        'rubro_title': 'CONTRATO DE LOCACIÓN',
        'numero_display': f"Nº CT {_formato_miles_ar(contrato.id)}",
        'llave': cl['codigo_llave'],
        'fecha_documento': fdoc,
        'fecha_documento_con_hora': fdoc_con_hora,
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
        'productor_nombre': _nombres_productores_operacion(contrato=contrato),
        'fichador_nombre': cl.get('fichador_nombre') or _fichador_nombre_caratula(contrato.propiedad),
    }
    return render(request, 'inmobiliaria/caratulas/imprimir_caratula_papel.html', ctx)
