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

CARATULA_CARPETA_DEFAULT_KEY = 'caratulas_carpeta_default'
CARATULA_CARPETA_OVERRIDES_KEY = 'caratulas_carpeta_overrides'


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


def _carpeta_para_operacion(request, kind, op_id):
    key = f'{kind}:{op_id}'
    overrides = dict(request.session.get(CARATULA_CARPETA_OVERRIDES_KEY, {}))
    if key in overrides:
        return _normalizar_carpeta(overrides.get(key))
    # Congela carpeta histórica de la operación la primera vez que se consulta.
    carpeta_historica = _carpeta_default_actual(request)
    overrides[key] = carpeta_historica
    request.session[CARATULA_CARPETA_OVERRIDES_KEY] = overrides
    request.session.modified = True
    return carpeta_historica


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


def _recibos_legacy_par(movs, recibos):
    """Primer y segundo número de recibo para el bloque legado de carátula."""
    numeros = []
    vistos = set()
    for r in sorted(recibos, key=lambda x: x.fecha_emision or datetime.min):
        n = _numero_recibo_desde_recibo(r)
        if n and n != '—' and n not in vistos:
            numeros.append(n)
            vistos.add(n)
    for m in sorted(movs, key=lambda x: (x.fecha, x.id)):
        n = _numero_recibo_desde_movimiento(m)
        if n and n != '—' and n not in vistos:
            numeros.append(n)
            vistos.add(n)
    loc = numeros[0] if numeros else '0000-00000000'
    locat = numeros[1] if len(numeros) > 1 else loc
    return loc, locat


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


def _ctx_liquidacion_operacion(*, reserva=None, contrato=None):
    """Enlace a crear o ver liquidación del propietario para esta operación."""
    ctx = {
        'liquidacion_operacion': None,
        'url_liquidacion_operacion': None,
        'etiqueta_liquidacion_operacion': 'Liquidar operación',
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
    elif contrato is not None:
        liq = (
            LiquidacionPropietario.objects.filter(contrato=contrato)
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
                'inmobiliaria:crear_liquidacion_contrato', args=[contrato.id]
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
        return 'Por día'
    if getattr(propiedad, 'tipo_cliente', None) == 'ESTUDIANTE':
        return 'Estudiante'
    return 'Por día'


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
    dm = contrato.duracion_meses or 0
    if dm == 9:
        return 'invierno'
    if dm == 24:
        return 'meses_24'
    if dm == 6:
        return 'meses_6'
    return 'otros'


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
    carpeta_override=None,
    movimientos=None,
):
    prop = reserva.propiedad
    cli = reserva.cliente
    propi = getattr(prop, 'propietario', None) if prop else None
    vend = reserva.vendedor

    recibo_loc, recibo_locat = _recibos_legacy_par(movimientos or [], recibos)

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
        'recibo_locador': recibo_loc,
        'recibo_locatario': recibo_locat,
        'productor': productor,
        'terceros': terceros,
        'origen_operacion': _origen_operacion_sucursal(reserva.sucursal),
        'estado_txt': reserva.get_estado_display(),
        'locacion_mensual': _formato_importe_us(loc_mensual),
        'carpeta': _normalizar_carpeta(carpeta_override) if carpeta_override is not None else str(dias_estadia),
        'tipo_operacion_str': tipo_operacion_str,
    }


def _build_legacy_contrato(contrato, cuotas, tipo_label, carpeta_override=None, movimientos=None):
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
    recibo_loc, recibo_locat = _recibos_legacy_par(movimientos or [], [])

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
        'comision_locador': _formato_importe_us(0),
        'comision_locatario': _formato_importe_us(0),
        'recibo_locador': recibo_loc,
        'recibo_locatario': recibo_locat,
        'productor': productor,
        'terceros': terceros,
        'origen_operacion': _origen_operacion_sucursal(contrato.sucursal),
        'estado_txt': contrato.get_estado_display(),
        'locacion_mensual': _formato_importe_us(contrato.precio_mensual),
        'carpeta': _normalizar_carpeta(carpeta_override) if carpeta_override is not None else str(meses_contrato),
        'tipo_operacion_str': tipo_label,
    }


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
                'periodo_completo': periodo_completo,
                'carpeta_default': _carpeta_default_actual(request),
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
        q_res = (
            Q(propiedad__direccion__icontains=q)
            | Q(propiedad__ubicacion__icontains=q)
            | Q(propiedad__titulo__icontains=q)
            | Q(propiedad__id__icontains=q)
            | Q(propiedad__propietario__nombre__icontains=q)
            | Q(propiedad__propietario__apellido__icontains=q)
            | Q(propiedad__propietario__dni__icontains=q)
            | Q(propiedad__propietario__cuit__icontains=q)
            | Q(propiedad__propietario__email__icontains=q)
            | Q(cliente__nombre__icontains=q)
            | Q(cliente__apellido__icontains=q)
        )
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
                fecha_inicio__lte=dr_hasta,
                fecha_fin__gte=dr_desde,
            )
        elif dr_desde:
            reservas = reservas.filter(fecha_fin__gte=dr_desde)
        elif dr_hasta:
            reservas = reservas.filter(fecha_inicio__lte=dr_hasta)

    contratos = ContratoAlquiler.objects.filter(sucursal=sucursal).select_related(
        'propiedad', 'inquilino', 'vendedor'
    )
    if tipo_filtro == 'invierno':
        contratos = contratos.filter(duracion_meses=9)
    elif tipo_filtro == '24meses':
        contratos = contratos.filter(duracion_meses=24)
    elif tipo_filtro in ('dia', 'estudiante'):
        contratos = contratos.none()

    if operacion:
        contratos = contratos.filter(id=operacion_num) if operacion_num is not None else contratos.none()

    contratos = contratos.order_by('-fecha_creacion', '-id')

    if q:
        q_ctr = (
            Q(propiedad__direccion__icontains=q)
            | Q(propiedad__ubicacion__icontains=q)
            | Q(propiedad__titulo__icontains=q)
            | Q(propiedad__id__icontains=q)
            | Q(propiedad__propietario__nombre__icontains=q)
            | Q(propiedad__propietario__apellido__icontains=q)
            | Q(propiedad__propietario__dni__icontains=q)
            | Q(propiedad__propietario__cuit__icontains=q)
            | Q(propiedad__propietario__email__icontains=q)
            | Q(inquilino__nombre__icontains=q)
            | Q(inquilino__apellido__icontains=q)
        )
        if q.isdigit():
            try:
                q_ctr |= Q(id=int(q))
            except (TypeError, ValueError):
                pass
        contratos = contratos.filter(q_ctr)
    if not omitir_filtro_fechas:
        if dr_desde and dr_hasta:
            contratos = contratos.filter(
                fecha_inicio__lte=dr_hasta,
                fecha_fin__gte=dr_desde,
            )
        elif dr_desde:
            contratos = contratos.filter(fecha_fin__gte=dr_desde)
        elif dr_hasta:
            contratos = contratos.filter(fecha_inicio__lte=dr_hasta)

    filas = []

    for r in reservas:
        carpeta_hist = _carpeta_para_operacion(request, 'reserva', r.id)
        tipo = _tipo_reserva(r.propiedad)
        p = r.propiedad
        piso_dto = ''
        if p:
            pi = (p.piso or '').strip() or '—'
            dep = (p.departamento or '').strip() or '—'
            piso_dto = f'{pi} / {dep}'
        plinea, psub = _etiqueta_propiedad_lista(p)
        filas.append(
            {
                'kind': 'reserva',
                'pk': r.id,
                'tipo': tipo,
                'numero': r.id,
                'fecha': r.fecha_inicio,
                'caratula': _caratula_nombre_cliente(r.cliente),
                'propiedad_linea': plinea,
                'propiedad_sub': psub,
                'direccion': p.direccion if p else '—',
                'piso_dto': piso_dto,
                'ficha': p.id if p else '—',
                'estado': r.get_estado_display() if hasattr(r, 'get_estado_display') else r.estado,
                'carpeta': carpeta_hist,
                'sort': r.fecha_creacion or r.fecha_inicio,
            }
        )

    for c in contratos:
        carpeta_hist = _carpeta_para_operacion(request, 'contrato', c.id)
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
        clinea, csub = _etiqueta_propiedad_lista(p)
        filas.append(
            {
                'kind': 'contrato',
                'pk': c.id,
                'tipo': tipo_c,
                'numero': c.id,
                'fecha': c.fecha_operacion,
                'caratula': _caratula_nombre_cliente(c.inquilino),
                'propiedad_linea': clinea,
                'propiedad_sub': csub,
                'direccion': p.direccion if p else '—',
                'piso_dto': piso_dto,
                'ficha': p.id if p else '—',
                'estado': c.get_estado_display() if hasattr(c, 'get_estado_display') else c.estado,
                'carpeta': carpeta_hist,
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
            'operacion': operacion,
            'fecha_desde': fecha_desde if not periodo_completo else '',
            'fecha_hasta': fecha_hasta if not periodo_completo else '',
            'tipo_filtro': tipo_filtro,
            'periodo_completo': periodo_completo,
            'busqueda_por_numero': busqueda_por_numero,
            'carpeta_default': _carpeta_default_actual(request),
        },
    )


@login_required
def caratula_reserva(request, reserva_id):
    if not _puede_ver_caratulas(request.user):
        return HttpResponseForbidden()
    if request.method == 'POST' and request.POST.get('action') == 'set_carpeta_reserva':
        _set_carpeta_override(request, 'reserva', reserva_id, request.POST.get('carpeta'))
        return redirect('inmobiliaria:caratula_reserva', reserva_id=reserva_id)
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
    carpeta_actual = _carpeta_para_operacion(request, 'reserva', reserva.id)
    ctx = {
        'reserva': reserva,
        'propiedad': reserva.propiedad,
        'tipo_operacion': tipo_op,
        'movimientos': movimientos,
        'recibos': recibos,
        'comisiones': comisiones,
        'total_movimientos': total_mov,
        'saldo_reserva': saldo_reserva,
        'caratula_legacy': _build_legacy_reserva(
            reserva,
            recibos,
            comisiones,
            saldo_reserva,
            tipo_op,
            carpeta_override=carpeta_actual,
            movimientos=movimientos,
        ),
        'carpeta_actual': carpeta_actual,
        'carpeta_default': _carpeta_default_actual(request),
        **_ctx_liquidacion_operacion(reserva=reserva),
    }
    return render(request, 'inmobiliaria/caratulas/detalle_reserva.html', ctx)


@login_required
def caratula_contrato(request, contrato_id):
    if not _puede_ver_caratulas(request.user):
        return HttpResponseForbidden()
    if request.method == 'POST' and request.POST.get('action') == 'set_carpeta_contrato':
        _set_carpeta_override(request, 'contrato', contrato_id, request.POST.get('carpeta'))
        return redirect('inmobiliaria:caratula_contrato', contrato_id=contrato_id)
    contrato = get_object_or_404(
        ContratoAlquiler.objects.select_related(
            'propiedad', 'propiedad__propietario', 'inquilino', 'vendedor', 'sucursal'
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

    movimientos = []
    if contrato.propiedad_id:
        movs_qs = (
            MovimientoCaja.objects.filter(
                propiedad_id=contrato.propiedad_id,
                sucursal_id=contrato.sucursal_id,
                tipo=TipoMovimientoCajaEnum.INGRESO,
            )
            .select_related('recibo')
            .order_by('-fecha')
        )
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

    cuotas_list = list(contrato.cuotas.all()) if hasattr(contrato, 'cuotas') else []
    if cuotas_list:
        from inmobiliaria.cuotas_imputacion import mapa_movimientos_recibo_por_cuota_id

        recibos_por_cuota = mapa_movimientos_recibo_por_cuota_id(cuotas_list, movimientos)
        for c in cuotas_list:
            c.recibos_cobro = recibos_por_cuota.get(int(c.id), [])

    if contrato.duracion_meses == 9:
        tipo_label = 'Invierno (9 meses)'
    elif contrato.duracion_meses == 24:
        tipo_label = '24 meses'
    else:
        tipo_label = f'Contrato {contrato.duracion_meses} meses'
    carpeta_actual = _carpeta_para_operacion(request, 'contrato', contrato.id)

    ctx = {
        'contrato': contrato,
        'propiedad': contrato.propiedad,
        'tipo_label': tipo_label,
        'movimientos': movimientos,
        'total_movimientos': total_mov,
        'cuotas': cuotas_list,
        'caratula_legacy': _build_legacy_contrato(
            contrato,
            cuotas_list,
            tipo_label,
            carpeta_override=carpeta_actual,
            movimientos=movimientos,
        ),
        'carpeta_actual': carpeta_actual,
        'carpeta_default': _carpeta_default_actual(request),
        **_ctx_liquidacion_operacion(contrato=contrato),
    }
    return render(request, 'inmobiliaria/caratulas/detalle_contrato.html', ctx)


@login_required
def imprimir_caratula_reserva(request, reserva_id):
    """Vista sólo impresión: formato papel tipo libro de alquileres."""
    if not _puede_ver_caratulas(request.user):
        return HttpResponseForbidden()
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
        carpeta_override=_carpeta_para_operacion(request, 'reserva', reserva.id),
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

    ctx = {
        'es_reserva': True,
        'volver_url': reverse('inmobiliaria:caratula_reserva', args=[reserva_id]),
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
    if not _puede_ver_caratulas(request.user):
        return HttpResponseForbidden()
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
    if contrato.duracion_meses == 9:
        tipo_label = 'Invierno (9 meses)'
    elif contrato.duracion_meses == 24:
        tipo_label = '24 meses'
    else:
        tipo_label = f'Contrato {contrato.duracion_meses} meses'
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
        carpeta_override=_carpeta_para_operacion(request, 'contrato', contrato.id),
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

    ctx = {
        'es_reserva': False,
        'volver_url': reverse('inmobiliaria:caratula_contrato', args=[contrato_id]),
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
