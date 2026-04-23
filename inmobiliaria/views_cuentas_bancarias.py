from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from inmobiliaria.models.caja import MovimientoCaja, TipoMovimientoCajaEnum
from inmobiliaria.models.sucursal import CuentaBancaria


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

    fecha_desde = request.GET.get('fecha_desde', '').strip()
    fecha_hasta = request.GET.get('fecha_hasta', '').strip()
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

    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']

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
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'querystring': query_params.urlencode(),
        },
    )
