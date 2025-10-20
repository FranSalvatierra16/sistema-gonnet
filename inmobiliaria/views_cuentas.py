# ================================
# GESTIÓN DE CUENTAS BANCARIAS
# ================================

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Max
from .models import CuentaBancaria

@login_required
def gestionar_cuentas_bancarias(request):
    """Vista para gestionar las cuentas bancarias de la sucursal"""
    cuentas = CuentaBancaria.objects.filter(sucursal=request.user.sucursal).order_by('orden', 'nombre')
    
    context = {
        'cuentas': cuentas,
        'sucursal': request.user.sucursal,
    }
    
    return render(request, 'inmobiliaria/configuracion/cuentas_bancarias.html', context)


@login_required
def agregar_cuenta_bancaria(request):
    """Vista para agregar una nueva cuenta bancaria"""
    if request.method == 'POST':
        try:
            nombre = request.POST.get('nombre', '').strip()
            tipo = request.POST.get('tipo', 'banco')
            numero_cuenta = request.POST.get('numero_cuenta', '').strip()
            cbu_alias = request.POST.get('cbu_alias', '').strip()
            
            if not nombre:
                return JsonResponse({'error': 'El nombre de la cuenta es requerido'}, status=400)
            
            # Verificar que no exista una cuenta con el mismo nombre
            if CuentaBancaria.objects.filter(sucursal=request.user.sucursal, nombre=nombre).exists():
                return JsonResponse({'error': f'Ya existe una cuenta con el nombre "{nombre}"'}, status=400)
            
            # Obtener el próximo orden
            ultimo_orden = CuentaBancaria.objects.filter(sucursal=request.user.sucursal).aggregate(
                max_orden=Max('orden')
            )['max_orden'] or 0
            
            # Crear la cuenta
            cuenta = CuentaBancaria.objects.create(
                sucursal=request.user.sucursal,
                nombre=nombre,
                tipo=tipo,
                numero_cuenta=numero_cuenta if numero_cuenta else None,
                cbu_alias=cbu_alias if cbu_alias else None,
                orden=ultimo_orden + 1,
                activa=True
            )
            
            return JsonResponse({
                'success': True,
                'cuenta': {
                    'id': cuenta.id,
                    'nombre': cuenta.nombre,
                    'tipo': cuenta.get_tipo_display(),
                    'numero_cuenta': cuenta.numero_cuenta or '',
                    'cbu_alias': cuenta.cbu_alias or '',
                    'activa': cuenta.activa
                }
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)


@login_required
def editar_cuenta_bancaria(request, cuenta_id):
    """Vista para editar una cuenta bancaria"""
    try:
        cuenta = get_object_or_404(CuentaBancaria, id=cuenta_id, sucursal=request.user.sucursal)
        
        if request.method == 'POST':
            nombre = request.POST.get('nombre', '').strip()
            tipo = request.POST.get('tipo', 'banco')
            numero_cuenta = request.POST.get('numero_cuenta', '').strip()
            cbu_alias = request.POST.get('cbu_alias', '').strip()
            activa = request.POST.get('activa') == 'true'
            
            if not nombre:
                return JsonResponse({'error': 'El nombre de la cuenta es requerido'}, status=400)
            
            # Verificar que no exista otra cuenta con el mismo nombre
            if CuentaBancaria.objects.filter(
                sucursal=request.user.sucursal, 
                nombre=nombre
            ).exclude(id=cuenta_id).exists():
                return JsonResponse({'error': f'Ya existe otra cuenta con el nombre "{nombre}"'}, status=400)
            
            # Actualizar la cuenta
            cuenta.nombre = nombre
            cuenta.tipo = tipo
            cuenta.numero_cuenta = numero_cuenta if numero_cuenta else None
            cuenta.cbu_alias = cbu_alias if cbu_alias else None
            cuenta.activa = activa
            cuenta.save()
            
            return JsonResponse({
                'success': True,
                'cuenta': {
                    'id': cuenta.id,
                    'nombre': cuenta.nombre,
                    'tipo': cuenta.get_tipo_display(),
                    'numero_cuenta': cuenta.numero_cuenta or '',
                    'cbu_alias': cuenta.cbu_alias or '',
                    'activa': cuenta.activa
                }
            })
        
        # GET request - devolver datos de la cuenta
        return JsonResponse({
            'cuenta': {
                'id': cuenta.id,
                'nombre': cuenta.nombre,
                'tipo': cuenta.tipo,
                'numero_cuenta': cuenta.numero_cuenta or '',
                'cbu_alias': cuenta.cbu_alias or '',
                'activa': cuenta.activa
            }
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def eliminar_cuenta_bancaria(request, cuenta_id):
    """Vista para eliminar una cuenta bancaria"""
    if request.method == 'POST':
        try:
            cuenta = get_object_or_404(CuentaBancaria, id=cuenta_id, sucursal=request.user.sucursal)
            
            # Verificar que no sea una cuenta por defecto crítica
            if cuenta.nombre.lower() in ['efectivo']:
                return JsonResponse({'error': 'No se puede eliminar esta cuenta'}, status=400)
            
            nombre_cuenta = cuenta.nombre
            cuenta.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'Cuenta "{nombre_cuenta}" eliminada correctamente'
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)


@login_required
def obtener_cuentas_bancarias_activas(request):
    """Vista para obtener las cuentas bancarias activas de la sucursal (para formularios)"""
    cuentas = CuentaBancaria.objects.filter(
        sucursal=request.user.sucursal,
        activa=True
    ).order_by('orden', 'nombre')
    
    cuentas_data = []
    for cuenta in cuentas:
        cuentas_data.append({
            'id': cuenta.id,
            'nombre': cuenta.nombre,
            'tipo': cuenta.tipo,
            'field_name': f'monto_{cuenta.nombre.lower().replace(" ", "_")}'
        })
    
    return JsonResponse({'cuentas': cuentas_data})
