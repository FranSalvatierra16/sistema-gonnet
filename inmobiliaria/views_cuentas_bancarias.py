import json
import re
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from inmobiliaria.models.caja import MovimientoCaja, TipoMovimientoCajaEnum
from inmobiliaria.models.sucursal import CuentaBancaria


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

    detalle_l1 = ''
    detalle_l2 = ''
    try:
        detalle_l1 = (m.listado_detalle_l1 or '').strip()
        detalle_l2 = (m.listado_detalle_l2 or '').strip()
    except Exception:
        detalle_l1 = (m.concepto or '')[:200] if m.concepto else '—'
        detalle_l2 = ''

    if detalle_l2 in ('—', ''):
        detalle_l2 = ''

    num_op = ''
    try:
        raw_num = m.numero_operacion_listado
        if raw_num and str(raw_num) != '0':
            num_op = str(raw_num)
    except Exception:
        pass

    propiedad_direccion = ''
    if getattr(m, 'propiedad_id', None):
        try:
            prop = m.propiedad
            propiedad_direccion = (getattr(prop, 'direccion', None) or '').strip()
        except Exception:
            propiedad_direccion = ''

    return {
        'etiqueta': etiqueta,
        'detalle_l1': detalle_l1 or '—',
        'detalle_l2': detalle_l2,
        'numero_operacion': num_op,
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

@login_required
def crear_cuenta_bancaria(request):
    """
    Vista para crear una nueva cuenta bancaria
    """
    if request.method == 'POST':
        try:
            sucursal = request.user.sucursal
            
            # Crear la cuenta bancaria
            cuenta = CuentaBancaria.objects.create(
                sucursal=sucursal,
                nombre_banco=request.POST.get('nombre_banco'),
                alias=request.POST.get('alias'),
                numero_cuenta=request.POST.get('numero_cuenta'),
                tipo_cuenta=request.POST.get('tipo_cuenta', 'banco'),
                activa=request.POST.get('activa') == 'on'
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
            # Actualizar la cuenta bancaria
            cuenta.nombre_banco = request.POST.get('nombre_banco')
            cuenta.alias = request.POST.get('alias')
            cuenta.numero_cuenta = request.POST.get('numero_cuenta')
            cuenta.tipo_cuenta = request.POST.get('tipo_cuenta', 'banco')
            cuenta.activa = request.POST.get('activa') == 'on'
            cuenta.save()
            
            messages.success(request, f'Cuenta bancaria "{cuenta.nombre_banco}" actualizada exitosamente.')
            return redirect('inmobiliaria:gestionar_cuentas_bancarias')
        
        # GET - Mostrar formulario con datos actuales
        context = {
            'cuenta': cuenta,
            'sucursal': request.user.sucursal,
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
    """
    cuenta = get_object_or_404(CuentaBancaria, id=cuenta_id, sucursal=request.user.sucursal)
    destino = f'cuenta_{cuenta.id}'

    movimientos_qs = (
        MovimientoCaja.objects.filter(
            sucursal=request.user.sucursal,
            destino_deposito=destino,
            monto_deposito__gt=0,
        )
        .select_related('caja', 'empleado', 'propiedad')
        .order_by('-fecha', '-id')
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
            movimientos_qs = movimientos_qs.filter(fecha__date__gte=fecha_desde)
        if fecha_hasta:
            movimientos_qs = movimientos_qs.filter(fecha__date__lte=fecha_hasta)

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
    saldo_transferencias = total_ingresos - total_egresos

    paginator = Paginator(movimientos_qs, 50)
    page = paginator.get_page(request.GET.get('page'))
    for mov in page.object_list:
        mov.reporte_bc_extra = _reporte_cuenta_bancaria_movimiento_extras(mov)

    query_params = request.GET.copy()
    query_params.pop('page', None)
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

    return render(
        request,
        'inmobiliaria/caja/reporte_cuenta_bancaria.html',
        {
            'cuenta': cuenta,
            'sucursal': request.user.sucursal,
            'movimientos': page,
            'total_ingresos': total_ingresos,
            'total_egresos': total_egresos,
            'saldo_transferencias': saldo_transferencias,
            'cantidad_movimientos': movimientos_qs.count(),
            'fecha_desde': fecha_desde if not periodo_completo else '',
            'fecha_hasta': fecha_hasta if not periodo_completo else '',
            'querystring': query_params.urlencode(),
            'periodo_completo': periodo_completo,
        },
    )
