import json
import re
from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import F, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from inmobiliaria.decimal_utils import parse_decimal_monto
from inmobiliaria.models.caja import MovimientoCaja, TipoMovimientoCajaEnum
from inmobiliaria.models.sucursal import CuentaBancaria

# Corte único para todas las cuentas: el saldo inicial cuenta como del 05/06/2026.
FECHA_SALDO_INICIAL_CUENTA = date(2026, 6, 5)


def _parse_saldo_inicial_post(request) -> Decimal:
    raw = (request.POST.get('saldo_inicial') or '0').strip()
    try:
        return parse_decimal_monto(raw).quantize(Decimal('0.01'))
    except Exception:
        return Decimal('0')


def _parse_fecha_filtro(valor):
    if not valor:
        return None
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    try:
        return datetime.strptime(str(valor)[:10], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _saldo_inicial_en_periodo(fecha_desde, fecha_hasta, periodo_completo=False):
    """
    El saldo inicial (fecha fija 05/06) se muestra como fila propia solo si esa fecha
    cae dentro del período (o es todo el historial).
    """
    if periodo_completo:
        return True
    fd = _parse_fecha_filtro(fecha_desde)
    fh = _parse_fecha_filtro(fecha_hasta)
    if fd is not None and fh is not None:
        return fd <= FECHA_SALDO_INICIAL_CUENTA <= fh
    if fd is not None:
        return fd <= FECHA_SALDO_INICIAL_CUENTA
    if fh is not None:
        return fh >= FECHA_SALDO_INICIAL_CUENTA
    return True


def _mostrar_fila_saldo_inicial(fecha_desde, fecha_hasta, periodo_completo=False):
    """Mostrar la fila 'Saldo inicial' con fecha 05/06 cuando cae dentro del filtro."""
    return _saldo_inicial_en_periodo(fecha_desde, fecha_hasta, periodo_completo)


def _qs_movimientos_cuenta(sucursal, destino):
    return (
        MovimientoCaja.objects.filter(
            sucursal=sucursal,
            destino_deposito=destino,
            monto_deposito__gt=0,
        ).annotate(fecha_banco=Coalesce(F('fecha_transferencia'), TruncDate('fecha')))
    )


def _neto_movimientos_cuenta(qs) -> Decimal:
    total_ing = (
        qs.filter(tipo=TipoMovimientoCajaEnum.INGRESO).aggregate(t=Sum('monto_deposito'))['t']
        or Decimal('0')
    )
    total_egr = (
        qs.filter(tipo=TipoMovimientoCajaEnum.EGRESO).aggregate(t=Sum('monto_deposito'))['t']
        or Decimal('0')
    )
    return (Decimal(str(total_ing)) - Decimal(str(total_egr))).quantize(Decimal('0.01'))


def _saldo_apertura_periodo(
    cuenta, sucursal, destino, fecha_desde, fecha_hasta, periodo_completo=False
) -> Decimal:
    """
    Saldo al inicio del rango filtrado (como el «TRANSPORTE» del extracto bancario).

    - Todo el historial / período que incluye el 05/06: arranca en 0; la fila de
      saldo inicial suma el corte.
    - Período que empieza después del 05/06: SI + movimientos desde el corte
      hasta el día anterior a ``fecha_desde``.
    """
    saldo_si = Decimal(str(cuenta.saldo_inicial or 0)).quantize(Decimal('0.01'))
    if periodo_completo:
        return Decimal('0.00')
    fd = _parse_fecha_filtro(fecha_desde)
    if fd is None:
        return Decimal('0.00')
    if fd <= FECHA_SALDO_INICIAL_CUENTA:
        return Decimal('0.00')
    qs_prev = _qs_movimientos_cuenta(sucursal, destino).filter(
        fecha_banco__gte=FECHA_SALDO_INICIAL_CUENTA,
        fecha_banco__lt=fd,
    )
    return (saldo_si + _neto_movimientos_cuenta(qs_prev)).quantize(Decimal('0.01'))


def _etiqueta_inquilino_movimiento(m: MovimientoCaja) -> str:
    """Apellido, nombre del inquilino vinculado a operación o contrato."""
    texto = (m.concepto or '')
    rid_m = re.search(r'Operaci[oó]n\s*#?\s*(\d+)', texto, re.I)
    if rid_m:
        from inmobiliaria.models.propiedad import Reserva

        r = Reserva.objects.select_related('cliente').filter(pk=int(rid_m.group(1))).first()
        if r and r.cliente:
            ap = (r.cliente.apellido or '').strip()
            no = (r.cliente.nombre or '').strip()
            partes = [p for p in (ap, no) if p]
            if partes:
                return ', '.join(partes)
    cid_m = re.search(r'[Cc]ontrato\s*#?\s*(\d+)', texto)
    if cid_m:
        from inmobiliaria.models.contrato import ContratoAlquiler

        c = ContratoAlquiler.objects.select_related('inquilino').filter(pk=int(cid_m.group(1))).first()
        if c and c.inquilino:
            ap = (c.inquilino.apellido or '').strip()
            no = (c.inquilino.nombre or '').strip()
            partes = [p for p in (ap, no) if p]
            if partes:
                return ', '.join(partes)
    return ''


def _concepto_detalle_es_contrato(concepto_detalle: str) -> bool:
    raw = (concepto_detalle or '').strip()
    if not raw.startswith('{'):
        return False
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    if isinstance(data.get('conceptos'), list) and len(data['conceptos']) > 0:
        return True
    if data.get('mes_alquiler_tipo') or data.get('mes_alquiler_importe') is not None:
        return True
    return False


def _reporte_cuenta_bancaria_movimiento_extras(m: MovimientoCaja) -> dict:
    """
    Etiqueta de operación (por día / contrato / liquidación) y textos de detalle para el reporte bancario.
    """
    MovimientoCaja.precargar_nombres_concepto([m], sucursal=getattr(m, 'sucursal', None))

    concepto = (m.concepto or '').strip()
    lc = concepto.lower()
    etiqueta = ''

    if _concepto_detalle_es_contrato(m.concepto_detalle):
        etiqueta = 'Contrato'
    elif re.search(r'\bcontrato\b|\bcuota\s+\d', lc) or 'mes de alquiler' in lc or 'mes alquiler' in lc:
        etiqueta = 'Contrato'
    elif re.search(
        r'reserva\s*#?\s*\d|operaci[oó]n\s*#?\s*\d|operacion\s*#?\s*\d|alquiler\s+por\s+d[ií]a',
        lc,
    ):
        etiqueta = 'Por día'
    elif 'liquidaci' in lc:
        etiqueta = 'Liquidación'
    elif (m.tipo_comprobante or '').strip().upper() == 'RC' and m.propiedad_id:
        try:
            if m.listado_concepto_l1 == 'ALQUILER A COBRAR':
                etiqueta = 'Contrato'
        except Exception:
            pass

    categoria = ''
    direccion = ''
    concepto_nombre = '—'
    observaciones = ''
    try:
        categoria = (m.listado_concepto_l1 or '').strip()
        direccion = (m.listado_concepto_l2 or '').strip()
        concepto_nombre = (m.listado_detalle_l1 or '').strip() or '—'
        obs = (m.listado_detalle_tabla_secundario or '').strip()
        observaciones = '' if obs == '—' else obs
    except Exception:
        concepto_nombre = (m.concepto or '')[:200] if m.concepto else '—'

    num_op = ''
    try:
        raw_num = m.numero_operacion_listado
        if raw_num and str(raw_num) != '0':
            num_op = str(raw_num)
    except Exception:
        pass

    inquilino = _etiqueta_inquilino_movimiento(m)
    op_line = ''
    if num_op:
        op_line = f'Op. {num_op}'
        if inquilino:
            op_line = f'{op_line} — {inquilino}'

    propiedad_direccion = ''
    if getattr(m, 'propiedad_id', None):
        try:
            prop = m.propiedad
            propiedad_direccion = (getattr(prop, 'direccion', None) or '').strip()
        except Exception:
            propiedad_direccion = ''
    if not direccion and propiedad_direccion:
        direccion = propiedad_direccion[:80]

    return {
        'etiqueta': etiqueta,
        'op_line': op_line,
        'categoria': categoria,
        'direccion': direccion,
        'concepto_nombre': concepto_nombre,
        'observaciones': observaciones,
        'detalle_l1': concepto_nombre,
        'detalle_l2': observaciones,
        'numero_operacion': num_op,
        'inquilino': inquilino,
        'propiedad_direccion': propiedad_direccion[:80] if propiedad_direccion else '',
    }


# ========================================
# GESTIÓN DE CUENTAS BANCARIAS
# ========================================

@login_required
def gestionar_cuentas_bancarias(request):
    """
    Vista para gestionar las cuentas bancarias de la sucursal
    """
    try:
        sucursal = request.user.sucursal
        cuentas = CuentaBancaria.objects.filter(sucursal=sucursal).order_by('nombre_banco', 'alias')
        
        context = {
            'sucursal': sucursal,
            'cuentas': cuentas,
        }
        
        return render(request, 'inmobiliaria/caja/gestionar_cuentas_bancarias.html', context)
        
    except Exception as e:
        messages.error(request, f'Error al acceder a las cuentas bancarias: {str(e)}')
        return redirect('inmobiliaria:dashboard_caja')

def _post_cuenta_bancaria_limpio(request):
    """Banco, titular y CBU/alias obligatorios; número de cuenta opcional."""
    nombre_banco = (request.POST.get('nombre_banco') or '').strip()
    titular = (request.POST.get('titular') or '').strip()
    alias = (request.POST.get('alias') or '').strip()
    numero_cuenta = (request.POST.get('numero_cuenta') or '').strip()
    return nombre_banco, titular, alias, numero_cuenta


@login_required
def crear_cuenta_bancaria(request):
    """
    Vista para crear una nueva cuenta bancaria
    """
    if request.method == 'POST':
        try:
            sucursal = request.user.sucursal
            nombre_banco, titular, alias, numero_cuenta = _post_cuenta_bancaria_limpio(request)
            if not nombre_banco:
                messages.error(request, 'El banco es obligatorio.')
                return redirect('inmobiliaria:crear_cuenta_bancaria')
            if not titular:
                messages.error(request, 'El titular es obligatorio.')
                return redirect('inmobiliaria:crear_cuenta_bancaria')
            if not alias:
                messages.error(request, 'El CBU o alias es obligatorio.')
                return redirect('inmobiliaria:crear_cuenta_bancaria')

            # Crear la cuenta bancaria
            cuenta = CuentaBancaria.objects.create(
                sucursal=sucursal,
                nombre_banco=nombre_banco,
                titular=titular,
                alias=alias,
                numero_cuenta=numero_cuenta,
                tipo_cuenta=request.POST.get('tipo_cuenta', 'banco'),
                activa=request.POST.get('activa') == 'on',
                saldo_inicial=_parse_saldo_inicial_post(request),
            )
            
            messages.success(request, f'Cuenta bancaria "{cuenta.nombre_banco}" creada exitosamente.')
            return redirect('inmobiliaria:gestionar_cuentas_bancarias')
            
        except Exception as e:
            messages.error(request, f'Error al crear la cuenta bancaria: {str(e)}')
            return redirect('inmobiliaria:gestionar_cuentas_bancarias')
    
    # GET - Mostrar formulario
    context = {
        'sucursal': request.user.sucursal,
    }
    return render(request, 'inmobiliaria/caja/crear_cuenta_bancaria.html', context)

@login_required
def editar_cuenta_bancaria(request, cuenta_id):
    """
    Vista para editar una cuenta bancaria existente
    """
    try:
        cuenta = get_object_or_404(CuentaBancaria, id=cuenta_id, sucursal=request.user.sucursal)
        
        if request.method == 'POST':
            nombre_banco, titular, alias, numero_cuenta = _post_cuenta_bancaria_limpio(request)
            if not nombre_banco:
                messages.error(request, 'El banco es obligatorio.')
                return redirect('inmobiliaria:editar_cuenta_bancaria', cuenta_id=cuenta_id)
            if not titular:
                messages.error(request, 'El titular es obligatorio.')
                return redirect('inmobiliaria:editar_cuenta_bancaria', cuenta_id=cuenta_id)
            if not alias:
                messages.error(request, 'El CBU o alias es obligatorio.')
                return redirect('inmobiliaria:editar_cuenta_bancaria', cuenta_id=cuenta_id)
            cuenta.nombre_banco = nombre_banco
            cuenta.titular = titular
            cuenta.alias = alias
            cuenta.numero_cuenta = numero_cuenta
            cuenta.tipo_cuenta = request.POST.get('tipo_cuenta', 'banco')
            cuenta.activa = request.POST.get('activa') == 'on'
            # saldo_inicial: corte fijo 05/06 — no se edita más desde acá
            cuenta.save()
            
            messages.success(request, f'Cuenta bancaria "{cuenta.nombre_banco}" actualizada exitosamente.')
            return redirect('inmobiliaria:gestionar_cuentas_bancarias')
        
        # GET - Mostrar formulario con datos actuales
        context = {
            'cuenta': cuenta,
            'sucursal': request.user.sucursal,
            'fecha_saldo_inicial': FECHA_SALDO_INICIAL_CUENTA,
        }
        return render(request, 'inmobiliaria/caja/editar_cuenta_bancaria.html', context)
        
    except Exception as e:
        messages.error(request, f'Error al editar la cuenta bancaria: {str(e)}')
        return redirect('inmobiliaria:gestionar_cuentas_bancarias')

@login_required
def eliminar_cuenta_bancaria(request, cuenta_id):
    """
    Vista para eliminar una cuenta bancaria
    """
    try:
        cuenta = get_object_or_404(CuentaBancaria, id=cuenta_id, sucursal=request.user.sucursal)
        nombre_cuenta = cuenta.nombre_banco
        cuenta.delete()
        
        messages.success(request, f'Cuenta bancaria "{nombre_cuenta}" eliminada exitosamente.')
        return redirect('inmobiliaria:gestionar_cuentas_bancarias')
        
    except Exception as e:
        messages.error(request, f'Error al eliminar la cuenta bancaria: {str(e)}')
        return redirect('inmobiliaria:gestionar_cuentas_bancarias')

@login_required
def toggle_cuenta_bancaria(request, cuenta_id):
    """
    Vista AJAX para activar/desactivar una cuenta bancaria
    """
    try:
        cuenta = get_object_or_404(CuentaBancaria, id=cuenta_id, sucursal=request.user.sucursal)
        cuenta.activa = not cuenta.activa
        cuenta.save()
        
        return JsonResponse({
            'success': True,
            'activa': cuenta.activa,
            'message': f'Cuenta {"activada" if cuenta.activa else "desactivada"} exitosamente'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
def reporte_movimientos_cuenta_bancaria(request, cuenta_id):
    """
    Listado tipo reporte: ingresos y egresos con transferencia/deposito a esta cuenta bancaria
    (destino_deposito = cuenta_<id>, monto_deposito > 0), filtrable por rango de fechas.
    El saldo inicial cuenta como del 05/06/2026 (corte fijo) y no se edita desde el reporte.
    """
    cuenta = get_object_or_404(CuentaBancaria, id=cuenta_id, sucursal=request.user.sucursal)
    destino = f'cuenta_{cuenta.id}'

    modo_imprimir = request.GET.get('imprimir') == '1'

    movimientos_qs = (
        MovimientoCaja.objects.filter(
            sucursal=request.user.sucursal,
            destino_deposito=destino,
            monto_deposito__gt=0,
        )
        .select_related('caja', 'empleado', 'propiedad')
        .annotate(fecha_banco=Coalesce(F('fecha_transferencia'), TruncDate('fecha')))
        .order_by('-fecha_banco', '-fecha', '-id')
    )

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

    if not periodo_completo:
        if fecha_desde:
            movimientos_qs = movimientos_qs.filter(fecha_banco__gte=fecha_desde)
        if fecha_hasta:
            movimientos_qs = movimientos_qs.filter(fecha_banco__lte=fecha_hasta)

    total_ingresos = (
        movimientos_qs.filter(tipo=TipoMovimientoCajaEnum.INGRESO).aggregate(
            t=Sum('monto_deposito')
        )['t']
        or Decimal('0')
    )
    total_egresos = (
        movimientos_qs.filter(tipo=TipoMovimientoCajaEnum.EGRESO).aggregate(
            t=Sum('monto_deposito')
        )['t']
        or Decimal('0')
    )
    saldo_periodo = total_ingresos - total_egresos

    saldo_inicial = Decimal(str(cuenta.saldo_inicial or 0)).quantize(Decimal('0.01'))
    aplica_si = _saldo_inicial_en_periodo(fecha_desde, fecha_hasta, periodo_completo)
    mostrar_fila_si = (
        aplica_si
        and saldo_inicial != 0
        and _mostrar_fila_saldo_inicial(fecha_desde, fecha_hasta, periodo_completo)
    )
    saldo_base = _saldo_apertura_periodo(
        cuenta,
        request.user.sucursal,
        destino,
        fecha_desde,
        fecha_hasta,
        periodo_completo,
    )
    fd_filtro = _parse_fecha_filtro(fecha_desde)
    mostrar_fila_transporte = (
        not periodo_completo
        and not mostrar_fila_si
        and fd_filtro is not None
        and fd_filtro > FECHA_SALDO_INICIAL_CUENTA
    )

    cronologicos = list(movimientos_qs.order_by('fecha_banco', 'fecha', 'id'))
    saldo_run = saldo_base
    saldos_por_id = {}
    saldo_despues_fila_inicial = None
    if mostrar_fila_si:
        saldo_run = (saldo_run + saldo_inicial).quantize(Decimal('0.01'))
        saldo_despues_fila_inicial = saldo_run
    for mov in cronologicos:
        monto = Decimal(str(mov.monto_deposito or 0))
        if (mov.tipo or '').strip().upper() == TipoMovimientoCajaEnum.INGRESO:
            saldo_run += monto
        else:
            saldo_run -= monto
        saldos_por_id[mov.id] = saldo_run.quantize(Decimal('0.01'))

    # Resumen: saldo inicial del corte solo si el 05/06 está en el rango.
    saldo_inicial_resumen = saldo_inicial if mostrar_fila_si else Decimal('0.00')
    saldo_final = saldo_run.quantize(Decimal('0.01')) if (
        cronologicos or mostrar_fila_si
    ) else saldo_base

    query_params = request.GET.copy()
    query_params.pop('page', None)
    query_params.pop('imprimir', None)
    if periodo_completo:
        query_params['todo'] = '1'
        query_params.pop('fecha_desde', None)
        query_params.pop('fecha_hasta', None)
    else:
        query_params.pop('todo', None)
        if fecha_desde:
            query_params['fecha_desde'] = fecha_desde
        if fecha_hasta:
            query_params['fecha_hasta'] = fecha_hasta

    query_imprimir = query_params.copy()
    query_imprimir['imprimir'] = '1'

    context_extra = {
        'saldo_inicial_cuenta': saldo_inicial,
        'saldo_inicial_resumen': saldo_inicial_resumen,
        'saldo_base_periodo': saldo_base,
        'saldo_transporte': saldo_base,
        'saldo_periodo': saldo_periodo,
        'saldo_final': saldo_final,
        'saldo_transferencias': saldo_final,
        'fecha_saldo_inicial': FECHA_SALDO_INICIAL_CUENTA,
        'mostrar_fila_saldo_inicial': mostrar_fila_si,
        'mostrar_fila_transporte': mostrar_fila_transporte,
        'saldo_acumulado_inicial': saldo_despues_fila_inicial,
        'saldo_inicial_aplica_periodo': mostrar_fila_si,
    }

    if modo_imprimir:
        for mov in cronologicos:
            mov.reporte_bc_extra = _reporte_cuenta_bancaria_movimiento_extras(mov)
            mov.saldo_acumulado = saldos_por_id.get(mov.id, saldo_base)
        return render(
            request,
            'inmobiliaria/caja/reporte_cuenta_bancaria_imprimir.html',
            {
                'cuenta': cuenta,
                'sucursal': request.user.sucursal,
                'movimientos': cronologicos,
                'total_ingresos': total_ingresos,
                'total_egresos': total_egresos,
                'cantidad_movimientos': len(cronologicos),
                'fecha_desde': fecha_desde if not periodo_completo else '',
                'fecha_hasta': fecha_hasta if not periodo_completo else '',
                'periodo_completo': periodo_completo,
                'querystring': query_params.urlencode(),
                **context_extra,
            },
        )

    paginator = Paginator(movimientos_qs, 50)
    page = paginator.get_page(request.GET.get('page'))
    for mov in page.object_list:
        mov.reporte_bc_extra = _reporte_cuenta_bancaria_movimiento_extras(mov)
        mov.saldo_acumulado = saldos_por_id.get(mov.id, saldo_base)

    return render(
        request,
        'inmobiliaria/caja/reporte_cuenta_bancaria.html',
        {
            'cuenta': cuenta,
            'sucursal': request.user.sucursal,
            'movimientos': page,
            'total_ingresos': total_ingresos,
            'total_egresos': total_egresos,
            'cantidad_movimientos': movimientos_qs.count(),
            'fecha_desde': fecha_desde if not periodo_completo else '',
            'fecha_hasta': fecha_hasta if not periodo_completo else '',
            'querystring': query_params.urlencode(),
            'querystring_imprimir': query_imprimir.urlencode(),
            'periodo_completo': periodo_completo,
            **context_extra,
        },
    )
