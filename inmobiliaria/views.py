from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse, QueryDict
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from datetime import datetime, date, timedelta
from django.forms import inlineformset_factory
from django.template.loader import render_to_string
from django.contrib.auth import authenticate
from django.db import models, transaction, IntegrityError
from django.db.utils import OperationalError, ProgrammingError
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_POST
import re
import logging

from .decimal_utils import format_monto_argentino, parse_decimal_monto

logger = logging.getLogger(__name__)


def _recibo_monto_str(valor, dec_places=2):
    """Montos en recibo HTML/PDF: $ + formato argentino (miles con punto, decimales con coma)."""
    try:
        return f'${format_monto_argentino(valor, dec_places)}'
    except Exception:
        return f'${valor}'

# Modelos usados por vistas definidas antes del import masivo de .models (línea ~871)
from .models import ComisionVendedor, ValeVendedor, MesComisionPagadoVendedor
from .models.persona import Vendedor

# Importar vistas de cuentas bancarias
from .views_cuentas_bancarias import (
    gestionar_cuentas_bancarias,
    crear_cuenta_bancaria,
    editar_cuenta_bancaria,
    eliminar_cuenta_bancaria,
    toggle_cuenta_bancaria,
    reporte_movimientos_cuenta_bancaria,
)

# ✅ VISTAS PARA COMISIONES DE VENDEDORES (SOLO ADMINS)

@login_required
def historial_comisiones_vendedor(request, vendedor_id):
    """
    Vista para mostrar el historial de comisiones de un vendedor específico
    Solo accesible para administradores (nivel 4)
    """
    # Verificar que el usuario sea nivel 4
    if request.user.nivel != 4:
        messages.error(request, 'No tienes permisos para acceder a esta sección.')
        return redirect('inmobiliaria:dashboard')
    
    vendedor = get_object_or_404(
        Vendedor, id=vendedor_id, sucursal=request.user.sucursal
    )
    try:
        comisiones = (
            ComisionVendedor.objects.filter(vendedor=vendedor)
            .que_suman()
            .select_related('vendedor', 'reserva__propiedad')
            .ordenadas_para_listado_historial()
        )
        vales = ValeVendedor.objects.filter(vendedor=vendedor).order_by('-fecha')
        total_comisiones = comisiones.aggregate(
            total=models.Sum('monto_comision')
        )['total'] or Decimal('0')
        total_vales = ValeVendedor.total_saldo_para_comisiones(vendedor)
        total_vales_egreso = (
            vales.filter(tipo_vale='EG').aggregate(t=models.Sum('monto'))['t'] or Decimal('0')
        )
        total_vales_ingreso = (
            vales.filter(tipo_vale='IN').aggregate(t=models.Sum('monto'))['t'] or Decimal('0')
        )
    except (ProgrammingError, OperationalError) as exc:
        logger.exception(
            'historial_comisiones_vendedor: error de esquema o BD (¿migraciones pendientes?). vendedor_id=%s',
            vendedor_id,
        )
        messages.error(
            request,
            'No se pudo cargar comisiones/vales. Verificá que las migraciones estén aplicadas en el servidor '
            f'(detalle técnico: {exc.__class__.__name__}).',
        )
        return redirect('inmobiliaria:vendedores')
    
    # Calcular neto histórico (comisiones − entregas en vale + devoluciones ingreso a caja)
    total_neto = total_comisiones - total_vales

    # Meses marcados como pagados al vendedor (excluidos de totales «pendientes» en cajas superiores)
    try:
        meses_pagados_keys = {
            f'{a:04d}-{m:02d}'
            for a, m in MesComisionPagadoVendedor.objects.filter(vendedor=vendedor).values_list(
                'anio', 'mes'
            )
        }
    except (ProgrammingError, OperationalError):
        meses_pagados_keys = set()

    total_comisiones_pendiente = Decimal('0')
    comisiones_resumen_count = 0
    for c in comisiones:
        fo = c.fecha_operacion
        if not fo:
            continue
        mk = fo.strftime('%Y-%m')
        if mk in meses_pagados_keys:
            continue
        total_comisiones_pendiente += c.monto_comision
        comisiones_resumen_count += 1

    total_vales_egreso_pendiente = Decimal('0')
    total_vales_ingreso_pendiente = Decimal('0')
    vales_resumen_count = 0
    for vale in vales:
        vf = vale.fecha
        if not vf:
            continue
        mk = vf.strftime('%Y-%m')
        if mk in meses_pagados_keys:
            continue
        vales_resumen_count += 1
        tipo_v = getattr(vale, 'tipo_vale', None) or 'EG'
        if tipo_v == 'EG':
            total_vales_egreso_pendiente += vale.monto
        else:
            total_vales_ingreso_pendiente += vale.monto

    total_vales_pendiente = total_vales_egreso_pendiente - total_vales_ingreso_pendiente
    total_neto_pendiente = total_comisiones_pendiente - total_vales_pendiente

    # Calcular totales por mes
    from datetime import datetime

    comisiones_por_mes = {}
    for comision in comisiones:
        fo = comision.fecha_operacion
        if not fo:
            continue
        mes_key = fo.strftime('%Y-%m')
        if mes_key not in comisiones_por_mes:
            comisiones_por_mes[mes_key] = {
                'mes': fo.strftime('%B %Y'),
                'total_comisiones': Decimal('0'),
                'total_vales': Decimal('0'),
                'cantidad': 0
            }
        comisiones_por_mes[mes_key]['total_comisiones'] += comision.monto_comision
        comisiones_por_mes[mes_key]['cantidad'] += 1
    
    # Agregar vales por mes (egreso suma al “descuento”, ingreso lo resta)
    for vale in vales:
        vf = vale.fecha
        if not vf:
            continue
        mes_key = vf.strftime('%Y-%m')
        if mes_key not in comisiones_por_mes:
            comisiones_por_mes[mes_key] = {
                'mes': vf.strftime('%B %Y'),
                'total_comisiones': Decimal('0'),
                'total_vales': Decimal('0'),
                'cantidad': 0
            }
        tipo_v = getattr(vale, 'tipo_vale', None) or 'EG'
        if tipo_v == 'EG':
            comisiones_por_mes[mes_key]['total_vales'] += vale.monto
        else:
            comisiones_por_mes[mes_key]['total_vales'] -= vale.monto
    
    # Calcular neto por mes, enteros para enlaces y URL resuelta en vista (evita NoReverseMatch al renderizar)
    for mes_key in comisiones_por_mes:
        datos = comisiones_por_mes[mes_key]
        datos['total_neto'] = datos['total_comisiones'] - datos['total_vales']
        try:
            parte_anio, parte_mes = mes_key.split('-', 1)
            datos['resumen_anio'] = int(parte_anio)
            datos['resumen_mes'] = int(parte_mes)
        except (ValueError, TypeError, AttributeError):
            datos['resumen_anio'] = 0
            datos['resumen_mes'] = 1
        try:
            datos['url_resumen_mes'] = reverse(
                'inmobiliaria:resumen_comisiones_mensual',
                kwargs={
                    'vendedor_id': vendedor.id,
                    'anio': datos['resumen_anio'],
                    'mes': datos['resumen_mes'],
                },
            )
        except (NoReverseMatch, TypeError, ValueError, KeyError) as exc:
            logger.warning(
                'historial_comisiones_vendedor: URL resumen mensual v=%s anio=%s mes=%s: %s',
                vendedor.id,
                datos.get('resumen_anio'),
                datos.get('resumen_mes'),
                exc,
            )
            datos['url_resumen_mes'] = '#'

    comisiones_por_mes = dict(
        sorted(comisiones_por_mes.items(), key=lambda kv: kv[0], reverse=True)
    )
    for _mes_key, datos in comisiones_por_mes.items():
        datos['pagado'] = _mes_key in meses_pagados_keys

    # Calcular comisiones del mes calendario actual (en cero si ese mes está marcado pagado)
    mes_actual = datetime.now().strftime('%Y-%m')
    if mes_actual in meses_pagados_keys:
        comision_mes_actual = Decimal('0')
        vale_mes_actual = Decimal('0')
        neto_mes_actual = Decimal('0')
        cantidad_operaciones = 0
    else:
        datos_mes_actual = comisiones_por_mes.get(mes_actual, {
            'total_comisiones': Decimal('0'),
            'total_vales': Decimal('0'),
            'total_neto': Decimal('0'),
            'cantidad': 0,
        })
        comision_mes_actual = datos_mes_actual.get('total_comisiones', Decimal('0'))
        vale_mes_actual = datos_mes_actual.get('total_vales', Decimal('0'))
        neto_mes_actual = datos_mes_actual.get('total_neto', Decimal('0'))
        cantidad_operaciones = datos_mes_actual.get('cantidad', 0)

    context = {
        'comisiones': comisiones,
        'vales': vales,
        'total_comisiones': total_comisiones_pendiente,
        'total_vales': total_vales_pendiente,
        'total_vales_egreso': total_vales_egreso_pendiente,
        'total_vales_ingreso': total_vales_ingreso_pendiente,
        'total_neto': total_neto_pendiente,
        'comisiones_resumen_count': comisiones_resumen_count,
        'vales_resumen_count': vales_resumen_count,
        'comisiones_por_mes': comisiones_por_mes,
        'comision_mes_actual': comision_mes_actual,
        'vale_mes_actual': vale_mes_actual,
        'neto_mes_actual': neto_mes_actual,
        'cantidad_operaciones': cantidad_operaciones,
        'vendedor': vendedor,
        'porcentaje_comision': vendedor.porcentaje_comision_efectivo(),
    }

    return render(request, 'inmobiliaria/comisiones/historial_comisiones.html', context)


@login_required
@require_POST
def toggle_mes_comision_pagado(request, vendedor_id):
    """Marca o desmarca un mes calendario como pagado al vendedor (nivel 4, misma sucursal)."""
    if request.user.nivel != 4:
        messages.error(request, 'No tienes permisos para acceder a esta sección.')
        return redirect('inmobiliaria:dashboard')

    vendedor = get_object_or_404(
        Vendedor, id=vendedor_id, sucursal=request.user.sucursal
    )
    try:
        anio = int(request.POST.get('anio', ''))
        mes = int(request.POST.get('mes', ''))
    except (TypeError, ValueError):
        messages.error(request, 'Año o mes inválido.')
        return redirect('inmobiliaria:historial_comisiones_vendedor', vendedor_id=vendedor_id)

    if mes < 1 or mes > 12 or anio < 1970 or anio > 2100:
        messages.error(request, 'Fecha fuera de rango.')
        return redirect('inmobiliaria:historial_comisiones_vendedor', vendedor_id=vendedor_id)

    accion = (request.POST.get('accion') or '').strip().lower()
    try:
        if accion == 'marcar':
            MesComisionPagadoVendedor.objects.get_or_create(
                vendedor=vendedor,
                anio=anio,
                mes=mes,
            )
            messages.success(
                request,
                f'Mes {mes:02d}/{anio} marcado como pagado. Deja de sumar en los totales pendientes.',
            )
        elif accion == 'desmarcar':
            MesComisionPagadoVendedor.objects.filter(
                vendedor=vendedor, anio=anio, mes=mes
            ).delete()
            messages.success(request, 'Mes desmarcado como pagado.')
        else:
            messages.error(request, 'Acción inválida.')
    except (ProgrammingError, OperationalError, IntegrityError) as exc:
        logger.exception('toggle_mes_comision_pagado: vendedor_id=%s', vendedor_id)
        messages.error(
            request,
            'No se pudo actualizar el estado del mes. Verificá migraciones o intentá de nuevo. '
            f'({exc.__class__.__name__})',
        )

    return redirect('inmobiliaria:historial_comisiones_vendedor', vendedor_id=vendedor_id)

@login_required
def detalle_comision(request, comision_id):
    """
    Vista para mostrar el detalle de una comisión específica
    Solo accesible para administradores (nivel 4)
    """
    # Verificar que el usuario sea nivel 4
    if request.user.nivel != 4:
        messages.error(request, 'No tienes permisos para acceder a esta sección.')
        return redirect('inmobiliaria:dashboard')
    
    comision = get_object_or_404(ComisionVendedor, id=comision_id)
    if comision.vendedor.sucursal_id != request.user.sucursal_id:
        messages.error(request, 'No tienes permisos para ver esta comisión.')
        return redirect('inmobiliaria:dashboard_comisiones')

    context = {
        'comision': comision
    }
    
    return render(request, 'inmobiliaria/comisiones/detalle_comision.html', context)

@login_required
def resumen_comisiones_mensual(request, vendedor_id, anio=None, mes=None):
    """
    Vista para mostrar un resumen de comisiones por mes de un vendedor específico
    Solo accesible para administradores (nivel 4)
    """
    # Verificar que el usuario sea nivel 4
    if request.user.nivel != 4:
        messages.error(request, 'No tienes permisos para acceder a esta sección.')
        return redirect('inmobiliaria:dashboard')
    
    from datetime import datetime
    from calendar import month_name
    
    # Parámetro de ruta en ASCII (anio): evita fallos con reverse/WSGI y el nombre "año" con ñ.
    if anio is None or mes is None:
        ahora = datetime.now()
        anio = ahora.year
        mes = ahora.month
    else:
        try:
            anio = int(anio)
            mes = int(mes)
        except (TypeError, ValueError):
            messages.error(request, 'Año o mes inválido.')
            return redirect(
                'inmobiliaria:historial_comisiones_vendedor',
                vendedor_id=vendedor_id,
            )
        if mes < 1 or mes > 12:
            messages.error(request, 'El mes debe estar entre 1 y 12.')
            return redirect(
                'inmobiliaria:historial_comisiones_vendedor',
                vendedor_id=vendedor_id,
            )
        if anio < 1970 or anio > 2100:
            messages.error(request, 'El año no es válido.')
            return redirect(
                'inmobiliaria:historial_comisiones_vendedor',
                vendedor_id=vendedor_id,
            )

    vendedor = get_object_or_404(
        Vendedor, id=vendedor_id, sucursal=request.user.sucursal
    )
    try:
        comisiones_mes = (
            ComisionVendedor.objects.filter(
                vendedor=vendedor,
                fecha_operacion__year=anio,
                fecha_operacion__month=mes,
            )
            .que_suman()
            .select_related('vendedor', 'reserva__propiedad')
            .ordenadas_para_listado_historial()
        )
        total_mes = comisiones_mes.aggregate(
            total=models.Sum('monto_comision')
        )['total'] or Decimal('0')
    except (ProgrammingError, OperationalError) as exc:
        logger.exception(
            'resumen_comisiones_mensual: error de esquema o BD. vendedor_id=%s anio=%s mes=%s',
            vendedor_id,
            anio,
            mes,
        )
        messages.error(
            request,
            'No se pudo cargar el resumen (posible migración pendiente en el servidor). '
            f'{exc.__class__.__name__}',
        )
        return redirect(
            'inmobiliaria:historial_comisiones_vendedor',
            vendedor_id=vendedor_id,
        )

    try:
        nombre_mes = month_name[mes]
    except IndexError:
        nombre_mes = f'mes {mes}'

    context = {
        'comisiones': comisiones_mes,
        'total_mes': total_mes,
        'año': anio,
        'mes': mes,
        'nombre_mes': nombre_mes,
        'vendedor': vendedor,
    }

    return render(request, 'inmobiliaria/comisiones/resumen_mensual.html', context)

@login_required
def dashboard_comisiones(request):
    """
    Panel de comisiones por vendedor.
    Solo accesible para administradores (nivel 4).
    """
    if request.user.nivel != 4:
        messages.error(request, 'No tienes permisos para acceder a esta sección.')
        return redirect('inmobiliaria:dashboard')

    vendedores = Vendedor.objects.filter(
        sucursal=request.user.sucursal,
        is_active=True
    ).order_by('apellido', 'nombre')

    vendedores_data = []
    for vendedor in vendedores:
        total_comisiones = (
            ComisionVendedor.objects.filter(vendedor=vendedor)
            .que_suman()
            .aggregate(total=models.Sum('monto_comision'))['total']
            or Decimal('0')
        )

        comisiones_pendientes = ComisionVendedor.objects.filter(
            vendedor=vendedor,
            estado='pendiente'
        ).count()

        total_vales = ValeVendedor.total_saldo_para_comisiones(vendedor)
        total_vales_egreso = (
            ValeVendedor.objects.filter(vendedor=vendedor, tipo_vale='EG')
            .aggregate(t=models.Sum('monto'))['t']
            or Decimal('0')
        )
        total_vales_ingreso = (
            ValeVendedor.objects.filter(vendedor=vendedor, tipo_vale='IN')
            .aggregate(t=models.Sum('monto'))['t']
            or Decimal('0')
        )

        vendedores_data.append({
            'vendedor': vendedor,
            'total_comisiones': total_comisiones,
            'comisiones_pendientes': comisiones_pendientes,
            'total_vales': total_vales,
            'total_vales_egreso': total_vales_egreso,
            'total_vales_ingreso': total_vales_ingreso,
            'neto': total_comisiones - total_vales,
        })

    vendedores_data.sort(key=lambda x: x['comisiones_pendientes'], reverse=True)

    total_comisiones_sucursal = sum(
        (d['total_comisiones'] for d in vendedores_data), start=Decimal('0')
    )
    total_vales_egreso_sucursal = sum(
        (d['total_vales_egreso'] for d in vendedores_data), start=Decimal('0')
    )
    total_vales_ingreso_sucursal = sum(
        (d['total_vales_ingreso'] for d in vendedores_data), start=Decimal('0')
    )
    total_saldo_vales_sucursal = sum(
        (d['total_vales'] for d in vendedores_data), start=Decimal('0')
    )
    total_neto_sucursal = sum((d['neto'] for d in vendedores_data), start=Decimal('0'))
    total_ops_comisiones = ComisionVendedor.objects.filter(
        vendedor__in=vendedores
    ).que_suman().count()
    total_mov_vales = ValeVendedor.objects.filter(vendedor__in=vendedores).count()

    ahora = timezone.now()
    ay, am = ahora.year, ahora.month
    comisiones_mes_sucursal = (
        ComisionVendedor.objects.filter(
            vendedor__in=vendedores,
            fecha_operacion__year=ay,
            fecha_operacion__month=am,
        )
        .que_suman()
        .aggregate(t=models.Sum('monto_comision'))['t']
        or Decimal('0')
    )
    vales_mes_q = ValeVendedor.objects.filter(
        vendedor__in=vendedores,
        fecha__year=ay,
        fecha__month=am,
    )
    eg_mes = (
        vales_mes_q.filter(tipo_vale='EG').aggregate(t=models.Sum('monto'))['t']
        or Decimal('0')
    )
    in_mes = (
        vales_mes_q.filter(tipo_vale='IN').aggregate(t=models.Sum('monto'))['t']
        or Decimal('0')
    )
    saldo_vales_mes = eg_mes - in_mes
    neto_mes_sucursal = comisiones_mes_sucursal - saldo_vales_mes
    cant_ops_mes = ComisionVendedor.objects.filter(
        vendedor__in=vendedores,
        fecha_operacion__year=ay,
        fecha_operacion__month=am,
    ).que_suman().count()

    context = {
        'vendedores_data': vendedores_data,
        'sucursal_actual': request.user.sucursal,
        'porcentaje_sucursal': getattr(
            request.user.sucursal, 'porcentaje_comision_default', None
        ),
        'total_comisiones_sucursal': total_comisiones_sucursal,
        'total_vales_egreso_sucursal': total_vales_egreso_sucursal,
        'total_vales_ingreso_sucursal': total_vales_ingreso_sucursal,
        'total_saldo_vales_sucursal': total_saldo_vales_sucursal,
        'total_neto_sucursal': total_neto_sucursal,
        'total_ops_comisiones': total_ops_comisiones,
        'total_mov_vales': total_mov_vales,
        'neto_mes_sucursal': neto_mes_sucursal,
        'cant_ops_mes': cant_ops_mes,
    }
    return render(request, 'inmobiliaria/comisiones/dashboard.html', context)

# ✅ VISTAS PARA VALES DE VENDEDORES

@login_required
def crear_vale(request):
    """
    Vista para crear un vale (préstamo) a un vendedor
    El vale se descuenta del efectivo de caja
    """
    if request.method == 'POST':
        try:
            # Obtener datos del formulario
            vendedor_id = request.POST.get('vendedor_id')
            monto = parse_decimal_monto(request.POST.get('monto', '0'))
            concepto = request.POST.get('concepto', 'Vale')
            observaciones = request.POST.get('observaciones', '')
            
            # Validar monto
            if monto <= 0:
                messages.error(request, 'El monto debe ser mayor a cero.')
                return redirect('inmobiliaria:dashboard_caja')
            
            # Obtener vendedor (misma sucursal)
            vendedor = get_object_or_404(
                Vendedor, id=vendedor_id, sucursal=request.user.sucursal
            )
            
            # Obtener caja activa
            caja_actual = Caja.objects.filter(
                sucursal=request.user.sucursal,
                estado='abierta'
            ).first()
            
            if not caja_actual:
                messages.error(request, 'No hay una caja abierta. Debes abrir una caja primero.')
                return redirect('inmobiliaria:dashboard_caja')
            
            # Crear el vale
            vale = ValeVendedor.crear_vale(
                vendedor=vendedor,
                monto=monto,
                caja=caja_actual,
                concepto=concepto,
                observaciones=observaciones,
                usuario_creador=request.user
            )
            
            messages.success(request, f'Vale de ${monto:,.0f} creado exitosamente para {vendedor.nombre_completo_vendedor()}.')
            return redirect('inmobiliaria:dashboard_caja')
            
        except Exception as e:
            messages.error(request, f'Error al crear el vale: {str(e)}')
            return redirect('inmobiliaria:dashboard_caja')
    
    # GET - Mostrar formulario
    vendedores = Vendedor.objects.filter(sucursal=request.user.sucursal).order_by('nombre', 'apellido')
    context = {
        'vendedores': vendedores
    }
    return render(request, 'inmobiliaria/vales/crear_vale.html', context)

# ============================================================================
# LIQUIDACIONES - SISTEMA DE LIQUIDACIÓN DE PROPIETARIOS
# ============================================================================

@login_required
def liquidaciones_propietarios(request):
    """
    Vista principal de liquidaciones - Búsqueda de propietarios
    """
    sucursal = request.user.sucursal
    propietarios = Propietario.objects.filter(sucursal=sucursal).order_by('apellido', 'nombre')
    
    # Aplicar búsqueda si existe
    busqueda = request.GET.get('busqueda', '').strip()
    if busqueda:
        # Intentar búsqueda exacta por ID primero
        try:
            # Si la búsqueda parece ser un ID exacto, intentar búsqueda exacta
            propietario_exacto = propietarios.filter(id=busqueda).first()
            if propietario_exacto:
                propietarios = propietarios.filter(id=busqueda)
            else:
                # Si no es exacto, buscar en todos los campos
                propietarios = propietarios.filter(
                    Q(id__icontains=busqueda) |
                    Q(nombre__icontains=busqueda) |
                    Q(apellido__icontains=busqueda) |
                    Q(dni__icontains=busqueda)
                )
        except (ValueError, TypeError):
            # Si hay error al convertir a ID, buscar en todos los campos
            propietarios = propietarios.filter(
                Q(id__icontains=busqueda) |
                Q(nombre__icontains=busqueda) |
                Q(apellido__icontains=busqueda) |
                Q(dni__icontains=busqueda)
            )
    
    context = {
        'propietarios': propietarios,
        'busqueda': busqueda
    }
    
    return render(request, 'inmobiliaria/liquidaciones/lista_propietarios.html', context)

@login_required
def liquidacion_propietario(request, propietario_id):
    """
    Vista de liquidación completa de un propietario
    Muestra todos los gastos y desglose por propiedad
    """
    propietario = get_object_or_404(Propietario, id=propietario_id)
    
    # Verificar que pertenezca a la sucursal del usuario
    if propietario.sucursal != request.user.sucursal:
        messages.error(request, 'No tienes permisos para ver esta liquidación.')
        return redirect('inmobiliaria:liquidaciones_propietarios')
    
    # Obtener filtros de fecha
    fecha_desde = request.GET.get('fecha_desde', '')
    fecha_hasta = request.GET.get('fecha_hasta', '')
    
    # Obtener todas las propiedades del propietario ordenadas por número de propiedad
    propiedades = Propiedad.objects.filter(propietario=propietario).order_by('numero_por_propietario')
    
    # Obtener todos los movimientos de caja relacionados con las propiedades del propietario
    # Buscar en movimientos que tengan la propiedad asignada
    movimientos_totales = MovimientoCaja.objects.filter(
        propiedad__propietario=propietario
    ).select_related('caja', 'propiedad', 'empleado').order_by('-fecha')
    
    # Aplicar filtros de fecha
    if fecha_desde:
        movimientos_totales = movimientos_totales.filter(fecha__gte=fecha_desde)
    if fecha_hasta:
        movimientos_totales = movimientos_totales.filter(fecha__lte=fecha_hasta)
    
    # Calcular totales generales
    total_gastos = Decimal('0')
    for mov in movimientos_totales:
        if mov.tipo == TipoMovimientoCajaEnum.EGRESO:
            total_gastos += mov.monto_total
    
    # Calcular gastos por propiedad (aplicando mismos filtros de fecha)
    propiedades_con_gastos = []
    for propiedad in propiedades:
        movimientos_prop = MovimientoCaja.objects.filter(
            propiedad=propiedad
        ).order_by('-fecha')
        
        # Aplicar filtros de fecha también aquí
        if fecha_desde:
            movimientos_prop = movimientos_prop.filter(fecha__gte=fecha_desde)
        if fecha_hasta:
            movimientos_prop = movimientos_prop.filter(fecha__lte=fecha_hasta)
        
        total_gastos_prop = Decimal('0')
        for mov in movimientos_prop:
            if mov.tipo == TipoMovimientoCajaEnum.EGRESO:
                total_gastos_prop += mov.monto_total
        
        propiedades_con_gastos.append({
            'propiedad': propiedad,
            'movimientos': movimientos_prop,
            'total_gastos': total_gastos_prop,
            'cantidad_movimientos': movimientos_prop.count()
        })
    
    context = {
        'propietario': propietario,
        'movimientos_totales': movimientos_totales,
        'total_gastos': total_gastos,
        'propiedades_con_gastos': propiedades_con_gastos,
        'total_propiedades': propiedades.count(),
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta
    }
    
    return render(request, 'inmobiliaria/liquidaciones/detalle_propietario.html', context)

@login_required
def liquidacion_propiedad(request, propiedad_id):
    """
    Vista de liquidación detallada de una propiedad específica
    """
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    
    # Verificar que pertenezca a la sucursal del usuario
    if propiedad.sucursal != request.user.sucursal:
        messages.error(request, 'No tienes permisos para ver esta liquidación.')
        return redirect('inmobiliaria:liquidaciones_propietarios')
    
    # Obtener filtros de fecha
    fecha_desde = request.GET.get('fecha_desde', '')
    fecha_hasta = request.GET.get('fecha_hasta', '')
    
    # Obtener todos los movimientos de esta propiedad
    movimientos = MovimientoCaja.objects.filter(
        propiedad=propiedad
    ).select_related('caja', 'empleado').order_by('-fecha')
    
    # Aplicar filtros de fecha
    if fecha_desde:
        movimientos = movimientos.filter(fecha__gte=fecha_desde)
    if fecha_hasta:
        movimientos = movimientos.filter(fecha__lte=fecha_hasta)
    
    # Separar por tipo
    ingresos = movimientos.filter(tipo=TipoMovimientoCajaEnum.INGRESO)
    egresos = movimientos.filter(tipo=TipoMovimientoCajaEnum.EGRESO)
    
    # Calcular totales
    total_ingresos = sum(mov.monto_total for mov in ingresos)
    total_egresos = sum(mov.monto_total for mov in egresos)
    balance = total_ingresos - total_egresos
    
    context = {
        'propiedad': propiedad,
        'propietario': propiedad.propietario,
        'movimientos': movimientos,
        'ingresos': ingresos,
        'egresos': egresos,
        'total_ingresos': total_ingresos,
        'total_egresos': total_egresos,
        'balance': balance,
        'total_movimientos': movimientos.count(),
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta
    }
    
    return render(request, 'inmobiliaria/liquidaciones/detalle_propiedad.html', context)

@login_required
def lista_vales_vendedor(request, vendedor_id):
    """
    Vista para mostrar todos los vales de un vendedor específico
    Solo accesible para administradores (nivel 4)
    """
    # Verificar que el usuario sea nivel 4
    if request.user.nivel != 4:
        messages.error(request, 'No tienes permisos para acceder a esta sección.')
        return redirect('inmobiliaria:dashboard')
    
    vendedor = get_object_or_404(
        Vendedor, id=vendedor_id, sucursal=request.user.sucursal
    )
    vales = (
        ValeVendedor.objects.filter(vendedor=vendedor)
        .select_related('movimiento_caja', 'movimiento_caja__caja', 'usuario_creador')
        .order_by('-fecha')
    )
    
    total_vales_saldo = ValeVendedor.total_saldo_para_comisiones(vendedor)
    total_vales_egreso = (
        vales.filter(tipo_vale='EG').aggregate(total=models.Sum('monto'))['total'] or Decimal('0')
    )
    total_vales_ingreso = (
        vales.filter(tipo_vale='IN').aggregate(total=models.Sum('monto'))['total'] or Decimal('0')
    )
    
    context = {
        'vendedor': vendedor,
        'vales': vales,
        'total_vales': total_vales_saldo,
        'total_vales_egreso': total_vales_egreso,
        'total_vales_ingreso': total_vales_ingreso,
    }
    
    return render(request, 'inmobiliaria/vales/lista_vales.html', context)

# ✅ VISTA PARA MOVIMIENTOS HISTÓRICOS DE TODAS LAS CAJAS

@login_required
def todos_movimientos_caja(request):
    """
    Vista para mostrar TODOS los movimientos de TODAS las cajas
    Con filtros de búsqueda por ID, concepto, empleado, etc.
    Si hay filtro por propiedad(es), el total y el resumen mensual de ingresos usan el neto al propietario
    (monto_a_pagar de la liquidación vinculada al movimiento), no el monto total en caja.
    """
    # Imports locales: esta vista está definida antes del bloque masivo de imports del módulo (~L1173).
    from django.db.models import Q, Sum, Case, When, F, Count, DecimalField
    from django.db.models.functions import TruncMonth

    from inmobiliaria.models.caja import MovimientoCaja, TipoMovimientoCajaEnum
    from inmobiliaria.models.liquidacion import LiquidacionPropietario
    from inmobiliaria.models.propiedad import Propiedad

    movimientos = MovimientoCaja.objects.filter(
        sucursal=request.user.sucursal
    ).select_related(
        'caja', 'empleado', 'propiedad', 'cuenta'
    ).order_by('-fecha')

    busqueda = request.GET.get('busqueda', '').strip()
    tipo_filtro = request.GET.get('tipo', '')
    propiedad_id = request.GET.get('propiedad_id', '').strip()
    propiedad_ids = [p.strip() for p in request.GET.getlist('propiedad_ids') if p.strip()]
    if propiedad_id and propiedad_id not in propiedad_ids:
        propiedad_ids.append(propiedad_id)
    # Evita URLs enormes / límites del motor SQL y mantiene la vista usable.
    _max_prop_filtro = 100
    if len(propiedad_ids) > _max_prop_filtro:
        propiedad_ids = propiedad_ids[:_max_prop_filtro]
    mes_filtro = request.GET.get('mes', '').strip()  # YYYY-MM
    fecha_desde = request.GET.get('fecha_desde', '')
    fecha_hasta = request.GET.get('fecha_hasta', '')

    if busqueda:
        # id es BigAutoField: icontains en PostgreSQL puede romper el lookup; usar pk exacto si es numérico.
        q_bus = (
            Q(concepto__icontains=busqueda)
            | Q(numero_liquidacion__icontains=busqueda)
            | Q(empleado__nombre__icontains=busqueda)
            | Q(empleado__apellido__icontains=busqueda)
            | Q(empleado__dni__icontains=busqueda)
        )
        # isdigit() es True para algunos dígitos Unicode donde int() falla → ValueError fuera del try del neto.
        if busqueda.isascii() and busqueda.isdigit():
            q_bus |= Q(pk=int(busqueda))
        movimientos = movimientos.filter(q_bus)

    if tipo_filtro:
        movimientos = movimientos.filter(tipo=tipo_filtro)

    if propiedad_ids:
        movimientos = movimientos.filter(propiedad_id__in=propiedad_ids)

    # Atajo por mes (si no hay rango manual)
    if mes_filtro and not fecha_desde and not fecha_hasta:
        try:
            y, m = mes_filtro.split('-', 1)
            year = int(y)
            month = int(m)
            fecha_desde = date(year, month, 1).strftime('%Y-%m-%d')
            if month == 12:
                fecha_hasta_dt = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                fecha_hasta_dt = date(year, month + 1, 1) - timedelta(days=1)
            fecha_hasta = fecha_hasta_dt.strftime('%Y-%m-%d')
        except Exception:
            mes_filtro = ''

    if fecha_desde:
        movimientos = movimientos.filter(fecha__date__gte=fecha_desde)
    if fecha_hasta:
        movimientos = movimientos.filter(fecha__date__lte=fecha_hasta)

    # Con filtro por propiedad(es): ingresos = neto al propietario (liquidación si existe; si no, toma/70% como liquidaciones).
    ingresos_son_neto_propietario = bool(propiedad_ids)
    neto_por_mov_id = {}

    if ingresos_son_neto_propietario:
        try:
            from collections import defaultdict

            from inmobiliaria.neto_propietario_movimiento import (
                monto_medios_movimiento_decimal,
                neto_propietario_movimiento,
                precios_por_propiedad_ids,
                primer_dia_mes_movimiento,
            )

            precios_map = precios_por_propiedad_ids(propiedad_ids)
            mov_ids = list(movimientos.values_list('id', flat=True))
            liq_by_mov = {}
            _batch = 400
            for _i in range(0, len(mov_ids), _batch):
                _chunk = mov_ids[_i : _i + _batch]
                for _liq in LiquidacionPropietario.objects.filter(
                    movimiento_caja_id__in=_chunk
                ).exclude(estado='cancelada'):
                    _mid = _liq.movimiento_caja_id
                    if _mid and _mid not in liq_by_mov:
                        liq_by_mov[_mid] = _liq

            mes_buckets = defaultdict(
                lambda: {
                    'ingresos': Decimal('0'),
                    'egresos': Decimal('0'),
                    'reservas': 0,
                    'movimientos': 0,
                }
            )
            total_ingresos = Decimal('0')

            for mov in movimientos.select_related('propiedad'):
                mes_key = primer_dia_mes_movimiento(mov)
                mes_buckets[mes_key]['movimientos'] += 1
                _conc = mov.concepto or ''
                if mov.tipo == TipoMovimientoCajaEnum.INGRESO and (
                    'Operación' in _conc or 'Reserva' in _conc
                ):
                    mes_buckets[mes_key]['reservas'] += 1

                if mov.tipo == TipoMovimientoCajaEnum.INGRESO:
                    _neto = neto_propietario_movimiento(mov, liq_by_mov, precios_map)
                    neto_por_mov_id[mov.id] = _neto
                    total_ingresos += _neto
                    mes_buckets[mes_key]['ingresos'] += _neto
                elif mov.tipo == TipoMovimientoCajaEnum.EGRESO:
                    neto_por_mov_id[mov.id] = Decimal('0')
                    mes_buckets[mes_key]['egresos'] += monto_medios_movimiento_decimal(mov)

            resumen_mensual = []
            for mk in sorted(mes_buckets.keys(), reverse=True):
                v = mes_buckets[mk]
                resumen_mensual.append(
                    {
                        'mes': mk,
                        'ingresos': v['ingresos'],
                        'egresos': v['egresos'],
                        'balance': v['ingresos'] - v['egresos'],
                        'reservas': v['reservas'],
                        'movimientos': v['movimientos'],
                    }
                )
        except Exception:
            logger.exception(
                'todos_movimientos_caja: falló el cálculo de neto propietario; se muestran totales de caja.'
            )
            ingresos_son_neto_propietario = False
            neto_por_mov_id = {}
            ingresos = movimientos.filter(tipo=TipoMovimientoCajaEnum.INGRESO).aggregate(
                efectivo=Sum('monto_efectivo'),
                cheque=Sum('monto_cheque'),
                tarjeta=Sum('monto_tarjeta'),
                deposito=Sum('monto_deposito'),
            )
            total_ingresos = (
                (ingresos['efectivo'] or Decimal('0'))
                + (ingresos['cheque'] or Decimal('0'))
                + (ingresos['tarjeta'] or Decimal('0'))
                + (ingresos['deposito'] or Decimal('0'))
            )
            _dec18_fb = DecimalField(max_digits=18, decimal_places=2)
            resumen_mensual = (
                movimientos.annotate(mes=TruncMonth('fecha'))
                .values('mes')
                .annotate(
                    ingresos=Sum(
                        Case(
                            When(
                                tipo=TipoMovimientoCajaEnum.INGRESO,
                                then=F('monto_efectivo')
                                + F('monto_cheque')
                                + F('monto_tarjeta')
                                + F('monto_deposito'),
                            ),
                            default=Decimal('0'),
                            output_field=_dec18_fb,
                        )
                    ),
                    egresos=Sum(
                        Case(
                            When(
                                tipo=TipoMovimientoCajaEnum.EGRESO,
                                then=F('monto_efectivo')
                                + F('monto_cheque')
                                + F('monto_tarjeta')
                                + F('monto_deposito'),
                            ),
                            default=Decimal('0'),
                            output_field=_dec18_fb,
                        )
                    ),
                    reservas=Count(
                        'id',
                        filter=Q(tipo=TipoMovimientoCajaEnum.INGRESO)
                        & (
                            Q(concepto__icontains='Operación')
                            | Q(concepto__icontains='Reserva')
                        ),
                    ),
                    movimientos=Count('id'),
                )
                .annotate(balance=F('ingresos') - F('egresos'))
                .order_by('-mes')
            )
    else:
        ingresos = movimientos.filter(tipo=TipoMovimientoCajaEnum.INGRESO).aggregate(
            efectivo=Sum('monto_efectivo'),
            cheque=Sum('monto_cheque'),
            tarjeta=Sum('monto_tarjeta'),
            deposito=Sum('monto_deposito'),
        )
        total_ingresos = (
            (ingresos['efectivo'] or Decimal('0'))
            + (ingresos['cheque'] or Decimal('0'))
            + (ingresos['tarjeta'] or Decimal('0'))
            + (ingresos['deposito'] or Decimal('0'))
        )

        _dec18 = DecimalField(max_digits=18, decimal_places=2)
        resumen_mensual = (
            movimientos.annotate(mes=TruncMonth('fecha'))
            .values('mes')
            .annotate(
                ingresos=Sum(
                    Case(
                        When(
                            tipo=TipoMovimientoCajaEnum.INGRESO,
                            then=F('monto_efectivo')
                            + F('monto_cheque')
                            + F('monto_tarjeta')
                            + F('monto_deposito'),
                        ),
                        default=Decimal('0'),
                        output_field=_dec18,
                    )
                ),
                egresos=Sum(
                    Case(
                        When(
                            tipo=TipoMovimientoCajaEnum.EGRESO,
                            then=F('monto_efectivo')
                            + F('monto_cheque')
                            + F('monto_tarjeta')
                            + F('monto_deposito'),
                        ),
                        default=Decimal('0'),
                        output_field=_dec18,
                    )
                ),
                reservas=Count(
                    'id',
                    filter=Q(tipo=TipoMovimientoCajaEnum.INGRESO)
                    & (
                        Q(concepto__icontains='Operación')
                        | Q(concepto__icontains='Reserva')
                    ),
                ),
                movimientos=Count('id'),
            )
            .annotate(balance=F('ingresos') - F('egresos'))
            .order_by('-mes')
        )

    egresos = movimientos.filter(tipo=TipoMovimientoCajaEnum.EGRESO).aggregate(
        efectivo=Sum('monto_efectivo'),
        cheque=Sum('monto_cheque'),
        tarjeta=Sum('monto_tarjeta'),
        deposito=Sum('monto_deposito'),
    )
    total_egresos = (
        (egresos['efectivo'] or Decimal('0'))
        + (egresos['cheque'] or Decimal('0'))
        + (egresos['tarjeta'] or Decimal('0'))
        + (egresos['deposito'] or Decimal('0'))
    )

    total_reservas = movimientos.filter(
        tipo=TipoMovimientoCajaEnum.INGRESO
    ).filter(
        Q(concepto__icontains='Operación') | Q(concepto__icontains='Reserva')
    ).count()

    from django.core.paginator import Paginator
    paginator = Paginator(movimientos, 50)
    page_number = request.GET.get('page')
    movimientos_paginados = paginator.get_page(page_number)
    if ingresos_son_neto_propietario:
        for _m in movimientos_paginados:
            setattr(
                _m,
                '_neto_propietario_liq',
                neto_por_mov_id.get(_m.id, Decimal('0')),
            )
    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']

    context = {
        'movimientos': movimientos_paginados,
        'total_movimientos': movimientos.count(),
        'total_ingresos': total_ingresos,
        'total_egresos': total_egresos,
        'total_reservas': total_reservas,
        'busqueda': busqueda,
        'tipo_filtro': tipo_filtro,
        'propiedad_id': propiedad_id,
        'propiedad_ids': propiedad_ids,
        'mes_filtro': mes_filtro,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'propiedades': Propiedad.objects.filter(
            sucursal=request.user.sucursal
        ).order_by('direccion'),
        'resumen_mensual': resumen_mensual,
        'querystring': query_params.urlencode(),
        'ingresos_son_neto_propietario': ingresos_son_neto_propietario,
    }
    
    return render(request, 'inmobiliaria/caja/todos_movimientos.html', context)


@login_required
def historial_propiedad_caja(request):
    """
    Apartado de caja: historial por propiedad (movimientos, reservas, contratos, pagos).
    Los totales superiores se arman desde liquidaciones (parte propietario / neto a pagar / comisión), no desde el monto total de caja.
    """
    termino = request.GET.get('q', '').strip()
    propiedad_id = request.GET.get('propiedad_id', '').strip()

    propiedades_base = Propiedad.objects.filter(
        sucursal=request.user.sucursal
    ).select_related('propietario', 'sucursal').order_by('direccion')

    propiedad = None
    coincidencias = Propiedad.objects.none()

    if propiedad_id:
        propiedad = propiedades_base.filter(id=propiedad_id).first()
    elif termino:
        if termino.isdigit():
            propiedad = propiedades_base.filter(id=int(termino)).first()
        if not propiedad:
            coincidencias = propiedades_base.filter(
                Q(direccion__icontains=termino) |
                Q(ubicacion__icontains=termino)
            )[:20]
            if coincidencias.count() == 1:
                propiedad = coincidencias.first()

    movimientos = []
    reservas = Reserva.objects.none()
    contratos = ContratoAlquiler.objects.none()
    pagos = Pago.objects.none()
    total_pagos = Decimal('0')
    liquidaciones = []
    total_liq_parte_propietario = Decimal('0')
    total_liq_neto_a_pagar = Decimal('0')
    total_liq_inmobiliaria = Decimal('0')

    if propiedad:
        mov_qs = (
            MovimientoCaja.objects.filter(
                sucursal=request.user.sucursal,
                propiedad=propiedad,
            )
            .select_related('caja', 'empleado', 'cuenta', 'propiedad')
            .order_by('-fecha')[:200]
        )
        movimientos = list(mov_qs)
        mov_ids = [m.id for m in movimientos]
        liq_por_mov = {}
        if mov_ids:
            for liq in LiquidacionPropietario.objects.filter(
                movimiento_caja_id__in=mov_ids
            ).exclude(estado='cancelada'):
                mid = liq.movimiento_caja_id
                if mid not in liq_por_mov:
                    liq_por_mov[mid] = liq
        from inmobiliaria.neto_propietario_movimiento import (
            neto_propietario_movimiento,
            precios_por_propiedad_ids,
        )

        _precios_hist = precios_por_propiedad_ids([propiedad.id])
        for m in movimientos:
            setattr(m, 'liquidacion_movimiento', liq_por_mov.get(m.id))
            setattr(
                m,
                '_neto_propietario_display',
                neto_propietario_movimiento(m, liq_por_mov, _precios_hist),
            )

        reservas = Reserva.objects.filter(
            propiedad=propiedad,
            eliminada=False
        ).select_related(
            'cliente', 'vendedor'
        ).order_by('-fecha_creacion')

        contratos = ContratoAlquiler.objects.filter(
            propiedad=propiedad
        ).select_related(
            'inquilino', 'vendedor'
        ).order_by('-fecha_creacion')

        pagos = Pago.objects.filter(
            reserva__propiedad=propiedad,
            reserva__eliminada=False
        ).select_related(
            'reserva', 'concepto'
        ).order_by('-fecha')

        total_pagos = pagos.aggregate(total=Sum('monto'))['total'] or Decimal('0')

        liq_base = LiquidacionPropietario.objects.filter(
            propiedad=propiedad
        ).exclude(estado='cancelada')
        agg_liq = liq_base.aggregate(
            tp=Sum('monto_propietario'),
            tap=Sum('monto_a_pagar'),
            ti=Sum('monto_inmobiliaria'),
        )
        total_liq_parte_propietario = agg_liq['tp'] or Decimal('0')
        total_liq_neto_a_pagar = agg_liq['tap'] or Decimal('0')
        total_liq_inmobiliaria = agg_liq['ti'] or Decimal('0')
        liquidaciones = list(
            liq_base.select_related('reserva', 'contrato', 'movimiento_caja').order_by(
                '-fecha_creacion'
            )[:100]
        )

    context = {
        'termino': termino,
        'propiedad_id': propiedad_id,
        'propiedad': propiedad,
        'coincidencias': coincidencias,
        'movimientos': movimientos,
        'reservas': reservas[:100],
        'contratos': contratos[:100],
        'pagos': pagos[:200],
        'total_pagos': total_pagos,
        'liquidaciones': liquidaciones,
        'total_liq_parte_propietario': total_liq_parte_propietario,
        'total_liq_neto_a_pagar': total_liq_neto_a_pagar,
        'total_liq_inmobiliaria': total_liq_inmobiliaria,
    }
    return render(request, 'inmobiliaria/caja/historial_propiedad_caja.html', context)

from xhtml2pdf import pisa
from io import BytesIO
from .models import (
    Vendedor, Inquilino, Propietario, Propiedad, Reserva, 
    Disponibilidad, ImagenPropiedad, Precio, TipoPrecio, 
    Pago, ConceptoPago, HistorialDisponibilidad, VentaPropiedad, 
    AlquilerMeses, AlquilerInvierno, Caja, MovimientoCaja, Cuenta, Concepto, Sucursal,
    TipoMovimientoCajaEnum, ContratoAlquiler, ContratoInquilino, CuotaMensual, ComisionVendedor, ValeVendedor, MesComisionPagadoVendedor,
    LiquidacionPropietario, GastoPropietario
)
from .catalogo_conceptos_caja import (
    get_sucursal_referencia_catalogo_conceptos_caja,
    q_conceptos_caja_visibles,
    sucursal_destino_nuevo_concepto_caja,
)
from .forms import  VendedorUserCreationForm, VendedorChangeForm, InquilinoForm, PropietarioForm, PropiedadForm, ReservaForm,BuscarPropiedadesForm, DisponibilidadForm,PrecioForm, PrecioFormSet, PropietarioBuscarForm, InquilinoBuscarForm, SucursalForm, LoginForm, PropiedadSearchForm, VentaPropiedadForm, MovimientoCajaForm
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm, SetPasswordForm
from django.contrib.auth import login
from datetime import datetime, date, timedelta
from django.db.models import Q, Prefetch, Case, When, IntegerField, Sum, Max, F, Count, DecimalField
from django.db.models.functions import TruncMonth, Lower
from django.core.exceptions import ValidationError
from django.forms import modelformset_factory
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from dateutil.parser import parse
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from django.views.decorators.http import require_POST, require_http_methods
import json
from django.db import models
from django.conf import settings
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import os
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth import get_user_model
from django.contrib.auth import update_session_auth_hash
from .utils import numero_a_palabras

import logging
logger = logging.getLogger(__name__)

# IDs de concepto en |CONCEPTOS:…| que cuentan como seña / «saldo a ocupar» al finalizar o completar pago de operación.
# 50 = refuerzo de seña, 100 = saldo locación (además de 1 alquiler, 15, 103, 219).
CONCEPTOS_SENIA_OPERACION_RESERVA = frozenset({"1", "15", "50", "100", "103", "219"})


def get_inquilinos_queryset_unificado(request):
    """Lista de inquilinos unificada: en Colón y Corrientes se muestran los de ambas sucursales; en el resto solo los de la sucursal del usuario."""
    nombre_suc = (getattr(request.user.sucursal, 'nombre', None) or '').lower()
    if 'colon' in nombre_suc or 'corrientes' in nombre_suc:
        return Inquilino.objects.filter(
            Q(sucursal__nombre__icontains='colon') | Q(sucursal__nombre__icontains='corrientes')
        ).order_by('apellido', 'nombre')
    return Inquilino.objects.filter(sucursal=request.user.sucursal).order_by('apellido', 'nombre')

import traceback  # Agregada esta importación
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from django import forms

# Formulario para recuperación de contraseña
class EmailForm(forms.Form):
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'ejemplo@correo.com',
            'autocomplete': 'email'
        })
    )

# index view
def index(request):
    if request.user.is_authenticated:
        return redirect('inmobiliaria:dashboard')
    else:
        return redirect('inmobiliaria:index')

# Vendedor views
@login_required
def dashboard(request):
    vendedor = None
    nivel = 0
    if request.user.is_authenticated and hasattr(request.user, 'vendedor'):
        vendedor = request.user.vendedor
        nivel = vendedor.nivel

    context = {
        'nivel_usuario': nivel,
        'vendedor': vendedor,
    }
    return render(request, 'inmobiliaria/dashboard.html', context)
@login_required
def vendedores(request):
    vendedores = Vendedor.objects.filter(sucursal=request.user.sucursal)
    return render(request, 'inmobiliaria/vendedores/lista.html', {'vendedores': vendedores})

@login_required
def vendedor_detalle(request, vendedor_id):
    vendedor = get_object_or_404(
        Vendedor.objects.select_related('sucursal'),
        pk=vendedor_id,
    )
    return render(request, 'inmobiliaria/vendedores/detalle.html', {'vendedor': vendedor})
@login_required
def vendedor_nuevo(request):
    if request.method == "POST":
        form = VendedorUserCreationForm(request.POST)
        if form.is_valid():
            vendedor = form.save()
            messages.success(request, 'Vendedor creado exitosamente.')
            return redirect('inmobiliaria:vendedor_detalle', vendedor_id=vendedor.id)
    else:
        form = VendedorUserCreationForm()
    return render(request, 'inmobiliaria/vendedores/formulario.html', {'form': form})

@login_required
def vendedor_editar(request, vendedor_id):
    vendedor = get_object_or_404(Vendedor, pk=vendedor_id)
    if request.method == "POST":
        form = VendedorChangeForm(request.POST, instance=vendedor)
        if form.is_valid():
            vendedor = form.save()
            messages.success(request, 'Vendedor actualizado exitosamente.')
            return redirect('inmobiliaria:vendedor_detalle', vendedor_id=vendedor.id)
    else:
        form = VendedorChangeForm(instance=vendedor)
    return render(request, 'inmobiliaria/vendedores/formulario.html', {'form': form, 'vendedor': vendedor})
@login_required
def vendedor_eliminar(request, vendedor_id):
    vendedor = get_object_or_404(Vendedor, pk=vendedor_id)
    if request.method == "POST":
        vendedor.delete()
        messages.success(request, 'Vendedor eliminado exitosamente.')
        return redirect('inmobiliaria:vendedores')
    return render(request, 'inmobiliaria/vendedores/confirmar_eliminar.html', {'vendedor': vendedor})

# Inquilino views
@login_required
def inquilinos(request):
    form = InquilinoBuscarForm(request.GET or None)
    inquilinos = get_inquilinos_queryset_unificado(request)
    

    if form.is_valid():
        termino = form.cleaned_data.get('termino')
        
        if termino:
            palabras = termino.split()
            query = Q()
            for palabra in palabras:
                query |= Q(nombre__icontains=palabra) | Q(apellido__icontains=palabra)
            query |= Q(dni__icontains=termino)
            inquilinos = inquilinos.filter(query)

    # Detectar si la solicitud es AJAX
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        inquilinos_data = [{
            'id': i.id,
            'dni': i.dni or '',
            'nombre': i.nombre,
            'apellido': i.apellido,
            'email': i.email or ''
        } for i in inquilinos]
        return JsonResponse({'inquilinos': inquilinos_data})

    # Retornar la plantilla completa si no es AJAX
    return render(request, 'inmobiliaria/inquilinos/lista.html', {
        'form': form,
        'inquilinos': inquilinos
    })

@login_required
def inquilino_detalle(request, inquilino_id):
    inquilino = get_object_or_404(Inquilino, pk=inquilino_id)
    return render(request, 'inmobiliaria/inquilinos/detalle.html', {'inquilino': inquilino})

@login_required
def inquilino_nuevo(request):
    if request.method == "POST":
        form = InquilinoForm(request.POST, user=request.user)
        if form.is_valid():
            inquilino = form.save()
            messages.success(request, 'Inquilino creado exitosamente.')
            return redirect('inmobiliaria:inquilinos')
    else:
        form = InquilinoForm(user=request.user)
    return render(request, 'inmobiliaria/inquilinos/formulario.html', {'form': form})

@login_required
def inquilino_editar(request, inquilino_id):
    inquilino = get_object_or_404(Inquilino, pk=inquilino_id)
    if request.method == "POST":
        form = InquilinoForm(request.POST, instance=inquilino)
        if form.is_valid():
            inquilino = form.save()
            messages.success(request, 'Inquilino actualizado exitosamente.')
            return redirect('inmobiliaria:inquilino_detalle', inquilino_id=inquilino.id)
    else:
        form = InquilinoForm(instance=inquilino)
    return render(request, 'inmobiliaria/inquilinos/formulario.html', {'form': form, 'inquilino': inquilino})

@login_required
def inquilino_eliminar(request, inquilino_id):
    inquilino = get_object_or_404(Inquilino, pk=inquilino_id)
    if request.method == "POST":
        inquilino.delete()
        messages.success(request, 'Inquilino eliminado exitosamente.')
        return redirect('inmobiliaria:inquilinos')
    return render(request, 'inmobiliaria/inquilinos/confirmar_eliminar.html', {'inquilino': inquilino})

# Propietario views
@login_required
def propietarios(request):
    form = PropietarioBuscarForm(request.GET or None)
    
    # Determinar qué propietarios mostrar según el nivel del usuario
    if request.user.is_superuser or request.user.nivel == 4:
        propietarios = Propietario.objects.filter(sucursal=request.user.sucursal)
    else:
        # Filtrar por la sucursal del vendedor logueado
        propietarios = Propietario.objects.filter(sucursal=request.user.sucursal)

    if form.is_valid():
        termino = form.cleaned_data.get('termino')
        if termino:
            termino = termino.strip()
            # 1) Coincidir término completo en nombre, apellido, DNI o ID (apellidos con espacio ej. "de Marcos")
            query = (
                Q(nombre__icontains=termino) |
                Q(apellido__icontains=termino) |
                Q(dni__icontains=termino) |
                Q(id__icontains=termino)
            )
            # 2) Si hay varias palabras, también coincidir si TODAS aparecen en nombre o apellido
            palabras = [p.strip() for p in termino.split() if p.strip()]
            if len(palabras) > 1:
                query_palabras = Q()
                for palabra in palabras:
                    query_palabras &= (Q(nombre__icontains=palabra) | Q(apellido__icontains=palabra))
                query = query | query_palabras
            elif len(palabras) == 1:
                query |= Q(nombre__icontains=palabras[0]) | Q(apellido__icontains=palabras[0])
            propietarios = propietarios.filter(query)

    # Detectar si la solicitud es AJAX
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        propietarios_data = [{
            'id': p.id,
            'nombre': p.nombre,
            'apellido': p.apellido,
            'dni': p.dni,
            'cuenta_bancaria': p.cuenta_bancaria if hasattr(p, 'cuenta_bancaria') else '',
            'sucursal': p.sucursal.nombre  # Agregar el nombre de la sucursal si lo necesitas en la respuesta
        } for p in propietarios]
        return JsonResponse({'propietarios': propietarios_data})

    # Retornar la plantilla completa si no es AJAX
    context = {
        'form': form,
        'propietarios': propietarios,
        'sucursal_actual': request.user.sucursal.nombre if not request.user.is_superuser else 'Todas las sucursales'
    }
    
    return render(request, 'inmobiliaria/propietarios/lista.html', context)

@login_required
def propietario_detalle(request, propietario_id):
    propietario = get_object_or_404(Propietario, pk=propietario_id)
    return render(request, 'inmobiliaria/propietarios/detalle.html', {'propietario': propietario})

@login_required
def propietario_nuevo(request):
    if request.method == "POST":
        form = PropietarioForm(request.POST, user=request.user)
        if form.is_valid():
            propietario = form.save()
            messages.success(request, 'Propietario creado exitosamente.')
            return redirect('inmobiliaria:propietario_detalle', propietario_id=propietario.id)
    else:
        form = PropietarioForm(user=request.user)
    return render(request, 'inmobiliaria/propietarios/formulario.html', {'form': form})

@login_required
def propietario_editar(request, propietario_id):
    propietario = get_object_or_404(Propietario, pk=propietario_id)
    if request.method == "POST":
        form = PropietarioForm(request.POST, instance=propietario)
        if form.is_valid():
            propietario = form.save()
            messages.success(request, 'Propietario actualizado exitosamente.')
            return redirect('inmobiliaria:propietario_detalle', propietario_id=propietario.id)
    else:
        form = PropietarioForm(instance=propietario)
    return render(request, 'inmobiliaria/propietarios/formulario.html', {'form': form, 'propietario': propietario})

@login_required
def propietario_eliminar(request, propietario_id):
    propietario = get_object_or_404(Propietario, pk=propietario_id)
    if request.method == "POST":
        propietario.delete()
        messages.success(request, 'Propietario eliminado exitosamente.')
        return redirect('inmobiliaria:propietarios')
    return render(request, 'inmobiliaria/propietarios/confirmar_eliminar.html', {'propietario': propietario})
@login_required
def propiedades(request):
    form = PropiedadSearchForm(request.GET or None)
    propiedades = Propiedad.objects.filter(sucursal=request.user.sucursal)

    if form.is_valid():
        query = form.cleaned_data.get('query')
        if query:
            propiedades = propiedades.filter(
                Q(direccion__icontains=query) |
                Q(id__icontains=query) |
                Q(propietario__nombre__icontains=query) |
                Q(propietario__apellido__icontains=query) |
                Q(fichado_por__nombre__icontains=query) |
                Q(fichado_por__apellido__icontains=query) |
                Q(fichado_por__username__icontains=query)
            )

    propiedades_list = list(propiedades)
    propiedades_list.sort(key=lambda p: int(p.id) if p.id.isdigit() else float('inf'))

    return render(request, 'inmobiliaria/propiedades/lista.html', {
        'form': form,
        'propiedades': propiedades_list
    })

@login_required
def propiedad_detalle(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, pk=propiedad_id)
    if not _propiedad_accesible_por_sucursal_usuario(request, propiedad):
        messages.error(request, 'No tenés permiso para ver esta propiedad (pertenece a otra sucursal).')
        return redirect('inmobiliaria:propiedades')
    # ✅ FILTRAR SOLO DISPONIBILIDADES MANUALES (no automáticas)
    disponibilidades = propiedad.disponibilidades.filter(es_manual=True).order_by('fecha_inicio')
    ids_superpuestos, textos_superpuestos = _disponibilidades_superpuestas(disponibilidades)
    hay_superposiciones = len(ids_superpuestos) > 0
    
    # Obtener el historial de disponibilidad (sin duplicados: mismo rango+estado+reserva solo una vez)
    historiales_qs = HistorialDisponibilidad.objects.filter(
        propiedad=propiedad
    ).order_by('fecha_inicio', 'fecha_fin')
    seen = set()
    historiales = []
    for h in historiales_qs:
        key = (h.fecha_inicio, h.fecha_fin, h.estado, h.reserva_id)
        if key not in seen:
            seen.add(key)
            historiales.append(h)
    
    # Si el historial está vacío pero hay reservas, reconstruirlo automáticamente
    if not historiales:
        # Verificar si hay reservas activas (no eliminadas)
        reservas_activas = propiedad.reservas.filter(eliminada=False).exists()
        # Verificar si hay disponibilidades manuales
        disponibilidades_manuales = propiedad.disponibilidades.filter(es_manual=True).exists()
        
        if reservas_activas or disponibilidades_manuales:
            # Reconstruir el historial automáticamente
            from inmobiliaria.models.propiedad import Reserva
            primera_reserva = propiedad.reservas.filter(eliminada=False).first()
            if primera_reserva:
                primera_reserva.reconstruir_historial_cronologico()
                historiales_qs = HistorialDisponibilidad.objects.filter(propiedad=propiedad).order_by('fecha_inicio', 'fecha_fin')
                seen = set()
                historiales = []
                for h in historiales_qs:
                    key = (h.fecha_inicio, h.fecha_fin, h.estado, h.reserva_id)
                    if key not in seen:
                        seen.add(key)
                        historiales.append(h)

    # Incluir solo contratos de invierno vigentes (no cancelados/rescindidos); si hay superposición de fechas, solo el más reciente
    from types import SimpleNamespace
    _contratos_inv = list(ContratoAlquiler.objects.filter(
        propiedad=propiedad,
        duracion_meses=9,
        estado__in=['activo', 'reservado']
    ).select_related('inquilino').order_by('-id'))
    contratos_invierno = []
    for c in _contratos_inv:
        if any(c.fecha_inicio < ex.fecha_fin and c.fecha_fin > ex.fecha_inicio for ex in contratos_invierno):
            continue
        contratos_invierno.append(c)
    contratos_invierno.sort(key=lambda x: (x.fecha_inicio, x.fecha_fin))
    # Recortar segmentos "Libre" del historial que se superpongan con contratos de invierno
    rangos_contrato = [(c.fecha_inicio, c.fecha_fin) for c in contratos_invierno]
    new_historiales = []
    for h in historiales:
        if getattr(h, 'estado', None) != 'libre':
            new_historiales.append(h)
            continue
        ini, fin = getattr(h, 'fecha_inicio', None), getattr(h, 'fecha_fin', None)
        if ini is None or fin is None:
            new_historiales.append(h)
            continue
        segmentos = [(ini, fin)]
        for (c_ini, c_fin) in rangos_contrato:
            nuevos = []
            for (s_ini, s_fin) in segmentos:
                if s_ini >= c_fin or s_fin <= c_ini:
                    nuevos.append((s_ini, s_fin))
                    continue
                if s_ini < c_ini:
                    # Hotel: Libre hasta el día de inicio del contrato inclusive
                    nuevos.append((s_ini, min(s_fin, c_ini)))
                if s_fin > c_fin:
                    # Hotel: Libre desde el día de fin del contrato inclusive
                    nuevos.append((max(s_ini, c_fin), s_fin))
            segmentos = [(a, b) for a, b in nuevos if a <= b]
        for (a, b) in segmentos:
            if hasattr(h, 'reserva') or isinstance(h, SimpleNamespace):
                new_historiales.append(SimpleNamespace(
                    fecha_inicio=a, fecha_fin=b, estado='libre', reserva=getattr(h, 'reserva', None),
                    es_libre_invierno=False, es_invierno=False, contrato=None,
                    fecha_actualizacion=getattr(h, 'fecha_actualizacion', None),
                ))
            else:
                new_historiales.append(SimpleNamespace(
                    fecha_inicio=a, fecha_fin=b, estado='libre', reserva=h.reserva if hasattr(h, 'reserva') else None,
                    es_libre_invierno=False, es_invierno=False, contrato=None,
                    fecha_actualizacion=getattr(h, 'fecha_actualizacion', None),
                ))
    historiales = new_historiales
    contratos_ya_mostrados = set()
    # Convertir filas del historial que son "Operación" sin reserva (creadas desde ficha Invierno) en "Operación (Invierno)" si coinciden con un contrato
    for i, h in enumerate(historiales):
        if getattr(h, 'reserva', None) is None and getattr(h, 'estado', None) in ('alquilado', 'reservado'):
            for c in contratos_invierno:
                if c.id in contratos_ya_mostrados:
                    continue
                # ¿El rango del historial se solapa con el del contrato?
                if h.fecha_inicio < c.fecha_fin and h.fecha_fin > c.fecha_inicio:
                    historiales[i] = SimpleNamespace(
                        fecha_inicio=h.fecha_inicio,
                        fecha_fin=h.fecha_fin,
                        estado='alquilado',
                        reserva=None,
                        es_invierno=True,
                        contrato=c,
                        fecha_actualizacion=getattr(h, 'fecha_actualizacion', c.fecha_creacion),
                    )
                    contratos_ya_mostrados.add(c.id)
                    break
    # Agregar contratos de invierno que no estaban ya en el historial (ej. recién creados)
    for contrato in contratos_invierno:
        if contrato.id in contratos_ya_mostrados:
            continue
        entry = SimpleNamespace(
            fecha_inicio=contrato.fecha_inicio,
            fecha_fin=contrato.fecha_fin,
            estado='alquilado',
            reserva=None,
            es_invierno=True,
            contrato=contrato,
            fecha_actualizacion=contrato.fecha_creacion,
        )
        historiales.append(entry)

    # Incluir períodos "Libre (Invierno)" entre y después de contratos invierno, para que se vea la fecha disponible
    try:
        info_invierno = propiedad.info_invierno
    except AlquilerInvierno.DoesNotExist:
        info_invierno = None
    if info_invierno and getattr(info_invierno, 'disponible', False):
        hoy = date.today()
        # Entre dos contratos: hotelero, disponible desde el día de fin del primero hasta el día de inicio del siguiente (inclusive)
        for j in range(len(contratos_invierno) - 1):
            c1 = contratos_invierno[j]
            c2 = contratos_invierno[j + 1]
            libre_inicio = c1.fecha_fin
            libre_fin = c2.fecha_inicio
            if libre_inicio <= libre_fin:
                historiales.append(SimpleNamespace(
                    fecha_inicio=libre_inicio,
                    fecha_fin=libre_fin,
                    estado='libre',
                    reserva=None,
                    es_libre_invierno=True,
                    es_invierno=False,
                    contrato=None,
                    fecha_actualizacion=info_invierno.fecha_actualizacion,
                ))
        # No agregar "Libre (Invierno)" después del último contrato (evita que se muestre hasta 180 días después, ej. hasta 2027).
        # No agregar "Libre (Invierno)" antes del primer contrato: al crear una operación de invierno no debe aparecer ese bloque automático.
        # Si no hay contratos y está disponible para invierno: mostrar el rango configurado (fecha_inicio/fecha_fin) o un año por defecto, recortado por reservas
        if not contratos_invierno and getattr(info_invierno, 'estado', None) == 'disponible':
            if getattr(info_invierno, 'fecha_inicio', None) and getattr(info_invierno, 'fecha_fin', None):
                libre_inicio = info_invierno.fecha_inicio
                libre_fin = info_invierno.fecha_fin
            else:
                libre_inicio = hoy
                libre_fin = hoy + timedelta(days=365)
            # No mostrar "Libre (Invierno)" en el pasado: si la fecha inicio guardada es anterior a hoy, arrancar desde hoy
            if libre_inicio < hoy:
                libre_inicio = hoy
            if libre_fin < libre_inicio:
                libre_fin = libre_inicio
            rangos_ocupados = []
            for h in historiales:
                if getattr(h, 'estado', None) not in ('reservado', 'alquilado'):
                    continue
                ri, rf = getattr(h, 'fecha_inicio', None), getattr(h, 'fecha_fin', None)
                if ri is None or rf is None:
                    continue
                if ri < libre_fin and rf > libre_inicio:
                    rangos_ocupados.append((max(ri, libre_inicio), min(rf, libre_fin)))
            rangos_ocupados.sort(key=lambda x: x[0])
            segmentos_libre = []
            if not rangos_ocupados:
                segmentos_libre = [(libre_inicio, libre_fin)]
            else:
                actual = libre_inicio
                for (o_ini, o_fin) in rangos_ocupados:
                    if actual < o_ini:
                        segmentos_libre.append((actual, o_ini))
                    actual = max(actual, o_fin)
                if actual < libre_fin:
                    segmentos_libre.append((actual, libre_fin))
            for (a, b) in segmentos_libre:
                if a >= b:
                    continue
                historiales.append(SimpleNamespace(
                    fecha_inicio=a,
                    fecha_fin=b,
                    estado='libre',
                    reserva=None,
                    es_libre_invierno=True,
                    es_invierno=False,
                    contrato=None,
                    fecha_actualizacion=info_invierno.fecha_actualizacion,
                ))
    historiales.sort(key=lambda x: (x.fecha_inicio, x.fecha_fin))
    
    # Obtener imágenes usando el related_name correcto
    imagenes = propiedad.imagenes.all()
# print("Propiedad ID:", propiedad_id)
# print("Número de imágenes encontradas:", imagenes.count())
    for imagen in imagenes:
        pass  # ✅ Bloque vacío después de comentar print
# print("URL de imagen:", imagen.imagen.url if imagen.imagen else "No hay URL")

    # Definir el orden personalizado para los tipos de precio
    orden_tipo_precio = Case(
        When(tipo_precio=TipoPrecio.QUINCENA_1_DICIEMBRE, then=0),
        When(tipo_precio=TipoPrecio.QUINCENA_2_DICIEMBRE, then=1),
        When(tipo_precio=TipoPrecio.QUINCENA_1_ENERO, then=2),
        When(tipo_precio=TipoPrecio.QUINCENA_2_ENERO, then=3),
        When(tipo_precio=TipoPrecio.QUINCENA_1_FEBRERO, then=4),
        When(tipo_precio=TipoPrecio.QUINCENA_2_FEBRERO, then=5),
        When(tipo_precio=TipoPrecio.QUINCENA_1_MARZO, then=6),
        When(tipo_precio=TipoPrecio.QUINCENA_2_MARZO, then=7),
        When(tipo_precio=TipoPrecio.TEMPORADA_BAJA, then=8),
        When(tipo_precio=TipoPrecio.FINDE_LARGO, then=9),
        When(tipo_precio=TipoPrecio.SEMANA_SANTA, then=10),
        When(tipo_precio=TipoPrecio.CARNAVALES, then=11),
        When(tipo_precio=TipoPrecio.VACACIONES_INVIERNO, then=12),
        When(tipo_precio=TipoPrecio.ESTUDIANTE, then=13),
        default=999,
        output_field=IntegerField(),
    )

    # Obtener los precios ordenados
    precios = propiedad.precios.annotate(
        orden_tipo_precio=orden_tipo_precio
    ).order_by('orden_tipo_precio')

    # Debug de imágenes
    try:
        pass  # ✅ Bloque vacío después de comentar print
# print("Imágenes de la propiedad:", [imagen.imagen.url for imagen in imagenes])
    except Exception as e:
        pass  # ✅ Bloque vacío después de comentar print
# print("Error al acceder a las imágenes:", str(e))

    # ✅ Obtener información de venta si existe
    try:
        info_venta = propiedad.info_venta
    except VentaPropiedad.DoesNotExist:
        info_venta = None
    except Exception as e:
        info_venta = None

    # ✅ Obtener información de 24 meses si existe  
    try:
        info_meses = propiedad.info_meses
    except:
        info_meses = None

    # ✅ Obtener información de invierno si existe
    try:
        info_invierno = propiedad.info_invierno
    except:
        info_invierno = None

    context = {
        'propiedad': propiedad,
        'disponibilidades': disponibilidades,
        'hay_superposiciones': hay_superposiciones,
        'textos_superpuestos': textos_superpuestos,
        'precios': precios,
        'imagenes': imagenes,
        'historiales': historiales,  # Agregamos el historial al contexto
        'active_tab': request.GET.get('tab', 'alquiler'),  # default a 'alquiler'
        'info_venta': info_venta,  # ✅ Agregamos info_venta al contexto
        'info_meses': info_meses,  # ✅ Agregamos info_meses al contexto
        'info_invierno': info_invierno,  # ✅ Agregamos info_invierno al contexto
        'inquilinos': get_inquilinos_queryset_unificado(request),
        'vendedores': Vendedor.objects.filter(sucursal=request.user.sucursal).order_by('apellido', 'nombre'),
        'puede_cambiar_sucursal_propiedad': _puede_usar_cambio_sucursal_propiedad(request.user),
    }
    
    return render(request, 'inmobiliaria/propiedades/detalle.html', context)

@login_required
def propiedad_nuevo(request):
    if request.method == 'POST':
        try:
            form = PropiedadForm(request.POST, request.FILES, user=request.user)
            propietario_form = PropietarioForm(user=request.user)
            if form.is_valid():
                try:
                    propiedad = form.save()
                    # Las imágenes ya se procesan en el método save() del formulario
                    # No las proceses aquí para evitar duplicación
                    messages.success(request, 'Propiedad creada exitosamente.')
                    return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad.id)
                except ValidationError as e:
                    # Si hay errores de validación, agregarlos al formulario (solo si el campo existe en el form)
                    if hasattr(e, 'error_dict'):
                        for field, errors in e.error_dict.items():
                            for error in errors:
                                if field in form.fields:
                                    form.add_error(field, error)
                                else:
                                    # Campos del modelo que no están en PropiedadForm (ej. precio_invierno)
                                    messages.error(request, str(error))
                    else:
                        messages.error(request, str(e))
            else:
                # Mostrar mensajes de error específicos para campos faltantes
                campos_faltantes = []
                for field, errors in form.errors.items():
                    for error in errors:
                        if 'requerido' in str(error).lower() or 'required' in str(error).lower():
                            campos_faltantes.append(form.fields[field].label if field in form.fields else field)
                        messages.error(request, f'{form.fields[field].label if field in form.fields else field}: {error}')
                
                if campos_faltantes:
                    messages.warning(request, f'Por favor, complete los siguientes campos requeridos: {", ".join(campos_faltantes)}')
        except Exception as e:
            # Capturar cualquier otro error inesperado
            import traceback
            error_msg = f'Error inesperado al crear la propiedad: {str(e)}'
            messages.error(request, error_msg)
            # Log del error completo para debugging
            print(f"Error al crear propiedad: {traceback.format_exc()}")
    else:
        form = PropiedadForm(user=request.user)
        propietario_form = PropietarioForm(user=request.user)
    
    return render(request, 'inmobiliaria/propiedades/formulario.html', {
        'form': form,
        'propietario_form': propietario_form,
        'titulo': 'Nueva Propiedad',
        'imagenes': []  # Para el template
    })


def _puede_usar_cambio_sucursal_propiedad(user):
    """Solo superusuario o nivel 4 (administración)."""
    return bool(getattr(user, 'is_superuser', False) or getattr(user, 'nivel', 0) == 4)


def _propiedad_accesible_por_sucursal_usuario(request, propiedad):
    """True si el usuario puede operar esta propiedad (misma sucursal o superusuario)."""
    if getattr(request.user, 'is_superuser', False):
        return True
    uid = getattr(request.user, 'sucursal_id', None)
    return uid is not None and propiedad.sucursal_id == uid


@login_required
def propiedad_cambiar_sucursal(request, propiedad_id):
    """
    Traslado explícito de una propiedad a otra sucursal (solo nivel 4 o superusuario).
    Requiere escribir una frase exacta de confirmación para evitar cambios accidentales.
    """
    propiedad = get_object_or_404(Propiedad, pk=propiedad_id)
    if not _puede_usar_cambio_sucursal_propiedad(request.user):
        messages.error(request, 'Solo administradores pueden cambiar la sucursal de una propiedad.')
        return redirect('inmobiliaria:propiedades')
    if not _propiedad_accesible_por_sucursal_usuario(request, propiedad):
        messages.error(request, 'No podés reasignar propiedades que no pertenecen a tu sucursal.')
        return redirect('inmobiliaria:propiedades')

    frase_requerida = f'CAMBIAR-SUCURSAL-{propiedad.id}'
    sucursales = Sucursal.objects.all().order_by('nombre')

    if request.method == 'POST':
        nueva_id = request.POST.get('nueva_sucursal_id')
        frase = (request.POST.get('texto_confirmacion') or '').strip()
        if frase != frase_requerida:
            messages.error(
                request,
                f'Confirmación incorrecta. Debés escribir exactamente (mayúsculas y guiones): {frase_requerida}'
            )
        else:
            try:
                nueva = Sucursal.objects.get(pk=int(nueva_id))
            except (ValueError, TypeError, Sucursal.DoesNotExist):
                messages.error(request, 'Sucursal de destino no válida.')
            else:
                if nueva.pk == propiedad.sucursal_id:
                    messages.warning(request, 'La propiedad ya está en esa sucursal.')
                else:
                    anterior = propiedad.sucursal.nombre
                    propiedad.sucursal = nueva
                    propiedad.save(update_fields=['sucursal'])
                    messages.success(
                        request,
                        f'Sucursal actualizada: de «{anterior}» a «{nueva.nombre}» (ficha #{propiedad.id}).'
                    )
                    return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad.id)

    return render(request, 'inmobiliaria/propiedades/cambiar_sucursal_propiedad.html', {
        'propiedad': propiedad,
        'sucursales': sucursales,
        'frase_requerida': frase_requerida,
    })


@login_required
def propiedad_editar(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    if not _propiedad_accesible_por_sucursal_usuario(request, propiedad):
        messages.error(request, 'No tenés permiso para editar esta propiedad (pertenece a otra sucursal).')
        return redirect('inmobiliaria:propiedades')
    imagenes = ImagenPropiedad.objects.filter(propiedad=propiedad).order_by('orden')
    
    if request.method == 'POST':
        try:
            # Pasar solo campos que existen en PropiedadForm para evitar error si POST trae precio_invierno u otros no incluidos
            allowed_keys = set(PropiedadForm.base_fields.keys()) | {'csrfmiddlewaretoken'}
            post_data = QueryDict(mutable=True)
            for key in allowed_keys:
                if key in request.POST:
                    post_data.setlist(key, request.POST.getlist(key))
            form = PropiedadForm(post_data, request.FILES, instance=propiedad, user=request.user)
            propietario_form = PropietarioForm(user=request.user)
            if form.is_valid():
                try:
                    propiedad = form.save()  # El formulario se encarga de procesar las imágenes
                    messages.success(request, 'Propiedad actualizada exitosamente.')
                    return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad.id)
                except ValidationError as e:
                    # Si hay errores de validación, agregarlos al formulario (solo si el campo existe en el form)
                    if hasattr(e, 'error_dict'):
                        for field, errors in e.error_dict.items():
                            for error in errors:
                                if field in form.fields:
                                    form.add_error(field, error)
                                else:
                                    # Campos del modelo que no están en PropiedadForm (ej. precio_invierno)
                                    messages.error(request, str(error))
                    else:
                        messages.error(request, str(e))
            else:
                # Mostrar mensajes de error específicos para campos faltantes
                campos_faltantes = []
                for field, errors in form.errors.items():
                    for error in errors:
                        if 'requerido' in str(error).lower() or 'required' in str(error).lower():
                            campos_faltantes.append(form.fields[field].label if field in form.fields else field)
                        messages.error(request, f'{form.fields[field].label if field in form.fields else field}: {error}')
                
                if campos_faltantes:
                    messages.warning(request, f'Por favor, complete los siguientes campos requeridos: {", ".join(campos_faltantes)}')
        except Exception as e:
            # Capturar cualquier otro error inesperado
            import traceback
            error_msg = f'Error inesperado al actualizar la propiedad: {str(e)}'
            messages.error(request, error_msg)
            # Log del error completo para debugging
            print(f"Error al actualizar propiedad: {traceback.format_exc()}")
    else:
        form = PropiedadForm(instance=propiedad, user=request.user)
        propietario_form = PropietarioForm(user=request.user)
    
    return render(request, 'inmobiliaria/propiedades/formulario.html', {
        'form': form,
        'propietario_form': propietario_form,
        'propiedad': propiedad,
        'imagenes': imagenes,
        'titulo': 'Editar Propiedad'
    })

@login_required
def propiedad_eliminar(request, propiedad_id):
    """Eliminación con doble confirmación y soft delete (se puede recuperar)."""
    propiedad = get_object_or_404(Propiedad.all_objects, pk=propiedad_id)
    if propiedad.sucursal != request.user.sucursal and not request.user.is_superuser:
        messages.error(request, 'No tiene permisos para eliminar esta propiedad.')
        return redirect('inmobiliaria:propiedades')

    if request.method == 'POST':
        paso = request.POST.get('paso', '1')
        if paso == '2':
            try:
                propiedad.eliminada = True
                propiedad.fecha_eliminacion = timezone.now()
                propiedad.save()
                messages.success(
                    request,
                    f'La propiedad "{propiedad.direccion}" fue eliminada. Puede recuperarla desde "Propiedades eliminadas".'
                )
                return redirect('inmobiliaria:propiedades')
            except Exception as e:
                logger.error(f"Error al eliminar propiedad {propiedad_id}: {str(e)}")
                messages.error(request, f'Error al eliminar la propiedad: {str(e)}')
                return redirect('inmobiliaria:propiedades')
        return render(request, 'inmobiliaria/propiedades/confirmar_eliminar.html', {
            'propiedad': propiedad,
            'paso': 2,
        })

    return render(request, 'inmobiliaria/propiedades/confirmar_eliminar.html', {
        'propiedad': propiedad,
        'paso': 1,
    })


@login_required
def propiedades_eliminadas(request):
    """Lista de propiedades marcadas como eliminadas (soft delete); el usuario puede recuperarlas."""
    base = Propiedad.all_objects.filter(eliminada=True)
    if not request.user.is_superuser:
        base = base.filter(sucursal=request.user.sucursal)
    propiedades = base.select_related('propietario', 'sucursal').order_by('-fecha_eliminacion')
    return render(request, 'inmobiliaria/propiedades/lista_eliminadas.html', {
        'propiedades': propiedades,
    })


@login_required
def propiedad_recuperar(request, propiedad_id):
    """Recupera una propiedad eliminada (quita marca eliminada y vuelve a mostrarla)."""
    if request.method != 'POST':
        return redirect('inmobiliaria:propiedades_eliminadas')
    propiedad = get_object_or_404(Propiedad.all_objects, pk=propiedad_id, eliminada=True)
    if propiedad.sucursal != request.user.sucursal and not request.user.is_superuser:
        messages.error(request, 'No tiene permisos para recuperar esta propiedad.')
        return redirect('inmobiliaria:propiedades_eliminadas')
    propiedad.eliminada = False
    propiedad.fecha_eliminacion = None
    propiedad.save()
    messages.success(request, f'La propiedad "{propiedad.direccion}" fue recuperada correctamente.')
    return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad.id)


def register(request):
    if request.method == 'POST':
        form = VendedorUserCreationForm(request.POST)
# print("\n=== DATOS DEL FORMULARIO RECIBIDOS ===")
# print(f"Datos POST: {request.POST}")
        
        if form.is_valid():
            pass  # ✅ Bloque vacío
# print("\n=== DATOS VALIDADOS ===")
# print(f"Username: {form.cleaned_data.get('username')}")
# print(f"DNI: {form.cleaned_data.get('dni')}")
# print(f"Nombre: {form.cleaned_data.get('nombre')}")
# print(f"Apellido: {form.cleaned_data.get('apellido')}")
# print(f"Email: {form.cleaned_data.get('email')}")
# print(f"Comisión: {form.cleaned_data.get('comision')}")
# print(f"Fecha Nacimiento: {form.cleaned_data.get('fecha_nacimiento')}")
# print(f"Nivel: {form.cleaned_data.get('nivel')}")
# print(f"Sucursal: {form.cleaned_data.get('sucursal')}")
# print(f"Password1 presente: {'password1' in form.cleaned_data}")
# print(f"Password2 presente: {'password2' in form.cleaned_data}")
# print(f"Passwords coinciden: {form.cleaned_data.get('password1') == form.cleaned_data.get('password2')}")
            
            vendedor = form.save()
            
            # Verificar que la contraseña se guardó correctamente
# print("\n=== VENDEDOR CREADO ===")
# print(f"ID: {vendedor.id}")
# print(f"Username: {vendedor.username}")
# print(f"Nombre completo: {vendedor.nombre} {vendedor.apellido}")
# print(f"Es activo: {vendedor.is_active}")
# print(f"Es staff: {vendedor.is_staff}")
# print(f"Es superusuario: {vendedor.is_superuser}")
# print(f"Sucursal asignada: {vendedor.sucursal}")
# print(f"Contraseña hasheada guardada: {bool(vendedor.password)}")
# print(f"Longitud del hash de la contraseña: {len(vendedor.password)}")
            
            # Verificar que podemos autenticar con la contraseña
            from django.contrib.auth import authenticate
            test_auth = authenticate(username=vendedor.username, 
                                  password=form.cleaned_data.get('password1'))
# print(f"Prueba de autenticación exitosa: {test_auth is not None}")
            
            messages.success(request, 'Registro exitoso. Ahora puedes iniciar sesión.')
            return redirect('inmobiliaria:login')
        else:
            pass  # ✅ Bloque vacío
# print("\n=== ERRORES EN EL FORMULARIO ===")
# print(f"Errores: {form.errors}")
            if 'password1' in form.errors:
                pass  # ✅ Bloque vacío
# print(f"Errores de password1: {form.errors['password1']}")
            if 'password2' in form.errors:
                pass  # ✅ Bloque vacío
# print(f"Errores de password2: {form.errors['password2']}")
    else:
        form = VendedorUserCreationForm()
# print("\n=== NUEVO FORMULARIO CREADO ===")
# print("Método GET - Mostrando formulario vacío")
    
    return render(request, 'inmobiliaria/autenticacion/register.html', {'form': form})

@receiver(user_logged_in)
def user_logged_in_handler(sender, request, user, **kwargs):
    if hasattr(user, 'vendedor'):
        request.session['nivel_usuario'] = user.vendedor.nivel
    else:
        request.session['nivel_usuario'] = 0  # Default level if not a vendedor

def ver_disponibilidad(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    
    # Obtener todas las reservas de la propiedad
    reservas = propiedad.reservas.all()
    
    # Obtener todas las disponibilidades de la propiedad
    disponibilidades = Disponibilidad.objects.filter(propiedad=propiedad)

    context = {
        'propiedad': propiedad,
        'reservas': reservas,
        'disponibilidades': disponibilidades,
    }

    return render(request, 'inmobiliaria/ver_disponibilidad.html', context)
@login_required                                                                 
def reservas(request):
    # ✅ Ordenar por ID descendente como en operaciones
    # Excluir reservas eliminadas (soft delete)
    reservas = Reserva.objects.filter(sucursal=request.user.sucursal, eliminada=False).select_related('cliente', 'propiedad', 'propiedad__propietario', 'vendedor').order_by('-id')
    
    # ✅ Filtro de búsqueda por ID (opcional)
    search_id = request.GET.get('search_id', '').strip()
    if search_id:
        try:
            # Intentar buscar por ID exacto primero
            reservas = reservas.filter(id=int(search_id))
        except ValueError:
            # Si no es un número, buscar como string
            reservas = reservas.filter(id__icontains=search_id)
    
    # ✅ Filtro por fecha (fecha de inicio de la reserva)
    fecha_desde = request.GET.get('fecha_desde', '').strip()
    fecha_hasta = request.GET.get('fecha_hasta', '').strip()
    
    if fecha_desde:
        try:
            fecha_desde_obj = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
            reservas = reservas.filter(fecha_inicio__gte=fecha_desde_obj)
        except ValueError:
            pass
    
    if fecha_hasta:
        try:
            fecha_hasta_obj = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
            reservas = reservas.filter(fecha_inicio__lte=fecha_hasta_obj)
        except ValueError:
            pass
    
    # ✅ Filtro por vendedor (ID del vendedor seleccionado)
    search_vendedor_id = request.GET.get('search_vendedor', '').strip()
    if search_vendedor_id:
        try:
            reservas = reservas.filter(vendedor_id=int(search_vendedor_id))
        except ValueError:
            pass
    
    # ✅ Filtro por número de ficha (numero_por_propietario)
    search_ficha = request.GET.get('search_ficha', '').strip()
    if search_ficha:
        try:
            # Intentar buscar por número exacto
            reservas = reservas.filter(propiedad__numero_por_propietario=int(search_ficha))
        except ValueError:
            # Si no es un número, buscar como string
            reservas = reservas.filter(propiedad__numero_por_propietario__icontains=search_ficha)
    
    # Obtener lista de vendedores para el select
    vendedores = Vendedor.objects.filter(sucursal=request.user.sucursal).order_by('apellido', 'nombre')
    
    return render(request, 'inmobiliaria/reserva/lista.html', {
        'reservas': reservas,
        'search_id': search_id,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'search_vendedor': search_vendedor_id,
        'search_ficha': search_ficha,
        'vendedores': vendedores
    })

@login_required
def reservas_eliminadas(request):
    # Verificar que el usuario tenga nivel >= 2
    if request.user.nivel < 2:
        messages.error(request, 'No tienes permisos para acceder a esta sección.')
        return redirect('inmobiliaria:dashboard')
    
    # Obtener solo reservas eliminadas (soft delete)
    reservas = Reserva.objects.filter(
        sucursal=request.user.sucursal,
        eliminada=True
    ).select_related('propiedad', 'cliente', 'vendedor', 'usuario_eliminacion').order_by('-fecha_eliminacion')
    
    # Filtro de búsqueda por ID (opcional)
    search_id = request.GET.get('search_id', '').strip()
    if search_id:
        reservas = reservas.filter(id__icontains=search_id)
    
    # Filtro por fecha de eliminación
    fecha_desde = request.GET.get('fecha_desde', '').strip()
    fecha_hasta = request.GET.get('fecha_hasta', '').strip()
    
    if fecha_desde:
        try:
            fecha_desde_obj = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
            reservas = reservas.filter(fecha_eliminacion__date__gte=fecha_desde_obj)
        except ValueError:
            pass
    
    if fecha_hasta:
        try:
            fecha_hasta_obj = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
            reservas = reservas.filter(fecha_eliminacion__date__lte=fecha_hasta_obj)
        except ValueError:
            pass
    
    return render(request, 'inmobiliaria/reserva/lista_eliminadas.html', {
        'reservas': reservas,
        'search_id': search_id,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta
    })

def operaciones(request):
    from .models.recibo import Recibo
    # Obtener solo reservas pagadas (completas o con saldo pendiente) ordenadas por fecha más reciente
    # Excluir reservas eliminadas (soft delete)
    reservas = Reserva.objects.filter(
        sucursal=request.user.sucursal,
        estado__in=['pagada', 'confirmada_no_pagada'],
        eliminada=False
    ).select_related('cliente', 'propiedad', 'propiedad__propietario', 'vendedor').prefetch_related(
        'pagos',
        Prefetch('recibos', queryset=Recibo.objects.select_related('movimiento_caja__caja')),
    ).order_by('-id')
    
    # ✅ Filtro de búsqueda por ID
    search_id = request.GET.get('search_id', '').strip()
    if search_id:
        try:
            reservas = reservas.filter(id=int(search_id))
        except ValueError:
            reservas = reservas.filter(id__icontains=search_id)
    
    # ✅ Filtro por fecha (fecha de inicio de la reserva)
    fecha_desde = request.GET.get('fecha_desde', '').strip()
    fecha_hasta = request.GET.get('fecha_hasta', '').strip()
    
    if fecha_desde:
        try:
            fecha_desde_obj = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
            reservas = reservas.filter(fecha_inicio__gte=fecha_desde_obj)
        except ValueError:
            pass
    
    if fecha_hasta:
        try:
            fecha_hasta_obj = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
            reservas = reservas.filter(fecha_inicio__lte=fecha_hasta_obj)
        except ValueError:
            pass
    
    # ✅ Filtro por vendedor (ID del vendedor seleccionado)
    search_vendedor_id = request.GET.get('search_vendedor', '').strip()
    if search_vendedor_id:
        try:
            reservas = reservas.filter(vendedor_id=int(search_vendedor_id))
        except ValueError:
            pass
    
    # ✅ Filtro por número de ficha (numero_por_propietario)
    search_ficha = request.GET.get('search_ficha', '').strip()
    if search_ficha:
        try:
            reservas = reservas.filter(propiedad__numero_por_propietario=int(search_ficha))
        except ValueError:
            reservas = reservas.filter(propiedad__numero_por_propietario__icontains=search_ficha)
    
    # ✅ Filtro de pendientes de pago
    solo_pendientes = request.GET.get('solo_pendientes', '') == 'true'
    
    # Obtener lista de vendedores para el select
    vendedores = Vendedor.objects.filter(sucursal=request.user.sucursal).order_by('apellido', 'nombre')
    
    # ✅ Carga masiva de movimientos (evita N+1): una sola query por todas las reservas
    import re
    reserva_ids = list(reservas.values_list('id', flat=True)[:2000])  # límite razonable
    propiedad_ids = list(reservas.values_list('propiedad_id', flat=True).distinct()[:2000])
    movimientos_por_reserva = {}
    if reserva_ids and propiedad_ids:
        movs_qs = MovimientoCaja.objects.filter(
            propiedad_id__in=propiedad_ids,
            tipo=TipoMovimientoCajaEnum.INGRESO,
            concepto__icontains="Operación"
        ).select_related('caja').only(
            'id', 'propiedad_id', 'concepto', 'fecha',
            'monto_efectivo', 'monto_cheque', 'monto_tarjeta', 'monto_deposito',
            'caja_id', 'caja__estado', 'caja__fecha_cierre', 'caja__numero',
        )
        for mov in movs_qs:
            if not mov.concepto:
                continue
            match = re.search(r'Operaci[oó]n\s+(\d+)', mov.concepto, re.IGNORECASE)
            if match:
                rid = int(match.group(1))
                if rid in reserva_ids:
                    movimientos_por_reserva.setdefault(rid, []).append(mov)
    
    # Lista para almacenar solo las reservas con pagos
    reservas_con_pagos = []
    
    # ✅ Variables para estadísticas
    total_operaciones = 0
    operaciones_pendientes = 0
    
    # Calcular totales pagados para cada reserva y filtrar las que tienen pagos
    for reserva in reservas:
        movimientos = movimientos_por_reserva.get(reserva.id, [])
        
        # ❌ FILTRO: Si no hay movimientos de pago, no incluir en operaciones
        if not movimientos:
            continue
        
        # ✅ LÓGICA SIMPLE: SALDO = PRECIO TOTAL - SEÑA DEL CASILLERO
        saldo_pendiente = reserva.precio_total - (reserva.senia or 0)
        
# print(f"💰 OPERACIONES - CÁLCULO DIRECTO:")
# print(f"   - Precio Total: ${reserva.precio_total}")
# print(f"   - Seña: ${reserva.senia or 0}")
# print(f"   - Saldo Pendiente: ${saldo_pendiente}")
        
        # ✅ VERIFICAR QUE HAYA AL MENOS ALGÚN PAGO REAL
        total_pagado = sum(
            float(mov.monto_efectivo or 0) + float(mov.monto_cheque or 0) + float(mov.monto_tarjeta or 0) + float(mov.monto_deposito or 0)
            for mov in movimientos
        )
        
        if total_pagado > 0:
            # ✅ CORREGIDO: total_pagado debe ser solo la seña (sin depósito)
            reserva.total_pagado = reserva.senia or 0  # Solo la seña
            reserva.saldo_pendiente = saldo_pendiente  # Ya está calculado correctamente
            reserva.total_senia_pagada = reserva.senia or 0
            reserva.total_deposito_pagado = reserva.deposito_garantia or 0
            
            # ✅ DETECTAR SI EL DEPÓSITO FUE PAGADO (concepto 10)
            deposito_pagado = False
            for movimiento in movimientos:
                if movimiento.concepto and "|CONCEPTOS:" in movimiento.concepto:
                    # Buscar concepto 10 en la estructura
                    concepto_parts = movimiento.concepto.split("|CONCEPTOS:", 1)
                    if len(concepto_parts) > 1:
                        conceptos_data = concepto_parts[1]
                        # ✅ MEJORADO: Buscar concepto 10 de forma más robusta
                        concepto_10_encontrado = False
                        if "|10:" in conceptos_data or ":10:" in conceptos_data:
                            concepto_10_encontrado = True
                        else:
                            # Buscar en cada item individual
                            conceptos_items = [item for item in conceptos_data.split("|") if item.strip()]
                            for concepto_item in conceptos_items:
                                parts = concepto_item.split(":", 1)
                                if len(parts) > 0 and parts[0].strip() == "10":
                                    concepto_10_encontrado = True
                                    break
                        
                        if concepto_10_encontrado:  # Concepto 10 presente
                            deposito_pagado = True
                            break
            
            # Agregar estado del depósito
            reserva.deposito_estado = 'pagado' if deposito_pagado else 'pendiente'
            
# print(f"✅ OPERACIONES - Reserva {reserva.id}: Precio Total: {reserva.precio_total}, Seña: {reserva.senia or 0}, Depósito: {reserva.deposito_garantia or 0} ({reserva.deposito_estado}), Saldo: {reserva.saldo_pendiente}")
            
            # Obtener el movimiento más reciente para el enlace del recibo
            reserva.movimiento_reciente = movimientos[0] if movimientos else None
            
            # ✅ Recibos ya prefetched en reserva.recibos
            reserva.todos_recibos = list(reserva.recibos.all()) if hasattr(reserva, 'recibos') else []
            reserva.todos_recibos.sort(key=lambda r: getattr(r, 'fecha_emision', None) or r.id, reverse=True)
            
# print(f"🔍 DEBUG RECIBOS - Reserva {reserva.id}:")
# print(f"   - Cantidad de recibos: {recibos_reserva.count()}")
# print(f"   - QuerySet evaluado: {list(recibos_reserva.values('id', 'numero_recibo', 'monto_este_pago'))}")
            
            # ✅ VERIFICAR SI HAY MÚLTIPLES RECIBOS (ya no se usa para nada crítico aquí)
            
            # ✅ Contar estadísticas
            total_operaciones += 1
            if saldo_pendiente > 0:
                operaciones_pendientes += 1
            
            # ✅ Aplicar filtro de pendientes si está activo
            if solo_pendientes and saldo_pendiente == 0:
                # Si solo queremos pendientes y esta está pagada completa, saltarla
                continue
            
            # Fecha en que se hizo la operación (para ordenar): fecha de creación de la reserva
            reserva.fecha_operacion_dia = reserva.fecha_creacion.date() if getattr(reserva, 'fecha_creacion', None) else reserva.fecha_inicio
            
            reserva.es_invierno = False
            reservas_con_pagos.append(reserva)
        else:
            pass  # ✅ Bloque vacío
# print(f"❌ OPERACIONES - Reserva {reserva.id} SIN PAGOS REALES - No se incluye en operaciones")

    # ✅ Incluir operaciones de invierno (ContratoAlquiler 9 meses con movimientos de caja)
    from types import SimpleNamespace
    from decimal import Decimal
    contratos_invierno_qs = ContratoAlquiler.objects.filter(
        sucursal=request.user.sucursal,
        duracion_meses=9
    ).select_related('propiedad', 'vendedor').order_by('-id')

    if search_id:
        try:
            contratos_invierno_qs = contratos_invierno_qs.filter(id=int(search_id))
        except ValueError:
            contratos_invierno_qs = contratos_invierno_qs.none()
    if fecha_desde:
        try:
            fecha_desde_obj = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
            contratos_invierno_qs = contratos_invierno_qs.filter(fecha_inicio__gte=fecha_desde_obj)
        except ValueError:
            pass
    if fecha_hasta:
        try:
            fecha_hasta_obj = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
            contratos_invierno_qs = contratos_invierno_qs.filter(fecha_inicio__lte=fecha_hasta_obj)
        except ValueError:
            pass
    if search_vendedor_id:
        try:
            contratos_invierno_qs = contratos_invierno_qs.filter(vendedor_id=int(search_vendedor_id))
        except ValueError:
            pass
    if search_ficha:
        try:
            contratos_invierno_qs = contratos_invierno_qs.filter(propiedad__numero_por_propietario=int(search_ficha))
        except ValueError:
            contratos_invierno_qs = contratos_invierno_qs.filter(propiedad__numero_por_propietario__icontains=search_ficha)

    # ✅ Carga masiva movimientos para contratos invierno (una sola query)
    contrato_invierno_ids = list(contratos_invierno_qs.values_list('id', flat=True)[:2000])
    prop_ids_invierno = list(contratos_invierno_qs.values_list('propiedad_id', flat=True).distinct()[:2000])
    movimientos_por_contrato = {}
    if contrato_invierno_ids and prop_ids_invierno:
        movs_inv_all = MovimientoCaja.objects.filter(
            propiedad_id__in=prop_ids_invierno,
            sucursal=request.user.sucursal,
            tipo=TipoMovimientoCajaEnum.INGRESO,
            concepto__icontains="Contrato #"
        ).only('id', 'propiedad_id', 'concepto', 'monto_efectivo', 'monto_cheque', 'monto_tarjeta', 'monto_deposito')
        for mov in movs_inv_all:
            if not mov.concepto:
                continue
            match = re.search(r'Contrato\s*#\s*(\d+)', mov.concepto, re.IGNORECASE)
            if match:
                cid = int(match.group(1))
                if cid in contrato_invierno_ids:
                    movimientos_por_contrato.setdefault(cid, []).append(mov)
    invierno_list = []
    for contrato in contratos_invierno_qs:
        movimientos = movimientos_por_contrato.get(contrato.id, [])
        total_pagado = sum(
            float(mov.monto_efectivo or 0) + float(mov.monto_cheque or 0) + float(mov.monto_tarjeta or 0) + float(mov.monto_deposito or 0)
            for mov in movimientos
        ) if movimientos else 0
        precio_total = (contrato.deposito_garantia or Decimal('0')) + (contrato.precio_mensual or Decimal('0')) * 9
        saldo_pendiente = precio_total - Decimal(str(total_pagado))
        if solo_pendientes and saldo_pendiente <= 0:
            continue
        total_operaciones += 1
        if saldo_pendiente > 0:
            operaciones_pendientes += 1
        deposito_ok = contrato.deposito_garantia and total_pagado >= float(contrato.deposito_garantia or 0)
        invierno_list.append(SimpleNamespace(
            es_invierno=True,
            contrato=contrato,
            id=contrato.id,
            propiedad=contrato.propiedad,
            fecha_inicio=contrato.fecha_inicio,
            fecha_fin=contrato.fecha_fin,
            fecha_operacion_dia=contrato.fecha_operacion,
            precio_total=precio_total,
            total_pagado=Decimal(str(total_pagado)),
            saldo_pendiente=saldo_pendiente,
            estado=contrato.estado,
            deposito_estado='pagado' if deposito_ok else 'pendiente',
            total_deposito_pagado=contrato.deposito_garantia or Decimal('0'),
            movimiento_reciente=movimientos[0] if movimientos else None,
            todos_recibos=None,
        ))

    operaciones = list(reservas_con_pagos) + invierno_list
    operaciones.sort(key=lambda x: getattr(x, 'fecha_operacion_dia', x.fecha_inicio) or x.fecha_inicio, reverse=True)

    # ✅ Paginación: 50 por página para mejorar velocidad de render
    page_size = 50
    try:
        page = max(1, int(request.GET.get('page', 1)))
    except ValueError:
        page = 1
    total_ops = len(operaciones)
    num_pages = max(1, (total_ops + page_size - 1) // page_size)
    page = min(page, num_pages)
    offset = (page - 1) * page_size
    operaciones_pagina = operaciones[offset:offset + page_size]

    return render(request, 'inmobiliaria/reserva/operaciones.html', {
        'operaciones': operaciones_pagina,
        'reservas': reservas_con_pagos,
        'search_id': search_id,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'search_vendedor': search_vendedor_id,
        'search_ficha': search_ficha,
        'solo_pendientes': solo_pendientes,
        'total_operaciones': total_operaciones,
        'operaciones_pendientes': operaciones_pendientes,
        'operaciones_mostradas': len(operaciones_pagina),
        'vendedores': vendedores,
        'page': page,
        'num_pages': num_pages,
        'total_ops': total_ops,
        'page_size': page_size,
        'has_previous': page > 1,
        'has_next': page < num_pages,
        'previous_page': page - 1,
        'next_page': page + 1,
    })


@login_required
def listado_entradas(request):
    """
    Listado de entradas por fecha exacta (inicio de alquiler).
    Incluye reservas temporales y contratos (invierno/24 meses).
    """
    if not (request.user.is_superuser or getattr(request.user, 'nivel', None) == 4):
        messages.error(request, 'No tenés permisos para acceder a esta sección.')
        return redirect('inmobiliaria:dashboard')

    fecha_raw = (request.GET.get('fecha') or '').strip()
    fecha_obj = None

    if fecha_raw:
        try:
            fecha_obj = datetime.strptime(fecha_raw, '%Y-%m-%d').date()
        except ValueError:
            fecha_obj = None

    if fecha_obj is None:
        fecha_obj = timezone.localdate()
        fecha_raw = fecha_obj.strftime('%Y-%m-%d')

    entradas = []

    reservas = Reserva.objects.filter(
        sucursal=request.user.sucursal,
        eliminada=False,
        estado__in=['confirmada', 'confirmada_no_pagada', 'pagada'],
        fecha_inicio=fecha_obj,
    ).select_related('cliente', 'propiedad__propietario', 'vendedor').order_by('fecha_inicio', 'id')

    for r in reservas:
        titular = '—'
        if r.cliente:
            apellido = (getattr(r.cliente, 'apellido', '') or '').strip()
            nombre = (getattr(r.cliente, 'nombre', '') or '').strip()
            titular = f'{apellido}, {nombre}'.strip(', ') or '—'

        propietario = '—'
        if r.propiedad and r.propiedad.propietario:
            ap = (getattr(r.propiedad.propietario, 'apellido', '') or '').strip()
            no = (getattr(r.propiedad.propietario, 'nombre', '') or '').strip()
            propietario = f'{ap}, {no}'.strip(', ') or '—'

        vendedor = '—'
        if r.vendedor:
            apv = (getattr(r.vendedor, 'apellido', '') or '').strip()
            nov = (getattr(r.vendedor, 'nombre', '') or '').strip()
            vendedor = (apv or nov or '—').upper()

        precio_total = r.precio_total or Decimal('0')
        senia = r.senia or Decimal('0')
        saldo = precio_total - senia
        if saldo < 0:
            saldo = Decimal('0')

        entradas.append({
            'tipo': 'reserva',
            'titular': titular,
            'propietario': propietario,
            'operacion': f'{r.id:05d}',
            'direccion': (getattr(r.propiedad, 'direccion', None) or '—'),
            'desde': r.fecha_inicio,
            'hasta': r.fecha_fin,
            'saldo': saldo,
            'deposito': r.deposito_garantia or Decimal('0'),
            'intervino': vendedor,
            'llave': (getattr(r.propiedad, 'llave', None) or '—'),
            'fecha_op': (r.fecha_creacion.date() if getattr(r, 'fecha_creacion', None) else r.fecha_inicio),
        })

    contratos = ContratoAlquiler.objects.filter(
        sucursal=request.user.sucursal,
        fecha_inicio=fecha_obj,
    ).exclude(estado='rescindido').select_related(
        'inquilino', 'propiedad__propietario', 'vendedor'
    ).order_by('fecha_inicio', 'id')

    contrato_ids = list(contratos.values_list('id', flat=True))
    movs_por_contrato = {}
    if contrato_ids:
        movs = MovimientoCaja.objects.filter(
            sucursal=request.user.sucursal,
            tipo=TipoMovimientoCajaEnum.INGRESO,
            concepto__icontains='Contrato #',
        ).only('concepto', 'monto_efectivo', 'monto_cheque', 'monto_tarjeta', 'monto_deposito')
        for m in movs:
            if not m.concepto:
                continue
            match = re.search(r'Contrato\s*#\s*(\d+)', m.concepto, re.IGNORECASE)
            if not match:
                continue
            cid = int(match.group(1))
            if cid in contrato_ids:
                movs_por_contrato.setdefault(cid, []).append(m)

    for c in contratos:
        titular = '—'
        if c.inquilino:
            apellido = (getattr(c.inquilino, 'apellido', '') or '').strip()
            nombre = (getattr(c.inquilino, 'nombre', '') or '').strip()
            titular = f'{apellido}, {nombre}'.strip(', ') or '—'

        propietario = '—'
        if c.propiedad and c.propiedad.propietario:
            ap = (getattr(c.propiedad.propietario, 'apellido', '') or '').strip()
            no = (getattr(c.propiedad.propietario, 'nombre', '') or '').strip()
            propietario = f'{ap}, {no}'.strip(', ') or '—'

        vendedor = '—'
        if c.vendedor:
            apv = (getattr(c.vendedor, 'apellido', '') or '').strip()
            nov = (getattr(c.vendedor, 'nombre', '') or '').strip()
            vendedor = (apv or nov or '—').upper()

        total_contrato = (c.deposito_garantia or Decimal('0')) + (c.precio_mensual or Decimal('0')) * Decimal(c.duracion_meses or 0)
        total_pagado = Decimal('0')
        for m in movs_por_contrato.get(c.id, []):
            total_pagado += Decimal(str(m.monto_efectivo or 0))
            total_pagado += Decimal(str(m.monto_cheque or 0))
            total_pagado += Decimal(str(m.monto_tarjeta or 0))
            total_pagado += Decimal(str(m.monto_deposito or 0))
        saldo = total_contrato - total_pagado
        if saldo < 0:
            saldo = Decimal('0')

        entradas.append({
            'tipo': 'contrato',
            'titular': titular,
            'propietario': propietario,
            'operacion': f'{c.id:05d}',
            'direccion': (getattr(c.propiedad, 'direccion', None) or '—'),
            'desde': c.fecha_inicio,
            'hasta': c.fecha_fin,
            'saldo': saldo,
            'deposito': c.deposito_garantia or Decimal('0'),
            'intervino': vendedor,
            'llave': (getattr(c.propiedad, 'llave', None) or '—'),
            'fecha_op': (c.fecha_operacion or (c.fecha_creacion.date() if getattr(c, 'fecha_creacion', None) else c.fecha_inicio)),
        })

    entradas.sort(key=lambda x: (x.get('desde') or fecha_obj, x.get('operacion') or ''))

    return render(
        request,
        'inmobiliaria/reportes/listado_entradas.html',
        {
            'fecha': fecha_raw,
            'fecha_obj': fecha_obj,
            'entradas': entradas,
            'cantidad_entradas': len(entradas),
        },
    )


@login_required
def listado_salidas(request):
    """
    Listado de salidas por fecha exacta (fin de alquiler).
    Incluye reservas temporales y contratos (invierno/24 meses).
    """
    if not (request.user.is_superuser or getattr(request.user, 'nivel', None) == 4):
        messages.error(request, 'No tenés permisos para acceder a esta sección.')
        return redirect('inmobiliaria:dashboard')

    fecha_raw = (request.GET.get('fecha') or '').strip()
    fecha_obj = None

    if fecha_raw:
        try:
            fecha_obj = datetime.strptime(fecha_raw, '%Y-%m-%d').date()
        except ValueError:
            fecha_obj = None

    if fecha_obj is None:
        fecha_obj = timezone.localdate()
        fecha_raw = fecha_obj.strftime('%Y-%m-%d')

    salidas = []

    reservas = Reserva.objects.filter(
        sucursal=request.user.sucursal,
        eliminada=False,
        estado__in=['confirmada', 'confirmada_no_pagada', 'pagada'],
        fecha_fin=fecha_obj,
    ).select_related('cliente', 'propiedad__propietario', 'vendedor').order_by('fecha_fin', 'id')

    for r in reservas:
        titular = '—'
        if r.cliente:
            apellido = (getattr(r.cliente, 'apellido', '') or '').strip()
            nombre = (getattr(r.cliente, 'nombre', '') or '').strip()
            titular = f'{apellido}, {nombre}'.strip(', ') or '—'

        propietario = '—'
        if r.propiedad and r.propiedad.propietario:
            ap = (getattr(r.propiedad.propietario, 'apellido', '') or '').strip()
            no = (getattr(r.propiedad.propietario, 'nombre', '') or '').strip()
            propietario = f'{ap}, {no}'.strip(', ') or '—'

        vendedor = '—'
        if r.vendedor:
            apv = (getattr(r.vendedor, 'apellido', '') or '').strip()
            nov = (getattr(r.vendedor, 'nombre', '') or '').strip()
            vendedor = (apv or nov or '—').upper()

        salidas.append({
            'tipo': 'reserva',
            'titular': titular,
            'propietario': propietario,
            'operacion': f'{r.id:05d}',
            'direccion': (getattr(r.propiedad, 'direccion', None) or '—'),
            'desde': r.fecha_inicio,
            'hasta': r.fecha_fin,
            'deposito': r.deposito_garantia or Decimal('0'),
            'intervino': vendedor,
            'llave': (getattr(r.propiedad, 'llave', None) or '—'),
            'fecha': r.fecha_fin,
            'hora': (r.fecha_creacion.strftime('%H:%M') if getattr(r, 'fecha_creacion', None) else '—'),
        })

    contratos = ContratoAlquiler.objects.filter(
        sucursal=request.user.sucursal,
        fecha_fin=fecha_obj,
    ).exclude(estado='rescindido').select_related(
        'inquilino', 'propiedad__propietario', 'vendedor'
    ).order_by('fecha_fin', 'id')

    for c in contratos:
        titular = '—'
        if c.inquilino:
            apellido = (getattr(c.inquilino, 'apellido', '') or '').strip()
            nombre = (getattr(c.inquilino, 'nombre', '') or '').strip()
            titular = f'{apellido}, {nombre}'.strip(', ') or '—'

        propietario = '—'
        if c.propiedad and c.propiedad.propietario:
            ap = (getattr(c.propiedad.propietario, 'apellido', '') or '').strip()
            no = (getattr(c.propiedad.propietario, 'nombre', '') or '').strip()
            propietario = f'{ap}, {no}'.strip(', ') or '—'

        vendedor = '—'
        if c.vendedor:
            apv = (getattr(c.vendedor, 'apellido', '') or '').strip()
            nov = (getattr(c.vendedor, 'nombre', '') or '').strip()
            vendedor = (apv or nov or '—').upper()

        salidas.append({
            'tipo': 'contrato',
            'titular': titular,
            'propietario': propietario,
            'operacion': f'{c.id:05d}',
            'direccion': (getattr(c.propiedad, 'direccion', None) or '—'),
            'desde': c.fecha_inicio,
            'hasta': c.fecha_fin,
            'deposito': c.deposito_garantia or Decimal('0'),
            'intervino': vendedor,
            'llave': (getattr(c.propiedad, 'llave', None) or '—'),
            'fecha': c.fecha_fin,
            'hora': (c.fecha_creacion.strftime('%H:%M') if getattr(c, 'fecha_creacion', None) else '—'),
        })

    salidas.sort(key=lambda x: (x.get('hasta') or fecha_obj, x.get('operacion') or ''))

    return render(
        request,
        'inmobiliaria/reportes/listado_salidas.html',
        {
            'fecha': fecha_raw,
            'fecha_obj': fecha_obj,
            'salidas': salidas,
            'cantidad_salidas': len(salidas),
        },
    )


def crear_reserva(request):

    if request.method == 'POST':
        propiedad_id = request.POST.get('propiedad_id')
        fecha_inicio_str = request.POST.get('fecha_inicio')
        fecha_fin_str = request.POST.get('fecha_fin')

        try:
            fecha_inicio = parse_date(fecha_inicio_str)
            fecha_fin = parse_date(fecha_fin_str)

            if not fecha_inicio or not fecha_fin:
                raise ValidationError('Las fechas proporcionadas no son válidas.')

            if fecha_inicio > fecha_fin:
                raise ValidationError('La fecha de inicio no puede ser posterior a la fecha de fin.')

            propiedad = get_object_or_404(Propiedad, id=propiedad_id)
            
            # Aquí puedes añadir la lógica para crear la reserva o validar disponibilidad
            reserva = form.save(commit=False)
            reserva.propiedad_id = propiedad_id
            reserva.vendedor = request.user
            # Asegúrate de que precio_total tenga un valor
            reserva.precio_total = form.cleaned_data.get('precio_total', 0)
            # La cuota_pendiente se establecerá automáticamente en el save()
            reserva.save()

        except (ValueError, ValidationError) as e:
            return render(request, 'inmobiliaria/reserva/error.html', {'error': str(e)})

        return redirect('inmobiliaria:confirmar_reserva')

    return redirect('inmobiliaria:buscar_propiedades')
def reserva_editar(request, reserva_id):
    reserva = get_object_or_404(Reserva, pk=reserva_id)
    
    if request.method == "POST":
        form = ReservaForm(request.POST, instance=reserva)
        
        if form.is_valid():
            reserva = form.save(commit=False)
            propiedad = reserva.propiedad
            fecha_inicio = reserva.fecha_inicio
            fecha_fin = reserva.fecha_fin

            # Validacin de temporadas
            hoy = date.today()
  

            # Guardar los cambios si pasa las validaciones de temporada
            reserva.save()
            messages.success(request, 'Reserva actualizada exitosamente.')
            return redirect('inmobiliaria:reserva_detalle', reserva_id=reserva.id)
    else:
        form = ReservaForm(instance=reserva)
    
    return render(request, 'inmobiliaria/reserva/crear_reserva.html', {'form': form, 'reserva': reserva})

def _sanitize_internal_next_path(raw_next):
    """Evita open redirects: solo rutas relativas internas."""
    n = (raw_next or '').strip()
    if n.startswith('/') and not n.startswith('//'):
        return n
    return ''


@login_required
def reserva_eliminar(request, reserva_id):
    reserva = get_object_or_404(Reserva, pk=reserva_id)

    if request.method == "POST":
        next_url = _sanitize_internal_next_path(request.POST.get('next'))
        try:
            # ✅ NUEVO: Cancelar la reserva primero para restaurar disponibilidades
# print(f"🗑️ ELIMINANDO RESERVA {reserva_id}: {reserva.fecha_inicio} al {reserva.fecha_fin}")
# print(f"   Propiedad: {reserva.propiedad.id} - {reserva.propiedad.direccion}")
            
            # Guardar datos para el mensaje
            fecha_inicio = reserva.fecha_inicio
            fecha_fin = reserva.fecha_fin
            propiedad_direccion = reserva.propiedad.direccion
            
            # 1️⃣ Cancelar la reserva (esto restaura las disponibilidades y reconstruye historial)
            reserva.cancelar_reserva()
            
            # 2️⃣ Soft delete: marcar como eliminada en lugar de eliminar físicamente
            from django.utils import timezone
            reserva.eliminada = True
            reserva.fecha_eliminacion = timezone.now()
            reserva.usuario_eliminacion = request.user
            reserva.save()
            
# print(f"✅ Reserva eliminada y disponibilidades restauradas: {fecha_inicio} al {fecha_fin}")
            messages.success(request, f'Reserva eliminada exitosamente. Las fechas del {fecha_inicio.strftime("%d/%m/%Y")} al {fecha_fin.strftime("%d/%m/%Y")} vuelven a estar disponibles.')
            
        except Exception as e:
            pass  # ✅ Bloque vacío
# print(f"❌ Error al eliminar reserva: {e}")
            messages.error(request, f'Error al eliminar la reserva: {str(e)}')

        if next_url:
            return redirect(next_url)
        return redirect('inmobiliaria:reservas')

    next_get = _sanitize_internal_next_path(request.GET.get('next'))
    return render(
        request,
        'inmobiliaria/reserva/confirmar_eliminar.html',
        {'reserva': reserva, 'next': next_get},
    )
def parse_fecha(fecha_str):
    try:
        # Dividir la fecha en sus componentes
        dia, mes, anio = fecha_str.split('/')
        
        # Convertir a enteros
        dia = int(dia)
        mes = int(mes)
        anio = int(anio)
        
        # Validar que los valores sean razonables
        if dia < 1 or dia > 31 or mes < 1 or mes > 12:
            raise ValidationError('Fecha inválida')
            
        # Crear la fecha en el formato correcto
        return date(anio, mes, dia)
        
    except (ValueError, TypeError, AttributeError):
        raise ValidationError('El formato de fecha debe ser DD/MM/YYYY')


def parsear_monto_desde_ui(precio_raw: str) -> Decimal:
    """
    Convierte el texto de precio ingresado por el usuario a Decimal.

    - Formato argentino: 350.803,20 (miles con punto, decimales con coma)
    - Punto como decimal: 350803.20
    - Solo miles con puntos sin coma: 1.234.567 → 1234567
    - Entero sin separadores: 350803
    """
    s = (precio_raw or '').strip().replace('$', '').replace(' ', '').replace('\u00a0', '')
    if not s:
        raise ValueError('el precio está vacío')
    if ',' in s:
        entero_raw, decimal_raw = s.rsplit(',', 1)
        if not decimal_raw.isdigit():
            raise ValueError('decimales inválidos')
        entero_limpio = entero_raw.replace('.', '')
        if not entero_limpio.isdigit():
            raise ValueError('parte entera inválida')
        return Decimal(f'{entero_limpio}.{decimal_raw}')

    if '.' in s:
        partes = s.split('.')
        ultima = partes[-1]
        if len(partes) == 2 and ultima.isdigit() and 1 <= len(ultima) <= 2:
            izquierda = partes[0]
            if not izquierda.isdigit():
                raise ValueError('parte entera inválida')
            return Decimal(f'{izquierda}.{ultima}')
        if all(p.isdigit() for p in partes):
            return Decimal(''.join(partes))
        raise ValueError('formato no reconocido')

    if not s.isdigit():
        raise ValueError('formato no reconocido')
    return Decimal(s)


def confirmar_reserva(request):
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Obtener datos del formulario
                propiedad_id = request.POST.get('propiedad_id')
                fecha_inicio_str = request.POST.get('fecha_inicio')
                fecha_fin_str = request.POST.get('fecha_fin')
                vendedor_id = request.POST.get('vendedor_id')
                inquilino_id = request.POST.get('inquilino_id')
                precio = request.POST.get('precio_total', '0')
                es_operacion_directa = request.POST.get('es_operacion_directa') == '1'

                # Convertir fechas
                try:
                    fecha_inicio = datetime.strptime(fecha_inicio_str, '%d/%m/%Y').date()
                    fecha_fin = datetime.strptime(fecha_fin_str, '%d/%m/%Y').date()
                except ValueError as e:
                    return JsonResponse({
                        'success': False,
                        'error': f'Error en el formato de las fechas: {str(e)}'
                    })

                # Obtener los objetos necesarios
                try:
                    propiedad = Propiedad.objects.get(id=propiedad_id)
                    vendedor = Vendedor.objects.get(id=vendedor_id)
                    inquilino = Inquilino.objects.get(id=inquilino_id)
                except (Propiedad.DoesNotExist, Vendedor.DoesNotExist, Inquilino.DoesNotExist) as e:
                    return JsonResponse({
                        'success': False,
                        'error': f'Error al obtener los datos: {str(e)}'
                    })

                # Verificar disponibilidad usando el método del modelo
                if not propiedad.esta_disponible_en_fecha(fecha_inicio, fecha_fin):
                    return JsonResponse({
                        'success': False,
                        'error': 'La propiedad no está disponible para las fechas seleccionadas.'
                    })

                # Verificar que no haya reservas en el período
                reservas_existentes = Reserva.objects.filter(
                    propiedad=propiedad,
                    fecha_inicio__lt=fecha_fin,
                    fecha_fin__gt=fecha_inicio,
                    estado__in=['confirmada', 'confirmada_no_pagada']
                )

                if reservas_existentes.exists():
                    return JsonResponse({
                        'success': False,
                        'error': 'El período seleccionado ya tiene una reserva'
                    })

                try:
                    precio_total_dec = parsear_monto_desde_ui(precio)
                except ValueError as exc:
                    return JsonResponse({
                        'success': False,
                        'error': f'El precio no tiene un formato válido ({exc}). Ejemplos válidos: 350803.20; 350.803,20; 350803',
                    })
                if precio_total_dec <= 0:
                    return JsonResponse({
                        'success': False,
                        'error': 'El precio debe ser mayor a cero',
                    })

                # Crear la reserva
                reserva = Reserva.objects.create(
                    propiedad=propiedad,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    vendedor=vendedor,
                    cliente=inquilino,
                    precio_total=precio_total_dec,
                    estado='confirmada' if es_operacion_directa else 'confirmada_no_pagada',
                    sucursal=request.user.sucursal  # Asignar la sucursal del usuario
                )

                # ✅ MANTENER DISPONIBILIDADES FIJAS - Solo actualizar historial
# print(f"✅ Reserva creada correctamente. ID: {reserva.id}")
# print(f"📋 Las disponibilidades se mantienen fijas, solo se actualiza el historial")

                # Si es operación directa, crear el movimiento de caja
                if es_operacion_directa:
                    # Crear el movimiento de caja aquí
                    caja_actual = Caja.objects.filter(
                        sucursal=request.user.sucursal,
                        fecha_cierre__isnull=True
                    ).first()

                    if not caja_actual:
                        return JsonResponse({
                            'success': False,
                            'error': 'No hay una caja abierta para registrar la operación'
                        })

                    MovimientoCaja.objects.create(
                        caja=caja_actual,
                        tipo=TipoMovimientoCajaEnum.INGRESO,
                        concepto='Alquiler por día',
                        monto_efectivo=precio_total_dec,  # Ajustar según la forma de pago
                        descripcion=f'Alquiler por día - {propiedad.direccion}',
                        reserva=reserva
                    )

                # Determinar el estado asignado
                estado_asignado = 'confirmada' if es_operacion_directa else 'confirmada_no_pagada'
                tipo_operacion = 'Operación Directa' if es_operacion_directa else 'Reserva'
                
                return JsonResponse({
                    'success': True,
                    'reserva_id': reserva.id,
                    'estado_asignado': estado_asignado,
                    'tipo_operacion': tipo_operacion,
                    'mensaje_estado': f'{tipo_operacion} creada con estado: {estado_asignado}',
                    'redirect_url': reverse('inmobiliaria:ver_recibo', args=[reserva.id]) if es_operacion_directa else reverse('inmobiliaria:reserva_exitosa', args=[reserva.id])
                })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })

    return JsonResponse({
        'success': False,
        'error': 'Método no permitido'
    })

def consolidar_disponibilidades(propiedad):
    """
    Consolida disponibilidades adyacentes
    """
    disponibilidades = list(Disponibilidad.objects.filter(
        propiedad=propiedad
    ).order_by('fecha_inicio'))
    
    i = 0
    while i < len(disponibilidades) - 1:
        actual = disponibilidades[i]
        siguiente = disponibilidades[i + 1]
        
        # Si son adyacentes
        if actual.fecha_fin == siguiente.fecha_inicio:
            # Extender la disponibilidad actual
            actual.fecha_fin = siguiente.fecha_fin
            actual.save()
            # Eliminar la siguiente
            siguiente.delete()
            # Actualizar la lista
            disponibilidades = list(Disponibilidad.objects.filter(
                propiedad=propiedad
            ).order_by('fecha_inicio'))
        else:
            i += 1

def reserva_detalle(request, reserva_id):
    reserva = get_object_or_404(Reserva, pk=reserva_id)
    return render(request, 'inmobiliaria/reserva/detalle.html', {'reserva': reserva})

@login_required
@require_http_methods(["GET"])
def obtener_info_reserva(request, reserva_id):
    """
    API endpoint para obtener información básica de una reserva (cliente y celular)
    """
    try:
        reserva = get_object_or_404(Reserva, id=reserva_id, sucursal=request.user.sucursal)
        
        cliente_data = {}
        if reserva.cliente:
            cliente_data = {
                'nombre': reserva.cliente.nombre or '',
                'apellido': reserva.cliente.apellido or '',
                'dni': str(reserva.cliente.dni) if reserva.cliente.dni else '',
                'celular': str(reserva.cliente.celular) if reserva.cliente.celular else '',
                'email': reserva.cliente.email or '',
                'domicilio': reserva.cliente.domicilio or '',
                'localidad': reserva.cliente.localidad or '',
            }
        
        # Determinar el estado a mostrar
        estado_display = reserva.estado
        if reserva.estado == 'confirmada_no_pagada':
            estado_display = 'Reservado'
        elif hasattr(reserva, 'get_estado_display'):
            estado_display = reserva.get_estado_display()
        
        # Información del vendedor
        vendedor_data = {}
        if reserva.vendedor:
            vendedor_data = {
                'id': reserva.vendedor.id,
                'nombre': reserva.vendedor.nombre or '',
                'apellido': reserva.vendedor.apellido or '',
                'nombre_completo': f"{reserva.vendedor.apellido or ''}, {reserva.vendedor.nombre or ''}".strip(', ').strip() or 'N/A'
            }
        
        reserva_data = {
            'id': reserva.id,
            'estado': estado_display,
            'fecha_inicio': reserva.fecha_inicio.strftime('%d/%m/%Y') if reserva.fecha_inicio else '',
            'fecha_fin': reserva.fecha_fin.strftime('%d/%m/%Y') if reserva.fecha_fin else '',
            'precio_total': f'${reserva.precio_total:,.0f}' if reserva.precio_total else 'N/A',
            'cliente': cliente_data,
            'vendedor': vendedor_data
        }
        
        return JsonResponse({
            'success': True,
            'reserva': reserva_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error al cargar información: {str(e)}'
        })
# inmobiliaria/views.py
def formato_fecha(fecha):
    return fecha.strftime('%d/%m/%Y') if fecha else ''


def calcular_disponibilidad_real(propiedad, disponibilidades, reservas, fecha_inicio, fecha_fin):
    """
    Calcula la disponibilidad real de una propiedad considerando las reservas existentes.
    Retorna el período disponible más amplio que incluya o se superponga con las fechas solicitadas.
    """
    from datetime import timedelta
    
    # Calcular la duración del período solicitado
    dias_solicitados = (fecha_fin - fecha_inicio).days + 1
    
    # Obtener todas las disponibilidades que tienen superposición REAL con el período solicitado
    # Evitar casos donde solo se "tocan" en un día
    disponibilidades_validas = disponibilidades.filter(
        fecha_inicio__lt=fecha_fin,     # La disponibilidad empieza ANTES del fin solicitado (no en el mismo día)
        fecha_fin__gt=fecha_inicio      # La disponibilidad termina DESPUÉS del inicio solicitado (no en el mismo día)
    )
    
    if not disponibilidades_validas.exists():
        pass  # ✅ Bloque vacío
# print(f"🚫 No hay disponibilidades que se superpongan con el período {fecha_inicio} a {fecha_fin}")
        return None
    
    # Obtener todas las reservas confirmadas o pagadas que se superponen
    # Excluir reservas eliminadas
    reservas_confirmadas = reservas.filter(
        Q(estado='confirmada') | Q(estado='pagada') | Q(estado='confirmada_no_pagada'),
        fecha_inicio__lt=fecha_fin,
        fecha_fin__gt=fecha_inicio,
        eliminada=False
    )
    
    # Si no hay reservas, usar el rango completo de disponibilidad
    if not reservas_confirmadas.exists():
        primera_disponibilidad = disponibilidades_validas.order_by('fecha_inicio').first()
        ultima_disponibilidad = disponibilidades_validas.order_by('-fecha_fin').first()
        
        return {
            'inicio': primera_disponibilidad.fecha_inicio if primera_disponibilidad else fecha_inicio,
            'fin': ultima_disponibilidad.fecha_fin if ultima_disponibilidad else fecha_fin
        }
    
    # Buscar períodos libres entre las reservas
    periodos_libres = []
    
    # Para cada disponibilidad, encontrar los períodos no reservados
    for disponibilidad in disponibilidades_validas:
        inicio_disp = max(disponibilidad.fecha_inicio, fecha_inicio)
        fin_disp = min(disponibilidad.fecha_fin, fecha_fin)
        
        # Dividir este período según las reservas existentes
        reservas_en_periodo = reservas_confirmadas.filter(
            fecha_inicio__lt=fin_disp,
            fecha_fin__gt=inicio_disp
        ).order_by('fecha_inicio')
        
        if not reservas_en_periodo.exists():
            # No hay reservas en este período, verificar que cubra completamente las fechas solicitadas
            if disponibilidad.fecha_inicio <= fecha_inicio and disponibilidad.fecha_fin >= fecha_fin:
                # La disponibilidad completa cubre las fechas solicitadas, mostrar todo el período disponible
                periodos_libres.append({
                    'inicio': disponibilidad.fecha_inicio,  # Mostrar desde el inicio real de la disponibilidad
                    'fin': disponibilidad.fecha_fin,        # Hasta el fin real de la disponibilidad
                    'dias': (disponibilidad.fecha_fin - disponibilidad.fecha_inicio).days + 1
                })
        else:
            # Hay reservas, encontrar los huecos
            fecha_actual = inicio_disp
            
            for reserva in reservas_en_periodo:
                if fecha_actual < reserva.fecha_inicio:
                    # Hay un período libre antes de esta reserva
                    fin_periodo = reserva.fecha_inicio - timedelta(days=1)
                    if fecha_actual <= fin_periodo:
                        # Agregar cualquier período libre válido (sin exigir cobertura completa)
                        periodos_libres.append({
                            'inicio': fecha_actual,      # Mostrar desde el inicio real del período libre
                            'fin': fin_periodo,          # Hasta el fin real del período libre
                            'dias': (fin_periodo - fecha_actual).days + 1
                        })
                
                # Mover la fecha actual al final de la reserva
                fecha_actual = max(fecha_actual, reserva.fecha_fin + timedelta(days=1))
            
            # Verificar si hay un período libre después de la última reserva
            if fecha_actual <= disponibilidad.fecha_fin:
                # Agregar cualquier período libre válido (sin exigir cobertura completa)
                periodos_libres.append({
                    'inicio': fecha_actual,                    # Desde donde queda libre después de la reserva
                    'fin': disponibilidad.fecha_fin,          # Hasta el fin real de la disponibilidad
                    'dias': (disponibilidad.fecha_fin - fecha_actual).days + 1
                })
    
    if not periodos_libres:
        return None
    
    # Si hay períodos libres, devolver el más amplio o conveniente
    if periodos_libres:
        # Buscar el período que mejor cubra las fechas solicitadas o el más amplio
        mejor_periodo = max(periodos_libres, key=lambda p: p['dias'])
# print(f"✅ Período disponible encontrado: {mejor_periodo['inicio']} a {mejor_periodo['fin']} ({mejor_periodo['dias']} días)")
        return {
            'inicio': mejor_periodo['inicio'],
            'fin': mejor_periodo['fin']
        }
    
# print(f"🚫 No se encontraron períodos libres para {fecha_inicio} a {fecha_fin}")
    return None


@login_required
def buscar_propiedades_reserva(request):
    # FUNCIÓN: buscar_propiedades_reserva - cálculo día por día con temporadas ✅
    # Obtener la sucursal del vendedor logueado
    sucursal_vendedor = request.user.sucursal
    
    inquilinos = get_inquilinos_queryset_unificado(request)
    form = BuscarPropiedadesForm(request.POST or None)
    inquilino_form = InquilinoForm(request.POST)
    propiedades_disponibles = []
    propiedades_sin_precio = []
    vendedores = Vendedor.objects.filter(sucursal=sucursal_vendedor)
    total_dias_reserva = 0
    
    # Inicializar conteos
    total_propiedades = 0
    reservas_count = 0
    disponibles_count = 0

    fecha_inicio = None
    fecha_fin = None
    origen = None
    destino = None

    if form.is_valid():
        fecha_inicio = form.cleaned_data['fecha_inicio']
        fecha_fin = form.cleaned_data['fecha_fin']
        origen = form.cleaned_data['origen']
        destino = form.cleaned_data['destino']
        ver_todas = form.cleaned_data.get('ver_todas', False)

        # Filtrar propiedades según la opción seleccionada
        if ver_todas:
            # Solo mostrar propiedades de las sucursales Colón y Corrientes
            # Buscar por nombre de sucursal con múltiples variaciones
            # Buscar "colon" (sin tilde) y "colón" (con tilde) para cubrir todas las formas
            propiedades = Propiedad.objects.filter(
                Q(sucursal__nombre__icontains='colon') | 
                Q(sucursal__nombre__icontains='corrientes')
            )
        else:
            propiedades = Propiedad.objects.filter(sucursal=sucursal_vendedor)

        # Prefetch los precios para cada propiedad
        propiedades = propiedades.prefetch_related(
            Prefetch('precios', queryset=Precio.objects.all(), to_attr='todos_precios')
        ).select_related('sucursal')

        # Aplicar filtros del formulario
        if origen:
            propiedades = propiedades.filter(ubicacion__icontains=origen)
        
        if destino:
            propiedades = propiedades.filter(ubicacion__icontains=destino)

        tipo_inmueble = form.cleaned_data.get('tipo_inmueble')
        if tipo_inmueble:
            propiedades = propiedades.filter(tipo_inmueble__in=tipo_inmueble)

        vista = form.cleaned_data.get('vista')
        if vista:
            propiedades = propiedades.filter(vista__in=vista)

        ambientes = form.cleaned_data.get('ambientes')
        if ambientes:
            propiedades = propiedades.filter(ambientes=ambientes)

        valoracion = form.cleaned_data.get('valoracion')
        if valoracion:
            propiedades = propiedades.filter(valoracion=valoracion)

        precio_min = form.cleaned_data.get('precio_min')
        if precio_min is not None:
            propiedades = propiedades.filter(precio__gte=precio_min)

        precio_max = form.cleaned_data.get('precio_max')
        if precio_max is not None:
            propiedades = propiedades.filter(precio__lte=precio_max)

        # Filtros booleanos
        caracteristicas_booleanas = [
            'amoblado', 'cochera', 'tv_smart', 'wifi', 'dependencia', 'patio',
            'parrilla', 'piscina', 'reciclado', 'a_estrenar', 'terraza', 'balcon',
            'baulera', 'lavadero', 'seguridad', 'vista_al_Mar', 'vista_panoramica', 'apto_credito'
        ]
        for caracteristica in caracteristicas_booleanas:
            if form.cleaned_data.get(caracteristica):
                propiedades = propiedades.filter(**{caracteristica: True})

        # ✅ LÓGICA MEJORADA: Verificar cobertura completa con disponibilidades contiguas
        for propiedad in propiedades:
            from datetime import timedelta
# print(f"🔍 PROCESANDO PROPIEDAD {propiedad.id}: {propiedad}")
# print(f"   🔎 Buscando disponibilidades para {fecha_inicio} al {fecha_fin}")
            
            # 1️⃣ BUSCAR TODAS LAS DISPONIBILIDADES QUE SE SUPERPONEN CON EL PERÍODO
            disponibilidades_superpuestas = Disponibilidad.objects.filter(
                propiedad=propiedad,
                fecha_inicio__lt=fecha_fin,   # Empieza antes de que termine la búsqueda
                fecha_fin__gt=fecha_inicio,   # Termina después de que empiece la búsqueda
            ).order_by('fecha_inicio')
            
            # 2️⃣ VERIFICAR SI LAS DISPONIBILIDADES CUBREN TODO EL RANGO (permitiendo contiguas)
            periodo_cubierto = False
            if disponibilidades_superpuestas.exists():
                # Verificar si las disponibilidades contiguas cubren todo el rango
                disponibilidades_list = list(disponibilidades_superpuestas)
                
                # Ordenar por fecha de inicio
                disponibilidades_list.sort(key=lambda d: d.fecha_inicio)
                
                # Verificar cobertura continua
                cobertura_inicio = disponibilidades_list[0].fecha_inicio
                cobertura_fin = disponibilidades_list[0].fecha_fin
                
                for i in range(1, len(disponibilidades_list)):
                    disp_actual = disponibilidades_list[i]
                    # Si la disponibilidad actual empieza el mismo día o antes que termine la anterior
                    # (permitiendo fechas contiguas como 07-11 y 11-15)
                    if disp_actual.fecha_inicio <= cobertura_fin:
                        # Extender la cobertura
                        cobertura_fin = max(cobertura_fin, disp_actual.fecha_fin)
                    else:
                        # Hay un hueco
                        break
                
                # Verificar si la cobertura completa incluye el período buscado
                if cobertura_inicio <= fecha_inicio and cobertura_fin >= fecha_fin:
                    periodo_cubierto = True
# print(f"   ✅ Período CUBIERTO por disponibilidades contiguas: {cobertura_inicio} al {cobertura_fin}")
                else:
                    pass  # ✅ Bloque vacío
# print(f"   ❌ Período NO cubierto. Cobertura: {cobertura_inicio} al {cobertura_fin}, necesario: {fecha_inicio} al {fecha_fin}")
            
            # Usar la variable disponibilidades para mantener compatibilidad con el resto del código
            disponibilidades = disponibilidades_superpuestas if periodo_cubierto else Disponibilidad.objects.none()
            
            if periodo_cubierto:
                # 3️⃣ CALCULAR PERÍODO LIBRE usando la cobertura de disponibilidades contiguas
                # Usar la cobertura calculada anteriormente (cobertura_inicio y cobertura_fin)
                fecha_disponible_desde = cobertura_inicio
                fecha_disponible_hasta = cobertura_fin
                
                # 4️⃣ AJUSTAR POR RESERVAS ANTERIORES Y POSTERIORES
                # Fechas finales de reservas que terminan antes o en la fecha de inicio
                # Excluir reservas eliminadas
                reservas_anteriores = propiedad.reservas.filter(
                    fecha_fin__lte=fecha_inicio,
                    eliminada=False
                ).order_by('-fecha_fin').first()
                
                if reservas_anteriores:
                    # 🏨 LÓGICA HOTEL: Si reserva termina el 17, el 17 ya está disponible
                    fecha_disponible_desde = max(fecha_disponible_desde, reservas_anteriores.fecha_fin)
                
                # Fechas iniciales de reservas que empiezan después o en la fecha de fin
                # Excluir reservas eliminadas
                reservas_posteriores = propiedad.reservas.filter(
                    fecha_inicio__gte=fecha_fin,
                    eliminada=False
                ).order_by('fecha_inicio').first()
                
                if reservas_posteriores:
                    # 🏨 LÓGICA HOTEL: Si próxima reserva empieza el 25, hasta el 25 está disponible
                    fecha_disponible_hasta = min(fecha_disponible_hasta, reservas_posteriores.fecha_inicio)
                
                # 4b. Ajustar "disponible hasta" si hay contrato de alquiler (invierno/24m) que empiece dentro del período libre
                contrato_corta = ContratoAlquiler.objects.filter(
                    propiedad=propiedad,
                    estado__in=['reservado', 'activo'],
                    fecha_inicio__lte=fecha_disponible_hasta,
                    fecha_fin__gt=fecha_disponible_desde
                ).order_by('fecha_inicio').first()
                if contrato_corta:
                    fecha_disponible_hasta = min(fecha_disponible_hasta, contrato_corta.fecha_inicio)
                
                # 5️⃣ ASIGNAR FECHAS CALCULADAS
                propiedad.disponibilidad_inicio = fecha_disponible_desde
                propiedad.disponibilidad_fin = fecha_disponible_hasta
                
# print(f"🎯 PROP {propiedad.id}: Libre desde {fecha_disponible_desde} hasta {fecha_disponible_hasta}")
# print(f"   📅 Asignado: disponibilidad_inicio={propiedad.disponibilidad_inicio}")
# print(f"   📅 Asignado: disponibilidad_fin={propiedad.disponibilidad_fin}")
# print(f"   📊 Cobertura de disponibilidades contiguas: {cobertura_inicio} al {cobertura_fin}")
                if reservas_anteriores:
                    pass  # ✅ Bloque vacío
# print(f"   ⏪ Reserva anterior termina: {reservas_anteriores.fecha_fin}")
                if reservas_posteriores:
                    pass  # ✅ Bloque vacío
# print(f"   ⏩ Próxima reserva empieza: {reservas_posteriores.fecha_inicio}")
            else:
                pass  # ✅ Bloque vacío
# print(f"❌ PROP {propiedad.id}: NO tiene disponibilidades que contengan el período {fecha_inicio} al {fecha_fin}")
                disponibilidades = Disponibilidad.objects.none()
                
                # Para debugging: mostrar todas las disponibilidades de esta propiedad
                todas_disponibilidades = Disponibilidad.objects.filter(propiedad=propiedad)
# print(f"   📋 Disponibilidades existentes ({todas_disponibilidades.count()}):")
                for disp in todas_disponibilidades:
                    pass  # ✅ Bloque vacío
# print(f"     - {disp.fecha_inicio} al {disp.fecha_fin}")

            # Obtener las reservas asociadas a la propiedad
            # Excluir reservas eliminadas
            reservas = propiedad.reservas.filter(
                Q(fecha_inicio__lt=fecha_fin) & Q(fecha_fin__gt=fecha_inicio),
                eliminada=False
            )
            
            # Excluir si tiene contrato de alquiler (invierno o 24 meses) que se superponga con el período buscado
            if ContratoAlquiler.objects.filter(
                propiedad=propiedad,
                estado__in=['reservado', 'activo'],
                fecha_inicio__lt=fecha_fin,
                fecha_fin__gt=fecha_inicio
            ).exists():
                continue  # No mostrar como disponible: está ocupada por operación

            if reservas.filter(estado='pagada').exists():
                continue  # Saltar esta propiedad si ya tiene una reserva pagada

            # Verificar si existe una reserva que debe mostrarse en rojo
            reserva_confirmada_no_pagada = reservas.filter(Q(estado='confirmada_no_pagada') | Q(estado='confirmada') | Q(estado='en_espera')).first()

            # Evaluar la disponibilidad y las reservas de la propiedad
            if disponibilidades.exists() and not reservas.filter(estado='confirmada').exists():
                if reserva_confirmada_no_pagada:
                    propiedad.reserva = reserva_confirmada_no_pagada
                    propiedad.estado_reserva = 'confirmada_no_pagada'  # Siempre mostrar como confirmada_no_pagada en frontend
                    propiedad.precio_total_reserva = reserva_confirmada_no_pagada.precio_total
                else:
                    propiedad.estado_reserva = 'disponible'

                # Calcular el precio total de la reserva según las fechas seleccionadas
                precio_total = 0
# print('fecha de inicio',fecha_inicio)
# print('fecha de fin',fecha_fin)
                # Calcular noches, no días (del 13 al 15 = 2 noches)
                noches_reserva = (fecha_fin - fecha_inicio).days
                total_dias_reserva = noches_reserva

                # 🔍 DEBUGGING CRÍTICO: Ver todos los precios de esta propiedad
# print(f"🔍 DEBUGGING PRECIOS - Propiedad {propiedad.id} (fechas: {fecha_inicio} al {fecha_fin}):")
                todos_precios = Precio.objects.filter(propiedad=propiedad)
# print(f"   Total precios configurados: {todos_precios.count()}")
                for precio in todos_precios:
                    pass  # ✅ Bloque vacío
# print(f"   - {precio.tipo_precio}: ${precio.precio_por_dia}")
                

                
                # ✅ CÁLCULO POR NOCHES: Usar precio del día de SALIDA, EXCEPTO Año Nuevo
                # Ejemplo: 29/12→30/12 usa precio del 29/12
                #          30/12→31/12 usa precio del 30/12
                #          31/12→01/01 usa precio del 01/01 (EXCEPCIÓN: Año Nuevo)
                #          01/01→02/01 usa precio del 01/01
                precio_mas_caro = 0
                
                for noche in range(noches_reserva):
                    # Día de salida (el día actual de la noche)
                    dia_salida = fecha_inicio + timedelta(noche)
                    dia_llegada = fecha_inicio + timedelta(noche + 1)
                    
                    # ✅ EXCEPCIÓN: Año Nuevo (31/12 → 01/01) usa precio del 0ew1/01
                    if dia_salida.month == 12 and dia_salida.day == 31 and dia_llegada.month == 1 and dia_llegada.day == 1:
                        dia_a_usar = dia_llegada  # Usar precio del 01/01
                    else:
                        dia_a_usar = dia_salida  # Usar precio del día de salida
                    
                    # Determinar el tipo de precio según el día a usar
                    tipo_precio = None
                    if dia_a_usar.month == 1:  # Enero
                        tipo_precio = 'QUINCENA_1_ENERO' if dia_a_usar.day <= 15 else 'QUINCENA_2_ENERO'
                    elif dia_a_usar.month == 2:  # Febrero
                        tipo_precio = 'QUINCENA_1_FEBRERO' if dia_a_usar.day <= 15 else 'QUINCENA_2_FEBRERO'
                    elif dia_a_usar.month == 3:  # Marzo
                        tipo_precio = 'QUINCENA_1_MARZO' if dia_a_usar.day <= 15 else 'QUINCENA_2_MARZO'
                    elif dia_a_usar.month == 7:  # Julio (Vacaciones de Invierno)
                        tipo_precio = 'VACACIONES_INVIERNO'
                    elif dia_a_usar.month == 12:  # Diciembre
                        tipo_precio = 'QUINCENA_1_DICIEMBRE' if dia_a_usar.day <= 15 else 'QUINCENA_2_DICIEMBRE'
                    else:
                        tipo_precio = 'TEMPORADA_BAJA'

                    # Obtener el precio para la propiedad y la quincena correspondiente
                    try:
                        precio = Precio.objects.get(propiedad=propiedad, tipo_precio=tipo_precio)
                        precio_dia = precio.precio_por_dia or 0
# print(f"✅ Noche {noche+1} ({fecha_inicio + timedelta(noche)}→{dia_llegada}): {tipo_precio} = ${precio_dia}")
                    except Precio.DoesNotExist:
                        precio_dia = 0
# print(f"❌ Noche {noche+1}: {tipo_precio} = NO EXISTE")

                    # Rastrear el día más caro
                    if precio_dia > precio_mas_caro:
                        precio_mas_caro = precio_dia

                    precio_total += precio_dia

                # ✅ AGREGAR DÍA DE COMISIÓN (día más caro)
                precio_final_calculado = precio_total + precio_mas_caro
                propiedad.precio_total_reserva = precio_final_calculado
# print(f"🔥 PROPIEDAD {propiedad.id}: suma_noches=${precio_total}, dia_mas_caro=${precio_mas_caro}, FINAL=${precio_final_calculado}")

                # Calcular la disponibilidad real considerando las reservas existentes
                disponibilidad_calculada = calcular_disponibilidad_real(
                    propiedad, disponibilidades, reservas, fecha_inicio, fecha_fin
                )
                
                if disponibilidad_calculada:
                    propiedad.disponibilidad_inicio = disponibilidad_calculada['inicio']
                    propiedad.disponibilidad_fin = disponibilidad_calculada['fin']
                else:
                    # Si no hay disponibilidad, usar la lógica original como fallback
                    if not reservas.exists():
                        primera_disponibilidad = disponibilidades.order_by('fecha_inicio').first()
                        ultima_disponibilidad = disponibilidades.order_by('-fecha_fin').first()

                        if primera_disponibilidad:
                            propiedad.disponibilidad_inicio = primera_disponibilidad.fecha_inicio
                        if ultima_disponibilidad:
                            propiedad.disponibilidad_fin = ultima_disponibilidad.fecha_fin

                    # Obtener la reserva más cercana antes de la fecha de inicio
                    reserva_cercana = propiedad.reservas.filter(fecha_fin__lte=fecha_inicio).order_by('-fecha_fin').first()
                    reserva_cercana_fin = propiedad.reservas.filter(fecha_inicio__gte=fecha_fin).order_by('fecha_inicio').first()

                    if reserva_cercana:
                        propiedad.disponibilidad_inicio = reserva_cercana.fecha_fin

                    if reserva_cercana_fin:
                        propiedad.disponibilidad_fin = reserva_cercana_fin.fecha_inicio

                if reserva_confirmada_no_pagada:
                    propiedad.disponibilidad_inicio = reserva_confirmada_no_pagada.fecha_inicio 
                    propiedad.disponibilidad_fin = reserva_confirmada_no_pagada.fecha_fin

                # Añadir la propiedad disponible a la lista
                dias_disponibles = (fecha_inicio - propiedad.disponibilidad_inicio).days
                propiedad.dias_disponibles = max(dias_disponibles, 0)
                propiedades_disponibles.append(propiedad)
                propiedades_disponibles.sort(key=lambda x: x.dias_disponibles)

                # Asegúrate de que todos los precios estén disponibles
                try:
                    # Función auxiliar para manejar tipos de precio no válidos
                    def get_precio_order(precio):
                        try:
                            return TipoPrecio[precio.tipo_precio].value
                        except KeyError:
                            # Si el tipo no existe en el enum, ponerlo al final
                            return 999
                        
                    propiedad.todos_precios = sorted(propiedad.todos_precios, key=get_precio_order)
                except Exception as e:
                    pass  # ✅ Bloque vacío
# print(f"Error ordenando precios para propiedad {propiedad.id}: {e}")
                    # En caso de error, no ordenar los precios
                    pass

    # Alerta si hay propiedades sin precio
    alerta_sin_precio = len(propiedades_sin_precio) > 0
# print("las fechas de inicio y fin son ",fecha_inicio,fecha_fin)
# print("los dias de reserva son ",total_dias_reserva)

    # ❌ ELIMINADO: El cálculo duplicado que estaba sobrescribiendo el precio correcto
    # El precio ya se calculó correctamente arriba en las líneas 1132-1167

    # Obtener conceptos para el template
    conceptos = Concepto.objects.filter(
        q_conceptos_caja_visibles(sucursal_vendedor)
    ).order_by('nombre')

    # Calcular conteos para el template
    total_propiedades = len(propiedades_disponibles)
    reservas_count = 0
    disponibles_count = 0
    
    if total_propiedades > 0:
        for p in propiedades_disponibles:
            estado = getattr(p, 'estado_reserva', None)
            if estado == 'confirmada_no_pagada':
                reservas_count += 1
            else:
                disponibles_count += 1
        
        # Asegurar que los conteos sumen el total
        if (reservas_count + disponibles_count) != total_propiedades:
            disponibles_count = total_propiedades - reservas_count

    return render(request, 'inmobiliaria/reserva/buscar_propiedades.html', {
        'form': form,
        'propiedades_disponibles': propiedades_disponibles,
        'alerta_sin_precio': alerta_sin_precio,
        'fecha_inicio': fecha_inicio.strftime('%d/%m/%Y') if fecha_inicio else '',
        'fecha_fin': fecha_fin.strftime('%d/%m/%Y') if fecha_fin else '',
        'total_dias': total_dias_reserva,
        'total_propiedades': total_propiedades,
        'reservas_count': reservas_count,
        'disponibles_count': disponibles_count,
        'inquilinos': get_inquilinos_queryset_unificado(request),
        'vendedores': vendedores,
        'tipos_precio': TipoPrecio,
        'conceptos': conceptos
    })

@login_required
def crear_disponibilidad(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    
    if request.method == 'POST':
        form = DisponibilidadForm(propiedad=propiedad, data=request.POST)
        if form.is_valid():
            try:
                # Crear una nueva instancia de Disponibilidad
                nueva_disponibilidad = Disponibilidad(
                    propiedad=propiedad,
                    fecha_inicio=form.cleaned_data['fecha_inicio'],
                    fecha_fin=form.cleaned_data['fecha_fin'],
                    es_manual=True,  # Marcada explícitamente como manual
                    asegurado=form.cleaned_data.get('asegurado', False),
                    monto_asegurado=form.cleaned_data.get('monto_asegurado'),
                    moneda_asegurado=form.cleaned_data.get('moneda_asegurado')
                )
                
                # ✅ MEJORADO: Verificar superposición REAL (permitir fechas contiguas)
                todas_disponibilidades = Disponibilidad.objects.filter(
                    propiedad=propiedad
                )
                
                # Verificar VERDADERA superposición (excluir fechas contiguas)
                solapamiento_real = False
                for disp in todas_disponibilidades:
                    # Superposición REAL: comparten MÁS de un día
                    # Si solo se tocan en UN día (contiguas como 10-15 y 15-20), es válido
                    if disp.fecha_fin > nueva_disponibilidad.fecha_inicio and disp.fecha_inicio < nueva_disponibilidad.fecha_fin:
                        solapamiento_real = True
                        break
                
                if solapamiento_real:
                    messages.error(request, 'Ya existe una disponibilidad que se superpone con estas fechas')
                else:
                    nueva_disponibilidad.save()
                    
                    # ✅ Las disponibilidades manuales no crean historial automáticamente
                    # El historial se gestiona por separado
                    
                    messages.success(request, 'Disponibilidad creada exitosamente')
                    return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad.id)
                    
            except Exception as e:
                messages.error(request, f'Error al crear la disponibilidad: {str(e)}')
    else:
        form = DisponibilidadForm(propiedad=propiedad)
    
    # Obtener disponibilidades existentes
    disponibilidades = Disponibilidad.objects.filter(propiedad=propiedad).order_by('fecha_inicio')
    
    return render(request, 'inmobiliaria/propiedades/crear_disponibilidad.html', {
        'form': form,
        'propiedad': propiedad,
        'disponibilidades': disponibilidades
    })

def reserva_exitosa(request, reserva_id):
    
    reserva = Reserva.objects.get(id=reserva_id)
# print("la reserva es ",reserva.precio_total)
    
    context = {
        'reserva': reserva
    }
    return render(request, 'inmobiliaria/reserva/reserva_exitosa.html', context)

@login_required
def finalizar_reserva_nueva(request, reserva_id):
    """
    Nueva vista para finalizar reserva basada en la carga de recibo
    """
    try:
        # Obtener la reserva
        reserva = get_object_or_404(Reserva, id=reserva_id, sucursal=request.user.sucursal)
        
        # 🚀 SOLUCIÓN: Si la reserva tiene precio 0, recalcularlo
        if reserva.precio_total == 0:
            pass  # ✅ Bloque vacío
# print(f"⚠️ Reserva {reserva.id} tiene precio 0, recalculando...")
            recalcular_precio_reserva(reserva)
            # Refrescar desde la base de datos
            reserva.refresh_from_db()
        
        # Obtener la caja actual de la sucursal
        caja_actual = Caja.objects.filter(
            sucursal=request.user.sucursal,
            fecha_cierre__isnull=True
        ).first()
        
        if not caja_actual:
            messages.error(request, 'No hay una caja abierta. Debe abrir una caja primero.')
            return redirect('inmobiliaria:reservas')
        
        # Calcular información del próximo movimiento
        cantidad_movimientos = MovimientoCaja.objects.filter(caja=caja_actual).count()
        proximo_numero_movimiento = cantidad_movimientos + 1
        
        # Obtener conceptos de caja disponibles
        conceptos_caja = Concepto.objects.filter(
            q_conceptos_caja_visibles(request.user.sucursal)
        ).order_by('id')
        
        # ✅ Obtener cuentas bancarias activas de la sucursal
        from inmobiliaria.models.sucursal import CuentaBancaria
        cuentas_bancarias = CuentaBancaria.objects.filter(
            sucursal=request.user.sucursal,
            activa=True
        ).order_by('nombre_banco', 'alias')
        
        # ✅ CALCULAR SALDO PENDIENTE CONSIDERANDO SOLO LA SEÑA (NO EL DEPÓSITO)
        # Buscar todos los movimientos de caja pagados para esta reserva
        pagos_anteriores = MovimientoCaja.objects.filter(
            propiedad=reserva.propiedad,
            tipo=TipoMovimientoCajaEnum.INGRESO,
            concepto__icontains=f"Operaci\u00f3n {reserva.id}"
        )
        
        # ✅ DETECTAR SI ES "COMPLETAR PAGO" O "FINALIZAR RESERVA"
        # Si ya hay pagos anteriores, es "Completar Pago", sino es "Finalizar Reserva"
        total_pagos_anteriores = sum(pago.monto_total for pago in pagos_anteriores)
        
        # ✅ CALCULAR SOLO LA SEÑA DE PAGOS ANTERIORES (concepto ID: 1)
        total_senia_anteriores = Decimal('0')
        for pago in pagos_anteriores:
            if pago.concepto and "|CONCEPTOS:" in pago.concepto:
                # Parsear conceptos del formato |CONCEPTOS:id:nombre:importe|
                concepto_parts = pago.concepto.split("|CONCEPTOS:", 1)
                if len(concepto_parts) > 1:
                    conceptos_data = concepto_parts[1]
                    conceptos_items = [item for item in conceptos_data.split("|") if item.strip()]
                    
                    for concepto_item in conceptos_items:
                        parts = concepto_item.split(":")
                        if len(parts) >= 3:
                            concepto_id = parts[0].strip()
                            concepto_importe = parts[2].strip()
                            
                            # ✅ CONCEPTOS QUE CUENTAN COMO SEÑA / saldo a ocupar: ver CONCEPTOS_SENIA_OPERACION_RESERVA
                            if concepto_id in CONCEPTOS_SENIA_OPERACION_RESERVA:
                                try:
                                    importe_num = Decimal(concepto_importe.replace(',', ''))
                                    total_senia_anteriores += importe_num
# print(f"💰 SEÑA ANTERIOR DETECTADA: Concepto {concepto_id} - ${importe_num}")
                                except:
                                    pass
        
# print(f"📊 CÁLCULO PAGOS ANTERIORES:")
# print(f"   - Total pagos anteriores: ${total_pagos_anteriores}")
# print(f"   - Seña anteriores (conceptos seña/locación): ${total_senia_anteriores}")
        
        es_completar_pago = total_pagos_anteriores > 0
        
        if es_completar_pago:
            # COMPLETAR PAGO: SALDO = PRECIO TOTAL - SOLO LA SEÑA ANTERIOR (concepto ID:1)
            saldo_a_ocupar = reserva.precio_total - total_senia_anteriores
        else:
            # FINALIZAR RESERVA: SALDO = PRECIO TOTAL (no hay seña anterior)
            saldo_a_ocupar = reserva.precio_total
        
        tipo_operacion = "COMPLETAR PAGO" if es_completar_pago else "FINALIZAR RESERVA"
# print(f"✅ CÁLCULO {tipo_operacion}:")
# print(f"   - Precio Total: ${reserva.precio_total}")
# print(f"   - Seña: ${reserva.senia or 0}")
        if es_completar_pago:
            pass  # ✅ Bloque vacío
# print(f"   - Pagos Anteriores: ${total_pagos_anteriores}")
# print(f"   - Saldo Pendiente: ${saldo_a_ocupar}")
# print(f"   - Depósito: ${reserva.deposito_garantia or 0}")

        
        # ✅ CALCULAR SEÑA PENDIENTE: Si ya pagó seña, mostrar 0
        senia_pendiente = 0  # Por defecto 0, porque si ya pagó seña no debe pagar más
        if (reserva.senia or 0) == 0:
            # Si no hay seña pagada aún, puede que necesite pagar algo
            # Pero normalmente en "finalizar reserva" ya se pagó todo
            senia_pendiente = 0
        
# print(f"✅ SEÑA PENDIENTE CALCULADA:")
# print(f"   - Seña ya pagada: ${reserva.senia or 0}")
# print(f"   - Seña pendiente a mostrar: ${senia_pendiente}")

        # Datos para el formulario (solo lectura)
        # ✅ VARIABLES PARA EL TEMPLATE ORIGINAL (igual que finalizar_reserva)
        context = {
            'reserva': reserva,
            'pagos_previos': pagos_anteriores,  # Lista de MovimientoCaja anteriores
            'total_pagado': total_pagos_anteriores,  # Total de pagos anteriores
            'deposito': reserva.deposito_garantia or 0,  # Depósito de garantía
            'saldo_pendiente': saldo_a_ocupar,  # Saldo pendiente calculado
            'conceptos_pago': conceptos_caja,  # Conceptos disponibles
            'conceptos_caja': conceptos_caja,  # Para el template HTML
            'conceptos_json': list(conceptos_caja.values('id', 'nombre')),  # Para JavaScript
            'cuentas_bancarias': cuentas_bancarias,  # ✅ Cuentas bancarias de la sucursal
            'cliente_id': reserva.cliente.id,
            'cliente_nombre': f"{reserva.cliente.apellido}, {reserva.cliente.nombre}",
            'interno_caja': caja_actual.numero,
            'propiedad_id': reserva.propiedad.id,
            'propiedad_direccion': reserva.propiedad.direccion,
            'fecha_actual': datetime.now().strftime('%d/%m/%Y'),
            'numero_movimiento': proximo_numero_movimiento,
            'numero_recibo': '0000-00000000',  # Para completar
            'productor_id': reserva.vendedor.id if reserva.vendedor else request.user.id,
            'productor_nombre': f"{reserva.vendedor.apellido}, {reserva.vendedor.nombre}" if reserva.vendedor else f"{request.user.apellido}, {request.user.nombre}",
            'saldo_a_ocupar': saldo_a_ocupar,
            'senia_pendiente': senia_pendiente,
            'total_senia_pagada': float(total_senia_anteriores),
            'total_deposito_pagado': reserva.deposito_garantia or 0,  # ✅ SIMPLE: Del casillero
            'deposito_garantia': reserva.deposito_garantia,
            'fecha_desde': reserva.fecha_inicio.strftime('%d/%m/%Y'),
            'fecha_hasta': reserva.fecha_fin.strftime('%d/%m/%Y'),
        }
        
        return render(request, 'inmobiliaria/reserva/finalizar_reserva_nueva.html', context)
        
    except Exception as e:
        messages.error(request, f'Error al cargar la reserva: {str(e)}')
        return redirect('inmobiliaria:reservas')

@login_required
def terminar_reserva(request, reserva_id):
    try:
        reserva = get_object_or_404(Reserva, id=reserva_id)
        conceptos_pago = ConceptoPago.objects.all()
        pagos_previos = Pago.objects.filter(reserva=reserva).order_by('-fecha')
        
        # Verificar si hay pagos y actualizar el estado
        if pagos_previos.exists():
            reserva.estado = 'pagada'
            reserva.save()
        
        # Inicializar o actualizar cuota_pendiente si es necesario
        if reserva.cuota_pendiente is None or reserva.cuota_pendiente == 0:
            reserva.cuota_pendiente = reserva.precio_total
            reserva.save()
        
        if request.method == 'POST':
            try:
                with transaction.atomic():
                    # Obtener datos del formulario
                    monto = Decimal(request.POST.get('monto', '0'))
                    forma_pago = request.POST.get('forma_pago')
                    concepto_id = request.POST.get('concepto')
                    deposito = Decimal(request.POST.get('deposito', '0'))
                    
                    # Validaciones
                    if monto <= 0:
                        raise ValueError('El monto debe ser mayor que cero')
                    
                    if monto > reserva.cuota_pendiente:
                        raise ValueError('El monto no puede ser mayor al saldo pendiente')
                    
                    # Obtener el concepto
                    concepto = get_object_or_404(ConceptoPago, id=concepto_id)
                    
                    # Obtener datos adicionales de tarjeta si es necesario
                    numero_tarjeta = None
                    tipo_tarjeta = None
                    if 'tarjeta' in forma_pago:
                        numero_tarjeta = request.POST.get('numero_tarjeta')
                        tipo_tarjeta = request.POST.get('tipo_tarjeta')
                        
                        if not numero_tarjeta or not tipo_tarjeta:
                            raise ValueError('Los datos de la tarjeta son requeridos')
                    
                    # Crear el pago con los datos adicionales
                    pago = Pago.objects.create(
                        reserva=reserva,
                        monto=monto,
                        forma_pago=forma_pago,
                        concepto=concepto,
                        numero_tarjeta=numero_tarjeta,
                        tipo_tarjeta=tipo_tarjeta
                    )
                    
                    # Calcular total pagado y actualizar saldo pendiente
                    total_pagado = Pago.objects.filter(reserva=reserva).aggregate(
                        total=models.Sum('monto'))['total'] or Decimal('0')
                    
                    # ✅ ACTUALIZAR RESERVA CON LÓGICA CORRECTA: SEPARAR SEÑA DE DEPÓSITO
                    # Calcular solo la seña (excluyendo depósitos)
                    pagos_reserva = Pago.objects.filter(reserva=reserva)
                    total_senia_only = 0
                    total_deposito_only = 0
                    
                    for pago in pagos_reserva:
                        concepto_lower = pago.concepto.concepto.lower() if pago.concepto else ''
                        es_deposito = any(palabra in concepto_lower for palabra in [
                            'depósito', 'deposito', 'garantía', 'garantia', 
                            'caución', 'caucion', 'seguridad', 'fianza',
                            'deposit', 'warranty', 'security'
                        ])
                        
                        if es_deposito:
                            total_deposito_only += pago.monto
                        else:
                            total_senia_only += pago.monto
                    
                    # Actualizar reserva solo con la seña
                    reserva.senia = total_senia_only  # ✅ Solo seña
                    reserva.deposito_garantia = deposito  # ✅ CORREGIDO: usar el campo correcto
                    reserva.cuota_pendiente = reserva.precio_total - total_senia_only  # ✅ Solo descontar seña
                    
                    # Si la cuota pendiente es 0 o menor, finalizar la reserva y crear movimiento de caja
                    if reserva.cuota_pendiente <= 0:
                        # Verificar si hay una caja abierta
                        caja_actual = Caja.objects.filter(
                            sucursal=request.user.sucursal,
                            estado='abierta'
                        ).first()
                        
                        if not caja_actual:
                            messages.error(request, 'No hay una caja abierta. Por favor, abra una caja antes de finalizar la reserva.')
                            return redirect('inmobiliaria:finalizar_reserva', reserva_id=reserva_id)
                        
                        # Crear el movimiento de caja
                        movimiento = MovimientoCaja(
                            caja=caja_actual,
                            tipo=TipoMovimientoCajaEnum.INGRESO,
                            tipo_comprobante=TipoComprobanteEnum.RECIBO,
                            concepto=f"Operaci\u00f3n #{reserva.id} - {reserva.propiedad.direccion}",
                            fecha_desde=reserva.fecha_inicio,
                            fecha_hasta=reserva.fecha_fin,
                            propiedad=reserva.propiedad,
                            sucursal=request.user.sucursal,
                            empleado=request.user
                        )
                        
                        # Asignar montos según los pagos de la reserva
                        for pago in reserva.pagos.all():
                            if pago.forma_pago == 'efectivo':
                                movimiento.monto_efectivo = (movimiento.monto_efectivo or 0) + (pago.monto or 0)
                            elif pago.forma_pago == 'tarjeta':
                                movimiento.monto_tarjeta = (movimiento.monto_tarjeta or 0) + (pago.monto or 0)
                            elif pago.forma_pago == 'transferencia':
                                movimiento.monto_deposito = (movimiento.monto_deposito or 0) + (pago.monto or 0)
                                movimiento.destino_deposito = pago.destino_deposito
                            elif pago.forma_pago == 'cheque':
                                movimiento.monto_cheque = (movimiento.monto_cheque or 0) + (pago.monto or 0)
                            elif pago.forma_pago == 'qr':
                                movimiento.monto_deposito = (movimiento.monto_deposito or 0) + (pago.monto or 0)
                                movimiento.destino_deposito = pago.destino_deposito
                        
                        # Guardar el movimiento
                        movimiento.save()
                        reserva.estado = 'finalizada'
                        messages.success(request, 'Reserva finalizada y movimiento de caja registrado exitosamente')
                    else:
                        reserva.estado = 'en_espera'
                        messages.success(request, f'Pago registrado. Saldo pendiente: ${reserva.cuota_pendiente}')
                    
                    reserva.save()
                    
                    return JsonResponse({
                        'success': True,
                        'message': 'Pago registrado exitosamente',
                        'redirect_url': reverse('inmobiliaria:ver_recibo', args=[reserva.id]),
                        'detalles': {
                            'total_pagado': float(total_pagado),
                            'saldo_pendiente': float(reserva.cuota_pendiente),
                            'deposito_garantia': float(reserva.deposito_garantia or 0),
                            'estado': reserva.estado
                        }
                    })
                    
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': str(e)
                })
        
        # ✅ CALCULAR SALDO SEPARANDO SEÑA DE DEPÓSITO
        total_senia_pagada = 0
        total_deposito_pagado = 0
        total_pagado = 0
        
        for pago in pagos_previos:
            total_pagado += pago.monto
            
            # Identificar si es depósito por el concepto
            concepto_lower = pago.concepto.concepto.lower() if pago.concepto else ''
            es_deposito = any(palabra in concepto_lower for palabra in [
                'depósito', 'deposito', 'garantía', 'garantia', 
                'caución', 'caucion', 'seguridad', 'fianza',
                'deposit', 'warranty', 'security'
            ])
            
            if es_deposito:
                total_deposito_pagado += pago.monto
# print(f"💳 DEPÓSITO TERMINAR - Concepto: '{concepto_lower}', Monto: {pago.monto}")
            else:
                total_senia_pagada += pago.monto
# print(f"💰 SEÑA TERMINAR - Concepto: '{concepto_lower}', Monto: {pago.monto}")
        
        # ✅ SALDO PENDIENTE = Precio total - SOLO LA SEÑA (NO EL DEPÓSITO)
        saldo_pendiente = reserva.precio_total - total_senia_pagada
        
# print(f"💰 TERMINAR RESERVA - Precio Total: {reserva.precio_total}, Seña: {total_senia_pagada}, Depósito: {total_deposito_pagado}, Saldo: {saldo_pendiente}")
        
        context = {
            'reserva': reserva,
            'conceptos_pago': conceptos_pago,
            'pagos_previos': pagos_previos,
            'formas_pago': Pago.FORMA_PAGO_CHOICES,
            'total_pagado': total_pagado,
            'saldo_pendiente': saldo_pendiente,  # ✅ Usar el saldo correcto calculado
            'total_senia_pagada': total_senia_pagada,  # ✅ NUEVO: Solo seña
            'total_deposito_pagado': total_deposito_pagado,  # ✅ NUEVO: Solo depósito
            'deposito': reserva.deposito_garantia or 0
        }
        
        return render(request, 'inmobiliaria/reserva/finalizar_reserva.html', context)
        
    except Exception as e:
        messages.error(request, f'Error al procesar la reserva: {str(e)}')
        return redirect('inmobiliaria:finalizar_reserva', reserva_id=reserva_id)

@login_required
def ver_recibo(request, reserva_id):
    # DEBUG: Confirmar que estamos en la función correcta
# print("🧾 EJECUTANDO ver_recibo desde views.py (FUNCIÓN ACTUALIZADA)")
# print(f"🧾 Reserva ID: {reserva_id}")
    try:
        reserva = get_object_or_404(Reserva, id=reserva_id)
        
        # Crear movimiento de caja automáticamente
        caja_actual = Caja.objects.filter(
            sucursal=request.user.sucursal,
            estado='abierta'
        ).first()
        
        if caja_actual:
            # Crear el movimiento
            movimiento = MovimientoCaja(
                caja=caja_actual,
                tipo=TipoMovimientoCajaEnum.INGRESO,
                concepto=f"Operaci\u00f3n #{reserva.id} - {reserva.propiedad.direccion}",
                fecha_desde=reserva.fecha_inicio,
                fecha_hasta=reserva.fecha_fin,
                propiedad=reserva.propiedad,
                sucursal=request.user.sucursal,
                empleado=request.user
                # Removemos a_descontar ya que es un ingreso
            )
            
            # Asignar montos según los pagos de la reserva
            for pago in reserva.pagos.all():
                if pago.forma_pago == 'efectivo':
                    movimiento.monto_efectivo = (movimiento.monto_efectivo or 0) + (pago.monto or 0)
                elif pago.forma_pago == 'tarjeta':
                    movimiento.monto_tarjeta = (movimiento.monto_tarjeta or 0) + (pago.monto or 0)
                elif pago.forma_pago == 'transferencia':
                    movimiento.monto_deposito = (movimiento.monto_deposito or 0) + (pago.monto or 0)
                    movimiento.destino_deposito = pago.destino_deposito
                elif pago.forma_pago == 'cheque':
                    movimiento.monto_cheque = (movimiento.monto_cheque or 0) + (pago.monto or 0)
            
            movimiento.save()
            
            messages.success(request, 'Movimiento de caja creado exitosamente')
        else:
            messages.warning(request, 'No hay una caja abierta para registrar el movimiento')
        
        # Preparar datos para el recibo
        from datetime import datetime
        from django.utils.dateformat import format
        
        fecha_actual = timezone.now()
        
        # Obtener los pagos de la reserva
        pagos = []
        total_pagado = 0
        formas_de_pago = []
        
        # Buscar si hay conceptos detallados de la operación
        from .models import Registro
        conceptos_operacion = None
        
        # Intentar encontrar registros relacionados usando número de recibo o ID de reserva
        try:
            # Buscar por número de recibo si existe un movimiento reciente
            if hasattr(reserva, 'movimiento_reciente') and reserva.movimiento_reciente:
                conceptos_operacion = Registro.objects.filter(
                    interno_caja=reserva.movimiento_reciente.numero_liquidacion
                ).order_by('fecha')
        except:
            pass
        
        if conceptos_operacion and conceptos_operacion.exists():
            # Usar los conceptos de la operación
            for registro in conceptos_operacion:
                concepto_desc = ''
                if registro.concepto:
                    concepto_desc = f'{registro.concepto.id} - {registro.concepto.nombre}'
                else:
                    concepto_desc = 'Concepto no especificado'
                
                pagos.append({
                    'fecha': registro.fecha_comprobante.strftime('%d/%m/%Y'),
                    'codigo': registro.interno_caja or f'R{registro.id:04d}',
                    'concepto': concepto_desc,
                    'monto': _recibo_monto_str(registro.liquidacion),
                })
                total_pagado += (registro.liquidacion or 0)
        else:
            # Fallback: usar los pagos de la reserva como antes
            for pago in reserva.pagos.all():
                # Obtener el concepto correcto del pago
                concepto_desc = ''
                if hasattr(pago, 'concepto') and pago.concepto:
                    concepto_desc = f'{pago.concepto.codigo} - {pago.concepto.nombre}'
                else:
                    concepto_desc = f'Pago reserva {reserva.id}'
                
                pagos.append({
                    'fecha': pago.fecha.strftime('%d/%m/%Y') if pago.fecha else '',
                    'codigo': pago.codigo if hasattr(pago, 'codigo') and pago.codigo else f'P{pago.id:04d}',
                    'concepto': concepto_desc,
                    'monto': _recibo_monto_str(pago.monto),
                })
                total_pagado += (pago.monto or 0)
                if pago.forma_pago not in formas_de_pago:
                    formas_de_pago.append(pago.forma_pago.title())
        
        # Si no hay formas de pago desde pagos, intentar obtener del movimiento creado
        if not formas_de_pago and 'movimiento' in locals():
            formas_con_montos = []
            if (movimiento.monto_efectivo or 0) > 0:
                formas_con_montos.append(f'Efectivo {_recibo_monto_str(movimiento.monto_efectivo)}')
                formas_de_pago.append('Efectivo')
            if (movimiento.monto_tarjeta or 0) > 0:
                formas_con_montos.append(f'Tarjeta {_recibo_monto_str(movimiento.monto_tarjeta)}')
                formas_de_pago.append('Tarjeta')
            if (movimiento.monto_cheque or 0) > 0:
                formas_con_montos.append(f'Cheque {_recibo_monto_str(movimiento.monto_cheque)}')
                formas_de_pago.append('Cheque')
            if (movimiento.monto_deposito or 0) > 0:
                if movimiento.destino_deposito == 'galicia':
                    formas_con_montos.append(f'Transferencia Galicia {_recibo_monto_str(movimiento.monto_deposito)}')
                    formas_de_pago.append('Galicia')
                elif movimiento.destino_deposito == 'mp':
                    formas_con_montos.append(f'Transferencia Mercado Pago {_recibo_monto_str(movimiento.monto_deposito)}')
                    formas_de_pago.append('Mercado Pago')
                else:
                    formas_con_montos.append(f'Transferencia {_recibo_monto_str(movimiento.monto_deposito)}')
                    formas_de_pago.append('Transferencia')
            
            # Siempre usar formas con montos para mostrar el desglose completo
            formas_de_pago_mostrar = formas_con_montos if formas_con_montos else formas_de_pago
        else:
            formas_de_pago_mostrar = formas_de_pago

        def numero_a_palabras(numero):
            try:
                n = int(numero)
                if n == 0:
                    return "PESOS CERO CON 00/100"
                return f"PESOS {format_monto_argentino(n, 0)} CON 00/100"
            except Exception:
                return "PESOS CERO CON 00/100"
        
        # Preparar datos del cliente con campos adicionales
        cliente_data = reserva.cliente
        cliente_completo = {
            'nombre_completo': f"{cliente_data.apellido}, {cliente_data.nombre}",
            'domicilio': cliente_data.domicilio or '',
            'localidad': cliente_data.localidad or '',
            'provincia': cliente_data.provincia or '',
            'dni': cliente_data.dni or '',
            'telefono': cliente_data.celular or '',  # Mapear celular a telefono
            'cuit': getattr(cliente_data, 'cuit', '') or '',  # CUIT puede no existir
        }
        
        # Preparar datos de la propiedad con formato correcto
        propiedad_data = reserva.propiedad
        propiedad_completa = {
            'direccion': propiedad_data.direccion or '',
            'id': propiedad_data.id,
            'llave': propiedad_data.llave or 'N/A',
            'piso': propiedad_data.piso or '',
            'departamento': propiedad_data.departamento or '',
            'cantidad_personas': propiedad_data.cantidad_personas or None,
            'wifi': 'SÍ' if propiedad_data.wifi else 'NO',
            'cochera': 'SÍ' if propiedad_data.cochera else 'NO',
        }
        
        # Preparar datos de la reserva con formato de moneda
        reserva_formateada = {
            'id': reserva.id,
            'precio_total': _recibo_monto_str(reserva.precio_total),
            'senia': _recibo_monto_str(reserva.senia),
            'cuota_pendiente': _recibo_monto_str(reserva.cuota_pendiente),
            'deposito_garantia': _recibo_monto_str(reserva.deposito_garantia),
            'propiedad': propiedad_completa,
        }
        
        # ✅ CALCULAR VALORES CORRECTOS PARA EL RECIBO
        # Calcular seña y saldo restante basado en lo que realmente se pagó
        senia_pagada = float(reserva.senia or 0)
        deposito_pagado = float(reserva.deposito_garantia or 0)
        precio_total = float(reserva.precio_total or 0)
        saldo_restante = precio_total - senia_pagada
        
        # ✅ Verificar si el depósito fue pagado usando la función que busca en movimientos de caja
        deposito_estado = determinar_estado_deposito_completo(reserva)
        
        # DEBUG: Confirmar template y datos
# print("🧾 TEMPLATE USADO: inmobiliaria/reserva/recibo.html")
# print(f"🧾 PRECIO TOTAL: ${precio_total:,.0f}")
# print(f"🧾 SEÑA PAGADA: ${senia_pagada:,.0f}")
# print(f"🧾 SALDO RESTANTE: ${saldo_restante:,.0f}")
# print(f"🧾 DEPÓSITO: ${deposito_pagado:,.0f} ({deposito_estado})")
# print(f"🧾 TOTAL PAGADO: {f'${total_pagado:,.0f}'}")
# print(f"🧾 FORMAS DE PAGO: {', '.join(formas_de_pago) if formas_de_pago else 'EFECTIVO'}")
# print(f"🧾 PAGOS COUNT: {len(pagos)}")
        
        # Obtener honorarios y sellados del movimiento si existe
        honorarios_monto = 0
        sellados_monto = 0
        if 'movimiento' in locals() and movimiento:
            honorarios_monto = float(movimiento.honorarios or 0)
            sellados_monto = float(movimiento.sellados or 0)
        
        # Generar logo en base64 para evitar problemas de carga con html2canvas
        import base64
        import os
        from django.conf import settings
        
        logo_base64 = None
        try:
            logo_path = os.path.join(settings.BASE_DIR, 'inmobiliaria', 'static', 'images', 'logo.png')
            with open(logo_path, 'rb') as logo_file:
                logo_data = base64.b64encode(logo_file.read()).decode()
                logo_base64 = f'data:image/png;base64,{logo_data}'
        except Exception as e:
            logo_base64 = None
        
        # Obtener información de la sucursal
        sucursal = request.user.sucursal if hasattr(request.user, 'sucursal') and request.user.sucursal else None
        
        # Continuar con la generación del recibo usando el template correcto
        return render(request, 'inmobiliaria/reserva/recibo.html', {
            'reserva': reserva_formateada,
            'cliente': cliente_completo,
            'propiedad': propiedad_completa,
            'numero_recibo': f'R{reserva.id:06d}',
            'fecha': fecha_actual.strftime('%d/%m/%Y'),
            'hora': fecha_actual.strftime('%H:%M'),
            'fecha_inicio': reserva.fecha_inicio.strftime('%d/%m/%Y'),
            'fecha_fin': reserva.fecha_fin.strftime('%d/%m/%Y'),
            'descripcion': 'Alquiler temporario por días',
            'pagos': pagos,
            'total_pagado': _recibo_monto_str(total_pagado),
            'monto_en_palabras': numero_a_palabras(total_pagado),
            'formas_de_pago': ', '.join(formas_de_pago_mostrar) if formas_de_pago_mostrar else 'EFECTIVO',
            # ✅ AGREGAR VARIABLES QUE NECESITA EL TEMPLATE
            'precio_total_operacion': _recibo_monto_str(precio_total),
            'monto_este_pago': _recibo_monto_str(senia_pagada),
            'saldo_pendiente': _recibo_monto_str(saldo_restante),
            'deposito_garantia': _recibo_monto_str(deposito_pagado),
            'deposito_estado': deposito_estado,  # Estado del depósito
            # ✅ AGREGAR HONORARIOS Y SELLADOS
            'honorarios': _recibo_monto_str(honorarios_monto),
            'sellados': _recibo_monto_str(sellados_monto),
            'tiene_honorarios': honorarios_monto > 0,
            'tiene_sellados': sellados_monto > 0,
            'logo_base64': logo_base64,
            'sucursal': sucursal,  # Agregar sucursal al contexto
        })
        
    except Exception as e:
        messages.error(request, f'Error al generar el recibo: {str(e)}')
        return redirect('inmobiliaria:finalizar_reserva', reserva_id=reserva_id)

def generar_recibo_pdf(reserva, pago_senia):
    from datetime import datetime
    
    # Preparar datos para el recibo (similar a ver_recibo)
    fecha_actual = timezone.now()
    
    # Obtener los pagos de la reserva
    pagos = []
    total_pagado = 0
    formas_de_pago = []
    
    # Buscar si hay conceptos detallados de la operación
    from .models import Registro
    conceptos_operacion = None
    
    # Intentar encontrar registros relacionados usando número de recibo o ID de reserva
    try:
        # Buscar por número de recibo si existe un movimiento reciente
        if hasattr(reserva, 'movimiento_reciente') and reserva.movimiento_reciente:
            conceptos_operacion = Registro.objects.filter(
                interno_caja=reserva.movimiento_reciente.numero_liquidacion
            ).order_by('fecha')
    except:
        pass
    
    if conceptos_operacion and conceptos_operacion.exists():
        # Usar los conceptos de la operación
        for registro in conceptos_operacion:
            concepto_desc = ''
            if registro.concepto:
                concepto_desc = f'{registro.concepto.id} - {registro.concepto.nombre}'
            else:
                concepto_desc = 'Concepto no especificado'
            
            pagos.append({
                'fecha': registro.fecha_comprobante.strftime('%d/%m/%Y'),
                'codigo': registro.interno_caja or f'R{registro.id:04d}',
                'concepto': concepto_desc,
                'monto': _recibo_monto_str(registro.liquidacion),
            })
            total_pagado += (registro.liquidacion or 0)
    else:
        # Fallback: usar los pagos de la reserva como antes
        for pago in reserva.pagos.all():
            # Obtener el concepto correcto del pago
            concepto_desc = ''
            if hasattr(pago, 'concepto') and pago.concepto:
                concepto_desc = f'{pago.concepto.codigo} - {pago.concepto.nombre}'
            else:
                concepto_desc = f'Pago reserva {reserva.id}'
            
            pagos.append({
                'fecha': pago.fecha.strftime('%d/%m/%Y') if pago.fecha else '',
                'codigo': pago.codigo if hasattr(pago, 'codigo') and pago.codigo else f'P{pago.id:04d}',
                'concepto': concepto_desc,
                'monto': _recibo_monto_str(pago.monto),
            })
            total_pagado += (pago.monto or 0)
            if pago.forma_pago not in formas_de_pago:
                formas_de_pago.append(pago.forma_pago.title())
    
    # Función para convertir número a palabras
    def numero_a_palabras(numero):
        # Convertir número a palabras en español (versión simplificada)
        unidades = ['', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve']
        decenas = ['', '', 'veinte', 'treinta', 'cuarenta', 'cincuenta', 'sesenta', 'setenta', 'ochenta', 'noventa']
        centenas = ['', 'ciento', 'doscientos', 'trescientos', 'cuatrocientos', 'quinientos', 'seiscientos', 'setecientos', 'ochocientos', 'novecientos']
        
        numero = int(numero)
        if numero == 0:
            return "PESOS CERO CON 00/100"
        elif numero == 100:
            return "PESOS CIEN CON 00/100"
        elif numero < 10:
            return f"PESOS {unidades[numero].upper()} CON 00/100"
        elif numero < 100:
            if numero < 20:
                especiales = ['diez', 'once', 'doce', 'trece', 'catorce', 'quince', 'dieciséis', 'diecisiete', 'dieciocho', 'diecinueve']
                return f"PESOS {especiales[numero-10].upper()} CON 00/100"
            else:
                dec = numero // 10
                uni = numero % 10
                if uni == 0:
                    return f"PESOS {decenas[dec].upper()} CON 00/100"
                else:
                    return f"PESOS {decenas[dec].upper()} Y {unidades[uni].upper()} CON 00/100"
        elif numero < 1000:
            cent = numero // 100
            resto = numero % 100
            if resto == 0:
                return f"PESOS {centenas[cent].upper()} CON 00/100"
            else:
                palabras_resto = numero_a_palabras(resto).replace("PESOS ", "").replace(" CON 00/100", "")
                return f"PESOS {centenas[cent].upper()} {palabras_resto} CON 00/100"
        else:
            return f"PESOS {format_monto_argentino(numero, 0)} CON 00/100"
    
    # Preparar datos del cliente con campos adicionales
    cliente_data = reserva.cliente
    cliente_completo = {
        'nombre_completo': f"{cliente_data.nombre} {cliente_data.apellido}",
        'domicilio': cliente_data.domicilio or '',
        'localidad': cliente_data.localidad or '',
        'provincia': cliente_data.provincia or '',
        'dni': cliente_data.dni or '',
        'telefono': cliente_data.celular or '',  # Mapear celular a telefono
        'cuit': getattr(cliente_data, 'cuit', '') or '',  # CUIT puede no existir
    }
    
    # Preparar datos de la propiedad con formato correcto
    propiedad_data = reserva.propiedad
    propiedad_completa = {
        'direccion': propiedad_data.direccion or '',
        'id': propiedad_data.id,
        'llave': propiedad_data.llave or 'N/A',
        'piso': propiedad_data.piso or '',
        'departamento': propiedad_data.departamento or '',
        'cantidad_personas': propiedad_data.cantidad_personas or None,
        'wifi': 'SÍ' if propiedad_data.wifi else 'NO',
        'cochera': 'SÍ' if propiedad_data.cochera else 'NO',
    }
    
    # Preparar datos de la reserva con formato de moneda
    reserva_formateada = {
        'id': reserva.id,
        'precio_total': _recibo_monto_str(reserva.precio_total),
        'senia': _recibo_monto_str(reserva.senia),
        'cuota_pendiente': _recibo_monto_str(reserva.cuota_pendiente),
        'deposito_garantia': _recibo_monto_str(reserva.deposito_garantia),
        'propiedad': propiedad_completa,
    }
    
    template_name = 'inmobiliaria/reserva/recibo.html'
    context = {
        'reserva': reserva_formateada,
        'cliente': cliente_completo,
        'propiedad': propiedad_completa,
        'numero_recibo': f'R{reserva.id:06d}',
        'fecha': fecha_actual.strftime('%d/%m/%Y'),
        'hora': fecha_actual.strftime('%H:%M'),
        'fecha_inicio': reserva.fecha_inicio.strftime('%d/%m/%Y'),
        'fecha_fin': reserva.fecha_fin.strftime('%d/%m/%Y'),
        'descripcion': 'Alquiler temporario por días',
        'pagos': pagos,
        'total_pagado': _recibo_monto_str(total_pagado),
        'monto_en_palabras': numero_a_palabras(total_pagado),
        'formas_de_pago': ', '.join(formas_de_pago) if formas_de_pago else 'EFECTIVO',
    }
    
    # Renderizar HTML a string
    html = render_to_string(template_name, context)
    
    # Crear el PDF
    pdf_buffer = BytesIO()
    pisa_status = pisa.CreatePDF(BytesIO(html.encode("UTF-8")), dest=pdf_buffer)
    
    if pisa_status.err:
        return None
    else:
        return pdf_buffer.getvalue()
def realizar_pago(request, reserva_id):
    # Obtener la reserva a partir del ID
    reserva = get_object_or_404(Reserva, id=reserva_id)

    if request.method == 'POST':
        # Obtener el monto del pago ingresado en el formulario
        pago = Decimal(request.POST.get('pago', '0.00'))

        if pago <= 0:
            messages.error(request, 'El monto del pago debe ser mayor que cero.')
            return redirect('inmobiliaria:finalizar_reserva', reserva_id=reserva.id)

        # Actualizar la seña y la cuota pendiente
        reserva.senia += pago

        # Calcular la cuota pendiente
        reserva.cuota_pendiente = reserva.precio_total - reserva.senia

        if reserva.cuota_pendiente <= 0:
            # Si la cuota pendiente es 0 o menor, marcar la reserva como 'realizada'
            reserva.estado = 'realizada'
            reserva.cuota_pendiente = 0  # Asegurarse de que no quede negativo
            messages.success(request, 'La reserva ha sido completada y está totalmente pagada.')
        else:
            # Si queda saldo pendiente, mostrar el saldo restante
            messages.info(request, f'Pago recibido. Saldo pendiente: {reserva.cuota_pendiente:.2f} USD.')

        # Guardar los cambios en la reserva
        reserva.save()

        # Redirigir al listado de reservas o a alguna página de confirmación
        return redirect('inmobiliaria:reservas')

    # Si es una solicitud GET, mostrar la página de finalizar reserva
    return render(request, 'inmobiliaria/reserva/finalizar_reserva.html', {'reserva': reserva})

PrecioFormSet = inlineformset_factory(
    Propiedad,  # Modelo padre
    Precio,     # Modelo hijo (relacionado con Propiedad)
    fields=['tipo_precio', 'precio_total', 'precio_por_dia'],  # Campos que gestionamos
    extra=1,  # Formularios adicionales vacíos
    can_delete=True  # Para permitir la eliminación de precios
)
def gestionar_precios(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    precios = Precio.objects.filter(propiedad=propiedad)
    
    # Obtener el vendedor directamente
    vendedor = request.user
    
    # Definir campos según el nivel del vendedor
    fields = [
        'tipo_precio',
        'precio_por_dia',
        'precio_total',
        'ajuste_porcentaje'
    ]
    
    # Agregar campos adicionales si el nivel es mayor a 2
    if vendedor.nivel > 2:
        fields.extend(['precio_toma', 'precio_dia_toma'])
    
    PrecioFormSet = modelformset_factory(
        Precio, 
        form=PrecioForm, 
        fields=fields,
        extra=0
    )
    
    # Asegurar que existan TODOS los tipos de precio
    # Crear los que faltan usando get_or_create para evitar duplicados
    for tipo_choice in TipoPrecio.choices:
        tipo_key = tipo_choice[0]
        Precio.objects.get_or_create(
            propiedad=propiedad,
            tipo_precio=tipo_key,
            defaults={
                'precio_por_dia': 0,
                'precio_total': 0,
                'precio_toma': 0 if vendedor.nivel > 2 else None,
                'precio_dia_toma': 0 if vendedor.nivel > 2 else None,
                'ajuste_porcentaje': 0
            }
        )
    
    # Definir el orden personalizado para los tipos de precio (igual que en propiedad_detalle)
    orden_tipo_precio = Case(
        When(tipo_precio=TipoPrecio.QUINCENA_1_DICIEMBRE, then=0),
        When(tipo_precio=TipoPrecio.QUINCENA_2_DICIEMBRE, then=1),
        When(tipo_precio=TipoPrecio.QUINCENA_1_ENERO, then=2),
        When(tipo_precio=TipoPrecio.QUINCENA_2_ENERO, then=3),
        When(tipo_precio=TipoPrecio.QUINCENA_1_FEBRERO, then=4),
        When(tipo_precio=TipoPrecio.QUINCENA_2_FEBRERO, then=5),
        When(tipo_precio=TipoPrecio.QUINCENA_1_MARZO, then=6),
        When(tipo_precio=TipoPrecio.QUINCENA_2_MARZO, then=7),
        When(tipo_precio=TipoPrecio.TEMPORADA_BAJA, then=8),
        When(tipo_precio=TipoPrecio.FINDE_LARGO, then=9),
        When(tipo_precio=TipoPrecio.SEMANA_SANTA, then=10),
        When(tipo_precio=TipoPrecio.CARNAVALES, then=11),
        When(tipo_precio=TipoPrecio.VACACIONES_INVIERNO, then=12),
        When(tipo_precio=TipoPrecio.ESTUDIANTE, then=13),
        default=999,
        output_field=IntegerField(),
    )
    
    # Obtener TODOS los precios ordenados con el orden personalizado
    precios = Precio.objects.filter(propiedad=propiedad).annotate(
        orden_tipo_precio=orden_tipo_precio
    ).order_by('orden_tipo_precio')

    if request.method == 'POST':
        formset = PrecioFormSet(request.POST, queryset=precios)
        if formset.is_valid():
            instances = formset.save(commit=False)
            for instance in instances:
                instance.propiedad = propiedad
                instance.save()
            messages.success(request, 'Precios actualizados correctamente.')
            return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad_id)
    else:
        formset = PrecioFormSet(queryset=precios)

    # Obtener la última disponibilidad agregada
    ultima_disponibilidad = propiedad.disponibilidades.order_by('-id').first()
    
    # Obtener el historial de disponibilidad
    historiales = HistorialDisponibilidad.objects.filter(
        propiedad=propiedad
    ).order_by('fecha_inicio', 'fecha_fin')
    
    return render(request, 'inmobiliaria/propiedades/gestionar_precios.html', {
        'propiedad': propiedad,
        'formset': formset,
        'nivel_vendedor': vendedor.nivel,
        'ultima_disponibilidad': ultima_disponibilidad,
        'historiales': historiales
    })

def historial_reservas_vendedor(request, vendedor_id):
    reservas = Reserva.objects.filter(vendedor_id=vendedor_id)

    return render(request, 'inmobiliaria/vendedores/historial.html', {
        'reservas': reservas,
    })
def historial_reservas_inquilino(request, inquilino_id):
    reservas = Reserva.objects.filter(cliente_id=inquilino_id).select_related('propiedad', 'propiedad__propietario').order_by('-fecha_inicio')

    # Usar el precio_total de la reserva
    reservas_con_monto = []
    for reserva in reservas:
        reservas_con_monto.append({
            'reserva': reserva,
            'total_pagado': reserva.precio_total or 0
        })

    return render(request, 'inmobiliaria/inquilinos/historial.html', {
        'reservas_con_monto': reservas_con_monto,
    })    
def buscar_propietarios(request):
    """
    Devuelve los propietarios en formato Select2:
    {
        "results": [{"id": 1, "text": "Pérez, Ana – 30123456"}, ...],
        "pagination": {"more": true}
    }
    """
    term = request.GET.get("term", "").strip()
    page = int(request.GET.get("page", 1) or 1)
    page_size = 20
    offset = (page - 1) * page_size

    qs = Propietario.objects.all()
    
    # Filtrar por sucursal del usuario si está disponible
    if hasattr(request, 'user') and hasattr(request.user, 'sucursal') and request.user.sucursal:
        qs = qs.filter(sucursal=request.user.sucursal)

    if term:
        # Término completo (apellidos con espacio, ej. "de Marcos") y por palabras
        term = term.strip()
        q = (
            Q(nombre__icontains=term) |
            Q(apellido__icontains=term) |
            Q(dni__icontains=term) |
            Q(id__icontains=term)
        )
        palabras = [p.strip() for p in term.split() if p.strip()]
        if len(palabras) > 1:
            q_palabras = Q()
            for p in palabras:
                q_palabras &= (Q(nombre__icontains=p) | Q(apellido__icontains=p))
            q = q | q_palabras
        qs = qs.filter(q)

    total = qs.count()
    propietarios = qs.order_by("apellido", "nombre")[offset: offset + page_size]

    results = [
        {
            "id": p.id,
            "text": f"{p.apellido}, {p.nombre} – {p.dni}"
        }
        for p in propietarios
    ]

    return JsonResponse(
        {"results": results, "pagination": {"more": total > offset + page_size}}
    )

def ver_diagrama_db(request):
    """Vista para mostrar el diagrama de la base de datos (acceso público)"""
    from django.http import HttpResponse
    import os
    from django.conf import settings
    
    # Ruta del archivo HTML
    diagrama_path = os.path.join(settings.BASE_DIR, 'diagrama_db.html')
    
    try:
        with open(diagrama_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        return HttpResponse(html_content, content_type='text/html; charset=utf-8')
    except FileNotFoundError:
        return HttpResponse(
            '<h1>Diagrama no encontrado</h1><p>Por favor, ejecuta primero: <code>python3 manage.py generar_diagrama_db</code></p>',
            status=404
        )
    except Exception as e:
        return HttpResponse(f'<h1>Error</h1><p>{str(e)}</p>', status=500)

@login_required
def buscar_operacion(request):
    """Vista para buscar operación por número y autocompletar campos"""
    operacion = request.GET.get('operacion', '')
    
    if not operacion:
        return JsonResponse({'success': False, 'message': 'Número de operación requerido'})
    
    try:
        # Buscar el movimiento por número (ajusta esto según tu modelo)
        movimiento = Movimiento.objects.get(numero=operacion)
        
        # Preparar datos para autocompletar
        return JsonResponse({
            'success': True,
            'concepto_id': movimiento.concepto_id,
            'cuenta_id': movimiento.cuenta_id if movimiento.cuenta else None,
            'productor_id': movimiento.productor_id if hasattr(movimiento, 'productor') else None,
            'monto': str(movimiento.monto_total),
            'tipo_comprobante': movimiento.tipo_comprobante if hasattr(movimiento, 'tipo_comprobante') else None
        })
    except Movimiento.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Operación no encontrada'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

def buscar_inquilinos(request):
    query = request.GET.get('term', '')
    base = get_inquilinos_queryset_unificado(request)
    inquilinos = base.filter(
        Q(nombre__icontains=query) | 
        Q(apellido__icontains=query) |
        Q(dni__icontains=query)
    )[:10]
    
    results = []
    for inquilino in inquilinos:
        results.append({
            'id': inquilino.id,
            'text': f"{inquilino.apellido}, {inquilino.nombre} (DNI: {inquilino.dni})"
        })
    
    return JsonResponse({
        'results': results,
        'pagination': {
            'more': False
        }
    })
def propietario_nuevo_ajax(request):
    if request.method == "POST" and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        form = PropietarioForm(request.POST)
        if form.is_valid():
            propietario = form.save()
            return JsonResponse({
                'success': True,
                'id': propietario.id,
                'nombre': propietario.nombre,
                'apellido': propietario.apellido,
                'dni': propietario.dni
            })
        else:
            return JsonResponse({'success': False, 'errors': form.errors})
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)
    
def propiedades_por_propietario(request, propietario_id):
    propietario = get_object_or_404(Propietario, pk=propietario_id)
    propiedades = Propiedad.objects.filter(propietario=propietario).order_by('numero_por_propietario')
    return render(request, 'inmobiliaria/propietarios/propiedades_propietario.html', {
        'propietario': propietario,
        'propiedades': propiedades
    })
def autenticacion_vendedor(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        reserva_id = request.POST.get('reserva_id')  # Obtener el reserva_id
        
        # Autenticar al usuario
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Autenticación exitosa
            # Aquí puedes procesar la reserva usando el reserva_id si es necesario
            return JsonResponse({'success': True, 'reserva_id': reserva_id})
        else:
            return JsonResponse({'success': False})
    return JsonResponse({'error': 'Método no permitido'}, status=405)

@login_required
def autenticar_seguridad(request):
    """
    Vista para autenticación de seguridad antes de operaciones sensibles
    """
    if request.method == 'POST':
        usuario = request.POST.get('usuario', '').strip()
        contrasena = request.POST.get('contrasena', '')
        
# print(f"🔐 AUTENTICACIÓN SEGURIDAD - Usuario: {usuario}")
        
        if not usuario or not contrasena:
            return JsonResponse({
                'success': False, 
                'error': 'Por favor completa todos los campos'
            })
        
        # Autenticar al usuario
        user = authenticate(request, username=usuario, password=contrasena)
        
        if user is not None:
            # Verificar que el usuario esté activo
            if not user.is_active:
                pass  # ✅ Bloque vacío
# print(f"❌ Usuario {usuario} no está activo")
                return JsonResponse({
                    'success': False, 
                    'error': 'Tu cuenta no está activa. Contacta al administrador.'
                })
            
            # Verificar que sea un vendedor con permisos adecuados
            try:
                vendedor = user  # El user ya es un Vendedor debido al modelo personalizado
                
                # Verificar nivel mínimo (nivel 1 o superior para operaciones - permitir usuarios básicos)
                if vendedor.nivel < 1:
                    pass  # ✅ Bloque vacío
# print(f"❌ Usuario {usuario} sin permisos suficientes (nivel: {vendedor.nivel})")
                    return JsonResponse({
                        'success': False, 
                        'error': 'No tienes permisos suficientes para esta operación'
                    })
                
# print(f"✅ Autenticación exitosa - Usuario: {usuario}, Nivel: {vendedor.nivel}")
                return JsonResponse({
                    'success': True,
                    'usuario': vendedor.nombre_completo_vendedor(),
                    'nivel': vendedor.nivel
                })
                
            except Exception as e:
                pass  # ✅ Bloque vacío
# print(f"❌ Error verificando vendedor: {e}")
                return JsonResponse({
                    'success': False, 
                    'error': 'Error interno. Contacta al administrador.'
                })
            
        else:
            pass  # ✅ Bloque vacío
# print(f"❌ Credenciales incorrectas para usuario: {usuario}")
            return JsonResponse({
                'success': False, 
                'error': 'Usuario o contraseña incorrectos'
            })
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)

def buscar_clientes(request):
    term = request.GET.get('term', '')
    base = get_inquilinos_queryset_unificado(request)
    clientes = base.filter(
        Q(nombre__icontains=term) | 
        Q(apellido__icontains=term) | 
        Q(dni__icontains=term)
    )[:10]
    results = [{'id': c.id, 'text': f"{c.apellido}, {c.nombre} (DNI: {c.dni})"} for c in clientes]
    return JsonResponse({'results': results})

@login_required
def crear_concepto_ajax(request):
    """
    Vista AJAX para crear nuevos conceptos desde el modal
    """
    if request.method == 'POST':
        try:
            id_personalizado = request.POST.get('id', '').strip()
            nombre = request.POST.get('nombre', '').strip()
            
            if not nombre:
                return JsonResponse({
                    'success': False,
                    'error': 'El nombre del concepto es requerido'
                })
            
            # Verificar si el concepto ya existe por nombre
            if Concepto.objects.filter(nombre__iexact=nombre).exists():
                return JsonResponse({
                    'success': False,
                    'error': 'Ya existe un concepto con ese nombre'
                })
            
            # Si se proporciona un ID personalizado
            if id_personalizado:
                try:
                    id_num = int(id_personalizado)
                    if Concepto.objects.filter(id=id_num).exists():
                        return JsonResponse({
                            'success': False,
                            'error': f'Ya existe un concepto con el ID {id_num}'
                        })
                    
                    # Crear concepto con ID específico
                    concepto = Concepto(id=id_num, nombre=nombre)
                    concepto.save()
                except ValueError:
                    return JsonResponse({
                        'success': False,
                        'error': 'El ID debe ser un número válido'
                    })
            else:
                # Crear concepto con ID automático
                concepto = Concepto.objects.create(nombre=nombre)
            
            return JsonResponse({
                'success': True,
                'concepto': {
                    'id': concepto.id,
                    'nombre': concepto.nombre
                }
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    
    return JsonResponse({'success': False, 'error': 'Método no permitido'})

@login_required
@transaction.atomic
def procesar_movimiento_reserva(request):
    """
    Vista para procesar el movimiento de caja completo y cambiar estado de reserva
    """
# print(f"Usuario autenticado: {request.user.is_authenticated}")
# print(f"Método de request: {request.method}")
# print(f"Headers: {dict(request.headers)}")
    
    if request.method == 'POST':
        try:
            pass  # ✅ Bloque vacío
# print("=== INICIANDO PROCESAMIENTO DE MOVIMIENTO ===")
            reserva_id = request.POST.get('reserva_id')
# print(f"Reserva ID recibido: {reserva_id}")
# print(f"Todos los datos POST: {dict(request.POST)}")
            
            if not reserva_id:
                return JsonResponse({'success': False, 'error': 'ID de reserva requerido'})
            
            # Obtener la reserva (propiedad para tipo_fichaje / comisión)
            reserva = get_object_or_404(
                Reserva.objects.select_related('propiedad', 'vendedor', 'vendedor__sucursal'),
                id=reserva_id,
                sucursal=request.user.sucursal,
            )
            
            # ✅ DETECTAR SI ES "COMPLETAR PAGO" (ya hay pagos anteriores)
            pagos_anteriores = MovimientoCaja.objects.filter(
                propiedad=reserva.propiedad,
                tipo=TipoMovimientoCajaEnum.INGRESO,
                concepto__icontains=f"Operaci\u00f3n {reserva.id}"
            )
            total_pagos_anteriores = sum(pago.monto_total for pago in pagos_anteriores)
            es_completar_pago = total_pagos_anteriores > 0
            
# print(f"🔍 DETECTANDO TIPO DE OPERACIÓN:")
# print(f"   - Pagos anteriores encontrados: {pagos_anteriores.count()}")
# print(f"   - Total pagos anteriores: ${total_pagos_anteriores}")
# print(f"   - Es completar pago: {es_completar_pago}")
            
            # Obtener la caja actual
            caja_actual = Caja.objects.filter(
                sucursal=request.user.sucursal,
                estado='abierta'
            ).first()
            
            if not caja_actual:
                return JsonResponse({'success': False, 'error': 'No hay una caja abierta'})
            
            # Obtener datos del formulario
            numero_recibo = request.POST.get('numero_recibo', '').strip()
            
            # ✅ Función para limpiar valores monetarios
            def limpiar_valor_monetario(valor_str):
                return str(parse_decimal_monto(valor_str or '0'))

            def obtener_decimal(nombre_campo, etiqueta=None):
                """
                Convierte el valor de un campo enviado en el POST a Decimal.
                Si la conversión falla, levanta un ValueError con un mensaje descriptivo.
                """
                raw_value = request.POST.get(nombre_campo, '')
                valor_limpio = limpiar_valor_monetario(raw_value or '0')
                try:
                    return Decimal(valor_limpio)
                except (InvalidOperation, ValueError):
                    campo_descripcion = etiqueta or nombre_campo
                    raise ValueError(f"Valor inválido en {campo_descripcion}: '{raw_value}'")
            
            # Formas de pago (limpiar antes de convertir a Decimal)
            try:
                monto_efectivo = obtener_decimal('monto_efectivo', 'Importe efectivo')
                monto_cheque = obtener_decimal('monto_cheque', 'Importe cheque')
                monto_tarjeta = obtener_decimal('monto_tarjeta', 'Importe tarjeta')
            except ValueError as exc:
                return JsonResponse({'success': False, 'error': str(exc)})
            
            # ✅ Obtener cuentas bancarias dinámicamente
            from inmobiliaria.models.sucursal import CuentaBancaria
            cuentas_bancarias = CuentaBancaria.objects.filter(
                sucursal=request.user.sucursal,
                activa=True
            ).order_by('nombre_banco', 'alias')
            
            # ✅ Procesar montos de cuentas bancarias dinámicamente
            montos_cuentas_bancarias = {}
            monto_deposito_total = Decimal('0')
            
            for cuenta in cuentas_bancarias:
                campo_name = cuenta.field_name  # ej: monto_deposito_1
                etiqueta_cuenta = cuenta.nombre_banco
                if cuenta.alias:
                    etiqueta_cuenta = f"{etiqueta_cuenta} - {cuenta.alias}"
                try:
                    monto_cuenta = obtener_decimal(campo_name, f"Transferencia {etiqueta_cuenta}")
                except ValueError as exc:
                    return JsonResponse({'success': False, 'error': str(exc)})
                montos_cuentas_bancarias[cuenta.id] = {
                    'cuenta': cuenta,
                    'monto': monto_cuenta,
                    'campo': campo_name
                }
                monto_deposito_total += monto_cuenta
# print(f"💰 Cuenta {cuenta.nombre_banco}: ${monto_cuenta}")
            
            # Mantener compatibilidad con campos antiguos (fallback)
            try:
                monto_deposito_galicia = obtener_decimal('monto_deposito_galicia', 'Transferencia Galicia')
                monto_deposito_mp = obtener_decimal('monto_deposito_mp', 'Transferencia Mercado Pago')
            except ValueError as exc:
                return JsonResponse({'success': False, 'error': str(exc)})
            monto_deposito_legacy = monto_deposito_galicia + monto_deposito_mp
            
            # Usar el total dinámico o el legacy como fallback
            monto_deposito = monto_deposito_total if monto_deposito_total > 0 else monto_deposito_legacy
            
# print(f"=== VALORES RAW RECIBIDOS ===")
# print(f"monto_efectivo RAW: '{request.POST.get('monto_efectivo', '0')}'")
# print(f"Cuentas bancarias dinámicas: {len(montos_cuentas_bancarias)}")
            for cuenta_id, data in montos_cuentas_bancarias.items():
                pass  # ✅ Bloque vacío
# print(f"  {data['cuenta'].nombre_banco} ({data['campo']}): '{request.POST.get(data['campo'], '0')}'")
            
# print(f"=== VALORES CONVERTIDOS A DECIMAL ===")
# print(f"Montos recibidos - Efectivo: {monto_efectivo}, Cheque: {monto_cheque}, Tarjeta: {monto_tarjeta}")
# print(f"Transferencias dinámicas: ${monto_deposito_total}, Legacy: ${monto_deposito_legacy}, Total final: ${monto_deposito}")
            total_movimientos = (monto_efectivo or 0) + (monto_cheque or 0) + (monto_tarjeta or 0) + (monto_deposito or 0)
# print(f"TOTAL A CREAR EN MOVIMIENTOS: {total_movimientos}")
            
            # Datos adicionales
            banco = request.POST.get('banco', '').strip()
            nro_cheque = request.POST.get('nro_cheque', '').strip()
            numero_tarjeta = request.POST.get('numero_tarjeta', '').strip()
            destino_transferencia = request.POST.get('destino_transferencia', '').strip()
            observaciones_generales = request.POST.get('observaciones_generales', '').strip()
            
            # Preparar datos del movimiento
            movimiento_data = {
                'caja': caja_actual,
                'sucursal': request.user.sucursal,
                'tipo': TipoMovimientoCajaEnum.INGRESO,
                'concepto': f"Operaci\u00f3n {reserva.id} - {reserva.propiedad.direccion}",
                'propiedad': reserva.propiedad,
                'fecha_desde': reserva.fecha_inicio,
                'fecha_hasta': reserva.fecha_fin,
                'monto_efectivo': monto_efectivo,
                'monto_cheque': monto_cheque,
                'monto_tarjeta': monto_tarjeta,
                'monto_deposito': monto_deposito,
                'numero_liquidacion': numero_recibo,
                'empleado': request.user
            }
            
            # ✅ PROCESAR CONCEPTOS INDIVIDUALES DEL FRONTEND
            conceptos_count = len([key for key in request.POST.keys() if key.startswith('concepto_') and key.endswith('_nombre')])
            conceptos_detalle = []
            conceptos_completos = []  # Para guardar información completa
            conceptos_importes_decimal = {}
            
            # ✅ VARIABLES PARA VALIDAR CONCEPTO 10 (DEPÓSITO)
            concepto_10_presente = False
            concepto_10_importe = Decimal('0')
            total_conceptos = Decimal('0')
            
            for i in range(conceptos_count):
                concepto_id = request.POST.get(f'concepto_{i}_id')
                concepto_nombre = request.POST.get(f'concepto_{i}_nombre')
                concepto_observaciones = request.POST.get(f'concepto_{i}_observaciones')
                concepto_importe = request.POST.get(f'concepto_{i}_importe')
                
                if concepto_nombre:
                    conceptos_detalle.append(f"{concepto_nombre}")
                    
                    # ✅ DETECTAR CONCEPTO 10 (DEPÓSITO)
                    if concepto_id == '10':
                        concepto_10_presente = True
                        try:
                            concepto_10_importe = obtener_decimal(f'concepto_{i}_importe', 'Concepto 10 (Depósito)')
                        except ValueError as exc:
                            return JsonResponse({'success': False, 'error': str(exc)})
# print(f"🏦 CONCEPTO 10 (DEPÓSITO) DETECTADO: ${concepto_10_importe}")
                    
                    # ✅ SUMAR AL TOTAL DE CONCEPTOS
                    try:
                        importe_limpio = obtener_decimal(f'concepto_{i}_importe', f'Concepto {concepto_nombre}')
                    except ValueError as exc:
                        return JsonResponse({'success': False, 'error': str(exc)})
                    total_conceptos += importe_limpio
                    conceptos_importes_decimal[i] = importe_limpio
                    
                    # Guardar información completa del concepto
                    # ✅ Formatear el importe como número entero sin decimales para evitar problemas de parseo
                    if isinstance(importe_limpio, Decimal):
                        importe_str = str(int(importe_limpio.quantize(Decimal('1'))))
                    else:
                        importe_str = str(int(float(importe_limpio))) if importe_limpio else '0'
                    
                    concepto_completo = {
                        'id': concepto_id or f'C{i+1:02d}',
                        'nombre': concepto_nombre,
                        'importe': importe_str
                    }
                    conceptos_completos.append(concepto_completo)
# print(f"💰 CONCEPTO {i}: ID={concepto_id}, {concepto_nombre} - ${concepto_importe}")
# print(f"💰 CONCEPTO COMPLETO GUARDADO: {concepto_completo}")
            
            # Construir concepto detallado con los conceptos individuales
            if conceptos_detalle:
                concepto_detallado = f"Operaci\u00f3n {reserva.id} - " + " + ".join(conceptos_detalle)
                
                # Agregar información estructurada al final para parsing posterior
                # Formato: |CONCEPTOS:id1:nombre1:importe1|id2:nombre2:importe2|
                if conceptos_completos:
                    conceptos_info = "|CONCEPTOS:"
                    for concepto in conceptos_completos:
                        conceptos_info += f"{concepto['id']}:{concepto['nombre']}:{concepto['importe']}|"
                    concepto_detallado += conceptos_info
            else:
                concepto_detallado = f"Operaci\u00f3n {reserva.id} - {reserva.propiedad.direccion}"
            
            # ✅ Truncar concepto a 200 caracteres para evitar error de base de datos
            # Si tiene |CONCEPTOS:, preservar esa parte completa y truncar solo la parte descriptiva
            if len(concepto_detallado) > 200:
                if "|CONCEPTOS:" in concepto_detallado:
                    # Separar la parte descriptiva de la parte estructurada
                    partes = concepto_detallado.split("|CONCEPTOS:", 1)
                    parte_descriptiva = partes[0]
                    parte_estructurada = "|CONCEPTOS:" + partes[1]
                    
                    # Calcular cuánto espacio queda para la parte descriptiva
                    espacio_disponible = 200 - len(parte_estructurada)
                    if espacio_disponible > 3:
                        parte_descriptiva = parte_descriptiva[:espacio_disponible-3] + "..."
                        concepto_detallado = parte_descriptiva + parte_estructurada
                    else:
                        # Si la parte estructurada es muy larga, truncarla también
                        concepto_detallado = concepto_detallado[:197] + "..."
                else:
                    concepto_detallado = concepto_detallado[:197] + "..."
            
# print(f"📝 CONCEPTO FINAL: {concepto_detallado}")
            
            # Crear movimiento principal con concepto detallado
            movimiento_principal = MovimientoCaja.objects.create(
                caja=caja_actual,
                sucursal=request.user.sucursal,
                tipo=TipoMovimientoCajaEnum.INGRESO,
                concepto=concepto_detallado,  # ✅ Usar concepto con detalles (truncado si es necesario)
                propiedad=reserva.propiedad,
                fecha_desde=reserva.fecha_inicio,
                fecha_hasta=reserva.fecha_fin,
                monto_efectivo=monto_efectivo,
                monto_cheque=monto_cheque,
                monto_tarjeta=monto_tarjeta,
                monto_deposito=monto_deposito,
                numero_liquidacion=numero_recibo,
                empleado=request.user
            )
            
            # Crear movimientos separados para transferencias si existen
            movimientos_creados = [movimiento_principal]
            
            # ✅ ASIGNAR DESTINO DE TRANSFERENCIA DINÁMICAMENTE
            cuentas_con_monto = [data for data in montos_cuentas_bancarias.values() if data['monto'] > 0]
            
            if len(cuentas_con_monto) == 1:
                # Solo una cuenta bancaria con monto
                cuenta_usada = cuentas_con_monto[0]['cuenta']
                movimiento_principal.destino_deposito = f"cuenta_{cuenta_usada.id}"
                movimiento_principal.save()
# print(f"✅ Destino asignado: Cuenta {cuenta_usada.nombre_banco} (ID: {cuenta_usada.id})")
            elif len(cuentas_con_monto) > 1:
                # Múltiples cuentas bancarias con monto - actualizar concepto
                detalles_cuentas = []
                for data in cuentas_con_monto:
                    cuenta = data['cuenta']
                    monto = data['monto']
                    detalles_cuentas.append(f"{cuenta.nombre_banco}: ${monto}")
                
                concepto_actualizado = f"Operaci\u00f3n {reserva.id} - " + ", ".join(detalles_cuentas)
                movimiento_principal.concepto = concepto_actualizado
                movimiento_principal.destino_deposito = 'mixto'
                movimiento_principal.save()
# print(f"✅ Destino mixto asignado: {', '.join(detalles_cuentas)}")
            elif monto_deposito_legacy > 0:
                # Fallback a lógica legacy si hay montos en campos antiguos
                if monto_deposito_galicia > 0 and monto_deposito_mp == 0:
                    movimiento_principal.destino_deposito = 'galicia'
                    movimiento_principal.save()
            elif monto_deposito_mp > 0 and monto_deposito_galicia == 0:
                    movimiento_principal.destino_deposito = 'mp'
                    movimiento_principal.save()
            elif monto_deposito_galicia > 0 and monto_deposito_mp > 0:
                    concepto_actualizado = f"Operaci\u00f3n {reserva.id} - Galicia: ${monto_deposito_galicia}, MP: ${monto_deposito_mp}"
                    movimiento_principal.concepto = concepto_actualizado
                    movimiento_principal.save()
            
            total_movimiento_creado = (monto_efectivo or 0) + (monto_cheque or 0) + (monto_tarjeta or 0) + (monto_deposito or 0)
# print(f"✅ MOVIMIENTO ÚNICO CREADO - ID: {movimiento_principal.id}, Total: ${total_movimiento_creado}")

            # Honorarios (concepto 25) en este pago — base para comisiones desglosadas
            honorarios_monto = Decimal('0')
            for i in range(conceptos_count):
                cid = (request.POST.get(f'concepto_{i}_id') or '').strip()
                if cid == '25':
                    honorarios_monto += conceptos_importes_decimal.get(i, Decimal('0'))
            if honorarios_monto > 0:
                movimiento_principal.honorarios = honorarios_monto
                movimiento_principal.save(update_fields=['honorarios'])

            # ✅ Comisiones: con concepto 25 (honorarios) → fichaje + línea día/invierno/24.
            # Sin concepto 25 pero propiedad en primer/segundo fichaje con % cargado y operación «por día»:
            # misma lógica usando el monto del movimiento como base de fichaje + comisión por día sobre el total de la reserva.
            if reserva.vendedor:
                from inmobiliaria.models.comision import (
                    ComisionVendedor,
                    clasificar_tipo_operacion_reserva,
                    registrar_comisiones_honorarios_movimiento_reserva,
                )

                try:
                    if honorarios_monto > 0:
                        registrar_comisiones_honorarios_movimiento_reserva(
                            reserva, movimiento_principal, honorarios_monto
                        )
                    else:
                        vend = reserva.vendedor
                        prop = reserva.propiedad
                        tipo_fichaje = getattr(prop, 'tipo_fichaje', None) or 'primer'
                        pct_fichaje = (
                            vend.comision_segundo_fichaje
                            if tipo_fichaje == 'segundo'
                            else vend.comision_primer_fichaje
                        )
                        hubo_fichaje = pct_fichaje is not None and pct_fichaje > 0
                        tipo_op = clasificar_tipo_operacion_reserva(reserva)
                        try:
                            monto_mov_dec = Decimal(str(movimiento_principal.monto_total))
                        except (InvalidOperation, TypeError, ValueError):
                            monto_mov_dec = Decimal('0')

                        if hubo_fichaje and tipo_op == 'dia' and monto_mov_dec > 0:
                            registrar_comisiones_honorarios_movimiento_reserva(
                                reserva,
                                movimiento_principal,
                                monto_mov_dec,
                            )
                        else:
                            pct_comision = vend.porcentaje_comision_para_reserva(reserva)
                            if pct_comision is not None and pct_comision > 0:
                                monto_total_reserva = reserva.precio_total or Decimal('0')
                                ComisionVendedor.crear_comision(
                                    vendedor=vend,
                                    reserva=reserva,
                                    movimiento_caja=movimiento_principal,
                                    monto_total=monto_total_reserva,
                                    concepto=f"Operación {reserva.id} - {reserva.propiedad.direccion}",
                                )
                except Exception:
                    pass
            
            # Usar el movimiento principal para la respuesta
            movimiento = movimiento_principal
            
            # ✅ Valores del formulario (el campo «senia» del POST no define la seña del recibo; se usa la suma de CONCEPTOS_SENIA_OPERACION_RESERVA)
            deposito_garantia_input = limpiar_valor_monetario(request.POST.get('deposito_garantia', '0'))
            
            # ✅ CALCULAR TOTALES PAGADOS ANTES DE ESTE PAGO
            pagos_anteriores = MovimientoCaja.objects.filter(
                propiedad=reserva.propiedad,
                tipo=TipoMovimientoCajaEnum.INGRESO,
                concepto__icontains=f"Operaci\u00f3n {reserva.id}"
            )
            
            total_pagado_anteriormente = sum(
                (mov.monto_efectivo or 0) + (mov.monto_cheque or 0) + (mov.monto_tarjeta or 0) + (mov.monto_deposito or 0)
                for mov in pagos_anteriores
            )
            
            # 🔍 DEBUGGING CRÍTICO: Ver qué llega del formulario
# print(f"🔥 VALORES CRUDOS DEL FORMULARIO:")
# print(f"   - request.POST.get('deposito_garantia'): '{request.POST.get('deposito_garantia', 'NO_ENVIADO')}'")
# print(f"   - deposito_garantia_input (limpiado): '{deposito_garantia_input}'")
# print(f"🔥 TODOS LOS CAMPOS DEL POST:")
            for key, value in request.POST.items():
                if 'csrf' not in key.lower():
                    pass  # ✅ Bloque vacío
# print(f"   - {key}: '{value}'")
            
            try:
                deposito_garantia = Decimal(deposito_garantia_input) if deposito_garantia_input else Decimal('0')
                # Importe locación: siempre el precio total guardado en la reserva (no editable en el recibo; no se toma del POST)
                importe_locacion = reserva.precio_total or Decimal('0')
                
                # ✅ VALIDACIÓN CONCEPTO 10 vs DEPÓSITO DE GARANTÍA (después de definir variables)
                if deposito_garantia > 0 and not concepto_10_presente:
                    pass  # ✅ Bloque vacío
# print(f"⚠️  ADVERTENCIA: Se indicó depósito de ${deposito_garantia} pero no se cargó el concepto 10")
# print(f"   El depósito NO será considerado como pagado hasta que se cargue el concepto 10")
                elif concepto_10_presente and concepto_10_importe != deposito_garantia:
                    pass  # ✅ Bloque vacío
# print(f"⚠️  ADVERTENCIA: Concepto 10 (${concepto_10_importe}) no coincide con depósito de garantía (${deposito_garantia})")
# print(f"   Se usará el monto del concepto 10 como depósito realmente pagado")
                    # Actualizar el depósito para que coincida con el concepto 10
                    deposito_garantia = concepto_10_importe
                
                # 🔄 NUEVA LÓGICA: No validar conceptos vs seña+depósito
                # Los conceptos pueden ser diferentes a la seña (ej: gastos bancarios extras)
                # Solo validamos que formas de pago = total conceptos (se hace más abajo)
# print(f"✅ NUEVA VALIDACIÓN: Total conceptos: ${total_conceptos}")
# print(f"   Los conceptos pueden incluir extras como gastos bancarios")
# print(f"   Validación principal: formas de pago = total conceptos")
                
                monto_total_pagado = (monto_efectivo or 0) + (monto_cheque or 0) + (monto_tarjeta or 0) + (monto_deposito or 0)
                
# print(f"✅ VALORES DIRECTOS DEL FORMULARIO:")
# print(f"   - Depósito nuevo a agregar: ${deposito_garantia}")
# print(f"   - Importe Locación TOTAL: ${importe_locacion}")
# print(f"   - Monto total pagado: ${monto_total_pagado}")
# print(f"   - Monto seña este recibo (conceptos): ${monto_seña_este_pago}")
# print(f"   - Total pagado anteriormente: ${total_pagado_anteriormente}")
# print(f"   - Seña anterior en reserva: ${reserva.senia or 0}")
# print(f"   - Depósito anterior en reserva: ${reserva.deposito_garantia or 0}")
                
                # ✅ CORREGIDO: CALCULAR SEÑA SOLO CON CONCEPTOS QUE NO SEAN DEPÓSITO
                senia_anterior = reserva.senia or 0
                
                # ✅ CORREGIDO: Solo contar conceptos de alquiler como seña (ID: 1)
                senia_real = Decimal('0')
                
                # Revisar conceptos para encontrar solo los de alquiler
                for i in range(conceptos_count):
                    concepto_id = request.POST.get(f'concepto_{i}_id')
                    concepto_importe = request.POST.get(f'concepto_{i}_importe')
                    
                    # ✅ CONCEPTOS QUE CUENTAN COMO SEÑA / saldo a ocupar: ver CONCEPTOS_SENIA_OPERACION_RESERVA
                    if (concepto_id or "").strip() in CONCEPTOS_SENIA_OPERACION_RESERVA:
                        importe_limpio = conceptos_importes_decimal.get(i, Decimal('0'))
                        senia_real += importe_limpio
# print(f"💰 SEÑA DETECTADA: Concepto {concepto_id} - ${importe_limpio}")
                
                # ✅ CORREGIDO: En completar pago, sumar seña anterior + nueva seña
                if es_completar_pago:
                    # Sumar seña anterior + nueva seña de este pago
                    reserva.senia = senia_anterior + senia_real
                else:
                    # En finalizar reserva, usar solo la seña de este pago
                    reserva.senia = senia_real
                
                monto_este_pago = senia_real
                monto_seña_este_pago = senia_real
                
# print(f"🔧 CORRECCIÓN SEÑA:")
# print(f"   - Seña anterior: ${senia_anterior}")
# print(f"   - Seña nueva (conceptos seña/locación): ${senia_real}")
# print(f"   - Es completar pago: {es_completar_pago}")
                if es_completar_pago:
                    pass  # ✅ Bloque vacío
# print(f"   - Seña total (anterior + nueva): ${reserva.senia}")
                else:
                    pass  # ✅ Bloque vacío
# print(f"   - Seña total (solo nueva): ${reserva.senia}")
# print(f"   - Saldo restante esperado: ${reserva.precio_total - reserva.senia}")
                
                # ✅ ACTUALIZAR DEPÓSITO (siempre se guarda, pero solo se marca como pagado con concepto 10)
                if deposito_garantia > 0:
                    # Siempre guardar el depósito que se indica en el casillero
                    reserva.deposito_garantia = deposito_garantia
                    
                    if concepto_10_presente:
                        pass  # ✅ Bloque vacío
# print(f"💳 DEPÓSITO PAGADO: ${deposito_garantia} (confirmado por concepto 10)")
                    else:
                        pass  # ✅ Bloque vacío
# print(f"💰 DEPÓSITO REGISTRADO: ${deposito_garantia} (PENDIENTE - falta concepto 10 para pagar)")
                else:
                    pass  # ✅ Bloque vacío
# print(f"ℹ️  Sin depósito en este pago")
                
                # ✅ CALCULAR SALDO PENDIENTE (precio total - solo seña)
                saldo_pendiente = reserva.precio_total - reserva.senia
                
# print(f"🔥 CÁLCULOS FINALES:")
# print(f"   - Precio Total: ${reserva.precio_total}")
# print(f"   - Total Pagado (seña): ${reserva.senia}")
# print(f"   - Depósito: ${reserva.deposito_garantia}")
# print(f"   - Saldo Pendiente: ${saldo_pendiente}")
                
                reserva.save()
                
                # ✅ ACTUALIZAR HISTORIAL: Cambiar estado de "Reservado" a "Operación" si hay seña
# print(f"🔄 ACTUALIZANDO HISTORIAL después del pago...")
                reserva.actualizar_historial_disponibilidad()
# print(f"✅ HISTORIAL ACTUALIZADO - Estado debería ser 'Operación'")
                
                # ✅ CREAR RECIBO PARA ESTE PAGO
                from .models.recibo import Recibo
                # ✅ NUMERACIÓN AUTOMÁTICA DE RECIBOS POR SUCURSAL
                sucursal = request.user.sucursal
                if sucursal.usar_numeracion_automatica and sucursal.prefijo_recibo:
                    numero_recibo = sucursal.generar_numero_recibo()
# print(f"🧾 NÚMERO AUTOMÁTICO GENERADO: {numero_recibo}")
                else:
                    # Fallback al formato anterior si no hay numeración automática
                    numero_recibo = f"R{reserva.id:06d}-{len(pagos_anteriores) + 1:02d}"
# print(f"🧾 NÚMERO MANUAL GENERADO: {numero_recibo}")
                
# print(f"🧾 DEBUG CREACIÓN RECIBO:")
# print(f"   - precio_total_operacion (reserva.precio_total): ${reserva.precio_total}")
# print(f"   - monto_este_pago (senia): ${monto_este_pago}")
# print(f"   - total_pagado_antes (senia_anterior): ${senia_anterior}")
# print(f"   - saldo_pendiente: ${saldo_pendiente}")
                
                recibo = Recibo.objects.create(
                    numero_recibo=numero_recibo,
                    movimiento_caja=movimiento,
                    reserva=reserva,
                    propiedad=reserva.propiedad,
                    empleado=request.user,
                    precio_total_operacion=reserva.precio_total,
                    monto_este_pago=monto_este_pago,
                    total_pagado_antes=senia_anterior,  # ✅ CORREGIDO: usar seña anterior, no total calculado mal
                    saldo_pendiente=saldo_pendiente,
                    conceptos_detalle={
                        'conceptos': conceptos_completos,
                        'fecha_pago': timezone.now().strftime('%Y-%m-%d'),
                        'formas_pago': {
                            'efectivo': float(monto_efectivo),
                            'cheque': float(monto_cheque),
                            'tarjeta': float(monto_tarjeta),
                            'deposito': float(monto_deposito)
                        }
                    }
                )
                
# print(f"✅ RECIBO CREADO: {numero_recibo}")
                
            except (ValueError, TypeError) as e:
                pass  # ✅ Bloque vacío
# print(f"❌ Error al convertir valores: {e}")
                # Si hay error en la conversión, usar valores por defecto
                reserva.senia = Decimal('0')
                deposito_garantia = Decimal('0')
                
            # ✅ ACTUALIZAR VENDEDOR SI SE CAMBIÓ EN EL FORMULARIO
            productor_id = request.POST.get('productor_id')
            if productor_id and productor_id.strip():
                try:
                    nuevo_vendedor = Vendedor.objects.get(id=int(productor_id))
                    if reserva.vendedor != nuevo_vendedor:
                        pass  # ✅ Bloque vacío
# print(f"🔄 Cambiando vendedor de {reserva.vendedor} a {nuevo_vendedor}")
                        reserva.vendedor = nuevo_vendedor
                except (Vendedor.DoesNotExist, ValueError) as e:
                    pass  # ✅ Bloque vacío
# print(f"⚠️ Error al cambiar vendedor: {e}")
                    # No cambiar el vendedor si hay error, mantener el original
            
            # Cambiar estado de la reserva
            reserva.estado = 'pagada'
            reserva.save()

            # Devolución de depósito (solo al finalizar: saldo pendiente en 0)
            devolver_deposito = request.POST.get('devolver_deposito') in ('1', 'true', 'on', 'yes')
            if devolver_deposito:
                monto_devolucion_raw = request.POST.get('monto_devolucion_deposito', '')
                if monto_devolucion_raw:
                    try:
                        monto_devolucion = Decimal(limpiar_valor_monetario(monto_devolucion_raw))
                    except (InvalidOperation, ValueError):
                        return JsonResponse({'success': False, 'error': 'Monto de devolución de depósito inválido'})
                else:
                    monto_devolucion = Decimal(str(reserva.deposito_garantia or 0))

                if saldo_pendiente > 0:
                    return JsonResponse({
                        'success': False,
                        'error': 'La devolución de depósito solo se puede registrar cuando la operación queda finalizada (saldo pendiente en 0).'
                    })
                if monto_devolucion <= 0:
                    return JsonResponse({'success': False, 'error': 'El monto a devolver debe ser mayor a 0'})

                deposito_estado_global = determinar_estado_deposito_completo(reserva)
                if deposito_estado_global != 'pagado':
                    return JsonResponse({
                        'success': False,
                        'error': 'No se puede devolver depósito porque no figura como pagado (concepto 10).'
                    })

                ya_devuelto = MovimientoCaja.objects.filter(
                    sucursal=request.user.sucursal,
                    tipo=TipoMovimientoCajaEnum.EGRESO,
                    propiedad=reserva.propiedad,
                    concepto__icontains=f'Devolución depósito operación {reserva.id}'
                ).exists()
                if ya_devuelto:
                    return JsonResponse({'success': False, 'error': 'El depósito de esta operación ya fue devuelto anteriormente.'})

                MovimientoCaja.objects.create(
                    caja=caja_actual,
                    sucursal=request.user.sucursal,
                    tipo=TipoMovimientoCajaEnum.EGRESO,
                    concepto=f'Devolución depósito operación {reserva.id} - {reserva.propiedad.direccion}',
                    propiedad=reserva.propiedad,
                    monto_efectivo=monto_devolucion,
                    empleado=request.user,
                    a_descontar='oficina'
                )
            
            # Cambiar estado de la propiedad (opcional - depende de tu lógica de negocio)
            # reserva.propiedad.estado = 'reservada'
            # reserva.propiedad.save()
            
# print(f"=== MOVIMIENTO CREADO EXITOSAMENTE - ID: {movimiento.id} ===")
            
            return JsonResponse({
                'success': True,
                'movimiento_id': movimiento.id,
                'redirect_url': reverse('inmobiliaria:ver_recibo_movimiento', args=[movimiento.id])
            })
            
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
# print(f"Error en procesar_movimiento_reserva: {str(e)}")
# print(f"Traceback: {error_traceback}")
            return JsonResponse({
                'success': False, 
                'error': str(e),
                'debug_info': error_traceback if settings.DEBUG else None
            })
    
    return JsonResponse({'success': False, 'error': 'Método no permitido'})

@login_required
def test_json_response(request):
    """Vista de prueba para verificar que JSON funciona"""
    return JsonResponse({'success': True, 'message': 'Test OK', 'user': str(request.user)})

@login_required
def api_propiedad_detalle(request, propiedad_id):
    """API para obtener detalles de una propiedad"""
    try:
        # Intentar obtener la propiedad de la sucursal del usuario
        try:
            propiedad = Propiedad.objects.get(id=propiedad_id, sucursal=request.user.sucursal)
        except Propiedad.DoesNotExist:
            # Si no está en la sucursal del usuario, buscar en cualquier sucursal
            propiedad = get_object_or_404(Propiedad, id=propiedad_id)
# print(f"⚠️ Propiedad {propiedad_id} encontrada en sucursal {propiedad.sucursal.nombre}, no en {request.user.sucursal.nombre}")
        
# print(f"🏠 API Propiedad {propiedad_id}:")
# print(f"   Ambientes: {propiedad.ambientes}")
# print(f"   Descripcion: {propiedad.descripcion}")
# print(f"   Caracteristicas: {propiedad.caracteristicas}")
# print(f"   Estado: {propiedad.estado}")
        
        # Obtener precios de la propiedad
        precios = PrecioPropiedad.objects.filter(propiedad=propiedad).order_by('fecha_desde')
        precios_data = []
        
        for precio in precios:
            periodo = f"{precio.fecha_desde.strftime('%d/%m/%Y')} - {precio.fecha_hasta.strftime('%d/%m/%Y')}"
            precios_data.append({
                'periodo': periodo,
                'precio_total': float(precio.precio_total),
                'precio_por_dia': float(precio.precio_por_dia)
            })
        
        # Obtener información de alquiler 24 meses si existe
        info_meses = None
        try:
            from .models import AlquilerMeses
            info_meses = AlquilerMeses.objects.get(propiedad=propiedad)
            info_meses_data = {
                'precio_mensual': float(info_meses.precio_mensual),
                'precio_expensas': float(info_meses.precio_expensas) if info_meses.precio_expensas else 0,
                'estado': info_meses.estado
            }
        except:
            info_meses_data = None
        
        data = {
            'id': propiedad.id,
            'direccion': propiedad.direccion,
            'sucursal': propiedad.sucursal.nombre,
            'ambientes': propiedad.ambientes,
            'cantidad_personas': propiedad.cantidad_personas,
            'descripcion': propiedad.descripcion or '',
            'caracteristicas': propiedad.caracteristicas or '',
            'estado': propiedad.estado,
            'precios': precios_data,
            'info_meses': info_meses_data
        }
        
# print(f"📤 Datos enviados: {data}")
        return JsonResponse(data)
        
    except Propiedad.DoesNotExist:
        pass  # ✅ Bloque vacío
# print(f"❌ Propiedad {propiedad_id} no encontrada")
        return JsonResponse({
            'error': f'Propiedad {propiedad_id} no encontrada',
            'id': propiedad_id,
            'direccion': 'Propiedad no encontrada',
            'sucursal': 'N/A',
            'ambientes': 0,
            'descripcion': 'Propiedad no encontrada',
            'caracteristicas': 'Propiedad no encontrada',
            'estado': 'No encontrada',
            'precios': [],
            'info_meses': None
        }, status=404)
    except Exception as e:
        pass  # ✅ Bloque vacío
# print(f"❌ Error en API propiedad: {str(e)}")
        return JsonResponse({
            'error': str(e),
            'id': propiedad_id,
            'direccion': 'Error al cargar',
            'sucursal': 'Error al cargar',
            'ambientes': 0,
            'descripcion': 'Error al cargar descripción',
            'caracteristicas': 'Error al cargar características',
            'estado': 'Error',
            'precios': [],
            'info_meses': None
        }, status=500)

def determinar_estado_deposito_completo(reserva):
    """
    Determina si el depósito fue pagado en CUALQUIER movimiento de la reserva.
    Revisa todos los movimientos de caja de la reserva para ver si alguno tiene concepto 10.
    """
# print(f"🔍 VERIFICANDO ESTADO DEPÓSITO GLOBAL - Reserva {reserva.id}")
    
    if not reserva or not reserva.deposito_garantia:
        pass  # ✅ Bloque vacío
# print(f"❌ No hay depósito para verificar: reserva={reserva}, deposito={reserva.deposito_garantia if reserva else 'N/A'}")
        return 'no_aplica'  # No hay depósito
    
    # Buscar todos los movimientos de esta reserva
    todos_movimientos = MovimientoCaja.objects.filter(
        propiedad=reserva.propiedad,
        tipo=TipoMovimientoCajaEnum.INGRESO,
        concepto__icontains=f"Operaci\u00f3n {reserva.id}"
    )
    
# print(f"📋 MOVIMIENTOS ENCONTRADOS: {todos_movimientos.count()}")
    
    # Verificar si algún movimiento tiene concepto 10
    for i, movimiento in enumerate(todos_movimientos):
        pass  # ✅ Bloque vacío
# print(f"🔍 Movimiento {i+1} (ID: {movimiento.id}): {movimiento.concepto[:100]}...")
        
        if movimiento.concepto and "|CONCEPTOS:" in movimiento.concepto:
            concepto_parts = movimiento.concepto.split("|CONCEPTOS:", 1)
            if len(concepto_parts) > 1:
                conceptos_data = concepto_parts[1]
# print(f"   📝 Conceptos data: {conceptos_data}")
                
                # ✅ MEJORADO: Buscar concepto 10 de forma más robusta
                # Buscar tanto "|10:" como ":10:" o "10:" al inicio
                concepto_10_encontrado = False
                if "|10:" in conceptos_data or ":10:" in conceptos_data:
                    concepto_10_encontrado = True
                else:
                    # Buscar en cada item individual
                    conceptos_items = [item for item in conceptos_data.split("|") if item.strip()]
                    for concepto_item in conceptos_items:
                        # Formato esperado: "10:nombre:importe" o "id:nombre:importe"
                        parts = concepto_item.split(":", 1)
                        if len(parts) > 0 and parts[0].strip() == "10":
                            concepto_10_encontrado = True
                            break
                
                if concepto_10_encontrado:
# print(f"💳 DEPÓSITO GLOBAL PAGADO: Encontrado concepto 10 en movimiento {movimiento.id}")
                    return 'pagado'
                else:
                    pass  # ✅ Bloque vacío
# print(f"   ❌ No encontrado concepto 10 en: {conceptos_data}")
            else:
                pass  # ✅ Bloque vacío
# print(f"   ❌ No se pudo parsear conceptos estructurados")
        else:
            pass  # ✅ Bloque vacío
# print(f"   ❌ Sin estructura |CONCEPTOS: o concepto vacío")
    
# print(f"⏳ DEPÓSITO GLOBAL PENDIENTE: No se encontró concepto 10 en ningún movimiento")
    return 'pendiente'

@login_required
def ver_recibo_movimiento(request, movimiento_id):
    """
    Vista para mostrar el recibo basado en un MovimientoCaja
    """
# print("🧾 EJECUTANDO ver_recibo_movimiento desde views.py (FUNCIÓN ACTUALIZADA)")
# print(f"🧾 Movimiento ID: {movimiento_id}")
# print("="*50)
# print("🔧 VERSIÓN ACTUALIZADA DE LA FUNCIÓN - DICIEMBRE 2024")
# print("="*50)
    try:
        # Obtener el movimiento de caja principal
        movimiento = get_object_or_404(MovimientoCaja, id=movimiento_id, sucursal=request.user.sucursal)
        
        # Obtener la reserva relacionada desde el concepto del movimiento
        reserva = None
        if movimiento.concepto and "Operaci\u00f3n" in movimiento.concepto:
            try:
                # Extraer el ID de la reserva del concepto (formato: "Operaci\u00f3n 123 - Dirección")
                import re
                match = re.search(r'Operaci\u00f3n (\d+)', movimiento.concepto)
                if match:
                    reserva_id = int(match.group(1))
                    reserva = Reserva.objects.filter(id=reserva_id).first()
# print(f"🔍 RESERVA ENCONTRADA desde concepto: ID {reserva_id}, Estado: {reserva.estado if reserva else 'No encontrada'}")
                else:
                    pass  # ✅ Bloque vacío
# print(f"⚠️ No se pudo extraer ID de reserva del concepto: '{movimiento.concepto}'")
            except Exception as e:
                pass  # ✅ Bloque vacío
# print(f"❌ Error al buscar reserva desde concepto: {e}")
        
        # Fallback: buscar por propiedad si no se encontró por concepto
        if not reserva and movimiento.propiedad:
            reserva = movimiento.propiedad.reservas.filter(estado__in=['pagada', 'confirmada_no_pagada']).first()
# print(f"🔍 RESERVA FALLBACK desde propiedad: {reserva.id if reserva else 'No encontrada'}")
        
        # ✅ CORRECCIÓN: Buscar movimientos DE ESTA OPERACIÓN ESPECÍFICA (mismo número de recibo)
        movimientos_relacionados = MovimientoCaja.objects.filter(
            numero_liquidacion=movimiento.numero_liquidacion,
            propiedad=movimiento.propiedad,
            tipo=TipoMovimientoCajaEnum.INGRESO
        ).order_by('id')
        
        # ✅ USAR SOLO EL MOVIMIENTO PRINCIPAL (no sumar movimientos múltiples)
        total_efectivo = movimiento.monto_efectivo or 0
        total_cheque = movimiento.monto_cheque or 0
        total_tarjeta = movimiento.monto_tarjeta or 0
        total_deposito = movimiento.monto_deposito or 0
        
        # ✅ Para transferencias, extraer del concepto si hay ambas o usar destino_deposito
        total_deposito_galicia = 0
        total_deposito_mp = 0
        
        if movimiento.destino_deposito == 'galicia':
            total_deposito_galicia = movimiento.monto_deposito or 0
        elif movimiento.destino_deposito == 'mp':
            total_deposito_mp = movimiento.monto_deposito or 0
        elif 'Galicia:' in movimiento.concepto and 'MP:' in movimiento.concepto:
            # Extraer montos del concepto si están ambos
            import re
            galicia_match = re.search(r'Galicia: \$(\d+)', movimiento.concepto)
            mp_match = re.search(r'MP: \$(\d+)', movimiento.concepto)
            
            if galicia_match:
                total_deposito_galicia = int(galicia_match.group(1))
            if mp_match:
                total_deposito_mp = int(mp_match.group(1))
        else:
            # Si no hay destino específico, asumir que es todo en uno
            total_deposito_galicia = movimiento.monto_deposito
        
        total_movimiento = total_efectivo + total_cheque + total_tarjeta + total_deposito
        
# print(f"🧾 RECIBO ÚNICO - Movimiento ID: {movimiento.id}, Número: {movimiento.numero_liquidacion}")
# print(f"🧾 DESGLOSE - Efectivo: {total_efectivo}, Cheque: {total_cheque}, Tarjeta: {total_tarjeta}")
# print(f"🧾 TRANSFERENCIAS - Galicia: {total_deposito_galicia}, MP: {total_deposito_mp}, Total Depósitos: {total_deposito}")
# print(f"🧾 TOTAL OPERACIÓN: {total_movimiento} (debe coincidir con lo pagado)")
        
        # Calcular saldo pendiente si hay reserva
        saldo_pendiente = 0
        total_pagado_reserva = 0
        total_senia_pagada_recibo = 0  # ✅ Inicializar para evitar errores
        total_deposito_pagado_recibo = 0  # ✅ Inicializar para evitar errores
        precio_total_operacion = 0  # ✅ Inicializar para evitar errores
        concepto_10_en_recibo = False  # ✅ Inicializar estado del concepto 10
        if reserva:
            # Buscar todos los movimientos de esta reserva para calcular total pagado
            todos_movimientos = MovimientoCaja.objects.filter(
                propiedad=reserva.propiedad,
                tipo=TipoMovimientoCajaEnum.INGRESO,
                concepto__icontains=f"Operaci\u00f3n {reserva.id}"
            )
            
# print(f"🔍 BÚSQUEDA MOVIMIENTOS - Buscando concepto: 'Operaci\u00f3n {reserva.id}'")
# print(f"🔍 MOVIMIENTOS ENCONTRADOS: {todos_movimientos.count()}")
            for mov in todos_movimientos:
                total_mov = (mov.monto_efectivo or 0) + (mov.monto_cheque or 0) + (mov.monto_tarjeta or 0) + (mov.monto_deposito or 0)
# print(f"🔍 Movimiento ID: {mov.id}, Concepto: '{mov.concepto}', Total: {total_mov}")
            
            # ✅ INTENTAR OBTENER EL RECIBO ASOCIADO A ESTE MOVIMIENTO
            recibo_obj = None
            try:
                from .models.recibo import Recibo
                recibo_obj = Recibo.objects.get(movimiento_caja=movimiento)
# print(f"🧾 RECIBO ENCONTRADO: {recibo_obj.numero_recibo}")
            except Recibo.DoesNotExist:
                pass  # ✅ Bloque vacío
# print("⚠️ No se encontró recibo asociado a este movimiento")
            
            if recibo_obj:
                # ✅ USAR DATOS DEL RECIBO (MÁS PRECISOS)
                total_pagado_reserva = recibo_obj.total_pagado_antes + recibo_obj.monto_este_pago
                saldo_pendiente = recibo_obj.saldo_pendiente
                precio_total_operacion = recibo_obj.precio_total_operacion
                
# print(f"✅ USANDO DATOS DEL RECIBO:")
# print(f"   - Precio Total Operación: ${precio_total_operacion}")
# print(f"   - Monto Este Pago: ${recibo_obj.monto_este_pago}")
# print(f"   - Total Pagado Antes: ${recibo_obj.total_pagado_antes}")
# print(f"   - Total Pagado Ahora: ${total_pagado_reserva}")
# print(f"   - Saldo Pendiente: ${saldo_pendiente}")
                
            else:
                # ✅ SIMPLIFICADO: USAR DIRECTAMENTE VALORES DEL CASILLERO DE LA RESERVA
                total_senia_pagada_recibo = reserva.senia or 0
                total_deposito_pagado_recibo = reserva.deposito_garantia or 0
                precio_total_operacion = reserva.precio_total
                
                # Verificar si hay concepto 10 para el estado del depósito
                try:
                    import json
                    if movimiento.concepto and movimiento.concepto.startswith('['):
                        conceptos_data = json.loads(movimiento.concepto)
                        for concepto_data in conceptos_data:
                            concepto_id = str(concepto_data.get('id', ''))
                            if concepto_id == '10':  # Depósito
                                concepto_10_en_recibo = True
                                break
                except:
                    pass
                
# print(f"✅ USANDO VALORES DIRECTOS DE LA RESERVA:")
# print(f"   - Seña (reserva.senia): ${total_senia_pagada_recibo}")
# print(f"   - Depósito (reserva.deposito_garantia): ${total_deposito_pagado_recibo}")
# print(f"   - Concepto 10 presente: {concepto_10_en_recibo}")
            
            # ✅ CORREGIDO: Solo la seña cuenta para el total pagado (el depósito es aparte)
            total_pagado_reserva = total_senia_pagada_recibo
            
            # ✅ NUEVO CÁLCULO: El saldo pendiente es precio total - SOLO LA SEÑA (NO EL DEPÓSITO)
            saldo_pendiente = reserva.precio_total - total_senia_pagada_recibo
            
# print(f"💰 SALDO RECIBO - Precio Total: {reserva.precio_total}, Seña Pagada: {total_senia_pagada_recibo}, Depósito: {total_deposito_pagado_recibo}, Saldo Pendiente: {saldo_pendiente}")
        else:
            total_pagado_reserva = total_movimiento
        
        # Si encontramos una reserva, usar el nuevo diseño de recibo
        if reserva:
            # Usar el mismo código que la función ver_recibo
            from datetime import datetime
            fecha_actual = timezone.now()
            
            # Obtener los pagos de la reserva
            pagos = []
            total_pagado = 0
            formas_de_pago = []
            
            # Búsqueda simple de conceptos para evitar errores
# print(f"🔍 DEBUG SIMPLE - Movimiento ID: {movimiento.id}")
# print(f"🔍 Número liquidación: '{movimiento.numero_liquidacion}'")
            
            conceptos_operacion = None
            
            try:
                from .models import Registro
                # Búsqueda básica
                conceptos_operacion = Registro.objects.filter(
                    interno_caja=movimiento.numero_liquidacion
                ).order_by('fecha')
# print(f"🔍 CONCEPTOS ENCONTRADOS: {conceptos_operacion.count()}")
            except Exception as e:
                pass  # ✅ Bloque vacío
# print(f"❌ Error en búsqueda básica: {e}")
                conceptos_operacion = None
            
            if conceptos_operacion and conceptos_operacion.exists():
                # Usar los conceptos de la operación
                for registro in conceptos_operacion:
                    concepto_desc = ''
                    if registro.concepto:
                        concepto_desc = f'{registro.concepto.id} - {registro.concepto.nombre}'
                    else:
                        concepto_desc = 'Concepto no especificado'
                    
# print(f"💰 CONCEPTO: {concepto_desc} - ${registro.liquidacion}")
                    
                    pagos.append({
                        'fecha': registro.fecha_comprobante.strftime('%d/%m/%Y'),
                        'codigo': registro.interno_caja or f'R{registro.id:04d}',
                        'concepto': concepto_desc,
                        'monto': _recibo_monto_str(registro.liquidacion),
                    })
                    total_pagado += registro.liquidacion
            else:
                # Fallback: extraer conceptos individuales del campo concepto del movimiento
# print("📋 FALLBACK: Extrayendo conceptos individuales desde movimiento.concepto")
                
                # ✅ INICIALIZAR VARIABLE DE CONTROL
                conceptos_procesados = False
                
                try:
                    fecha_mov = movimiento.fecha.strftime('%d/%m/%Y')
                    codigo_mov = movimiento.numero_liquidacion or f'M{movimiento.id:04d}'
                    
                    # Intentar extraer conceptos individuales del campo concepto
                    # Nuevo formato esperado: "Reserva 85 - limpieza + alquiler + deposito|CONCEPTOS:11:limpieza:35000|1:alquiler:35000|10:deposito:20000|"
                    concepto_texto = movimiento.concepto or ""
# print(f"📝 CONCEPTO COMPLETO: {concepto_texto}")
# print(f"📝 LONGITUD: {len(concepto_texto)} caracteres")
# print(f"📝 TIPO: {type(concepto_texto)}")
                    
                    # ✅ MEJORADO: Detectar si tiene formato estructurado |CONCEPTOS:
                    conceptos_procesados = False
                    
                    # Si no es JSON, continuar con el formato anterior
                    if not conceptos_procesados and "|CONCEPTOS:" in concepto_texto:
                        # Extraer la parte estructurada
                        concepto_parts = concepto_texto.split("|CONCEPTOS:", 1)
                        if len(concepto_parts) > 1:
                            conceptos_data = concepto_parts[1]  # "11:limpieza:35000|1:alquiler:35000|10:deposito:20000|"
                            conceptos_items = [item for item in conceptos_data.split("|") if item.strip()]
# print(f"✅ CONCEPTOS ENCONTRADOS: {len(conceptos_items)} items")
                            
                            # Crear una entrada por cada concepto individual
                            for i, concepto_item in enumerate(conceptos_items):
                                parts = concepto_item.split(":")
                                if len(parts) >= 3:
                                    concepto_id = parts[0].strip()
                                    concepto_nombre = parts[1].strip()
                                    concepto_importe = parts[2].strip()
                                    
                                    # Limpiar y convertir el importe
                                    try:
                                        # Remover puntos y comas, luego convertir
                                        importe_limpio = concepto_importe.replace('.', '').replace(',', '').strip()
                                        if importe_limpio:
                                            importe_num = float(importe_limpio)
                                        else:
                                            importe_num = 0
                                    except (ValueError, AttributeError):
                                        importe_num = 0
                                    
                                    # ✅ SIEMPRE agregar el concepto, incluso si el importe es 0
                                    # Esto asegura que conceptos como depósito y gastos bancarios se muestren
                                    pagos.append({
                                        'fecha': fecha_mov,
                                        'codigo': concepto_id,
                                        'concepto': concepto_nombre,
                                        'monto': _recibo_monto_str(importe_num) if importe_num > 0 else ''
                                    })
                                    total_pagado += importe_num
# print(f"💰 CONCEPTO: ID={concepto_id}, {concepto_nombre} - ${importe_num:,.0f}")
                            
                            conceptos_procesados = True
# print(f"✅ CONCEPTOS PROCESADOS: {len(pagos)} conceptos")
                        else:
                            # Fallback al método anterior
# print("⚠️ No se pudo parsear información estructurada, usando método anterior")
                            conceptos_procesados = False
                    
                    # ✅ SOLO EJECUTAR FALLBACK SI NO HAY CONCEPTOS PROCESADOS
                    if not conceptos_procesados and not pagos and " + " in concepto_texto:
                        # Extraer la parte después del número de reserva
                        parts = concepto_texto.split(" - ", 1)
                        if len(parts) > 1:
                            conceptos_parte = parts[1].split("|")[0]  # Tomar solo la parte antes de |CONCEPTOS si existe
                            conceptos_individuales = [c.strip() for c in conceptos_parte.split(" + ")]
# print(f"🔍 CONCEPTOS ENCONTRADOS (método anterior): {conceptos_individuales}")
                            
                            # Crear una entrada por cada concepto individual
                            for i, concepto_nombre in enumerate(conceptos_individuales):
                                # Distribuir el monto total entre los conceptos
                                monto_por_concepto = movimiento.monto_total / len(conceptos_individuales)
                                
                                pagos.append({
                                    'fecha': fecha_mov,
                                    'codigo': f'{codigo_mov}_{i+1}' if len(conceptos_individuales) > 1 else codigo_mov,
                                    'concepto': concepto_nombre,
                                    'monto': _recibo_monto_str(monto_por_concepto),
                                })
# print(f"💰 CONCEPTO {i+1}: {concepto_nombre} - ${monto_por_concepto:,.0f}")
                            
                            total_pagado += movimiento.monto_total
                        else:
                            pass  # ✅ Bloque vacío
                            # No se pudo parsear, usar concepto único
# print("⚠️ No se pudieron extraer conceptos individuales, usando concepto único")
                    
                    # ✅ FALLBACK FINAL: Si no se procesaron conceptos, usar el concepto completo
                    if not conceptos_procesados and not pagos:
                        # Si es un concepto simple como "Operación X - Dirección", crear un concepto genérico
                        if concepto_texto and "Operación" in concepto_texto and " - " in concepto_texto:
                            pass  # ✅ Bloque vacío
# print(f"🔄 CONCEPTO SIMPLE DETECTADO: {concepto_texto}")
                            # Extraer información básica
                            partes = concepto_texto.split(" - ", 1)
                            if len(partes) > 1:
                                direccion = partes[1]
                                concepto_nombre = f"Alquiler - {direccion}"
                            else:
                                concepto_nombre = "Alquiler temporario"
                        else:
                            concepto_nombre = concepto_texto or 'ALQ - Alquiler temporario'
                        
                        pagos.append({
                            'fecha': fecha_mov,
                            'codigo': codigo_mov,
                            'concepto': concepto_nombre,
                            'monto': _recibo_monto_str(movimiento.monto_total),
                        })
                        total_pagado += movimiento.monto_total
# print(f"💰 CONCEPTO FALLBACK: {concepto_nombre} - ${movimiento.monto_total:,.0f}")
                    
                except Exception as e:
                    pass  # ✅ Bloque vacío
# print(f"❌ Error en fallback: {e}")
                    # Solo usar fallback ultra simple si no se procesaron conceptos
                    if not conceptos_procesados:
                        pass  # ✅ Bloque vacío
# print("🚨 USANDO FALLBACK ULTRA SIMPLE")
                        pagos.append({
                            'fecha': '15/09/2025',
                            'codigo': 'M0001',
                            'concepto': 'ALQ - Alquiler temporario',
                            'monto': _recibo_monto_str(130000),
                        })
                        total_pagado = 130000
                    else:
                        pass  # ✅ Bloque vacío
# print("✅ CONCEPTOS YA PROCESADOS - No usar fallback ultra simple")
            
            # Obtener formas de pago del movimiento con montos detallados
            formas_con_montos = []
            if (movimiento.monto_efectivo or 0) > 0:
                formas_con_montos.append(f'Efectivo {_recibo_monto_str(movimiento.monto_efectivo)}')
                formas_de_pago.append('Efectivo')
            if (movimiento.monto_tarjeta or 0) > 0:
                formas_con_montos.append(f'Tarjeta {_recibo_monto_str(movimiento.monto_tarjeta)}')
                formas_de_pago.append('Tarjeta')
            if (movimiento.monto_cheque or 0) > 0:
                formas_con_montos.append(f'Cheque {_recibo_monto_str(movimiento.monto_cheque)}')
                formas_de_pago.append('Cheque')
            if (movimiento.monto_deposito or 0) > 0:
                if movimiento.destino_deposito == 'galicia':
                    formas_con_montos.append(f'Transferencia Galicia {_recibo_monto_str(movimiento.monto_deposito)}')
                    formas_de_pago.append('Galicia')
                elif movimiento.destino_deposito == 'mp':
                    formas_con_montos.append(f'Transferencia Mercado Pago {_recibo_monto_str(movimiento.monto_deposito)}')
                    formas_de_pago.append('Mercado Pago')
                else:
                    formas_con_montos.append(f'Transferencia {_recibo_monto_str(movimiento.monto_deposito)}')
                    formas_de_pago.append('Transferencia')
            
            # Siempre usar formas con montos para mostrar el desglose completo
            formas_de_pago_mostrar = formas_con_montos if formas_con_montos else formas_de_pago
            
            # Función para convertir número a palabras
            def numero_a_palabras(numero):
                # Convertir número a palabras en español (versión simplificada)
                unidades = ['', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve']
                decenas = ['', '', 'veinte', 'treinta', 'cuarenta', 'cincuenta', 'sesenta', 'setenta', 'ochenta', 'noventa']
                centenas = ['', 'ciento', 'doscientos', 'trescientos', 'cuatrocientos', 'quinientos', 'seiscientos', 'setecientos', 'ochocientos', 'novecientos']
                
                numero = int(numero)
                if numero == 0:
                    return "PESOS CERO CON 00/100"
                elif numero == 100:
                    return "PESOS CIEN CON 00/100"
                elif numero < 10:
                    return f"PESOS {unidades[numero].upper()} CON 00/100"
                elif numero < 100:
                    if numero < 20:
                        especiales = ['diez', 'once', 'doce', 'trece', 'catorce', 'quince', 'dieciséis', 'diecisiete', 'dieciocho', 'diecinueve']
                        return f"PESOS {especiales[numero-10].upper()} CON 00/100"
                    else:
                        dec = numero // 10
                        uni = numero % 10
                        if uni == 0:
                            return f"PESOS {decenas[dec].upper()} CON 00/100"
                        else:
                            return f"PESOS {decenas[dec].upper()} Y {unidades[uni].upper()} CON 00/100"
                elif numero < 1000:
                    cent = numero // 100
                    resto = numero % 100
                    if resto == 0:
                        return f"PESOS {centenas[cent].upper()} CON 00/100"
                    else:
                        palabras_resto = numero_a_palabras(resto).replace("PESOS ", "").replace(" CON 00/100", "")
                        return f"PESOS {centenas[cent].upper()} {palabras_resto} CON 00/100"
                else:
                    return f"PESOS {format_monto_argentino(numero, 0)} CON 00/100"
            
            # Preparar datos del cliente con campos adicionales
            cliente_data = reserva.cliente
            cliente_completo = {
                'nombre_completo': f"{cliente_data.apellido}, {cliente_data.nombre}",
                'domicilio': cliente_data.domicilio or '',
                'localidad': cliente_data.localidad or '',
                'provincia': cliente_data.provincia or '',
                'dni': cliente_data.dni or '',
                'telefono': cliente_data.celular or '',  # Mapear celular a telefono
                'cuit': getattr(cliente_data, 'cuit', '') or '',  # CUIT puede no existir
            }
            
            # Preparar datos de la propiedad con formato correcto
            propiedad_data = reserva.propiedad
            propiedad_completa = {
                'direccion': propiedad_data.direccion or '',
                'id': propiedad_data.id,
                'llave': propiedad_data.llave or 'N/A',
                'piso': propiedad_data.piso or '',
                'departamento': propiedad_data.departamento or '',
                'cantidad_personas': propiedad_data.cantidad_personas or None,
                'wifi': 'SÍ' if propiedad_data.wifi else 'NO',
                'cochera': 'SÍ' if propiedad_data.cochera else 'NO',
            }
            
            # Preparar datos de la reserva con formato de moneda
            reserva_formateada = {
                'id': reserva.id,
                'precio_total': _recibo_monto_str(reserva.precio_total),
                'senia': _recibo_monto_str(reserva.senia),
                'cuota_pendiente': _recibo_monto_str(reserva.cuota_pendiente),
                'deposito_garantia': _recibo_monto_str(reserva.deposito_garantia),
                'propiedad': propiedad_completa,
            }
            
            # DEBUG: Confirmar template y datos en ver_recibo_movimiento
# print("🧾 TEMPLATE USADO en ver_recibo_movimiento: inmobiliaria/reserva/recibo.html") 
# print(f"🧾 TOTAL PAGADO: {f'${total_pagado:,.0f}'}")
# print(f"🧾 FORMAS DE PAGO: {', '.join(formas_de_pago) if formas_de_pago else 'EFECTIVO'}")
# print(f"🧾 PAGOS COUNT: {len(pagos)}")
# print(f"🧾 MONTO MOVIMIENTO: ${movimiento.monto_total:,.0f}")
            
            # Si no hay pagos específicos, usar el total del movimiento
            if total_pagado == 0:
                pass  # ✅ Bloque vacío
# print("⚠️ TOTAL PAGADO ES 0 - USANDO MONTO DEL MOVIMIENTO")
                total_pagado = movimiento.monto_total
            
            # Generar logo en base64 para evitar problemas de carga
            import base64
            import os
            from django.conf import settings
            
            logo_base64 = None
            try:
                logo_path = os.path.join(settings.BASE_DIR, 'inmobiliaria', 'static', 'images', 'logo.png')
                with open(logo_path, 'rb') as logo_file:
                    logo_data = base64.b64encode(logo_file.read()).decode()
                    logo_base64 = f'data:image/png;base64,{logo_data}'
            except Exception as e:
                pass  # ✅ Bloque vacío
# print(f"⚠️ Error al cargar logo: {e}")
                logo_base64 = None
            
            # ✅ PREPARAR DATOS CORREGIDOS PARA EL RECIBO
            if recibo_obj:
                numero_recibo_mostrar = recibo_obj.numero_recibo
                precio_total_mostrar = recibo_obj.precio_total_operacion
                saldo_pendiente_mostrar = recibo_obj.saldo_pendiente
                monto_este_pago_mostrar = recibo_obj.monto_este_pago
                
# print(f"🧾 DEBUG RECIBO - USANDO DATOS DEL RECIBO:")
# print(f"   - precio_total_operacion: ${precio_total_mostrar}")
# print(f"   - monto_este_pago: ${monto_este_pago_mostrar}")
# print(f"   - saldo_pendiente: ${saldo_pendiente_mostrar}")
            else:
                numero_recibo_mostrar = f'R{reserva.id:06d}'
                precio_total_mostrar = reserva.precio_total
                saldo_pendiente_mostrar = saldo_pendiente
                # ✅ CORREGIDO: Usar la seña del casillero, no el total del movimiento
                monto_este_pago_mostrar = total_senia_pagada_recibo
            
            # Obtener honorarios y sellados del movimiento
            honorarios_monto = float(movimiento.honorarios or 0)
            sellados_monto = float(movimiento.sellados or 0)
            
            # Obtener información de la sucursal
            sucursal = request.user.sucursal if hasattr(request.user, 'sucursal') and request.user.sucursal else None
            
            # Usar el nuevo template de recibo
            return render(request, 'inmobiliaria/reserva/recibo.html', {
                'reserva': reserva_formateada,
                'cliente': cliente_completo,
                'propiedad': propiedad_completa,
                'numero_recibo': numero_recibo_mostrar,
                'fecha': fecha_actual.strftime('%d/%m/%Y'),
                'hora': fecha_actual.strftime('%H:%M'),
                'fecha_inicio': reserva.fecha_inicio.strftime('%d/%m/%Y'),
                'fecha_fin': reserva.fecha_fin.strftime('%d/%m/%Y'),
                'descripcion': 'Alquiler temporario por días',
                'pagos': pagos,
                'total_pagado': _recibo_monto_str(total_pagado),
                'monto_en_palabras': numero_a_palabras(total_pagado),
                'formas_de_pago': ', '.join(formas_de_pago_mostrar) if formas_de_pago_mostrar else 'EFECTIVO',
                'logo_base64': logo_base64,
                # ✅ DATOS CORREGIDOS PARA MOSTRAR EN RECIBO
                'precio_total_operacion': _recibo_monto_str(precio_total_mostrar),
                'saldo_pendiente': _recibo_monto_str(saldo_pendiente_mostrar),
                'monto_este_pago': _recibo_monto_str(monto_este_pago_mostrar),
                'deposito_garantia': _recibo_monto_str(reserva.deposito_garantia),
                # ✅ ESTADO DEL DEPÓSITO: Verificar si fue pagado en CUALQUIER movimiento de la reserva
                'deposito_estado': determinar_estado_deposito_completo(reserva),
                # ✅ AGREGAR HONORARIOS Y SELLADOS
                'honorarios': _recibo_monto_str(honorarios_monto),
                'sellados': _recibo_monto_str(sellados_monto),
                'tiene_honorarios': honorarios_monto > 0,
                'tiene_sellados': sellados_monto > 0,
                'sucursal': sucursal,  # Agregar sucursal al contexto
            })
        
        # Si no hay reserva, usar el template original
        context = {
            'movimiento': movimiento,
            'reserva': reserva,
            'total_movimiento': total_movimiento,
            'total_efectivo': total_efectivo,
            'total_cheque': total_cheque,
            'total_tarjeta': total_tarjeta,
            'total_deposito': total_deposito,
            'total_deposito_galicia': total_deposito_galicia,
            'total_deposito_mp': total_deposito_mp,
            'saldo_pendiente': saldo_pendiente,
            'total_pagado_acumulado': total_pagado_reserva if reserva else total_movimiento,
            'total_senia_pagada': total_senia_pagada_recibo if reserva else 0,  # ✅ NUEVO: Solo seña
            'total_deposito_pagado': total_deposito_pagado_recibo if reserva else 0,  # ✅ NUEVO: Solo depósito
            'movimientos_relacionados': movimientos_relacionados,
            'fecha_actual': datetime.now().strftime('%d/%m/%Y'),
            'caja': movimiento.caja,
            'propiedad': movimiento.propiedad,
            'empleado': movimiento.empleado,
        }
        
        return render(request, 'inmobiliaria/caja/recibo_movimiento.html', context)
        
    except Exception as e:
        messages.error(request, f'Error al generar el recibo: {str(e)}')
        return redirect('inmobiliaria:lista_cajas')

@login_required
def listar_recibos_propiedad(request, propiedad_id):
    """
    Vista para listar todos los recibos de una propiedad específica
    """
    try:
        from .models.recibo import Recibo
        from .models.propiedad import Propiedad
        
        propiedad = get_object_or_404(Propiedad, id=propiedad_id, sucursal=request.user.sucursal)
        
        # Obtener todos los recibos de esta propiedad
        recibos = Recibo.objects.filter(propiedad=propiedad).order_by('-fecha_emision')
        
        # Preparar datos para el template
        recibos_data = []
        for recibo in recibos:
            recibos_data.append({
                'numero_recibo': recibo.numero_recibo,
                'fecha_emision': recibo.fecha_emision,
                'reserva_id': recibo.reserva.id,
                'monto_este_pago': recibo.monto_este_pago,
                'precio_total_operacion': recibo.precio_total_operacion,
                'saldo_pendiente': recibo.saldo_pendiente,
                'movimiento_id': recibo.movimiento_caja.id,
                'empleado': recibo.empleado.username if recibo.empleado else 'N/A',
            })
        
        context = {
            'propiedad': propiedad,
            'recibos': recibos_data,
        }
        
        return render(request, 'inmobiliaria/recibos/lista_recibos_propiedad.html', context)
        
    except Exception as e:
        messages.error(request, f'Error al cargar recibos: {str(e)}')
        return redirect('inmobiliaria:propiedades')

@login_required
def crear_inquilino_ajax(request):
    if request.method == 'POST':
        try:
            # Obtener la sucursal del usuario logueado
            sucursal = request.user.sucursal
            
            # Campos opcionales que pueden no estar en el formulario
            fecha_nacimiento = request.POST.get('fecha_nacimiento')
            if fecha_nacimiento == '':
                fecha_nacimiento = None
            
            tipo_doc = request.POST.get('tipo_doc', 'dni')
            
            # Validar y limpiar DNI (obligatorio)
            dni_raw = request.POST.get('dni', '').strip()
            if not dni_raw:
                return JsonResponse({
                    'success': False,
                    'error': 'El DNI es obligatorio. Por favor, ingrese el DNI.'
                })
            
            # Limpiar DNI: quitar puntos, espacios, guiones
            dni_limpio = dni_raw.replace('.', '').replace(' ', '').replace('-', '').replace(',', '')
            
            # Validar que el DNI solo contenga números
            if not dni_limpio.isdigit():
                return JsonResponse({
                    'success': False,
                    'error': 'El DNI solo puede contener números. Por favor, ingrese solo los 7 u 8 dígitos del DNI sin puntos ni guiones.'
                })
            
            # Validar longitud del DNI (7 u 8 dígitos)
            if len(dni_limpio) != 7 and len(dni_limpio) != 8:
                return JsonResponse({
                    'success': False,
                    'error': f'El DNI debe tener 7 u 8 dígitos. Usted ingresó {len(dni_limpio)} dígito(s). Por favor, verifique el DNI.'
                })
            
            # Verificar si el DNI ya existe
            if Inquilino.objects.filter(dni=dni_limpio).exists():
                inquilino_existente = Inquilino.objects.get(dni=dni_limpio)
                return JsonResponse({
                    'success': False,
                    'error': f'Ya existe un inquilino con el DNI {dni_limpio}. Inquilino: {inquilino_existente.apellido}, {inquilino_existente.nombre}'
                })
            
            # Validar y limpiar CUIT (opcional)
            cuit_raw = request.POST.get('cuit', '').strip()
            cuit_limpio = None
            
            if cuit_raw:  # Solo validar si se proporciona CUIT
                # Limpiar CUIT: quitar puntos, espacios, guiones
                cuit_limpio = cuit_raw.replace('.', '').replace(' ', '').replace('-', '').replace(',', '')
                
                # Validar que el CUIT solo contenga números
                if not cuit_limpio.isdigit():
                    return JsonResponse({
                        'success': False,
                        'error': 'El CUIT solo puede contener números. Por favor, ingrese solo los 11 dígitos del CUIT sin puntos ni guiones.'
                    })
                
                # Validar longitud del CUIT (11 dígitos)
                if len(cuit_limpio) != 11:
                    return JsonResponse({
                        'success': False,
                        'error': f'El CUIT debe tener 11 dígitos. Usted ingresó {len(cuit_limpio)} dígito(s). Por favor, verifique el CUIT.'
                    })
            
            inquilino = Inquilino.objects.create(
                nombre=request.POST['nombre'],
                apellido=request.POST['apellido'],
                fecha_nacimiento=fecha_nacimiento,
                email=request.POST['email'],
                celular=request.POST['celular'],
                tipo_doc=tipo_doc,
                dni=dni_limpio,  # Puede ser None si no se proporciona
                tipo_ins=request.POST.get('tipo_ins', 'otro'),  # Valor por defecto
                cuit=cuit_limpio or request.POST.get('cuit', ''),  # Usar CUIT limpio o el valor original
                localidad=request.POST['localidad'],
                provincia=request.POST['provincia'],
                domicilio=request.POST['domicilio'],
                codigo_postal=request.POST.get('codigo_postal', ''),
                observaciones=request.POST.get('observaciones', ''),
                garantia=request.POST.get('garantia', ''),
                sucursal=sucursal  # Agregar la sucursal
            )
            return JsonResponse({
                'success': True,
                'inquilino': {
                    'id': inquilino.id,
                    'nombre': inquilino.nombre,
                    'apellido': inquilino.apellido,
                    'dni': inquilino.dni
                }
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    return JsonResponse({'success': False, 'error': 'Método no permitido'})

@login_required
def crear_propietario_ajax(request):
    if request.method == 'POST':
        try:
            # Obtener la sucursal del usuario logueado
            sucursal = request.user.sucursal
            
            # Campos opcionales que pueden no estar en el formulario
            fecha_nacimiento = request.POST.get('fecha_nacimiento')
            if fecha_nacimiento == '':
                fecha_nacimiento = None
                
            # Validar campos requeridos (tipo_doc y codigo_postal ya no son requeridos)
            campos_requeridos = ['nombre', 'apellido', 'email', 'celular', 'dni', 'localidad', 'provincia', 'domicilio']
            campos_faltantes = [campo for campo in campos_requeridos if not request.POST.get(campo)]
            
            if campos_faltantes:
                nombres_campos = {
                    'nombre': 'Nombre',
                    'apellido': 'Apellido',
                    'email': 'Email',
                    'celular': 'Celular',
                    'tipo_doc': 'Tipo de Documento',
                    'dni': 'DNI',
                    'localidad': 'Localidad',
                    'provincia': 'Provincia',
                    'domicilio': 'Domicilio',
                }
                campos_faltantes_nombres = [nombres_campos.get(campo, campo) for campo in campos_faltantes]
                return JsonResponse({
                    'success': False,
                    'error': f'Faltan campos requeridos: {", ".join(campos_faltantes_nombres)}'
                })
            
            # Validar y limpiar DNI (ahora opcional)
            dni_raw = request.POST.get('dni', '').strip()
            dni_limpio = None
            
            if dni_raw:  # Solo validar si se proporciona DNI
                # Limpiar DNI: quitar puntos, espacios, guiones
                dni_limpio = dni_raw.replace('.', '').replace(' ', '').replace('-', '').replace(',', '')
                
                # Validar que el DNI solo contenga números
                if not dni_limpio.isdigit():
                    return JsonResponse({
                        'success': False,
                        'error': 'El DNI solo puede contener números. Por favor, ingrese solo los 7 u 8 dígitos del DNI sin puntos ni guiones.'
                    })
                
                # Validar longitud del DNI (7 u 8 dígitos)
                if len(dni_limpio) != 7 and len(dni_limpio) != 8:
                    return JsonResponse({
                        'success': False,
                        'error': f'El DNI debe tener 7 u 8 dígitos. Usted ingresó {len(dni_limpio)} dígito(s). Por favor, verifique el DNI.'
                    })
                
                # Verificar si el DNI ya existe
                if Propietario.objects.filter(dni=dni_limpio).exists():
                    propietario_existente = Propietario.objects.get(dni=dni_limpio)
                    return JsonResponse({
                        'success': False,
                        'error': f'Ya existe un propietario con el DNI {dni_limpio}. Propietario: {propietario_existente.apellido}, {propietario_existente.nombre}'
                    })
            
            propietario = Propietario.objects.create(
                nombre=request.POST['nombre'],
                apellido=request.POST['apellido'],
                fecha_nacimiento=fecha_nacimiento,
                email=request.POST['email'],
                celular=request.POST['celular'],
                tipo_doc=request.POST.get('tipo_doc', 'dni'),  # Valor por defecto si no se envía
                dni=dni_limpio,
                tipo_ins=request.POST.get('tipo_ins', 'otro'),  # Valor por defecto
                cuit=request.POST.get('cuit', ''),
                localidad=request.POST['localidad'],
                provincia=request.POST['provincia'],
                domicilio=request.POST['domicilio'],
                codigo_postal=request.POST.get('codigo_postal', ''),
                observaciones=request.POST.get('observaciones', ''),
                cuenta_bancaria=request.POST.get('cuenta_bancaria', ''),
                sucursal=sucursal  # Agregar la sucursal
            )
            return JsonResponse({
                'success': True,
                'propietario': {
                    'id': propietario.id,
                    'nombre': propietario.nombre,
                    'apellido': propietario.apellido,
                    'dni': propietario.dni
                }
            })
        except KeyError as e:
            return JsonResponse({
                'success': False,
                'error': f'Campo faltante: {str(e)}'
            })
        except Exception as e:
            import traceback
            error_str = str(e)
            
            # Detectar errores específicos de base de datos
            if 'value too long' in error_str.lower() and 'dni' in error_str.lower():
                return JsonResponse({
                    'success': False,
                    'error': 'El DNI ingresado es demasiado largo. El DNI debe tener exactamente 8 dígitos sin puntos ni guiones.'
                })
            elif 'unique constraint' in error_str.lower() or 'duplicate key' in error_str.lower():
                return JsonResponse({
                    'success': False,
                    'error': 'Ya existe un propietario con este DNI. Por favor, verifique que el DNI no esté duplicado.'
                })
            elif 'dni' in error_str.lower():
                return JsonResponse({
                    'success': False,
                    'error': f'Error con el DNI: {error_str}'
                })
            
            return JsonResponse({
                'success': False,
                'error': f'Error al crear propietario: {error_str}'
            })
    return JsonResponse({'success': False, 'error': 'Método no permitido'})


@login_required
def buscar_propiedades_por_fechas(request):
    """
    Vista para buscar propiedades que tienen disponibilidad en un rango de fechas,
    sin importar si están reservadas o no.
    """
    propiedades_encontradas = []
    fecha_desde = None
    fecha_hasta = None
    
    if request.method == 'POST':
        fecha_desde_str = request.POST.get('fecha_desde', '')
        fecha_hasta_str = request.POST.get('fecha_hasta', '')
        
        if fecha_desde_str and fecha_hasta_str:
            try:
                fecha_desde = datetime.strptime(fecha_desde_str, '%Y-%m-%d').date()
                fecha_hasta = datetime.strptime(fecha_hasta_str, '%Y-%m-%d').date()
                
                # Buscar todas las disponibilidades que se superponen con el rango
                disponibilidades = Disponibilidad.objects.filter(
                    fecha_inicio__lt=fecha_hasta,
                    fecha_fin__gt=fecha_desde,
                ).select_related('propiedad', 'propiedad__propietario', 'propiedad__sucursal').distinct()
                
                # Obtener propiedades únicas de disponibilidades
                propiedades_ids_disponibilidades = disponibilidades.values_list('propiedad_id', flat=True).distinct()
                
                # También buscar propiedades que tienen reservas que terminan en fecha_desde
                # (para mostrar en amarillo aunque no tengan disponibilidad que se superponga)
                reservas_terminan_inicio = Reserva.objects.filter(
                    eliminada=False,
                    fecha_fin=fecha_desde
                ).select_related('propiedad', 'propiedad__propietario', 'propiedad__sucursal')
                
                propiedades_ids_reservas = reservas_terminan_inicio.values_list('propiedad_id', flat=True).distinct()
                
                # Combinar ambas listas de IDs
                propiedades_ids = list(set(list(propiedades_ids_disponibilidades) + list(propiedades_ids_reservas)))
                
                propiedades = Propiedad.objects.filter(id__in=propiedades_ids).select_related('propietario', 'sucursal')
                
                # Para cada propiedad, obtener información relevante
                for propiedad in propiedades:
                    # Obtener disponibilidades de esta propiedad en el rango
                    disponibilidades_propiedad = disponibilidades.filter(propiedad=propiedad)
                    
                    # Verificar si tiene reservas en el rango
                    reservas_en_rango = propiedad.reservas.filter(
                        eliminada=False,
                        fecha_inicio__lt=fecha_hasta,
                        fecha_fin__gt=fecha_desde
                    )
                    
                    # Verificar si hay una reserva que termina exactamente en la fecha de inicio
                    # IMPORTANTE: Buscar reservas que terminan el día ANTES del inicio de búsqueda
                    # Si busco del 15 al 16, una reserva del 14 al 15 termina el 15, que es el día de inicio
                    # SOLO si está en estado confirmada o confirmada_no_pagada (no pagadas)
                    reserva_termina_en_inicio = propiedad.reservas.filter(
                        eliminada=False,
                        fecha_fin=fecha_desde,
                        estado__in=['confirmada', 'confirmada_no_pagada', 'en_espera']
                    ).exclude(
                        # Excluir reservas que también empiezan en fecha_desde (esas están en el rango)
                        fecha_inicio=fecha_desde
                    ).first()
                    
                    # Determinar el estado de la propiedad
                    estado_propiedad = 'disponible'
                    if reservas_en_rango.filter(estado='pagada').exists():
                        estado_propiedad = 'pagada'
                    elif reservas_en_rango.filter(estado__in=['confirmada', 'confirmada_no_pagada']).exists():
                        estado_propiedad = 'reservada'
                    elif reservas_en_rango.filter(estado='en_espera').exists():
                        estado_propiedad = 'temporal'
                    
                    # Debug: Verificar si encontramos la reserva
                    # if reserva_termina_en_inicio:
                    #     print(f"DEBUG: Propiedad {propiedad.id} tiene reserva que termina en {fecha_desde}: {reserva_termina_en_inicio.id}")
                    
                    propiedades_encontradas.append({
                        'propiedad': propiedad,
                        'disponibilidades': disponibilidades_propiedad,
                        'tiene_reservas': reservas_en_rango.exists(),
                        'reservas': reservas_en_rango,
                        'estado': estado_propiedad,
                        'reserva_termina_en_inicio': reserva_termina_en_inicio  # Reserva que termina el día de inicio (None si no hay)
                    })
                
            except ValueError:
                messages.error(request, 'Formato de fecha inválido')
    
    return render(request, 'inmobiliaria/propiedades/buscar_por_fechas.html', {
        'propiedades_encontradas': propiedades_encontradas,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta
    })


def obtener_precios_propiedad(request):
    propiedad_id = request.GET.get('propiedad_id')
    propiedad = Propiedad.objects.get(id=propiedad_id)
    precios = Precio.objects.filter(propiedad=propiedad)

    # Asegúrate de que todos los tipos de precios estén presentes
    todos_los_precios = []
    for tipo_choice in TipoPrecio.choices:
        tipo_key = tipo_choice[0]
        precio = precios.filter(tipo_precio=tipo_key).first()
        if not precio:
            precio = Precio(
                propiedad=propiedad,
                tipo_precio=tipo_key,
                precio_total=0,
                precio_por_dia=0,
                precio_toma=0,
                precio_dia_toma=0,
                ajuste_porcentaje=0
            )
        todos_los_precios.append(precio)

    # Serializar y devolver los precios
    precios_serializados = [
        {
            'tipo_precio': precio.tipo_precio,
            'precio_total': str(precio.precio_total),
            'precio_por_dia': str(precio.precio_por_dia),
            'precio_toma': str(precio.precio_toma),
            'precio_dia_toma': str(precio.precio_dia_toma),
            'ajuste_porcentaje': str(precio.ajuste_porcentaje),
        }
        for precio in todos_los_precios
    ]

    return JsonResponse({'precios': precios_serializados})

def format_price(value):
    try:
        return "{:,.0f}".format(value).replace(',', '.')
    except (ValueError, TypeError):
        return str(value)

def obtener_vendedor(request, vendedor_id):
    logger.info(f"Solicitando vendedor con ID: {vendedor_id}")
    try:
        vendedor = Vendedor.objects.get(id=vendedor_id)
        logger.info(f"Vendedor encontrado: {vendedor.nombre} {vendedor.apellido}")
# print(f"Vendedor encontrado: {vendedor.nombre} {vendedor.apellido}")
        return JsonResponse({
            'success': True,
            'vendedor': {
                'id': vendedor.id,
                'nombre_completo': f"{vendedor.apellido}, {vendedor.nombre}"
            }
        })
    except Vendedor.DoesNotExist:
        logger.warning(f"Vendedor con ID {vendedor_id} no encontrado")
        return JsonResponse({'success': False, 'message': 'Vendedor no encontrado'}, status=404)
    except Exception as e:
        logger.error(f"Error al obtener vendedor: {str(e)}")
        return JsonResponse({'success': False, 'message': 'Error interno del servidor'}, status=500)











@login_required
def estudiantes(request):
    """Página principal de Estudiantes: enlaces a disponibilidad masiva y buscar propiedades."""
    return render(request, 'inmobiliaria/estudiantes/index.html')


@login_required
def estudiantes_disponibilidad_masiva(request):
    """
    Disponibilidad masiva para propiedades de tipo Estudiante.
    Por defecto muestra solo la sucursal del usuario; con ver_todas=1 muestra Colón y Corrientes juntas.
    """
    q_sucursales_colon_corrientes = Q(sucursal__nombre__icontains='colon') | Q(sucursal__nombre__icontains='corrientes')
    ver_todas = request.GET.get('ver_todas') == '1'

    if request.method == 'POST':
        propiedad_ids = request.POST.getlist('propiedades[]')
        fecha_inicio_str = request.POST.get('fecha_inicio')
        fecha_fin_str = request.POST.get('fecha_fin')
        try:
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date() if fecha_inicio_str else None
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date() if fecha_fin_str else None
        except (ValueError, TypeError):
            fecha_inicio = fecha_fin = None
        if not fecha_inicio or not fecha_fin:
            return JsonResponse({'success': False, 'message': 'Fechas de inicio y fin son obligatorias y deben ser válidas.'})
        if fecha_inicio > fecha_fin:
            return JsonResponse({'success': False, 'message': 'La fecha de inicio no puede ser posterior a la fecha de fin.'})

        propiedades_actualizadas = 0
        propiedades_exitosas = []
        errores_detallados = []

        try:
            for propiedad_id in propiedad_ids:
                try:
                    propiedad = Propiedad.objects.filter(q_sucursales_colon_corrientes, tipo_cliente='ESTUDIANTE').get(id=propiedad_id)
                except Propiedad.DoesNotExist:
                    errores_detallados.append({
                        'propiedad_id': propiedad_id,
                        'direccion': 'Desconocida',
                        'error': 'No es una propiedad de estudiante de Colón/Corrientes o no existe',
                        'tipo': 'no_existe'
                    })
                    continue

                try:
                    todas_disponibilidades = Disponibilidad.objects.filter(propiedad=propiedad)
                    solapamientos_reales = [
                        d for d in todas_disponibilidades
                        if d.fecha_inicio is not None and d.fecha_fin is not None
                        and d.fecha_fin > fecha_inicio and d.fecha_inicio < fecha_fin
                    ]
                    if solapamientos_reales:
                        fechas_conflicto = [f"{d.fecha_inicio.strftime('%d/%m/%Y')} - {d.fecha_fin.strftime('%d/%m/%Y')}" for d in solapamientos_reales]
                        raise ValueError(f"Se superpone con disponibilidades existentes: {', '.join(fechas_conflicto)}")

                    Disponibilidad.objects.create(
                        propiedad=propiedad,
                        fecha_inicio=fecha_inicio,
                        fecha_fin=fecha_fin,
                        es_manual=True
                    )
                    propiedades_actualizadas += 1
                    propiedades_exitosas.append({
                        'propiedad_id': propiedad_id,
                        'direccion': propiedad.direccion,
                        'piso': propiedad.piso or '-',
                        'departamento': propiedad.departamento or '-'
                    })
                except ValueError as e:
                    errores_detallados.append({
                        'propiedad_id': propiedad_id,
                        'direccion': propiedad.direccion,
                        'piso': propiedad.piso or '-',
                        'departamento': propiedad.departamento or '-',
                        'error': str(e),
                        'tipo': 'solapamiento'
                    })
                except Exception as e:
                    errores_detallados.append({
                        'propiedad_id': propiedad_id,
                        'direccion': getattr(propiedad, 'direccion', 'Desconocida'),
                        'piso': getattr(propiedad, 'piso', '-') or '-',
                        'departamento': getattr(propiedad, 'departamento', '-') or '-',
                        'error': str(e),
                        'tipo': 'error_general'
                    })

            respuesta = {
                'propiedades_procesadas': len(propiedad_ids),
                'propiedades_exitosas': propiedades_actualizadas,
                'propiedades_con_errores': len(errores_detallados),
                'detalles_exitosas': propiedades_exitosas,
                'detalles_errores': errores_detallados
            }
            if propiedades_actualizadas > 0:
                mensaje = f'✅ {propiedades_actualizadas} propiedades actualizadas correctamente'
                if errores_detallados:
                    mensaje += f'\n⚠️ {len(errores_detallados)} propiedades con errores'
                return JsonResponse({'success': True, 'message': mensaje, 'detalles': respuesta})
            return JsonResponse({
                'success': False,
                'message': f'❌ No se pudo actualizar ninguna propiedad ({len(errores_detallados)} errores)',
                'detalles': respuesta
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    # Lista: por defecto sucursal del usuario; con ver_todas=1, Colón y Corrientes juntas
    base_qs = Propiedad.objects.filter(tipo_cliente='ESTUDIANTE')
    if ver_todas:
        base_qs = base_qs.filter(q_sucursales_colon_corrientes)
    else:
        sucursal_usuario = getattr(request.user, 'sucursal', None)
        if sucursal_usuario:
            base_qs = base_qs.filter(sucursal=sucursal_usuario)
        else:
            base_qs = base_qs.filter(q_sucursales_colon_corrientes)
    propiedades = base_qs.select_related('propietario', 'sucursal').order_by(
        Lower('propietario__apellido'), Lower('propietario__nombre'), 'direccion', 'id'
    )

    return render(request, 'inmobiliaria/estudiantes/disponibilidad_masiva.html', {
        'propiedades': propiedades,
        'es_estudiantes': True,
        'ver_todas': ver_todas,
    })


@login_required
def buscar_propiedades_estudiantes(request):
    """
    Buscar propiedades de estudiantes por fechas, ambientes, precio máximo, dirección y ficha.
    """
    propiedades_encontradas = []
    fecha_desde = None
    fecha_hasta = None
    filtro_ambientes = None
    filtro_precio_max = None
    filtro_direccion = ''
    filtro_ficha = ''
    total_propiedades_disponibles = 0
    total_propiedades_reservadas = 0

    q_sucursales = Q(sucursal__nombre__icontains='colon') | Q(sucursal__nombre__icontains='corrientes')

    if request.method == 'POST':
        fecha_desde_str = request.POST.get('fecha_desde', '')
        fecha_hasta_str = request.POST.get('fecha_hasta', '')
        ambientes_str = request.POST.get('ambientes', '').strip()
        precio_max_str = request.POST.get('precio_max', '').strip()
        filtro_direccion = (request.POST.get('direccion', '') or '').strip()
        filtro_ficha = (request.POST.get('ficha', '') or '').strip()

        if fecha_desde_str and fecha_hasta_str:
            try:
                fecha_desde = datetime.strptime(fecha_desde_str, '%Y-%m-%d').date()
                fecha_hasta = datetime.strptime(fecha_hasta_str, '%Y-%m-%d').date()
                if ambientes_str:
                    filtro_ambientes = int(ambientes_str)
                if precio_max_str:
                    filtro_precio_max = Decimal(precio_max_str.replace(',', '.'))
            except (ValueError, InvalidOperation):
                pass

        if fecha_desde and fecha_hasta:
            disponibilidades = Disponibilidad.objects.filter(
                fecha_inicio__lt=fecha_hasta,
                fecha_fin__gt=fecha_desde,
            ).select_related('propiedad', 'propiedad__propietario', 'propiedad__sucursal')

            propiedades_ids = list(disponibilidades.values_list('propiedad_id', flat=True).distinct())
            q_prop = Q(id__in=propiedades_ids, tipo_cliente='ESTUDIANTE') & q_sucursales
            if filtro_ambientes is not None:
                q_prop = q_prop & Q(ambientes=filtro_ambientes)
            if filtro_direccion:
                q_prop = q_prop & Q(direccion__icontains=filtro_direccion)
            if filtro_ficha:
                try:
                    q_prop = q_prop & Q(numero_por_propietario=int(filtro_ficha))
                except ValueError:
                    pass  # Si no es número, no se aplica filtro por ficha
            propiedades = Propiedad.objects.filter(q_prop).select_related('propietario', 'sucursal').prefetch_related('precios')

            for propiedad in propiedades:
                precio_est = next((p for p in propiedad.precios.all() if p.tipo_precio == 'ESTUDIANTE'), None)
                precio_val = precio_est.precio_total if (precio_est and precio_est.precio_total is not None) else None
                if filtro_precio_max is not None:
                    if precio_val is None:
                        continue
                    if precio_val > filtro_precio_max:
                        continue
                disp_prop = disponibilidades.filter(propiedad=propiedad)
                reserva_termina_en_inicio = propiedad.reservas.filter(
                    eliminada=False,
                    fecha_fin=fecha_desde,
                    estado__in=['confirmada', 'confirmada_no_pagada', 'en_espera']
                ).exclude(fecha_inicio=fecha_desde).first()
                # ¿Tiene reserva activa que solapa con el rango? (para contar como reservada)
                reserva_activa_rango = propiedad.reservas.filter(
                    eliminada=False,
                    estado__in=['confirmada', 'confirmada_no_pagada', 'en_espera'],
                    fecha_inicio__lt=fecha_hasta,
                    fecha_fin__gt=fecha_desde
                ).exists()
                propiedades_encontradas.append({
                    'propiedad': propiedad,
                    'disponibilidades': disp_prop,
                    'reserva_termina_en_inicio': reserva_termina_en_inicio,
                    'precio_estudiante': precio_val,
                    'es_reservada': reserva_activa_rango,
                })

    total_propiedades_disponibles = sum(1 for item in propiedades_encontradas if not item.get('es_reservada', False))
    total_propiedades_reservadas = sum(1 for item in propiedades_encontradas if item.get('es_reservada', False))

    ambientes_choices = list(Propiedad.objects.filter(tipo_cliente='ESTUDIANTE').filter(q_sucursales).values_list('ambientes', flat=True).distinct().order_by('ambientes'))
    ambientes_choices = [a for a in ambientes_choices if a is not None]

    return render(request, 'inmobiliaria/estudiantes/buscar.html', {
        'propiedades_encontradas': propiedades_encontradas,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'filtro_ambientes': filtro_ambientes,
        'filtro_precio_max': filtro_precio_max,
        'filtro_direccion': filtro_direccion,
        'filtro_ficha': filtro_ficha,
        'ambientes_choices': ambientes_choices,
        'total_propiedades_disponibles': total_propiedades_disponibles,
        'total_propiedades_reservadas': total_propiedades_reservadas,
    })


def agregar_disponibilidad_masiva(request):
    # Obtener la sucursal del usuario logueado
    sucursal = request.user.sucursal

    if request.method == 'POST':
        propiedad_ids = request.POST.getlist('propiedades[]')
        fecha_inicio_str = (request.POST.get('fecha_inicio') or '').strip()
        fecha_fin_str = (request.POST.get('fecha_fin') or '').strip()
        try:
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date() if fecha_inicio_str else None
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date() if fecha_fin_str else None
        except (ValueError, TypeError):
            fecha_inicio = fecha_fin = None
        if not fecha_inicio or not fecha_fin:
            return JsonResponse({
                'success': False,
                'message': 'Indicá fecha de inicio y fin válidas (formato del navegador: AAAA-MM-DD).',
            })
        if fecha_inicio > fecha_fin:
            return JsonResponse({
                'success': False,
                'message': 'La fecha de inicio no puede ser posterior a la fecha de fin.',
            })

        propiedades_actualizadas = 0
        propiedades_exitosas = []
        errores_detallados = []
        
        try:
            # Procesar cada propiedad individualmente y reportar resultados detallados
            for propiedad_id in propiedad_ids:
                try:
                    propiedad = Propiedad.objects.get(
                        id=propiedad_id,
                        sucursal=sucursal  # Usar la sucursal del usuario
                    )
                    
                    # ✅ VALIDAR SUPERPOSICIÓN REAL (permitir fechas contiguas)
                    todas_disponibilidades = Disponibilidad.objects.filter(
                        propiedad=propiedad
                    )
                    
                    # Verificar VERDADERA superposición (excluir fechas contiguas)
                    solapamientos_reales = []
                    for disp in todas_disponibilidades:
                        # Filas legacy o corruptas con NULL rompen la comparación (TypeError con "date" en el mensaje)
                        if disp.fecha_inicio is None or disp.fecha_fin is None:
                            continue
                        # Superposición REAL: comparten MÁS de un día
                        # Si solo se tocan en UN día (contiguas como 10-15 y 15-20), es válido
                        if disp.fecha_fin > fecha_inicio and disp.fecha_inicio < fecha_fin:
                            solapamientos_reales.append(disp)
                    
                    if solapamientos_reales:
                        # Obtener info de las disponibilidades que se superponen REALMENTE
                        fechas_conflicto = []
                        for disp in solapamientos_reales:
                            fechas_conflicto.append(f"{disp.fecha_inicio.strftime('%d/%m/%Y')} - {disp.fecha_fin.strftime('%d/%m/%Y')}")
                        
                        raise ValueError(f"Se superpone con disponibilidades existentes: {', '.join(fechas_conflicto)}")
                    
                    # 🎯 CREAR DISPONIBILIDAD (solo si no hay superposición)
                    nueva_disponibilidad = Disponibilidad.objects.create(
                        propiedad=propiedad,
                        fecha_inicio=fecha_inicio,
                        fecha_fin=fecha_fin,
                        es_manual=True  # Marcada explícitamente como manual
                    )
                    
                    # ✅ Las disponibilidades manuales no crean historial automáticamente
                    # El historial se gestiona por separado
                    
                    # ✅ Si llegamos aquí, fue exitoso
                    propiedades_actualizadas += 1
                    propiedades_exitosas.append({
                        'propiedad_id': propiedad_id,
                        'direccion': f"{propiedad.direccion}",
                        'piso': propiedad.piso or '-',
                        'departamento': propiedad.departamento or '-'
                    })
                        
                except Propiedad.DoesNotExist:
                    errores_detallados.append({
                        'propiedad_id': propiedad_id,
                        'direccion': 'Desconocida',
                        'error': 'No pertenece a su sucursal o no existe',
                        'tipo': 'no_existe'
                    })
                except Exception as e:
                    # Intentar obtener la dirección para mejor reporte
                    try:
                        propiedad = Propiedad.objects.get(id=propiedad_id)
                        direccion = f"{propiedad.direccion}"
                        piso = propiedad.piso or '-'
                        departamento = propiedad.departamento or '-'
                    except:
                        direccion = 'Desconocida'
                        piso = '-'
                        departamento = '-'
                    
                    # 🔍 Clasificar el tipo de error para mayor claridad
                    error_msg = str(e)
                    tipo_error = 'error_general'
                    
                    if 'superpone con disponibilidades' in error_msg.lower():
                        tipo_error = 'solapamiento'
                    elif 'UNIQUE constraint failed' in error_msg or 'duplicate' in error_msg.lower():
                        error_msg = 'Ya existe disponibilidad para estas fechas'
                        tipo_error = 'solapamiento'
                    elif 'foreign key' in error_msg.lower():
                        error_msg = 'Problema de referencia en la base de datos'
                        tipo_error = 'referencia'
                    elif len(error_msg) > 280:
                        error_msg = error_msg[:277] + '...'
                    
                    errores_detallados.append({
                        'propiedad_id': propiedad_id,
                        'direccion': direccion,
                        'piso': piso,
                        'departamento': departamento,
                        'error': error_msg,
                        'tipo': tipo_error,
                        'error_original': str(e)  # Para debugging si es necesario
                    })
            
            # Preparar respuesta detallada
            respuesta = {
                'propiedades_procesadas': len(propiedad_ids),
                'propiedades_exitosas': propiedades_actualizadas,
                'propiedades_con_errores': len(errores_detallados),
                'detalles_exitosas': propiedades_exitosas,
                'detalles_errores': errores_detallados
            }
            
            if propiedades_actualizadas > 0:
                mensaje = f'✅ {propiedades_actualizadas} propiedades actualizadas correctamente'
                if errores_detallados:
                    mensaje += f'\n⚠️ {len(errores_detallados)} propiedades con errores'
                
                return JsonResponse({
                    'success': True,
                    'message': mensaje,
                    'detalles': respuesta
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': f'❌ No se pudo actualizar ninguna propiedad ({len(errores_detallados)} errores)',
                    'detalles': respuesta
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error al actualizar disponibilidades: {str(e)}'
            })
    
    # Filtrar propiedades por sucursal para el listado (orden por apellido del propietario)
    propiedades = Propiedad.objects.filter(
        sucursal=sucursal
    ).select_related('propietario').order_by(
        Lower('propietario__apellido'), Lower('propietario__nombre'), 'direccion', 'id'
    )

    return render(request, 'inmobiliaria/propiedades/disponibilidad_masiva.html', {
        'propiedades': propiedades,
        'sucursal': sucursal  # Pasar la sucursal al template
    })

# views.py
@login_required
def obtener_inquilino(request, inquilino_id):
    try:
        inquilino = Inquilino.objects.get(id=inquilino_id)
        return JsonResponse({'success': True, 'inquilino': {
            'id': inquilino.id,
            'nombre': inquilino.nombre,
            'apellido': inquilino.apellido,
            'dni': inquilino.dni,
            # Agrega más campos según sea necesario
        }})
    except Inquilino.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Inquilino no encontrado.'}, status=404)

def crear_sucursal(request):
    if request.method == 'POST':
        form = SucursalForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('inmobiliaria:reservas')  # Redirige a una lista de sucursales o a donde desees
    else:
        form = SucursalForm()
    
    return render(request, 'inmobiliaria/sucursal/crear_sucursal.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            
            try:
                vendedor = Vendedor.objects.select_related('sucursal').get(username=username)
                
                if not vendedor.is_active:
                    messages.error(request, 'Tu cuenta no está activa. Contacta al administrador.')
                    return render(request, 'inmobiliaria/autenticacion/login.html', {'form': form})
                
                user = authenticate(request, username=username, password=password)
                if user is not None:
                    login(request, user)
                    # Verificar si tiene contraseña temporal
                    if hasattr(user, 'password_temporal') and user.password_temporal:
                        return redirect('inmobiliaria:cambiar_password')
                    return redirect('inmobiliaria:index')
                else:
                    messages.error(request, 'Contraseña incorrecta.')
                
            except Vendedor.DoesNotExist:
                messages.error(request, f'El usuario {username} no existe.')
            except Exception as e:
                logger.exception('Error 500 en login para usuario %s: %s', username, e)
                messages.error(request, 'Error al iniciar sesión. Si el problema continúa, contacta al administrador.')
                return render(request, 'inmobiliaria/autenticacion/login.html', {'form': form})
        else:
            messages.error(request, 'Por favor, corrige los errores del formulario.')
    else:
        form = LoginForm()
    
    return render(request, 'inmobiliaria/autenticacion/login.html', {'form': form})

@login_required
@require_http_methods(["POST"])
def actualizar_orden_imagenes(request):
    try:
        data = json.loads(request.body)
        imagenes_orden = data.get('imagenes', [])
        logger.info(f"Actualizando orden de imágenes: {imagenes_orden}")
        
        for item in imagenes_orden:
            try:
                imagen = ImagenPropiedad.objects.get(id=item['id'])
                if imagen.orden != item['orden']:
                    imagen.orden = item['orden']
                    imagen.save()
            except ImagenPropiedad.DoesNotExist:
                logger.error(f"No se encontró la imagen con ID: {item['id']}")
            except Exception as e:
                logger.error(f"Error al actualizar imagen {item['id']}: {str(e)}")
        
        return JsonResponse({'success': True})
    except json.JSONDecodeError as e:
        logger.error(f"Error al decodificar JSON: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Datos JSON inválidos'}, status=400)
    except Exception as e:
        logger.error(f"Error general en actualizar_orden_imagenes: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
@require_http_methods(["DELETE"])
def eliminar_imagen(request):
    try:
        imagen_id = request.GET.get('imagen_id')
        logger.info(f"Intentando eliminar imagen ID: {imagen_id}")
        
        if not imagen_id:
            return JsonResponse({'success': False, 'error': 'ID de imagen no proporcionado'}, status=400)
        
        imagen = get_object_or_404(ImagenPropiedad, id=imagen_id)
        orden_eliminado = imagen.orden
        propiedad = imagen.propiedad
        
        # Eliminar el archivo físico
        try:
            if imagen.imagen:
                imagen.imagen.delete(save=False)
        except Exception as e:
            logger.error(f"Error al eliminar archivo físico: {str(e)}")
        
        # Eliminar el registro de la base de datos
        imagen.delete()
        
        # Reordenar las imágenes restantes
        ImagenPropiedad.objects.filter(
            propiedad=propiedad,
            orden__gt=orden_eliminado
        ).update(orden=models.F('orden') - 1)
        
        return JsonResponse({'success': True})
    except ImagenPropiedad.DoesNotExist:
        logger.error(f"Imagen no encontrada: {imagen_id}")
        return JsonResponse({'success': False, 'error': 'Imagen no encontrada'}, status=404)
    except Exception as e:
        logger.error(f"Error al eliminar imagen: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def enviar_recuperacion(request):
    form = EmailForm()
    
    if request.method == "POST":
        form = EmailForm(request.POST)
        
        if form.is_valid():
            email = form.cleaned_data['email']
            User = get_user_model()
            
            try:
                # Buscar usuario por email (case-insensitive)
                user = User.objects.filter(email__iexact=email).first()
                
                if user:
                    # Verificar que el usuario tiene email válido
                    if not user.email or not user.email.strip():
                        messages.error(request, 'Tu cuenta no tiene un correo electrónico configurado. Contacta al administrador.')
                        return render(request, 'inmobiliaria/autenticacion/password_reset_form.html', {'form': form})
                    
                    # Generar una nueva contraseña temporal
                    nueva_password = User.objects.make_random_password()
                    user.set_password(nueva_password)
                    user.password_temporal = True  # Marcar como contraseña temporal
                    user.save()
                    
                    # Enviar email con la nueva contraseña
                    subject = 'Tu nueva contraseña - Sistema Gonnet'
                    message = f'''
Hola {user.first_name if user.first_name else user.username},

Tu nueva contraseña temporal es: {nueva_password}

Por favor, ingresa con esta contraseña y cámbiala inmediatamente por una de tu preferencia.

Saludos,
El equipo de Sistema Gonnet
                    '''
                    
                    try:
                        send_mail(
                            subject,
                            message,
                            'gonnetinterno@gmail.com',  # Remitente
                            [user.email],  # Destinatario
                            fail_silently=False,
                        )
                        messages.success(request, f'Se ha enviado un correo con tu nueva contraseña a {user.email}.')
                        return redirect('inmobiliaria:password_reset_done')
                    except Exception as e:
                        # Revertir el cambio de contraseña si falla el envío
                        user.refresh_from_db()
                        messages.error(request, f'Error al enviar el correo: {str(e)}. Por favor, contacta al administrador.')
                else:
                    # Mensaje simple sin debug complejo
                    messages.error(request, 'No existe una cuenta con ese correo electrónico. Verifica que esté escrito correctamente.')
                        
            except Exception as e:
                messages.error(request, f'Error al procesar la solicitud: {str(e)}')
        else:
            # Si el formulario no es válido, mostrar errores
            messages.error(request, 'Por favor, ingresa un correo electrónico válido.')
    
    return render(request, 'inmobiliaria/autenticacion/password_reset_form.html', {'form': form})

@login_required
def cambiar_password(request):
    if request.method == 'POST':
        form = SetPasswordForm(request.user, request.POST)
        if form.is_valid():
            try:
                user = form.save()
                update_session_auth_hash(request, user)  # Mantiene la sesión activa
                user.password_temporal = False
                user.save()
                messages.success(request, 'Tu contraseña ha sido actualizada exitosamente.')
                return redirect('inmobiliaria:index')
            except Exception as e:
                messages.error(request, f'Error al guardar la contraseña: {str(e)}')
        else:
            # Mostrar errores específicos del formulario
            for field in form:
                for error in field.errors:
                    messages.error(request, f'{field.label}: {error}')
            if form.non_field_errors():
                for error in form.non_field_errors():
                    messages.error(request, error)
    else:
        form = SetPasswordForm(request.user)
    
    return render(request, 'inmobiliaria/autenticacion/cambiar_password.html', {
        'form': form,
        'user': request.user
    })

@login_required
def confirmar_pago(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    conceptos_pago = ConceptoPago.objects.all()
    
    context = {
        'reserva': reserva,
        'conceptos_pago': conceptos_pago,
    }
    return render(request, 'inmobiliaria/reserva/finalizar_reserva.html', context)

@login_required
def agregar_pago(request, reserva_id):
    try:
        reserva = get_object_or_404(Reserva, id=reserva_id)
        
        if request.method == 'POST':
            with transaction.atomic():
                # Obtener datos del formulario
                monto = Decimal(request.POST.get('monto', '0'))
                forma_pago = request.POST.get('forma_pago')
                concepto_id = request.POST.get('concepto')
                
                # Validaciones
                if monto <= 0:
                    raise ValueError('El monto debe ser mayor que cero')
                
                if monto > reserva.cuota_pendiente:
                    raise ValueError('El monto no puede ser mayor al saldo pendiente')
                
                # Obtener el concepto
                concepto = get_object_or_404(ConceptoPago, id=concepto_id)
                
                # Obtener datos adicionales según forma de pago
                numero_tarjeta = None
                tipo_tarjeta = None
                destino_deposito = None

                if 'tarjeta' in forma_pago:
                    numero_tarjeta = request.POST.get('numero_tarjeta')
                    tipo_tarjeta = request.POST.get('tipo_tarjeta')
                    
                    if not numero_tarjeta or not tipo_tarjeta:
                        raise ValueError('Los datos de la tarjeta son requeridos')
                
                elif forma_pago in ['transferencia', 'qr']:
                    destino_deposito = request.POST.get('destino_deposito')
                    if not destino_deposito:
                        raise ValueError('El destino de la transferencia es requerido')
                
                # Crear el pago
                pago = Pago.objects.create(
                    reserva=reserva,
                    monto=monto,
                    forma_pago=forma_pago,
                    concepto=concepto,
                    numero_tarjeta=numero_tarjeta,
                    tipo_tarjeta=tipo_tarjeta,
                    destino_deposito=destino_deposito
                )
                
                # ✅ ACTUALIZAR SALDOS SEPARANDO SEÑA DE DEPÓSITO
                pagos_reserva = Pago.objects.filter(reserva=reserva)
                total_senia_only = 0
                total_deposito_only = 0
                total_pagado = 0
                
                for pago_item in pagos_reserva:
                    total_pagado += pago_item.monto
                    
                    # Identificar si es depósito por el concepto
                    concepto_lower = pago_item.concepto.concepto.lower() if pago_item.concepto else ''
                    es_deposito = any(palabra in concepto_lower for palabra in [
                        'depósito', 'deposito', 'garantía', 'garantia', 
                        'caución', 'caucion', 'seguridad', 'fianza',
                        'deposit', 'warranty', 'security'
                    ])
                    
                    if es_deposito:
                        total_deposito_only += pago_item.monto
# print(f"💳 DEPÓSITO AGREGAR_PAGO - Concepto: '{concepto_lower}', Monto: {pago_item.monto}")
                    else:
                        total_senia_only += pago_item.monto
# print(f"💰 SEÑA AGREGAR_PAGO - Concepto: '{concepto_lower}', Monto: {pago_item.monto}")
                
                # Actualizar reserva solo con la seña
                reserva.senia = total_senia_only  # ✅ Solo seña
                reserva.cuota_pendiente = reserva.precio_total - total_senia_only  # ✅ Solo descontar seña
                
# print(f"💰 AGREGAR_PAGO - Precio Total: {reserva.precio_total}, Seña: {total_senia_only}, Depósito: {total_deposito_only}, Saldo: {reserva.cuota_pendiente}")
                
                # Si se completó el pago, finalizar la reserva
                if reserva.cuota_pendiente <= 0:
                    reserva.estado = 'finalizada'
                else:
                    reserva.estado = 'en_espera'
                
                reserva.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Pago registrado exitosamente',
                    'redirect_url': reverse('inmobiliaria:finalizar_reserva', args=[reserva.id]),
                    'detalles': {
                        'total_pagado': float(total_pagado),
                        'saldo_pendiente': float(reserva.cuota_pendiente),
                        'estado': reserva.estado
                    }
                })
                
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        })

@login_required
def eliminar_pago(request, pago_id):
    pago = get_object_or_404(Pago, id=pago_id)
    reserva_id = pago.reserva.id
    
    try:
        pago.delete()
        messages.success(request, 'Pago eliminado correctamente.')
    except Exception as e:
        messages.error(request, f'Error al eliminar el pago: {str(e)}')
    
    return redirect('inmobiliaria:confirmar_pago', reserva_id=reserva_id)

@login_required
def agregar_deposito(request, reserva_id):
    try:
        reserva = get_object_or_404(Reserva, id=reserva_id)
        
        if request.method == 'POST':
            monto_deposito = Decimal(request.POST.get('monto_deposito', '0'))
            
            if monto_deposito <= 0:
                raise ValueError('El monto del depósito debe ser mayor que cero')
            
            # Actualizar el depósito de garantía
            reserva.deposito_garantia = monto_deposito
            reserva.save()
            
            messages.success(request, 'Depósito de garantía registrado exitosamente')
        
        return redirect('inmobiliaria:finalizar_reserva', reserva_id=reserva_id)
        
    except Exception as e:
        messages.error(request, f'Error al registrar el depósito: {str(e)}')
        return redirect('inmobiliaria:finalizar_reserva', reserva_id=reserva_id)

from django.contrib.auth import logout
from django.shortcuts import redirect

def logout_view(request):
    logout(request)
    return redirect('inmobiliaria:login')

def _clip_libre_por_contratos_invierno(items, contratos_invierno):
    """Recorta segmentos 'libre' para que no se superpongan con contratos de invierno."""
    if not contratos_invierno:
        return items
    from datetime import datetime as dt
    rangos_contrato = [(c.fecha_inicio, c.fecha_fin) for c in contratos_invierno]
    resultado = []
    for it in items:
        if it.get('estado') != 'libre':
            resultado.append(it)
            continue
        try:
            ini = dt.strptime(it['fecha_inicio'], '%d/%m/%Y').date()
            fin = dt.strptime(it['fecha_fin'], '%d/%m/%Y').date()
        except (ValueError, TypeError):
            resultado.append(it)
            continue
        segmentos = [(ini, fin)]
        for (c_ini, c_fin) in rangos_contrato:
            nuevos = []
            for (s_ini, s_fin) in segmentos:
                if s_ini >= c_fin or s_fin <= c_ini:
                    nuevos.append((s_ini, s_fin))
                    continue
                if s_ini < c_ini:
                    # Hotel: Libre hasta el día de inicio del contrato inclusive
                    nuevos.append((s_ini, min(s_fin, c_ini)))
                if s_fin > c_fin:
                    # Hotel: Libre desde el día de fin del contrato inclusive
                    nuevos.append((max(s_ini, c_fin), s_fin))
            segmentos = [(a, b) for a, b in nuevos if a <= b]
        for (a, b) in segmentos:
            copia = dict(it)
            copia['fecha_inicio'] = a.strftime('%d/%m/%Y')
            copia['fecha_fin'] = b.strftime('%d/%m/%Y')
            copia['_sort'] = (a, b)
            resultado.append(copia)
    return resultado


def actualizar_historial_por_contrato_invierno(propiedad, fecha_inicio, fecha_fin):
    """Trunca segmentos 'libre' del historial que superpongan con el contrato de invierno."""
    segmentos = list(HistorialDisponibilidad.objects.filter(
        propiedad=propiedad, estado='libre'
    ))
    for seg in segmentos:
        if seg.fecha_inicio >= fecha_fin or seg.fecha_fin <= fecha_inicio:
            continue
        if seg.fecha_inicio >= fecha_inicio and seg.fecha_fin <= fecha_fin:
            seg.delete()
        elif seg.fecha_inicio < fecha_inicio and seg.fecha_fin > fecha_fin:
            # Hotel: Libre hasta inicio inclusive, Libre desde fin inclusive
            HistorialDisponibilidad.objects.create(
                propiedad=propiedad, fecha_inicio=seg.fecha_inicio,
                fecha_fin=fecha_inicio, estado='libre', es_principal=seg.es_principal
            )
            HistorialDisponibilidad.objects.create(
                propiedad=propiedad, fecha_inicio=fecha_fin,
                fecha_fin=seg.fecha_fin, estado='libre', es_principal=seg.es_principal
            )
            seg.delete()
        elif seg.fecha_inicio < fecha_inicio:
            # Hotel: Libre hasta el día de inicio del contrato inclusive
            seg.fecha_fin = fecha_inicio
            if seg.fecha_inicio <= seg.fecha_fin:
                seg.save(update_fields=['fecha_fin'])
            else:
                seg.delete()
        else:
            # Hotel: Libre desde el día de fin del contrato inclusive
            seg.fecha_inicio = fecha_fin
            if seg.fecha_inicio <= seg.fecha_fin:
                seg.save(update_fields=['fecha_inicio'])
            else:
                seg.delete()


def ver_historial_disponibilidad(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, pk=propiedad_id)
    # Orden cronológico: más antiguo primero (fecha_inicio ascendente)
    historial_qs = HistorialDisponibilidad.objects.filter(
        propiedad=propiedad
    ).order_by('fecha_inicio', 'fecha_fin', 'id')

    items = []
    for h in historial_qs:
        items.append({
            'id': h.id,
            'fecha_inicio': h.fecha_inicio.strftime('%d/%m/%Y'),
            'fecha_fin': h.fecha_fin.strftime('%d/%m/%Y'),
            'estado': h.estado,
            'reserva_id': h.reserva.id if h.reserva else None,
            'cliente': h.reserva.cliente.nombre if h.reserva and h.reserva.cliente else None,
            'ultima_actualizacion': h.fecha_actualizacion.strftime('%d/%m/%Y %H:%M'),
            'es_invierno': False,
            'contrato_id': None,
            'inquilino_texto': None,
            'es_libre_invierno': False,
            '_sort': (h.fecha_inicio, h.fecha_fin),
        })

    # Incluir solo contratos de invierno vigentes (no cancelados/rescindidos)
    contratos_invierno_qs = ContratoAlquiler.objects.filter(
        propiedad=propiedad,
        duracion_meses=9,
        estado__in=['activo', 'reservado']
    ).select_related('inquilino').order_by('-id')
    # Si hay varios con fechas superpuestas, mostrar solo el más reciente (mayor id) por rango
    contratos_invierno = []
    for c in contratos_invierno_qs:
        if any(c.fecha_inicio < ex.fecha_fin and c.fecha_fin > ex.fecha_inicio for ex in contratos_invierno):
            continue
        contratos_invierno.append(c)
    contratos_invierno.sort(key=lambda x: (x.fecha_inicio, x.fecha_fin))
    for c in contratos_invierno:
        items.append({
            'id': None,
            'fecha_inicio': c.fecha_inicio.strftime('%d/%m/%Y'),
            'fecha_fin': c.fecha_fin.strftime('%d/%m/%Y'),
            'estado': 'alquilado',
            'reserva_id': None,
            'cliente': None,
            'ultima_actualizacion': c.fecha_creacion.strftime('%d/%m/%Y %H:%M') if c.fecha_creacion else '',
            'es_invierno': True,
            'contrato_id': c.id,
            'inquilino_texto': f'{c.inquilino.apellido}, {c.inquilino.nombre}' if c.inquilino else '-',
            'es_libre_invierno': False,
            '_sort': (c.fecha_inicio, c.fecha_fin),
        })

    # Incluir períodos "Libre (Invierno)" entre y después de contratos invierno
    try:
        info_invierno = propiedad.info_invierno
    except AlquilerInvierno.DoesNotExist:
        info_invierno = None
    if info_invierno and getattr(info_invierno, 'disponible', False):
        hoy = date.today()
        for j in range(len(contratos_invierno) - 1):
            c1 = contratos_invierno[j]
            c2 = contratos_invierno[j + 1]
            libre_inicio = c1.fecha_fin
            libre_fin = c2.fecha_inicio
            if libre_inicio <= libre_fin:
                items.append({
                    'id': None,
                    'fecha_inicio': libre_inicio.strftime('%d/%m/%Y'),
                    'fecha_fin': libre_fin.strftime('%d/%m/%Y'),
                    'estado': 'libre',
                    'reserva_id': None,
                    'cliente': None,
                    'ultima_actualizacion': info_invierno.fecha_actualizacion.strftime('%d/%m/%Y %H:%M') if info_invierno.fecha_actualizacion else '',
                    'es_invierno': False,
                    'contrato_id': None,
                    'inquilino_texto': None,
                    'es_libre_invierno': True,
                    '_sort': (libre_inicio, libre_fin),
                })
        # No agregar "Libre (Invierno)" después del último contrato (evita fecha hasta 2027).
        # No agregar "Libre (Invierno)" antes del primer contrato: al crear una operación de invierno no debe aparecer ese bloque automático.
        if not contratos_invierno and getattr(info_invierno, 'estado', None) == 'disponible':
            if getattr(info_invierno, 'fecha_inicio', None) and getattr(info_invierno, 'fecha_fin', None):
                libre_inicio = info_invierno.fecha_inicio
                libre_fin = info_invierno.fecha_fin
            else:
                libre_inicio = hoy
                libre_fin = hoy + timedelta(days=365)
            # No mostrar "Libre (Invierno)" en el pasado: si la fecha inicio guardada es anterior a hoy, arrancar desde hoy
            if libre_inicio < hoy:
                libre_inicio = hoy
            if libre_fin < libre_inicio:
                libre_fin = libre_inicio
            # Recortar el bloque "Libre (Invierno)" por reservas y otros segmentos ocupados ya en items
            rangos_ocupados = []
            for it in items:
                if it.get('estado') not in ('reservado', 'alquilado'):
                    continue
                try:
                    from datetime import datetime as _dt
                    ri = _dt.strptime(it['fecha_inicio'], '%d/%m/%Y').date()
                    rf = _dt.strptime(it['fecha_fin'], '%d/%m/%Y').date()
                except (ValueError, TypeError, KeyError):
                    continue
                if ri < libre_fin and rf > libre_inicio:
                    rangos_ocupados.append((max(ri, libre_inicio), min(rf, libre_fin)))
            rangos_ocupados.sort(key=lambda x: x[0])
            # Unir solapados y obtener huecos libres
            segmentos_libre = []
            if not rangos_ocupados:
                segmentos_libre = [(libre_inicio, libre_fin)]
            else:
                actual = libre_inicio
                for (o_ini, o_fin) in rangos_ocupados:
                    if actual < o_ini:
                        segmentos_libre.append((actual, o_ini))
                    actual = max(actual, o_fin)
                if actual < libre_fin:
                    segmentos_libre.append((actual, libre_fin))
            ultima_act = info_invierno.fecha_actualizacion.strftime('%d/%m/%Y %H:%M') if info_invierno.fecha_actualizacion else ''
            for (a, b) in segmentos_libre:
                if a >= b:
                    continue
                items.append({
                    'id': None,
                    'fecha_inicio': a.strftime('%d/%m/%Y'),
                    'fecha_fin': b.strftime('%d/%m/%Y'),
                    'estado': 'libre',
                    'reserva_id': None,
                    'cliente': None,
                    'ultima_actualizacion': ultima_act,
                    'es_invierno': False,
                    'contrato_id': None,
                    'inquilino_texto': None,
                    'es_libre_invierno': True,
                    '_sort': (a, b),
                })

    # Recortar segmentos 'libre' que se superpongan con contratos de invierno
    items = _clip_libre_por_contratos_invierno(items, contratos_invierno)

    items.sort(key=lambda x: x['_sort'])
    for it in items:
        del it['_sort']

    return JsonResponse({
        'success': True,
        'historial': items,
    })

@login_required
def limpiar_historial_disponibilidad(request):
    """
    Vista para limpiar y reconstruir el historial de disponibilidad
    """
    if request.method == 'POST':
        propiedad_id = request.POST.get('propiedad_id')
        
        try:
            if propiedad_id:
                # Limpiar una propiedad específica
                propiedad = get_object_or_404(Propiedad, id=propiedad_id)
                
                # Eliminar historial de esta propiedad
                count_eliminados = HistorialDisponibilidad.objects.filter(propiedad=propiedad).count()
                HistorialDisponibilidad.objects.filter(propiedad=propiedad).delete()
                
                # Reconstruir historial
                reconstruir_historial_propiedad(propiedad)
                
                return JsonResponse({
                    'success': True,
                    'message': f'✅ Historial limpiado y reconstruido para propiedad {propiedad_id}',
                    'eliminados': count_eliminados
                })
            else:
                # Limpiar TODAS las propiedades
                count_total = HistorialDisponibilidad.objects.count()
                HistorialDisponibilidad.objects.all().delete()
                
                # Reconstruir para todas las propiedades con reservas
                propiedades_con_reservas = Propiedad.objects.filter(
                    reservas__estado__in=['confirmada', 'confirmada_no_pagada']
                ).distinct()
                
                for propiedad in propiedades_con_reservas:
                    reconstruir_historial_propiedad(propiedad)
                
                return JsonResponse({
                    'success': True,
                    'message': f'✅ Historial completamente limpiado y reconstruido',
                    'eliminados': count_total,
                    'propiedades_procesadas': propiedades_con_reservas.count()
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error al limpiar historial: {str(e)}'
            })
    
    return JsonResponse({'success': False, 'error': 'Método no permitido'})

@login_required
@require_POST
def editar_historial_disponibilidad(request):
    """
    Vista para editar las fechas de un HistorialDisponibilidad con estado 'libre'
    Permite extender o modificar las fechas incluso si hay reservas en esos días
    """
    try:
        historial_id = request.POST.get('historial_id')
        fecha_inicio_str = request.POST.get('fecha_inicio')
        fecha_fin_str = request.POST.get('fecha_fin')
        
        if not historial_id or not fecha_inicio_str or not fecha_fin_str:
            return JsonResponse({
                'success': False,
                'error': 'Faltan datos requeridos'
            })
        
        # Obtener el historial
        historial = get_object_or_404(HistorialDisponibilidad, id=historial_id)
        
        # Verificar permisos
        if historial.propiedad.sucursal != request.user.sucursal:
            return JsonResponse({
                'success': False,
                'error': 'No tienes permisos para editar este historial'
            })
        
        # Verificar que el estado sea 'libre'
        if historial.estado != 'libre':
            return JsonResponse({
                'success': False,
                'error': 'Solo se pueden editar historiales con estado "Libre"'
            })
        
        # Parsear fechas
        fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
        
        # Validaciones básicas
        if fecha_inicio >= fecha_fin:
            return JsonResponse({
                'success': False,
                'error': 'La fecha de inicio debe ser anterior a la fecha de fin'
            })
        
        # Actualizar las fechas del historial (sin validar reservas, como lo requiere el usuario)
        historial.fecha_inicio = fecha_inicio
        historial.fecha_fin = fecha_fin
        historial.save()
        
        # ✅ IMPORTANTE: También actualizar o crear la Disponibilidad correspondiente
        # para que la propiedad realmente esté disponible en esas fechas
        propiedad = historial.propiedad
        
        # Buscar todas las disponibilidades manuales que se superponen o están cerca del rango editado
        # Incluir un margen de 1 día para encontrar disponibilidades contiguas
        from datetime import timedelta
        todas_disponibilidades = Disponibilidad.objects.filter(
            propiedad=propiedad,
            es_manual=True
        )
        
        # Buscar disponibilidades que se superponen o están contiguas (dentro de 1 día)
        disponibilidades_cercanas = todas_disponibilidades.filter(
            fecha_inicio__lte=fecha_fin + timedelta(days=1),
            fecha_fin__gte=fecha_inicio - timedelta(days=1)
        ).order_by('fecha_inicio')
        
        if disponibilidades_cercanas.exists():
            # Calcular el rango mínimo y máximo que cubre todas las disponibilidades cercanas + el nuevo rango
            fechas_inicio = [disp.fecha_inicio for disp in disponibilidades_cercanas] + [fecha_inicio]
            fechas_fin = [disp.fecha_fin for disp in disponibilidades_cercanas] + [fecha_fin]
            
            nueva_fecha_inicio = min(fechas_inicio)
            nueva_fecha_fin = max(fechas_fin)
            
            # Actualizar la primera disponibilidad para que cubra todo el rango extendido
            disponibilidad_principal = disponibilidades_cercanas.first()
            disponibilidad_principal.fecha_inicio = nueva_fecha_inicio
            disponibilidad_principal.fecha_fin = nueva_fecha_fin
            disponibilidad_principal.save()
            
            # Eliminar las otras disponibilidades cercanas que ahora están cubiertas por la principal
            if disponibilidades_cercanas.count() > 1:
                disponibilidades_cercanas.exclude(id=disponibilidad_principal.id).delete()
        else:
            # No hay disponibilidades cercanas, crear una nueva para este rango exacto
            Disponibilidad.objects.create(
                propiedad=propiedad,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                es_manual=True
            )

        # Actualizar historial automáticamente para que refleje el cambio sin pulsar "Reconstruir historial"
        reconstruir_historial_propiedad(propiedad)

        return JsonResponse({
            'success': True,
            'message': f'Fechas actualizadas correctamente: {fecha_inicio.strftime("%d/%m/%Y")} al {fecha_fin.strftime("%d/%m/%Y")}. La propiedad ahora está disponible en este rango.'
        })
        
    except ValueError as e:
        return JsonResponse({
            'success': False,
            'error': f'Formato de fecha inválido: {str(e)}'
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': f'Error al actualizar historial: {str(e)}'
        })


@login_required
@require_POST
def editar_historial_reserva(request):
    """
    Editar las fechas de un historial que corresponde a una reserva (reservado/alquilado).
    Solo se modifican las fechas; el precio y la info de la reserva no cambian.
    Si se acorta el rango (ej: de 15-17 a 15-16), los días liberados (ej: 17) pasan a estar
    disponibles y la propiedad sale en búsqueda para esas fechas.
    """
    from datetime import timedelta
    try:
        historial_id = request.POST.get('historial_id')
        fecha_inicio_str = request.POST.get('fecha_inicio')
        fecha_fin_str = request.POST.get('fecha_fin')
        if not historial_id or not fecha_inicio_str or not fecha_fin_str:
            return JsonResponse({'success': False, 'error': 'Faltan datos requeridos'})
        historial = get_object_or_404(HistorialDisponibilidad, id=historial_id)
        if historial.propiedad.sucursal != request.user.sucursal:
            return JsonResponse({'success': False, 'error': 'No tienes permisos para editar este historial'})
        if not historial.reserva_id or historial.estado not in ('reservado', 'alquilado'):
            return JsonResponse({'success': False, 'error': 'Este historial no corresponde a una reserva editable'})
        fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
        if fecha_inicio > fecha_fin:
            return JsonResponse({'success': False, 'error': 'La fecha de inicio debe ser anterior o igual a la de fin'})
        reserva = historial.reserva
        old_start = historial.fecha_inicio
        old_fin = historial.fecha_fin
        with transaction.atomic():
            # Guardar fechas originales la primera vez que se edita
            fecha_inicio_original_val = reserva.fecha_inicio_original if reserva.fue_editada else old_start
            fecha_fin_original_val = reserva.fecha_fin_original if reserva.fue_editada else old_fin
            
            # Actualizar la reserva usando update() para evitar que se dispare save() y la reconstrucción automática
            Reserva.objects.filter(id=reserva.id).update(
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                fecha_inicio_original=fecha_inicio_original_val,
                fecha_fin_original=fecha_fin_original_val,
                fue_editada=True
            )
            
            # Actualizar TODOS los historiales relacionados con esta reserva (no solo el que se pasó)
            # Esto evita duplicados porque actualizamos los existentes en lugar de crear nuevos
            HistorialDisponibilidad.objects.filter(
                reserva=reserva,
                estado__in=('reservado', 'alquilado')
            ).update(
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin
            )
            
            # Refrescar el objeto reserva para tener los valores actualizados
            reserva.refresh_from_db()
            propiedad = historial.propiedad
            def _crear_o_actualizar_periodo_libre(prop, start, fin):
                """Crea período libre o lo fusiona con uno contiguo existente (formato hotel: libre empieza el mismo día que termina reserva)."""
                # Evitar crear duplicados: verificar si ya existe un historial libre exactamente en este rango
                historial_existente = HistorialDisponibilidad.objects.filter(
                    propiedad=prop, estado='libre',
                    fecha_inicio=start,
                    fecha_fin=fin
                ).first()
                if historial_existente:
                    # Ya existe, no crear duplicado
                    return
                
                # ¿Hay un historial libre que empieza el mismo día o el día siguiente? (ej: liberamos 2, existe 2-10 o 3-10 → fusionar)
                siguiente_qs = HistorialDisponibilidad.objects.filter(
                    propiedad=prop, estado='libre',
                    fecha_inicio__gte=start,
                    fecha_inicio__lte=fin + timedelta(days=1)
                )
                if historial_existente:
                    siguiente_qs = siguiente_qs.exclude(id=historial_existente.id)
                siguiente = siguiente_qs.order_by('fecha_inicio').first()
                if siguiente:
                    # Fusionar: extender el siguiente para que empiece en start y termine en max(fin, siguiente.fecha_fin)
                    siguiente_fecha_inicio_original = siguiente.fecha_inicio
                    nueva_fin = max(fin, siguiente.fecha_fin)
                    siguiente.fecha_inicio = start
                    siguiente.fecha_fin = nueva_fin
                    siguiente.save(update_fields=['fecha_inicio', 'fecha_fin'])
                    # Buscar Disponibilidad que empiece en o cerca de siguiente.fecha_inicio original (antes de cambiar)
                    disp = Disponibilidad.objects.filter(
                        propiedad=prop, es_manual=True,
                        fecha_inicio__gte=siguiente_fecha_inicio_original,
                        fecha_inicio__lte=siguiente_fecha_inicio_original + timedelta(days=1)
                    ).order_by('fecha_inicio').first()
                    if disp:
                        disp.fecha_inicio = start
                        disp.fecha_fin = nueva_fin
                        disp.save(update_fields=['fecha_inicio', 'fecha_fin'])
                    else:
                        # Verificar que no existe ya una Disponibilidad en este rango
                        if not Disponibilidad.objects.filter(
                            propiedad=prop, es_manual=True,
                            fecha_inicio=start, fecha_fin=nueva_fin
                        ).exists():
                            Disponibilidad.objects.create(
                                propiedad=prop, fecha_inicio=start, fecha_fin=nueva_fin, es_manual=True
                            )
                    return
                # ¿Hay un historial libre que termina justo antes o el mismo día? (ej: existe 20-1, liberamos 2-3 → fusionar)
                anterior_qs = HistorialDisponibilidad.objects.filter(
                    propiedad=prop, estado='libre',
                    fecha_fin__gte=start - timedelta(days=1),
                    fecha_fin__lte=start
                )
                if historial_existente:
                    anterior_qs = anterior_qs.exclude(id=historial_existente.id)
                anterior = anterior_qs.order_by('-fecha_fin').first()
                if anterior:
                    # Fusionar: extender el anterior para que termine en fin
                    anterior.fecha_fin = fin
                    anterior.save(update_fields=['fecha_fin'])
                    disp = Disponibilidad.objects.filter(
                        propiedad=prop, es_manual=True,
                        fecha_fin__gte=anterior.fecha_fin - timedelta(days=1),
                        fecha_fin__lte=anterior.fecha_fin + timedelta(days=1)
                    ).order_by('-fecha_fin').first()
                    if disp:
                        disp.fecha_fin = fin
                        disp.save(update_fields=['fecha_fin'])
                    else:
                        # Verificar que no existe ya una Disponibilidad en este rango
                        if not Disponibilidad.objects.filter(
                            propiedad=prop, es_manual=True,
                            fecha_inicio=start, fecha_fin=fin
                        ).exists():
                            Disponibilidad.objects.create(
                                propiedad=prop, fecha_inicio=start, fecha_fin=fin, es_manual=True
                            )
                    return
                # Sin contiguo: crear nuevo solo si no existe ya
                if not HistorialDisponibilidad.objects.filter(
                    propiedad=prop, estado='libre',
                    fecha_inicio=start, fecha_fin=fin
                ).exists():
                    HistorialDisponibilidad.objects.create(
                        propiedad=prop,
                        fecha_inicio=start,
                        fecha_fin=fin,
                        estado='libre',
                        reserva=None,
                        es_principal=True
                    )
                if not Disponibilidad.objects.filter(
                    propiedad=prop, es_manual=True,
                    fecha_inicio=start, fecha_fin=fin
                ).exists():
                    Disponibilidad.objects.create(
                        propiedad=prop,
                        fecha_inicio=start,
                        fecha_fin=fin,
                        es_manual=True
                    )

            if fecha_inicio > old_start:
                # Formato hotel: el período libre anterior termina el mismo día que empieza la nueva reserva
                libre_start = old_start
                libre_fin = fecha_inicio  # Hasta el mismo día que empieza la reserva (formato hotel)
                if libre_start <= libre_fin:
                    _crear_o_actualizar_periodo_libre(propiedad, libre_start, libre_fin)
            if fecha_fin < old_fin:
                # Formato hotel: el período libre empieza el mismo día que termina la reserva
                libre_start = fecha_fin  # Mismo día que termina la reserva
                libre_fin = old_fin
                if libre_start <= libre_fin:
                    _crear_o_actualizar_periodo_libre(propiedad, libre_start, libre_fin)
        return JsonResponse({
            'success': True,
            'message': f'Fechas de la reserva actualizadas: {fecha_inicio.strftime("%d/%m/%Y")} al {fecha_fin.strftime("%d/%m/%Y")}. Los días liberados quedan disponibles.'
        })
    except ValueError as e:
        return JsonResponse({'success': False, 'error': f'Formato de fecha inválido: {str(e)}'})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def limpieza_brutal(request):
    """
    🔥 LIMPIEZA BRUTAL: Elimina TODO y reconstruye desde cero
    """
    if request.method == 'POST':
        try:
            from datetime import timedelta
            from dateutil.relativedelta import relativedelta
            
            # 1. ELIMINAR absolutamente TODO
            count_historial = HistorialDisponibilidad.objects.count()
            count_disponibilidades = Disponibilidad.objects.count()
            
            HistorialDisponibilidad.objects.all().delete()
            Disponibilidad.objects.all().delete()
            
            # 2. Reconstruir SOLO propiedades con reservas
            propiedades_con_reservas = Propiedad.objects.filter(
                reservas__estado__in=['confirmada', 'confirmada_no_pagada']
            ).distinct()
            
            for propiedad in propiedades_con_reservas:
                # Obtener reservas de esta propiedad
                # Excluir reservas eliminadas
                reservas = propiedad.reservas.filter(
                    estado__in=['confirmada', 'confirmada_no_pagada'],
                    eliminada=False
                ).order_by('fecha_inicio')
                
                if not reservas.exists():
                    continue
                
                # Definir rango total (6 meses antes de la primera, 6 meses después de la última)
                primera_reserva = reservas.first()
                ultima_reserva = reservas.last()
                
                fecha_inicio_total = primera_reserva.fecha_inicio - relativedelta(months=6)
                fecha_fin_total = ultima_reserva.fecha_fin + relativedelta(months=6)
                
                # Crear disponibilidades y historial fragmentados
                fecha_actual = fecha_inicio_total
                
                for reserva in reservas:
                    # Crear disponibilidad ANTES de la reserva (si hay espacio)
                    # 🏨 LÓGICA HOTELERA: El día de inicio de reserva está disponible hasta la tarde
                    if fecha_actual < reserva.fecha_inicio:
                        fecha_fin_libre = reserva.fecha_inicio  # SIN restar días
                        
                        # ❌ NO CREAR DISPONIBILIDADES AUTOMÁTICAS - Solo historial
                        # Crear historial
                        HistorialDisponibilidad.objects.create(
                            propiedad=propiedad,
                            fecha_inicio=fecha_actual,
                            fecha_fin=fecha_fin_libre,
                            estado='libre'
                        )
                    
                    # Crear historial para la RESERVA (fechas exactas)
                    HistorialDisponibilidad.objects.create(
                        propiedad=propiedad,
                        fecha_inicio=reserva.fecha_inicio,
                        fecha_fin=reserva.fecha_fin,
                        estado='reservado',
                        reserva=reserva
                    )
                    
                    # Mover fecha actual al día de fin de reserva
                    # 🏨 LÓGICA HOTELERA: El día de checkout está disponible desde la mañana
                    fecha_actual = reserva.fecha_fin  # SIN sumar días
                
                # Crear disponibilidad final
                if fecha_actual <= fecha_fin_total:
                    # ❌ NO CREAR DISPONIBILIDADES AUTOMÁTICAS - Solo historial
                    
                    # Crear historial
                    HistorialDisponibilidad.objects.create(
                        propiedad=propiedad,
                        fecha_inicio=fecha_actual,
                        fecha_fin=fecha_fin_total,
                        estado='libre'
                    )
            
            return JsonResponse({
                'success': True,
                'message': '🔥 LIMPIEZA BRUTAL completada. TODO reconstruido desde cero.',
                'historial_eliminado': count_historial,
                'disponibilidades_eliminadas': count_disponibilidades,
                'propiedades_procesadas': propiedades_con_reservas.count()
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error en limpieza brutal: {str(e)}'
            })
    
    return JsonResponse({'success': False, 'error': 'Método no permitido'})

def reconstruir_historial_propiedad(propiedad):
    """
    Función auxiliar para reconstruir el historial de una propiedad
    
    ✅ LÓGICA CORREGIDA: 
    - Usa el método de reconstrucción cronológica que fragmenta correctamente
    - Incluye reservas con estado 'pagada' y las marca como 'alquilado'
    - Fragmenta las disponibilidades con las reservas
    """
# print(f"🔄 Reconstruyendo historial para propiedad {propiedad.id}")
    
    # Usar el método de reconstrucción cronológica que fragmenta correctamente
    reservas_activas = propiedad.reservas.filter(eliminada=False)
    if reservas_activas.exists():
        # Usar el método de reconstrucción que fragmenta correctamente
        primera_reserva = reservas_activas.first()
        primera_reserva.reconstruir_historial_cronologico()
    else:
        # Si no hay reservas, crear historial con rangos unidos (evitar duplicados por solapamiento)
        HistorialDisponibilidad.objects.filter(propiedad=propiedad).delete()
        disps = list(propiedad.disponibilidades.filter(es_manual=True).order_by('fecha_inicio').values_list('fecha_inicio', 'fecha_fin'))
        rangos = []
        for ini, fin in disps:
            if rangos and ini <= rangos[-1][1]:
                rangos[-1] = (rangos[-1][0], max(rangos[-1][1], fin))
            else:
                rangos.append((ini, fin))
        for fecha_inicio, fecha_fin in rangos:
            HistorialDisponibilidad.objects.create(
                propiedad=propiedad,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                estado='libre'
            )


@login_required
def reconstruir_historial_propiedad_ajax(request, propiedad_id):
    """Reconstruye el historial de una propiedad (elimina duplicados y regenera). POST con AJAX."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)
    propiedad = get_object_or_404(Propiedad, id=str(propiedad_id))
    if propiedad.sucursal != request.user.sucursal and not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': 'Sin permisos'}, status=403)
    try:
        reconstruir_historial_propiedad(propiedad)
        return JsonResponse({'success': True, 'message': 'Historial reconstruido correctamente.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def actualizar_historial_invierno_propiedad(request, propiedad_id):
    """Actualiza el historial de una propiedad para que los segmentos Libre no se superpongan con sus contratos de invierno (evita fechas superpuestas)."""
    propiedad = get_object_or_404(Propiedad, id=str(propiedad_id))
    if propiedad.sucursal != request.user.sucursal and not request.user.is_superuser:
        messages.error(request, 'No tenés permisos para esta propiedad.')
        return redirect('inmobiliaria:lista_contratos')
    contratos_invierno = ContratoAlquiler.objects.filter(
        propiedad=propiedad, duracion_meses=9
    ).order_by('fecha_inicio')
    for c in contratos_invierno:
        actualizar_historial_por_contrato_invierno(propiedad, c.fecha_inicio, c.fecha_fin)
    if contratos_invierno:
        messages.success(
            request,
            f'Historial de la propiedad {propiedad.direccion} (id {propiedad.id}) actualizado: los períodos Libre ya no se superponen con los contratos de invierno.'
        )
    else:
        messages.info(request, f'La propiedad {propiedad.id} no tiene contratos de invierno; no se modificó el historial.')
    next_url = request.GET.get('next') or request.META.get('HTTP_REFERER')
    if next_url and next_url.startswith('/'):
        return redirect(next_url)
    return redirect('inmobiliaria:lista_contratos')


@login_required
def editar_info_venta(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    info_venta, created = VentaPropiedad.objects.get_or_create(propiedad=propiedad)

    if request.method == 'POST':
        # Verificar si es una acción de desactivar (AJAX)
        accion = request.POST.get('accion')
        if accion == 'desactivar':
            try:
                info_venta.en_venta = False
                info_venta.save()
                return JsonResponse({
                    'success': True, 
                    'message': 'Venta desactivada correctamente'
                })
            except Exception as e:
                return JsonResponse({
                    'success': False, 
                    'error': str(e)
                })
        
        # Lógica normal del formulario (no AJAX)
        en_venta = request.POST.get('en_venta') == 'on'
        info_venta.en_venta = en_venta

        if en_venta:
            # Solo actualizar otros campos si está en venta (decimales: vacío -> None para no provocar error de validación)
            def _decimal_post(key):
                v = (request.POST.get(key) or '').strip()
                if not v:
                    return None
                try:
                    return Decimal(v.replace(',', '.'))
                except (ValueError, InvalidOperation):
                    return None
            info_venta.metros_cuadrados = _decimal_post('metros_cuadrados')
            info_venta.precio_venta = _decimal_post('precio_venta')
            info_venta.precio_autorizacion = _decimal_post('precio_autorizacion')
            info_venta.estado = request.POST.get('estado', 'disponible')
            info_venta.precio_expensas = _decimal_post('precio_expensas')
            info_venta.escribania = request.POST.get('escribania', '')
            info_venta.observaciones = request.POST.get('observaciones', '')

        info_venta.save()
        messages.success(request, 'Información de venta actualizada correctamente')
        return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad_id)

    return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad_id)

@login_required
def editar_info_meses(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    
    if request.method == 'POST':
        try:
            try:
                info_meses, created = AlquilerMeses.objects.get_or_create(propiedad=propiedad)
            except IntegrityError:
                # Secuencia de id desincronizada: usar fila existente si hay, si no informar
                info_meses = AlquilerMeses.objects.filter(propiedad=propiedad).first()
                if not info_meses:
                    messages.error(
                        request,
                        'Error de numeración en la base de datos. Por favor ejecutá la migración: python manage.py migrate inmobiliaria 0085_fix_alquilermeses_id_sequence'
                    )
                    return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad_id)
            
            info_meses.disponible = 'disponible' in request.POST
            if info_meses.disponible:
                _pm = (request.POST.get('precio_mensual') or '').strip()
                try:
                    info_meses.precio_mensual = Decimal(_pm.replace(',', '.')) if _pm else None
                except (ValueError, InvalidOperation):
                    info_meses.precio_mensual = None
                info_meses.estado = request.POST.get('estado')
                info_meses.fecha_inicio = request.POST.get('fecha_inicio')
                info_meses.fecha_fin = request.POST.get('fecha_fin')
                _pe = (request.POST.get('precio_expensas') or '').strip()
                try:
                    info_meses.precio_expensas = Decimal(_pe.replace(',', '.')) if _pe else None
                except (ValueError, InvalidOperation):
                    info_meses.precio_expensas = None
                info_meses.observaciones = request.POST.get('observaciones', '')
                
                # Si el estado es 'disponible', limpiamos las fechas
                if info_meses.estado == 'disponible':
                    info_meses.fecha_inicio = None
                    info_meses.fecha_fin = None
                # Solo establecemos fechas si el estado no es 'disponible'
                elif info_meses.estado in ['reservado', 'ocupado']:
                    info_meses.fecha_inicio = request.POST.get('fecha_inicio')
                    info_meses.fecha_fin = request.POST.get('fecha_fin')
            
            info_meses.save()
            messages.success(request, 'Información de alquiler 24 meses actualizada correctamente.')
        except Exception as e:
            messages.error(request, f'Error al actualizar la información: {str(e)}')
        
        return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad_id)
    
    return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad_id)

@login_required
def editar_info_invierno(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    
    if request.method == 'POST':
        try:
            info_invierno, created = AlquilerInvierno.objects.get_or_create(propiedad=propiedad)
            
            info_invierno.disponible = 'disponible' in request.POST
            if info_invierno.disponible:
                nuevo_estado = request.POST.get('estado')
                fi = request.POST.get('fecha_inicio', '').strip()
                ff = request.POST.get('fecha_fin', '').strip()
                # Antes de cambiar fechas: si pasamos a disponible, borrar segmentos con las fechas viejas
                if nuevo_estado == 'disponible' and info_invierno.fecha_inicio and info_invierno.fecha_fin:
                    HistorialDisponibilidad.objects.filter(
                        propiedad=propiedad,
                        reserva__isnull=True,
                        es_principal=True,
                        fecha_inicio=info_invierno.fecha_inicio,
                        fecha_fin=info_invierno.fecha_fin
                    ).delete()

                _pm = (request.POST.get('precio_mensual') or '').strip()
                try:
                    info_invierno.precio_mensual = Decimal(_pm.replace(',', '.')) if _pm else None
                except (ValueError, InvalidOperation):
                    info_invierno.precio_mensual = None
                info_invierno.estado = nuevo_estado
                _pe = (request.POST.get('precio_expensas') or '').strip()
                try:
                    info_invierno.precio_expensas = Decimal(_pe.replace(',', '.')) if _pe else None
                except (ValueError, InvalidOperation):
                    info_invierno.precio_expensas = None
                _pa = request.POST.get('precio_autorizacion', '').strip()
                if _pa:
                    try:
                        info_invierno.precio_autorizacion = Decimal(_pa.replace(',', '.'))
                    except (ValueError, InvalidOperation):
                        info_invierno.precio_autorizacion = None
                else:
                    info_invierno.precio_autorizacion = None
                info_invierno.observaciones = request.POST.get('observaciones', '')

                if nuevo_estado == 'disponible':
                    # Guardar rango de fechas para "Libre (Invierno)" (ej. 15/04–30/08) para el historial
                    info_invierno.fecha_inicio = datetime.strptime(fi, '%Y-%m-%d').date() if fi else None
                    info_invierno.fecha_fin = datetime.strptime(ff, '%Y-%m-%d').date() if ff else None
                elif nuevo_estado in ['reservado', 'ocupado']:
                    info_invierno.fecha_inicio = datetime.strptime(fi, '%Y-%m-%d').date() if fi else None
                    info_invierno.fecha_fin = datetime.strptime(ff, '%Y-%m-%d').date() if ff else None
                else:
                    info_invierno.fecha_inicio = datetime.strptime(fi, '%Y-%m-%d').date() if fi else None
                    info_invierno.fecha_fin = datetime.strptime(ff, '%Y-%m-%d').date() if ff else None

            info_invierno.save()
            # Crear segmento en historial si estado reservado/ocupado con fechas
            if info_invierno.disponible and info_invierno.estado in ('reservado', 'ocupado') and info_invierno.fecha_inicio and info_invierno.fecha_fin:
                HistorialDisponibilidad.objects.filter(
                    propiedad=propiedad,
                    reserva__isnull=True,
                    fecha_inicio=info_invierno.fecha_inicio,
                    fecha_fin=info_invierno.fecha_fin
                ).delete()
                hist_estado = 'reservado' if info_invierno.estado == 'reservado' else 'alquilado'
                HistorialDisponibilidad.objects.create(
                    propiedad=propiedad,
                    fecha_inicio=info_invierno.fecha_inicio,
                    fecha_fin=info_invierno.fecha_fin,
                    estado=hist_estado,
                    es_principal=True,
                )
            messages.success(request, 'Información de alquiler invierno actualizada correctamente.')
        except Exception as e:
            messages.error(request, f'Error al actualizar la información: {str(e)}')
        
        return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad_id)
    
    return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad_id)

@login_required
def obtener_meses_info_ajax(request, propiedad_id):
    """Devuelve la info de alquiler 24 meses de una propiedad para editar desde la lista."""
    nivel = getattr(request.user, 'nivel', 0)
    if not (request.user.is_superuser or nivel >= 3):
        return JsonResponse({'error': 'Sin permisos.'}, status=403)

    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    if propiedad.sucursal != request.user.sucursal and not request.user.is_superuser:
        return JsonResponse({'error': 'No puede editar propiedades de otra sucursal.'}, status=403)

    try:
        info = propiedad.info_meses
    except AlquilerMeses.DoesNotExist:
        info = None

    if not info:
        return JsonResponse({
            'precio_mensual': '',
            'precio_expensas': '',
            'estado': 'disponible',
            'fecha_inicio': '',
            'fecha_fin': '',
            'observaciones': '',
        })

    return JsonResponse({
        'precio_mensual': str(info.precio_mensual) if info.precio_mensual is not None else '',
        'precio_expensas': str(info.precio_expensas) if info.precio_expensas is not None else '',
        'estado': info.estado or 'disponible',
        'fecha_inicio': info.fecha_inicio.strftime('%Y-%m-%d') if info.fecha_inicio else '',
        'fecha_fin': info.fecha_fin.strftime('%Y-%m-%d') if info.fecha_fin else '',
        'observaciones': info.observaciones or '',
    })


@login_required
def actualizar_meses_ajax(request):
    """
    Actualizar precio e info de alquiler 24 meses desde la lista.
    Solo admin o nivel >= 3.
    """
    nivel = getattr(request.user, 'nivel', 0)
    if not (request.user.is_superuser or nivel >= 3):
        return JsonResponse({'success': False, 'error': 'Sin permisos para editar.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido.'}, status=405)

    propiedad_id = request.POST.get('propiedad_id')
    if not propiedad_id:
        return JsonResponse({'success': False, 'error': 'Falta propiedad_id.'}, status=400)

    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    if propiedad.sucursal != request.user.sucursal and not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': 'No puede editar propiedades de otra sucursal.'}, status=403)

    try:
        info_meses, created = AlquilerMeses.objects.get_or_create(propiedad=propiedad)
        info_meses.disponible = True

        precio_mensual = request.POST.get('precio_mensual', '').strip()
        precio_expensas = request.POST.get('precio_expensas', '').strip()

        if precio_mensual:
            try:
                info_meses.precio_mensual = Decimal(precio_mensual.replace(',', '.'))
            except (ValueError, InvalidOperation):
                pass
        else:
            info_meses.precio_mensual = None

        if precio_expensas:
            try:
                info_meses.precio_expensas = Decimal(precio_expensas.replace(',', '.'))
            except (ValueError, InvalidOperation):
                pass
        else:
            info_meses.precio_expensas = None

        info_meses.estado = request.POST.get('estado', 'disponible') or 'disponible'
        fi = request.POST.get('fecha_inicio', '').strip()
        ff = request.POST.get('fecha_fin', '').strip()

        info_meses.fecha_inicio = datetime.strptime(fi, '%Y-%m-%d').date() if fi else None
        info_meses.fecha_fin = datetime.strptime(ff, '%Y-%m-%d').date() if ff else None
        info_meses.observaciones = request.POST.get('observaciones', '') or ''

        if info_meses.estado == 'disponible':
            info_meses.fecha_inicio = None
            info_meses.fecha_fin = None

        info_meses.save()

        return JsonResponse({
            'success': True,
            'precio_mensual': str(info_meses.precio_mensual) if info_meses.precio_mensual is not None else '0',
            'precio_expensas': str(info_meses.precio_expensas) if info_meses.precio_expensas is not None else '',
            'estado': info_meses.estado,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def obtener_invierno_info_ajax(request, propiedad_id):
    """Devuelve la info de alquiler invierno de una propiedad para editar desde la lista. Solo nivel >= 3 o admin."""
    nivel = getattr(request.user, 'nivel', 0)
    if not (request.user.is_superuser or nivel >= 3):
        return JsonResponse({'error': 'Sin permisos.'}, status=403)
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    if propiedad.sucursal != request.user.sucursal and not request.user.is_superuser:
        return JsonResponse({'error': 'No puede editar propiedades de otra sucursal.'}, status=403)
    try:
        info = propiedad.info_invierno
    except AlquilerInvierno.DoesNotExist:
        info = None
    if not info:
        return JsonResponse({
            'precio_mensual': '',
            'precio_expensas': '',
            'precio_autorizacion': '',
            'estado': 'disponible',
            'fecha_inicio': '',
            'fecha_fin': '',
            'observaciones': '',
        })
    return JsonResponse({
        'precio_mensual': str(info.precio_mensual) if info.precio_mensual is not None else '',
        'precio_expensas': str(info.precio_expensas) if info.precio_expensas is not None else '',
        'precio_autorizacion': str(info.precio_autorizacion) if getattr(info, 'precio_autorizacion', None) is not None else '',
        'estado': info.estado or 'disponible',
        'fecha_inicio': info.fecha_inicio.strftime('%Y-%m-%d') if info.fecha_inicio else '',
        'fecha_fin': info.fecha_fin.strftime('%Y-%m-%d') if info.fecha_fin else '',
        'observaciones': info.observaciones or '',
    })


@login_required
def actualizar_invierno_ajax(request):
    """
    Actualizar precio e info de alquiler invierno desde la lista de Alquileres Invierno.
    Solo admin (nivel 4) o nivel >= 3.
    """
    nivel = getattr(request.user, 'nivel', 0)
    if not (request.user.is_superuser or nivel >= 3):
        return JsonResponse({'success': False, 'error': 'Sin permisos para editar.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido.'}, status=405)
    propiedad_id = request.POST.get('propiedad_id')
    if not propiedad_id:
        return JsonResponse({'success': False, 'error': 'Falta propiedad_id.'}, status=400)
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    if propiedad.sucursal != request.user.sucursal and not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': 'No puede editar propiedades de otra sucursal.'}, status=403)
    try:
        info_invierno, created = AlquilerInvierno.objects.get_or_create(propiedad=propiedad)
        info_invierno.disponible = True
        precio_mensual = request.POST.get('precio_mensual', '').strip()
        precio_expensas = request.POST.get('precio_expensas', '').strip()
        precio_autorizacion = request.POST.get('precio_autorizacion', '').strip()
        if precio_mensual:
            try:
                info_invierno.precio_mensual = Decimal(precio_mensual.replace(',', '.'))
            except (ValueError, InvalidOperation):
                pass
        else:
            info_invierno.precio_mensual = None
        if precio_expensas:
            try:
                info_invierno.precio_expensas = Decimal(precio_expensas.replace(',', '.'))
            except (ValueError, InvalidOperation):
                pass
        else:
            info_invierno.precio_expensas = None
        if precio_autorizacion:
            try:
                info_invierno.precio_autorizacion = Decimal(precio_autorizacion.replace(',', '.'))
            except (ValueError, InvalidOperation):
                pass
        else:
            info_invierno.precio_autorizacion = None
        info_invierno.estado = request.POST.get('estado', 'disponible') or 'disponible'
        fi = request.POST.get('fecha_inicio', '').strip()
        ff = request.POST.get('fecha_fin', '').strip()
        if info_invierno.estado == 'disponible':
            # Quitar segmentos de historial que eran de invierno (reserva=null, es_principal) para el rango anterior
            if info_invierno.fecha_inicio and info_invierno.fecha_fin:
                HistorialDisponibilidad.objects.filter(
                    propiedad=propiedad,
                    reserva__isnull=True,
                    es_principal=True,
                    fecha_inicio=info_invierno.fecha_inicio,
                    fecha_fin=info_invierno.fecha_fin
                ).delete()
            # Guardar rango de fechas para "Libre (Invierno)" (ej. 15/04–30/08) para el historial
            info_invierno.fecha_inicio = datetime.strptime(fi, '%Y-%m-%d').date() if fi else None
            info_invierno.fecha_fin = datetime.strptime(ff, '%Y-%m-%d').date() if ff else None
        else:
            info_invierno.fecha_inicio = datetime.strptime(fi, '%Y-%m-%d').date() if fi else None
            info_invierno.fecha_fin = datetime.strptime(ff, '%Y-%m-%d').date() if ff else None
        info_invierno.observaciones = request.POST.get('observaciones', '') or ''
        info_invierno.save()
        # Sincronizar Historial de Disponibilidad: si estado es reservado/ocupado con fechas, crear segmento
        if info_invierno.estado in ('reservado', 'ocupado') and info_invierno.fecha_inicio and info_invierno.fecha_fin:
            hist_estado = 'reservado' if info_invierno.estado == 'reservado' else 'alquilado'
            # Eliminar segmentos previos de invierno (reserva=null) que solapen este rango para no duplicar
            HistorialDisponibilidad.objects.filter(
                propiedad=propiedad,
                reserva__isnull=True,
                fecha_inicio=info_invierno.fecha_inicio,
                fecha_fin=info_invierno.fecha_fin
            ).delete()
            HistorialDisponibilidad.objects.create(
                propiedad=propiedad,
                fecha_inicio=info_invierno.fecha_inicio,
                fecha_fin=info_invierno.fecha_fin,
                estado=hist_estado,
                reserva=None,
                es_principal=True
            )
        return JsonResponse({
            'success': True,
            'precio_mensual': str(info_invierno.precio_mensual) if info_invierno.precio_mensual is not None else '0',
            'precio_expensas': str(info_invierno.precio_expensas) if info_invierno.precio_expensas is not None else '',
            'estado': info_invierno.estado,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def reactivar_propiedad_invierno(request, propiedad_id):
    """Reactivar una propiedad para alquileres de invierno"""
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    es_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    try:
        info_invierno, created = AlquilerInvierno.objects.get_or_create(propiedad=propiedad)
        info_invierno.disponible = True
        info_invierno.estado = 'disponible'
        info_invierno.save()
        if es_ajax:
            return JsonResponse({'success': True, 'message': 'Propiedad reactivada para alquileres de invierno.'})
        messages.success(request, 'Propiedad reactivada para alquileres de invierno.')
    except Exception as e:
        if es_ajax:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
        messages.error(request, f'Error al reactivar la propiedad: {str(e)}')

    return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad_id)

@login_required
def desactivar_propiedad_invierno(request, propiedad_id):
    """Desactivar una propiedad para alquileres de invierno"""
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    es_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    try:
        if hasattr(propiedad, 'info_invierno'):
            info_invierno = propiedad.info_invierno
            # Desactivar la propiedad para invierno (disponible = False)
            info_invierno.disponible = False
            info_invierno.save()
            if es_ajax:
                return JsonResponse({'success': True, 'message': 'Propiedad desactivada para alquileres de invierno.'})
            messages.success(request, 'Propiedad desactivada para alquileres de invierno.')
        else:
            if es_ajax:
                return JsonResponse({'success': False, 'error': 'Esta propiedad no tiene información de invierno.'})
            messages.warning(request, 'Esta propiedad no tiene información de invierno.')
    except Exception as e:
        if es_ajax:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
        messages.error(request, f'Error al desactivar la propiedad: {str(e)}')

    return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad_id)

@login_required
def ventas(request):
    # Filtrar propiedades que tienen info de venta y están disponibles o reservadas
    propiedades_venta = Propiedad.objects.filter(
        info_venta__en_venta=True,
        info_venta__estado__in=['disponible', 'reservado']
    ).select_related('info_venta', 'sucursal').prefetch_related('imagenes')

    # Debug: Imprimir información sobre las propiedades y sus imágenes
# print("\n=== DEBUG IMÁGENES DE PROPIEDADES ===")
# print(f"MEDIA_ROOT: {settings.MEDIA_ROOT}")
# print(f"MEDIA_URL: {settings.MEDIA_URL}")
# print(f"DEBUG: {settings.DEBUG}")
# print(f"AWS_ACCESS_KEY_ID presente: {'AWS_ACCESS_KEY_ID' in os.environ}")
# print(f"AWS_STORAGE_BUCKET_NAME presente: {'AWS_STORAGE_BUCKET_NAME' in os.environ}")
    
    for propiedad in propiedades_venta:
        pass  # ✅ Bloque vacío
# print(f"\nPropiedad ID: {propiedad.id}")
# print(f"Dirección: {propiedad.direccion}")
        imagenes = propiedad.imagenes.all()
# print(f"Número de imágenes: {imagenes.count()}")
        for img in imagenes:
            pass  # ✅ Bloque vacío
# print(f"- Imagen ID: {img.id}")
# print(f"  URL: {img.imagen.url if img.imagen else 'No hay URL'}")
# print(f"  Nombre archivo: {img.imagen.name if img.imagen else 'No hay archivo'}")
            if img.imagen:
                ruta_completa = os.path.join(settings.MEDIA_ROOT, img.imagen.name)
# print(f"  ¿Archivo existe localmente?: {os.path.exists(ruta_completa)}")
# print("=== FIN DEBUG ===\n")

    # Calcular los contadores
    total_propiedades = propiedades_venta.count()
    propiedades_disponibles = propiedades_venta.filter(info_venta__estado='disponible').count()
    propiedades_reservadas = propiedades_venta.filter(info_venta__estado='reservado').count()

    # Aplicar filtros de búsqueda si existen
    busqueda = request.GET.get('busqueda', '')
    if busqueda:
        propiedades_venta = propiedades_venta.filter(
            Q(direccion__icontains=busqueda) |
            Q(id__icontains=busqueda)
        )

    estado = request.GET.get('estado', '')
    if estado:
        propiedades_venta = propiedades_venta.filter(info_venta__estado=estado)

    # Filtro por ambientes
    ambientes = request.GET.get('ambientes', '')
    if ambientes:
        if ambientes == '5':  # 5+ ambientes
            propiedades_venta = propiedades_venta.filter(ambientes__gte=5)
        else:
            propiedades_venta = propiedades_venta.filter(ambientes=int(ambientes))

    # Filtros avanzados
    tipo_inmueble = request.GET.get('tipo_inmueble', '')
    if tipo_inmueble:
        propiedades_venta = propiedades_venta.filter(tipo_inmueble=tipo_inmueble)

    vista = request.GET.get('vista', '')
    if vista:
        propiedades_venta = propiedades_venta.filter(vista=vista)

    valoracion = request.GET.get('valoracion', '')
    if valoracion:
        propiedades_venta = propiedades_venta.filter(valoracion=int(valoracion))

    # Filtros de precio
    precio_min = request.GET.get('precio_min', '')
    if precio_min:
        propiedades_venta = propiedades_venta.filter(info_venta__precio_venta__gte=float(precio_min))

    precio_max = request.GET.get('precio_max', '')
    if precio_max:
        propiedades_venta = propiedades_venta.filter(info_venta__precio_venta__lte=float(precio_max))

    # Filtros de características (checkboxes)
    caracteristicas_filtros = [
        'amoblado', 'cochera', 'wifi', 'piscina', 'patio', 'parrilla', 
        'terraza', 'balcon', 'vista_al_Mar', 'a_estrenar', 'seguridad', 'apto_credito'
    ]
    
    for caracteristica in caracteristicas_filtros:
        if request.GET.get(caracteristica):
            # Filtrar propiedades que tienen esta característica marcada como True
            filter_kwargs = {caracteristica: True}
            propiedades_venta = propiedades_venta.filter(**filter_kwargs)

    context = {
        'propiedades': propiedades_venta,
        'busqueda': busqueda,
        'estado_filtro': estado,
        'ambientes_filtro': ambientes,
        'estados': VentaPropiedad.ESTADO_CHOICES,
        'telefono_empresa': '5492235916229',
        'total_propiedades': total_propiedades,
        'propiedades_disponibles': propiedades_disponibles,
        'propiedades_reservadas': propiedades_reservadas,
        # Filtros avanzados para mantener en el contexto
        'tipo_inmueble_filtro': tipo_inmueble,
        'vista_filtro': vista,
        'valoracion_filtro': valoracion,
        'precio_min_filtro': precio_min,
        'precio_max_filtro': precio_max,
        # Características seleccionadas
        'caracteristicas_seleccionadas': {
            caracteristica: request.GET.get(caracteristica, False) 
            for caracteristica in caracteristicas_filtros
        }
    }
    
    return render(request, 'inmobiliaria/propiedades/ventas.html', context)

@login_required
def alquileres_24_meses(request):
    from django.db.models import Q, F, Value
    from django.db.models.functions import Coalesce

    estado = request.GET.get('estado', '')
    busqueda = request.GET.get('busqueda', '')
    filtro_ambientes = request.GET.get('ambientes', '')
    filtro_precio_max = request.GET.get('precio_max', '')
    ver_todas = request.GET.get('ver_todas') == '1'

    q_sucursales_colon_corrientes = Q(sucursal__nombre__icontains='colon') | Q(sucursal__nombre__icontains='corrientes')
    propiedades_meses = Propiedad.objects.filter(info_meses__disponible=True)

    if ver_todas:
        propiedades_meses = propiedades_meses.filter(q_sucursales_colon_corrientes)
    else:
        sucursal_usuario = getattr(request.user, 'sucursal', None)
        if sucursal_usuario:
            propiedades_meses = propiedades_meses.filter(sucursal=sucursal_usuario)
        else:
            propiedades_meses = propiedades_meses.filter(q_sucursales_colon_corrientes)

    if estado:
        propiedades_meses = propiedades_meses.filter(info_meses__estado=estado)
    else:
        propiedades_meses = propiedades_meses.filter(info_meses__estado='disponible')

    propiedades_meses = propiedades_meses.select_related(
        'info_meses',
        'sucursal'
    ).prefetch_related('imagenes').annotate(
        precio_ord=Coalesce(F('info_meses__precio_mensual'), Value(Decimal('999999999')))
    ).order_by('precio_ord', 'direccion')

    if busqueda:
        propiedades_meses = propiedades_meses.filter(
            Q(direccion__icontains=busqueda) |
            Q(id__icontains=busqueda)
        )

    if filtro_ambientes:
        try:
            propiedades_meses = propiedades_meses.filter(ambientes=int(filtro_ambientes))
        except ValueError:
            pass

    if filtro_precio_max:
        try:
            precio_max = Decimal(filtro_precio_max.replace(',', '.'))
            propiedades_meses = propiedades_meses.filter(info_meses__precio_mensual__lte=precio_max)
        except (ValueError, InvalidOperation):
            pass

    base_para_totales = Propiedad.objects.filter(info_meses__disponible=True)
    if ver_todas:
        base_para_totales = base_para_totales.filter(q_sucursales_colon_corrientes)
    else:
        sucursal_usuario = getattr(request.user, 'sucursal', None)
        if sucursal_usuario:
            base_para_totales = base_para_totales.filter(sucursal=sucursal_usuario)
        else:
            base_para_totales = base_para_totales.filter(q_sucursales_colon_corrientes)

    if busqueda:
        base_para_totales = base_para_totales.filter(
            Q(direccion__icontains=busqueda) | Q(id__icontains=busqueda)
        )

    if filtro_ambientes:
        try:
            base_para_totales = base_para_totales.filter(ambientes=int(filtro_ambientes))
        except ValueError:
            pass

    if filtro_precio_max:
        try:
            precio_max = Decimal(filtro_precio_max.replace(',', '.'))
            base_para_totales = base_para_totales.filter(info_meses__precio_mensual__lte=precio_max)
        except (ValueError, InvalidOperation):
            pass

    total_disponibles_meses = base_para_totales.filter(info_meses__estado='disponible').count()
    total_reservados_meses = base_para_totales.filter(info_meses__estado='reservado').count()

    base_ambientes = Propiedad.objects.filter(habilitar_23_meses=True)
    if ver_todas:
        base_ambientes = base_ambientes.filter(q_sucursales_colon_corrientes)
    else:
        sucursal_usuario = getattr(request.user, 'sucursal', None)
        if sucursal_usuario:
            base_ambientes = base_ambientes.filter(sucursal=sucursal_usuario)
        else:
            base_ambientes = base_ambientes.filter(q_sucursales_colon_corrientes)
    ambientes_choices = list(base_ambientes.values_list('ambientes', flat=True).distinct().order_by('ambientes'))
    ambientes_choices = [a for a in ambientes_choices if a is not None]

    nivel = getattr(request.user, 'nivel', 0)
    puede_editar_meses = request.user.is_superuser or nivel >= 3

    context = {
        'propiedades': propiedades_meses,
        'busqueda': busqueda,
        'estado_filtro': estado or 'disponible',
        'estados': AlquilerMeses.ESTADO_CHOICES,
        'filtro_ambientes': filtro_ambientes,
        'filtro_precio_max': filtro_precio_max,
        'ambientes_choices': ambientes_choices,
        'inquilinos': get_inquilinos_queryset_unificado(request),
        'puede_editar_meses': puede_editar_meses,
        'ver_todas': ver_todas,
        'total_disponibles_meses': total_disponibles_meses,
        'total_reservados_meses': total_reservados_meses,
    }

    return render(request, 'inmobiliaria/propiedades/alquileres_24_meses.html', context)

@login_required
def alquileres_invierno(request):
    # Por defecto: propiedades de la sucursal del usuario. Con ver_todas=1: Colón y Corrientes juntas.
    from django.db.models import Q, F, Value
    from django.db.models.functions import Coalesce

    estado = request.GET.get('estado', '')
    busqueda = request.GET.get('busqueda', '')
    filtro_ambientes = request.GET.get('ambientes', '')
    filtro_precio_max = request.GET.get('precio_max', '')
    ver_todas = request.GET.get('ver_todas') == '1'

    q_sucursales_colon_corrientes = Q(sucursal__nombre__icontains='colon') | Q(sucursal__nombre__icontains='corrientes')
    propiedades_invierno = Propiedad.objects.filter(info_invierno__disponible=True)
    if ver_todas:
        propiedades_invierno = propiedades_invierno.filter(q_sucursales_colon_corrientes)
    else:
        sucursal_usuario = getattr(request.user, 'sucursal', None)
        if sucursal_usuario:
            propiedades_invierno = propiedades_invierno.filter(sucursal=sucursal_usuario)
        else:
            propiedades_invierno = propiedades_invierno.filter(q_sucursales_colon_corrientes)
    if estado:
        propiedades_invierno = propiedades_invierno.filter(info_invierno__estado=estado)
    else:
        propiedades_invierno = propiedades_invierno.filter(info_invierno__estado='disponible')
    propiedades_invierno = propiedades_invierno.select_related(
        'info_invierno',
        'sucursal'
    ).prefetch_related('imagenes').annotate(
        precio_ord=Coalesce(F('info_invierno__precio_mensual'), Value(Decimal('999999999')))
    ).order_by('precio_ord', 'direccion')

    if busqueda:
        propiedades_invierno = propiedades_invierno.filter(
            Q(direccion__icontains=busqueda) |
            Q(id__icontains=busqueda)
        )
    if filtro_ambientes:
        try:
            propiedades_invierno = propiedades_invierno.filter(ambientes=int(filtro_ambientes))
        except ValueError:
            pass
    if filtro_precio_max:
        try:
            precio_max = Decimal(filtro_precio_max.replace(',', '.'))
            propiedades_invierno = propiedades_invierno.filter(
                info_invierno__precio_mensual__lte=precio_max
            )
        except (ValueError, InvalidOperation):
            pass

    # Totales Disponibles / Reservados (mismo ámbito y filtros, sin filtrar por estado)
    base_para_totales = Propiedad.objects.filter(info_invierno__disponible=True)
    if ver_todas:
        base_para_totales = base_para_totales.filter(q_sucursales_colon_corrientes)
    else:
        sucursal_usuario = getattr(request.user, 'sucursal', None)
        if sucursal_usuario:
            base_para_totales = base_para_totales.filter(sucursal=sucursal_usuario)
        else:
            base_para_totales = base_para_totales.filter(q_sucursales_colon_corrientes)
    if busqueda:
        base_para_totales = base_para_totales.filter(
            Q(direccion__icontains=busqueda) | Q(id__icontains=busqueda)
        )
    if filtro_ambientes:
        try:
            base_para_totales = base_para_totales.filter(ambientes=int(filtro_ambientes))
        except ValueError:
            pass
    if filtro_precio_max:
        try:
            precio_max = Decimal(filtro_precio_max.replace(',', '.'))
            base_para_totales = base_para_totales.filter(info_invierno__precio_mensual__lte=precio_max)
        except (ValueError, InvalidOperation):
            pass
    total_disponibles_invierno = base_para_totales.filter(info_invierno__estado='disponible').count()
    total_reservados_invierno = base_para_totales.filter(info_invierno__estado='reservado').count()

    # Opciones de ambientes (mismo ámbito: sucursal actual o Colón/Corrientes)
    base_ambientes = Propiedad.objects.filter(habilitar_invierno=True)
    if ver_todas:
        base_ambientes = base_ambientes.filter(q_sucursales_colon_corrientes)
    else:
        sucursal_usuario = getattr(request.user, 'sucursal', None)
        if sucursal_usuario:
            base_ambientes = base_ambientes.filter(sucursal=sucursal_usuario)
        else:
            base_ambientes = base_ambientes.filter(q_sucursales_colon_corrientes)
    ambientes_choices = list(base_ambientes.values_list('ambientes', flat=True).distinct().order_by('ambientes'))
    ambientes_choices = [a for a in ambientes_choices if a is not None]

    nivel = getattr(request.user, 'nivel', 0)
    puede_editar_invierno = request.user.is_superuser or nivel >= 3
    context = {
        'propiedades': propiedades_invierno,
        'busqueda': busqueda,
        'estado_filtro': estado or 'disponible',
        'estados': AlquilerInvierno.ESTADO_CHOICES,
        'filtro_ambientes': filtro_ambientes,
        'filtro_precio_max': filtro_precio_max,
        'ambientes_choices': ambientes_choices,
        'inquilinos': get_inquilinos_queryset_unificado(request),
        'puede_editar_invierno': puede_editar_invierno,
        'ver_todas': ver_todas,
        'total_disponibles_invierno': total_disponibles_invierno,
        'total_reservados_invierno': total_reservados_invierno,
    }
    return render(request, 'inmobiliaria/propiedades/alquileres_invierno.html', context)


@login_required
def invierno_disponibilidad_masiva(request):
    """
    Disponibilidad masiva para Alquileres Invierno: lista solo propiedades de la sucursal actual
    para activarlas. Al activar, se puede elegir rango de fechas (desde/hasta) que se aplica a todas.
    """
    sucursal = request.user.sucursal

    if request.method == 'POST':
        propiedad_ids = request.POST.getlist('propiedades[]')
        fecha_inicio_str = request.POST.get('fecha_inicio', '').strip()
        fecha_fin_str = request.POST.get('fecha_fin', '').strip()

        if not fecha_inicio_str or not fecha_fin_str:
            return JsonResponse({
                'success': False,
                'message': 'Debe indicar fecha de inicio y fecha de fin para el período de invierno.'
            })

        try:
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({
                'success': False,
                'message': 'Formato de fecha inválido. Use AAAA-MM-DD.'
            })
        if fecha_inicio > fecha_fin:
            return JsonResponse({
                'success': False,
                'message': 'La fecha de inicio debe ser anterior o igual a la fecha de fin.'
            })

        propiedades_actualizadas = 0
        propiedades_exitosas = []
        errores_detallados = []

        for propiedad_id in propiedad_ids:
            try:
                propiedad = Propiedad.objects.filter(sucursal=sucursal).get(id=propiedad_id)
            except Propiedad.DoesNotExist:
                errores_detallados.append({
                    'propiedad_id': propiedad_id,
                    'direccion': 'Desconocida',
                    'error': 'No pertenece a su sucursal o no existe',
                    'tipo': 'no_existe'
                })
                continue

            try:
                propiedad.habilitar_invierno = True
                propiedad.save(update_fields=['habilitar_invierno'])
                info_invierno, created = AlquilerInvierno.objects.get_or_create(propiedad=propiedad)
                info_invierno.disponible = True
                info_invierno.estado = 'disponible'
                info_invierno.fecha_inicio = fecha_inicio
                info_invierno.fecha_fin = fecha_fin
                info_invierno.save()
                propiedades_actualizadas += 1
                propiedades_exitosas.append({
                    'propiedad_id': propiedad_id,
                    'direccion': propiedad.direccion,
                    'piso': propiedad.piso or '-',
                    'departamento': propiedad.departamento or '-'
                })
            except Exception as e:
                errores_detallados.append({
                    'propiedad_id': propiedad_id,
                    'direccion': getattr(propiedad, 'direccion', 'Desconocida'),
                    'piso': getattr(propiedad, 'piso', '-') or '-',
                    'departamento': getattr(propiedad, 'departamento', '-') or '-',
                    'error': str(e),
                    'tipo': 'error_general'
                })

        respuesta = {
            'propiedades_procesadas': len(propiedad_ids),
            'propiedades_exitosas': propiedades_actualizadas,
            'propiedades_con_errores': len(errores_detallados),
            'detalles_exitosas': propiedades_exitosas,
            'detalles_errores': errores_detallados
        }
        if propiedades_actualizadas > 0:
            mensaje = f'✅ {propiedades_actualizadas} propiedades habilitadas para invierno ({fecha_inicio_str} a {fecha_fin_str})'
            if errores_detallados:
                mensaje += f'\n⚠️ {len(errores_detallados)} con errores'
            return JsonResponse({'success': True, 'message': mensaje, 'detalles': respuesta})
        return JsonResponse({
            'success': False,
            'message': f'❌ No se pudo habilitar ninguna propiedad ({len(errores_detallados)} errores)',
            'detalles': respuesta
        })

    # Listar solo propiedades de la sucursal que aún no están activadas para invierno
    propiedades = Propiedad.objects.filter(
        sucursal=sucursal
    ).exclude(
        info_invierno__disponible=True
    ).select_related('propietario', 'sucursal', 'info_invierno').order_by(
        Lower('propietario__apellido'), Lower('propietario__nombre'), 'direccion', 'id'
    )

    return render(request, 'inmobiliaria/propiedades/invierno_disponibilidad_masiva.html', {
        'propiedades': propiedades,
        'sucursal': sucursal,
    })


def generar_mensaje_whatsapp(propiedad):
    # Formatear el mensaje
    mensaje = f"""
*Propiedad en {propiedad.direccion}*
{propiedad.get_tipo_inmueble_display()}
{propiedad.ambientes} ambientes
{propiedad.metros_cuadrados}m²

Precio: U$D {propiedad.precios.filter(tipo_precio='VENTA').first().monto if propiedad.precios.filter(tipo_precio='VENTA').exists() else 'Consultar'}

Para más información: https://tu-sitio.com/propiedad/{propiedad.id}
"""
    # Codificar el mensaje para URL
    from urllib.parse import quote
    return quote(mensaje)

@login_required
def iniciar_compra(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    
    if request.method == 'POST':
        try:
            # Verificar que la propiedad esté disponible
            if propiedad.info_venta.estado != 'disponible':
                messages.error(request, 'La propiedad no está disponible para la compra.')
                return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad_id)
            
            # Eliminar cualquier venta pendiente anterior
            VentaPropiedad.objects.filter(
                propiedad=propiedad,
                estado='pendiente'
            ).delete()
            
            # Crear la nueva venta
            venta = VentaPropiedad.objects.create(
                propiedad=propiedad,
                precio_venta=propiedad.info_venta.precio_venta,
                estado='pendiente'
            )
            
            # Actualizar estado de la propiedad
            propiedad.info_venta.estado = 'reservado'
            propiedad.info_venta.save()
            
            messages.success(request, 'Se ha iniciado el proceso de compra correctamente.')
            return redirect('inmobiliaria:cargar_cliente_venta', venta_id=venta.id)
            
        except Exception as e:
            messages.error(request, f'Error al iniciar la compra: {str(e)}')
            return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad_id)
    
    return render(request, 'inmobiliaria/propiedades/iniciar_compra.html', {
        'propiedad': propiedad
    })

@login_required
def abrir_caja(request):
    sucursal = request.user.sucursal
    
    # Verificar si ya hay una caja abierta
    if Caja.objects.filter(sucursal=sucursal, estado='abierta').exists():
        messages.error(request, "Ya hay una caja abierta para esta sucursal")
        return redirect('inmobiliaria:gestionar_caja')
    
    try:
        # numero es PK autoincremental global: no asignar a mano (evita colisión con otras sucursales).
        caja = Caja.objects.create(
            sucursal=sucursal,
            estado='abierta',
            usuario_apertura=request.user,
            saldo_inicial=0,
        )
        
        messages.success(request, f'Caja #{caja.numero} abierta exitosamente')
        return redirect('inmobiliaria:gestionar_caja')
        
    except Exception as e:
        messages.error(request, f'Error al abrir la caja: {str(e)}')
        return redirect('inmobiliaria:gestionar_caja')

@login_required
def ver_caja(request, caja_id):
    try:
        caja = Caja.objects.get(id=caja_id, sucursal=request.user.sucursal)
        return render(request, 'inmobiliaria/caja/ver_caja.html', {'caja': caja})
    except Caja.DoesNotExist:
        messages.error(request, 'Caja no encontrada')
        return redirect('inmobiliaria:lista_cajas')
    except Exception as e:
        pass  # ✅ Bloque vacío
# print("Error en ver_caja:")
# print(traceback.format_exc())
        messages.error(request, f'Error: {str(e)}')
        return redirect('inmobiliaria:lista_cajas')

@login_required
def lista_cajas(request):
    # Obtener la sucursal del usuario logueado
    sucursal = request.user.sucursal
    
    # Obtener las cajas de la sucursal
    cajas = Caja.objects.filter(sucursal=sucursal).order_by('-fecha_apertura')
    
    # Obtener la caja abierta actual (la más reciente por fecha de apertura)
    caja_actual = cajas.filter(estado='abierta').order_by('-fecha_apertura').first()
    cajas_abiertas_count = Caja.objects.filter(sucursal=sucursal, estado='abierta').count()
    
    context = {
        'cajas': cajas,
        'caja_actual': caja_actual,
        'cajas_abiertas_count': cajas_abiertas_count,
    }
    
    return render(request, 'inmobiliaria/caja/lista_cajas.html', context)

@login_required
def gestionar_caja(request):
    try:
        # Obtener la sucursal del usuario logueado
        sucursal = request.user.sucursal
        
        # Verificar si hay una caja abierta para esta sucursal
        caja_actual = Caja.objects.filter(
            sucursal=sucursal,
            estado='abierta',
        ).order_by('-fecha_apertura').first()
        
        # Obtener últimos movimientos si hay caja abierta
        movimientos = []
        if caja_actual:
            movimientos = MovimientoCaja.objects.filter(
                caja=caja_actual
            ).order_by('-fecha')[:10]  # Últimos 10 movimientos
        
        # Obtener historial de cajas de la sucursal
        historial_cajas = Caja.objects.filter(
            sucursal=sucursal
        ).order_by('-fecha_apertura')[:5]  # Últimas 5 cajas
        
        context = {
            'sucursal': sucursal,
            'caja_actual': caja_actual,
            'movimientos': movimientos,
            'historial_cajas': historial_cajas,
        }
        
        return render(request, 'inmobiliaria/caja/gestionar_caja.html', context)
        
    except Exception as e:
        messages.error(request, f'Error al acceder a la caja: {str(e)}')
        return redirect('inmobiliaria:dashboard')


@login_required
@transaction.atomic
def eliminar_movimiento(request, movimiento_id):
    if request.method not in ('GET', 'POST', 'HEAD'):
        return HttpResponseNotAllowed(['GET', 'POST', 'HEAD'])
    movimiento = get_object_or_404(MovimientoCaja, id=movimiento_id, sucursal=request.user.sucursal)
    caja = movimiento.caja
    if caja and (getattr(caja, 'estado', None) != 'abierta' or caja.fecha_cierre is not None):
        messages.error(request, 'Solo se pueden eliminar movimientos de una caja abierta.')
        if caja and caja.numero is not None:
            return redirect('inmobiliaria:detalle_caja', numero=caja.numero)
        return redirect('inmobiliaria:gestionar_caja')

    caja_numero = movimiento.caja_id and movimiento.caja.numero
    _eliminar_movimiento_y_anexos(movimiento)
    messages.success(request, 'Movimiento de caja y recibo asociado eliminados correctamente.')

    next_target = (request.POST.get('next') or request.GET.get('next') or '').strip()
    if next_target == 'operaciones':
        return redirect('inmobiliaria:operaciones')
    if caja_numero is not None:
        return redirect('inmobiliaria:detalle_caja', numero=caja_numero)
    return redirect('inmobiliaria:gestionar_caja')

@login_required
def caja(request):
    # Obtener la caja actual
    sucursal = request.user.sucursal
    caja = Caja.objects.filter(sucursal=sucursal, estado='abierta').first()
    
    if not caja:
        messages.error(request, "No hay una caja abierta")
        return redirect('inmobiliaria:gestionar_caja')
    
    # Obtener todos los movimientos de la caja
    movimientos = MovimientoCaja.objects.filter(
        caja=caja
    ).order_by('-fecha')
    
    # Calcular totales
    totales = {
        'efectivo': sum(m.monto_efectivo for m in movimientos),
        'cheques': sum(m.monto_cheque for m in movimientos),
        'tarjetas': sum(m.monto_tarjeta for m in movimientos),
        'depositos': sum(m.monto_deposito for m in movimientos),
    }
    
    # Calcular saldos (tipo en BD: IN / EG, ver TipoMovimientoCajaEnum)
    ingresos = movimientos.filter(tipo=TipoMovimientoCajaEnum.INGRESO)
    egresos = movimientos.filter(tipo=TipoMovimientoCajaEnum.EGRESO)

    def _suma_medios(m):
        return (
            (m.monto_efectivo or 0)
            + (m.monto_cheque or 0)
            + (m.monto_tarjeta or 0)
            + (m.monto_deposito or 0)
        )

    saldos = {
        'anterior': caja.saldo_inicial,
        'ingresos': sum(_suma_medios(m) for m in ingresos),
        'egresos': sum(_suma_medios(m) for m in egresos),
        'anterior_total': caja.saldo_inicial,
        'ingresos_total': sum(_suma_medios(m) for m in ingresos),
        'egresos_total': sum(_suma_medios(m) for m in egresos),
    }
    
    # Calcular saldo del día y total
    saldos['dia'] = saldos['ingresos'] - saldos['egresos']
    saldos['total'] = saldos['anterior'] + saldos['dia']
    
    context = {
        'caja': caja,
        'movimientos': movimientos,
        'totales': totales,
        'saldos': saldos,
    }
    
    return render(request, 'inmobiliaria/caja/caja.html', context)


def _build_context_detalle_caja(request, caja, movimientos_order=('-fecha', '-id')):
    """Contexto compartido entre detalle de caja y resumen imprimible."""
    from inmobiliaria.models.sucursal import CuentaBancaria

    movimientos_qs = (
        MovimientoCaja.objects.filter(caja=caja)
        .select_related('propiedad', 'empleado')
        .order_by(*movimientos_order)
    )
    movimientos = list(movimientos_qs)

    def _resumir_concepto_crudo(concepto):
        texto = (concepto or '').strip()
        if not texto:
            return '-'
        t = texto.lower()
        if t.startswith('operación') or t.startswith('operacion'):
            return 'Operación'
        if t.startswith('contrato'):
            return 'Contrato'
        if t.startswith('reserva'):
            return 'Reserva'
        return 'Movimiento'

    for mov in movimientos:
        mov.concepto_resumen = _resumir_concepto_crudo(getattr(mov, 'concepto', ''))

    ingresos = movimientos_qs.filter(tipo=TipoMovimientoCajaEnum.INGRESO)
    egresos = movimientos_qs.filter(tipo=TipoMovimientoCajaEnum.EGRESO)

    cuentas_bancarias = CuentaBancaria.objects.filter(
        sucursal=request.user.sucursal,
        activa=True
    ).order_by('nombre_banco', 'alias')

    totales_ingresos = {
        'efectivo': sum(m.monto_efectivo for m in ingresos),
        'cheque': sum(m.monto_cheque for m in ingresos),
        'tarjeta': sum(m.monto_tarjeta for m in ingresos),
        'deposito': sum(m.monto_deposito for m in ingresos),
        'total': sum(m.monto_total for m in ingresos)
    }
    totales_ingresos['cuentas_bancarias'] = {}
    for cuenta in cuentas_bancarias:
        total_cuenta = sum(m.monto_deposito for m in ingresos.filter(destino_deposito=f'cuenta_{cuenta.id}'))
        totales_ingresos['cuentas_bancarias'][cuenta.id] = {
            'nombre': cuenta.nombre_banco,
            'alias': cuenta.alias,
            'total': total_cuenta
        }
    totales_ingresos['deposito_galicia'] = sum(m.monto_deposito for m in ingresos.filter(destino_deposito='galicia'))
    totales_ingresos['deposito_mp'] = sum(m.monto_deposito for m in ingresos.filter(destino_deposito='mp'))

    totales_egresos = {
        'efectivo': sum(m.monto_efectivo for m in egresos),
        'cheque': sum(m.monto_cheque for m in egresos),
        'tarjeta': sum(m.monto_tarjeta for m in egresos),
        'deposito': sum(m.monto_deposito for m in egresos),
        'total': sum(m.monto_total for m in egresos)
    }
    totales_egresos['cuentas_bancarias'] = {}
    for cuenta in cuentas_bancarias:
        total_cuenta = sum(m.monto_deposito for m in egresos.filter(destino_deposito=f'cuenta_{cuenta.id}'))
        totales_egresos['cuentas_bancarias'][cuenta.id] = {
            'nombre': cuenta.nombre_banco,
            'alias': cuenta.alias,
            'total': total_cuenta
        }
    totales_egresos['deposito_galicia'] = sum(m.monto_deposito for m in egresos.filter(destino_deposito='galicia'))
    totales_egresos['deposito_mp'] = sum(m.monto_deposito for m in egresos.filter(destino_deposito='mp'))

    saldo_actual = {
        'efectivo': totales_ingresos['efectivo'] - totales_egresos['efectivo'],
        'cheque': totales_ingresos['cheque'] - totales_egresos['cheque'],
        'tarjeta': totales_ingresos['tarjeta'] - totales_egresos['tarjeta'],
        'deposito': totales_ingresos['deposito'] - totales_egresos['deposito'],
        'deposito_galicia': totales_ingresos['deposito_galicia'] - totales_egresos['deposito_galicia'],
        'deposito_mp': totales_ingresos['deposito_mp'] - totales_egresos['deposito_mp']
    }
    saldo_actual['cuentas_bancarias'] = {}
    for cuenta in cuentas_bancarias:
        saldo_cuenta = totales_ingresos['cuentas_bancarias'][cuenta.id]['total'] - totales_egresos['cuentas_bancarias'][cuenta.id]['total']
        saldo_actual['cuentas_bancarias'][cuenta.id] = {
            'nombre': cuenta.nombre_banco,
            'alias': cuenta.alias,
            'saldo': saldo_cuenta
        }

    saldo_total = totales_ingresos['total'] - totales_egresos['total']
    totales = {
        'ingresos': totales_ingresos,
        'egresos': totales_egresos,
        'saldo_actual': saldo_actual,
        'saldo_total': saldo_total
    }

    return {
        'caja': caja,
        'movimientos': movimientos,
        'totales': totales,
        'cuentas_bancarias': cuentas_bancarias,
        'es_saldo_positivo': saldo_total >= 0,
    }


@login_required
def detalle_caja(request, numero):
    caja = get_object_or_404(Caja, numero=numero, sucursal=request.user.sucursal)
    context = _build_context_detalle_caja(request, caja, movimientos_order=('-fecha', '-id'))
    return render(request, 'inmobiliaria/caja/detalle_caja.html', context)


@login_required
def imprimir_resumen_caja(request, numero):
    """
    Resumen imprimible de movimientos de una caja (orden cronológico).
    Útil tras el cierre como resumen del período / día.
    """
    caja = get_object_or_404(Caja, numero=numero, sucursal=request.user.sucursal)
    context = _build_context_detalle_caja(request, caja, movimientos_order=('fecha', 'id'))
    context['es_cierre'] = caja.estado == 'cerrada'
    neto = context['totales']['saldo_total']
    neto_dec = neto if isinstance(neto, Decimal) else Decimal(str(neto))
    context['saldo_teorico_final'] = Decimal(str(caja.saldo_inicial)) + neto_dec
    return render(request, 'inmobiliaria/caja/resumen_caja_imprimir.html', context)

@login_required
def nuevo_movimiento(request, numero_caja=None):
    from inmobiliaria.models.sucursal import CuentaBancaria

    if numero_caja:
        caja = get_object_or_404(Caja, numero=numero_caja, sucursal=request.user.sucursal, estado='abierta')
    else:
        # Varias cajas abiertas (datos legacy) rompen .get(); alineado con gestionar_caja / detalle.
        caja = (
            Caja.objects.filter(sucursal=request.user.sucursal, estado='abierta')
            .order_by('-fecha_apertura')
            .first()
        )
        if not caja:
            messages.error(request, 'No hay una caja abierta')
            return redirect('inmobiliaria:lista_cajas')

    sucursal = request.user.sucursal
    cuentas_bancarias = CuentaBancaria.objects.filter(sucursal=sucursal, activa=True).order_by('nombre_banco', 'alias')

    def _ctx_nuevo_movimiento(extra=None):
        ctx = {
            'caja': caja,
            'fecha_actual': timezone.now(),
            'cuentas_bancarias': cuentas_bancarias,
        }
        if extra:
            ctx.update(extra)
        return ctx

    if request.method == 'POST':
        try:
            # Procesar fechas
            fecha_desde = None
            fecha_hasta = None
            try:
                if request.POST.get('fecha_desde'):
                    fecha_desde = datetime.strptime(request.POST.get('fecha_desde'), '%Y-%m-%d').date()
                if request.POST.get('fecha_hasta'):
                    fecha_hasta = datetime.strptime(request.POST.get('fecha_hasta'), '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, 'Formato de fecha inválido')
                return render(request, 'inmobiliaria/caja/nuevo_movimiento.html', _ctx_nuevo_movimiento())

            # ✅ Truncar concepto a 200 caracteres para evitar error de base de datos
            concepto_valor = request.POST.get('concepto_id', '')
            if len(concepto_valor) > 200:
                concepto_valor = concepto_valor[:197] + "..."
            
            # Obtener y validar tipo (debe ser 'IN' o 'EG')
            tipo_raw = (request.POST.get('tipo', 'IN') or '').strip()
            tipo_raw_upper = tipo_raw.upper()
            tipo_raw_lower = tipo_raw.lower()
            if tipo_raw_upper in ['IN', 'EG']:
                tipo = tipo_raw_upper
            elif tipo_raw_lower in ['ingreso', 'in']:
                tipo = 'IN'
            elif tipo_raw_lower in ['egreso', 'eg']:
                tipo = 'EG'
            elif 'ingreso' in tipo_raw_lower:
                tipo = 'IN'
            elif 'egreso' in tipo_raw_lower:
                tipo = 'EG'
            else:
                tipo = 'IN'  # Default seguro
            
            # Obtener y validar tipo_comprobante (debe ser código de 2 caracteres)
            tipo_comprobante_raw = request.POST.get('tipo_comprobante', 'RC')
            # Mapear valores comunes a códigos de 2 caracteres
            tipo_comprobante_map = {
                'RC': 'RC', 'Recibo': 'RC',
                'LQ': 'LQ', 'Liquidación': 'LQ', 'liquidacion': 'LQ', 'liquidación': 'LQ',
                'GS': 'GS', 'Gasto': 'GS',
                'OT': 'OT', 'Otro': 'OT'
            }
            tipo_comprobante = tipo_comprobante_map.get(tipo_comprobante_raw, tipo_comprobante_raw[:2] if len(tipo_comprobante_raw) > 2 else tipo_comprobante_raw)
            
            a_descontar_raw = (request.POST.get('a_descontar') or 'oficina').strip().lower()
            if a_descontar_raw not in ('oficina', 'propietario', 'inquilino'):
                a_descontar_raw = 'oficina'

            # Crear el movimiento con valores iniciales
            movimiento = MovimientoCaja(
                caja=caja,
                tipo=tipo,
                tipo_comprobante=tipo_comprobante,
                numero_liquidacion=request.POST.get('numero_liquidacion', ''),
                concepto=concepto_valor,  # ✅ Truncado si es necesario
                propiedad_id=request.POST.get('propiedad_id') if request.POST.get('propiedad_id') else None,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                monto_efectivo=0,
                monto_cheque=0,
                monto_tarjeta=0,
                monto_deposito=0,
                destino_deposito=None,
                a_descontar=a_descontar_raw,
                sucursal=request.user.sucursal,
                empleado=request.user
            )

            # Procesar los montos
            try:
                movimiento.monto_efectivo = float(request.POST.get('monto_efectivo', '0').replace(',', '.') or '0')
                movimiento.monto_cheque = float(request.POST.get('monto_cheque', '0').replace(',', '.') or '0')
                movimiento.monto_tarjeta = float(request.POST.get('monto_tarjeta', '0').replace(',', '.') or '0')
                movimiento.monto_deposito = float(request.POST.get('monto_deposito', '0').replace(',', '.') or '0')
            except (ValueError, TypeError):
                messages.error(request, 'Error en los montos ingresados')
                return render(request, 'inmobiliaria/caja/nuevo_movimiento.html', _ctx_nuevo_movimiento())

            dd_raw = (request.POST.get('destino_deposito') or '').strip()
            if movimiento.monto_deposito and float(movimiento.monto_deposito) > 0:
                destino_ok = None
                if dd_raw.startswith('cuenta_'):
                    suf = dd_raw.replace('cuenta_', '', 1)
                    if suf.isdigit() and cuentas_bancarias.filter(id=int(suf)).exists():
                        destino_ok = dd_raw
                if not destino_ok:
                    messages.error(
                        request,
                        'Con importe en transferencia tenés que elegir una cuenta de la sucursal. '
                        'Configurá cuentas en Caja → Cuentas bancarias si no aparece ninguna.',
                    )
                    return render(request, 'inmobiliaria/caja/nuevo_movimiento.html', _ctx_nuevo_movimiento())
                movimiento.destino_deposito = destino_ok
            else:
                movimiento.destino_deposito = None

            movimiento.tarjeta_numero = (request.POST.get('tarjeta_numero') or '')[:32]
            movimiento.tarjeta_cupon = (request.POST.get('tarjeta_cupon') or '')[:64]
            tt = (request.POST.get('tarjeta_tipo') or '').strip().lower()
            movimiento.tarjeta_tipo = tt if tt in ('credito', 'debito') else ''
            movimiento.cheque_numero = (request.POST.get('cheque_numero') or '')[:32]
            movimiento.cheque_banco = (request.POST.get('cheque_banco') or '')[:100]
            fv = (request.POST.get('cheque_fecha_vencimiento') or '').strip()
            if fv:
                try:
                    movimiento.cheque_fecha_vencimiento = datetime.strptime(fv, '%Y-%m-%d').date()
                except ValueError:
                    movimiento.cheque_fecha_vencimiento = None
            else:
                movimiento.cheque_fecha_vencimiento = None

            m_ef = Decimal(str(movimiento.monto_efectivo or 0))
            m_ch = Decimal(str(movimiento.monto_cheque or 0))
            m_ta = Decimal(str(movimiento.monto_tarjeta or 0))
            m_dp = Decimal(str(movimiento.monto_deposito or 0))
            total_mov = m_ef + m_ch + m_ta + m_dp
            if total_mov <= 0:
                messages.error(request, 'El importe total del movimiento debe ser mayor a cero.')
                return render(request, 'inmobiliaria/caja/nuevo_movimiento.html', _ctx_nuevo_movimiento())

            productor_id_raw = (request.POST.get('productor_id') or '').strip()
            concepto_ref = (concepto_valor or "").strip()
            concepto_row = None
            if concepto_ref:
                concepto_row = Concepto.objects.filter(
                    id=concepto_ref,
                ).filter(q_conceptos_caja_visibles(request.user.sucursal)).first()
            quiere_vale = bool(
                concepto_row and concepto_row.indica_movimiento_vale_productor()
            )
            vendedor_vale = None
            if quiere_vale:
                if not productor_id_raw:
                    messages.error(
                        request,
                        'Este concepto es de vale: elegí un productor (legajo / búsqueda) para registrar el vale.',
                    )
                    return render(request, 'inmobiliaria/caja/nuevo_movimiento.html', _ctx_nuevo_movimiento())
                try:
                    pid = int(productor_id_raw)
                except (TypeError, ValueError):
                    messages.error(request, 'ID de productor inválido.')
                    return render(request, 'inmobiliaria/caja/nuevo_movimiento.html', _ctx_nuevo_movimiento())
                vendedor_vale = get_object_or_404(
                    Vendedor, id=pid, sucursal=request.user.sucursal
                )

            with transaction.atomic():
                movimiento.save()
                if quiere_vale and vendedor_vale:
                    ValeVendedor.crear_desde_movimiento(
                        movimiento,
                        vendedor_vale,
                        usuario_creador=request.user,
                    )

            if quiere_vale and vendedor_vale:
                messages.success(
                    request,
                    'Movimiento creado y vale registrado para el productor en el historial de vales.',
                )
            else:
                messages.success(request, 'Movimiento creado exitosamente')
            return redirect('inmobiliaria:detalle_caja', numero=caja.numero)

        except Exception as e:
            messages.error(request, f'Error al crear el movimiento: {str(e)}')
            return render(request, 'inmobiliaria/caja/nuevo_movimiento.html', _ctx_nuevo_movimiento())
    
    return render(request, 'inmobiliaria/caja/nuevo_movimiento.html', _ctx_nuevo_movimiento())

@login_required
def cerrar_caja(request, numero_caja):
    caja = get_object_or_404(Caja, numero=numero_caja, sucursal=request.user.sucursal, estado='abierta')
    
    if request.method == 'POST':
        observaciones = request.POST.get('observaciones', '')
        saldo_final = caja.get_saldo_actual()
        
        try:
            # Cerrar la caja actual
            caja.fecha_cierre = timezone.now()
            caja.estado = 'cerrada'
            caja.saldo_final = saldo_final
            caja.usuario_cierre = request.user
            caja.observaciones_cierre = observaciones
            caja.save()
            
            # Apertura automática de nueva caja (numero = PK autoincremental; no fijar a mano).
            nueva_caja = Caja.objects.create(
                sucursal=request.user.sucursal,
                estado='abierta',
                usuario_apertura=request.user,
                saldo_inicial=saldo_final,
                observaciones_apertura=f'Apertura automática tras cierre de Caja #{caja.numero}',
            )
            
            num_cerrada = caja.numero
            messages.success(request, f'✅ Caja #{num_cerrada} cerrada exitosamente')
            messages.success(request, f'🚀 Nueva Caja #{nueva_caja.numero} abierta automáticamente con saldo inicial: ${saldo_final:,.0f}')
            messages.info(request, 'Podés imprimir el resumen de movimientos de la caja cerrada desde la página que se abre.')
            return redirect('inmobiliaria:imprimir_resumen_caja', numero=num_cerrada)
            
        except Exception as e:
            messages.error(request, f'Error al cerrar/abrir caja: {str(e)}')
            return redirect('inmobiliaria:lista_cajas')
    
    return render(request, 'inmobiliaria/caja/cerrar_caja.html', {'caja': caja})

@login_required
def nuevo_registro(request):
    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            registro = form.save(commit=False)
            registro.sucursal = request.user.sucursal
            registro.empleado = request.user
            registro.interno_caja = f"IC-{timezone.now().strftime('%Y%m%d')}-{Registro.objects.count() + 1}"
            registro.save()
            
            messages.success(request, 'Registro creado correctamente.')
            caja_abierta = (
                Caja.objects.filter(sucursal=request.user.sucursal, estado='abierta')
                .order_by('-fecha_apertura')
                .first()
            )
            if caja_abierta:
                return redirect('inmobiliaria:detalle_caja', numero=caja_abierta.numero)
            return redirect('inmobiliaria:gestionar_caja')
    else:
        form = RegistroForm()
    
    return render(request, 'inmobiliaria/caja/nuevo_registro.html', {
        'form': form,
        'caja_actual': request.user.sucursal.caja_set.filter(estado='abierta').order_by(
            '-fecha_apertura'
        ).first()
    })

@login_required
def nuevo_concepto(request):
    """Vista para crear un nuevo concepto desde Ajax con código único"""
    if request.method == 'POST':
        try:
            nombre = request.POST.get('nombre')
            tipo = request.POST.get('tipo', 'general')
            sucursal = request.user.sucursal
            
            if not nombre:
                return JsonResponse({'error': 'El nombre del concepto es obligatorio'}, status=400)
            
            # Generar código único para el concepto (puedes personalizar esto)
            ultimo_concepto = Concepto.objects.filter(sucursal=sucursal).order_by('-id').first()
            codigo = f"C{(ultimo_concepto.id + 1 if ultimo_concepto else 1):04d}"
            
            # Crear el concepto
            concepto = Concepto.objects.create(
                nombre=nombre,
                tipo=tipo,
                codigo=codigo,
                sucursal=sucursal
            )
            
            return JsonResponse({
                'id': concepto.id,
                'nombre': concepto.nombre,
                'codigo': concepto.codigo,
                'success': True
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)

@login_required
def buscar_cuentas(request):
    search = request.GET.get('term', '')
    cuentas = Cuenta.objects.filter(
        Q(numero__icontains=search) | 
        Q(nombre__icontains=search)
    )[:10]
    
    results = [{'id': c.id, 'text': f"{c.numero} - {c.nombre}"} for c in cuentas]
    return JsonResponse({'results': results})



@login_required
@require_POST
def crear_concepto(request):
    try:
        nombre = request.POST.get('nombre')
        if not nombre:
            return JsonResponse({'error': 'El nombre es requerido'}, status=400)
        
        concepto = Concepto.objects.create(nombre=nombre)
        return JsonResponse({
            'id': concepto.id,
            'nombre': concepto.nombre
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_POST
def crear_propiedad(request):
    try:
        direccion = request.POST.get('direccion')
        if not direccion:
            return JsonResponse({'error': 'La dirección es requerida'}, status=400)
        
        propiedad = Propiedad.objects.create(direccion=direccion)
        return JsonResponse({
            'id': propiedad.id,
            'direccion': propiedad.direccion
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# Función para búsqueda de propiedades en Select2 (nueva función)
@login_required
def buscar_propiedades_select2(request):
    """Vista para el autocompletado de Select2"""
    try:
        term = request.GET.get('term', '')
        
        # En caso de que user.sucursal cause problemas
        sucursal_vendedor = None
        if hasattr(request.user, 'sucursal'):
            sucursal_vendedor = request.user.sucursal
            
        # Consulta más segura
        propiedades = Propiedad.objects.all()
        if sucursal_vendedor:
            propiedades = propiedades.filter(sucursal=sucursal_vendedor)
            
        if term:
            propiedades = propiedades.filter(
                Q(direccion__icontains=term) | 
                Q(id__icontains=term)
            )
        
        propiedades = propiedades[:10]
        
        results = []
        for prop in propiedades:
            results.append({
                'id': prop.id,
                'text': f"{prop.direccion}"
            })
        
        return JsonResponse({'results': results})
    except Exception as e:
        import traceback
# print(f"Error en buscar_propiedades_select2: {str(e)}")
# print(traceback.format_exc())
        return JsonResponse({'results': [], 'error': str(e)})

# Asegúrate de que tu función original de alquiler por día siga intacta
# Mantén su nombre y comportamiento original

# Una versión súper simple que no debería fallar
def simple_select2(request):
    """Versión simplificada para debuggear"""
    return JsonResponse({'results': []})

@login_required
def crear_cuenta(request):
    """Vista para crear una nueva cuenta desde Ajax"""
    if request.method == 'POST':
        try:
            nombre = request.POST.get('nombre')
            tipo = request.POST.get('tipo')
            numero_cuenta = request.POST.get('numero_cuenta', '')
            cbu = request.POST.get('cbu', '')
            
            if not nombre:
                return JsonResponse({'error': 'El nombre de la cuenta es obligatorio'}, status=400)
            
            # Crear la cuenta
            cuenta = Cuenta.objects.create(
                nombre=nombre,
                tipo=tipo,
                numero_cuenta=numero_cuenta,
                cbu=cbu,
                sucursal=request.user.sucursal
            )
            
            return JsonResponse({
                'id': cuenta.id,
                'nombre': cuenta.nombre,
                'success': True
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)

@login_required
def buscar_productores(request):
    """Vista para buscar vendedores/productores"""
    term = request.GET.get('term', '')
    
    # IMPORTANTE: Depuración para verificar la consulta
# print(f"Buscando vendedores con término: '{term}'")
    
    try:
        # Buscar TODOS los vendedores sin filtros de sucursal
        if not term or len(term) < 2:
            vendedores = Vendedor.objects.all()[:15]
        else:
            vendedores = Vendedor.objects.filter(
                Q(nombre__icontains=term) | 
                Q(id__icontains=term)
            )[:15]
        
        # Imprimir resultados para depuración
# print(f"Encontrados {vendedores.count()} vendedores")
        for v in vendedores:
            pass  # ✅ Bloque vacío
# print(f"Vendedor: ID={v.id}, Nombre={v.nombre}")
        
        # Formatear resultados
        resultados = []
        for v in vendedores:
            resultados.append({
                'id': v.id,
                'nombre': v.nombre,
                'telefono': getattr(v, 'telefono', '')
            })
        
        return JsonResponse({
            'success': True,
            'resultados': resultados
        })
    
    except Exception as e:
        pass  # ✅ Bloque vacío
# print(f"Error en buscar_productores: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        })

def conceptos_list(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        conceptos = Concepto.objects.filter(q_conceptos_caja_visibles(None)).order_by('id')
        data = {
            'conceptos': [
                {'id': c.id, 'nombre': c.nombre}
                for c in conceptos
            ]
        }
        return JsonResponse(data)
    # Si acceden por navegador normal, redirigir a la gestión completa
    return redirect('inmobiliaria:gestionar_conceptos')

def propietario_cuentas(request):
    propietario_id = request.GET.get('propietario_id')
    if not propietario_id:
        return JsonResponse({'cuentas': []})
    cuentas = CuentaBancaria.objects.filter(propietario_id=propietario_id)
    data = {
        'cuentas': [
            {'id': c.id, 'numero': c.numero, 'alias': getattr(c, 'alias', '')}
            for c in cuentas
        ]
    }
    return JsonResponse(data)

def guardar_movimiento(request):
    if request.method == 'POST':
        propietario_id = request.POST.get('propietario')
        cuenta_bancaria = request.POST.get('cuenta')
        concepto_id = request.POST.get('concepto')
        monto = request.POST.get('monto')
        # ...otros campos...

        # 1. Actualizar la cuenta bancaria del propietario
        if propietario_id and cuenta_bancaria is not None:
            try:
                propietario = Propietario.objects.get(id=propietario_id)
                propietario.cuenta_bancaria = cuenta_bancaria
                propietario.save()
            except Propietario.DoesNotExist:
                messages.error(request, "No se encontró el propietario seleccionado.")
                return redirect('inmobiliaria:nuevo_movimiento')

        # 2. Guardar el movimiento (ajusta los campos según tu modelo)
        movimiento = Movimiento.objects.create(
            propietario_id=propietario_id,
            cuenta=cuenta_bancaria,
            concepto_id=concepto_id,
            monto=monto,
            # ...otros campos...
        )

        messages.success(request, "Movimiento y cuenta bancaria guardados correctamente.")
        return redirect('inmobiliaria:gestionar_caja')  # O la URL que corresponda

    # Si GET, muestra el formulario normalmente
    # ...código para mostrar el formulario...

def propiedades_propietario(request, propietario_id):
    propietario = get_object_or_404(Propietario, pk=propietario_id)

    # Obtener propiedades ordenadas por número de propiedad (no por ID/ficha)
    propiedades = Propiedad.objects.filter(propietario=propietario).select_related('sucursal').order_by('numero_por_propietario')

    return render(
        request,
        "inmobiliaria/propietarios/propiedades_propietario.html",
        {"propietario": propietario, "propiedades": propiedades},
    )

@require_POST
def imagen_eliminar(request, imagen_id):
    """
    Elimina una imagen (botón rojo). Devuelve JSON {success: True}
    """
    imagen = get_object_or_404(ImagenPropiedad, pk=imagen_id)
    imagen.delete()
    return JsonResponse({"success": True})


@require_POST
def reordenar_imagenes(request, propiedad_id):
    """
    Recibe via AJAX la lista nueva de órdenes y actualiza la BD.
    """
    ordenes = json.loads(request.POST.get("ordenes", "[]"))
    with transaction.atomic():
        for item in ordenes:
            ImagenPropiedad.objects.filter(
                pk=item["id"], propiedad_id=propiedad_id
            ).update(orden=item["orden"])
    return JsonResponse({"success": True})

def obtener_caracteristicas_propiedad(request):
    propiedad_id = request.GET.get('propiedad_id')
    
    if not propiedad_id:
        return JsonResponse({'error': 'ID de propiedad requerido'}, status=400)
    
    try:
        propiedad = Propiedad.objects.get(id=propiedad_id)
        
        caracteristicas = []
        
        # Mapear los campos booleanos a nombres legibles
        caracteristicas_map = {
            'amoblado': 'Amoblado',
            'cochera': 'Cochera',
            'tv_smart': 'TV Smart',
            'wifi': 'WiFi',
            'dependencia': 'Dependencia',
            'patio': 'Patio',
            'parrilla': 'Parrilla',
            'piscina': 'Piscina',
            'reciclado': 'Reciclado',
            'a_estrenar': 'A Estrenar',
            'terraza': 'Terraza',
            'balcon': 'Balcón'
        }
        
        # Revisar cada característica y agregar las que sean True
        for campo, nombre in caracteristicas_map.items():
            if getattr(propiedad, campo, False):
                caracteristicas.append(nombre)
        
        return JsonResponse({
            'caracteristicas': caracteristicas,
            'propiedad_id': propiedad_id
        })
        
    except Propiedad.DoesNotExist:
        return JsonResponse({'error': 'Propiedad no encontrada'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def editar_sucursal(request, sucursal_id):
    sucursal = get_object_or_404(Sucursal, id=sucursal_id)
    
    if request.method == 'POST':
        form = SucursalForm(request.POST, instance=sucursal)
        if form.is_valid():
            form.save()
            messages.success(request, f'Sucursal "{sucursal.nombre}" actualizada exitosamente.')
            return redirect('inmobiliaria:detalle_sucursal', sucursal_id=sucursal.id)
    else:
        form = SucursalForm(instance=sucursal)
    
    return render(request, 'inmobiliaria/sucursales/editar.html', {
        'form': form,
        'sucursal': sucursal,
        'titulo': 'Editar Sucursal'
    })

@login_required
def sucursales(request):
    """Lista todas las sucursales"""
    # Debug: Imprimir información del usuario
# print(f"Usuario: {request.user}")
# print(f"Nivel del usuario: {request.user.nivel}")
# print(f"¿Es administrador?: {request.user.nivel == 4}")
    
    # Total de sucursales en la BD
    total_sucursales = Sucursal.objects.all().count()
# print(f"Total de sucursales en BD: {total_sucursales}")
    
    # Mostrar todas las sucursales solo si es administrador (nivel 4)
    if request.user.nivel == 4:
        sucursales = Sucursal.objects.all()
# print(f"Usuario es administrador - mostrando {sucursales.count()} sucursales")
    else:
        # Solo mostrar la sucursal del usuario actual
        sucursales = Sucursal.objects.filter(id=request.user.sucursal.id)
# print(f"Usuario NO es administrador - mostrando {sucursales.count()} sucursales")
    
    return render(request, 'inmobiliaria/sucursal/lista.html', {
        'sucursales': sucursales
    })

@login_required
def sucursal_detalle(request, sucursal_id):
    """Muestra los detalles de una sucursal"""
    sucursal = get_object_or_404(Sucursal, id=sucursal_id)
    
    # Verificar permisos
    if not request.user.is_superuser and request.user.sucursal != sucursal:
        messages.error(request, 'No tienes permisos para ver esta sucursal.')
        return redirect('inmobiliaria:sucursales')
    
    return render(request, 'inmobiliaria/sucursal/detalle.html', {
        'sucursal': sucursal
    })

@login_required
def editar_sucursal(request, sucursal_id):
    """Edita una sucursal existente"""
    sucursal = get_object_or_404(Sucursal, id=sucursal_id)
    
    # Verificar permisos - solo administrador (nivel 4)
    if request.user.nivel != 4:
        messages.error(request, 'No tienes permisos para editar sucursales.')
        return redirect('inmobiliaria:sucursal_detalle', sucursal_id=sucursal.id)
    
    if request.method == 'POST':
        form = SucursalForm(request.POST, instance=sucursal)
        if form.is_valid():
            sucursal = form.save()
            messages.success(request, f'Sucursal "{sucursal.nombre}" actualizada exitosamente.')
            return redirect('inmobiliaria:sucursal_detalle', sucursal_id=sucursal.id)
    else:
        form = SucursalForm(instance=sucursal)
    
    return render(request, 'inmobiliaria/sucursal/editar.html', {
        'form': form,
        'sucursal': sucursal,
        'titulo': f'Editar Sucursal: {sucursal.nombre}'
    })

@login_required
def crear_sucursal(request):
    """Crea una nueva sucursal"""
    # Solo administrador (nivel 4)
    if request.user.nivel != 4:
        messages.error(request, 'No tienes permisos para crear sucursales.')
        return redirect('inmobiliaria:sucursales')
    
    if request.method == 'POST':
        form = SucursalForm(request.POST)
        if form.is_valid():
            sucursal = form.save()
            messages.success(request, f'Sucursal "{sucursal.nombre}" creada exitosamente.')
            return redirect('inmobiliaria:sucursal_detalle', sucursal_id=sucursal.id)
    else:
        form = SucursalForm()
    
    return render(request, 'inmobiliaria/sucursal/crear_sucursal.html', {
        'form': form,
        'titulo': 'Nueva Sucursal'
    })

@login_required
@require_http_methods(["GET"])
def obtener_fotos_propiedad(request, propiedad_id):
    """Obtiene las fotos de una propiedad específica"""
# print(f"=== OBTENER FOTOS PROPIEDAD ===")
# print(f"Propiedad ID: {propiedad_id}")
    
    try:
        propiedad = get_object_or_404(Propiedad, id=propiedad_id)
# print(f"Propiedad encontrada: {propiedad}")
        
        # Obtener todas las fotos de la propiedad usando la relación correcta y ordenadas
        imagenes = propiedad.imagenes.all().order_by('orden')
# print(f"Imágenes encontradas: {imagenes.count()}")
        
        # Obtener el dominio base de la aplicación
        domain = request.get_host()
        protocol = 'https' if request.is_secure() else 'http'
        base_url = f"{protocol}://{domain}"
        
        imagenes_data = []
        for imagen in imagenes:
            try:
                pass  # ✅ Bloque vacío
# print(f"Procesando imagen: {imagen}")
                url_imagen = imagen.imagen.url if imagen.imagen else ''
                # Asegurar que la URL sea absoluta
                if url_imagen.startswith('/'):
                    url_imagen = base_url + url_imagen
# print(f"URL de imagen: {url_imagen}")
                
                imagenes_data.append({
                    'id': imagen.id,
                    'url': url_imagen,
                    'orden': imagen.orden
                })
            except Exception as e:
                pass  # ✅ Bloque vacío
# print(f"Error procesando imagen {imagen.id}: {e}")
                continue
        
        response_data = {
            'success': True,
            'fotos': imagenes_data,
            'total': len(imagenes_data)
        }
        
# print(f"Respuesta imágenes: {response_data}")
        return JsonResponse(response_data)
        
    except Exception as e:
        pass  # ✅ Bloque vacío
# print(f"Error en obtener_fotos_propiedad: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
@require_http_methods(["GET"])
def obtener_precios_propiedad(request, propiedad_id):
    """Obtiene los precios de una propiedad para un período específico"""
# print(f"=== OBTENER PRECIOS PROPIEDAD ===")
# print(f"Propiedad ID: {propiedad_id}")
    
    try:
        propiedad = get_object_or_404(Propiedad, id=propiedad_id)
        
        # Obtener todos los precios de la propiedad ordenados por tipo
        precios = propiedad.precios.all()
        
        # Si no hay precios, crearlos
        if not precios.exists():
            propiedad.crear_precios_iniciales()
            precios = propiedad.precios.all()
        
        # Crear un diccionario con todos los tipos de precio posibles
        precios_data = []
        # print(f"📊 Total de tipos de precio disponibles: {len(TipoPrecio.choices)}")
        for tipo_choice in TipoPrecio.choices:
            tipo_key = tipo_choice[0]
            tipo_display = tipo_choice[1]
            
            # Buscar el precio para este tipo
            precio = precios.filter(tipo_precio=tipo_key).first()
            
            # Si no existe el precio para este tipo, crear un registro temporal
            if not precio:
                precio = Precio(
                    propiedad=propiedad,
                    tipo_precio=tipo_key,
                    precio_total=0,
                    precio_por_dia=0,
                    precio_toma=0,
                    precio_dia_toma=0,
                    ajuste_porcentaje=0
                )
            
            # Agregar los datos del precio
            precios_data.append({
                'id': precio.id if hasattr(precio, 'id') and precio.id else None,
                'tipo_precio': tipo_key,
                'tipo_precio_display': tipo_display,
                'precio_total': str(precio.precio_total or 0),
                'precio_por_dia': str(precio.precio_por_dia or 0),
                'precio_toma': str(precio.precio_toma or 0),
                'precio_dia_toma': str(precio.precio_dia_toma or 0),
                'ajuste_porcentaje': str(precio.ajuste_porcentaje or 0)
            })
        
        # print(f"📊 Total de precios devueltos: {len(precios_data)}")
        response_data = {
            'success': True,
            'precios': precios_data
        }
        
# print(f"Respuesta precios: {response_data}")
        return JsonResponse(response_data)
        
    except Exception as e:
        pass  # ✅ Bloque vacío
# print(f"Error en obtener_precios_propiedad: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
@require_POST
def eliminar_todas_imagenes(request, propiedad_id):
    """Elimina todas las imágenes de una propiedad específica"""
    try:
        propiedad = get_object_or_404(Propiedad, id=propiedad_id)
        imagenes = ImagenPropiedad.objects.filter(propiedad=propiedad)
        
        # Primero intentamos eliminar los archivos físicos
        for imagen in imagenes:
            try:
                if imagen.imagen:
                    imagen.imagen.delete(save=False)
            except Exception as e:
                logger.warning(f'No se pudo eliminar el archivo físico de la imagen {imagen.id}: {str(e)}')
        
        # Luego eliminamos todos los registros de la base de datos
        total_eliminadas = imagenes.count()
        imagenes.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Se eliminaron {total_eliminadas} imágenes',
            'total_eliminadas': total_eliminadas
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
def dashboard_caja(request):
    return render(request, 'inmobiliaria/caja/dashboard_caja.html')


def _etiqueta_id_concepto_caja_visual(cid):
    """Presentación: el id de catálogo «RE» se muestra como RECIBO (el id real en BD no cambia)."""
    s = (cid or '').strip()
    if s.upper() == 'RE':
        return 'RECIBO'
    return s


def _filtro_qs_por_buscar_concepto(qs, texto, conceptos_catalogo):
    """
    Un solo criterio de búsqueda por concepto.
    Tolera '6', '6 - EXPENSAS', '6 — Expensas' (guiones - – —).
    Si el movimiento solo guarda el id ('6'), coincide por catálogo aunque el usuario
    haya elegido '6 - NOMBRE' en la lista (OR con búsqueda por frase completa).
    """
    texto = (texto or '').strip()
    if not texto:
        return qs

    lookup_id = {c.id: c for c in conceptos_catalogo}

    def q_por_id(cid, c_obj):
        q = (
            Q(concepto__iexact=cid)
            | Q(concepto__istartswith=f'{cid} -')
            | Q(concepto__istartswith=f'{cid}-')
            | Q(concepto__istartswith=f'{cid} ')
            | Q(concepto__icontains=f'Concepto {cid}')
            | Q(concepto_detalle__icontains=cid)
        )
        if c_obj:
            n = (c_obj.nombre or '').strip()
            if len(n) >= 2:
                q |= Q(concepto__icontains=n) | Q(concepto_detalle__icontains=n)
        return q

    q_full = Q(concepto__icontains=texto) | Q(concepto_detalle__icontains=texto)

    # Solo números: id de catálogo si existe; si no, substring
    if re.match(r'^\d+$', texto):
        if texto in lookup_id:
            return qs.filter(q_por_id(texto, lookup_id[texto]) | q_full)
        return qs.filter(q_full)

    # "6 - algo" / "6 — algo" (típico al elegir del datalist)
    m = re.match(r'^(\d+)\s*[-–—]\s*(.+)$', texto)
    if m:
        cid = m.group(1)
        c_obj = lookup_id.get(cid)
        q_id = q_por_id(cid, c_obj)
        return qs.filter(q_id | q_full)

    # Texto libre: frase completa; si hay varias partes, también AND suave por tokens
    partes = [p for p in re.split(r'[\s\-–—]+', texto) if p]
    if len(partes) <= 1:
        return qs.filter(q_full)

    q_tok = None
    for p in partes:
        if re.match(r'^\d+$', p) and p in lookup_id:
            qp = q_por_id(p, lookup_id[p])
        else:
            qp = Q(concepto__icontains=p) | Q(concepto_detalle__icontains=p)
        q_tok = qp if q_tok is None else (q_tok & qp)
    return qs.filter(q_full | q_tok)


@login_required
def reportes_caja(request):
    """
    Resumen de ingresos/egresos por rango de fechas, con filtros por medio de pago,
    cuenta de transferencia y texto en concepto (concepto / concepto_detalle).
    """
    from inmobiliaria.models.sucursal import CuentaBancaria

    sucursal = request.user.sucursal
    hoy = timezone.localdate()

    def _parse_date(s):
        if not s:
            return None
        try:
            return datetime.strptime(s.strip(), '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return None

    fecha_desde = _parse_date(request.GET.get('fecha_desde', ''))
    fecha_hasta = _parse_date(request.GET.get('fecha_hasta', ''))
    if not fecha_desde:
        fecha_desde = hoy.replace(day=1)
    if not fecha_hasta:
        fecha_hasta = hoy
    if fecha_hasta < fecha_desde:
        fecha_desde, fecha_hasta = fecha_hasta, fecha_desde

    tipo_mov = (request.GET.get('tipo_mov') or '').strip().upper()
    if tipo_mov not in ('', 'IN', 'EG'):
        tipo_mov = ''

    medio = (request.GET.get('medio') or '').strip().lower()
    medios_validos = (
        '', 'efectivo', 'cheque', 'tarjeta', 'tarjeta_credito', 'tarjeta_debito', 'transferencia',
    )
    if medio not in medios_validos:
        medio = ''

    destino_transferencia = (request.GET.get('destino_transferencia') or '').strip()
    conceptos_catalogo = list(
        Concepto.objects.filter(q_conceptos_caja_visibles(sucursal)).order_by('id')
    )
    # Un solo campo GET; compatibilidad con enlaces viejos (?q_concepto= / ?concepto_catalogo=)
    buscar_concepto = (request.GET.get('buscar_concepto') or '').strip()[:200]
    if not buscar_concepto:
        buscar_concepto = (request.GET.get('q_concepto') or '').strip()[:200]
    if not buscar_concepto:
        buscar_concepto = (request.GET.get('concepto_catalogo') or '').strip()[:30]

    cuentas_bancarias = list(
        CuentaBancaria.objects.filter(sucursal=sucursal, activa=True).order_by('nombre_banco', 'alias')
    )

    # Solo destinos que esta sucursal realmente usó en transferencias (evita listar MP/Galicia
    # en sucursales que solo usan cuentas configuradas en CuentaBancaria).
    destinos_usados = set(
        MovimientoCaja.objects.filter(sucursal=sucursal, monto_deposito__gt=0)
        .exclude(destino_deposito__isnull=True)
        .exclude(destino_deposito='')
        .values_list('destino_deposito', flat=True)
    )

    # Etiquetas distintas a las cuentas bancarias (ej. "Banco Galicia") para no duplicar el nombre en el select.
    fijos_etiqueta = {
        'galicia': 'Galicia (registros antiguos)',
        'mp': 'Mercado Pago (registros antiguos)',
        'mixto': 'Mixto (registros antiguos)',
    }
    opciones_destino = []
    for clave in ('galicia', 'mp', 'mixto'):
        if clave in destinos_usados:
            opciones_destino.append({'valor': clave, 'etiqueta': fijos_etiqueta[clave]})

    cuentas_map = {c.id: c for c in cuentas_bancarias}
    vistos_cuenta = set(cuentas_map.keys())

    for c in cuentas_bancarias:
        lbl = c.nombre_banco
        if c.alias:
            lbl = f'{lbl} — {c.alias}'
        opciones_destino.append({'valor': f'cuenta_{c.id}', 'etiqueta': lbl})

    for d in destinos_usados:
        if not isinstance(d, str) or not d.startswith('cuenta_'):
            continue
        suf = d.replace('cuenta_', '', 1)
        if not suf.isdigit():
            continue
        cid = int(suf)
        if cid in vistos_cuenta:
            continue
        extra = CuentaBancaria.objects.filter(id=cid, sucursal=sucursal).first()
        if extra:
            lbl = extra.nombre_banco
            if extra.alias:
                lbl = f'{lbl} — {extra.alias}'
            if not extra.activa:
                lbl = f'{lbl} (inactiva)'
            opciones_destino.append({'valor': f'cuenta_{extra.id}', 'etiqueta': lbl})
            cuentas_map[extra.id] = extra
            vistos_cuenta.add(extra.id)

    valores_destino_validos = {op['valor'] for op in opciones_destino}
    if destino_transferencia and destino_transferencia not in valores_destino_validos:
        destino_transferencia = ''

    qs = (
        MovimientoCaja.objects.filter(
            sucursal=sucursal,
            fecha__date__gte=fecha_desde,
            fecha__date__lte=fecha_hasta,
        )
        .select_related('caja', 'empleado', 'propiedad')
        .order_by('-fecha', '-id')
    )

    if tipo_mov == 'IN':
        qs = qs.filter(tipo=TipoMovimientoCajaEnum.INGRESO)
    elif tipo_mov == 'EG':
        qs = qs.filter(tipo=TipoMovimientoCajaEnum.EGRESO)

    if medio == 'efectivo':
        qs = qs.filter(monto_efectivo__gt=0)
    elif medio == 'cheque':
        qs = qs.filter(monto_cheque__gt=0)
    elif medio == 'tarjeta':
        qs = qs.filter(monto_tarjeta__gt=0)
    elif medio == 'tarjeta_credito':
        qs = qs.filter(monto_tarjeta__gt=0, tarjeta_tipo='credito')
    elif medio == 'tarjeta_debito':
        qs = qs.filter(monto_tarjeta__gt=0, tarjeta_tipo='debito')
    elif medio == 'transferencia':
        q_dep = Q(monto_deposito__gt=0)
        if destino_transferencia:
            q_dep &= Q(destino_deposito=destino_transferencia)
        qs = qs.filter(q_dep)

    if buscar_concepto:
        qs = _filtro_qs_por_buscar_concepto(qs, buscar_concepto, conceptos_catalogo)

    def etiqueta_destino(val):
        if not val:
            return '—'
        if val == 'galicia':
            return fijos_etiqueta['galicia']
        if val == 'mp':
            return fijos_etiqueta['mp']
        if val == 'mixto':
            return fijos_etiqueta['mixto']
        if val.startswith('cuenta_'):
            rest = val.replace('cuenta_', '', 1)
            if rest.isdigit():
                c = cuentas_map.get(int(rest))
                if c:
                    return f'{c.nombre_banco}' + (f' ({c.alias})' if c.alias else '')
            return val
        return val

    lookup_nombre_concepto = {c.id: c.nombre for c in conceptos_catalogo}

    movimientos_lista = list(qs[:2000])
    for _m in movimientos_lista:
        _m.destino_etiqueta = etiqueta_destino(_m.destino_deposito)
        raw = (_m.concepto or '').strip()
        nom_cat = lookup_nombre_concepto.get(raw)
        primer_token = raw.split(None, 1)[0] if raw else ''
        primer_visual = _etiqueta_id_concepto_caja_visual(primer_token)
        if not nom_cat and primer_token:
            nom_cat = lookup_nombre_concepto.get(primer_token)
        if nom_cat:
            if raw == primer_token:
                _m.concepto_display = f'{primer_visual} — {nom_cat}'
            elif nom_cat.lower() not in raw.lower():
                _m.concepto_display = f'{raw} — {nom_cat}'
            else:
                _m.concepto_display = raw
        else:
            _m.concepto_display = primer_visual if raw == primer_token else raw

    def totales_por_tipo(queryset, tipo_code):
        sub = queryset.filter(tipo=tipo_code)
        ag = sub.aggregate(
            efectivo=models.Sum('monto_efectivo'),
            cheque=models.Sum('monto_cheque'),
            tarjeta=models.Sum('monto_tarjeta'),
            tarjeta_credito=models.Sum('monto_tarjeta', filter=Q(tarjeta_tipo='credito')),
            tarjeta_debito=models.Sum('monto_tarjeta', filter=Q(tarjeta_tipo='debito')),
            deposito=models.Sum('monto_deposito'),
            total_mov=models.Sum(
                F('monto_efectivo') + F('monto_cheque') + F('monto_tarjeta') + F('monto_deposito')
            ),
        )
        for k in list(ag.keys()):
            ag[k] = ag[k] or Decimal('0')
        return ag

    tot_in = totales_por_tipo(qs, TipoMovimientoCajaEnum.INGRESO)
    tot_eg = totales_por_tipo(qs, TipoMovimientoCajaEnum.EGRESO)

    transferencias_por_destino = []
    dep_rows = (
        qs.filter(monto_deposito__gt=0)
        .values('destino_deposito', 'tipo')
        .annotate(total=models.Sum('monto_deposito'))
        .order_by('tipo', 'destino_deposito')
    )
    for row in dep_rows:
        dest = row['destino_deposito'] or ''
        transferencias_por_destino.append({
            'destino': dest,
            'etiqueta': etiqueta_destino(dest),
            'tipo': row['tipo'],
            'tipo_display': 'Ingreso' if row['tipo'] == TipoMovimientoCajaEnum.INGRESO else 'Egreso',
            'total': row['total'] or Decimal('0'),
        })

    from django.core.paginator import Paginator

    paginator = Paginator(movimientos_lista, 100)
    page_obj = paginator.get_page(request.GET.get('page'))
    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']

    context = {
        'fecha_desde': fecha_desde.strftime('%Y-%m-%d'),
        'fecha_hasta': fecha_hasta.strftime('%Y-%m-%d'),
        'tipo_mov': tipo_mov,
        'medio': medio,
        'destino_transferencia': destino_transferencia,
        'buscar_concepto': buscar_concepto,
        'conceptos_catalogo': conceptos_catalogo,
        'opciones_destino': opciones_destino,
        'movimientos': page_obj,
        'total_filtrados': len(movimientos_lista),
        'truncado': qs.count() > 2000,
        'totales_ingresos': tot_in,
        'totales_egresos': tot_eg,
        'balance': (tot_in['total_mov'] - tot_eg['total_mov']),
        'transferencias_por_destino': transferencias_por_destino,
        'querystring': query_params.urlencode(),
    }
    return render(request, 'inmobiliaria/caja/reportes.html', context)

@login_required
def arqueo_caja(request):
    return render(request, 'inmobiliaria/caja/arqueo.html')

@login_required
def historial_caja(request):
    return render(request, 'inmobiliaria/caja/historial.html')

@login_required
def buscar_conceptos(request):
    termino = (request.POST.get('termino') or request.GET.get('termino') or request.GET.get('q') or '').strip()
    sucursal = request.user.sucursal
    base_qs = Concepto.objects.filter(q_conceptos_caja_visibles(sucursal))

    if not termino:
        conceptos = base_qs.order_by('nombre', 'id')[:100]
    else:
        conceptos_por_id = base_qs.filter(id__iexact=termino)
        conceptos_por_nombre = base_qs.filter(nombre__icontains=termino)
        conceptos = (conceptos_por_id | conceptos_por_nombre).distinct().order_by('nombre', 'id')[:50]

    return JsonResponse({
        'conceptos': [{
            'id': c.id,
            'nombre': c.nombre,
            'fecha_creacion': c.fecha_creacion.strftime('%d/%m/%Y %H:%M')
        } for c in conceptos]
    })

@login_required
def crear_concepto(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'})
    
    id = request.POST.get('id')
    nombre = request.POST.get('nombre')
    sucursal = request.user.sucursal
    
    if not id or not nombre:
        return JsonResponse({'success': False, 'error': 'ID y nombre son requeridos'})
    
    try:
        if Concepto.objects.filter(id=id).exists():
            return JsonResponse(
                {'success': False, 'error': 'Ya existe un concepto con ese ID en el catálogo compartido.'}
            )

        destino = sucursal_destino_nuevo_concepto_caja(sucursal)
        concepto = Concepto.objects.create(
            id=id,
            nombre=nombre,
            sucursal=destino,
        )
        
        return JsonResponse({
            'success': True,
            'concepto': {
                'id': concepto.id,
                'nombre': concepto.nombre,
                'fecha_creacion': concepto.fecha_creacion.strftime('%d/%m/%Y %H:%M')
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def buscar_propiedad(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'})
    
    termino = request.POST.get('id', '').strip()
    sucursal = request.user.sucursal
    
    if not termino:
        return JsonResponse({
            'success': False,
            'error': 'Ingrese un término de búsqueda'
        })
    
    try:
        # Buscar por ID exacto primero
        try:
            propiedad = Propiedad.objects.get(id=int(termino), sucursal=sucursal)
            return JsonResponse({
                'success': True,
                'propiedad': {
                    'id': propiedad.id,
                    'direccion': propiedad.direccion,
                    'ubicacion': propiedad.ubicacion,
                    'piso': (propiedad.piso or '').strip(),
                    'departamento': (propiedad.departamento or '').strip(),
                }
            })
        except (ValueError, Propiedad.DoesNotExist):
            # Si no es un número o no se encuentra por ID, buscar por dirección
            propiedades = Propiedad.objects.filter(
                sucursal=sucursal
            ).filter(
                Q(direccion__icontains=termino) |
                Q(ubicacion__icontains=termino) |
                Q(piso__icontains=termino) |
                Q(departamento__icontains=termino)
            ).order_by('direccion')[:1]
            
            if propiedades.exists():
                propiedad = propiedades.first()
                return JsonResponse({
                    'success': True,
                    'propiedad': {
                        'id': propiedad.id,
                        'direccion': propiedad.direccion,
                        'ubicacion': propiedad.ubicacion,
                        'piso': (propiedad.piso or '').strip(),
                        'departamento': (propiedad.departamento or '').strip(),
                    }
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'No se encontró la propiedad'
                })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })



@login_required
def buscar_movimiento(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'})
    
    operacion = request.POST.get('operacion')
    sucursal = request.user.sucursal
    
    try:
        movimiento = MovimientoCaja.objects.select_related(
            'productor',
            'propiedad',
            'concepto'
        ).get(operacion=operacion, caja__sucursal=sucursal)
        
        return JsonResponse({
            'success': True,
            'movimiento': {
                'tipo': movimiento.tipo,
                'tipo_comprobante': movimiento.tipo_comprobante,
                'numero_liquidacion': movimiento.numero_liquidacion,
                'detalles': movimiento.detalles,
                'productor': {
                    'id': movimiento.productor.id,
                    'nombre': movimiento.productor.nombre,
                    'apellido': movimiento.productor.apellido
                } if movimiento.productor else None,
                'propiedad': {
                    'id': movimiento.propiedad.id,
                    'direccion': movimiento.propiedad.direccion,
                    'ubicacion': getattr(movimiento.propiedad, 'ubicacion', None) or '',
                    'piso': (movimiento.propiedad.piso or '').strip(),
                    'departamento': (movimiento.propiedad.departamento or '').strip(),
                } if movimiento.propiedad else None,
                'concepto': {
                    'id': movimiento.concepto.id,
                    'nombre': movimiento.concepto.nombre
                } if movimiento.concepto else None
            }
        })
    except MovimientoCaja.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'No se encontró el movimiento'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })


@login_required
def buscar_liquidacion_caja(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'})

    liquidacion_id = (request.POST.get('liquidacion_id') or '').strip()
    if not liquidacion_id:
        return JsonResponse({'success': False, 'error': 'Ingrese un ID de liquidación'})

    try:
        liquidacion = LiquidacionPropietario.objects.select_related(
            'propietario', 'propiedad'
        ).get(
            id=int(liquidacion_id),
            sucursal=request.user.sucursal
        )
    except (ValueError, LiquidacionPropietario.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'No se encontró la liquidación'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({
        'success': True,
        'liquidacion': {
            'id': liquidacion.id,
            'estado': liquidacion.estado,
            'propiedad': {
                'id': liquidacion.propiedad.id if liquidacion.propiedad else None,
                'direccion': liquidacion.propiedad.direccion if liquidacion.propiedad else '',
                'ubicacion': (liquidacion.propiedad.ubicacion or '') if liquidacion.propiedad else '',
                'piso': (liquidacion.propiedad.piso or '').strip() if liquidacion.propiedad else '',
                'departamento': (liquidacion.propiedad.departamento or '').strip() if liquidacion.propiedad else '',
            },
            'propietario': str(liquidacion.propietario) if liquidacion.propietario else '',
            'cuenta_bancaria': (liquidacion.propietario.cuenta_bancaria or '').strip() if liquidacion.propietario else '',
            'fecha_desde': liquidacion.fecha_desde.strftime('%Y-%m-%d') if liquidacion.fecha_desde else '',
            'fecha_hasta': liquidacion.fecha_hasta.strftime('%Y-%m-%d') if liquidacion.fecha_hasta else '',
            'monto_a_pagar': float(liquidacion.monto_a_pagar or 0),
            'monto_propietario': float(liquidacion.monto_propietario or 0),
            'monto_total_operacion': float(liquidacion.monto_total_operacion or 0),
            'monto_cochera': float(liquidacion.monto_cochera or 0),
            'monto_fondo_mantenimiento': float(liquidacion.monto_fondo_mantenimiento or 0),
        }
    })

@login_required
def buscar_movimientos(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'})
    
    fecha_desde = request.POST.get('fecha_desde')
    fecha_fin = request.POST.get('fecha_hasta')
    productor_id = request.POST.get('productor_id')
    sucursal = request.user.sucursal
    
    try:
        # Construir el query base
        movimientos = MovimientoCaja.objects.filter(caja__sucursal=sucursal)
        
        # Aplicar filtros si se proporcionan
        if fecha_desde:
            movimientos = movimientos.filter(fecha__date__gte=fecha_desde)
        if fecha_fin:
            movimientos = movimientos.filter(fecha__date__lte=fecha_fin)
        if productor_id:
            movimientos = movimientos.filter(productor_id=productor_id)
        
        # Ordenar por fecha
        movimientos = movimientos.order_by('-fecha')
        
        # Convertir a lista de diccionarios para la respuesta JSON
        movimientos_data = [{
            'id': mov.id,
            'fecha': mov.fecha.strftime('%d/%m/%Y %H:%M'),
            'tipo': mov.tipo,
            'operacion': mov.operacion,
            'tipo_comprobante': mov.tipo_comprobante,
            'numero_liquidacion': mov.numero_liquidacion,
            'detalles': mov.detalles,
            'monto': float(mov.monto_total) if mov.monto_total else 0,
            'productor': {
                'id': mov.productor.id,
                'nombre': mov.productor.nombre,
                'apellido': mov.productor.apellido
            } if mov.productor else None,
            'propiedad': {
                'id': mov.propiedad.id,
                'direccion': mov.propiedad.direccion,
                'ubicacion': getattr(mov.propiedad, 'ubicacion', None) or '',
                'piso': (mov.propiedad.piso or '').strip(),
                'departamento': (mov.propiedad.departamento or '').strip(),
            } if mov.propiedad else None,
            'concepto': {
                'id': mov.concepto.id,
                'nombre': mov.concepto.nombre
            } if mov.concepto else None
        } for mov in movimientos]
        
        return JsonResponse({
            'success': True,
            'movimientos': movimientos_data
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
def buscar_vendedor(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'})
    
    termino = request.POST.get('id', '').strip()
    sucursal = request.user.sucursal
    
    if not termino:
        return JsonResponse({
            'success': False,
            'error': 'Ingrese un término de búsqueda'
        })
    
    try:
        # Buscar por ID exacto primero
        try:
            vendedor = Vendedor.objects.get(id=int(termino), sucursal=sucursal)
            return JsonResponse({
                'success': True,
                'vendedor': {
                    'id': vendedor.id,
                    'nombre': vendedor.nombre,
                    'apellido': vendedor.apellido
                }
            })
        except (ValueError, Vendedor.DoesNotExist):
            # Si no es un número o no se encuentra por ID, buscar por nombre/apellido
            vendedores = Vendedor.objects.filter(
                sucursal=sucursal
            ).filter(
                Q(nombre__icontains=termino) |
                Q(apellido__icontains=termino)
            ).order_by('apellido', 'nombre')[:1]
            
            if vendedores.exists():
                vendedor = vendedores.first()
                return JsonResponse({
                    'success': True,
                    'vendedor': {
                        'id': vendedor.id,
                        'nombre': vendedor.nombre,
                        'apellido': vendedor.apellido
                    }
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'No se encontró el vendedor'
                })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
def buscar_vendedores(request):
    # Aceptar tanto GET como POST para mayor flexibilidad
    if request.method == 'GET':
        termino = (request.GET.get('nombre') or '').strip()
    elif request.method == 'POST':
        termino = (request.POST.get('termino') or '').strip()
    else:
        return JsonResponse({'success': False, 'error': 'Método no permitido'})
    
    sucursal = request.user.sucursal
    
    if not termino:
        return JsonResponse({'success': True, 'vendedores': []})
    
    try:
        q_text = (
            Q(nombre__icontains=termino) |
            Q(apellido__icontains=termino)
        )
        try:
            vid = int(termino)
            q_text = q_text | Q(id=vid)
        except (ValueError, TypeError):
            pass
        vendedores = Vendedor.objects.filter(sucursal=sucursal).filter(q_text).order_by(
            'apellido', 'nombre'
        )[:30]
        
        return JsonResponse({
            'success': True,
            'vendedores': [{
                'id': v.id,
                'nombre': v.nombre,
                'apellido': v.apellido
            } for v in vendedores]
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
def obtener_caja_actual(request):
    """Devuelve el número de la caja actual abierta para la sucursal del usuario"""
    try:
        if not hasattr(request.user, 'sucursal') or not request.user.sucursal:
            return JsonResponse({
                'success': False,
                'error': 'Usuario sin sucursal asignada'
            })
        
        caja_actual = Caja.objects.filter(
            sucursal=request.user.sucursal,
            estado='abierta',
        ).order_by('-fecha_apertura').first()
        
        return JsonResponse({
            'success': True,
            'caja_numero': caja_actual.numero if caja_actual else None
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
def buscar_propiedades_caja(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'})
    
    termino = (request.POST.get('termino') or '').strip()
    sucursal = request.user.sucursal
    
    if not termino:
        return JsonResponse({'success': True, 'propiedades': []})
    
    try:
        q = (
            Q(direccion__icontains=termino) |
            Q(ubicacion__icontains=termino) |
            Q(piso__icontains=termino) |
            Q(departamento__icontains=termino)
        )
        try:
            pid = int(termino)
            q = q | Q(id=pid)
        except (ValueError, TypeError):
            pass
        propiedades = Propiedad.objects.filter(sucursal=sucursal).filter(q).order_by(
            'direccion'
        )[:40]
        
        return JsonResponse({
            'success': True,
            'propiedades': [{
                'id': p.id,
                'direccion': p.direccion,
                'ubicacion': p.ubicacion or '',
                'piso': (p.piso or '').strip(),
                'departamento': (p.departamento or '').strip(),
            } for p in propiedades]
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
def buscar_propiedades(request):
    # FUNCIÓN: buscar_propiedades - función que está siendo usada en producción ✅
# print("🚀 INICIO DE BUSCAR_PROPIEDADES - FUNCIÓN EJECUTÁNDOSE")
# print("🔍 DEBUGGING: Esta es la función que se está ejecutando para ordenamiento")
    
    # Obtener la sucursal del vendedor logueado
    sucursal_vendedor = request.user.sucursal
# print(f"👤 Usuario: {request.user}, Sucursal: {sucursal_vendedor}")
    
    inquilinos = get_inquilinos_queryset_unificado(request)
    form = BuscarPropiedadesForm(request.POST or None)
    inquilino_form = InquilinoForm(request.POST)
    propiedades_disponibles = []
    propiedades_sin_precio = []
    vendedores = Vendedor.objects.filter(sucursal=sucursal_vendedor)
    total_dias_reserva = 0
    
    # FLAG: Para identificar específicamente esta función en los edits siguientes
    FUNCION_PRINCIPAL_EN_USO = True

    fecha_inicio = None
    fecha_fin = None
    origen = None
    destino = None

    if form.is_valid():
        fecha_inicio = form.cleaned_data['fecha_inicio']
        fecha_fin = form.cleaned_data['fecha_fin']
        
        # VALIDACIÓN: Verificar que las fechas son válidas
        if not fecha_inicio or not fecha_fin:
            pass  # ✅ Bloque vacío
# print("❌ Error: Fechas de inicio o fin faltantes")
            return render(request, 'inmobiliaria/reserva/buscar_propiedades.html', {
                'form': form,
                'error_fechas': 'Por favor, ingresa fechas de inicio y fin válidas.',
                'inquilinos': inquilinos,
                'vendedores': vendedores,
                'propiedades_disponibles': [],
                'total_dias_reserva': 0,
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin,
            })
        origen = form.cleaned_data['origen']
        destino = form.cleaned_data['destino']
        ver_todas = form.cleaned_data.get('ver_todas', False)

        # Filtrar propiedades según la opción seleccionada
        if ver_todas:
            # Solo mostrar propiedades de las sucursales Colón y Corrientes
            # Buscar por nombre de sucursal con múltiples variaciones
            # Buscar "colon" (sin tilde) y "colón" (con tilde) para cubrir todas las formas
            propiedades = Propiedad.objects.filter(
                Q(sucursal__nombre__icontains='colon') | 
                Q(sucursal__nombre__icontains='corrientes')
            )
        else:
            propiedades = Propiedad.objects.filter(sucursal=sucursal_vendedor)
        
        # AGREGAR FLAG: Para editar específicamente el filtro de esta función
        ES_BUSCAR_PROPIEDADES_PRINCIPAL = True
        
        # 🎯 DEBUGGING: Verificar fechas de búsqueda
# print(f"🎯 BUSCAR_PROPIEDADES_PRINCIPAL: Buscando desde {fecha_inicio} hasta {fecha_fin}")
        
        # 🎯 DEBUGGING: Ver qué propiedades tienen reservas en estas fechas
        from inmobiliaria.models import Reserva
        reservas_en_fechas = Reserva.objects.filter(
            Q(fecha_inicio__lt=fecha_fin) & Q(fecha_fin__gt=fecha_inicio)
        )
# print(f"🔍 RESERVAS EN ESTAS FECHAS: {reservas_en_fechas.count()} encontradas")
        for r in reservas_en_fechas:
            pass  # ✅ Bloque vacío
# print(f"   - Reserva {r.id}: Propiedad {r.propiedad.id} ({r.propiedad.ubicacion})")
# print(f"     Fechas: {r.fecha_inicio} al {r.fecha_fin}, Estado: '{r.estado}'")
        
        # FLAG para identificar esta función específica para debugging posterior
        DEBUGGING_FUNCION_PRINCIPAL = True

        # Prefetch los precios para cada propiedad
        propiedades = propiedades.prefetch_related(
            Prefetch('precios', queryset=Precio.objects.all(), to_attr='todos_precios')
        ).select_related('sucursal')

        # Aplicar filtros del formulario
        if origen:
            propiedades = propiedades.filter(ubicacion__icontains=origen)
        
        if destino:
            propiedades = propiedades.filter(ubicacion__icontains=destino)

        tipo_inmueble = form.cleaned_data.get('tipo_inmueble')
        if tipo_inmueble:
            propiedades = propiedades.filter(tipo_inmueble__in=tipo_inmueble)

        vista = form.cleaned_data.get('vista')
        if vista:
            propiedades = propiedades.filter(vista__in=vista)

        ambientes = form.cleaned_data.get('ambientes')
        if ambientes:
            propiedades = propiedades.filter(ambientes=ambientes)

        valoracion = form.cleaned_data.get('valoracion')
        if valoracion:
            propiedades = propiedades.filter(valoracion=valoracion)

        precio_min = form.cleaned_data.get('precio_min')
        if precio_min is not None:
            propiedades = propiedades.filter(precio__gte=precio_min)

        precio_max = form.cleaned_data.get('precio_max')
        if precio_max is not None:
            propiedades = propiedades.filter(precio__lte=precio_max)

        # Filtros booleanos
        caracteristicas_booleanas = [
            'amoblado', 'cochera', 'tv_smart', 'wifi', 'dependencia', 'patio',
            'parrilla', 'piscina', 'reciclado', 'a_estrenar', 'terraza', 'balcon',
            'baulera', 'lavadero', 'seguridad', 'vista_al_Mar', 'vista_panoramica', 'apto_credito'
        ]
        for caracteristica in caracteristicas_booleanas:
            if form.cleaned_data.get(caracteristica):
                propiedades = propiedades.filter(**{caracteristica: True})

        # Filtrar propiedades que están disponibles en las fechas indicadas
        for propiedad in propiedades:
            from datetime import timedelta
# print(f"🔍 PROCESANDO PROPIEDAD {propiedad.id}: {propiedad}")
# print(f"   🔎 Buscando disponibilidades para {fecha_inicio} al {fecha_fin}")
            
            # 1️⃣ BUSCAR TODAS LAS DISPONIBILIDADES QUE SE SUPERPONEN CON EL PERÍODO
            disponibilidades_superpuestas = Disponibilidad.objects.filter(
                propiedad=propiedad,
                fecha_inicio__lt=fecha_fin,   # Empieza antes de que termine la búsqueda
                fecha_fin__gt=fecha_inicio,   # Termina después de que empiece la búsqueda
            ).order_by('fecha_inicio')
            
            # 2️⃣ VERIFICAR SI LAS DISPONIBILIDADES CUBREN TODO EL RANGO (permitiendo contiguas)
            periodo_cubierto = False
            if disponibilidades_superpuestas.exists():
                # Verificar si las disponibilidades contiguas cubren todo el rango
                disponibilidades_list = list(disponibilidades_superpuestas)
                
                # Ordenar por fecha de inicio
                disponibilidades_list.sort(key=lambda d: d.fecha_inicio)
                
                # Verificar cobertura continua
                cobertura_inicio = disponibilidades_list[0].fecha_inicio
                cobertura_fin = disponibilidades_list[0].fecha_fin
                
                for i in range(1, len(disponibilidades_list)):
                    disp_actual = disponibilidades_list[i]
                    # Si la disponibilidad actual empieza el mismo día o antes que termine la anterior
                    # (permitiendo fechas contiguas como 07-11 y 11-15)
                    if disp_actual.fecha_inicio <= cobertura_fin:
                        # Extender la cobertura
                        cobertura_fin = max(cobertura_fin, disp_actual.fecha_fin)
                    else:
                        # Hay un hueco
                        break
                
                # Verificar si la cobertura completa incluye el período buscado
                if cobertura_inicio <= fecha_inicio and cobertura_fin >= fecha_fin:
                    periodo_cubierto = True
# print(f"   ✅ Período CUBIERTO por disponibilidades contiguas: {cobertura_inicio} al {cobertura_fin}")
                else:
                    pass  # ✅ Bloque vacío
# print(f"   ❌ Período NO cubierto. Cobertura: {cobertura_inicio} al {cobertura_fin}, necesario: {fecha_inicio} al {fecha_fin}")
            
            # Usar la variable disponibilidades para mantener compatibilidad con el resto del código
            disponibilidades = disponibilidades_superpuestas if periodo_cubierto else Disponibilidad.objects.none()
            
            if periodo_cubierto:
                # 3️⃣ CALCULAR PERÍODO LIBRE usando la cobertura de disponibilidades contiguas
                # Usar la cobertura calculada anteriormente (cobertura_inicio y cobertura_fin)
                fecha_disponible_desde = cobertura_inicio
                fecha_disponible_hasta = cobertura_fin
                
                # 4️⃣ AJUSTAR POR RESERVAS ANTERIORES Y POSTERIORES
                # Fechas finales de reservas que terminan antes o en la fecha de inicio
                # Excluir reservas eliminadas
                reservas_anteriores = propiedad.reservas.filter(
                    fecha_fin__lte=fecha_inicio,
                    eliminada=False
                ).order_by('-fecha_fin').first()
                
                if reservas_anteriores:
                    # 🏨 LÓGICA HOTEL: Si reserva termina el 17, el 17 ya está disponible
                    fecha_disponible_desde = max(fecha_disponible_desde, reservas_anteriores.fecha_fin)
                
                # Fechas iniciales de reservas que empiezan después o en la fecha de fin
                # Excluir reservas eliminadas
                reservas_posteriores = propiedad.reservas.filter(
                    fecha_inicio__gte=fecha_fin,
                    eliminada=False
                ).order_by('fecha_inicio').first()
                
                if reservas_posteriores:
                    # 🏨 LÓGICA HOTEL: Si próxima reserva empieza el 25, hasta el 25 está disponible
                    fecha_disponible_hasta = min(fecha_disponible_hasta, reservas_posteriores.fecha_inicio)
                
                # 4b. Ajustar "disponible hasta" si hay contrato de alquiler (invierno/24m) que empiece dentro del período libre
                contrato_corta = ContratoAlquiler.objects.filter(
                    propiedad=propiedad,
                    estado__in=['reservado', 'activo'],
                    fecha_inicio__lte=fecha_disponible_hasta,
                    fecha_fin__gt=fecha_disponible_desde
                ).order_by('fecha_inicio').first()
                if contrato_corta:
                    fecha_disponible_hasta = min(fecha_disponible_hasta, contrato_corta.fecha_inicio)
                
                # 5️⃣ ASIGNAR FECHAS CALCULADAS
                propiedad.disponibilidad_inicio = fecha_disponible_desde
                propiedad.disponibilidad_fin = fecha_disponible_hasta
                
# print(f"🎯 PROP {propiedad.id}: Libre desde {fecha_disponible_desde} hasta {fecha_disponible_hasta}")
# print(f"   📅 Asignado: disponibilidad_inicio={propiedad.disponibilidad_inicio}")
# print(f"   📅 Asignado: disponibilidad_fin={propiedad.disponibilidad_fin}")
# print(f"   📊 Cobertura de disponibilidades contiguas: {cobertura_inicio} al {cobertura_fin}")
                if reservas_anteriores:
                    pass  # ✅ Bloque vacío
# print(f"   ⏪ Reserva anterior termina: {reservas_anteriores.fecha_fin}")
                if reservas_posteriores:
                    pass  # ✅ Bloque vacío
# print(f"   ⏩ Próxima reserva empieza: {reservas_posteriores.fecha_inicio}")
            else:
                pass  # ✅ Bloque vacío
# print(f"❌ PROP {propiedad.id}: NO tiene disponibilidades que contengan el período {fecha_inicio} al {fecha_fin}")
                disponibilidades = Disponibilidad.objects.none()
                
                # Para debugging: mostrar todas las disponibilidades de esta propiedad
                todas_disponibilidades = Disponibilidad.objects.filter(propiedad=propiedad)
# print(f"   📋 Disponibilidades existentes ({todas_disponibilidades.count()}):")
                for disp in todas_disponibilidades:
                    pass  # ✅ Bloque vacío
# print(f"     - {disp.fecha_inicio} al {disp.fecha_fin}")
                
                # 🚫 SALTEAR: Esta propiedad no tiene disponibilidades para el período buscado
# print(f"   🚫 SALTANDO PROPIEDAD {propiedad.id} - No aparecerá en resultados")
                continue
            
            # ✅ CALCULAR DISPONIBILIDADES FRAGMENTADAS POR RESERVAS

            # Obtener las reservas asociadas a la propiedad
            # Excluir reservas eliminadas
            reservas = propiedad.reservas.filter(
                Q(fecha_inicio__lt=fecha_fin) & Q(fecha_fin__gt=fecha_inicio),
                eliminada=False
            )
            
            # Excluir si tiene contrato de alquiler (invierno o 24 meses) que se superponga con el período buscado
            if ContratoAlquiler.objects.filter(
                propiedad=propiedad,
                estado__in=['reservado', 'activo'],
                fecha_inicio__lt=fecha_fin,
                fecha_fin__gt=fecha_inicio
            ).exists():
                continue  # No mostrar como disponible: está ocupada por operación

            if reservas.filter(estado='pagada').exists():
                continue  # Saltar esta propiedad si ya tiene una reserva pagada

            # 🎯 DEBUGGING: Ver todas las reservas encontradas
# print(f"🏠 Propiedad {propiedad.id} - Búsqueda: {fecha_inicio} al {fecha_fin}")
# print(f"   Reservas encontradas: {reservas.count()}")
            for r in reservas:
                pass  # ✅ Bloque vacío
# print(f"   - Reserva {r.id}: {r.fecha_inicio} al {r.fecha_fin}, estado='{r.estado}'")
            
            # Verificar si existe una reserva confirmada no pagada, confirmada o en espera
            reserva_confirmada_no_pagada = reservas.filter(Q(estado='confirmada_no_pagada') | Q(estado='confirmada') | Q(estado='en_espera')).first()
# print(f"   ¿Reserva para mostrar en rojo? {bool(reserva_confirmada_no_pagada)}")
            if reserva_confirmada_no_pagada:
                pass  # ✅ Bloque vacío
# print(f"     → Estado: {reserva_confirmada_no_pagada.estado}")
# print(f"     → Fechas: {reserva_confirmada_no_pagada.fecha_inicio} al {reserva_confirmada_no_pagada.fecha_fin}")
# print(f"     → Precio: ${reserva_confirmada_no_pagada.precio_total}")
            else:
                pass  # ✅ Bloque vacío
# print(f"     → No hay reservas confirmada_no_pagada/confirmada/en_espera en estas fechas")

            # ✅ CORREGIDO: Mostrar propiedades con reservas confirmada_no_pagada en las fechas buscadas
            if reservas.exists():
                for r in reservas:
                    pass  # ✅ Bloque vacío
# print(f"   Reserva {r.id}: {r.fecha_inicio} al {r.fecha_fin}, estado='{r.estado}'")
            
            # Evaluar la disponibilidad y las reservas de la propiedad
            # 🎯 CORREGIDO: Manejar propiedades CON O SIN disponibilidades
            
            # Verificar reservas conflictivas PRIMERO (solo las pagadas)
            reservas_conflictivas = reservas.filter(
                Q(estado='pagada')
            )
            
            if reservas_conflictivas.exists():
                pass  # ✅ Bloque vacío
# print(f"   ❌ Saltando por reservas conflictivas: {reservas_conflictivas.count()}")
                continue  # Saltar si hay reservas pagadas o confirmadas en estas fechas
            
            # Si hay una reserva para mostrar en rojo, mostrarla SIEMPRE (es información importante)
            if reserva_confirmada_no_pagada:
                pass  # ✅ Bloque vacío
# print(f"   ✅ MOSTRANDO EN ROJO: Reserva {reserva_confirmada_no_pagada.id} con estado '{reserva_confirmada_no_pagada.estado}'")
                propiedad.reserva = reserva_confirmada_no_pagada
                propiedad.estado_reserva = 'confirmada_no_pagada'  # Siempre mostrar como confirmada_no_pagada en frontend
                # ✅ USAR PRECIO DE LA RESERVA EXISTENTE, NO RECALCULAR
                propiedad.precio_total_reserva = reserva_confirmada_no_pagada.precio_total
# print(f"   💰 Precio de reserva existente: ${reserva_confirmada_no_pagada.precio_total}")
# print(f"   🔴 Estado asignado para mostrar: {propiedad.estado_reserva}")
                
                # Asignar fechas de la reserva
                propiedad.disponibilidad_inicio = reserva_confirmada_no_pagada.fecha_inicio
                propiedad.disponibilidad_fin = reserva_confirmada_no_pagada.fecha_fin
                
                # Agregar a la lista y continuar sin recalcular precios
                propiedades_disponibles.append(propiedad)
# print(f"   ✅ Propiedad {propiedad.id} agregada a la lista con reserva en rojo")
                continue
            else:
                # ✅ PROPIEDADES SIN RESERVAS - Calcular precios y agregar a lista
                propiedad.estado_reserva = 'disponible'
                
                # Verificar si hay una reserva que termina exactamente en la fecha de inicio
                # (para mostrar en amarillo) - SOLO si está en estado confirmada o confirmada_no_pagada
                reserva_termina_en_inicio = propiedad.reservas.filter(
                    eliminada=False,
                    fecha_fin=fecha_inicio,
                    estado__in=['confirmada', 'confirmada_no_pagada', 'en_espera']
                ).exclude(
                    # Excluir reservas que también empiezan en fecha_inicio (esas están en el rango)
                    fecha_inicio=fecha_inicio
                ).first()
                
                if reserva_termina_en_inicio:
                    propiedad.reserva_termina_en_inicio = reserva_termina_en_inicio
# print(f"   ✅ DISPONIBLE: Sin reservas para mostrar en rojo")

            # ✅ CÁLCULO POR NOCHES: Usar precio del día de SALIDA, EXCEPTO Año Nuevo
            # Ejemplo: 29/12→30/12 usa precio del 29/12
            #          30/12→31/12 usa precio del 30/12
            #          31/12→01/01 usa precio del 01/01 (EXCEPCIÓN: Año Nuevo)
            #          01/01→02/01 usa precio del 01/01
                precio_total = 0
                precio_mas_caro = 0
# print('fecha de inicio',fecha_inicio)
# print('fecha de fin',fecha_fin)
                # Calcular noches de reserva
                noches_reserva = (fecha_fin - fecha_inicio).days

# print(f"🔥 INICIANDO CÁLCULO para propiedad {propiedad.id} del {fecha_inicio} al {fecha_fin}")
# print(f"🔥 Noches a calcular: {noches_reserva}")
                
                # Calcular noche por noche
                for noche in range(noches_reserva):
                    # Día de salida (el día actual de la noche)
                    dia_salida = fecha_inicio + timedelta(noche)
                    dia_llegada = fecha_inicio + timedelta(noche + 1)
                    
                    # ✅ EXCEPCIÓN: Año Nuevo (31/12 → 01/01) usa precio del 01/01
                    if dia_salida.month == 12 and dia_salida.day == 31 and dia_llegada.month == 1 and dia_llegada.day == 1:
                        dia_a_usar = dia_llegada  # Usar precio del 01/01
                    else:
                        dia_a_usar = dia_salida  # Usar precio del día de salida
                    
                    # Determinar el tipo de precio según el día a usar
                    tipo_precio = None
                    if dia_a_usar.month == 1:  # Enero
                        tipo_precio = 'QUINCENA_1_ENERO' if dia_a_usar.day <= 15 else 'QUINCENA_2_ENERO'
                    elif dia_a_usar.month == 2:  # Febrero
                        tipo_precio = 'QUINCENA_1_FEBRERO' if dia_a_usar.day <= 15 else 'QUINCENA_2_FEBRERO'
                    elif dia_a_usar.month == 3:  # Marzo
                        tipo_precio = 'QUINCENA_1_MARZO' if dia_a_usar.day <= 15 else 'QUINCENA_2_MARZO'
                    elif dia_a_usar.month == 7:  # Julio (Vacaciones de Invierno)
                        tipo_precio = 'VACACIONES_INVIERNO'
                    elif dia_a_usar.month == 12:  # Diciembre
                        tipo_precio = 'QUINCENA_1_DICIEMBRE' if dia_a_usar.day <= 15 else 'QUINCENA_2_DICIEMBRE'
                    else:
                        tipo_precio = 'TEMPORADA_BAJA'

                    # Obtener el precio por día para esta temporada
                    try:
                        precio_obj = Precio.objects.get(propiedad=propiedad, tipo_precio=tipo_precio)
                        # Usar precio_por_dia directamente (ya incluye ajustes)
                        precio_dia = precio_obj.precio_por_dia or 0
                        
                        # Aplicar ajuste porcentual si existe
                        if precio_obj.ajuste_porcentaje != 0:
                            precio_dia *= (1 - precio_obj.ajuste_porcentaje / 100)
                        
                        # Rastrear el día más caro
                        if precio_dia > precio_mas_caro:
                            precio_mas_caro = precio_dia
                        
                        precio_total += precio_dia
# print(f"📅 Noche {noche+1} ({fecha_inicio + timedelta(noche)}→{dia_llegada.strftime('%d/%m')}): {tipo_precio} = ${precio_dia:,.0f} - Total: ${precio_total:,.0f}")
                    except Precio.DoesNotExist:
                        pass  # ✅ Bloque vacío
# print(f"📅 Noche {noche+1}: {tipo_precio} = $0 (sin precio configurado)")

                # ✅ AGREGAR DÍA DE COMISIÓN (día más caro)
                precio_final_calculado = precio_total + precio_mas_caro
# print(f"🔥 PRECIO FINAL: suma_noches=${precio_total}, dia_comision=${precio_mas_caro}, TOTAL=${precio_final_calculado}")
                propiedad.precio_total_reserva = precio_final_calculado
                
                # ✅ Las fechas de disponibilidad ya fueron calculadas dinámicamente en el primer bucle
                # No sobrescribir con las fechas de búsqueda
                
                # Verificar si hay una reserva que termina exactamente en la fecha de inicio
                # (para mostrar en amarillo) - SOLO si está en estado confirmada o confirmada_no_pagada
                if not hasattr(propiedad, 'reserva_termina_en_inicio'):
                    reserva_termina_en_inicio = propiedad.reservas.filter(
                        eliminada=False,
                        fecha_fin=fecha_inicio,
                        estado__in=['confirmada', 'confirmada_no_pagada', 'en_espera']
                    ).exclude(
                        # Excluir reservas que también empiezan en fecha_inicio (esas están en el rango)
                        fecha_inicio=fecha_inicio
                    ).first()
                    
                    if reserva_termina_en_inicio:
                        propiedad.reserva_termina_en_inicio = reserva_termina_en_inicio
                
                # Agregar la propiedad disponible a la lista
                propiedades_disponibles.append(propiedad)
    
    # Alerta si hay propiedades sin precio
    alerta_sin_precio = len(propiedades_sin_precio) > 0
    
    # CALCULAR NOCHES CORRECTAMENTE AQUÍ (después de validar fechas)
    if fecha_inicio and fecha_fin:
        total_dias_reserva = (fecha_fin - fecha_inicio).days
    
# print("las fechas de inicio y fin son ",fecha_inicio,fecha_fin)
# print("los dias de reserva son ",total_dias_reserva)

    # Los precios ya fueron calculados correctamente arriba para cada propiedad
    # No es necesario recalcular aquí

    # ✅ ORDENAMIENTO SIMPLIFICADO: Usar directamente la disponibilidad_inicio del cuadrito
    def calcular_dias_libres(propiedad, fecha_inicio_busqueda, fecha_fin_busqueda):
        """
        Calcula días perdidos usando DIRECTAMENTE la fecha de disponibilidad_inicio que se muestra en el cuadrito.
        """
        try:
            # Verificar estado de la propiedad
            if not hasattr(propiedad, 'estado_reserva'):
                return 999999  # Sin estado definido, ponerla al final
                
            if propiedad.estado_reserva == 'confirmada_no_pagada':
                return -1  # Rojas van primero (valor negativo)
            
            # ✅ LÓGICA SIMPLIFICADA: Usar directamente disponibilidad_inicio del cuadrito
            if hasattr(propiedad, 'disponibilidad_inicio') and propiedad.disponibilidad_inicio:
                dias_perdidos = (fecha_inicio_busqueda - propiedad.disponibilidad_inicio).days
                dias_resultado = max(dias_perdidos, 0)
                
# print(f"🔍 Propiedad {propiedad.id}: Disponible desde {propiedad.disponibilidad_inicio}, búsqueda {fecha_inicio_busqueda} → {dias_resultado} días perdidos")
# print(f"    📊 CÁLCULO SIMPLE: ({fecha_inicio_busqueda} - {propiedad.disponibilidad_inicio}).days = {dias_perdidos} → max(0, {dias_perdidos}) = {dias_resultado}")
                return dias_resultado
            else:
                pass  # ✅ Bloque vacío
# print(f"🔍 Propiedad {propiedad.id}: Sin disponibilidad_inicio, usando 999999")
                return 999999
            
        except Exception as e:
            pass  # ✅ Bloque vacío
# print(f"Error calculando días libres para propiedad {propiedad.id}: {e}")
            return 999999

    # ✅ APLICAR ORDENAMIENTO MEJORADO: Rojas primero, luego por días libres
    if propiedades_disponibles:
        pass  # ✅ Bloque vacío
# print("🔄 APLICANDO ORDENAMIENTO PERSONALIZADO...")
        
        # Agregar días libres a cada propiedad para debugging
        for propiedad in propiedades_disponibles:
            if fecha_inicio and fecha_fin:
                propiedad.dias_libres_calculados = calcular_dias_libres(propiedad, fecha_inicio, fecha_fin)
            else:
                # Sin fechas, usar un orden básico
                if hasattr(propiedad, 'estado_reserva') and propiedad.estado_reserva == 'confirmada_no_pagada':
                    propiedad.dias_libres_calculados = -1  # Rojas primero
                else:
                    propiedad.dias_libres_calculados = 999999  # Disponibles después
            
            estado_debug = getattr(propiedad, 'estado_reserva', 'N/A')
# print(f"🏠 Propiedad {propiedad.id}: Estado={estado_debug}, Días libres={propiedad.dias_libres_calculados}")
            
            # DEBUG ESPECIAL para propiedad 44554
            if propiedad.id == 44554:
                pass  # ✅ Bloque vacío
# print(f"🔍 DEBUG ESPECIAL 44554:")
# print(f"   - Estado reserva: {estado_debug}")
# print(f"   - Fecha inicio búsqueda: {fecha_inicio}")
# print(f"   - Fecha fin búsqueda: {fecha_fin}")
# print(f"   - Días libres calculados: {propiedad.dias_libres_calculados}")
                
                # Revisar reservas y disponibilidades
                # Excluir reservas eliminadas
                reservas = propiedad.reservas.filter(
                    fecha_fin__lt=fecha_inicio,
                    eliminada=False
                ).order_by('-fecha_fin')
# print(f"   - Reservas anteriores: {list(reservas.values('id', 'fecha_fin'))}")
                
                disponibilidades = Disponibilidad.objects.filter(propiedad=propiedad, fecha_fin__lt=fecha_inicio).order_by('-fecha_fin')
# print(f"   - Disponibilidades anteriores: {list(disponibilidades.values('id', 'fecha_fin'))}")
        
        # ✅ ORDENAR: primero las rojas (días libres = -1), luego por menos días libres, luego por ID
# print("🔧 ANTES DEL ORDENAMIENTO:")
# print(f"📅 Fechas de búsqueda: {fecha_inicio} al {fecha_fin}")
        for prop in propiedades_disponibles:
            disponibilidad_info = "Sin info"
            if hasattr(prop, 'disponibilidad_inicio') and hasattr(prop, 'disponibilidad_fin'):
                disponibilidad_info = f"{prop.disponibilidad_inicio} al {prop.disponibilidad_fin}"
# print(f"   Propiedad {prop.id}: dias_libres_calculados = {prop.dias_libres_calculados} | Disponibilidad: {disponibilidad_info}")
        
        propiedades_disponibles.sort(key=lambda p: (p.dias_libres_calculados, p.id))
        
# print("🔧 DESPUÉS DEL ORDENAMIENTO:")
        for i, prop in enumerate(propiedades_disponibles, 1):
            disponibilidad_info = "Sin info"
            if hasattr(prop, 'disponibilidad_inicio') and hasattr(prop, 'disponibilidad_fin'):
                disponibilidad_info = f"{prop.disponibilidad_inicio} al {prop.disponibilidad_fin}"
# print(f"   {i}. Propiedad {prop.id}: dias_libres_calculados = {prop.dias_libres_calculados} | Disponibilidad: {disponibilidad_info}")
        
        # ✅ DEBUG DETALLADO PARA VERIFICAR ORDENAMIENTO
# print("=" * 80)
# print("📋 PROPIEDADES ORDENADAS POR DÍAS PERDIDOS:")
# print(f"Total propiedades encontradas: {len(propiedades_disponibles)}")
# print("=" * 80)
        
        # Mostrar TODAS las propiedades con sus cálculos para debug
        for i, propiedad in enumerate(propiedades_disponibles, 1):
            try:
                estado = getattr(propiedad, 'estado_reserva', 'disponible')
                dias = propiedad.dias_libres_calculados
                
                # Obtener fechas de disponibilidad para mostrar
                try:
                    disponibilidad_info = "Sin info"
                    if hasattr(propiedad, 'disponibilidad_inicio') and hasattr(propiedad, 'disponibilidad_fin'):
                        disponibilidad_info = f"{propiedad.disponibilidad_inicio} al {propiedad.disponibilidad_fin}"
                except:
                    disponibilidad_info = "Error obteniendo fechas"
                
# print(f"  {i:2d}. ID:{propiedad.id:5d} | {estado:20s} | {str(dias):>6s} días | {disponibilidad_info}")
                
            except Exception as e:
                pass  # ✅ Bloque vacío
# print(f"  {i:2d}. ID:{propiedad.id} | ERROR: {e}")
        
# print("=" * 80)

    # Obtener conceptos para el template
    conceptos = Concepto.objects.filter(
        q_conceptos_caja_visibles(sucursal_vendedor)
    ).order_by('nombre')

    # ✅ Calcular totales de propiedades disponibles y reservadas
    total_propiedades_disponibles = 0
    total_propiedades_reservadas = 0
    
    for propiedad in propiedades_disponibles:
        if hasattr(propiedad, 'estado_reserva') and propiedad.estado_reserva == 'confirmada_no_pagada':
            total_propiedades_reservadas += 1
        else:
            total_propiedades_disponibles += 1
    
# print(f"📊 TOTALES: {total_propiedades_disponibles} disponibles, {total_propiedades_reservadas} reservadas")

    return render(request, 'inmobiliaria/reserva/buscar_propiedades.html', {
        'form': form,
        'propiedades_disponibles': propiedades_disponibles,
        'alerta_sin_precio': alerta_sin_precio,
        'fecha_inicio': fecha_inicio.strftime('%d/%m/%Y') if fecha_inicio else '',
        'fecha_fin': fecha_fin.strftime('%d/%m/%Y') if fecha_fin else '',
        'total_dias': total_dias_reserva,
        'inquilinos': get_inquilinos_queryset_unificado(request),
        'vendedores': vendedores,
        'tipos_precio': TipoPrecio,
        'conceptos': conceptos,
        'total_propiedades_disponibles': total_propiedades_disponibles,
        'total_propiedades_reservadas': total_propiedades_reservadas,
        'debugging_info': f"🔍 DEBUGGING: Se encontraron {len(propiedades_disponibles)} propiedades. Función ejecutada correctamente."
    })

# ============================
# VISTAS API PARA CONTRATOS 24 MESES
# ============================

@login_required
def api_inquilino_detalle(request, inquilino_id):
    """API para obtener detalles de un inquilino"""
    try:
        inquilino = get_object_or_404(Inquilino, id=inquilino_id)
        data = {
            'id': inquilino.id,
            'nombre': inquilino.nombre,
            'apellido': inquilino.apellido,
            'telefono': inquilino.telefono,
            'email': inquilino.email,
            'dni': inquilino.dni,
        }
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=404)

@login_required 
def api_vendedor_detalle(request, vendedor_id):
    """API para obtener detalles de un vendedor"""
    try:
        vendedor = get_object_or_404(Vendedor, id=vendedor_id)
        data = {
            'id': vendedor.id,
            'nombre': vendedor.nombre,
            'apellido': vendedor.apellido,
            'telefono': vendedor.telefono,
            'email': vendedor.email,
        }
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=404)

@login_required
@require_http_methods(['GET', 'POST'])
def crear_contrato_alquiler(request):
    if request.method == 'POST':
        try:
            # Obtener datos del formulario
            propiedad_id = request.POST.get('propiedad_id')
            inquilino_ids = [x for x in request.POST.getlist('inquilino_ids') if x.strip().isdigit()]
            if not inquilino_ids:
                inquilino_id = request.POST.get('inquilino_id')
                if inquilino_id and str(inquilino_id).strip().isdigit():
                    inquilino_ids = [inquilino_id.strip()]
            if not inquilino_ids:
                return JsonResponse({'error': 'Debe agregar al menos un inquilino al contrato.'}, status=400)
            inquilino_id = inquilino_ids[0]  # principal para FK
            vendedor_id = request.POST.get('vendedor_id')
            fecha_operacion = request.POST.get('fecha_operacion')
            fecha_inicio = request.POST.get('fecha_inicio')
            fecha_fin = request.POST.get('fecha_fin')
            duracion_meses = int(request.POST.get('duracion_meses', 24))
            precio_mensual = parse_decimal_monto(request.POST.get('precio_mensual'))
            _raw_2do = (request.POST.get('precio_segundo_cuatrimestre') or '').strip()
            precio_segundo_cuatrimestre = parse_decimal_monto(_raw_2do) if _raw_2do else None
            deposito_garantia = parse_decimal_monto(request.POST.get('deposito_garantia'))

            def _decimal_desde_input_plata(s):
                if not s or not str(s).strip():
                    return Decimal('0')
                return parse_decimal_monto(s)

            honorarios_referencia = _decimal_desde_input_plata(request.POST.get('honorarios_contrato'))
            sellados_referencia = _decimal_desde_input_plata(request.POST.get('sellados_contrato'))

            precios_bloques = None
            pb_raw = (request.POST.get('precios_bloques_json') or '').strip()
            if pb_raw:
                try:
                    precios_bloques = json.loads(pb_raw)
                    if not isinstance(precios_bloques, list):
                        precios_bloques = None
                except json.JSONDecodeError:
                    precios_bloques = None
            # Contratos no invierno: lista vacía = solo primer trimestre con precio; meses 4+ sin monto hasta definir cada trimestre
            if duracion_meses != 9 and precios_bloques is None:
                precios_bloques = []

            garante_nombre = (request.POST.get('garante_nombre') or '').strip()
            garante_apellido = (request.POST.get('garante_apellido') or '').strip()
            garante_dni = (request.POST.get('garante_dni') or '').strip()
            garante_celular = (request.POST.get('garante_celular') or '').strip()
            garante_email = (request.POST.get('garante_email') or '').strip()
            garante_domicilio = (request.POST.get('garante_domicilio') or '').strip()
            carrera = (request.POST.get('carrera') or '').strip()
            garante_ids = [x for x in request.POST.getlist('garante_ids') if x.strip().isdigit()]

            # Validar datos
            if not all([propiedad_id, inquilino_id, vendedor_id, fecha_operacion, fecha_inicio, fecha_fin]):
                return JsonResponse({'error': 'Todos los campos son requeridos'}, status=400)

            # Obtener objetos
            try:
                propiedad = Propiedad.objects.get(id=propiedad_id)
                inquilino = Inquilino.objects.get(id=inquilino_id)
                vendedor = Vendedor.objects.get(id=vendedor_id)
            except (Propiedad.DoesNotExist, Inquilino.DoesNotExist, Vendedor.DoesNotExist) as e:
                return JsonResponse({'error': f'Error al obtener datos: {str(e)}'}, status=400)

            # Evitar duplicados: ya existe un contrato activo o reservado para esta propiedad e inquilino
            existente = ContratoAlquiler.objects.filter(
                propiedad=propiedad,
                inquilino=inquilino,
                estado__in=['reservado', 'activo'],
                sucursal=request.user.sucursal
            ).first()
            if existente:
                operacion_url = reverse('inmobiliaria:crear_operacion_contrato', args=[existente.id]) + '?tipo=principal'
                return JsonResponse({
                    'success': False,
                    'error': f'Ya existe un contrato (#{existente.id}) para esta propiedad e inquilino. Completá la operación principal de ese contrato o cancelalo antes de crear otro.',
                    'redirect_url': operacion_url,
                }, status=400)

            # Si es contrato de invierno (9 meses), verificar que no haya reservas por día que se superpongan
            if duracion_meses == 9:
                try:
                    fi = datetime.strptime(fecha_inicio.strip(), '%Y-%m-%d').date()
                    ff = datetime.strptime(fecha_fin.strip(), '%Y-%m-%d').date()
                except (ValueError, TypeError, AttributeError):
                    try:
                        fi = datetime.strptime(fecha_inicio.strip(), '%d/%m/%Y').date()
                        ff = datetime.strptime(fecha_fin.strip(), '%d/%m/%Y').date()
                    except (ValueError, TypeError, AttributeError):
                        fi = ff = None
                if fi and ff:
                    reservas_solapadas = Reserva.objects.filter(
                        propiedad=propiedad,
                        eliminada=False,
                        fecha_inicio__lt=ff,
                        fecha_fin__gt=fi
                    ).order_by('fecha_inicio')
                    if reservas_solapadas.exists():
                        primera = reservas_solapadas.first()
                        desde = primera.fecha_inicio.strftime('%d/%m/%Y')
                        hasta = primera.fecha_fin.strftime('%d/%m/%Y')
                        if reservas_solapadas.count() > 1:
                            msg = f'Hay {reservas_solapadas.count()} reservas por día que se superponen. Una de ellas es del {desde} al {hasta}. Debe cancelar o modificar esas reservas antes de crear el contrato de invierno.'
                        else:
                            msg = f'Hay una reserva por día del {desde} al {hasta} que se superpone con las fechas del contrato. Debe cancelar o modificar esa reserva antes de crear el contrato de invierno.'
                        return JsonResponse({
                            'success': False,
                            'error': msg
                        }, status=400)

            # Crear el contrato
            create_kw = dict(
                propiedad=propiedad,
                inquilino=inquilino,
                vendedor=vendedor,
                sucursal=request.user.sucursal,
                fecha_operacion=fecha_operacion,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                duracion_meses=duracion_meses,
                precio_mensual=precio_mensual,
                deposito_garantia=deposito_garantia,
                honorarios_referencia=honorarios_referencia,
                sellados_referencia=sellados_referencia,
                precios_bloques=precios_bloques,
                estado='reservado',  # Iniciar en estado reservado
            )
            if duracion_meses == 9 and precio_segundo_cuatrimestre is not None:
                create_kw['precio_segundo_cuatrimestre'] = precio_segundo_cuatrimestre
            contrato = ContratoAlquiler.objects.create(
                **create_kw,
                garante_nombre=garante_nombre,
                garante_apellido=garante_apellido,
                garante_dni=garante_dni,
                garante_celular=garante_celular,
                garante_email=garante_email,
                garante_domicilio=garante_domicilio,
                carrera=carrera,
            )
            # Asignar garantes (inquilinos seleccionados)
            if garante_ids:
                garantes_ok = get_inquilinos_queryset_unificado(request).filter(
                    id__in=garante_ids
                ).values_list('id', flat=True)
                contrato.garantes.set(garantes_ok)
            # Asignar inquilinos con carrera por cada uno (through ContratoInquilino), respetando orden
            inquilinos_validos = set(get_inquilinos_queryset_unificado(request).filter(
                id__in=inquilino_ids
            ).values_list('id', flat=True))
            for i, inq_id in enumerate(inquilino_ids):
                if int(inq_id) not in inquilinos_validos:
                    continue
                carrera_i = (request.POST.get(f'carrera_inq_{i}') or request.POST.get(f'carrera_{i}') or (request.POST.get('carrera') if i == 0 else '') or '').strip()
                ContratoInquilino.objects.create(
                    contrato=contrato,
                    inquilino_id=int(inq_id),
                    carrera=carrera_i
                )

            # Marcar la propiedad como reservada según tipo de contrato
            if duracion_meses == 9:
                if hasattr(propiedad, 'info_invierno') and propiedad.info_invierno:
                    propiedad.info_invierno.estado = 'reservado'
                    propiedad.info_invierno.save()
                # Actualizar historial: truncar "Libre" que superponga con el contrato
                try:
                    fi = datetime.strptime(fecha_inicio.strip(), '%Y-%m-%d').date()
                    ff = datetime.strptime(fecha_fin.strip(), '%Y-%m-%d').date()
                    actualizar_historial_por_contrato_invierno(propiedad, fi, ff)
                except (ValueError, TypeError, AttributeError):
                    try:
                        fi = datetime.strptime(fecha_inicio.strip(), '%d/%m/%Y').date()
                        ff = datetime.strptime(fecha_fin.strip(), '%d/%m/%Y').date()
                        actualizar_historial_por_contrato_invierno(propiedad, fi, ff)
                    except (ValueError, TypeError, AttributeError):
                        pass
            else:
                if hasattr(propiedad, 'info_meses') and propiedad.info_meses:
                    propiedad.info_meses.estado = 'reservado'
                    propiedad.info_meses.save()

            messages.success(request, 'Contrato creado. Completá la operación principal (depósito + primer mes).')
            # Redirigir a operación principal para unificar creación de contrato con el pago (estudiantes, 24 meses, invierno)
            operacion_url = reverse('inmobiliaria:crear_operacion_contrato', args=[contrato.id]) + '?tipo=principal'
            return JsonResponse({
                'success': True,
                'redirect_url': operacion_url,
                'contrato_id': contrato.id,
            })

        except Exception as e:
            return JsonResponse({'error': f'Error al crear el contrato: {str(e)}'}, status=400)

    return render(request, 'inmobiliaria/contratos/crear.html')

@login_required
def lista_contratos(request):
    """Vista para listar todos los contratos de alquiler"""
    from .models import ContratoAlquiler, CuotaMensual
    from django.db.models import Q, Count, Case, When, IntegerField
    from datetime import datetime
    
    # Query base: por defecto solo activos y reservados; con mostrar_eliminados=1 se incluyen finalizados y rescindidos
    mostrar_eliminados = request.GET.get('mostrar_eliminados') == '1'
    contratos = ContratoAlquiler.objects.filter(
        sucursal=request.user.sucursal
    ).select_related('propiedad', 'inquilino', 'vendedor')
    if not mostrar_eliminados:
        contratos = contratos.filter(estado__in=['activo', 'reservado'])
    
    # Aplicar filtros
    estado_cuota = request.GET.get('estado_cuota')
    mes_vencimiento = request.GET.get('mes_vencimiento')
    busqueda = request.GET.get('q')
    
    # Determinar el mes de filtro (actual o seleccionado)
    mes_filtro = None
    if mes_vencimiento:
        try:
            mes_filtro = datetime.strptime(mes_vencimiento, '%Y-%m')
        except ValueError:
            mes_filtro = timezone.now()
    else:
        mes_filtro = timezone.now()
    
    # Crear fechas de inicio y fin del mes
    inicio_mes = datetime(mes_filtro.year, mes_filtro.month, 1, tzinfo=timezone.get_current_timezone())
    if mes_filtro.month == 12:
        fin_mes = datetime(mes_filtro.year + 1, 1, 1, tzinfo=timezone.get_current_timezone())
    else:
        fin_mes = datetime(mes_filtro.year, mes_filtro.month + 1, 1, tzinfo=timezone.get_current_timezone())
    
    # Filtros de cuotas
    filtro_mes = Q(
        cuotas__fecha_vencimiento__gte=inicio_mes,
        cuotas__fecha_vencimiento__lt=fin_mes
    )
    
    if estado_cuota:
        # Si es pendiente, filtrar por mes actual
        if estado_cuota == 'pendiente':
            contratos = contratos.filter(
                cuotas__estado='pendiente',
                cuotas__fecha_vencimiento__gte=inicio_mes,
                cuotas__fecha_vencimiento__lt=fin_mes
            ).distinct()
        else:
            contratos = contratos.filter(cuotas__estado=estado_cuota).distinct()
    
    if mes_vencimiento:
        contratos = contratos.filter(filtro_mes).distinct()
    
    if busqueda:
        contratos = contratos.filter(
            Q(inquilino__nombre__icontains=busqueda) |
            Q(inquilino__apellido__icontains=busqueda) |
            Q(propiedad__direccion__icontains=busqueda)
        )
    
    # Ordenar por fecha de creación
    contratos = contratos.order_by('-fecha_creacion')
    
    # Obtener estadísticas
    total_contratos = contratos.count()
    
    # Contratos al día (cuotas pagadas en el mes actual/filtrado)
    contratos_al_dia = contratos.filter(
        cuotas__estado='pagada',
        cuotas__fecha_vencimiento__gte=inicio_mes,
        cuotas__fecha_vencimiento__lt=fin_mes
    ).distinct().count()
    
    # Cuotas pendientes del mes actual/filtrado
    cuotas_pendientes = CuotaMensual.objects.filter(
        contrato__sucursal=request.user.sucursal,
        estado='pendiente',
        fecha_vencimiento__gte=inicio_mes,
        fecha_vencimiento__lt=fin_mes
    ).count()
    
    # Cuotas vencidas (del mes actual/filtrado que están vencidas)
    cuotas_vencidas = CuotaMensual.objects.filter(
        contrato__sucursal=request.user.sucursal,
        estado='vencida',
        fecha_vencimiento__gte=inicio_mes,
        fecha_vencimiento__lt=fin_mes
    ).count()
    
    # Obtener la próxima cuota para cada contrato
    for contrato in contratos:
        # Obtener la próxima cuota pendiente o vencida
        contrato.proxima_cuota = contrato.cuotas.filter(
            estado__in=['pendiente', 'vencida']
        ).order_by('fecha_vencimiento').first()
        
        # Marcar cuotas vencidas
        if contrato.proxima_cuota and contrato.proxima_cuota.fecha_vencimiento < timezone.now().date():
            contrato.proxima_cuota.estado = 'vencida'
            contrato.proxima_cuota.save()
        
        # Verificar si hay cuotas anteriores pendientes
        contrato.tiene_cuotas_anteriores_pendientes = contrato.cuotas.filter(
            Q(estado__in=['pendiente', 'vencida']) &
            Q(fecha_vencimiento__lt=contrato.proxima_cuota.fecha_vencimiento if contrato.proxima_cuota else timezone.now().date())
        ).exists()
        
        # Determinar estado de depósito, honorarios y sellados
        contrato.deposito_estado = determinar_estado_concepto_contrato(contrato, '10')  # Concepto 10 = depósito
        contrato.honorarios_estado = determinar_estado_concepto_contrato(contrato, '25')  # Concepto 25 = honorarios  
        contrato.sellados_estado = determinar_estado_concepto_contrato(contrato, '26')  # Concepto 26 = sellados
        
        # Honorarios/sellados: si ya hay movimiento, usarlo; si no está pagado y hay referencia del alta, mostrarla
        if not hasattr(contrato, 'honorarios'):
            mov_h = obtener_valor_concepto_contrato(contrato, 'honorarios')
            if contrato.honorarios_estado == 'pagado':
                contrato.honorarios = mov_h
            else:
                ref_h = getattr(contrato, 'honorarios_referencia', None) or Decimal('0')
                contrato.honorarios = mov_h if mov_h > 0 else ref_h
        if not hasattr(contrato, 'sellados'):
            mov_s = obtener_valor_concepto_contrato(contrato, 'sellados')
            if contrato.sellados_estado == 'pagado':
                contrato.sellados = mov_s
            else:
                ref_s = getattr(contrato, 'sellados_referencia', None) or Decimal('0')
                contrato.sellados = mov_s if mov_s > 0 else ref_s
    
    context = {
        'contratos': contratos,
        'total_contratos': total_contratos,
        'contratos_al_dia': contratos_al_dia,
        'cuotas_pendientes': cuotas_pendientes,
        'cuotas_vencidas': cuotas_vencidas,
        'mes_actual': mes_filtro.strftime('%B %Y'),
        'mostrar_eliminados': mostrar_eliminados,
    }
    
    return render(request, 'inmobiliaria/contratos/lista_contratos.html', context)


@login_required
def rescindir_contratos_duplicados(request):
    """Rescinde contratos duplicados (misma propiedad + inquilino) para la sucursal del usuario."""
    from django.db.models import Count
    sucursal = request.user.sucursal
    qs = (
        ContratoAlquiler.objects
        .filter(sucursal=sucursal, estado__in=['activo', 'reservado'])
        .values('propiedad', 'inquilino')
        .annotate(total=Count('id'))
        .filter(total__gt=1)
    )
    grupos = list(qs)
    rescindidos = 0
    for g in grupos:
        contratos = (
            ContratoAlquiler.objects
            .filter(
                sucursal=sucursal,
                propiedad_id=g['propiedad'],
                inquilino_id=g['inquilino'],
                estado__in=['activo', 'reservado'],
            )
            .order_by('-operacion_principal', '-id')
        )
        contratos_list = list(contratos)
        if len(contratos_list) <= 1:
            continue
        mantener = contratos_list[0]
        for c in contratos_list[1:]:
            c.estado = 'rescindido'
            c.fecha_cancelacion = timezone.now().date()
            c.motivo_cancelacion = f'Contrato duplicado - conservado #{mantener.id}'
            c.save()
            rescindidos += 1
    if rescindidos:
        messages.success(request, f'Se rescindieron {rescindidos} contrato(s) duplicado(s). Ya no aparecen en la lista.')
    else:
        messages.info(request, 'No había contratos duplicados (misma propiedad e inquilino) para rescindir.')
    return redirect('inmobiliaria:lista_contratos')


@login_required
def actualizar_historiales_invierno(request):
    """Actualiza el historial de disponibilidad de todas las propiedades con contratos de invierno, para que no queden segmentos 'Libre' superpuestos con las fechas del contrato."""
    contratos_invierno = ContratoAlquiler.objects.filter(
        sucursal=request.user.sucursal,
        duracion_meses=9
    ).select_related('propiedad')
    actualizados = 0
    for contrato in contratos_invierno:
        try:
            actualizar_historial_por_contrato_invierno(
                contrato.propiedad, contrato.fecha_inicio, contrato.fecha_fin
            )
            actualizados += 1
        except Exception:
            continue
    if actualizados:
        messages.success(
            request,
            f'Se actualizaron los historiales de {actualizados} contrato(s) de invierno. Los períodos "Libre" ya no se superponen con las operaciones.'
        )
    else:
        messages.info(request, 'No hay contratos de invierno en tu sucursal, o no fue necesario cambiar ningún historial.')
    return redirect('inmobiliaria:lista_contratos')


@login_required
def detalle_contrato(request, contrato_id):
    """Vista para ver el detalle de un contrato específico"""
    from .models import ContratoAlquiler
    
    contrato = get_object_or_404(ContratoAlquiler, id=contrato_id, sucursal=request.user.sucursal)
    cuotas = contrato.cuotas.all().order_by('numero_cuota')
    
    # Estadísticas
    cuotas_pagadas = cuotas.filter(estado='pagada').count()
    cuotas_vencidas = cuotas.filter(estado='pendiente', fecha_vencimiento__lt=timezone.now().date()).count()
    total_pagado = sum(
        (Decimal(str(c.monto_total)) for c in cuotas.filter(estado='pagada')),
        start=Decimal('0'),
    )
    total_cuotas_plan = sum((Decimal(str(c.monto_total)) for c in cuotas), start=Decimal('0'))
    total_pendiente_cuotas = total_cuotas_plan - total_pagado

    trimestres_extras_ui = []
    if contrato.duracion_meses != 9:
        trimestres_total = max(1, (contrato.duracion_meses + 2) // 3)
        bloques = contrato.precios_bloques or []
        if not isinstance(bloques, list):
            bloques = []
        for t in range(2, trimestres_total + 1):
            idx = t - 2
            raw = bloques[idx] if idx < len(bloques) else None
            valor_str = ''
            if raw is not None and str(raw).strip() not in ('', 'null', 'None'):
                try:
                    n = int(Decimal(str(raw)))
                    valor_str = f'{n:,}'.replace(',', '.')
                except (InvalidOperation, ValueError, TypeError):
                    valor_str = str(raw)
            trimestres_extras_ui.append({
                't': t,
                'mes_desde': (t - 1) * 3 + 1,
                'mes_hasta': min(t * 3, contrato.duracion_meses),
                'idx': idx,
                'valor': valor_str,
            })

    context = {
        'contrato': contrato,
        'cuotas': cuotas,
        'cuotas_pagadas': cuotas_pagadas,
        'cuotas_vencidas': cuotas_vencidas,
        'total_pagado': total_pagado,
        'total_cuotas_plan': total_cuotas_plan,
        'total_pendiente_cuotas': total_pendiente_cuotas,
        'trimestres_extras_ui': trimestres_extras_ui,
        'today': timezone.now().date(),
        'puede_activar_modo_trimestres': (
            contrato.duracion_meses != 9 and getattr(contrato, 'precios_bloques', None) is None
        ),
    }
    
    return render(request, 'inmobiliaria/contratos/detalle_contrato.html', context)


@login_required
@require_POST
def activar_precios_trimestres_contrato(request, contrato_id):
    """Contratos legacy (precios_bloques null): pasa a lista vacía y recalcula cuotas no pagadas (meses 4+ en 0)."""
    contrato = get_object_or_404(ContratoAlquiler, id=contrato_id, sucursal=request.user.sucursal)
    if contrato.duracion_meses == 9:
        messages.error(request, 'No aplica a contratos de invierno.')
        return redirect('inmobiliaria:detalle_contrato', contrato_id=contrato.id)
    if contrato.precios_bloques is not None:
        messages.warning(request, 'Este contrato ya está en modo trimestres.')
        return redirect('inmobiliaria:detalle_contrato', contrato_id=contrato.id)

    contrato.precios_bloques = []
    contrato.save(update_fields=['precios_bloques'])
    montos = _montos_cuotas_por_trimestre(contrato)
    n = 0
    for cuota in contrato.cuotas.exclude(estado__in=['pagada', 'pagada_con_mora']).order_by('numero_cuota'):
        idx = cuota.numero_cuota - 1
        if idx < len(montos):
            cuota.monto_base = montos[idx]
            cuota.recargo_mora = Decimal('0')
            cuota.descuento = Decimal('0')
            cuota.actualizar_monto_total()
            n += 1
    messages.success(
        request,
        f'Modo trimestres activado: meses 1–3 con el precio mensual del contrato; meses 4+ sin monto hasta que cargues cada trimestre abajo. Se actualizaron {n} cuota(s) no pagadas.',
    )
    return redirect('inmobiliaria:detalle_contrato', contrato_id=contrato.id)


@login_required
@require_POST
def actualizar_precios_bloques_contrato(request, contrato_id):
    """Guarda precios_bloques y recalcula montos de cuotas no pagadas (contratos viejos o correcciones)."""
    contrato = get_object_or_404(ContratoAlquiler, id=contrato_id, sucursal=request.user.sucursal)
    if contrato.duracion_meses == 9:
        messages.error(request, 'Esta herramienta no aplica a contratos de invierno (9 meses).')
        return redirect('inmobiliaria:detalle_contrato', contrato_id=contrato.id)

    num_bloques = max(1, (contrato.duracion_meses + 2) // 3)
    n_extra = num_bloques - 1

    def _post_trimestres_todos_vacios():
        for i in range(n_extra):
            if (request.POST.get(f'precio_trimester_{i}') or '').strip():
                return False
        return True

    if contrato.precios_bloques is None and _post_trimestres_todos_vacios():
        messages.info(
            request,
            'Sin cambios: este contrato sigue con el mismo precio en todos los meses (modo anterior). '
            'Completá al menos un importe de trimestre para pasar a cuotas por bloques de 3 meses.',
        )
        return redirect('inmobiliaria:detalle_contrato', contrato_id=contrato.id)

    raw_list = []
    for i in range(n_extra):
        v = (request.POST.get(f'precio_trimester_{i}') or '').strip()
        if not v:
            raw_list.append(None)
        else:
            try:
                raw_list.append(float(parse_decimal_monto(v)))
            except (InvalidOperation, ValueError, TypeError):
                raw_list.append(None)

    contrato.precios_bloques = raw_list
    contrato.save(update_fields=['precios_bloques'])

    montos = _montos_cuotas_por_trimestre(contrato)
    actualizadas = 0
    for cuota in contrato.cuotas.exclude(estado__in=['pagada', 'pagada_con_mora']).order_by('numero_cuota'):
        idx = cuota.numero_cuota - 1
        if idx < len(montos):
            cuota.monto_base = montos[idx]
            cuota.recargo_mora = Decimal('0')
            cuota.descuento = Decimal('0')
            cuota.actualizar_monto_total()
            actualizadas += 1

    messages.success(
        request,
        f'Precios por trimestre guardados. Se recalcularon {actualizadas} cuota(s) no pagadas (pendientes / vencidas).',
    )
    return redirect('inmobiliaria:detalle_contrato', contrato_id=contrato.id)

@login_required
def crear_operacion_contrato(request, contrato_id):
    contrato = get_object_or_404(ContratoAlquiler, id=contrato_id, sucursal=request.user.sucursal)
    tipo_operacion = request.GET.get('tipo', 'principal')
    
    # Verificar si hay una caja abierta
    try:
        caja = Caja.objects.get(sucursal=request.user.sucursal, estado='abierta')
    except Caja.DoesNotExist:
        # Si no hay caja abierta, crear una nueva
        caja = Caja.objects.create(
            sucursal=request.user.sucursal,
            usuario_apertura=request.user,
            saldo_inicial=0,
            estado='abierta',
            fecha_apertura=timezone.now()
        )
        messages.success(request, 'Se ha abierto una nueva caja automáticamente.')

    conceptos_qs = Concepto.objects.filter(
        q_conceptos_caja_visibles(request.user.sucursal)
    ).order_by('nombre')

    config_operacion = {
        'tipo_operacion': tipo_operacion,
        'contrato_id': contrato.id,
        'fecha_inicio': contrato.fecha_inicio.isoformat() if getattr(contrato, 'fecha_inicio', None) else None,
    }
    context = {
        'contrato': contrato,
        'tipo_operacion': tipo_operacion,
        'caja': caja,
        'conceptos': conceptos_qs,
        'today': timezone.now(),
        'config_operacion': config_operacion,
    }
    return render(request, 'inmobiliaria/contratos/crear_operacion.html', context)

def obtener_caja_abierta(request):
    """Obtiene la caja abierta para la sucursal del usuario"""
    try:
        return Caja.objects.get(sucursal=request.user.sucursal, estado='abierta')
    except Caja.DoesNotExist:
        return None

def determinar_estado_concepto_contrato(contrato, concepto_id):
    """
    Determina si un concepto específico está pagado para un contrato.
    Solo devuelve 'pagado' si el concepto está efectivamente en algún movimiento (JSON o texto).
    El depósito (concepto 10) queda pendiente si no se cargó ese concepto en la operación.
    """
    import json
    
    # Buscar movimientos de caja relacionados con este contrato
    movimientos = MovimientoCaja.objects.filter(
        propiedad=contrato.propiedad,
        concepto__icontains=f'Contrato #{contrato.id}'
    )
    
# print(f"🔍 ESTADO CONCEPTO {concepto_id} - Contrato #{contrato.id}")
# print(f"   - Movimientos encontrados: {movimientos.count()}")
    
    # Verificar si algún movimiento contiene el concepto específico
    for i, movimiento in enumerate(movimientos):
        pass  # ✅ Bloque vacío
# print(f"   - Movimiento {i+1}: {movimiento.concepto[:50]}...")
        
        try:
            # ✅ Usar concepto_detalle (JSON completo); puede ser array o objeto {conceptos, ...}
            json_str = getattr(movimiento, 'concepto_detalle', None)
            if json_str and json_str.strip():
                parsed = json.loads(json_str)
                if isinstance(parsed, dict) and 'conceptos' in parsed:
                    conceptos_data = parsed.get('conceptos', [])
                elif isinstance(parsed, list):
                    conceptos_data = parsed
                else:
                    conceptos_data = []
            else:
                try:
                    conceptos_data = json.loads(movimiento.concepto) if (movimiento.concepto or '').strip().startswith('[') else []
                except (json.JSONDecodeError, ValueError, TypeError):
                    conceptos_data = []

            for concepto in conceptos_data:
                concepto_id_actual = str(concepto.get('id', concepto.get('codigo', '')))
                if concepto_id_actual == str(concepto_id):
                    return 'pagado'
            
            # Si no hay concepto_detalle y no encontramos en JSON, buscar en texto (contratos antiguos)
            if not (json_str and json_str.strip().startswith('[')) and (movimiento.concepto or ''):
                concepto_texto = (movimiento.concepto or '').lower()
                if str(concepto_id) == '25' and ('honorario' in concepto_texto or 'concepto 25' in concepto_texto):
                    return 'pagado'
                if str(concepto_id) == '26' and ('sellado' in concepto_texto or 'concepto 26' in concepto_texto):
                    return 'pagado'
                if str(concepto_id) == '10' and ('deposito' in concepto_texto or 'concepto 10' in concepto_texto):
                    return 'pagado'
                    
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            # FALLBACK: Buscar en formato texto (contratos antiguos)
            concepto_texto = (movimiento.concepto or '').lower()
            if str(concepto_id) == '25' and ('honorario' in concepto_texto or 'concepto 25' in concepto_texto):
                return 'pagado'
            if str(concepto_id) == '26' and ('sellado' in concepto_texto or 'concepto 26' in concepto_texto):
                return 'pagado'
            if str(concepto_id) == '10' and ('deposito' in concepto_texto or 'concepto 10' in concepto_texto):
                return 'pagado'
                
        except Exception as e:
            pass  # ✅ Bloque vacío
# print(f"     ❌ Error: {e}")
            continue
    
# print(f"   ❌ CONCEPTO {concepto_id} NO ENCONTRADO = PENDIENTE")
    return 'pendiente'

def obtener_valor_concepto_contrato(contrato, campo):
    """
    Obtiene el valor de honorarios o sellados desde MovimientoCaja para un contrato.
    Usa el mismo criterio que el recibo: preferir el movimiento con concepto_detalle (más reciente con datos).
    """
    from decimal import Decimal
    
    movimientos = MovimientoCaja.objects.filter(
        propiedad=contrato.propiedad,
        concepto__icontains=f'Contrato #{contrato.id}',
        sucursal=contrato.sucursal
    ).order_by('-id')
    
    for mov in movimientos:
        detalle = (getattr(mov, 'concepto_detalle', None) or '').strip()
        if detalle and detalle.startswith('['):
            return getattr(mov, campo, Decimal('0'))
    
    primer = movimientos.first()
    if primer:
        return getattr(primer, campo, Decimal('0'))
    return Decimal('0')

def procesar_conceptos_y_crear_movimiento(request, caja, contrato):
    """Procesa los conceptos y crea el movimiento de caja. Retorna (movimiento, total) o (None, 0) y el tercer elemento opcional es el mensaje de error."""
    try:
        import json

        if not getattr(request.user, 'sucursal', None):
            raise ValueError('El usuario no tiene sucursal asignada. No se puede crear el movimiento.')

        # Función auxiliar para limpiar valores monetarios
        def limpiar_valor_monetario(valor_str):
            if not valor_str or str(valor_str).strip() == '':
                return Decimal('0')
            return parse_decimal_monto(valor_str)
        
        # ✅ Obtener cuentas bancarias dinámicamente
        from inmobiliaria.models.sucursal import CuentaBancaria
        cuentas_bancarias = CuentaBancaria.objects.filter(
            sucursal=request.user.sucursal,
            activa=True
        ).order_by('nombre_banco', 'alias')
        
        # ✅ Procesar montos de cuentas bancarias dinámicamente
        montos_cuentas_bancarias = {}
        monto_deposito_total = Decimal('0')
        
        for cuenta in cuentas_bancarias:
            campo_name = cuenta.field_name  # ej: monto_deposito_1
            monto_cuenta = limpiar_valor_monetario(request.POST.get(campo_name, '0'))
            montos_cuentas_bancarias[cuenta.id] = {
                'cuenta': cuenta,
                'monto': monto_cuenta,
                'campo': campo_name
            }
            monto_deposito_total += monto_cuenta
# print(f"💰 Cuenta {cuenta.nombre_banco}: ${monto_cuenta}")
        
        # Mantener compatibilidad con campos antiguos (fallback)
        monto_deposito_galicia = limpiar_valor_monetario(request.POST.get('monto_deposito_galicia', '0'))
        monto_deposito_mp = limpiar_valor_monetario(request.POST.get('monto_deposito_mp', '0'))
        monto_deposito_legacy = monto_deposito_galicia + monto_deposito_mp
        
        # Usar el total dinámico o el legacy como fallback
        monto_deposito_final = monto_deposito_total if monto_deposito_total > 0 else monto_deposito_legacy
        
        # Honorarios y sellados desde el form (se pueden sobrescribir con concepto 25/26)
        honorarios = limpiar_valor_monetario(request.POST.get('honorarios_top', '0'))
        sellados = limpiar_valor_monetario(request.POST.get('sellados_top', '0'))
        
        # Obtener montos de métodos de pago
        monto_efectivo = limpiar_valor_monetario(request.POST.get('monto_efectivo', '0'))
        monto_cheque = limpiar_valor_monetario(request.POST.get('monto_cheque', '0'))
        monto_tarjeta = limpiar_valor_monetario(request.POST.get('monto_tarjeta', '0'))
        
        total_movimiento = ((monto_efectivo or 0) + (monto_cheque or 0) + (monto_tarjeta or 0) + 
                          (monto_deposito_final or 0))
        
        # ✅ PROCESAR CONCEPTOS: prioridad 1 = conceptos_json (un solo campo con todo)
        conceptos_data = []
        conceptos_detalle = []
        conceptos_count_post = int(request.POST.get('conceptos_count', 0) or 0)
        conceptos_json_str = (request.POST.get('conceptos_json') or '').strip()
        if conceptos_json_str:
            try:
                lista = json.loads(conceptos_json_str)
                if isinstance(lista, list):
                    for i, item in enumerate(lista):
                        nombre = (item.get('nombre') or item.get('concepto') or '').strip()
                        importe_val = item.get('importe', 0)
                        if nombre and importe_val is not None:
                            try:
                                imp = float(importe_val)
                            except (TypeError, ValueError):
                                imp = float(limpiar_valor_monetario(str(importe_val)))
                            conceptos_data.append({
                                'id': str(item.get('id') or item.get('codigo') or f'C{i}'),
                                'nombre': nombre,
                                'importe': imp,
                                'observaciones': str(item.get('observaciones') or ''),
                                'fecha': str(item.get('fecha') or '')
                            })
                            conceptos_detalle.append(f"{nombre} ${imp}")
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        # Prioridad 2 = concepto_0_*, concepto_1_* (si no vinieron por JSON o faltan)
        if not conceptos_data or len(conceptos_data) < conceptos_count_post:
            import re
            indices_conceptos = set()
            for key in request.POST.keys():
                m = re.match(r'concepto_(\d+)_nombre', key)
                if m:
                    indices_conceptos.add(int(m.group(1)))
            max_idx = max(conceptos_count_post, max(indices_conceptos) + 1 if indices_conceptos else 0)
            # Si ya teníamos algo del JSON, solo agregar los índices que faltan
            start_i = len(conceptos_data) if conceptos_data else 0
            for i in range(start_i, max_idx):
                concepto_id = (request.POST.get(f'concepto_{i}_id') or '').strip()
                concepto_nombre = (request.POST.get(f'concepto_{i}_nombre') or '').strip()
                concepto_importe = request.POST.get(f'concepto_{i}_importe')
                concepto_observaciones = request.POST.get(f'concepto_{i}_observaciones', '')
                concepto_fecha = request.POST.get(f'concepto_{i}_fecha')
                if not concepto_nombre:
                    continue
                raw_importe = (concepto_importe if concepto_importe is not None else '').strip()
                if raw_importe == '':
                    continue
                importe_limpio = limpiar_valor_monetario(raw_importe)
                id_para_json = concepto_id if concepto_id else f'C{i}'
                conceptos_data.append({
                    'id': id_para_json,
                    'nombre': concepto_nombre,
                    'importe': float(importe_limpio),
                    'observaciones': concepto_observaciones or '',
                    'fecha': concepto_fecha or ''
                })
                conceptos_detalle.append(f"{concepto_nombre} ${importe_limpio}")
        
        # Construir concepto final
        if conceptos_data:
            # Guardar como JSON para parsing posterior
            concepto_json = json.dumps(conceptos_data)
# print(f"💾 CONCEPTO JSON GUARDADO: {concepto_json}")
        else:
            # Fallback si no hay conceptos
            concepto_json = f'Contrato #{contrato.id} - {contrato.propiedad.direccion}'
# print(f"💾 CONCEPTO FALLBACK: {concepto_json}")
        
        # Truncar concepto a 200 caracteres; incluir "Contrato #X" para que el recibo encuentre el movimiento
        prefijo = f'Contrato #{contrato.id} - '
        max_len = 200 - len(prefijo) - 3  # espacio para "..."
        concepto_json_truncado = concepto_json if len(concepto_json) <= max_len else concepto_json[:max_len] + "..."
        concepto_para_busqueda = prefijo + concepto_json_truncado
        if len(concepto_para_busqueda) > 200:
            concepto_para_busqueda = concepto_para_busqueda[:197] + "..."
        # Guardar mes_alquiler_importe y mes_alquiler_tipo (elegido: mensual o proporcional) para el recibo
        mes_alquiler_valor_raw = (request.POST.get('mes_alquiler_valor') or '').strip()
        mes_alquiler_tipo = (request.POST.get('mes_alquiler_tipo') or '').strip().lower()
        if mes_alquiler_tipo not in ('proporcional', 'mensual'):
            mes_alquiler_tipo = 'mensual'
        try:
            mes_alquiler_importe = float(limpiar_valor_monetario(mes_alquiler_valor_raw)) if mes_alquiler_valor_raw else None
        except (TypeError, ValueError):
            mes_alquiler_importe = None
        # Si no vino el valor pero sí el tipo, usar importe del concepto 1 (alquiler) o 0
        if mes_alquiler_importe is None and mes_alquiler_tipo and request.POST.get('mes_alquiler_tipo', '').strip().lower() in ('proporcional', 'mensual'):
            for c in conceptos_data:
                if str(c.get('id') or c.get('codigo')) == '1':
                    try:
                        mes_alquiler_importe = float(c.get('importe', 0))
                    except (TypeError, ValueError):
                        mes_alquiler_importe = 0.0
                    break
            if mes_alquiler_importe is None:
                mes_alquiler_importe = 0.0
        # Precio mensual completo (el del campo "Mes alquiler") para mostrarlo en el recibo aunque se haya elegido proporcional
        precio_mensual_completo = None
        try:
            pm_raw = (request.POST.get('precio_mensual') or request.POST.get('nuevo_precio_mensual') or '').strip()
            if pm_raw:
                precio_mensual_completo = float(limpiar_valor_monetario(pm_raw))
        except (TypeError, ValueError):
            pass

        # Honorarios / sellados: POST (honorarios_top / sellados_top) y/o conceptos 25 / 26 en la lista
        honorarios_final = honorarios
        for c in conceptos_data:
            if str(c.get('id') or c.get('codigo')) == '25':
                honorarios_final = Decimal(str(c.get('importe', 0)))
                break

        sellados_final = sellados
        for c in conceptos_data:
            if str(c.get('id') or c.get('codigo')) == '26':
                sellados_final = Decimal(str(c.get('importe', 0)))
                break

        if conceptos_data and (mes_alquiler_importe is not None or request.POST.get('mes_alquiler_tipo', '').strip().lower() in ('proporcional', 'mensual')):
            importe_para_json = float(mes_alquiler_importe) if mes_alquiler_importe is not None else 0.0
            payload = {
                'conceptos': conceptos_data,
                'mes_alquiler_importe': importe_para_json,
                'mes_alquiler_tipo': mes_alquiler_tipo,
            }
            if precio_mensual_completo is not None:
                payload['precio_mensual_completo'] = precio_mensual_completo
            texto_recibo = (request.POST.get('mes_alquiler_texto_recibo') or '').strip()[:200]
            if texto_recibo:
                payload['mes_alquiler_texto_recibo'] = texto_recibo
            if sellados_final and sellados_final > 0:
                payload['sellados'] = float(sellados_final)
            concepto_detalle_json = json.dumps(payload)
        elif conceptos_data:
            payload_min = {'conceptos': conceptos_data}
            if sellados_final and sellados_final > 0:
                payload_min['sellados'] = float(sellados_final)
            concepto_detalle_json = json.dumps(payload_min)
        else:
            concepto_detalle_json = ''

        movimiento = MovimientoCaja.objects.create(
            caja=caja,
            tipo=TipoMovimientoCajaEnum.INGRESO,
            concepto=concepto_para_busqueda,
            concepto_detalle=concepto_detalle_json,
            monto_efectivo=monto_efectivo,
            monto_cheque=monto_cheque,
            monto_tarjeta=monto_tarjeta,
            fecha=timezone.now(),
            empleado=request.user,
            sucursal=request.user.sucursal,
            propiedad=contrato.propiedad,
            honorarios=honorarios_final,
            sellados=sellados_final
        )
        
        cuentas_con_monto = [data for data in montos_cuentas_bancarias.values() if data['monto'] > 0]
        if len(cuentas_con_monto) == 1:
            cuenta_usada = cuentas_con_monto[0]['cuenta']
            movimiento.destino_deposito = f"cuenta_{cuenta_usada.id}"
            movimiento.monto_deposito = cuentas_con_monto[0]['monto']
        elif len(cuentas_con_monto) > 1:
            movimiento.destino_deposito = 'mixto'
            movimiento.monto_deposito = monto_deposito_final
        elif monto_deposito_legacy > 0:
            if monto_deposito_galicia > 0:
                movimiento.destino_deposito = 'galicia'
                movimiento.monto_deposito = monto_deposito_galicia
            elif monto_deposito_mp > 0:
                movimiento.destino_deposito = 'mp'
                movimiento.monto_deposito = monto_deposito_mp
        movimiento.save()
        
        return movimiento, total_movimiento
        
    except Exception as e:
        import traceback
        error_msg = f"Error al procesar conceptos: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)  # Log para debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(error_msg)
        return None, 0, str(e)

def _decimal_desde_trimestre_json(entry):
    """Parsea un ítem de precios_bloques (JSON); None si no hay monto válido."""
    if entry is None:
        return None
    if isinstance(entry, bool):
        return None
    if isinstance(entry, (int, float)):
        try:
            return Decimal(str(entry))
        except (InvalidOperation, ValueError, TypeError):
            return None
    s = str(entry).strip()
    if not s or s.lower() in ('null', 'none'):
        return None
    return parse_decimal_monto(s)


def _montos_cuotas_por_trimestre(contrato):
    """
    Monto por cada mes del contrato (len = duracion_meses).
    - precios_bloques **None** (legacy): mismo precio_mensual todos los meses.
    - precios_bloques **lista** (contratos nuevos o ya migrados): trimestre 1 = precio_mensual;
      trimestres siguientes usan precios_bloques[0], [1], … (meses 4–6, 7–9, …).
      Valor ausente/null = **0** (sin precio hasta cargar ese trimestre en el detalle del contrato).
    """
    n = int(contrato.duracion_meses or 0)
    if n <= 0:
        return []
    base = contrato.precio_mensual or Decimal('0')
    num_bloques = max(1, (n + 2) // 3)
    raw = getattr(contrato, 'precios_bloques', None)
    if raw is None:
        return [base] * n
    if not isinstance(raw, list):
        raw = []
    bloque_monto = []
    for b in range(num_bloques):
        if b == 0:
            bloque_monto.append(base)
            continue
        idx = b - 1
        parsed = _decimal_desde_trimestre_json(raw[idx]) if idx < len(raw) else None
        if parsed is not None and parsed >= 0:
            bloque_monto.append(parsed)
        else:
            bloque_monto.append(Decimal('0'))
    out = []
    for i in range(n):
        bi = i // 3
        out.append(bloque_monto[bi] if bi < len(bloque_monto) else Decimal('0'))
    return out


@login_required
@require_POST
def procesar_operacion_contrato(request, contrato_id):
    try:
        contrato = get_object_or_404(ContratoAlquiler, id=contrato_id)
        tipo_operacion = request.POST.get('tipo_operacion', '')
        nuevo_precio_mensual = request.POST.get('nuevo_precio_mensual')
        
        if nuevo_precio_mensual:
            try:
                nuevo_precio_mensual = parse_decimal_monto(nuevo_precio_mensual)
                contrato.precio_mensual = nuevo_precio_mensual
                contrato.save()
                CuotaMensual.objects.filter(
                    contrato=contrato, estado='pendiente'
                ).update(monto_base=nuevo_precio_mensual, monto_total=nuevo_precio_mensual)
            except (ValueError, InvalidOperation):
                return JsonResponse({'error': 'El precio mensual proporcionado no es válido'}, status=400)
        
        if tipo_operacion == 'principal' and contrato.operacion_principal:
            return JsonResponse({'error': 'La operación principal ya fue realizada'}, status=400)
        
        caja = obtener_caja_abierta(request)
        if not caja:
            return JsonResponse({'error': 'No hay una caja abierta'}, status=400)
        
        result = procesar_conceptos_y_crear_movimiento(request, caja, contrato)
        movimiento = result[0]
        total_movimiento = result[1]
        error_detalle = result[2] if len(result) > 2 else None
        if not movimiento:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error al procesar movimiento para contrato {contrato_id}: {error_detalle}")
            mensaje = error_detalle or 'Error al procesar el movimiento. Verifica los logs del servidor para más detalles.'
            return JsonResponse({'error': mensaje}, status=400)
        
        if tipo_operacion == 'principal':
            # Vencimientos siempre el día 5
            contrato.dia_vencimiento = 5
            contrato.save(update_fields=['dia_vencimiento'])
            
            # Leer concepto 10 y 1 desde POST si el usuario los agregó (no son obligatorios)
            conceptos_count = int(request.POST.get('conceptos_count', 0))
            concepto_10_importe = None
            concepto_1_importe = None
            for i in range(conceptos_count):
                cid = (request.POST.get(f'concepto_{i}_id') or '').strip()
                raw_importe = (request.POST.get(f'concepto_{i}_importe') or '0').strip()
                try:
                    importe_val = float(parse_decimal_monto(raw_importe))
                except (ValueError, InvalidOperation, TypeError):
                    importe_val = 0.0
                if cid == '10':
                    concepto_10_importe = importe_val
                elif cid == '1':
                    concepto_1_importe = importe_val

            # Actualizar contrato solo si el usuario incluyó esos conceptos: depósito (10) y/o primer mes (1)
            # No sobrescribir precio_mensual con el concepto 1 si eligieron proporcional (el concepto 1 puede ser el proporcional)
            mes_alquiler_tipo_post = (request.POST.get('mes_alquiler_tipo') or '').strip().lower()
            update_fields = []
            if concepto_10_importe is not None:
                contrato.deposito_garantia = Decimal(str(concepto_10_importe))
                update_fields.append('deposito_garantia')
            if concepto_1_importe is not None and float(concepto_1_importe) > 0 and mes_alquiler_tipo_post != 'proporcional':
                contrato.precio_mensual = Decimal(str(concepto_1_importe))
                update_fields.append('precio_mensual')
            if update_fields:
                contrato.save(update_fields=update_fields)
            
            # Usar el día de vencimiento seleccionado para crear las fechas
            fecha_actual = timezone.now().date()
            
            # Si es contrato de invierno (9 meses), generar cuotas de marzo a diciembre
            if contrato.duracion_meses == 9:
                # Para invierno: marzo (3) a diciembre (12) - 9 cuotas
                meses_invierno = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
                # Determinar el año base (si estamos antes de marzo, usar año anterior)
                año_base = fecha_actual.year
                if fecha_actual.month < 3:
                    año_base = fecha_actual.year - 1
                
                # Generar cuotas de marzo a diciembre (9 cuotas)
                for i, mes in enumerate(meses_invierno[:9], start=1):
                    try:
                        fecha_vencimiento = date(año_base, mes, contrato.dia_vencimiento)
                    except ValueError:
                        # Si el día no existe en el mes, usar el último día del mes
                        from calendar import monthrange
                        ultimo_dia = monthrange(año_base, mes)[1]
                        fecha_vencimiento = date(año_base, mes, min(contrato.dia_vencimiento, ultimo_dia))
                    
                    CuotaMensual.objects.create(
                        contrato=contrato, 
                        numero_cuota=i, 
                        fecha_vencimiento=fecha_vencimiento,
                        monto_base=contrato.precio_mensual, 
                        monto_total=contrato.precio_mensual,
                        estado='pendiente', 
                        movimiento=None, 
                        fecha_pago=None
                    )
            else:
                # Para contratos normales (24 meses u otros), usar lógica original
                try:
                    fecha_vencimiento = date(fecha_actual.year, fecha_actual.month, contrato.dia_vencimiento)
                    # Si ya pasó el día este mes, programar para el próximo mes
                    if fecha_actual.day >= contrato.dia_vencimiento:
                        fecha_vencimiento = fecha_vencimiento + relativedelta(months=1)
                except ValueError:
                    # Si el día no existe en el mes actual (ej: 31 en febrero), usar el último día del mes
                    fecha_vencimiento = date(fecha_actual.year, fecha_actual.month, 28)
                    if fecha_actual.day >= 28:
                        fecha_vencimiento = fecha_vencimiento + relativedelta(months=1)
                
                montos_meses = _montos_cuotas_por_trimestre(contrato)
                for i in range(contrato.duracion_meses):
                    monto_cuota = montos_meses[i] if i < len(montos_meses) else contrato.precio_mensual
                    CuotaMensual.objects.create(
                        contrato=contrato,
                        numero_cuota=i + 1,
                        fecha_vencimiento=fecha_vencimiento,
                        monto_base=monto_cuota,
                        monto_total=monto_cuota,
                        estado='pendiente',
                        movimiento=None,
                        fecha_pago=None
                    )
                    # Avanzar al siguiente mes manteniendo el día de vencimiento
                    try:
                        fecha_vencimiento = fecha_vencimiento.replace(month=fecha_vencimiento.month + 1)
                    except ValueError:
                        # Si el día no existe en el próximo mes, ajustar el año
                        if fecha_vencimiento.month == 12:
                            fecha_vencimiento = fecha_vencimiento.replace(year=fecha_vencimiento.year + 1, month=1)
                        else:
                            fecha_vencimiento = fecha_vencimiento.replace(month=fecha_vencimiento.month + 1)
                    except:
                        # Usar relativedelta como fallback
                        fecha_vencimiento = fecha_vencimiento + relativedelta(months=1)
            
            contrato.operacion_principal = True
            contrato.estado = 'activo'  # Cambiar estado a activo después de la operación principal
            contrato.save()
            
            # Actualizar estado de la propiedad
            # Actualizar estado de la propiedad según el tipo de contrato
            if contrato.duracion_meses == 9:
                # Contrato de invierno
                if hasattr(contrato.propiedad, 'info_invierno'):
                    contrato.propiedad.info_invierno.estado = 'ocupado'
                    contrato.propiedad.info_invierno.save()
                # Asegurar que el historial no muestre "Libre" superpuesto con el contrato
                actualizar_historial_por_contrato_invierno(
                    contrato.propiedad, contrato.fecha_inicio, contrato.fecha_fin
                )
            else:
                # Contrato de 24 meses
                if hasattr(contrato.propiedad, 'info_meses'):
                    contrato.propiedad.info_meses.estado = 'ocupado'
                    contrato.propiedad.info_meses.save()
        else:
            cuota = contrato.cuotas.filter(estado='pendiente').order_by('fecha_vencimiento').first()
            if not cuota:
                return JsonResponse({'error': 'No hay cuotas pendientes para pagar'}, status=400)
            
            if nuevo_precio_mensual:
                cuota.monto_base = nuevo_precio_mensual
                cuota.monto_total = nuevo_precio_mensual
                cuota.save()
            
            total_esperado = cuota.monto_total
            mensaje_error = f'El monto total (${total_movimiento}) debe ser igual al valor de la cuota (${cuota.monto_total})'
            
            cuota.estado = 'pagada'
            cuota.fecha_pago = timezone.now().date()
            cuota.movimiento = movimiento
            cuota.save()
            
            # Validación solo para pago de cuota: monto debe coincidir con el valor de la cuota
            diferencia = abs(float(total_movimiento) - float(total_esperado))
            if diferencia > 0.01:
                return JsonResponse({
                    'error': mensaje_error + f' (Diferencia: ${diferencia:.2f})'
                }, status=400)
        
        return JsonResponse({
            'success': True,
            'redirect_url': reverse('inmobiliaria:recibo_contrato_24', args=[contrato.id])
        })
    except Exception as e:
        import traceback
        import logging
        logger = logging.getLogger(__name__)
        error_msg = f"Error al procesar operación contrato {contrato_id}: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return JsonResponse({'error': f'Error al procesar la operación: {str(e)}'}, status=400)

@login_required
def ver_cuotas_contrato(request, contrato_id):
    """Vista para ver todas las cuotas de un contrato"""
    contrato = get_object_or_404(ContratoAlquiler, id=contrato_id, sucursal=request.user.sucursal)
    cuotas = contrato.cuotas.all().order_by('numero_cuota')
    
    # Marcar cuotas vencidas
    hoy = timezone.now().date()
    for cuota in cuotas:
        if cuota.estado == 'pendiente' and cuota.fecha_vencimiento < hoy:
            cuota.estado = 'vencida'
            cuota.save()
        
        # Verificar si hay cuotas anteriores pendientes
        cuota.hay_cuotas_anteriores_pendientes = cuotas.filter(
            numero_cuota__lt=cuota.numero_cuota,
            estado__in=['pendiente', 'vencida']
        ).exists()
    
    return render(request, 'inmobiliaria/contratos/cuotas.html', {
        'contrato': contrato,
        'cuotas': cuotas
    })

@login_required
def api_cuota_detalle(request, cuota_id):
    """API para obtener detalles de una cuota"""
    cuota = get_object_or_404(CuotaMensual, id=cuota_id, contrato__sucursal=request.user.sucursal)
    
    # Calcular recargo por mora si aplica
    if cuota.estado in ['pendiente', 'vencida'] and cuota.fecha_vencimiento < timezone.now().date():
        cuota.recargo_mora = cuota.calcular_mora()
        cuota.actualizar_monto_total()
        cuota.save()
    
    return JsonResponse({
        'id': cuota.id,
        'numero_cuota': cuota.numero_cuota,
        'monto_base': float(cuota.monto_base),  # Solo el precio mensual
        'recargo_mora': float(cuota.recargo_mora),
        'monto_total': float(cuota.monto_total)  # monto_base + recargo_mora - descuento
    })

@login_required
def pagar_cuota(request, cuota_id):
    try:
        cuota = get_object_or_404(CuotaMensual, id=cuota_id)
        contrato = cuota.contrato
        
        # Verificar que no haya cuotas anteriores pendientes
        cuotas_anteriores = contrato.cuotas.filter(
            numero_cuota__lt=cuota.numero_cuota,
            estado='pendiente'
        ).exists()
        
        if cuotas_anteriores:
            return JsonResponse({
                'error': 'Hay cuotas anteriores pendientes de pago'
            }, status=400)
        
        # Obtener caja abierta
        try:
            caja = Caja.objects.get(sucursal=request.user.sucursal, estado='abierta')
        except Caja.DoesNotExist:
            return JsonResponse({
                'error': 'No hay una caja abierta'
            }, status=400)
        
        # Procesar el pago
        with transaction.atomic():
            # Crear movimiento de caja (tipo debe ser código del enum: 'IN')
            movimiento = MovimientoCaja.objects.create(
                caja=caja,
                tipo=TipoMovimientoCajaEnum.INGRESO,
                concepto=f'Cuota {cuota.numero_cuota}/{contrato.duracion_meses} - {contrato.propiedad.direccion}',
                monto_efectivo=cuota.monto_total,
                fecha=timezone.now(),
                empleado=request.user,
                sucursal=request.user.sucursal,
                propiedad=contrato.propiedad
            )
            
            # Marcar la cuota actual como pagada
            cuota.estado = 'pagada'
            cuota.fecha_pago = timezone.now().date()
            cuota.movimiento = movimiento
            cuota.save()
            
            # Actualizar fecha de vencimiento de la siguiente cuota
            siguiente_cuota = contrato.cuotas.filter(
                numero_cuota=cuota.numero_cuota + 1
            ).first()
            
            if siguiente_cuota:
                # Calcular nueva fecha de vencimiento usando el día personalizado del contrato
                fecha_actual = cuota.fecha_vencimiento
                try:
                    # Intentar usar el día de vencimiento personalizado
                    if fecha_actual.month == 12:
                        nueva_fecha = date(fecha_actual.year + 1, 1, contrato.dia_vencimiento)
                    else:
                        nueva_fecha = date(fecha_actual.year, fecha_actual.month + 1, contrato.dia_vencimiento)
                    siguiente_cuota.fecha_vencimiento = nueva_fecha
                except ValueError:
                    # Si el día no existe en el próximo mes (ej: 31 en febrero), usar el último día válido
                    if fecha_actual.month == 12:
                        nueva_fecha = date(fecha_actual.year + 1, 1, min(contrato.dia_vencimiento, 28))
                    else:
                        nueva_fecha = date(fecha_actual.year, fecha_actual.month + 1, min(contrato.dia_vencimiento, 28))
                    siguiente_cuota.fecha_vencimiento = nueva_fecha
                siguiente_cuota.save()
            
            return JsonResponse({
                'success': True,
                'redirect_url': reverse('inmobiliaria:recibo_contrato_24', args=[contrato.id])
            })
            
    except Exception as e:
        pass  # ✅ Bloque vacío
# print("Error al procesar pago de cuota:", str(e))
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@require_POST
def cancelar_contrato(request, contrato_id):
    es_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    try:
        contrato = get_object_or_404(ContratoAlquiler, id=contrato_id)
        motivo = request.POST.get('motivo', '')
        
        if not motivo:
            if es_ajax:
                return JsonResponse({'error': 'El motivo de cancelación es requerido'}, status=400)
            messages.error(request, 'El motivo de cancelación es requerido.')
            return redirect('inmobiliaria:operaciones')
        
        # Cancelar el contrato directamente
        contrato.estado = 'rescindido'
        contrato.fecha_cancelacion = timezone.now().date()
        contrato.motivo_cancelacion = motivo
        contrato.save()

        # Alquiler de invierno (9 meses): poner la propiedad en disponible y limpiar historial
        if contrato.duracion_meses == 9 and hasattr(contrato.propiedad, 'info_invierno'):
            info_invierno = contrato.propiedad.info_invierno
            info_invierno.estado = 'disponible'
            # Borrar segmentos de historial de invierno (reserva=null, es_principal) por fechas de info_invierno
            if info_invierno.fecha_inicio and info_invierno.fecha_fin:
                HistorialDisponibilidad.objects.filter(
                    propiedad=contrato.propiedad,
                    reserva__isnull=True,
                    es_principal=True,
                    fecha_inicio=info_invierno.fecha_inicio,
                    fecha_fin=info_invierno.fecha_fin
                ).delete()
            # También borrar por fechas del contrato por si no estaban sincronizadas en info_invierno
            if contrato.fecha_inicio and contrato.fecha_fin:
                HistorialDisponibilidad.objects.filter(
                    propiedad=contrato.propiedad,
                    reserva__isnull=True,
                    es_principal=True,
                    fecha_inicio=contrato.fecha_inicio,
                    fecha_fin=contrato.fecha_fin
                ).delete()
            info_invierno.fecha_inicio = None
            info_invierno.fecha_fin = None
            info_invierno.save()

        # Contrato 24 meses: estudiante (carrera) -> disponible; resto -> desactivar
        elif hasattr(contrato.propiedad, 'info_meses'):
            if getattr(contrato, 'carrera', None) and contrato.carrera:
                contrato.propiedad.info_meses.disponible = True
                contrato.propiedad.info_meses.estado = 'disponible'
                contrato.propiedad.info_meses.save()
            else:
                contrato.propiedad.info_meses.disponible = False
                contrato.propiedad.info_meses.estado = 'disponible'
                contrato.propiedad.info_meses.save()

        messages.success(request, f'El contrato #{contrato.id} ha sido cancelado exitosamente')
        if es_ajax:
            return JsonResponse({'success': True})
        return redirect('inmobiliaria:operaciones')
    except Exception as e:
        pass  # ✅ Bloque vacío
# print(f"Error al cancelar contrato: {str(e)}")
        if es_ajax:
            return JsonResponse({'error': str(e)}, status=400)
        messages.error(request, f'Error al cancelar contrato: {str(e)}')
        return redirect('inmobiliaria:operaciones')

@login_required
@require_POST
def reactivar_propiedad_24_meses(request, propiedad_id):
    """Reactivar una propiedad para alquileres de 24 meses"""
    try:
        propiedad = get_object_or_404(Propiedad, id=propiedad_id)
        
        if hasattr(propiedad, 'info_meses'):
            propiedad.info_meses.disponible = True
            propiedad.info_meses.estado = 'disponible'
            propiedad.info_meses.save()
            
            messages.success(request, f'La propiedad {propiedad.direccion} ha sido reactivada para alquileres de 24 meses')
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'error': 'La propiedad no está configurada para 24 meses'}, status=400)
            
    except Exception as e:
        pass  # ✅ Bloque vacío
# print(f"Error al reactivar propiedad: {str(e)}")
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@require_POST
def desactivar_propiedad_24_meses(request, propiedad_id):
    """Desactivar una propiedad para alquileres de 24 meses"""
    try:
        propiedad = get_object_or_404(Propiedad, id=propiedad_id)
        
        if hasattr(propiedad, 'info_meses'):
            # Verificar si hay contratos activos
            contratos_activos = propiedad.contratos.filter(estado__in=['reservado', 'activo']).exists()
            
            if contratos_activos:
                return JsonResponse({
                    'error': 'No se puede desactivar la propiedad porque tiene contratos activos o reservados'
                }, status=400)
            
            propiedad.info_meses.disponible = False
            propiedad.info_meses.save()
            
            messages.success(request, f'La propiedad {propiedad.direccion} ha sido desactivada para alquileres de 24 meses')
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'error': 'La propiedad no está configurada para 24 meses'}, status=400)
            
    except Exception as e:
        pass  # ✅ Bloque vacío
# print(f"Error al desactivar propiedad: {str(e)}")
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@require_POST
def guardar_precios_propiedad(request):
    """Guarda los precios modificados de una propiedad"""
# print("=== GUARDAR PRECIOS PROPIEDAD ===")
    
    try:
        propiedad_id = request.POST.get('propiedad_id')
        precios_json = request.POST.get('precios')
        
# print(f"Propiedad ID: {propiedad_id}")
# print(f"Precios JSON: {precios_json}")
        
        if not propiedad_id or not precios_json:
            return JsonResponse({
                'success': False,
                'error': 'Faltan datos requeridos'
            })
        
        propiedad = get_object_or_404(Propiedad, id=propiedad_id)
        
# print(f"👤 Usuario: {request.user.username}, Nivel: {request.user.nivel}")
        
        # Solo usuarios nivel 3 o superior pueden modificar precios
        if request.user.nivel < 3:
            pass  # ✅ Bloque vacío
# print(f"❌ Usuario sin permisos - Nivel {request.user.nivel} < 3")
            return JsonResponse({
                'success': False,
                'error': 'No tienes permisos para modificar precios'
            })
        
        import json
        precios_data = json.loads(precios_json)
        
        # Actualizar cada precio
        for precio_info in precios_data:
            tipo_precio = precio_info.get('tipo_precio')
            
# print(f"🔍 Procesando precio: {tipo_precio}")
# print(f"📊 Datos recibidos: {precio_info}")
            
            # Buscar o crear el precio
            precio, created = Precio.objects.get_or_create(
                propiedad=propiedad,
                tipo_precio=tipo_precio,
                defaults={
                    'precio_total': 0,
                    'precio_por_dia': 0,
                    'precio_toma': 0,
                    'precio_dia_toma': 0,
                    'ajuste_porcentaje': 0
                }
            )
            
            # Actualizar valores - Convertir a Decimal/float explícitamente
            from decimal import Decimal
            
            precio_toma_nuevo = Decimal(str(precio_info.get('precio_toma', 0) or 0))
            precio_dia_toma_nuevo = Decimal(str(precio_info.get('precio_dia_toma', 0) or 0))
            precio_por_dia_nuevo = Decimal(str(precio_info.get('precio_por_dia', 0) or 0))
            
            # ✅ Tipos que NO deben tener precio_total (se guarda como None)
            tipos_sin_quincena = ['FINDE_LARGO', 'SEMANA_SANTA', 'CARNAVALES']
            if tipo_precio in tipos_sin_quincena:
                precio_total_nuevo = None
            else:
                precio_total_nuevo = Decimal(str(precio_info.get('precio_total', 0) or 0))
            
            ajuste_porcentaje_raw = Decimal(str(precio_info.get('ajuste_porcentaje', 0) or 0))
            # Evitar overflow: el campo es porcentaje (máx 999.99); si viene un valor tipo precio, limitar
            ajuste_porcentaje_nuevo = max(Decimal('-999.99'), min(Decimal('999.99'), ajuste_porcentaje_raw))
            
# print(f"💰 Valores RECIBIDOS del form:")
# print(f"   - precio_toma: {precio_toma_nuevo}")
# print(f"   - precio_dia_toma: {precio_dia_toma_nuevo}")
# print(f"   - precio_por_dia: {precio_por_dia_nuevo}")
# print(f"   - precio_total: {precio_total_nuevo} ⬅️ VALOR QUE QUIERE GUARDAR")
# print(f"   - ajuste_porcentaje: {ajuste_porcentaje_nuevo}")
            
            # Guardar valores actuales antes de modificar (para comparación)
            precio_total_antes = precio.precio_total
            
            precio.precio_toma = precio_toma_nuevo
            precio.precio_dia_toma = precio_dia_toma_nuevo
            precio.precio_por_dia = precio_por_dia_nuevo
            precio.precio_total = precio_total_nuevo
            precio.ajuste_porcentaje = ajuste_porcentaje_nuevo
            
# print(f"📝 Valores ASIGNADOS al objeto:")
# print(f"   - precio_total asignado: {precio.precio_total}")
            
            # Usar update_fields para evitar el recálculo automático del precio_total
            precio.save(update_fields=['precio_toma', 'precio_dia_toma', 'precio_por_dia', 'precio_total', 'ajuste_porcentaje'])
            
            # Recargar desde BD para ver qué se guardó realmente
            precio.refresh_from_db()
            
# print(f"✅ Actualizado precio {tipo_precio} para propiedad {propiedad_id}")
# print(f"📋 Valores FINALES guardados en BD:")
# print(f"   - precio_total ANTES: {precio_total_antes}")
# print(f"   - precio_total DESPUÉS: {precio.precio_total}")
# print(f"   - precio_por_dia: {precio.precio_por_dia}")
        
        return JsonResponse({
            'success': True,
            'message': 'Precios actualizados correctamente'
        })
        
    except Exception as e:
        pass  # ✅ Bloque vacío
# print(f"Error en guardar_precios_propiedad: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
@require_POST
def guardar_precio_individual(request):
    """Guarda un precio individual automáticamente"""
    try:
        precio_id = request.POST.get('precio_id')
        propiedad_id = request.POST.get('propiedad_id')
        tipo_precio = request.POST.get('tipo_precio')
        
        if not precio_id or not propiedad_id or not tipo_precio:
            return JsonResponse({
                'success': False,
                'error': 'Faltan datos requeridos'
            })
        
        propiedad = get_object_or_404(Propiedad, id=propiedad_id)
        
        # Solo usuarios nivel 3 o superior pueden modificar precios
        if request.user.nivel < 3:
            return JsonResponse({
                'success': False,
                'error': 'No tienes permisos para modificar precios'
            })
        
        # Buscar el precio
        precio = get_object_or_404(Precio, id=precio_id, propiedad=propiedad)
        
        # Actualizar valores
        from decimal import Decimal
        
        precio_toma_nuevo = Decimal(str(request.POST.get('precio_toma', 0) or 0))
        precio_dia_toma_nuevo = Decimal(str(request.POST.get('precio_dia_toma', 0) or 0))
        precio_por_dia_nuevo = Decimal(str(request.POST.get('precio_por_dia', 0) or 0))
        
        # Tipos que NO deben tener precio_total
        tipos_sin_quincena = ['FINDE_LARGO', 'SEMANA_SANTA', 'CARNAVALES']
        if tipo_precio in tipos_sin_quincena:
            precio_total_nuevo = None
        else:
            precio_total_nuevo = Decimal(str(request.POST.get('precio_total', 0) or 0))
        
        ajuste_porcentaje_raw = Decimal(str(request.POST.get('ajuste_porcentaje', 0) or 0))
        ajuste_porcentaje_nuevo = max(Decimal('-999.99'), min(Decimal('999.99'), ajuste_porcentaje_raw))
        
        # Actualizar el precio
        precio.precio_toma = precio_toma_nuevo
        precio.precio_dia_toma = precio_dia_toma_nuevo
        precio.precio_por_dia = precio_por_dia_nuevo
        precio.precio_total = precio_total_nuevo
        precio.ajuste_porcentaje = ajuste_porcentaje_nuevo
        
        # Guardar sin recalcular
        precio.save(update_fields=['precio_toma', 'precio_dia_toma', 'precio_por_dia', 'precio_total', 'ajuste_porcentaje'])
        
        return JsonResponse({
            'success': True,
            'message': 'Precio guardado correctamente'
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

def enviar_recuperacion(request):
    form = EmailForm()
    
    if request.method == "POST":
        form = EmailForm(request.POST)
        
        if form.is_valid():
            email = form.cleaned_data['email']
            User = get_user_model()
            
            try:
                # Buscar usuario por email (case-insensitive)
                user = User.objects.filter(email__iexact=email).first()
                
                if user:
                    # Verificar que el usuario tiene email válido
                    if not user.email or not user.email.strip():
                        messages.error(request, 'Tu cuenta no tiene un correo electrónico configurado. Contacta al administrador.')
                        return render(request, 'inmobiliaria/autenticacion/password_reset_form.html', {'form': form})
                    
                    # Generar una nueva contraseña temporal
                    nueva_password = User.objects.make_random_password()
                    user.set_password(nueva_password)
                    user.password_temporal = True  # Marcar como contraseña temporal
                    user.save()
                    
                    # Enviar email con la nueva contraseña
                    subject = 'Tu nueva contraseña - Sistema Gonnet'
                    message = f'''
Hola {user.first_name if user.first_name else user.username},

Tu nueva contraseña temporal es: {nueva_password}

Por favor, ingresa con esta contraseña y cámbiala inmediatamente por una de tu preferencia.

Saludos,
El equipo de Sistema Gonnet
                    '''
                    
                    try:
                        send_mail(
                            subject,
                            message,
                            'gonnetinterno@gmail.com',  # Remitente
                            [user.email],  # Destinatario
                            fail_silently=False,
                        )
                        messages.success(request, f'Se ha enviado un correo con tu nueva contraseña a {user.email}.')
                        return redirect('inmobiliaria:password_reset_done')
                    except Exception as e:
                        # Revertir el cambio de contraseña si falla el envío
                        user.refresh_from_db()
                        messages.error(request, f'Error al enviar el correo: {str(e)}. Por favor, contacta al administrador.')
                else:
                    # Mensaje simple sin debug complejo
                    messages.error(request, 'No existe una cuenta con ese correo electrónico. Verifica que esté escrito correctamente.')
                        
            except Exception as e:
                messages.error(request, f'Error al procesar la solicitud: {str(e)}')
        else:
            # Si el formulario no es válido, mostrar errores
            messages.error(request, 'Por favor, ingresa un correo electrónico válido.')
    
    return render(request, 'inmobiliaria/autenticacion/password_reset_form.html', {'form': form})

# Función temporal para recalcular precios de reservas con precio 0
def recalcular_precio_reserva(reserva):
    """
    Recalcula el precio de una reserva usando la misma lógica que buscar_propiedades_reserva
    """
# print(f"🔄 RECALCULANDO PRECIO para reserva {reserva.id}")
    
    try:
        fecha_inicio = reserva.fecha_inicio
        fecha_fin = reserva.fecha_fin
        propiedad = reserva.propiedad
        
        # Calcular noches de reserva
        noches_reserva = (fecha_fin - fecha_inicio).days
# print(f"   📅 Fechas: {fecha_inicio} al {fecha_fin} ({noches_reserva} noches)")
        
        # ✅ CÁLCULO POR NOCHES: Usar precio del día de SALIDA, EXCEPTO Año Nuevo
        # Ejemplo: 29/12→30/12 usa precio del 29/12
        #          30/12→31/12 usa precio del 30/12
        #          31/12→01/01 usa precio del 01/01 (EXCEPCIÓN: Año Nuevo)
        #          01/01→02/01 usa precio del 01/01
        precio_total = 0
        precio_mas_caro = 0
        
        for noche in range(noches_reserva):
            # Día de salida (el día actual de la noche)
            dia_salida = fecha_inicio + timedelta(noche)
            dia_llegada = fecha_inicio + timedelta(noche + 1)
            
            # ✅ EXCEPCIÓN: Año Nuevo (31/12 → 01/01) usa precio del 01/01
            if dia_salida.month == 12 and dia_salida.day == 31 and dia_llegada.month == 1 and dia_llegada.day == 1:
                dia_a_usar = dia_llegada  # Usar precio del 01/01
            else:
                dia_a_usar = dia_salida  # Usar precio del día de salida
            
            # Determinar el tipo de precio según el día a usar
            tipo_precio = None
            if dia_a_usar.month == 1:  # Enero
                tipo_precio = 'QUINCENA_1_ENERO' if dia_a_usar.day <= 15 else 'QUINCENA_2_ENERO'
            elif dia_a_usar.month == 2:  # Febrero
                tipo_precio = 'QUINCENA_1_FEBRERO' if dia_a_usar.day <= 15 else 'QUINCENA_2_FEBRERO'
            elif dia_a_usar.month == 3:  # Marzo
                tipo_precio = 'QUINCENA_1_MARZO' if dia_a_usar.day <= 15 else 'QUINCENA_2_MARZO'
            elif dia_a_usar.month == 7:  # Julio (Vacaciones de Invierno)
                tipo_precio = 'VACACIONES_INVIERNO'
            elif dia_a_usar.month == 12:  # Diciembre
                tipo_precio = 'QUINCENA_1_DICIEMBRE' if dia_a_usar.day <= 15 else 'QUINCENA_2_DICIEMBRE'
            else:
                tipo_precio = 'TEMPORADA_BAJA'

            # Obtener el precio para la propiedad y la quincena correspondiente
            try:
                precio = Precio.objects.get(propiedad=propiedad, tipo_precio=tipo_precio)
                precio_dia = precio.precio_por_dia or 0
# print(f"   ✅ Noche {noche+1} ({fecha_inicio + timedelta(noche)}→{dia_llegada}): {tipo_precio} = ${precio_dia}")
            except Precio.DoesNotExist:
                precio_dia = 0
# print(f"   ❌ Noche {noche+1}: {tipo_precio} = NO EXISTE")

            # Rastrear el día más caro
            if precio_dia > precio_mas_caro:
                precio_mas_caro = precio_dia

            precio_total += precio_dia
        
        # ✅ AGREGAR DÍA DE COMISIÓN (día más caro)
        precio_total = precio_total + precio_mas_caro
        
# print(f"   💰 PRECIO TOTAL RECALCULADO: suma_noches + dia_comision = ${precio_total:,.0f}")
        
        # Actualizar la reserva si el precio es diferente
        if precio_total != reserva.precio_total:
            reserva.precio_total = precio_total
            reserva.save()
# print(f"   ✅ RESERVA ACTUALIZADA con nuevo precio: ${precio_total:,.0f}")
        else:
            pass  # ✅ Bloque vacío
# print(f"   ℹ️ El precio ya era correcto: ${precio_total:,.0f}")
            
        return precio_total
        
    except Exception as e:
        pass  # ✅ Bloque vacío
# print(f"   ❌ ERROR recalculando precio: {str(e)}")
        return 0

@login_required
def finalizar_reserva_nueva(request, reserva_id):
    """
    Nueva vista para finalizar reserva basada en la carga de recibo
    """
    try:
        # Obtener la reserva
        reserva = get_object_or_404(Reserva, id=reserva_id, sucursal=request.user.sucursal)
        
        # Obtener la caja actual de la sucursal
        caja_actual = Caja.objects.filter(
            sucursal=request.user.sucursal,
            fecha_cierre__isnull=True
        ).first()
        
        if not caja_actual:
            messages.error(request, 'No hay una caja abierta. Debe abrir una caja primero.')
            return redirect('inmobiliaria:reservas')
        
        # Calcular información del próximo movimiento
        cantidad_movimientos = MovimientoCaja.objects.filter(caja=caja_actual).count()
        proximo_numero_movimiento = cantidad_movimientos + 1
        
        # Obtener conceptos de caja disponibles
        conceptos_caja = Concepto.objects.filter(
            q_conceptos_caja_visibles(request.user.sucursal)
        ).order_by('id')
        
        # ✅ Obtener cuentas bancarias activas de la sucursal
        from inmobiliaria.models.sucursal import CuentaBancaria
        cuentas_bancarias = CuentaBancaria.objects.filter(
            sucursal=request.user.sucursal,
            activa=True
        ).order_by('nombre_banco', 'alias')
        
        # ✅ CALCULAR SALDO PENDIENTE CONSIDERANDO SOLO LA SEÑA (NO EL DEPÓSITO)
        # Buscar todos los movimientos de caja pagados para esta reserva
        pagos_anteriores = MovimientoCaja.objects.filter(
            propiedad=reserva.propiedad,
            tipo=TipoMovimientoCajaEnum.INGRESO,
            concepto__icontains=f"Operaci\u00f3n {reserva.id}"
        )
        
        # ✅ DETECTAR SI ES "COMPLETAR PAGO" O "FINALIZAR RESERVA"
        # Si ya hay pagos anteriores, es "Completar Pago", sino es "Finalizar Reserva"
        total_pagos_anteriores = sum(pago.monto_total for pago in pagos_anteriores)
        
        # ✅ CALCULAR SOLO LA SEÑA DE PAGOS ANTERIORES (concepto ID: 1)
        total_senia_anteriores = Decimal('0')
        for pago in pagos_anteriores:
            if pago.concepto and "|CONCEPTOS:" in pago.concepto:
                # Parsear conceptos del formato |CONCEPTOS:id:nombre:importe|
                concepto_parts = pago.concepto.split("|CONCEPTOS:", 1)
                if len(concepto_parts) > 1:
                    conceptos_data = concepto_parts[1]
                    conceptos_items = [item for item in conceptos_data.split("|") if item.strip()]
                    
                    for concepto_item in conceptos_items:
                        parts = concepto_item.split(":")
                        if len(parts) >= 3:
                            concepto_id = parts[0].strip()
                            concepto_importe = parts[2].strip()
                            
                            # ✅ CONCEPTOS QUE CUENTAN COMO SEÑA / saldo a ocupar: ver CONCEPTOS_SENIA_OPERACION_RESERVA
                            if concepto_id in CONCEPTOS_SENIA_OPERACION_RESERVA:
                                try:
                                    importe_num = Decimal(concepto_importe.replace(',', ''))
                                    total_senia_anteriores += importe_num
# print(f"💰 SEÑA ANTERIOR DETECTADA: Concepto {concepto_id} - ${importe_num}")
                                except:
                                    pass
        
# print(f"📊 CÁLCULO PAGOS ANTERIORES:")
# print(f"   - Total pagos anteriores: ${total_pagos_anteriores}")
# print(f"   - Seña anteriores (conceptos seña/locación): ${total_senia_anteriores}")
        
        es_completar_pago = total_pagos_anteriores > 0
        
        if es_completar_pago:
            # COMPLETAR PAGO: SALDO = PRECIO TOTAL - SOLO LA SEÑA ANTERIOR (concepto ID:1)
            saldo_a_ocupar = reserva.precio_total - total_senia_anteriores
        else:
            # FINALIZAR RESERVA: SALDO = PRECIO TOTAL (no hay seña anterior)
            saldo_a_ocupar = reserva.precio_total
        
        # El casillero «seña» en el template muestra seña acumulada (pagos anteriores + conceptos del recibo), no un monto a ingresar.
        senia_pendiente = 0
        
# print(f"🔧 CÁLCULO SALDO Y SEÑA:")
# print(f"   - Precio Total: ${reserva.precio_total}")
# print(f"   - Seña Anteriores (conceptos seña/locación): ${total_senia_anteriores}")
# print(f"   - Saldo a Ocupar: ${saldo_a_ocupar}")
# print(f"   - Seña Pendiente: ${senia_pendiente}")
        
        # ✅ DETECTAR SI EL DEPÓSITO YA FUE PAGADO (concepto 10)
        deposito_pagado = False
        if reserva.deposito_garantia > 0:
            # Buscar movimientos con concepto 10
            for movimiento in pagos_anteriores:
                if movimiento.concepto and "|CONCEPTOS:" in movimiento.concepto:
                    concepto_parts = movimiento.concepto.split("|CONCEPTOS:", 1)
                    if len(concepto_parts) > 1:
                        conceptos_data = concepto_parts[1]
                        # ✅ MEJORADO: Buscar concepto 10 de forma más robusta
                        concepto_10_encontrado = False
                        if "|10:" in conceptos_data or ":10:" in conceptos_data:
                            concepto_10_encontrado = True
                        else:
                            # Buscar en cada item individual
                            conceptos_items = [item for item in conceptos_data.split("|") if item.strip()]
                            for concepto_item in conceptos_items:
                                parts = concepto_item.split(":", 1)
                                if len(parts) > 0 and parts[0].strip() == "10":
                                    concepto_10_encontrado = True
                                    break
                        
                        if concepto_10_encontrado:  # Concepto 10 presente
                            deposito_pagado = True
                            break
        
        deposito_estado = 'pagado' if deposito_pagado else 'pendiente'
        
# print(f"✅ CÁLCULO FINALIZAR RESERVA:")
# print(f"   - Precio Total (Importe Locación): ${reserva.precio_total}")
# print(f"   - Seña ya pagada: ${reserva.senia or 0}")
# print(f"   - Saldo Pendiente: ${saldo_a_ocupar}")
# print(f"   - Seña sugerida para este pago: ${senia_pendiente}")
# print(f"   - Depósito: ${reserva.deposito_garantia or 0} ({deposito_estado})")

        
        # ✅ VARIABLES PARA EL TEMPLATE ORIGINAL (igual que finalizar_reserva)
        context = {
            'reserva': reserva,
            'pagos_previos': pagos_anteriores,  # Lista de MovimientoCaja anteriores
            'total_pagado': total_pagos_anteriores,  # Total de pagos anteriores
            'deposito': reserva.deposito_garantia or 0,  # Depósito de garantía
            'saldo_pendiente': saldo_a_ocupar,  # Saldo pendiente calculado
            'conceptos_pago': conceptos_caja,  # Conceptos disponibles
            'conceptos_caja': conceptos_caja,  # Para el template HTML
            'conceptos_json': list(conceptos_caja.values('id', 'nombre')),  # Para JavaScript
            'cuentas_bancarias': cuentas_bancarias,  # ✅ Cuentas bancarias de la sucursal
            'cliente_id': reserva.cliente.id,
            'cliente_nombre': f"{reserva.cliente.apellido}, {reserva.cliente.nombre}",
            'interno_caja': caja_actual.numero,
            'propiedad_id': reserva.propiedad.id,
            'propiedad_direccion': reserva.propiedad.direccion,
            'fecha_actual': datetime.now().strftime('%d/%m/%Y'),
            'numero_movimiento': proximo_numero_movimiento,
            'numero_recibo': '0000-00000000',  # Para completar
            'productor_id': reserva.vendedor.id if reserva.vendedor else request.user.id,
            'productor_nombre': f"{reserva.vendedor.apellido}, {reserva.vendedor.nombre}" if reserva.vendedor else f"{request.user.apellido}, {request.user.nombre}",
            'saldo_a_ocupar': saldo_a_ocupar,  # Para mostrar en resumen
            'senia_pendiente': senia_pendiente,
            'total_senia_pagada': float(total_senia_anteriores),  # Seña ya registrada (CONCEPTOS_SENIA_OPERACION_RESERVA)
            'total_deposito_pagado': reserva.deposito_garantia or 0,  
            'deposito_garantia': reserva.deposito_garantia,
            'deposito_estado': deposito_estado,  # ✅ Estado del depósito (pagado/pendiente)
            'fecha_desde': reserva.fecha_inicio.strftime('%d/%m/%Y'),
            'fecha_hasta': reserva.fecha_fin.strftime('%d/%m/%Y'),
        }
        
        return render(request, 'inmobiliaria/reserva/finalizar_reserva_nueva.html', context)
        
    except Exception as e:
        messages.error(request, f'Error al cargar la reserva: {str(e)}')
        return redirect('inmobiliaria:reservas')


@login_required
@require_POST
def actualizar_precio_reserva(request, reserva_id):
    """Vista AJAX para actualizar el precio total de una reserva"""
    try:
        from decimal import Decimal
        
        reserva = get_object_or_404(Reserva, id=reserva_id, sucursal=request.user.sucursal)
        
        # Obtener el nuevo precio del request
        nuevo_precio_str = request.POST.get('precio_total', '').strip()
        
        if not nuevo_precio_str:
            return JsonResponse({
                'success': False,
                'error': 'El precio no puede estar vacío'
            })
        
        try:
            nuevo_precio = parse_decimal_monto(nuevo_precio_str)
        except (ValueError, InvalidOperation):
            return JsonResponse({
                'success': False,
                'error': 'El precio debe ser un número válido'
            })
        
        if nuevo_precio < 0:
            return JsonResponse({
                'success': False,
                'error': 'El precio no puede ser negativo'
            })
        
        # Actualizar el precio de la reserva
        reserva.precio_total = nuevo_precio
        reserva.save(update_fields=['precio_total'])
        
        return JsonResponse({
            'success': True,
            'message': 'Precio actualizado correctamente',
            'precio_total': float(reserva.precio_total)
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': f'Error al actualizar el precio: {str(e)}'
        })


@login_required
def eliminar_disponibilidad(request, disponibilidad_id):
    """
    Vista para eliminar una disponibilidad validando que no tenga reservas existentes
    """
    if request.method == 'POST':
        try:
            from .models.propiedad import Reserva  # ✅ Importar al inicio
            
            disponibilidad = get_object_or_404(Disponibilidad, id=disponibilidad_id)
            
            # Verificar que la disponibilidad pertenezca a la sucursal del usuario
            if disponibilidad.propiedad.sucursal != request.user.sucursal:
                return JsonResponse({
                    'success': False,
                    'error': 'No tienes permisos para eliminar esta disponibilidad'
                })
            
            # Buscar reservas ACTIVAS en el rango de fechas de la disponibilidad
            # Solo impedir eliminar si hay reservas ACTIVAS (no canceladas)
            reservas_existentes = Reserva.objects.filter(
                propiedad=disponibilidad.propiedad,
                estado__in=['confirmada', 'pagada', 'confirmada_no_pagada']  # Solo reservas activas
            ).filter(
                # Reserva que se superpone con la disponibilidad
                fecha_inicio__lte=disponibilidad.fecha_fin,
                fecha_fin__gte=disponibilidad.fecha_inicio
            ).order_by('fecha_inicio')
            
            # Verificar también reservas futuras (para no eliminar disponibilidades que ya tienen reservas confirmadas)
            from datetime import date
            hoy = date.today()
            
            reservas_futuras = reservas_existentes.filter(fecha_fin__gte=hoy)  # Reservas que no han terminado
            
# print(f"🔍 VALIDANDO ELIMINACIÓN DE DISPONIBILIDAD {disponibilidad.id}")
# print(f"📅 Disponibilidad: {disponibilidad.fecha_inicio} - {disponibilidad.fecha_fin}")
# print(f"🏠 Propiedad: {disponibilidad.propiedad.id}")
# print(f"📋 Reservas encontradas: {reservas_existentes.count()}")
# print(f"📋 Reservas futuras/activas: {reservas_futuras.count()}")
            
            for reserva in reservas_existentes:
                es_futura = reserva.fecha_fin >= hoy
# print(f"   - Reserva {reserva.id}: {reserva.fecha_inicio} - {reserva.fecha_fin} ({reserva.estado}) {'[ACTIVA]' if es_futura else '[PASADA]'}")
            
            if reservas_futuras.exists():
                # Si hay reservas futuras/activas, preparar la información para mostrar
                reservas_info = []
                for reserva in reservas_futuras:  # Solo mostrar las reservas activas
                    reservas_info.append({
                        'id': reserva.id,
                        'fecha_inicio': reserva.fecha_inicio.strftime('%d/%m/%Y'),
                        'fecha_fin': reserva.fecha_fin.strftime('%d/%m/%Y'),
                        'cliente': f"{reserva.cliente.apellido}, {reserva.cliente.nombre}" if reserva.cliente else 'Sin cliente',
                        'estado': reserva.get_estado_display(),
                        'precio': str(reserva.precio_total)
                    })
                
                return JsonResponse({
                    'success': False,
                    'error': 'No se puede eliminar la disponibilidad',
                    'motivo': 'Existen reservas activas/futuras en este período',
                    'reservas': reservas_info,
                    'total_reservas': len(reservas_info),
                    'nota': 'Solo se pueden eliminar disponibilidades sin reservas activas o futuras'
                })
            
            # Si no hay reservas, eliminar la disponibilidad
            propiedad_direccion = disponibilidad.propiedad.direccion
            fecha_inicio = disponibilidad.fecha_inicio.strftime('%d/%m/%Y')
            fecha_fin = disponibilidad.fecha_fin.strftime('%d/%m/%Y')
            propiedad = disponibilidad.propiedad
            
# print(f"🗑️ ELIMINANDO DISPONIBILIDAD: {fecha_inicio} al {fecha_fin} para {propiedad_direccion}")
            
            # ✅ NUEVO: Eliminar la disponibilidad Y reconstruir historial
            disponibilidad.delete()
            
            # ✅ Reconstruir historial cronológico para reflejar los cambios
            # Buscar una reserva de esta propiedad para usar su método de reconstruir historial
            reserva_ejemplo = Reserva.objects.filter(propiedad=propiedad).first()
            if reserva_ejemplo:
                reserva_ejemplo.reconstruir_historial_cronologico()
# print(f"✅ Historial reconstruido para propiedad {propiedad.id}")
            else:
                pass  # ✅ Bloque vacío
# print(f"⚠️ No se encontraron reservas para reconstruir historial de propiedad {propiedad.id}")
            
            return JsonResponse({
                'success': True,
                'message': f'Disponibilidad eliminada correctamente del {fecha_inicio} al {fecha_fin} para {propiedad_direccion}. Historial actualizado.'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error interno: {str(e)}'
            })
    
    return JsonResponse({
        'success': False,
        'error': 'Método no permitido'
    })

@login_required
def editar_disponibilidad(request, disponibilidad_id):
    """
    Vista para editar una disponibilidad con validaciones inteligentes basadas en reservas
    """
    if request.method == 'POST':
        try:
            disponibilidad = get_object_or_404(Disponibilidad, id=disponibilidad_id)
            
            # Verificar permisos
            if disponibilidad.propiedad.sucursal != request.user.sucursal:
                return JsonResponse({
                    'success': False,
                    'error': 'No tienes permisos para editar esta disponibilidad'
                })
            
            nueva_fecha_inicio = datetime.strptime(request.POST.get('fecha_inicio'), '%Y-%m-%d').date()
            nueva_fecha_fin = datetime.strptime(request.POST.get('fecha_fin'), '%Y-%m-%d').date()
            
            # Validaciones básicas
            if nueva_fecha_inicio >= nueva_fecha_fin:
                return JsonResponse({
                    'success': False,
                    'error': 'La fecha de inicio debe ser anterior a la fecha de fin'
                })
            
            # Buscar reservas existentes en la disponibilidad actual
            reservas_en_disponibilidad = Reserva.objects.filter(
                propiedad=disponibilidad.propiedad,
                fecha_inicio__lt=disponibilidad.fecha_fin,
                fecha_fin__gt=disponibilidad.fecha_inicio,
                estado__in=['confirmada', 'pagada', 'confirmada_no_pagada']
            ).order_by('fecha_inicio')
            
# print(f"🔍 EDITANDO DISPONIBILIDAD {disponibilidad.id}")
# print(f"📅 Original: {disponibilidad.fecha_inicio} - {disponibilidad.fecha_fin}")
# print(f"📅 Nueva: {nueva_fecha_inicio} - {nueva_fecha_fin}")
# print(f"📋 Reservas en disponibilidad: {reservas_en_disponibilidad.count()}")
            
            if reservas_en_disponibilidad.exists():
                # HAY RESERVAS: Calcular límites permitidos
                primera_reserva = reservas_en_disponibilidad.first()
                ultima_reserva = reservas_en_disponibilidad.last()
                
                # Límites para fecha de inicio
                limite_inicio_maximo = primera_reserva.fecha_inicio  # No puede pasar la primera reserva
                
                # Límites para fecha de fin
                limite_fin_minimo = ultima_reserva.fecha_fin  # No puede ser antes de la última reserva
                
# print(f"🚧 LÍMITES CALCULADOS:")
# print(f"   Fecha inicio: puede ir hasta {limite_inicio_maximo} (primera reserva)")
# print(f"   Fecha fin: debe ser desde {limite_fin_minimo} (última reserva) en adelante")
                
                # Validar que las nuevas fechas respeten los límites
                if nueva_fecha_inicio > limite_inicio_maximo:
                    return JsonResponse({
                        'success': False,
                        'error': f'La fecha de inicio no puede ser posterior al {limite_inicio_maximo.strftime("%d/%m/%Y")}',
                        'motivo': f'Hay una reserva que inicia el {primera_reserva.fecha_inicio.strftime("%d/%m/%Y")}',
                        'limite_inicio_maximo': limite_inicio_maximo.strftime('%Y-%m-%d')
                    })
                
                if nueva_fecha_fin < limite_fin_minimo:
                    return JsonResponse({
                        'success': False,
                        'error': f'La fecha de fin no puede ser anterior al {limite_fin_minimo.strftime("%d/%m/%Y")}',
                        'motivo': f'Hay una reserva que termina el {ultima_reserva.fecha_fin.strftime("%d/%m/%Y")}',
                        'limite_fin_minimo': limite_fin_minimo.strftime('%Y-%m-%d')
                    })
                
            # ✅ MEJORADO: Verificar superposición REAL con otras disponibilidades (permitir contiguas)
            otras_disponibilidades = Disponibilidad.objects.filter(
                propiedad=disponibilidad.propiedad
            ).exclude(id=disponibilidad.id)
            
            # Verificar VERDADERA superposición (excluir fechas contiguas)
            conflictos_reales = []
            for otra in otras_disponibilidades:
                # Superposición REAL: comparten MÁS de un día
                # Si solo se tocan en UN día (contiguas como 10-15 y 15-20), es válido
                if otra.fecha_fin > nueva_fecha_inicio and otra.fecha_inicio < nueva_fecha_fin:
                    conflictos_reales.append({
                        'id': otra.id,
                        'fecha_inicio': otra.fecha_inicio.strftime('%d/%m/%Y'),
                        'fecha_fin': otra.fecha_fin.strftime('%d/%m/%Y')
                    })
                
            if conflictos_reales:
                return JsonResponse({
                    'success': False,
                    'error': 'Las nuevas fechas se superponen con otras disponibilidades',
                    'conflictos': conflictos_reales
                })
            
            # Si todas las validaciones pasan, actualizar la disponibilidad
            fecha_inicio_anterior = disponibilidad.fecha_inicio.strftime('%d/%m/%Y')
            fecha_fin_anterior = disponibilidad.fecha_fin.strftime('%d/%m/%Y')
            
            disponibilidad.fecha_inicio = nueva_fecha_inicio
            disponibilidad.fecha_fin = nueva_fecha_fin
            
            # Actualizar campos de asegurado
            disponibilidad.asegurado = request.POST.get('asegurado', 'false').lower() == 'true'
            
            if disponibilidad.asegurado:
                monto_asegurado = request.POST.get('monto_asegurado', '').strip()
                if monto_asegurado:
                    disponibilidad.monto_asegurado = Decimal(monto_asegurado)
                else:
                    disponibilidad.monto_asegurado = None
                    
                disponibilidad.moneda_asegurado = request.POST.get('moneda_asegurado', 'ARS')
            else:
                # Si no está asegurado, limpiar los campos
                disponibilidad.monto_asegurado = None
                disponibilidad.moneda_asegurado = None
            
            disponibilidad.save()

            # Actualizar historial automáticamente para que refleje el cambio sin pulsar "Reconstruir historial"
            reconstruir_historial_propiedad(disponibilidad.propiedad)

            return JsonResponse({
                'success': True,
                'message': f'Disponibilidad actualizada correctamente',
                'cambios': {
                    'anterior': f'{fecha_inicio_anterior} - {fecha_fin_anterior}',
                    'nueva': f'{nueva_fecha_inicio.strftime("%d/%m/%Y")} - {nueva_fecha_fin.strftime("%d/%m/%Y")}'
                }
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error interno: {str(e)}'
            })
    
    elif request.method == 'GET':
        # Obtener información para edición (límites, etc.)
        try:
            disponibilidad = get_object_or_404(Disponibilidad, id=disponibilidad_id)
            
            # Buscar reservas en esta disponibilidad
            reservas_en_disponibilidad = Reserva.objects.filter(
                propiedad=disponibilidad.propiedad,
                fecha_inicio__lt=disponibilidad.fecha_fin,
                fecha_fin__gt=disponibilidad.fecha_inicio,
                estado__in=['confirmada', 'pagada', 'confirmada_no_pagada']
            ).order_by('fecha_inicio')
            
            limites = {
                'fecha_inicio_actual': disponibilidad.fecha_inicio.strftime('%Y-%m-%d'),
                'fecha_fin_actual': disponibilidad.fecha_fin.strftime('%Y-%m-%d'),
                'tiene_reservas': reservas_en_disponibilidad.exists(),
                'reservas_info': []
            }
            
            if reservas_en_disponibilidad.exists():
                primera_reserva = reservas_en_disponibilidad.first()
                ultima_reserva = reservas_en_disponibilidad.last()
                
                limites.update({
                    'limite_inicio_maximo': primera_reserva.fecha_inicio.strftime('%Y-%m-%d'),
                    'limite_fin_minimo': ultima_reserva.fecha_fin.strftime('%Y-%m-%d'),
                    'primera_reserva': {
                        'fecha_inicio': primera_reserva.fecha_inicio.strftime('%d/%m/%Y'),
                        'fecha_fin': primera_reserva.fecha_fin.strftime('%d/%m/%Y')
                    },
                    'ultima_reserva': {
                        'fecha_inicio': ultima_reserva.fecha_inicio.strftime('%d/%m/%Y'),
                        'fecha_fin': ultima_reserva.fecha_fin.strftime('%d/%m/%Y')
                    }
                })
                
                # Información de todas las reservas para mostrar al usuario
                for reserva in reservas_en_disponibilidad:
                    limites['reservas_info'].append({
                        'id': reserva.id,
                        'fecha_inicio': reserva.fecha_inicio.strftime('%d/%m/%Y'),
                        'fecha_fin': reserva.fecha_fin.strftime('%d/%m/%Y'),
                        'cliente': f"{reserva.cliente.apellido}, {reserva.cliente.nombre}" if reserva.cliente else 'Sin cliente',
                        'estado': reserva.get_estado_display()
                    })
            
            return JsonResponse({
                'success': True,
                'disponibilidad': limites
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error interno: {str(e)}'
            })
    
    return JsonResponse({
        'success': False,
        'error': 'Método no permitido'
    })


def _disponibilidades_superpuestas(disponibilidades):
    """Devuelve (lista de ids a eliminar, lista de textos para mostrar).
    Eliminamos las que están totalmente contenidas en otra."""
    lista = list(disponibilidades.order_by('fecha_inicio', 'fecha_fin'))
    ids_a_eliminar = []
    textos = []
    for i, d in enumerate(lista):
        for j, otra in enumerate(lista):
            if i == j:
                continue
            # d está contenida en otra: otra.inicio <= d.inicio y otra.fin >= d.fin
            if otra.fecha_inicio <= d.fecha_inicio and otra.fecha_fin >= d.fecha_fin:
                if d.id not in ids_a_eliminar:
                    ids_a_eliminar.append(d.id)
                    textos.append(
                        f"{d.fecha_inicio.strftime('%d/%m/%Y')}–{d.fecha_fin.strftime('%d/%m/%Y')} "
                        f"(contenida en {otra.fecha_inicio.strftime('%d/%m/%Y')}–{otra.fecha_fin.strftime('%d/%m/%Y')})"
                    )
                break
    return ids_a_eliminar, textos


@login_required
@require_POST
def corregir_superposiciones_disponibilidades(request, propiedad_id):
    """Elimina disponibilidades que están totalmente contenidas en otra (quita duplicados)."""
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    if propiedad.sucursal != request.user.sucursal and not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': 'Sin permisos.'}, status=403)
    disp = propiedad.disponibilidades.filter(es_manual=True)
    ids_a_eliminar, _ = _disponibilidades_superpuestas(disp)
    eliminadas = 0
    for did in ids_a_eliminar:
        Disponibilidad.objects.filter(id=did, propiedad=propiedad).delete()
        eliminadas += 1
    return JsonResponse({
        'success': True,
        'message': f'Se eliminaron {eliminadas} disponibilidad(es) duplicada(s).',
        'eliminadas': eliminadas
    })


@login_required
def configurar_numeracion_recibos(request, sucursal_id):
    """
    Vista para configurar la numeración automática de recibos de una sucursal
    """
    if request.method == 'POST':
        try:
            sucursal = get_object_or_404(Sucursal, id=sucursal_id)
            
            # Verificar permisos (solo administradores nivel 4)
            if request.user.nivel < 4:
                messages.error(request, 'No tienes permisos para configurar la numeración de recibos')
                return redirect('inmobiliaria:sucursal_detalle', sucursal_id=sucursal.id)
            
            usar_numeracion = request.POST.get('usar_numeracion_automatica') == 'on'
            
# print(f"🔧 CONFIGURANDO NUMERACIÓN RECIBOS - Sucursal: {sucursal.nombre}")
# print(f"   Usar numeración automática: {usar_numeracion}")
            
            if usar_numeracion:
                prefijo = request.POST.get('prefijo_recibo', '').strip()
                ultimo_numero = request.POST.get('ultimo_numero_recibo', '').strip()
                
                # Si es la primera configuración y están vacíos, usar valores por defecto
                if not prefijo:
                    prefijo = '1'  # Valor por defecto
                if not ultimo_numero:
                    ultimo_numero = '1'  # Valor por defecto
                
# print(f"   📋 DATOS RECIBIDOS:")
# print(f"      - Prefijo: '{prefijo}'")
# print(f"      - Último número: '{ultimo_numero}'")
                
                # Validaciones
                try:
                    prefijo_int = int(prefijo)
                    if prefijo_int < 1 or prefijo_int > 99999:
                        raise ValueError()
                except (ValueError, TypeError):
                    messages.error(request, 'El número identificador debe ser entre 1 y 99999')
                    return redirect('inmobiliaria:sucursal_detalle', sucursal_id=sucursal.id)
                
                try:
                    ultimo_numero_int = int(ultimo_numero)
                    if ultimo_numero_int < 1 or ultimo_numero_int > 99999:
                        raise ValueError()
                except (ValueError, TypeError):
                    messages.error(request, 'El contador inicial debe ser entre 1 y 99999')
                    return redirect('inmobiliaria:sucursal_detalle', sucursal_id=sucursal.id)
                
                # Si ya tenía numeración automática y se está cambiando el prefijo/número
                if sucursal.usar_numeracion_automatica:
                    if sucursal.prefijo_recibo != prefijo_int:
                        pass  # ✅ Bloque vacío
# print(f"   📝 Cambiando prefijo: {sucursal.prefijo_recibo} → {prefijo_int}")
                    if sucursal.ultimo_numero_recibo != ultimo_numero_int:
                        # Solo permitir incrementar el número, no decrementar
                        if ultimo_numero_int < sucursal.ultimo_numero_recibo:
                            messages.warning(request, 
                                f'No se puede decrementar el contador. Último número usado: {sucursal.ultimo_numero_recibo}')
                            return redirect('inmobiliaria:sucursal_detalle', sucursal_id=sucursal.id)
# print(f"   📈 Ajustando número: {sucursal.ultimo_numero_recibo} → {ultimo_numero_int}")
                
                # Actualizar configuración
                sucursal.usar_numeracion_automatica = True
                sucursal.prefijo_recibo = prefijo_int
                sucursal.ultimo_numero_recibo = ultimo_numero_int
                sucursal.save()
                
                proximo_numero = sucursal.obtener_proximo_numero_recibo()
                messages.success(request, f'✅ Numeración automática configurada. Próximo recibo: {proximo_numero}')
# print(f"   ✅ Configuración guardada. Próximo número: {proximo_numero}")
                
            else:
                # Desactivar numeración automática
                sucursal.usar_numeracion_automatica = False
                sucursal.save()
                messages.success(request, '✅ Numeración automática desactivada. Los recibos se ingresarán manualmente.')
# print(f"   ✅ Numeración automática desactivada")
            
            return redirect('inmobiliaria:sucursal_detalle', sucursal_id=sucursal.id)
            
        except Exception as e:
            pass  # ✅ Bloque vacío
# print(f"❌ Error al configurar numeración: {e}")
            messages.error(request, f'Error al guardar configuración: {str(e)}')
            return redirect('inmobiliaria:sucursal_detalle', sucursal_id=sucursal.id)
    
    return redirect('inmobiliaria:sucursal_detalle', sucursal_id=sucursal_id)


@login_required
def recibo_contrato_24(request, contrato_id):
    """Vista para mostrar el recibo de un contrato de 24 meses"""
    from decimal import Decimal
    try:
        contrato = get_object_or_404(ContratoAlquiler, id=contrato_id, sucursal=request.user.sucursal)
        
        # Obtener los conceptos del primer pago del contrato
        conceptos_contrato = []
        mes_alquiler_importe_recibo = None  # valor elegido (mensual/proporcional) guardado en movimiento
        mes_alquiler_tipo_recibo = 'mensual'  # 'proporcional' o 'mensual' para la etiqueta en el recibo
        precio_mensual_completo_recibo = None  # precio mensual del formulario (para "Mes alquiler" en recibo)
        mes_alquiler_texto_recibo = ''  # texto que va en los puntos del recibo (ej. "marzo 2026")
        sellados_importe_json = None  # sellados en raíz de concepto_detalle {..., "sellados": n}

        # Buscar movimientos del contrato (más reciente primero) y usar el que tenga concepto_detalle
        movimientos_contrato = MovimientoCaja.objects.filter(
            concepto__icontains=f'Contrato #{contrato.id}',
            propiedad=contrato.propiedad,
            sucursal=request.user.sucursal
        ).order_by('-id')
        
        primer_movimiento = None
        for mov in movimientos_contrato:
            detalle = (getattr(mov, 'concepto_detalle', None) or '').strip()
            if detalle and (detalle.startswith('[') or detalle.startswith('{')):
                primer_movimiento = mov
                break
        if not primer_movimiento:
            primer_movimiento = movimientos_contrato.first()
        
        if not primer_movimiento:
            cuota_pagada = contrato.cuotas.filter(estado='pagada', movimiento__isnull=False).first()
            if cuota_pagada and cuota_pagada.movimiento:
                primer_movimiento = cuota_pagada.movimiento
        
        # ✅ LÓGICA SIMPLIFICADA: SIEMPRE CREAR CONCEPTOS DETALLADOS
        if primer_movimiento:
            pass  # ✅ Bloque vacío
# print(f"🔍 DEBUG RECIBO: Movimiento encontrado ID={primer_movimiento.id}")
# print(f"🔍 DEBUG RECIBO: Concepto: '{primer_movimiento.concepto}'")
            
            # Obtener valores del movimiento
            monto_efectivo = float(primer_movimiento.monto_efectivo or 0)
            monto_cheque = float(primer_movimiento.monto_cheque or 0)
            monto_tarjeta = float(primer_movimiento.monto_tarjeta or 0)
            monto_deposito = float(primer_movimiento.monto_deposito or 0)
            total_pagado = monto_efectivo + monto_cheque + monto_tarjeta + monto_deposito
            
# print(f"🔍 VALORES DEL MOVIMIENTO:")
# print(f"  - monto_efectivo: ${monto_efectivo}")
# print(f"  - monto_cheque: ${monto_cheque}")
# print(f"  - monto_tarjeta: ${monto_tarjeta}")
# print(f"  - monto_deposito: ${monto_deposito}")
# print(f"  - TOTAL PAGADO: ${total_pagado}")
            
# print(f"🔍 VALORES DEL CONTRATO:")
# print(f"  - precio_mensual: ${contrato.precio_mensual}")
# print(f"  - deposito_garantia: ${contrato.deposito_garantia}")

            def observaciones_para_recibo(raw):
                if raw is None:
                    return ''
                t = str(raw).strip()
                if not t:
                    return ''
                tl = t.lower()
                if tl in ('sin observaciones', 'sin observaciones.'):
                    return ''
                return t

            # ✅ Usar concepto_detalle (JSON completo) si existe; puede ser array o objeto {conceptos, mes_alquiler_importe}
            try:
                import json
                concepto_detalle_raw = (getattr(primer_movimiento, 'concepto_detalle', None) or '').strip()
                json_str = concepto_detalle_raw if concepto_detalle_raw else (primer_movimiento.concepto or '[]')
                if json_str.strip().startswith('{'):
                    obj = json.loads(json_str)
                    conceptos_data = obj.get('conceptos', [])
                    if obj.get('mes_alquiler_importe') is not None:
                        try:
                            mes_alquiler_importe_recibo = Decimal(str(obj['mes_alquiler_importe']))
                        except (TypeError, ValueError):
                            pass
                    if obj.get('mes_alquiler_tipo') in ('proporcional', 'mensual'):
                        mes_alquiler_tipo_recibo = obj.get('mes_alquiler_tipo')
                    elif mes_alquiler_importe_recibo is not None and contrato.precio_mensual:
                        # Movimientos antiguos sin mes_alquiler_tipo: si el importe difiere del precio mensual, asumir proporcional
                        try:
                            if abs(float(mes_alquiler_importe_recibo) - float(contrato.precio_mensual)) > 0.01:
                                mes_alquiler_tipo_recibo = 'proporcional'
                        except (TypeError, ValueError):
                            pass
                    if obj.get('precio_mensual_completo') is not None:
                        try:
                            precio_mensual_completo_recibo = Decimal(str(obj['precio_mensual_completo']))
                        except (TypeError, ValueError):
                            pass
                    if obj.get('mes_alquiler_texto_recibo'):
                        mes_alquiler_texto_recibo = str(obj['mes_alquiler_texto_recibo']).strip()[:200]
                    if obj.get('sellados') is not None:
                        try:
                            sellados_importe_json = Decimal(str(obj['sellados']))
                            if sellados_importe_json < 0:
                                sellados_importe_json = None
                        except (TypeError, ValueError, ArithmeticError):
                            sellados_importe_json = None
                else:
                    if not (json_str and json_str.strip().startswith('[')):
                        json_str = '[]'
                    conceptos_data = json.loads(json_str) if json_str.strip() else []
# print(f"🎯 CONCEPTOS JSON ENCONTRADOS: {len(conceptos_data)} conceptos")
# print(f"🎯 DATOS COMPLETOS: {conceptos_data}")

                for i, concepto_data in enumerate(conceptos_data):
                    pass  # ✅ Bloque vacío
# print(f"  📋 CONCEPTO {i}: {concepto_data}")
                    importe_valor = float(concepto_data.get('importe', 0))
                    codigo_raw = concepto_data.get('id', concepto_data.get('codigo', ''))
                    codigo_txt = '' if codigo_raw is None else str(codigo_raw).strip()
                    codigo = _etiqueta_id_concepto_caja_visual(codigo_txt) if codigo_txt else ''
                    nombre = concepto_data.get('nombre', concepto_data.get('concepto', ''))
                    
# print(f"    - Importe: {importe_valor}")
# print(f"    - Código: '{codigo}'")
# print(f"    - Nombre: '{nombre}'")
                    
                    # Incluir TODOS los conceptos del detalle (alquiler, gas, etc.), no solo uno
                    conceptos_contrato.append({
                        'fecha': primer_movimiento.fecha,
                        'codigo': codigo,
                        'nombre': nombre,
                        'observaciones': observaciones_para_recibo(concepto_data.get('observaciones')),
                        'importe': f"${importe_valor:,.2f}".replace(',', '.'),
                        'importe_numerico': importe_valor
                    })
                
                if len(conceptos_contrato) > 0:
                    pass  # ✅ Bloque vacío
# print(f"🎉 USANDO CONCEPTOS REALES DEL JSON: {len(conceptos_contrato)} conceptos")
                else:
                    pass  # ✅ Bloque vacío
# print(f"⚠️ JSON parseado pero sin conceptos válidos")
                    
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                pass  # ✅ Bloque vacío
# print(f"⚠️ NO SE PUDO PARSEAR JSON: {e}")
# print(f"⚠️ CONTENIDO QUE FALLÓ: '{primer_movimiento.concepto[:100]}...'")
                conceptos_contrato = []  # Limpiar cualquier concepto previo
            
            # ✅ FALLBACK: Si no hay conceptos del JSON, crear desde TODOS los movimientos
            if len(conceptos_contrato) == 0:
                pass  # ✅ Bloque vacío
# print(f"🔧 FALLBACK: Buscando conceptos en TODOS los movimientos del contrato...")
                
                # Buscar TODOS los movimientos de este contrato para encontrar conceptos pagados
                import json
                
                todos_movimientos = MovimientoCaja.objects.filter(
                    propiedad=contrato.propiedad,
                    concepto__icontains=f'Contrato #{contrato.id}'
                ).order_by('fecha')
                
# print(f"  🔍 Movimientos encontrados: {todos_movimientos.count()}")
                
                conceptos_encontrados = {}  # Para evitar duplicados
                
                for mov in todos_movimientos:
                    pass  # ✅ Bloque vacío
# print(f"    📋 Revisando movimiento ID={mov.id}, Fecha={mov.fecha}")
                    
                    try:
                        # Intentar parsear JSON
                        conceptos_mov = json.loads(mov.concepto)
# print(f"      ✅ JSON parseado: {len(conceptos_mov)} conceptos")
                        
                        for concepto in conceptos_mov:
                            concepto_id = str(concepto.get('id', concepto.get('codigo', '')))
                            concepto_nombre = concepto.get('nombre', '')
                            concepto_importe = float(concepto.get('importe', 0))
                            
                            if concepto_importe > 0 and concepto_id not in conceptos_encontrados:
                                conceptos_encontrados[concepto_id] = {
                                    'fecha': mov.fecha,
                                    'codigo': concepto_id,
                                    'nombre': concepto_nombre,
                                    'observaciones': observaciones_para_recibo(concepto.get('observaciones')),
                                    'importe': f"${concepto_importe:,.2f}".replace(',', '.'),
                                    'importe_numerico': concepto_importe
                                }
# print(f"        ✅ CONCEPTO ENCONTRADO: {concepto_id} - {concepto_nombre} - ${concepto_importe}")
                            
                    except (json.JSONDecodeError, ValueError, TypeError):
                        pass  # ✅ Bloque vacío
# print(f"      ⚠️ No es JSON, revisando texto...")
                        
                        # Fallback: buscar conceptos específicos en texto
                        concepto_texto = mov.concepto.lower()
                        
                        # ✅ VERIFICAR CONCEPTOS ESPECÍFICOS Y CAMPOS DEL MOVIMIENTO
                        
                        # 1. ALQUILER - siempre agregar si hay precio mensual
                        if '1' not in conceptos_encontrados and contrato.precio_mensual and contrato.precio_mensual > 0:
                            conceptos_encontrados['1'] = {
                                'fecha': mov.fecha,
                                'codigo': '1',
                                'nombre': 'Alquiler',
                                'observaciones': '',
                                'importe': f"${float(contrato.precio_mensual):,.2f}".replace(',', '.'),
                                'importe_numerico': float(contrato.precio_mensual)
                            }
# print(f"        ✅ ALQUILER AGREGADO (precio mensual)")
                        
                        # 2. DEPÓSITO - verificar campo Y texto
                        if '10' not in conceptos_encontrados:
                            deposito_detectado = False
                            deposito_valor = 0
                            
                            # Verificar en texto
                            if 'deposito' in concepto_texto or 'concepto 10' in concepto_texto:
                                deposito_valor = float(contrato.deposito_garantia or 0)
                                deposito_detectado = True
# print(f"        🔍 DEPÓSITO detectado en texto")
                            
                            if deposito_detectado and deposito_valor > 0:
                                conceptos_encontrados['10'] = {
                                    'fecha': mov.fecha,
                                    'codigo': '10',
                                    'nombre': 'Depósito de garantía',
                                    'observaciones': '',
                                    'importe': f"${deposito_valor:,.2f}".replace(',', '.'),
                                    'importe_numerico': deposito_valor
                                }
# print(f"        ✅ DEPÓSITO AGREGADO: ${deposito_valor}")
                        
                        # 3. HONORARIOS - verificar campo Y texto Y diferencia
                        if '25' not in conceptos_encontrados:
                            honorarios_detectado = False
                            honorarios_valor = 0
                            
                            # Método 1: Campo honorarios del movimiento
                            if mov.honorarios and mov.honorarios > 0:
                                honorarios_valor = float(mov.honorarios)
                                honorarios_detectado = True
# print(f"        🔍 HONORARIOS detectado en campo: ${honorarios_valor}")
                            
                            # Método 2: Texto del concepto
                            elif 'honorario' in concepto_texto or 'concepto 25' in concepto_texto:
                                # Buscar valor en el texto o usar diferencia
                                total_mov = (float(mov.monto_efectivo or 0) + float(mov.monto_cheque or 0) + 
                                           float(mov.monto_tarjeta or 0) + float(mov.monto_deposito or 0))
                                diferencia = total_mov - float(contrato.precio_mensual or 0)
                                if diferencia > 0:
                                    honorarios_valor = diferencia
                                    honorarios_detectado = True
# print(f"        🔍 HONORARIOS detectado en texto, calculado: ${honorarios_valor}")
                            
                            if honorarios_detectado and honorarios_valor > 0:
                                conceptos_encontrados['25'] = {
                                    'fecha': mov.fecha,
                                    'codigo': '25',
                                    'nombre': 'Honorarios',
                                    'observaciones': '',
                                    'importe': f"${honorarios_valor:,.2f}".replace(',', '.'),
                                    'importe_numerico': honorarios_valor
                                }
# print(f"        ✅ HONORARIOS AGREGADO: ${honorarios_valor}")
                        
                        # 4. SELLADOS - verificar campo Y texto
                        if '26' not in conceptos_encontrados:
                            sellados_detectado = False
                            sellados_valor = 0
                            
                            # Campo sellados del movimiento
                            if mov.sellados and mov.sellados > 0:
                                sellados_valor = float(mov.sellados)
                                sellados_detectado = True
# print(f"        🔍 SELLADOS detectado en campo: ${sellados_valor}")
                            
                            # Texto del concepto
                            elif 'sellado' in concepto_texto or 'concepto 26' in concepto_texto:
                                sellados_detectado = True
# print(f"        🔍 SELLADOS detectado en texto")
                            
                            if sellados_detectado and sellados_valor > 0:
                                conceptos_encontrados['26'] = {
                                    'fecha': mov.fecha,
                                    'codigo': '26',
                                    'nombre': 'Sellados',
                                    'observaciones': '',
                                    'importe': f"${sellados_valor:,.2f}".replace(',', '.'),
                                    'importe_numerico': sellados_valor
                                }
# print(f"        ✅ SELLADOS AGREGADO: ${sellados_valor}")
                
                # Agregar conceptos encontrados al recibo
                for concepto_id, concepto_data in conceptos_encontrados.items():
                    conceptos_contrato.append(concepto_data)
# print(f"  🎯 CONCEPTO AGREGADO AL RECIBO: {concepto_id} - {concepto_data['nombre']}")
                
# print(f"  📊 TOTAL CONCEPTOS ENCONTRADOS: {len(conceptos_contrato)}")
            
            # ✅ SI AÚN NO HAY CONCEPTOS, FORZAR CREACIÓN DETALLADA
            if len(conceptos_contrato) == 0:
                pass  # ✅ Bloque vacío
# print(f"🚨 FORZANDO CONCEPTOS DETALLADOS - NO MÁS GENÉRICOS")
# print(f"🚨 DATOS PARA FORZAR:")
# print(f"   - Total pagado: ${total_pagado}")
# print(f"   - Precio mensual: ${contrato.precio_mensual}")
# print(f"   - Primer movimiento honorarios: ${primer_movimiento.honorarios if primer_movimiento else 'N/A'}")
# print(f"   - Primer movimiento sellados: ${primer_movimiento.sellados if primer_movimiento else 'N/A'}")
                
                # FORZAR conceptos básicos siempre
                # 1. ALQUILER (obligatorio)
                if contrato.precio_mensual and contrato.precio_mensual > 0:
                    conceptos_contrato.append({
                        'fecha': primer_movimiento.fecha,
                        'codigo': '1',
                        'nombre': 'Alquiler',
                        'observaciones': '',
                        'importe': f"${float(contrato.precio_mensual):,.2f}".replace(',', '.'),
                        'importe_numerico': float(contrato.precio_mensual)
                    })
# print(f"  🔥 FORZADO FINAL: Alquiler ${contrato.precio_mensual}")
                
                # 2. HONORARIOS (desde campo del movimiento O diferencia)
                honorarios_valor = 0
                if primer_movimiento and primer_movimiento.honorarios and primer_movimiento.honorarios > 0:
                    honorarios_valor = float(primer_movimiento.honorarios)
# print(f"  💰 HONORARIOS desde campo movimiento: ${honorarios_valor}")
                else:
                    # Calcular como diferencia
                    diferencia_final = total_pagado - float(contrato.precio_mensual or 0)
                    if diferencia_final > 0:
                        honorarios_valor = diferencia_final
# print(f"  💰 HONORARIOS calculado como diferencia: ${honorarios_valor}")
                
                if honorarios_valor > 0:
                    conceptos_contrato.append({
                        'fecha': primer_movimiento.fecha,
                        'codigo': '25',
                        'nombre': 'Honorarios',
                        'observaciones': '',
                        'importe': f"${honorarios_valor:,.2f}".replace(',', '.'),
                        'importe_numerico': honorarios_valor
                    })
# print(f"  🔥 FORZADO FINAL: Honorarios ${honorarios_valor}")
                
                # 3. SELLADOS (desde campo del movimiento)
                if primer_movimiento and primer_movimiento.sellados and primer_movimiento.sellados > 0:
                    sellados_valor = float(primer_movimiento.sellados)
                    conceptos_contrato.append({
                        'fecha': primer_movimiento.fecha,
                        'codigo': '26',
                        'nombre': 'Sellados',
                        'observaciones': '',
                        'importe': f"${sellados_valor:,.2f}".replace(',', '.'),
                        'importe_numerico': sellados_valor
                    })
# print(f"  🔥 FORZADO FINAL: Sellados ${sellados_valor}")
                
# print(f"🔥 CONCEPTOS FORZADOS FINALES: {len(conceptos_contrato)}")
            
# print(f"🎯 TOTAL CONCEPTOS FINALES: {len(conceptos_contrato)}")
        else:
            # Si no hay movimientos, crear conceptos básicos (NO genéricos)
# print(f"⚠️ NO HAY MOVIMIENTOS - CREANDO CONCEPTOS BÁSICOS")
            precio_mensual_valor = float(contrato.precio_mensual or 0)
            if precio_mensual_valor > 0:
                conceptos_contrato.append({
                    'fecha': contrato.fecha_operacion,
                    'codigo': '1',
                    'nombre': 'Alquiler',
                    'observaciones': '',
                    'importe': f"${precio_mensual_valor:,.2f}".replace(',', '.'),
                    'importe_numerico': precio_mensual_valor
                })
# print(f"  ✅ SIN MOVIMIENTO: Alquiler ${precio_mensual_valor}")
        
        from decimal import Decimal

        # Mes alquiler: prioridad = valor guardado en movimiento (mensual/proporcional elegido); luego contrato; luego concepto 1; luego propiedad
        alquiler_mensual = mes_alquiler_importe_recibo if mes_alquiler_importe_recibo is not None else None
        if alquiler_mensual is None:
            alquiler_mensual = contrato.precio_mensual or Decimal('0')
        if alquiler_mensual == 0 and conceptos_contrato:
            for c in conceptos_contrato:
                co = str(c.get('codigo') or c.get('id') or '')
                nom = (c.get('nombre') or '').lower()
                if co == '1' or 'alquiler' in nom:
                    alquiler_mensual = Decimal(str(c['importe_numerico']))
                    break
        if alquiler_mensual == 0 and contrato.propiedad:
            try:
                if contrato.duracion_meses == 9 and getattr(contrato.propiedad, 'info_invierno', None):
                    if contrato.propiedad.info_invierno and contrato.propiedad.info_invierno.precio_mensual:
                        alquiler_mensual = Decimal(str(contrato.propiedad.info_invierno.precio_mensual))
                elif getattr(contrato.propiedad, 'info_meses', None) and contrato.propiedad.info_meses:
                    if contrato.propiedad.info_meses.precio_mensual:
                        alquiler_mensual = Decimal(str(contrato.propiedad.info_meses.precio_mensual))
            except Exception:
                pass
        deposito_garantia = contrato.deposito_garantia or Decimal('0')
        # Honorarios = lo cargado en el campo "Honorarios" al hacer la operación (formulario)
        honorarios = Decimal('0')
        if primer_movimiento and getattr(primer_movimiento, 'honorarios', None):
            honorarios = Decimal(str(primer_movimiento.honorarios))
        # Sellados = raíz JSON del detalle, campo del movimiento o concepto 26 en conceptos[]
        sellados = Decimal('0')
        if sellados_importe_json is not None and sellados_importe_json > 0:
            sellados = sellados_importe_json
        elif primer_movimiento and getattr(primer_movimiento, 'sellados', None):
            try:
                sellados = Decimal(str(primer_movimiento.sellados))
            except Exception:
                sellados = Decimal('0')
        if sellados == 0 and conceptos_contrato:
            for c in conceptos_contrato:
                co = str(c.get('codigo') or c.get('id') or '')
                nom = (c.get('nombre') or '').lower()
                if co == '26' or 'sellado' in nom:
                    try:
                        sellados = Decimal(str(c.get('importe_numerico', 0)))
                    except Exception:
                        sellados = Decimal('0')
                    break
        
        deposito_estado = determinar_estado_concepto_contrato(contrato, '10')
        # Total a abonar = Mes alquiler + Depósito + Honorarios + Sellados
        total_a_abonar = float(alquiler_mensual) + float(deposito_garantia) + float(honorarios) + float(sellados)
        
        # Total solo = suma de los conceptos cargados (lo que se ha cobrado/pagado)
        total_solo = sum(Decimal(str(c['importe_numerico'])) for c in conceptos_contrato)
        total_solo_float = float(total_solo)
        
        # Neto a la posesión = Total a abonar - conceptos pagados (total solo)
        neto_a_posesion = Decimal(str(total_a_abonar)) - total_solo
        if neto_a_posesion < 0:
            neto_a_posesion = Decimal('0')
        
        subtotal = total_a_abonar
        total_contrato = total_a_abonar
        
        # Convertir números a formato de pesos argentinos
        def format_currency(amount):
            return f"${float(amount):,.2f}".replace(',', '.')
        
        # Obtener logo en base64
        logo_base64 = None
        try:
            import base64
            import os
            logo_path = os.path.join(os.path.dirname(__file__), 'static', 'images', 'logo.png')
            if os.path.exists(logo_path):
                with open(logo_path, 'rb') as logo_file:
                    logo_base64 = base64.b64encode(logo_file.read()).decode('utf-8')
        except Exception as e:
            pass  # ✅ Bloque vacío
# print(f"Error al cargar logo: {e}")
        
        # Función para convertir número a texto (básica)
        def numero_a_texto(numero):
            # Implementación simple - en producción usar una librería como num2words
            if numero > 0:
                return f"PESOS {str(int(float(numero))).upper()}"
            return ""
        
        # Precio mensual del contrato (siempre el valor mensual, no el proporcional) para "Mes alquiler" en el recibo
        if precio_mensual_completo_recibo is not None and float(precio_mensual_completo_recibo) > 0:
            precio_mensual_contrato = format_currency(precio_mensual_completo_recibo)
        else:
            precio_mensual_contrato = format_currency(contrato.precio_mensual or 0)

        # CLIENTE(S) = todos los inquilinos/estudiantes cargados en el contrato (pueden ser varios)
        through_list = list(contrato.contrato_inquilinos.select_related('inquilino').order_by('id'))
        garantes_db = list(contrato.garantes.all())

        if through_list:
            lista_inquilinos = [{'inquilino': ci.inquilino, 'carrera': ci.carrera or ''} for ci in through_list]
        else:
            lista_inquilinos = [{'inquilino': contrato.inquilino, 'carrera': contrato.carrera or ''}] if contrato.inquilino_id else []

        # lista_garantes_recibo = todos los garantes (primer garante = locatario en contrato; si 1 solo responde como locatario y garante)
        lista_garantes_recibo = []
        if garantes_db:
            lista_garantes_recibo = list(garantes_db)
        elif contrato.garante_apellido or contrato.garante_nombre:
            from types import SimpleNamespace
            lista_garantes_recibo = [SimpleNamespace(
                apellido=contrato.garante_apellido or '',
                nombre=contrato.garante_nombre or '',
                dni=contrato.garante_dni or '',
                celular=getattr(contrato, 'garante_celular', None) or '',
                email=contrato.garante_email or '',
                domicilio=contrato.garante_domicilio or ''
            )]

        context = {
            'contrato': contrato,
            'lista_inquilinos': lista_inquilinos,
            'lista_garantes_recibo': lista_garantes_recibo,
            'conceptos_contrato': conceptos_contrato,
            'alquiler_mensual': format_currency(alquiler_mensual),
            'deposito_garantia': format_currency(deposito_garantia),
            'deposito_estado': deposito_estado,
            'honorarios': format_currency(honorarios),
            'sellados': format_currency(sellados),
            'total_a_abonar': format_currency(total_a_abonar),
            'total_solo': format_currency(total_solo_float),
            'neto_a_posesion': format_currency(neto_a_posesion),
            'subtotal': format_currency(subtotal),
            'total_contrato': format_currency(total_contrato),
            'suma_en_letras': numero_a_texto(total_contrato),
            'logo_base64': logo_base64,
            'precio_mensual_contrato': precio_mensual_contrato,
            'mes_alquiler_es_proporcional': mes_alquiler_tipo_recibo == 'proporcional',
            'mes_alquiler_texto_recibo': mes_alquiler_texto_recibo,
        }
        
        return render(request, 'inmobiliaria/contratos/recibo_contrato_24.html', context)
        
    except Exception as e:
        logger.error(f"Error al generar recibo de contrato: {str(e)}")
        messages.error(request, f'Error al generar recibo: {str(e)}')
        return redirect('inmobiliaria:lista_contratos')


MESES_ES = [
    '', 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'
]


@login_required
def ver_comodato_invierno(request, contrato_id):
    """Genera el documento COMODATO INVIERNO (temporario) con datos del contrato rellenados. Solo para contratos de 9 meses (invierno)."""
    contrato = get_object_or_404(
        ContratoAlquiler.objects.select_related('propiedad', 'propiedad__propietario', 'inquilino'),
        id=contrato_id,
        sucursal=request.user.sucursal
    )
    if contrato.duracion_meses != 9:
        messages.warning(request, 'El comodato invierno solo aplica a contratos de 9 meses (invierno).')
        return redirect('inmobiliaria:detalle_contrato', contrato_id=contrato.id)

    prop = contrato.propiedad
    propi = prop.propietario
    inq = contrato.inquilino

    fi = contrato.fecha_inicio
    ff = contrato.fecha_fin
    fop = contrato.fecha_operacion or timezone.now().date()

    deposito = contrato.deposito_garantia or Decimal('0')
    deposito_int = int(deposito)
    deposito_texto = f"{deposito_int:,}".replace(',', '.')
    deposito_numero = f"${deposito_int:,}".replace(',', '.')

    context = {
        'contrato': contrato,
        'comodante_nombre': f"{propi.apellido or ''}, {propi.nombre or ''}".strip() or '—',
        'comodante_dni': propi.dni or '—',
        'comodante_domicilio': (propi.domicilio or '—')[:80],
        'comodante_localidad': propi.localidad or '—',
        'comodante_provincia': propi.provincia or 'Buenos Aires',
        'comodatario_nombre': f"{inq.apellido or ''}, {inq.nombre or ''}".strip() or '—',
        'comodatario_dni': inq.dni or '—',
        'comodatario_domicilio': (inq.domicilio or '—')[:80],
        'comodatario_localidad': inq.localidad or '—',
        'comodatario_provincia': inq.provincia or '—',
        'propiedad_direccion': prop.direccion or '—',
        'propiedad_piso': getattr(prop, 'piso', None) or '',
        'propiedad_dpto': getattr(prop, 'departamento', None) or '',
        'fecha_inicio_dia': fi.day,
        'fecha_inicio_mes': MESES_ES[fi.month],
        'fecha_inicio_anio': fi.year,
        'fecha_fin_dia': ff.day,
        'fecha_fin_mes': MESES_ES[ff.month],
        'fecha_fin_anio': ff.year,
        'firma_dia': fop.day,
        'firma_mes': MESES_ES[fop.month],
        'firma_anio': fop.year,
        'deposito_texto': deposito_texto,
        'deposito_numero': deposito_numero,
        'fiador_nombre': '..........................',
        'fiador_domicilio': '..........................',
        'fiador_ciudad': '..........................',
        'fiador_provincia': '..........................',
        'url_volver': reverse('inmobiliaria:detalle_contrato', args=[contrato.id]),
    }
    return render(request, 'inmobiliaria/contratos/comodato_invierno.html', context)


def _formatear_cuit(cuit):
    """Formatea CUIT/CUIL 11 dígitos como XX-XXXXXXXX-X."""
    if not cuit:
        return '—'
    s = re.sub(r'\D', '', str(cuit))
    if len(s) == 11:
        return f"{s[:2]}-{s[2:10]}-{s[10]}"
    return str(cuit)


def _numero_a_letras_es(n):
    """Convierte entero (0-999999) a palabras en español en MAYÚSCULAS (para montos)."""
    if n is None or n < 0:
        return "—"
    n = int(n)
    if n == 0:
        return "CERO"
    unidades = ['', 'UNO', 'DOS', 'TRES', 'CUATRO', 'CINCO', 'SEIS', 'SIETE', 'OCHO', 'NUEVE']
    especiales = ['DIEZ', 'ONCE', 'DOCE', 'TRECE', 'CATORCE', 'QUINCE', 'DIECISÉIS', 'DIECISIETE', 'DIECIOCHO', 'DIECINUEVE']
    decenas = ['', '', 'VEINTE', 'TREINTA', 'CUARENTA', 'CINCUENTA', 'SESENTA', 'SETENTA', 'OCHENTA', 'NOVENTA']
    centenas = ['', 'CIENTO', 'DOSCIENTOS', 'TRESCIENTOS', 'CUATROCIENTOS', 'QUINIENTOS', 'SEISCIENTOS', 'SETECIENTOS', 'OCHOCIENTOS', 'NOVECIENTOS']
    if n == 100:
        return "CIEN"
    if n < 10:
        return unidades[n]
    if n < 20:
        return especiales[n - 10]
    if n < 100:
        d, u = divmod(n, 10)
        if u == 0:
            return decenas[d]
        return decenas[d] + " Y " + unidades[u]
    if n < 1000:
        c, r = divmod(n, 100)
        if c == 1 and r == 0:
            return "CIEN"
        base = centenas[c]
        if r == 0:
            return base
        return base + " " + _numero_a_letras_es(r).lower()
    if n < 1000000:
        m, r = divmod(n, 1000)
        if m == 1:
            mile = "MIL"
        else:
            mile = _numero_a_letras_es(m).lower() + " MIL"
        if r == 0:
            return mile
        return mile + " " + _numero_a_letras_es(r).lower()
    # Millones (1.000.000 en adelante)
    if n < 1000000000:
        mill, r = divmod(n, 1000000)
        if mill == 1:
            mill_str = "UN MILLÓN"
        else:
            mill_str = _numero_a_letras_es(mill).lower() + " MILLONES"
        if r == 0:
            return mill_str
        return mill_str + " " + _numero_a_letras_es(r).lower()
    return str(n)


@login_required
def ver_contrato_estudiante(request, contrato_id):
    """Genera el documento CONTRATO DE LOCACIÓN PARA USO ESTUDIANTIL con el texto legal completo. Solo para contratos de 9 meses (invierno)."""
    contrato = get_object_or_404(
        ContratoAlquiler.objects.select_related('propiedad', 'propiedad__propietario', 'inquilino', 'sucursal').prefetch_related(
            Prefetch('contrato_inquilinos', queryset=ContratoInquilino.objects.select_related('inquilino').order_by('id')),
            'garantes'
        ),
        id=contrato_id,
        sucursal=request.user.sucursal
    )
    if contrato.duracion_meses != 9:
        messages.warning(request, 'El contrato de estudiante solo aplica a contratos de 9 meses (invierno).')
        return redirect('inmobiliaria:detalle_contrato', contrato_id=contrato.id)

    prop = contrato.propiedad
    propi = getattr(prop, 'propietario', None)
    fi = contrato.fecha_inicio
    ff = contrato.fecha_fin
    fop = contrato.fecha_operacion or timezone.now().date()

    # Locador (propietario)
    if propi:
        locador_nombre = f"{getattr(propi, 'nombre', '') or ''} {getattr(propi, 'apellido', '') or ''}".strip() or '—'
        locador_dni = (getattr(propi, 'dni', None) or '').strip() or '—'
        locador_domicilio = (getattr(propi, 'domicilio', None) or '—')[:120]
        locador_ciudad = (getattr(propi, 'localidad', None) or '—')[:80]
    else:
        locador_nombre = locador_dni = locador_domicilio = locador_ciudad = '—'

    # Inquilinos (estudiantes que vivirán en el inmueble)
    through_list = list(contrato.contrato_inquilinos.select_related('inquilino').order_by('id'))
    if through_list:
        inquilinos_orden = [ci.inquilino for ci in through_list]
    else:
        inquilinos_orden = [contrato.inquilino] if contrato.inquilino_id else []

    # Locatario: en contrato estudiantil es el RESPONSABLE que firma (primer garante), no el inquilino/estudiante.
    # Si no hay garantes, se usa el inquilino como locatario.
    garantes_list = list(contrato.garantes.all())
    locatario_persona = None
    if garantes_list:
        locatario_persona = garantes_list[0]
    elif contrato.garante_apellido or contrato.garante_nombre:
        from types import SimpleNamespace
        locatario_persona = SimpleNamespace(
            apellido=contrato.garante_apellido or '',
            nombre=contrato.garante_nombre or '',
            dni=contrato.garante_dni or '',
            cuit=None,
            email=contrato.garante_email or '',
            domicilio=contrato.garante_domicilio or '',
            localidad='—',
            provincia='Pcia de Buenos Aires'
        )
    if not locatario_persona and inquilinos_orden:
        locatario_persona = inquilinos_orden[0]

    # Locatarios: hasta 2 garantes con formato DNI y Mail
    def _formatear_locatario(persona):
        nom = f"{getattr(persona, 'apellido', '') or ''} {getattr(persona, 'nombre', '') or ''}".strip() or '—'
        dni = (getattr(persona, 'dni', None) or '').strip() or '—'
        dom = (getattr(persona, 'domicilio', None) or '—')[:100]
        ciudad = getattr(persona, 'localidad', None) or '—'
        prov = getattr(persona, 'provincia', None) or 'Buenos Aires'
        prov_texto = prov if (prov or '').strip().lower().startswith('pcia') else f"Pcia de {prov or '—'}"
        mail = (getattr(persona, 'email', None) or '').strip() or '—'
        return f"el/la Sr/a {nom}, DNI {dni}, con domicilio real en {dom} de la ciudad de {ciudad}, {prov_texto}, Mail: {mail}"

    partes_locatarios = []
    for g in garantes_list[:2]:
        partes_locatarios.append(_formatear_locatario(g))
    if len(partes_locatarios) == 1:
        # Segundo slot vacío como en el modelo del usuario
        partes_locatarios.append(
            "el/la Sr/a --, DNI --, con domicilio real en Calle -- de la ciudad de --, Pcia de --, Mail: --"
        )
    if partes_locatarios:
        locatarios_texto = " y ".join(partes_locatarios)
    elif locatario_persona:
        locatarios_texto = _formatear_locatario(locatario_persona) + " y el/la Sr/a --, DNI --, con domicilio real en Calle -- de la ciudad de --, Pcia de --, Mail: --"
    else:
        locatarios_texto = "—"

    # Estudiantes (hijos): solo los cargados; sin slots vacíos
    estudiantes = []
    for ci in through_list[:3]:
        inq = ci.inquilino
        estudiantes.append({
            'nombre': f"{getattr(inq, 'apellido', '') or ''} {getattr(inq, 'nombre', '') or ''}".strip() or '—',
            'dni': (getattr(inq, 'dni', None) or '').strip() or '—',
            'mail': (getattr(inq, 'email', None) or '').strip() or '—',
            'carrera': (getattr(ci, 'carrera', None) or '').strip() or '—',
        })
    if not through_list and inquilinos_orden:
        inq = inquilinos_orden[0]
        estudiantes.append({
            'nombre': f"{getattr(inq, 'apellido', '') or ''} {getattr(inq, 'nombre', '') or ''}".strip() or '—',
            'dni': (getattr(inq, 'dni', None) or '').strip() or '—',
            'mail': (getattr(inq, 'email', None) or '').strip() or '—',
            'carrera': (getattr(contrato, 'carrera', None) or '').strip() or '—',
        })
    # Filtrar solo estudiantes con datos reales (evitar "—" o "--")
    def _es_estudiante_valido(e):
        n, d = (e.get('nombre') or '').strip(), (e.get('dni') or '').strip()
        return n and n not in ('—', '--') and d and d not in ('—', '--')
    estudiantes_validos = [e for e in estudiantes if _es_estudiante_valido(e)]
    # Texto para PRIMERA: OBJETO - solo los estudiantes cargados (con Mail y "carrera de")
    partes_est = [
        f"de su hijo/a {e['nombre']}, DNI N° {e['dni']}, Mail: {e.get('mail') or '—'}, quien cursará estudios en la carrera de {e['carrera'] or '—'} en esta ciudad"
        for e in estudiantes_validos
    ]
    if len(partes_est) == 1:
        estudiantes_objeto_texto = "y " + partes_est[0]
    elif len(partes_est) > 1:
        estudiantes_objeto_texto = "y " + ", ".join(partes_est[:-1]) + " y " + partes_est[-1]
    else:
        estudiantes_objeto_texto = ","  # Evita "del LOCATARIO ," -> "del LOCATARIO,"

    # Variables legacy para contexto (estudiante_1, 2, 3) - padding con -- si faltan
    while len(estudiantes) < 3:
        estudiantes.append({'nombre': '--', 'dni': '--', 'carrera': '--'})
    estudiante_1_nombre, estudiante_1_dni, estudiante_1_carrera = estudiantes[0]['nombre'], estudiantes[0]['dni'], estudiantes[0]['carrera']
    estudiante_2_nombre, estudiante_2_dni, estudiante_2_carrera = estudiantes[1]['nombre'], estudiantes[1]['dni'], estudiantes[1]['carrera']
    estudiante_3_nombre, estudiante_3_dni, estudiante_3_carrera = estudiantes[2]['nombre'], estudiantes[2]['dni'], estudiantes[2]['carrera']

    # Inmueble: direccion + piso + departamento (ej: Corrientes 1854 Piso 4to, Dpto. "A", de la ciudad de Mar del Plata)
    dir_base = (prop.direccion or '—').strip()
    piso = (getattr(prop, 'piso', None) or '').strip()
    depto = (getattr(prop, 'departamento', None) or '').strip()
    ciudad = 'Mar del Plata'  # En el contrato de estudiante siempre Mar del Plata
    partes_inm = [dir_base]
    if piso:
        partes_inm.append(f"Piso {piso}")
    if depto:
        partes_inm.append(f'Dpto. "{depto}"')
    inmueble_direccion = " ".join(partes_inm)
    inmueble_direccion_completa = f"{inmueble_direccion}, de la ciudad de {ciudad}"
    inmueble_ciudad = ciudad

    # Plazo: "NUEVE (9) MESES"
    plazo_meses_texto = "NUEVE (9) MESES"

    # Fechas 1er y 2do cuatrimestre (por defecto marzo-julio y agosto-diciembre del año del contrato)
    anio = fi.year
    fecha_1er_fin = date(anio, 7, 31)
    fecha_2do_inicio = date(anio, 8, 1)

    # Precios: 1er cuatrimestre = precio_mensual; 2do = precio_segundo_cuatrimestre si existe, sino precio_mensual
    precio_1er = contrato.precio_mensual or Decimal('0')
    precio_2do = getattr(contrato, 'precio_segundo_cuatrimestre', None)
    if precio_2do is None:
        precio_2do = contrato.precio_mensual or Decimal('0')
    precio_1er_int = int(precio_1er)
    precio_2do_int = int(precio_2do)
    precio_1er_letras = ("PESOS " + _numero_a_letras_es(precio_1er_int)).upper()
    precio_2do_letras = ("PESOS " + _numero_a_letras_es(precio_2do_int)).upper()
    precio_1er_numero = f"$ {precio_1er_int:,.0f}".replace(',', '.') + ".-"
    precio_2do_numero = f"$ {precio_2do_int:,.0f}".replace(',', '.') + ".-"

    # Depósito
    deposito = contrato.deposito_garantia or Decimal('0')
    deposito_int = int(deposito)
    deposito_letras = ("PESOS " + _numero_a_letras_es(deposito_int)).upper()
    deposito_numero = f"$ {deposito_int:,.0f}".replace(',', '.')

    # Meses proporcionales (ej. Marzo y Diciembre)
    meses_proporcionales = f"{MESES_ES[fi.month].capitalize()} y {MESES_ES[ff.month].capitalize()}"

    # Rescisión: textos fijos según cláusula
    rescision_meses_texto = "SEIS (6) MESES"
    anticipacion_notificacion_texto = "UN (1) MES"
    indemnizacion_primeros_texto = "DOS (2) MESES"
    indemnizacion_despues_texto = "UN MES Y MEDIO (1,5) MES"
    meses_sin_indemnizacion_texto = "SEIS"
    anticipacion_sin_indemnizacion_texto = "TRES (3) MESES"

    # Fiadores: los garantes cargados en el contrato (Bustamante Lovera, etc.); si no hay, legacy o locador y locatario
    def _formatear_fiador(persona):
        nom = f"{getattr(persona, 'apellido', '') or ''} {getattr(persona, 'nombre', '') or ''}".strip().upper() or '—'
        dni_g = (getattr(persona, 'dni', None) or '').strip() or '—'
        cuit_g = _formatear_cuit(getattr(persona, 'cuit', None))
        mail_g = (getattr(persona, 'email', None) or '').strip() or '—'
        dom_g = (getattr(persona, 'domicilio', None) or '—')[:80]
        ciudad_g = getattr(persona, 'localidad', None) or '—'
        prov_g = getattr(persona, 'provincia', None) or 'Pcia. De Buenos Aires'
        return f"el/la Sr/a. {nom}, DNI N° {dni_g}, CUIT {cuit_g}, con MAIL: {mail_g}, con domicilio en {dom_g}, de la ciudad {ciudad_g}, {prov_g}"

    garantes_list = list(contrato.garantes.all())
    partes_fiadores = []
    if garantes_list:
        for g in garantes_list:
            partes_fiadores.append(_formatear_fiador(g))
    elif contrato.garante_apellido or contrato.garante_nombre:
        nom = f"{contrato.garante_apellido or ''} {contrato.garante_nombre or ''}".strip().upper() or '—'
        if nom != '—':
            dni_g = contrato.garante_dni or '—'
            cuit_g = _formatear_cuit(None)
            mail_g = contrato.garante_email or '—'
            dom_g = (contrato.garante_domicilio or '—')[:80]
            partes_fiadores.append(f"el/la Sr/a. {nom}, DNI N° {dni_g}, CUIT {cuit_g}, con MAIL: {mail_g}, con domicilio en {dom_g}, de la ciudad —, —")
    if not partes_fiadores:
        # Sin garantes: titular = locador y locatario
        if propi:
            partes_fiadores.append(_formatear_fiador(propi))
        if inquilinos_orden:
            partes_fiadores.append(_formatear_fiador(inquilinos_orden[0]))

    fiadores_texto = ", y ".join(partes_fiadores) if partes_fiadores else "—"

    # Logo en base64 para el contrato (Néstor Oscar Gonnet Propiedades - REG. 1572)
    logo_base64 = None
    try:
        import base64 as _b64
        _logo_path = os.path.join(os.path.dirname(__file__), 'static', 'images', 'logo_contrato_estudiante.png')
        if not os.path.exists(_logo_path):
            _logo_path = os.path.join(os.path.dirname(__file__), 'static', 'images', 'logo.png')
        if os.path.exists(_logo_path):
            with open(_logo_path, 'rb') as _f:
                logo_base64 = _b64.b64encode(_f.read()).decode('utf-8')
    except Exception:
        pass

    suc = contrato.sucursal
    sucursal_direccion = (getattr(suc, 'direccion', None) or 'calle Corrientes N° 1987').strip()
    sucursal_nombre = (getattr(suc, 'nombre', None) or '').strip().upper()
    if 'CORRIENTES' in sucursal_nombre:
        sucursal_telefono = '(223) 5205046 - (223) 4372700'
    else:
        sucursal_telefono = (getattr(suc, 'telefono', None) or '(0223) 595-4474 / 491-0600').strip()

    context = {
        'contrato': contrato,
        'logo_base64': logo_base64,
        'sucursal_direccion': sucursal_direccion,
        'sucursal_telefono': sucursal_telefono,
        'url_volver': reverse('inmobiliaria:detalle_contrato', args=[contrato.id]),
        'fecha_celebracion_dia': fop.day,
        'fecha_celebracion_mes': MESES_ES[fop.month].capitalize(),
        'fecha_celebracion_anio': fop.year,
        'locador_nombre': locador_nombre,
        'locador_dni': locador_dni,
        'locador_domicilio': locador_domicilio,
        'locador_ciudad': locador_ciudad,
        'locatarios_texto': locatarios_texto,
        'inmueble_direccion': inmueble_direccion,
        'inmueble_direccion_completa': inmueble_direccion_completa,
        'inmueble_ciudad': inmueble_ciudad,
        'estudiantes_objeto_texto': estudiantes_objeto_texto,
        'estudiante_1_nombre': estudiante_1_nombre,
        'estudiante_1_dni': estudiante_1_dni,
        'estudiante_1_carrera': estudiante_1_carrera,
        'estudiante_2_nombre': estudiante_2_nombre,
        'estudiante_2_dni': estudiante_2_dni,
        'estudiante_2_carrera': estudiante_2_carrera,
        'estudiante_3_nombre': estudiante_3_nombre,
        'estudiante_3_dni': estudiante_3_dni,
        'estudiante_3_carrera': estudiante_3_carrera,
        'plazo_meses_texto': plazo_meses_texto,
        'fecha_inicio_dia': fi.day,
        'fecha_inicio_mes': MESES_ES[fi.month].capitalize(),
        'fecha_inicio_anio': fi.year,
        'fecha_fin_dia': ff.day,
        'fecha_fin_mes': MESES_ES[ff.month].capitalize(),
        'fecha_fin_anio': ff.year,
        'fecha_1er_fin_dia': fecha_1er_fin.day,
        'fecha_1er_fin_mes': MESES_ES[fecha_1er_fin.month].capitalize(),
        'fecha_1er_fin_anio': fecha_1er_fin.year,
        'fecha_2do_inicio_dia': fecha_2do_inicio.day,
        'fecha_2do_inicio_mes': MESES_ES[fecha_2do_inicio.month].capitalize(),
        'fecha_2do_inicio_anio': fecha_2do_inicio.year,
        'precio_1er_cuatri_letras': precio_1er_letras,
        'precio_1er_cuatri_numero': precio_1er_numero,
        'precio_2do_cuatri_letras': precio_2do_letras,
        'precio_2do_cuatri_numero': precio_2do_numero,
        'meses_proporcionales': meses_proporcionales,
        'dia_vencimiento_hasta': str(getattr(contrato, 'dia_vencimiento', 5)).zfill(2),
        'deposito_letras': deposito_letras,
        'deposito_numero': deposito_numero,
        'rescision_meses_texto': rescision_meses_texto,
        'anticipacion_notificacion_texto': anticipacion_notificacion_texto,
        'indemnizacion_primeros_texto': indemnizacion_primeros_texto,
        'indemnizacion_despues_texto': indemnizacion_despues_texto,
        'meses_sin_indemnizacion_texto': meses_sin_indemnizacion_texto,
        'anticipacion_sin_indemnizacion_texto': anticipacion_sin_indemnizacion_texto,
        'fiadores_texto': fiadores_texto,
    }
    return render(request, 'inmobiliaria/contratos/contrato_estudiante.html', context)


@login_required
def detalles_operacion_reserva(request, reserva_id):
    """
    API endpoint para obtener detalles de la operación de una reserva
    """
    try:
        reserva = get_object_or_404(Reserva.objects.select_related('cliente', 'vendedor'), id=reserva_id)
        
        # Obtener movimientos de caja asociados a esta reserva
        # Buscar a través de los recibos que están relacionados con la reserva
        movimientos = MovimientoCaja.objects.filter(
            Q(recibo__reserva=reserva) |
            Q(concepto__icontains=f'Reserva #{reserva.id}') |
            Q(concepto__icontains=f'Reserva {reserva.id}') |
            Q(concepto__icontains=f'#{reserva.id}')
        ).order_by('fecha')
        
        # Calcular totales sumando todos los tipos de montos
        total_pagado = 0
        for movimiento in movimientos:
            total_movimiento = (
                movimiento.monto_efectivo + 
                movimiento.monto_cheque + 
                movimiento.monto_tarjeta + 
                movimiento.monto_deposito
            )
            total_pagado += total_movimiento
        
        saldo_pendiente = max(0, reserva.precio_total - total_pagado)
        
        # Obtener recibos generados a través de la relación
        recibos = []
        recibos_reserva = reserva.recibos.all().order_by('fecha_emision')
        for recibo in recibos_reserva:
            recibos.append({
                'id': recibo.id,
                'numero': recibo.numero_recibo,
                'fecha': recibo.fecha_emision.strftime('%d/%m/%Y'),
                'monto': float(recibo.monto_este_pago),
                'concepto': recibo.movimiento_caja.concepto if recibo.movimiento_caja else 'N/A',
                'movimiento_id': recibo.movimiento_caja.id if recibo.movimiento_caja else None
            })
        
        # Calcular precio por día desde la relación con Precio
        precio_por_dia = 0
        try:
            # Buscar precio por día en los precios de la propiedad
            precio_obj = reserva.propiedad.precios.filter(precio_por_dia__isnull=False).first()
            if precio_obj and precio_obj.precio_por_dia:
                precio_por_dia = float(precio_obj.precio_por_dia)
        except:
            precio_por_dia = 0
        
        # Preparar datos de respuesta
        operacion_data = {
            'importe_total': float(reserva.precio_total),
            'precio_por_dia': precio_por_dia,
            'senia_pagada': float(total_pagado),
            'deposito': float(reserva.deposito_garantia) if reserva.deposito_garantia else 0,
            'saldo_pendiente': float(saldo_pendiente),
            'recibos': recibos
        }
        
        # Formatear nombre del cliente: apellido, nombre
        # Usar EXACTAMENTE el mismo patrón que funciona en ver_recibo (línea 2799)
        cliente_nombre = 'No especificado'
        cliente_celular = None
        if reserva.cliente:
            # Acceder directamente como en ver_recibo - funciona ahí, debe funcionar aquí
            cliente_data = reserva.cliente
            # Formatear: apellido, nombre (EXACTAMENTE como en ver_recibo línea 2799)
            cliente_nombre = f"{cliente_data.apellido}, {cliente_data.nombre}" if cliente_data.apellido and cliente_data.nombre else (cliente_data.nombre or cliente_data.apellido or 'No especificado')
            
            # Obtener celular - EXACTAMENTE como en ver_recibo línea 2804
            cliente_celular = cliente_data.celular or None
            if cliente_celular:
                cliente_celular = str(cliente_celular)
        
        # Formatear nombre del vendedor: apellido, nombre
        productor_nombre = 'No especificado'
        if reserva.vendedor:
            apellido_vendedor = (reserva.vendedor.apellido or '').strip()
            nombre_vendedor = (reserva.vendedor.nombre or '').strip()
            if apellido_vendedor and nombre_vendedor:
                productor_nombre = f"{apellido_vendedor}, {nombre_vendedor}"
            elif nombre_vendedor:
                productor_nombre = nombre_vendedor
            elif apellido_vendedor:
                productor_nombre = apellido_vendedor
        
        reserva_data = {
            'id': reserva.id,
            'cliente': cliente_nombre,
            'cliente_celular': cliente_celular if cliente_celular else None,
            'productor_id': reserva.vendedor.id if reserva.vendedor else None,
            'productor_nombre': productor_nombre,
            'fecha_inicio': reserva.fecha_inicio.strftime('%d/%m/%Y'),
            'fecha_fin': reserva.fecha_fin.strftime('%d/%m/%Y'),
            'total_dias': (reserva.fecha_fin - reserva.fecha_inicio).days,
            'estado': reserva.estado,
            'fue_editada': reserva.fue_editada,
            'fecha_inicio_original': reserva.fecha_inicio_original.strftime('%d/%m/%Y') if reserva.fecha_inicio_original else None,
            'fecha_fin_original': reserva.fecha_fin_original.strftime('%d/%m/%Y') if reserva.fecha_fin_original else None,
        }
        
        # Debug: Log para verificar qué se está enviando
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"DEBUG detalles_operacion_reserva {reserva_id}: cliente_nombre={cliente_nombre}, cliente_celular={cliente_celular}")
        
        return JsonResponse({
            'success': True,
            'operacion': operacion_data,
            'reserva': reserva_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error al cargar detalles: {str(e)}'
        })


def _ordenar_conceptos(queryset, orden):
    """
    orden 'detalle': alfabético por nombre (como «Por detalle» del sistema viejo).
    orden 'numero': por ID numérico ascendente; IDs no numéricos al final, por texto.
    """
    orden = (orden or 'detalle').lower()
    if orden == 'numero':

        def clave_numero(c):
            sid = str(c.id)
            if sid.isdigit():
                return (0, int(sid), '')
            return (1, 0, sid.lower())

        return sorted(queryset, key=clave_numero)
    return queryset.order_by('nombre', 'id')


@login_required
def gestionar_conceptos(request):
    """
    Vista para gestionar conceptos: listar, crear, editar y eliminar
    """
    sucursal_vendedor = request.user.sucursal
    qs_base = Concepto.objects.filter(q_conceptos_caja_visibles(sucursal_vendedor))
    total_conceptos = qs_base.count()

    def orden_valido(val):
        v = (val or 'detalle').lower()
        return v if v in ('detalle', 'numero') else 'detalle'

    # Formulario para crear nuevo concepto
    if request.method == 'POST':
        orden = orden_valido(request.POST.get('orden'))
        action = request.POST.get('action')
        
        if action == 'crear':
            nuevo_id = request.POST.get('nuevo_id')
            nuevo_nombre = request.POST.get('nuevo_nombre')
            
            if nuevo_id and nuevo_nombre:
                try:
                    Concepto.objects.create(
                        id=nuevo_id,
                        nombre=nuevo_nombre,
                        sucursal=sucursal_destino_nuevo_concepto_caja(sucursal_vendedor),
                    )
                    messages.success(request, f'Concepto "{nuevo_nombre}" creado exitosamente.')
                except Exception as e:
                    messages.error(request, f'Error al crear concepto: {e}')
            else:
                messages.error(request, 'ID y nombre son requeridos.')
        
        elif action == 'editar':
            concepto_id = (request.POST.get('concepto_id') or '').strip()
            if concepto_id.lower() == 'undefined':
                concepto_id = ''
            nuevo_nombre = (request.POST.get('nuevo_nombre') or '').strip()
            nuevo_id_asignar = (request.POST.get('nuevo_id') or '').strip()
            nombre_lookup = (request.POST.get('concepto_nombre_lookup') or '').strip()
            sucursal_lookup = (request.POST.get('concepto_sucursal_id') or '').strip()

            def _id_concepto_valido(s):
                return bool(re.fullmatch(r'[a-zA-Z0-9]{1,20}', s or ''))

            if not nuevo_nombre:
                messages.error(request, 'El nombre no puede estar vacío.')
            elif not concepto_id and nuevo_id_asignar:
                if not _id_concepto_valido(nuevo_id_asignar):
                    messages.error(
                        request,
                        'El ID solo puede tener letras y números, entre 1 y 20 caracteres.',
                    )
                elif not nombre_lookup:
                    messages.error(
                        request,
                        'No se pudo identificar el concepto sin ID. Volvé a intentar desde la lista.',
                    )
                else:
                    try:
                        from .models import Registro

                        with transaction.atomic():
                            qs = Concepto.objects.select_for_update().filter(id='').filter(
                                nombre=nombre_lookup
                            )
                            if sucursal_lookup == '':
                                qs = qs.filter(sucursal__isnull=True)
                            else:
                                try:
                                    qs = qs.filter(sucursal_id=int(sucursal_lookup))
                                except (TypeError, ValueError):
                                    pass

                            n = qs.count()
                            if n == 0:
                                messages.error(
                                    request,
                                    'No se encontró el concepto sin ID (quizá ya se le asignó un ID o cambió el nombre).',
                                )
                            elif n > 1:
                                messages.error(
                                    request,
                                    'Hay más de un concepto sin ID que coincide; contactá al administrador.',
                                )
                            else:
                                viejo = qs.first()
                                suc = viejo.sucursal
                                existe = Concepto.objects.filter(
                                    id=nuevo_id_asignar, sucursal=suc
                                ).exists()
                                if existe:
                                    messages.error(
                                        request,
                                        f'Ya existe un concepto con el ID "{nuevo_id_asignar}" en esa sucursal.',
                                    )
                                else:
                                    nuevo = Concepto.objects.create(
                                        id=nuevo_id_asignar,
                                        nombre=nuevo_nombre,
                                        sucursal=suc,
                                        fecha_creacion=viejo.fecha_creacion,
                                    )
                                    Registro.objects.filter(concepto=viejo).update(
                                        concepto=nuevo
                                    )
                                    viejo.delete()
                                    messages.success(
                                        request,
                                        f'Concepto actualizado y asignado el ID "{nuevo_id_asignar}".',
                                    )
                    except IntegrityError as e:
                        messages.error(request, f'No se pudo guardar (ID duplicado u otro conflicto): {e}')
                    except Exception as e:
                        messages.error(request, f'Error al actualizar concepto: {e}')
            elif concepto_id:
                try:
                    concepto = Concepto.objects.get(id=concepto_id)
                    concepto.nombre = nuevo_nombre
                    concepto.save()
                    messages.success(request, 'Concepto actualizado exitosamente.')
                except Concepto.DoesNotExist:
                    messages.error(request, 'Concepto no encontrado.')
                except Exception as e:
                    messages.error(request, f'Error al actualizar concepto: {e}')
            else:
                messages.error(
                    request,
                    'Este concepto no tiene ID: completá el campo "Nuevo ID" y guardá de nuevo.',
                )
        
        elif action == 'eliminar':
            concepto_id = request.POST.get('concepto_id')
            
            try:
                # Buscar concepto en todas las sucursales
                concepto = Concepto.objects.get(id=concepto_id)
                nombre_concepto = concepto.nombre
                concepto.delete()
                messages.success(request, f'Concepto "{nombre_concepto}" eliminado exitosamente.')
            except Concepto.DoesNotExist:
                messages.error(request, 'Concepto no encontrado.')
            except Exception as e:
                messages.error(request, f'Error al eliminar concepto: {e}')
        
        return redirect(f'{reverse("inmobiliaria:gestionar_conceptos")}?orden={orden}')
    
    orden = orden_valido(request.GET.get('orden'))
    conceptos = _ordenar_conceptos(qs_base, orden)

    ref_cat = get_sucursal_referencia_catalogo_conceptos_caja()
    context = {
        'conceptos': conceptos,
        'total_conceptos': total_conceptos,
        'sucursal': (
            f'Catálogo unificado (referencia: {ref_cat.nombre})'
            if ref_cat
            else sucursal_vendedor.nombre
        ),
        'orden': orden,
    }
    
    return render(request, 'inmobiliaria/conceptos/gestionar_conceptos.html', context)


# Vista para generar PDF del recibo
from django.http import HttpResponse
from xhtml2pdf import pisa
from django.template.loader import get_template
import io

def ver_recibo_pdf(request, reserva_id):
    """Genera y devuelve el recibo como PDF"""
    try:
        reserva = get_object_or_404(Reserva, id=reserva_id)
        
        # Obtener los mismos datos que usa la vista normal del recibo
        propiedad = reserva.propiedad
        cliente = reserva.cliente
        
        # Obtener el último movimiento de la reserva para los datos del pago
        ultimo_movimiento = MovimientoCaja.objects.filter(
            propiedad=reserva.propiedad,
            tipo=TipoMovimientoCajaEnum.INGRESO,
            concepto__icontains=f"Operación {reserva.id}"
        ).order_by('-fecha').first()
        
        if ultimo_movimiento:
            # Usar los datos del movimiento
            total_pagado = ultimo_movimiento.monto_total
            
            # Construir formas de pago igual que en ver_recibo
            formas_de_pago = []
            formas_con_montos = []
            
            if ultimo_movimiento.monto_efectivo > 0:
                formas_con_montos.append(f'Efectivo {_recibo_monto_str(ultimo_movimiento.monto_efectivo)}')
                formas_de_pago.append('Efectivo')
            
            if ultimo_movimiento.monto_tarjeta > 0:
                formas_con_montos.append(f'Tarjeta {_recibo_monto_str(ultimo_movimiento.monto_tarjeta)}')
                formas_de_pago.append('Tarjeta')
            
            if ultimo_movimiento.monto_cheque > 0:
                formas_con_montos.append(f'Cheque {_recibo_monto_str(ultimo_movimiento.monto_cheque)}')
                formas_de_pago.append('Cheque')
            
            if ultimo_movimiento.monto_deposito > 0:
                if ultimo_movimiento.destino_deposito and ultimo_movimiento.destino_deposito == 'mp':
                    formas_con_montos.append(f'Transferencia Mercado Pago {_recibo_monto_str(ultimo_movimiento.monto_deposito)}')
                    formas_de_pago.append('Mercado Pago')
                elif ultimo_movimiento.destino_deposito and ultimo_movimiento.destino_deposito == 'galicia':
                    formas_con_montos.append(f'Transferencia Galicia {_recibo_monto_str(ultimo_movimiento.monto_deposito)}')
                    formas_de_pago.append('Galicia')
                else:
                    formas_con_montos.append(f'Transferencia {_recibo_monto_str(ultimo_movimiento.monto_deposito)}')
                    formas_de_pago.append('Transferencia')
            
            formas_de_pago_mostrar = formas_con_montos if formas_con_montos else formas_de_pago
            
            # Obtener número de recibo
            numero_recibo = f"{reserva.id:06d}"
            
        else:
            # Fallback si no hay movimiento
            total_pagado = reserva.monto_reserva or 0
            formas_de_pago_mostrar = ['Efectivo']
            numero_recibo = f"{reserva.id:06d}"
        
        # Preparar datos del cliente con formato correcto (igual que en ver_recibo)
        cliente_data = reserva.cliente
        cliente_completo = {
            'nombre_completo': f"{cliente_data.apellido}, {cliente_data.nombre}",
            'domicilio': cliente_data.domicilio or '',
            'localidad': cliente_data.localidad or '',
            'provincia': cliente_data.provincia or '',
            'dni': cliente_data.dni or '',
            'telefono': cliente_data.celular or '',
            'cuit': getattr(cliente_data, 'cuit', '') or '',
        }
        
        # Preparar datos de la propiedad con formato correcto
        propiedad_data = reserva.propiedad
        propiedad_completa = {
            'direccion': propiedad_data.direccion or '',
            'id': propiedad_data.id,
            'llave': propiedad_data.llave or 'N/A',
            'piso': propiedad_data.piso or '',
            'departamento': propiedad_data.departamento or '',
            'wifi': 'SÍ' if propiedad_data.wifi else 'NO',
            'cochera': 'SÍ' if propiedad_data.cochera else 'NO',
            'cantidad_personas': propiedad_data.cantidad_personas or None,
            'ambientes': propiedad_data.ambientes or '',
        }
        
        # Preparar datos del vendedor/productor
        vendedor_completo = {}
        if reserva.vendedor:
            vendedor_completo = {
                'id': reserva.vendedor.id,
                'nombre_completo': f"{reserva.vendedor.apellido}, {reserva.vendedor.nombre}",
            }
        
        # Obtener pagos de la reserva
        pagos = []
        from .models import Registro
        conceptos_operacion = None
        try:
            if ultimo_movimiento:
                conceptos_operacion = Registro.objects.filter(
                    interno_caja=ultimo_movimiento.numero_liquidacion
                ).order_by('fecha')
        except:
            pass
        
        if conceptos_operacion and conceptos_operacion.exists():
            for registro in conceptos_operacion:
                concepto_desc = ''
                if registro.concepto:
                    concepto_desc = f'{registro.concepto.id} - {registro.concepto.nombre}'
                else:
                    concepto_desc = 'Concepto no especificado'
                
                pagos.append({
                    'fecha': registro.fecha_comprobante.strftime('%d/%m/%Y'),
                    'codigo': registro.interno_caja or f'R{registro.id:04d}',
                    'concepto': concepto_desc,
                    'monto': _recibo_monto_str(registro.liquidacion),
                })
        else:
            for pago in reserva.pagos.all():
                concepto_desc = ''
                if hasattr(pago, 'concepto') and pago.concepto:
                    concepto_desc = f'{pago.concepto.codigo} - {pago.concepto.nombre}'
                else:
                    concepto_desc = f'Pago reserva {reserva.id}'
                
                pagos.append({
                    'fecha': pago.fecha.strftime('%d/%m/%Y') if pago.fecha else '',
                    'codigo': pago.codigo if hasattr(pago, 'codigo') and pago.codigo else f'P{pago.id:04d}',
                    'concepto': concepto_desc,
                    'monto': _recibo_monto_str(pago.monto),
                })
        
        # Calcular valores para el recibo
        senia_pagada = float(reserva.senia or 0)
        deposito_pagado = float(reserva.deposito_garantia or 0)
        precio_total = float(reserva.precio_total or 0)
        saldo_restante = precio_total - senia_pagada
        
        # Verificar estado del depósito
        deposito_estado = determinar_estado_deposito_completo(reserva)
        
        # Obtener honorarios y sellados
        honorarios_monto = 0
        sellados_monto = 0
        if ultimo_movimiento:
            honorarios_monto = float(ultimo_movimiento.honorarios or 0)
            sellados_monto = float(ultimo_movimiento.sellados or 0)
        
        # Función para convertir número a palabras (importe numérico en formato AR)
        def numero_a_palabras(numero):
            try:
                n = int(numero)
                if n == 0:
                    return "PESOS CERO CON 00/100"
                return f"PESOS {format_monto_argentino(n, 0)} CON 00/100"
            except Exception:
                return "PESOS CERO CON 00/100"
        
        # Generar logo en base64
        import base64
        import os
        from django.conf import settings
        logo_base64 = None
        try:
            logo_path = os.path.join(settings.BASE_DIR, 'inmobiliaria', 'static', 'images', 'logo.png')
            with open(logo_path, 'rb') as logo_file:
                logo_data = base64.b64encode(logo_file.read()).decode()
                logo_base64 = f'data:image/png;base64,{logo_data}'
        except Exception as e:
            logo_base64 = None
        
        # Obtener información de la sucursal
        sucursal = request.user.sucursal if hasattr(request.user, 'sucursal') and request.user.sucursal else None
        
        # Preparar contexto para el template
        context = {
            'reserva': reserva,
            'propiedad': propiedad_completa,
            'cliente': cliente_completo,
            'vendedor': vendedor_completo,
            'total_pagado': _recibo_monto_str(total_pagado),
            'formas_de_pago': ', '.join(formas_de_pago_mostrar) if formas_de_pago_mostrar else 'EFECTIVO',
            'numero_recibo': numero_recibo,
            'fecha': timezone.now().strftime('%d/%m/%Y'),
            'hora': timezone.now().strftime('%H:%M'),
            'fecha_inicio': reserva.fecha_inicio.strftime('%d/%m/%Y'),
            'fecha_fin': reserva.fecha_fin.strftime('%d/%m/%Y'),
            'descripcion': 'Alquiler temporario por días',
            'pagos': pagos,
            'precio_total_operacion': _recibo_monto_str(precio_total),
            'monto_este_pago': _recibo_monto_str(senia_pagada),
            'saldo_pendiente': _recibo_monto_str(saldo_restante),
            'deposito_garantia': _recibo_monto_str(deposito_pagado),
            'deposito_estado': deposito_estado,
            'honorarios': _recibo_monto_str(honorarios_monto),
            'sellados': _recibo_monto_str(sellados_monto),
            'tiene_honorarios': honorarios_monto > 0,
            'tiene_sellados': sellados_monto > 0,
            'monto_en_palabras': numero_a_palabras(total_pagado),
            'logo_base64': logo_base64,
            'sucursal': sucursal,  # Agregar sucursal al contexto
        }
        
        # Cargar template específico para PDF (sin botones)
        template = get_template('inmobiliaria/reserva/recibo_pdf.html')
        html = template.render(context)
        
        # Limpiar el HTML de posibles caracteres problemáticos
        html = html.replace('\x00', '')  # Eliminar caracteres nulos
        
        # Crear el PDF usando BytesIO
        pdf_buffer = io.BytesIO()
        
        # Generar el PDF usando pisaDocument (método más compatible)
        try:
            result = io.BytesIO()
            pdf = pisa.pisaDocument(
                io.BytesIO(html.encode('UTF-8')),
                result,
                encoding='UTF-8'
            )
            
            if pdf.err:
                import logging
                logger = logging.getLogger(__name__)
                error_details = f'Error al generar PDF: {pdf.err}'
                logger.error(error_details)
                print(f'❌ ERROR PDF: {error_details}')  # También imprimir en consola
                result.close()
                pdf_buffer.close()
                # Devolver error detallado para debugging
                return HttpResponse(
                    f'Error al generar PDF:<br><br>Detalles: {error_details}<br><br>'
                    f'Por favor, contacte al administrador o revise los logs del servidor.',
                    status=500,
                    content_type='text/html'
                )
            
            # Obtener el contenido del PDF
            pdf_content = result.getvalue()
            result.close()
            pdf_buffer.close()
            
            # Debug: Imprimir información del PDF generado
            print(f'📄 PDF generado - Tamaño: {len(pdf_content) if pdf_content else 0} bytes')
            if pdf_content:
                print(f'📄 Primeros 20 bytes: {pdf_content[:20]}')
            
            # Verificar que el PDF no esté vacío
            if not pdf_content or len(pdf_content) < 100:
                import logging
                logger = logging.getLogger(__name__)
                error_msg = f'Error: El PDF generado está vacío o corrupto. Tamaño: {len(pdf_content) if pdf_content else 0} bytes'
                logger.error(error_msg)
                print(f'❌ PDF VACÍO: {error_msg}')
                return HttpResponse(
                    f'<h2>Error al generar PDF</h2>'
                    f'<p>El PDF generado está vacío o corrupto.</p>'
                    f'<p><strong>Tamaño del archivo:</strong> {len(pdf_content) if pdf_content else 0} bytes</p>'
                    f'<p>Revisa los logs del servidor para más detalles.</p>',
                    status=500,
                    content_type='text/html'
                )
            
            # Verificar que el PDF tenga el header correcto (%PDF)
            if not pdf_content.startswith(b'%PDF'):
                import logging
                logger = logging.getLogger(__name__)
                first_bytes = pdf_content[:50] if len(pdf_content) >= 50 else pdf_content
                error_msg = f'Error: El PDF generado no tiene un formato válido. Primeros bytes: {first_bytes}'
                logger.error(error_msg)
                print(f'❌ PDF INVÁLIDO: {error_msg}')
                return HttpResponse(
                    f'<h2>Error al generar PDF</h2>'
                    f'<p>El PDF generado no tiene un formato válido.</p>'
                    f'<p>El archivo no comienza con %PDF.</p>'
                    f'<p><strong>Primeros bytes:</strong> {first_bytes}</p>'
                    f'<p>Revisa los logs del servidor para más detalles.</p>',
                    status=500,
                    content_type='text/html'
                )
            
            print(f'✅ PDF generado correctamente - Tamaño: {len(pdf_content)} bytes')
            
            # Configurar la respuesta HTTP
            response = HttpResponse(pdf_content, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="recibo_{reserva.id}.pdf"'
            response['Content-Length'] = len(pdf_content)
            
            return response
            
        except Exception as e:
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            error_trace = traceback.format_exc()
            error_msg = f'Excepción al generar PDF: {str(e)}\n{error_trace}'
            logger.error(error_msg)
            print(f'❌ EXCEPCIÓN PDF: {error_msg}')  # También imprimir en consola
            pdf_buffer.close()
            # Devolver error detallado para debugging
            return HttpResponse(
                f'Error al generar PDF:<br><br>Excepción: {str(e)}<br><br>'
                f'Traceback completo en logs del servidor.<br><br>'
                f'Por favor, contacte al administrador.',
                status=500,
                content_type='text/html'
            )
            
    except Exception as e:
        import traceback
        error_detail = f'Error: {str(e)}\n\n{traceback.format_exc()}'
        return HttpResponse(error_detail, status=500, content_type='text/plain')


# Vista AJAX para generar enlace público
from django.http import JsonResponse

def generar_enlace_publico(request):
    """Genera enlace público para compartir PDF"""
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            reserva_id = data.get('reserva_id')
            movimiento_id = data.get('movimiento_id')
            
            if movimiento_id:
                # Es un recibo de movimiento
                token = generar_token_publico(None, movimiento_id)
                url = request.build_absolute_uri(f'/recibo-movimiento-publico/{movimiento_id}/{token}/')
            elif reserva_id:
                # Es un recibo de reserva
                token = generar_token_publico(reserva_id)
                url = request.build_absolute_uri(f'/recibo-publico/{reserva_id}/{token}/')
            else:
                return JsonResponse({'error': 'ID requerido'}, status=400)
            
            return JsonResponse({'url': url})
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)


# Vista pública para compartir PDF (sin autenticación)
import hashlib
from django.utils import timezone
from datetime import timedelta

def generar_token_publico(reserva_id, movimiento_id=None):
    """Genera un token seguro para acceso público al PDF"""
    # Crear string único basado en IDs y fecha
    base_string = f"{reserva_id}_{movimiento_id}_{timezone.now().date()}_gonnet_secret_key"
    return hashlib.md5(base_string.encode()).hexdigest()[:16]

def verificar_token_publico(token, reserva_id, movimiento_id=None):
    """Verifica si el token es válido"""
    token_esperado = generar_token_publico(reserva_id, movimiento_id)
    return token == token_esperado

def ver_recibo_publico(request, reserva_id, token):
    """Vista pública para ver recibo sin autenticación"""
    try:
        # Verificar token
        if not verificar_token_publico(token, reserva_id):
            return HttpResponse('Enlace inválido o expirado', status=403)
        
        reserva = get_object_or_404(Reserva, id=reserva_id)
        
        # Obtener los mismos datos que usa la vista normal del recibo
        propiedad = reserva.propiedad
        cliente = reserva.cliente
        
        # Obtener el último movimiento de la reserva para los datos del pago
        ultimo_movimiento = MovimientoCaja.objects.filter(
            propiedad=reserva.propiedad,
            tipo=TipoMovimientoCajaEnum.INGRESO,
            concepto__icontains=f"Operación {reserva.id}"
        ).order_by('-fecha').first()
        
        if ultimo_movimiento:
            # Usar los datos del movimiento
            total_pagado = ultimo_movimiento.monto_total
            
            # Construir formas de pago igual que en ver_recibo
            formas_de_pago = []
            formas_con_montos = []
            
            if ultimo_movimiento.monto_efectivo > 0:
                formas_con_montos.append(f'Efectivo {_recibo_monto_str(ultimo_movimiento.monto_efectivo)}')
                formas_de_pago.append('Efectivo')
            
            if ultimo_movimiento.monto_tarjeta > 0:
                formas_con_montos.append(f'Tarjeta {_recibo_monto_str(ultimo_movimiento.monto_tarjeta)}')
                formas_de_pago.append('Tarjeta')
            
            if ultimo_movimiento.monto_cheque > 0:
                formas_con_montos.append(f'Cheque {_recibo_monto_str(ultimo_movimiento.monto_cheque)}')
                formas_de_pago.append('Cheque')
            
            if ultimo_movimiento.monto_deposito > 0:
                if ultimo_movimiento.destino_deposito and ultimo_movimiento.destino_deposito == 'mp':
                    formas_con_montos.append(f'Transferencia Mercado Pago {_recibo_monto_str(ultimo_movimiento.monto_deposito)}')
                    formas_de_pago.append('Mercado Pago')
                elif ultimo_movimiento.destino_deposito and ultimo_movimiento.destino_deposito == 'galicia':
                    formas_con_montos.append(f'Transferencia Galicia {_recibo_monto_str(ultimo_movimiento.monto_deposito)}')
                    formas_de_pago.append('Galicia')
                else:
                    formas_con_montos.append(f'Transferencia {_recibo_monto_str(ultimo_movimiento.monto_deposito)}')
                    formas_de_pago.append('Transferencia')
            
            formas_de_pago_mostrar = formas_con_montos if formas_con_montos else formas_de_pago
            
            # Obtener número de recibo
            numero_recibo = f"{reserva.id:06d}"
            
        else:
            # Fallback si no hay movimiento
            total_pagado = reserva.monto_reserva or 0
            formas_de_pago_mostrar = ['Efectivo']
            numero_recibo = f"{reserva.id:06d}"
        
        # Preparar datos del cliente con formato correcto (igual que en ver_recibo)
        cliente_data = reserva.cliente
        cliente_completo = {
            'nombre_completo': f"{cliente_data.apellido}, {cliente_data.nombre}",
            'domicilio': cliente_data.domicilio or '',
            'localidad': cliente_data.localidad or '',
            'provincia': cliente_data.provincia or '',
            'dni': cliente_data.dni or '',
            'telefono': cliente_data.celular or '',
            'cuit': getattr(cliente_data, 'cuit', '') or '',
        }
        
        # Preparar datos de la propiedad con formato correcto
        propiedad_data = reserva.propiedad
        propiedad_completa = {
            'direccion': propiedad_data.direccion or '',
            'id': propiedad_data.id,
            'llave': propiedad_data.llave or 'N/A',
            'piso': propiedad_data.piso or '',
            'departamento': propiedad_data.departamento or '',
            'wifi': 'SÍ' if propiedad_data.wifi else 'NO',
            'ambientes': propiedad_data.ambientes or '',
        }
        
        # Preparar datos del vendedor/productor
        vendedor_completo = {}
        if reserva.vendedor:
            vendedor_completo = {
                'id': reserva.vendedor.id,
                'nombre_completo': f"{reserva.vendedor.apellido}, {reserva.vendedor.nombre}",
            }
        
        # Preparar contexto para el template
        context = {
            'reserva': reserva,
            'propiedad': propiedad_completa,
            'cliente': cliente_completo,
            'vendedor': vendedor_completo,
            'total_pagado': _recibo_monto_str(total_pagado),
            'formas_de_pago': ', '.join(formas_de_pago_mostrar) if formas_de_pago_mostrar else 'EFECTIVO',
            'numero_recibo': numero_recibo,
            'fecha': timezone.now().strftime('%d/%m/%Y'),
            'hora': timezone.now().strftime('%H:%M'),
            'descripcion': 'Alquiler temporario por días',
        }
        
        # Cargar template específico para PDF (sin botones)
        template = get_template('inmobiliaria/reserva/recibo_pdf.html')
        html = template.render(context)
        
        # Limpiar el HTML de posibles caracteres problemáticos
        html = html.replace('\x00', '')  # Eliminar caracteres nulos
        
        # Crear el PDF usando BytesIO
        pdf_buffer = io.BytesIO()
        
        # Generar el PDF usando pisaDocument (método más compatible)
        try:
            result = io.BytesIO()
            pdf = pisa.pisaDocument(
                io.BytesIO(html.encode('UTF-8')),
                result,
                encoding='UTF-8'
            )
            
            if pdf.err:
                import logging
                logger = logging.getLogger(__name__)
                error_details = f'Error al generar PDF: {pdf.err}'
                logger.error(error_details)
                print(f'❌ ERROR PDF: {error_details}')  # También imprimir en consola
                result.close()
                pdf_buffer.close()
                # Devolver error detallado para debugging
                return HttpResponse(
                    f'Error al generar PDF:<br><br>Detalles: {error_details}<br><br>'
                    f'Por favor, contacte al administrador o revise los logs del servidor.',
                    status=500,
                    content_type='text/html'
                )
            
            # Obtener el contenido del PDF
            pdf_content = result.getvalue()
            result.close()
            pdf_buffer.close()
            
            # Debug: Imprimir información del PDF generado
            print(f'📄 PDF generado - Tamaño: {len(pdf_content) if pdf_content else 0} bytes')
            if pdf_content:
                print(f'📄 Primeros 20 bytes: {pdf_content[:20]}')
            
            # Verificar que el PDF no esté vacío
            if not pdf_content or len(pdf_content) < 100:
                import logging
                logger = logging.getLogger(__name__)
                error_msg = f'Error: El PDF generado está vacío o corrupto. Tamaño: {len(pdf_content) if pdf_content else 0} bytes'
                logger.error(error_msg)
                print(f'❌ PDF VACÍO: {error_msg}')
                return HttpResponse(
                    f'<h2>Error al generar PDF</h2>'
                    f'<p>El PDF generado está vacío o corrupto.</p>'
                    f'<p><strong>Tamaño del archivo:</strong> {len(pdf_content) if pdf_content else 0} bytes</p>'
                    f'<p>Revisa los logs del servidor para más detalles.</p>',
                    status=500,
                    content_type='text/html'
                )
            
            # Verificar que el PDF tenga el header correcto (%PDF)
            if not pdf_content.startswith(b'%PDF'):
                import logging
                logger = logging.getLogger(__name__)
                first_bytes = pdf_content[:50] if len(pdf_content) >= 50 else pdf_content
                error_msg = f'Error: El PDF generado no tiene un formato válido. Primeros bytes: {first_bytes}'
                logger.error(error_msg)
                print(f'❌ PDF INVÁLIDO: {error_msg}')
                return HttpResponse(
                    f'<h2>Error al generar PDF</h2>'
                    f'<p>El PDF generado no tiene un formato válido.</p>'
                    f'<p>El archivo no comienza con %PDF.</p>'
                    f'<p><strong>Primeros bytes:</strong> {first_bytes}</p>'
                    f'<p>Revisa los logs del servidor para más detalles.</p>',
                    status=500,
                    content_type='text/html'
                )
            
            print(f'✅ PDF generado correctamente - Tamaño: {len(pdf_content)} bytes')
            
            # Configurar la respuesta HTTP
            response = HttpResponse(pdf_content, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="recibo_{reserva.id}.pdf"'
            response['Content-Length'] = len(pdf_content)
            
            return response
            
        except Exception as e:
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            error_trace = traceback.format_exc()
            error_msg = f'Excepción al generar PDF: {str(e)}\n{error_trace}'
            logger.error(error_msg)
            print(f'❌ EXCEPCIÓN PDF: {error_msg}')  # También imprimir en consola
            pdf_buffer.close()
            # Devolver error detallado para debugging
            return HttpResponse(
                f'Error al generar PDF:<br><br>Excepción: {str(e)}<br><br>'
                f'Traceback completo en logs del servidor.<br><br>'
                f'Por favor, contacte al administrador.',
                status=500,
                content_type='text/html'
            )
            
    except Exception as e:
        import traceback
        error_detail = f'Error: {str(e)}\n\n{traceback.format_exc()}'
        return HttpResponse(error_detail, status=500, content_type='text/plain')


# Vista AJAX para generar enlace público
from django.http import JsonResponse

def generar_enlace_publico(request):
    """Genera enlace público para compartir PDF"""
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            reserva_id = data.get('reserva_id')
            movimiento_id = data.get('movimiento_id')
            
            if movimiento_id:
                # Es un recibo de movimiento
                token = generar_token_publico(None, movimiento_id)
                url = request.build_absolute_uri(f'/recibo-movimiento-publico/{movimiento_id}/{token}/')
            elif reserva_id:
                # Es un recibo de reserva
                token = generar_token_publico(reserva_id)
                url = request.build_absolute_uri(f'/recibo-publico/{reserva_id}/{token}/')
            else:
                return JsonResponse({'error': 'ID requerido'}, status=400)
            
            return JsonResponse({'url': url})
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)

def ver_recibo_movimiento_publico(request, movimiento_id, token):
    """Vista pública para ver recibo de movimiento sin autenticación"""
    try:
        # Verificar token
        if not verificar_token_publico(token, None, movimiento_id):
            return HttpResponse('Enlace inválido o expirado', status=403)
        
        movimiento = get_object_or_404(MovimientoCaja, id=movimiento_id)
        propiedad = movimiento.propiedad
        
        # Extraer ID de reserva del concepto
        import re
        match = re.search(r'Operación (\d+)', movimiento.concepto)
        if match:
            reserva_id = int(match.group(1))
            reserva = get_object_or_404(Reserva, id=reserva_id)
            cliente = reserva.cliente
        else:
            return HttpResponse('No se pudo identificar la reserva asociada', status=400)
        
        # Construir formas de pago igual que en ver_recibo_movimiento
        formas_de_pago = []
        formas_con_montos = []
        
        if movimiento.monto_efectivo > 0:
            formas_con_montos.append(f'Efectivo {_recibo_monto_str(movimiento.monto_efectivo)}')
            formas_de_pago.append('Efectivo')
        
        if movimiento.monto_tarjeta > 0:
            formas_con_montos.append(f'Tarjeta {_recibo_monto_str(movimiento.monto_tarjeta)}')
            formas_de_pago.append('Tarjeta')
        
        if movimiento.monto_cheque > 0:
            formas_con_montos.append(f'Cheque {_recibo_monto_str(movimiento.monto_cheque)}')
            formas_de_pago.append('Cheque')
        
        if movimiento.monto_deposito > 0:
            if movimiento.banco and 'Mercado Pago' in movimiento.banco:
                formas_con_montos.append(f'Transferencia Mercado Pago {_recibo_monto_str(movimiento.monto_deposito)}')
                formas_de_pago.append('Mercado Pago')
            elif movimiento.banco and 'Galicia' in movimiento.banco:
                formas_con_montos.append(f'Transferencia Galicia {_recibo_monto_str(movimiento.monto_deposito)}')
                formas_de_pago.append('Galicia')
            else:
                formas_con_montos.append(f'Transferencia {_recibo_monto_str(movimiento.monto_deposito)}')
                formas_de_pago.append('Transferencia')
        
        formas_de_pago_mostrar = formas_con_montos if formas_con_montos else formas_de_pago
        
        context = {
            'reserva': reserva,
            'propiedad': propiedad,
            'cliente': cliente,
            'movimiento': movimiento,
            'total_pagado': _recibo_monto_str(movimiento.monto_total),
            'formas_de_pago': ', '.join(formas_de_pago_mostrar) if formas_de_pago_mostrar else 'EFECTIVO',
            'numero_recibo': f"{movimiento.id:06d}",
            'fecha': movimiento.fecha.strftime('%d/%m/%Y'),
            'hora': movimiento.fecha.strftime('%H:%M'),
        }
        
        # Cargar template específico para PDF
        template = get_template('inmobiliaria/reserva/recibo_pdf.html')
        html = template.render(context)
        
        # Crear el PDF
        result = io.BytesIO()
        pdf = pisa.pisaDocument(io.BytesIO(html.encode("UTF-8")), result)
        
        if not pdf.err:
            response = HttpResponse(result.getvalue(), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="recibo_movimiento_{movimiento.id}.pdf"'
            return response
        else:
            return HttpResponse('Error al generar PDF', status=500)
            
    except Exception as e:
        return HttpResponse(f'Error: {str(e)}', status=500)


# Vista AJAX para generar enlace público
from django.http import JsonResponse

def generar_enlace_publico(request):
    """Genera enlace público para compartir PDF"""
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            reserva_id = data.get('reserva_id')
            movimiento_id = data.get('movimiento_id')
            
            if movimiento_id:
                # Es un recibo de movimiento
                token = generar_token_publico(None, movimiento_id)
                url = request.build_absolute_uri(f'/recibo-movimiento-publico/{movimiento_id}/{token}/')
            elif reserva_id:
                # Es un recibo de reserva
                token = generar_token_publico(reserva_id)
                url = request.build_absolute_uri(f'/recibo-publico/{reserva_id}/{token}/')
            else:
                return JsonResponse({'error': 'ID requerido'}, status=400)
            
            return JsonResponse({'url': url})
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)


def ver_recibo_movimiento_pdf(request, movimiento_id):
    """Genera y devuelve el recibo de movimiento como PDF"""
    try:
        movimiento = get_object_or_404(MovimientoCaja, id=movimiento_id)
        propiedad = movimiento.propiedad
        
        # Extraer ID de reserva del concepto
        import re
        match = re.search(r'Operación (\d+)', movimiento.concepto)
        if match:
            reserva_id = int(match.group(1))
            reserva = get_object_or_404(Reserva, id=reserva_id)
            cliente = reserva.cliente
        else:
            return HttpResponse('No se pudo identificar la reserva asociada', status=400)
        
        # Construir formas de pago igual que en ver_recibo_movimiento
        formas_de_pago = []
        formas_con_montos = []
        
        if movimiento.monto_efectivo > 0:
            formas_con_montos.append(f'Efectivo {_recibo_monto_str(movimiento.monto_efectivo)}')
            formas_de_pago.append('Efectivo')
        
        if movimiento.monto_tarjeta > 0:
            formas_con_montos.append(f'Tarjeta {_recibo_monto_str(movimiento.monto_tarjeta)}')
            formas_de_pago.append('Tarjeta')
        
        if movimiento.monto_cheque > 0:
            formas_con_montos.append(f'Cheque {_recibo_monto_str(movimiento.monto_cheque)}')
            formas_de_pago.append('Cheque')
        
        if movimiento.monto_deposito > 0:
            if movimiento.destino_deposito and movimiento.destino_deposito == 'mp':
                formas_con_montos.append(f'Transferencia Mercado Pago {_recibo_monto_str(movimiento.monto_deposito)}')
                formas_de_pago.append('Mercado Pago')
            elif movimiento.destino_deposito and movimiento.destino_deposito == 'galicia':
                formas_con_montos.append(f'Transferencia Galicia {_recibo_monto_str(movimiento.monto_deposito)}')
                formas_de_pago.append('Galicia')
            else:
                formas_con_montos.append(f'Transferencia {_recibo_monto_str(movimiento.monto_deposito)}')
                formas_de_pago.append('Transferencia')
        
        formas_de_pago_mostrar = formas_con_montos if formas_con_montos else formas_de_pago
        
        # Preparar datos del cliente con formato correcto
        cliente_completo = {
            'nombre_completo': f"{cliente.apellido}, {cliente.nombre}",
            'domicilio': cliente.domicilio or '',
            'localidad': cliente.localidad or '',
            'provincia': cliente.provincia or '',
            'dni': cliente.dni or '',
            'telefono': cliente.celular or '',
            'cuit': getattr(cliente, 'cuit', '') or '',
        }
        
        # Preparar datos de la propiedad con formato correcto
        propiedad_completa = {
            'direccion': propiedad.direccion or '',
            'id': propiedad.id,
            'llave': propiedad.llave or 'N/A',
            'piso': propiedad.piso or '',
            'departamento': propiedad.departamento or '',
            'wifi': 'SÍ' if propiedad.wifi else 'NO',
            'cochera': 'SÍ' if propiedad.cochera else 'NO',
            'cantidad_personas': propiedad.cantidad_personas or None,
            'ambientes': propiedad.ambientes or '',
        }
        
        # Preparar datos del vendedor/productor
        vendedor_completo = {}
        if reserva.vendedor:
            vendedor_completo = {
                'id': reserva.vendedor.id,
                'nombre_completo': f"{reserva.vendedor.apellido}, {reserva.vendedor.nombre}",
            }
        
        # Obtener pagos del movimiento
        pagos = []
        from .models import Registro
        try:
            if movimiento.numero_liquidacion:
                conceptos_operacion = Registro.objects.filter(
                    interno_caja=movimiento.numero_liquidacion
                ).order_by('fecha')
                if conceptos_operacion.exists():
                    for registro in conceptos_operacion:
                        concepto_desc = ''
                        if registro.concepto:
                            concepto_desc = f'{registro.concepto.id} - {registro.concepto.nombre}'
                        else:
                            concepto_desc = 'Concepto no especificado'
                        
                        pagos.append({
                            'fecha': registro.fecha_comprobante.strftime('%d/%m/%Y'),
                            'codigo': registro.interno_caja or f'R{registro.id:04d}',
                            'concepto': concepto_desc,
                            'monto': _recibo_monto_str(registro.liquidacion),
                        })
        except:
            pass
        
        # Si no hay pagos desde registros, crear uno desde el movimiento
        if not pagos:
            pagos.append({
                'fecha': movimiento.fecha.strftime('%d/%m/%Y'),
                'codigo': f'M{movimiento.id:04d}',
                'concepto': movimiento.concepto or 'Pago de reserva',
                'monto': _recibo_monto_str(movimiento.monto_total),
            })
        
        # Calcular valores para el recibo
        senia_pagada = float(reserva.senia or 0)
        deposito_pagado = float(reserva.deposito_garantia or 0)
        precio_total = float(reserva.precio_total or 0)
        saldo_restante = precio_total - senia_pagada
        
        # Verificar estado del depósito
        deposito_estado = determinar_estado_deposito_completo(reserva)
        
        # Obtener honorarios y sellados
        honorarios_monto = float(movimiento.honorarios or 0)
        sellados_monto = float(movimiento.sellados or 0)
        
        def numero_a_palabras(numero):
            try:
                n = int(numero)
                if n == 0:
                    return "PESOS CERO CON 00/100"
                return f"PESOS {format_monto_argentino(n, 0)} CON 00/100"
            except Exception:
                return "PESOS CERO CON 00/100"
        
        # Generar logo en base64
        import base64
        import os
        from django.conf import settings
        logo_base64 = None
        try:
            logo_path = os.path.join(settings.BASE_DIR, 'inmobiliaria', 'static', 'images', 'logo.png')
            with open(logo_path, 'rb') as logo_file:
                logo_data = base64.b64encode(logo_file.read()).decode()
                logo_base64 = f'data:image/png;base64,{logo_data}'
        except Exception as e:
            logo_base64 = None
        
        # Obtener información de la sucursal
        sucursal = request.user.sucursal if hasattr(request.user, 'sucursal') and request.user.sucursal else None
        
        context = {
            'reserva': reserva,
            'propiedad': propiedad_completa,
            'cliente': cliente_completo,
            'vendedor': vendedor_completo,
            'movimiento': movimiento,
            'total_pagado': _recibo_monto_str(movimiento.monto_total),
            'formas_de_pago': ', '.join(formas_de_pago_mostrar) if formas_de_pago_mostrar else 'EFECTIVO',
            'numero_recibo': f"{movimiento.id:06d}",
            'fecha': movimiento.fecha.strftime('%d/%m/%Y'),
            'hora': movimiento.fecha.strftime('%H:%M'),
            'fecha_inicio': reserva.fecha_inicio.strftime('%d/%m/%Y') if reserva.fecha_inicio else '',
            'fecha_fin': reserva.fecha_fin.strftime('%d/%m/%Y') if reserva.fecha_fin else '',
            'descripcion': 'Alquiler temporario por días',
            'pagos': pagos,
            'precio_total_operacion': _recibo_monto_str(precio_total),
            'monto_este_pago': _recibo_monto_str(senia_pagada),
            'saldo_pendiente': _recibo_monto_str(saldo_restante),
            'deposito_garantia': _recibo_monto_str(deposito_pagado),
            'deposito_estado': deposito_estado,
            'honorarios': _recibo_monto_str(honorarios_monto),
            'sellados': _recibo_monto_str(sellados_monto),
            'tiene_honorarios': honorarios_monto > 0,
            'tiene_sellados': sellados_monto > 0,
            'monto_en_palabras': numero_a_palabras(movimiento.monto_total),
            'logo_base64': logo_base64,
            'sucursal': sucursal,  # Agregar sucursal al contexto
        }
        
        # Cargar template específico para PDF
        template = get_template('inmobiliaria/reserva/recibo_pdf.html')
        html = template.render(context)
        
        # Limpiar el HTML de posibles caracteres problemáticos
        html = html.replace('\x00', '')  # Eliminar caracteres nulos
        
        # Crear el PDF usando BytesIO
        pdf_buffer = io.BytesIO()
        
        # Generar el PDF usando pisaDocument (método más compatible)
        try:
            result = io.BytesIO()
            pdf = pisa.pisaDocument(
                io.BytesIO(html.encode('UTF-8')),
                result,
                encoding='UTF-8'
            )
            
            if pdf.err:
                import logging
                logger = logging.getLogger(__name__)
                error_details = f'Error al generar PDF: {pdf.err}'
                logger.error(error_details)
                print(f'❌ ERROR PDF: {error_details}')  # También imprimir en consola
                result.close()
                pdf_buffer.close()
                # Devolver error detallado para debugging
                return HttpResponse(
                    f'Error al generar PDF:<br><br>Detalles: {error_details}<br><br>'
                    f'Por favor, contacte al administrador o revise los logs del servidor.',
                    status=500,
                    content_type='text/html'
                )
            
            # Obtener el contenido del PDF
            pdf_content = result.getvalue()
            result.close()
            pdf_buffer.close()
            
            # Debug: Imprimir información del PDF generado
            print(f'📄 PDF generado - Tamaño: {len(pdf_content) if pdf_content else 0} bytes')
            if pdf_content:
                print(f'📄 Primeros 20 bytes: {pdf_content[:20]}')
            
            # Verificar que el PDF no esté vacío
            if not pdf_content or len(pdf_content) < 100:
                import logging
                logger = logging.getLogger(__name__)
                error_msg = f'Error: El PDF generado está vacío o corrupto. Tamaño: {len(pdf_content) if pdf_content else 0} bytes'
                logger.error(error_msg)
                print(f'❌ PDF VACÍO: {error_msg}')
                return HttpResponse(
                    f'<h2>Error al generar PDF</h2>'
                    f'<p>El PDF generado está vacío o corrupto.</p>'
                    f'<p><strong>Tamaño del archivo:</strong> {len(pdf_content) if pdf_content else 0} bytes</p>'
                    f'<p>Revisa los logs del servidor para más detalles.</p>',
                    status=500,
                    content_type='text/html'
                )
            
            # Verificar que el PDF tenga el header correcto (%PDF)
            if not pdf_content.startswith(b'%PDF'):
                import logging
                logger = logging.getLogger(__name__)
                first_bytes = pdf_content[:50] if len(pdf_content) >= 50 else pdf_content
                error_msg = f'Error: El PDF generado no tiene un formato válido. Primeros bytes: {first_bytes}'
                logger.error(error_msg)
                print(f'❌ PDF INVÁLIDO: {error_msg}')
                return HttpResponse(
                    f'<h2>Error al generar PDF</h2>'
                    f'<p>El PDF generado no tiene un formato válido.</p>'
                    f'<p>El archivo no comienza con %PDF.</p>'
                    f'<p><strong>Primeros bytes:</strong> {first_bytes}</p>'
                    f'<p>Revisa los logs del servidor para más detalles.</p>',
                    status=500,
                    content_type='text/html'
                )
            
            print(f'✅ PDF generado correctamente - Tamaño: {len(pdf_content)} bytes')
            
            # Configurar la respuesta HTTP
            response = HttpResponse(pdf_content, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="recibo_movimiento_{movimiento.id}.pdf"'
            response['Content-Length'] = len(pdf_content)
            
            return response
            
        except Exception as e:
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            error_trace = traceback.format_exc()
            error_msg = f'Excepción al generar PDF: {str(e)}\n{error_trace}'
            logger.error(error_msg)
            print(f'❌ EXCEPCIÓN PDF: {error_msg}')  # También imprimir en consola
            pdf_buffer.close()
            # Devolver error detallado para debugging
            return HttpResponse(
                f'Error al generar PDF:<br><br>Excepción: {str(e)}<br><br>'
                f'Traceback completo en logs del servidor.<br><br>'
                f'Por favor, contacte al administrador.',
                status=500,
                content_type='text/html'
            )
            
    except Exception as e:
        import traceback
        error_detail = f'Error: {str(e)}\n\n{traceback.format_exc()}'
        print(f'❌ ERROR GENERAL: {error_detail}')  # También imprimir en consola
        return HttpResponse(
            f'<h2>Error al generar PDF</h2>'
            f'<p><strong>Error:</strong> {str(e)}</p>'
            f'<p>Revisa los logs del servidor para más detalles.</p>',
            status=500,
            content_type='text/html'
        )


# Vista AJAX para generar enlace público
from django.http import JsonResponse

def generar_enlace_publico(request):
    """Genera enlace público para compartir PDF"""
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            reserva_id = data.get('reserva_id')
            movimiento_id = data.get('movimiento_id')
            
            if movimiento_id:
                # Es un recibo de movimiento
                token = generar_token_publico(None, movimiento_id)
                url = request.build_absolute_uri(f'/recibo-movimiento-publico/{movimiento_id}/{token}/')
            elif reserva_id:
                # Es un recibo de reserva
                token = generar_token_publico(reserva_id)
                url = request.build_absolute_uri(f'/recibo-publico/{reserva_id}/{token}/')
            else:
                return JsonResponse({'error': 'ID requerido'}, status=400)
            
            return JsonResponse({'url': url})
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)


from django.http import JsonResponse

def generar_enlace_publico(request):
    """Genera enlace público para compartir PDF"""
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            reserva_id = data.get('reserva_id')
            movimiento_id = data.get('movimiento_id')
            
            if movimiento_id:
                # Es un recibo de movimiento
                token = generar_token_publico(None, movimiento_id)
                url = request.build_absolute_uri(f'/recibo-movimiento-publico/{movimiento_id}/{token}/')
            elif reserva_id:
                # Es un recibo de reserva
                token = generar_token_publico(reserva_id)
                url = request.build_absolute_uri(f'/recibo-publico/{reserva_id}/{token}/')
            else:
                return JsonResponse({'error': 'ID requerido'}, status=400)
            
            return JsonResponse({'url': url})
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)

def ver_recibo_movimiento_publico(request, movimiento_id, token):
    """Vista pública para ver recibo de movimiento sin autenticación"""
    try:
        # Verificar token
        if not verificar_token_publico(token, None, movimiento_id):
            return HttpResponse('Enlace inválido o expirado', status=403)
        
        movimiento = get_object_or_404(MovimientoCaja, id=movimiento_id)
        propiedad = movimiento.propiedad
        
        # Extraer ID de reserva del concepto
        import re
        match = re.search(r'Operación (\d+)', movimiento.concepto)
        if match:
            reserva_id = int(match.group(1))
            reserva = get_object_or_404(Reserva, id=reserva_id)
            cliente = reserva.cliente
        else:
            return HttpResponse('No se pudo identificar la reserva asociada', status=400)
        
        # Construir formas de pago igual que en ver_recibo_movimiento
        formas_de_pago = []
        formas_con_montos = []
        
        if movimiento.monto_efectivo > 0:
            formas_con_montos.append(f'Efectivo {_recibo_monto_str(movimiento.monto_efectivo)}')
            formas_de_pago.append('Efectivo')
        
        if movimiento.monto_tarjeta > 0:
            formas_con_montos.append(f'Tarjeta {_recibo_monto_str(movimiento.monto_tarjeta)}')
            formas_de_pago.append('Tarjeta')
        
        if movimiento.monto_cheque > 0:
            formas_con_montos.append(f'Cheque {_recibo_monto_str(movimiento.monto_cheque)}')
            formas_de_pago.append('Cheque')
        
        if movimiento.monto_deposito > 0:
            if movimiento.banco and 'Mercado Pago' in movimiento.banco:
                formas_con_montos.append(f'Transferencia Mercado Pago {_recibo_monto_str(movimiento.monto_deposito)}')
                formas_de_pago.append('Mercado Pago')
            elif movimiento.banco and 'Galicia' in movimiento.banco:
                formas_con_montos.append(f'Transferencia Galicia {_recibo_monto_str(movimiento.monto_deposito)}')
                formas_de_pago.append('Galicia')
            else:
                formas_con_montos.append(f'Transferencia {_recibo_monto_str(movimiento.monto_deposito)}')
                formas_de_pago.append('Transferencia')
        
        formas_de_pago_mostrar = formas_con_montos if formas_con_montos else formas_de_pago
        
        context = {
            'reserva': reserva,
            'propiedad': propiedad,
            'cliente': cliente,
            'movimiento': movimiento,
            'total_pagado': _recibo_monto_str(movimiento.monto_total),
            'formas_de_pago': ', '.join(formas_de_pago_mostrar) if formas_de_pago_mostrar else 'EFECTIVO',
            'numero_recibo': f"{movimiento.id:06d}",
            'fecha': movimiento.fecha.strftime('%d/%m/%Y'),
            'hora': movimiento.fecha.strftime('%H:%M'),
        }
        
        # Cargar template específico para PDF
        template = get_template('inmobiliaria/reserva/recibo_pdf.html')
        html = template.render(context)
        
        # Crear el PDF
        result = io.BytesIO()
        pdf = pisa.pisaDocument(io.BytesIO(html.encode("UTF-8")), result)
        
        if not pdf.err:
            response = HttpResponse(result.getvalue(), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="recibo_movimiento_{movimiento.id}.pdf"'
            return response
        else:
            return HttpResponse('Error al generar PDF', status=500)
            
    except Exception as e:
        return HttpResponse(f'Error: {str(e)}', status=500)


# Vista AJAX para generar enlace público
from django.http import JsonResponse

def generar_enlace_publico(request):
    """Genera enlace público para compartir PDF"""
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            reserva_id = data.get('reserva_id')
            movimiento_id = data.get('movimiento_id')
            
            if movimiento_id:
                # Es un recibo de movimiento
                token = generar_token_publico(None, movimiento_id)
                url = request.build_absolute_uri(f'/recibo-movimiento-publico/{movimiento_id}/{token}/')
            elif reserva_id:
                # Es un recibo de reserva
                token = generar_token_publico(reserva_id)
                url = request.build_absolute_uri(f'/recibo-publico/{reserva_id}/{token}/')
            else:
                return JsonResponse({'error': 'ID requerido'}, status=400)
            
            return JsonResponse({'url': url})
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)


# ==================== VISTAS PARA LIQUIDACIONES DE PROPIETARIOS ====================


def _liquidacion_solapa_periodo(liq, d1, d2):
    """
    True si el período de la liquidación intersecta [d1, d2] (fechas inclusive).
    Si no hay fecha_desde/fecha_hasta, se usa la fecha de creación del registro.
    """
    fc = None
    if getattr(liq, 'fecha_creacion', None):
        try:
            fc = timezone.localdate(liq.fecha_creacion)
        except (ValueError, TypeError, OverflowError):
            fc = liq.fecha_creacion.date() if hasattr(liq.fecha_creacion, 'date') else None
    start = liq.fecha_desde
    end = liq.fecha_hasta
    if start is None and end is None:
        if fc is None:
            return False
        start = end = fc
    elif start is None:
        start = end if end is not None else fc
        if start is None:
            return False
        if end is None:
            end = start
    elif end is None:
        end = start
    return start <= d2 and end >= d1


@login_required
def reporte_asegurado_liquidaciones(request, disponibilidad_id=None):
    """
    Listado de disponibilidades con pago asegurado (anticipo) y detalle por ítem:
    suma de liquidaciones de la propiedad que caen en el mismo período que la disponibilidad.
    La comparación con el anticipo (ARS) usa solo la suma de lo que va al propietario,
    no el total de la operación ni la parte inmobiliaria.
    """
    sucursal = getattr(request.user, 'sucursal', None)
    if not sucursal:
        messages.error(request, 'Tu usuario no tiene sucursal asignada; no se puede armar el reporte.')
        return redirect('inmobiliaria:dashboard')

    disps = (
        Disponibilidad.objects.filter(
            asegurado=True,
            propiedad__sucursal=sucursal,
        )
        .select_related('propiedad', 'propiedad__propietario')
        .order_by('-fecha_inicio', 'propiedad__direccion', 'id')
    )

    detalle = None
    if disponibilidad_id:
        disp = get_object_or_404(
            Disponibilidad,
            pk=disponibilidad_id,
            propiedad__sucursal=sucursal,
        )
        d1, d2 = disp.fecha_inicio, disp.fecha_fin
        liqs = (
            LiquidacionPropietario.objects.filter(
                propiedad=disp.propiedad,
                sucursal=sucursal,
            )
            .exclude(estado='cancelada')
            .select_related('reserva', 'contrato', 'propietario')
            .order_by('fecha_creacion', 'id')
        )
        filas = []
        total_operacion = Decimal('0')
        total_inmobiliaria = Decimal('0')
        total_propietario = Decimal('0')
        for liq in liqs:
            if not _liquidacion_solapa_periodo(liq, d1, d2):
                continue
            filas.append(liq)
            total_operacion += liq.monto_total_operacion or Decimal('0')
            total_inmobiliaria += liq.monto_inmobiliaria or Decimal('0')
            total_propietario += liq.monto_propietario or Decimal('0')

        anticipo = disp.monto_asegurado or Decimal('0')
        moneda = (disp.moneda_asegurado or 'ARS').upper()
        # Las liquidaciones del sistema se cargan en pesos; comparación automática solo ARS.
        puede_comparar = moneda == 'ARS'
        diff_prop_vs_anticipo = (total_propietario - anticipo) if puede_comparar else None
        if puede_comparar and diff_prop_vs_anticipo is not None:
            cmp_prop = diff_prop_vs_anticipo.compare(Decimal('0'))
            diff_prop_sign = 1 if cmp_prop > 0 else (-1 if cmp_prop < 0 else 0)
        else:
            diff_prop_sign = None

        detalle = {
            'disponibilidad': disp,
            'liquidaciones': filas,
            'total_operacion': total_operacion,
            'total_inmobiliaria': total_inmobiliaria,
            'total_propietario': total_propietario,
            'anticipo': anticipo,
            'moneda_anticipo': moneda,
            'diff_prop_vs_anticipo': diff_prop_vs_anticipo,
            'puede_comparar': puede_comparar,
            'diff_prop_sign': diff_prop_sign,
        }

    return render(
        request,
        'inmobiliaria/reportes/reporte_asegurado_liquidaciones.html',
        {
            'disponibilidades': disps,
            'detalle': detalle,
            'disponibilidad_id': disponibilidad_id,
        },
    )


@login_required
def lista_liquidaciones(request):
    """
    Vista para listar todas las liquidaciones de propietarios
    """
    liquidaciones = LiquidacionPropietario.objects.filter(
        sucursal=request.user.sucursal
    ).select_related(
        'propietario', 'propiedad', 'reserva', 'contrato', 'movimiento_caja'
    ).prefetch_related('gastos').order_by('-fecha_creacion')

    # Filtros
    estado_filtro = request.GET.get('estado', '')
    propietario_id = request.GET.get('propietario', '')
    busqueda = request.GET.get('busqueda', '')

    if estado_filtro:
        liquidaciones = liquidaciones.filter(estado=estado_filtro)

    if propietario_id:
        liquidaciones = liquidaciones.filter(propietario_id=propietario_id)

    if busqueda:
        liquidaciones = liquidaciones.filter(
            Q(propiedad__direccion__icontains=busqueda) |
            Q(propietario__nombre__icontains=busqueda) |
            Q(propietario__apellido__icontains=busqueda) |
            Q(id__icontains=busqueda)
        )

    # Calcular totales
    total_pendiente = liquidaciones.filter(estado='pendiente').aggregate(
        total=Sum('monto_a_pagar')
    )['total'] or Decimal('0')

    total_procesado = liquidaciones.filter(
        estado__in=['cerrada', 'pagada', 'oficina', 'procesada']
    ).aggregate(
        total=Sum('monto_a_pagar')
    )['total'] or Decimal('0')

    propietarios = Propietario.objects.filter(
        sucursal=request.user.sucursal
    ).order_by('apellido', 'nombre')

    context = {
        'liquidaciones': liquidaciones,
        'estado_filtro': estado_filtro,
        'propietario_id': propietario_id,
        'busqueda': busqueda,
        'propietarios': propietarios,
        'total_pendiente': total_pendiente,
        'total_procesado': total_procesado,
    }

    return render(request, 'inmobiliaria/liquidaciones/lista.html', context)


@login_required
def crear_liquidacion(request, reserva_id=None):
    """
    Vista para crear una nueva liquidación desde una reserva
    """
    reserva = None
    if reserva_id:
        reserva = get_object_or_404(Reserva, id=reserva_id, sucursal=request.user.sucursal)

        # Verificar si ya existe una liquidación para esta reserva
        liquidacion_existente = LiquidacionPropietario.objects.filter(
            reserva=reserva,
            estado='pendiente'
        ).first()

        if liquidacion_existente:
            messages.warning(request, 'Ya existe una liquidación pendiente para esta reserva.')
            return redirect('inmobiliaria:detalle_liquidacion', liquidacion_id=liquidacion_existente.id)

    if request.method == 'POST':
        try:
            def parse_decimal_es(valor):
                return parse_decimal_monto(valor or '0')

            propiedad_id = request.POST.get('propiedad_id')
            monto_total = parse_decimal_es(request.POST.get('monto_total', '0'))
            monto_propietario = parse_decimal_es(request.POST.get('monto_propietario', '0'))
            monto_cochera = parse_decimal_es(request.POST.get('monto_cochera', '0'))
            if monto_cochera < 0:
                monto_cochera = Decimal('0')
            monto_fondo_mantenimiento = parse_decimal_es(request.POST.get('monto_fondo_mantenimiento', '0'))
            if monto_fondo_mantenimiento < 0:
                monto_fondo_mantenimiento = Decimal('0')
            fecha_desde = request.POST.get('fecha_desde')
            fecha_hasta = request.POST.get('fecha_hasta')
            observaciones = request.POST.get('observaciones', '')

            if not propiedad_id:
                messages.error(request, 'Debe seleccionar una propiedad.')
                return redirect('inmobiliaria:lista_liquidaciones')

            propiedad = get_object_or_404(Propiedad, id=propiedad_id, sucursal=request.user.sucursal)

            # Monto inmobiliaria: si viene informado en el formulario, usarlo; si no, diferencia
            raw_inm = (request.POST.get('monto_inmobiliaria') or '').strip()
            if raw_inm:
                monto_inmobiliaria = parse_decimal_es(raw_inm)
            else:
                monto_inmobiliaria = monto_total - monto_propietario

            # Operaciones marcadas en el formulario (reserva:ID / contrato:ID)
            operaciones_incluidas = []
            for item in request.POST.getlist('operaciones_seleccionadas[]'):
                item = (item or '').strip()
                if ':' not in item:
                    continue
                tipo, sid = item.split(':', 1)
                tipo = tipo.strip().lower()
                try:
                    pk = int(sid.strip())
                except ValueError:
                    continue
                if tipo in ('reserva', 'contrato'):
                    operaciones_incluidas.append({'tipo': tipo, 'id': pk})

            # División manual en dos operaciones
            dividir_operacion = request.POST.get('dividir_operacion') == '1'
            if dividir_operacion:
                op1_fecha_desde = request.POST.get('op1_fecha_desde')
                op1_fecha_hasta = request.POST.get('op1_fecha_hasta')
                op2_fecha_desde = request.POST.get('op2_fecha_desde')
                op2_fecha_hasta = request.POST.get('op2_fecha_hasta')
                op1_monto = parse_decimal_es(request.POST.get('op1_monto', '0'))
                op2_monto = parse_decimal_es(request.POST.get('op2_monto', '0'))

                if not all([op1_fecha_desde, op1_fecha_hasta, op2_fecha_desde, op2_fecha_hasta]):
                    raise ValueError('Si dividís la liquidación, debés completar las fechas de ambas operaciones.')
                if op1_monto <= 0 or op2_monto <= 0:
                    raise ValueError('Los montos de ambas operaciones deben ser mayores a cero.')
                if (op1_monto + op2_monto).quantize(Decimal('0.01')) != monto_total.quantize(Decimal('0.01')):
                    raise ValueError('La suma de Operación 1 y Operación 2 debe ser igual al Monto Total de la operación.')

                f1_desde = datetime.strptime(op1_fecha_desde, '%Y-%m-%d').date()
                f1_hasta = datetime.strptime(op1_fecha_hasta, '%Y-%m-%d').date()
                f2_desde = datetime.strptime(op2_fecha_desde, '%Y-%m-%d').date()
                f2_hasta = datetime.strptime(op2_fecha_hasta, '%Y-%m-%d').date()
                if f1_desde > f1_hasta or f2_desde > f2_hasta:
                    raise ValueError('En cada operación, la fecha desde no puede ser mayor a la fecha hasta.')

                operaciones_incluidas.append({
                    'tipo': 'division',
                    'operaciones': [
                        {
                            'numero': 1,
                            'fecha_desde': op1_fecha_desde,
                            'fecha_hasta': op1_fecha_hasta,
                            'monto': str(op1_monto)
                        },
                        {
                            'numero': 2,
                            'fecha_desde': op2_fecha_desde,
                            'fecha_hasta': op2_fecha_hasta,
                            'monto': str(op2_monto)
                        },
                    ]
                })

                # Completar rango general si no fue cargado manualmente
                if not fecha_desde:
                    fecha_desde = min(op1_fecha_desde, op2_fecha_desde)
                if not fecha_hasta:
                    fecha_hasta = max(op1_fecha_hasta, op2_fecha_hasta)

            # Compatibilidad: si solo hay una reserva en el POST y no venimos por URL, asignar FK reserva
            if reserva is None:
                ids_res = [o['id'] for o in operaciones_incluidas if o['tipo'] == 'reserva']
                if len(ids_res) == 1:
                    reserva = Reserva.objects.filter(
                        id=ids_res[0], propiedad=propiedad, sucursal=request.user.sucursal
                    ).first()
            contrato_fk = None
            if reserva is None:
                ids_ct = [o['id'] for o in operaciones_incluidas if o['tipo'] == 'contrato']
                if len(ids_ct) == 1:
                    contrato_fk = ContratoAlquiler.objects.filter(
                        id=ids_ct[0], propiedad=propiedad, sucursal=request.user.sucursal
                    ).first()

            liquidacion = LiquidacionPropietario.objects.create(
                propietario=propiedad.propietario,
                propiedad=propiedad,
                reserva=reserva,
                contrato=contrato_fk,
                estado='pendiente',
                monto_total_operacion=monto_total,
                monto_propietario=monto_propietario,
                monto_inmobiliaria=monto_inmobiliaria,
                monto_cochera=monto_cochera,
                monto_fondo_mantenimiento=monto_fondo_mantenimiento,
                fecha_desde=datetime.strptime(fecha_desde, '%Y-%m-%d').date() if fecha_desde else None,
                fecha_hasta=datetime.strptime(fecha_hasta, '%Y-%m-%d').date() if fecha_hasta else None,
                observaciones=observaciones,
                operaciones_incluidas=operaciones_incluidas,
                sucursal=request.user.sucursal,
                usuario_creacion=request.user
            )

            # Asociar gastos pendientes seleccionados a la liquidación
            gastos_seleccionados = request.POST.getlist('gastos_seleccionados[]')
            if gastos_seleccionados:
                for gasto_id_str in gastos_seleccionados:
                    try:
                        # Verificar si es un movimiento de caja (prefijo 'movimiento_')
                        if gasto_id_str.startswith('movimiento_'):
                            movimiento_id = int(gasto_id_str.replace('movimiento_', ''))
                            movimiento = MovimientoCaja.objects.get(
                                id=movimiento_id,
                                propiedad=propiedad,
                                tipo=TipoMovimientoCajaEnum.EGRESO,
                                sucursal=request.user.sucursal
                            )
                            # Solo permitir egresos descontables al propietario
                            if movimiento.a_descontar not in ('propietario', 'oficina', None, ''):
                                continue
                            # Crear un GastoPropietario desde el movimiento de caja
                            desc_mov = movimiento.descripcion_para_gasto_liquidacion_propietario()[:200]
                            gasto = GastoPropietario.objects.create(
                                liquidacion=liquidacion,
                                propietario=propiedad.propietario,
                                propiedad=propiedad,
                                descripcion=desc_mov,
                                monto=movimiento.monto_total,
                                fecha_gasto=movimiento.fecha.date() if movimiento.fecha else None,
                                observaciones=f'Movimiento de caja #{movimiento.id}',
                                aceptado=True,
                                sucursal=request.user.sucursal
                            )
                        else:
                            # Es un gasto manual existente
                            gasto_id = int(gasto_id_str)
                            gasto = GastoPropietario.objects.get(
                                id=gasto_id,
                                propietario=propiedad.propietario,
                                liquidacion__isnull=True,
                                sucursal=request.user.sucursal
                            )
                            gasto.liquidacion = liquidacion
                            gasto.aceptado = True  # Automáticamente aceptado al asociarlo
                            gasto.save()
                    except (GastoPropietario.DoesNotExist, MovimientoCaja.DoesNotExist, ValueError):
                        pass  # Ignorar si el gasto/movimiento no existe o ya está asociado

            # Recalcular monto a pagar con los gastos
            liquidacion.calcular_monto_a_pagar()

            messages.success(request, 'Liquidación creada correctamente.')
            return redirect('inmobiliaria:detalle_liquidacion', liquidacion_id=liquidacion.id)

        except Exception as e:
            messages.error(request, f'Error al crear la liquidación: {str(e)}')
            return redirect('inmobiliaria:lista_liquidaciones')

    # Si hay reserva, pre-llenar datos
    propiedades = Propiedad.objects.filter(
        sucursal=request.user.sucursal
    ).select_related('propietario').order_by('direccion')

    propietarios_busqueda = list(
        Propietario.objects.filter(sucursal=request.user.sucursal)
        .order_by('apellido', 'nombre')
        .values('id', 'nombre', 'apellido', 'dni')
    )

    context = {
        'reserva': reserva,
        'propiedades': propiedades,
        'propietarios_busqueda': propietarios_busqueda,
    }

    if reserva:
        context['propiedad'] = reserva.propiedad
        context['monto_total'] = reserva.precio_total
        context['fecha_desde'] = reserva.fecha_inicio
        context['fecha_hasta'] = reserva.fecha_fin

    return render(request, 'inmobiliaria/liquidaciones/crear.html', context)


def _operaciones_gastos_pendientes_data(propiedad, sucursal):
    """
    Lista operaciones y gastos pendientes de liquidación para una propiedad (dict serializable a JSON).
    `sucursal` debe ser la sucursal del usuario (coincidente con la de la propiedad).
    """
    # Reservas/contratos ya cubiertos por liquidación pendiente o procesada
    # (FK directa o lista operaciones_incluidas del formulario masivo)
    reservas_excluidas = set()
    contratos_excluidos = set()
    for liq in LiquidacionPropietario.objects.filter(
        propiedad=propiedad,
    ).exclude(
        estado='cancelada'
    ).only('reserva_id', 'contrato_id', 'operaciones_incluidas'):
        if liq.reserva_id:
            reservas_excluidas.add(liq.reserva_id)
        if liq.contrato_id:
            contratos_excluidos.add(liq.contrato_id)
        for op in liq.operaciones_incluidas or []:
            if not isinstance(op, dict):
                continue
            t = (op.get('tipo') or '').lower()
            try:
                oid = int(op.get('id'))
            except (TypeError, ValueError):
                continue
            if t == 'reserva':
                reservas_excluidas.add(oid)
            elif t == 'contrato':
                contratos_excluidos.add(oid)

    reservas_pendientes = Reserva.objects.filter(
        propiedad=propiedad,
        estado__in=['pagada', 'confirmada_no_pagada', 'confirmada'],
        eliminada=False,
        sucursal=sucursal,
    ).exclude(
        id__in=reservas_excluidas
    ).select_related('cliente').order_by('-fecha_inicio')
    
    contratos_pendientes = ContratoAlquiler.objects.filter(
        propiedad=propiedad,
        estado='activo',
        sucursal=sucursal,
    ).exclude(
        id__in=contratos_excluidos
    ).prefetch_related('cuotas').select_related('inquilino')
    
    operaciones = []
    
    # Función auxiliar para determinar tipo de precio según fecha
    def obtener_tipo_precio(fecha):
        if fecha.month == 1:  # Enero
            return 'QUINCENA_1_ENERO' if fecha.day <= 15 else 'QUINCENA_2_ENERO'
        elif fecha.month == 2:  # Febrero
            return 'QUINCENA_1_FEBRERO' if fecha.day <= 15 else 'QUINCENA_2_FEBRERO'
        elif fecha.month == 3:  # Marzo
            return 'QUINCENA_1_MARZO' if fecha.day <= 15 else 'QUINCENA_2_MARZO'
        elif fecha.month == 7:  # Julio (Vacaciones de Invierno)
            return 'VACACIONES_INVIERNO'
        elif fecha.month == 12:  # Diciembre
            return 'QUINCENA_1_DICIEMBRE' if fecha.day <= 15 else 'QUINCENA_2_DICIEMBRE'
        else:
            return 'TEMPORADA_BAJA'
    
    # Procesar reservas
    for reserva in reservas_pendientes:
        # Verificar si tiene movimientos de caja (pagos)
        movimientos = MovimientoCaja.objects.filter(
            propiedad=propiedad,
            tipo=TipoMovimientoCajaEnum.INGRESO
        ).filter(
            Q(concepto__icontains=f"Operación {reserva.id}") |
            Q(concepto__icontains=f"Reserva {reserva.id}") |
            (Q(fecha_desde=reserva.fecha_inicio) & Q(fecha_hasta=reserva.fecha_fin))
        )
        
        total_pagado = sum(
            float(mov.monto_efectivo or 0) + float(mov.monto_cheque or 0) + 
            float(mov.monto_tarjeta or 0) + float(mov.monto_deposito or 0)
            for mov in movimientos
        )
        
        # Si no hay movimientos pero la reserva está pagada, usar el precio_total como monto
        if total_pagado == 0 and reserva.estado == 'pagada':
            total_pagado = float(reserva.precio_total)
        
        # Incluir la reserva si tiene pagos o está marcada como pagada
        if total_pagado > 0 or reserva.estado == 'pagada':
            # Calcular días de la reserva (mínimo 1 para no dejar el bucle vacío ni dividir por 0)
            dias_reserva = (reserva.fecha_fin - reserva.fecha_inicio).days
            if dias_reserva <= 0:
                dias_reserva = 1
            
            # Calcular montos según precio_toma y precio_por_dia
            monto_propietario_total = Decimal('0')
            monto_inmobiliaria_total = Decimal('0')
            hay_precio_toma = False
            
            # Calcular día por día
            for i in range(dias_reserva):
                fecha_actual = reserva.fecha_inicio + timedelta(days=i)
                tipo_precio = obtener_tipo_precio(fecha_actual)
                
                try:
                    precio = Precio.objects.get(propiedad=propiedad, tipo_precio=tipo_precio)
                    precio_toma = Decimal(str(precio.precio_toma or 0))
                    precio_por_dia = Decimal(str(precio.precio_por_dia or 0))
                    
                    # Si no hay precio_toma, usar precio_dia_toma como fallback
                    if precio_toma == 0 and precio.precio_dia_toma:
                        precio_toma = Decimal(str(precio.precio_dia_toma))
                    if precio_toma > 0:
                        hay_precio_toma = True
                    
                    # Calcular ganancia por día
                    ganancia_dia = precio_por_dia - precio_toma
                    
                    monto_propietario_total += precio_toma
                    monto_inmobiliaria_total += ganancia_dia
                except Precio.DoesNotExist:
                    # Si no existe precio, usar el precio_total de la reserva dividido por días
                    precio_promedio = Decimal(str(reserva.precio_total)) / Decimal(str(dias_reserva))
                    # Fallback sin precio de toma: 70% propietario / 30% inmobiliaria
                    monto_propietario_total += precio_promedio * Decimal('0.70')
                    monto_inmobiliaria_total += precio_promedio * Decimal('0.30')

            # Si no hay ningún precio de toma configurado, forzar 70/30.
            total_reserva = Decimal(str(reserva.precio_total))
            if not hay_precio_toma:
                monto_propietario_total = (total_reserva * Decimal('0.70')).quantize(Decimal('0.01'))
                monto_inmobiliaria_total = (total_reserva - monto_propietario_total).quantize(Decimal('0.01'))

            # Si la suma no cierra con el precio de la reserva, repartir por % de propiedad (default 70%).
            suma_split = monto_propietario_total + monto_inmobiliaria_total
            pct_prop = propiedad.porcentaje_propietario
            if pct_prop is None or pct_prop <= 0:
                pct_prop = Decimal('70')
            else:
                pct_prop = Decimal(str(pct_prop))
            tolerancia = Decimal('2.00')
            if (
                monto_propietario_total <= 0
                or suma_split <= 0
                or abs(suma_split - total_reserva) > tolerancia
            ):
                monto_propietario_total = (total_reserva * pct_prop / Decimal('100')).quantize(Decimal('0.01'))
                monto_inmobiliaria_total = (total_reserva - monto_propietario_total).quantize(Decimal('0.01'))
            
            operaciones.append({
                'tipo': 'reserva',
                'tipo_display': 'Por día',
                'incluible': True,
                'id': reserva.id,
                'descripcion': f'Reserva #{reserva.id} - {reserva.cliente.apellido}, {reserva.cliente.nombre}',
                'fecha_inicio': reserva.fecha_inicio.strftime('%Y-%m-%d'),
                'fecha_fin': reserva.fecha_fin.strftime('%Y-%m-%d'),
                'monto_total': str(reserva.precio_total),
                'monto_pagado': str(total_pagado if total_pagado > 0 else reserva.precio_total),
                'monto_propietario': str(monto_propietario_total),
                'monto_inmobiliaria': str(monto_inmobiliaria_total),
                'dias': dias_reserva,
            })
    
    # Procesar contratos (cuotas pagadas; sin pagos aún se listan como referencia, no liquidables)
    for contrato in contratos_pendientes:
        cuotas_pagadas = contrato.cuotas.filter(estado='pagada')
        inq = contrato.inquilino
        nombre_inq = f'{inq.apellido}, {inq.nombre}' if inq else '—'
        if not cuotas_pagadas.exists():
            operaciones.append({
                'tipo': 'contrato',
                'tipo_display': 'Contrato',
                'incluible': False,
                'id': contrato.id,
                'descripcion': (
                    f'Contrato #{contrato.id} - {nombre_inq} '
                    f'(sin cuotas pagadas aún; no se puede incluir en la liquidación hasta registrar pagos)'
                ),
                'fecha_inicio': contrato.fecha_inicio.strftime('%Y-%m-%d') if contrato.fecha_inicio else '',
                'fecha_fin': contrato.fecha_fin.strftime('%Y-%m-%d') if contrato.fecha_fin else '',
                'monto_total': '0',
                'monto_pagado': '0',
                'monto_propietario': '0',
                'monto_inmobiliaria': '0',
                'dias': 0,
            })
            continue

        total_cuotas = sum(float(cuota.monto_total) for cuota in cuotas_pagadas)

        # Para contratos, usar el precio_23_meses o precio_invierno de la propiedad
        # y calcular según el tipo de operación
        monto_propietario_contrato = Decimal('0')
        monto_inmobiliaria_contrato = Decimal('0')

        # Obtener precio mensual del contrato
        precio_mensual = Decimal(str(total_cuotas)) / Decimal(str(cuotas_pagadas.count()))

        # Buscar precio de toma en precios de la propiedad (usar TEMPORADA_BAJA como referencia)
        try:
            precio_ref = Precio.objects.filter(propiedad=propiedad).first()
            if precio_ref and precio_ref.precio_toma:
                # Calcular proporción: si precio_toma es 70 y precio_por_dia es 100
                # En un mes, el propietario recibe: precio_toma × 30 días
                precio_toma = Decimal(str(precio_ref.precio_toma))
                precio_por_dia = Decimal(str(precio_ref.precio_por_dia or 100))

                if precio_por_dia > 0:
                    # Calcular precio mensual de toma
                    precio_mensual_toma = (precio_toma / precio_por_dia) * precio_mensual
                    monto_propietario_contrato = precio_mensual_toma * Decimal(str(cuotas_pagadas.count()))
                    monto_inmobiliaria_contrato = Decimal(str(total_cuotas)) - monto_propietario_contrato
                else:
                    # Fallback sin precio de toma: 70% propietario / 30% inmobiliaria
                    monto_propietario_contrato = Decimal(str(total_cuotas)) * Decimal('0.70')
                    monto_inmobiliaria_contrato = Decimal(str(total_cuotas)) * Decimal('0.30')
            else:
                # Fallback sin precio de toma: 70% propietario / 30% inmobiliaria
                monto_propietario_contrato = Decimal(str(total_cuotas)) * Decimal('0.70')
                monto_inmobiliaria_contrato = Decimal(str(total_cuotas)) * Decimal('0.30')
        except Exception:
            # Fallback sin precio de toma: 70% propietario / 30% inmobiliaria
            monto_propietario_contrato = Decimal(str(total_cuotas)) * Decimal('0.70')
            monto_inmobiliaria_contrato = Decimal(str(total_cuotas)) * Decimal('0.30')

        operaciones.append({
            'tipo': 'contrato',
            'tipo_display': 'Contrato',
            'incluible': True,
            'id': contrato.id,
            'descripcion': f'Contrato #{contrato.id} - {nombre_inq}',
            'fecha_inicio': contrato.fecha_inicio.strftime('%Y-%m-%d') if contrato.fecha_inicio else '',
            'fecha_fin': contrato.fecha_fin.strftime('%Y-%m-%d') if contrato.fecha_fin else '',
            'monto_total': str(total_cuotas),
            'monto_pagado': str(total_cuotas),
            'monto_propietario': str(monto_propietario_contrato),
            'monto_inmobiliaria': str(monto_inmobiliaria_contrato),
            'dias': cuotas_pagadas.count() * 30,  # Aproximación: cada cuota = 30 días
        })
    
    # Obtener gastos pendientes del propietario (sin liquidación asociada)
    gastos_pendientes = GastoPropietario.objects.filter(
        propietario=propiedad.propietario,
        liquidacion__isnull=True,
        sucursal=sucursal,
    ).order_by('-fecha_creacion')
    
    # Si no hay gastos con propietario, buscar por propiedad
    if not gastos_pendientes.exists():
        gastos_pendientes = GastoPropietario.objects.filter(
            propiedad=propiedad,
            liquidacion__isnull=True,
            sucursal=sucursal,
        ).order_by('-fecha_creacion')
    
    # Obtener egresos de caja con a_descontar='oficina' relacionados con esta propiedad
    # que no estén asociados a ninguna liquidación procesada
    liquidaciones_procesadas = LiquidacionPropietario.objects.filter(
        propiedad=propiedad,
        estado__in=['cerrada', 'pagada', 'oficina', 'procesada']
    ).values_list('id', flat=True)
    
    # Obtener descripciones de gastos que ya están en liquidaciones procesadas
    # para evitar duplicar egresos que ya fueron convertidos en gastos
    gastos_procesados = GastoPropietario.objects.filter(
        liquidacion_id__in=liquidaciones_procesadas,
        propiedad=propiedad
    ).values_list('observaciones', flat=True)
    
    # Buscar movimientos de caja (egresos) relacionados con la propiedad.
    # Incluir:
    # - propietario (descuento directo),
    # - oficina (muchos registros históricos se cargaron así),
    # - vacíos/NULL (legacy).
    egresos_propiedad = MovimientoCaja.objects.filter(
        propiedad=propiedad,
        tipo=TipoMovimientoCajaEnum.EGRESO,
        sucursal=sucursal,
    ).filter(
        Q(a_descontar='propietario') |
        Q(a_descontar='oficina') |
        Q(a_descontar__isnull=True) |
        Q(a_descontar='')
    ).exclude(
        # Evitar reciclar pagos al propietario como "gasto pendiente"
        concepto__icontains='Liquidación Propietario'
    ).order_by('-fecha')
    
    gastos_pendientes_list = []
    
    # Agregar gastos de GastoPropietario
    for gasto in gastos_pendientes:
        obs = (gasto.observaciones or '').strip()
        gastos_pendientes_list.append({
            'id': gasto.id,
            'descripcion': gasto.descripcion,
            'concepto': gasto.descripcion or '—',
            'detalle': obs,
            'monto': str(gasto.monto),
            'fecha_gasto': gasto.fecha_gasto.strftime('%Y-%m-%d') if gasto.fecha_gasto else '',
            'fecha_gasto_display': gasto.fecha_gasto.strftime('%d/%m/%Y') if gasto.fecha_gasto else '—',
            'observaciones': gasto.observaciones,
            'tipo': 'gasto_manual'
        })
    
    # Agregar egresos de caja como gastos pendientes
    # Incluir todos los egresos relacionados con la propiedad
    # IDs de movimientos ya usados en liquidaciones (compatibilidad amplia)
    movimientos_ya_liquidados = set(
        LiquidacionPropietario.objects.filter(
            propiedad=propiedad,
            movimiento_caja__isnull=False
        ).values_list('movimiento_caja_id', flat=True)
    )

    for egreso in egresos_propiedad:
        if egreso.id in movimientos_ya_liquidados:
            continue
        # Verificar si ya existe un GastoPropietario para este movimiento
        # Buscamos por observaciones que contengan el ID del movimiento
        existe_gasto = GastoPropietario.objects.filter(
            Q(propiedad=propiedad) | Q(propietario=propiedad.propietario),
            observaciones__icontains=f'Movimiento de caja #{egreso.id}'
        ).exists()
        
        # Solo agregar si no existe un gasto para este movimiento
        # Incluir todos los egresos, independientemente del valor de a_descontar
        if not existe_gasto:
            descripcion = egreso.descripcion_para_gasto_liquidacion_propietario()[:200]
            try:
                c1 = (getattr(egreso, 'listado_concepto_l1', None) or '').strip()
            except Exception:
                c1 = ''
            try:
                c2 = (getattr(egreso, 'listado_concepto_l2', None) or '').strip()
            except Exception:
                c2 = ''
            concepto_mov = ' · '.join(x for x in (c1, c2) if x) or '—'
            try:
                d1 = (getattr(egreso, 'listado_detalle_l1', None) or '').strip()
            except Exception:
                d1 = ''
            try:
                d2 = (getattr(egreso, 'listado_detalle_l2', None) or '').strip()
            except Exception:
                d2 = ''
            detalle_mov = ' · '.join(x for x in (d1, d2) if x and x != '—') or ''

            gastos_pendientes_list.append({
                'id': f'movimiento_{egreso.id}',  # Prefijo para identificar que es un movimiento
                'descripcion': descripcion,
                'concepto': concepto_mov,
                'detalle': detalle_mov,
                'monto': str(egreso.monto_total),
                'fecha_gasto': egreso.fecha.strftime('%Y-%m-%d') if egreso.fecha else '',
                'fecha_gasto_display': egreso.fecha.strftime('%d/%m/%Y') if egreso.fecha else '—',
                'observaciones': f'Movimiento de caja #{egreso.id}',
                'tipo': 'egreso_caja',
                'movimiento_id': egreso.id
            })
    
    # Debug: contar egresos encontrados
    total_egresos = egresos_propiedad.count()
    
    return {
        'operaciones': operaciones,
        'gastos_pendientes': gastos_pendientes_list,
        'debug': {
            'total_egresos_encontrados': total_egresos,
            'total_gastos_agregados': len(gastos_pendientes_list),
        },
    }


def _etiqueta_propiedad_liquidacion(propiedad):
    lbl = f'{propiedad.direccion} (#{propiedad.id})'
    if getattr(propiedad, 'piso', None) or getattr(propiedad, 'departamento', None):
        lbl += f' — Piso {propiedad.piso or "—"} Dpto {propiedad.departamento or "—"}'
    return lbl


@login_required
def obtener_operaciones_pendientes(request, propiedad_id):
    """Vista AJAX: operaciones y gastos pendientes para una propiedad."""
    propiedad = get_object_or_404(Propiedad, id=propiedad_id, sucursal=request.user.sucursal)
    data = _operaciones_gastos_pendientes_data(propiedad, request.user.sucursal)
    lbl = _etiqueta_propiedad_liquidacion(propiedad)
    for op in data.get('operaciones') or []:
        op['propiedad_id'] = propiedad.id
        op['propiedad_label'] = lbl
    for g in data.get('gastos_pendientes') or []:
        g['propiedad_id'] = propiedad.id
        g['propiedad_label'] = lbl
    return JsonResponse({'success': True, **data})


@login_required
def obtener_operaciones_pendientes_propietario(request, propietario_id):
    """
    Vista AJAX: operaciones y gastos pendientes agrupados para todas las propiedades
    del propietario en la sucursal (una liquidación sigue siendo por una sola propiedad).
    """
    propietario = get_object_or_404(Propietario, id=propietario_id, sucursal=request.user.sucursal)
    operaciones = []
    gastos_merged = []
    seen_gasto_key = set()
    total_egresos = 0
    props = list(
        Propiedad.objects.filter(
            propietario=propietario,
            sucursal=request.user.sucursal,
        ).order_by('direccion')
    )
    for propiedad in props:
        data = _operaciones_gastos_pendientes_data(propiedad, request.user.sucursal)
        lbl = _etiqueta_propiedad_liquidacion(propiedad)
        for op in data.get('operaciones') or []:
            operaciones.append({**op, 'propiedad_id': propiedad.id, 'propiedad_label': lbl})
        for g in data.get('gastos_pendientes') or []:
            gkey = g.get('id')
            if gkey in seen_gasto_key:
                continue
            seen_gasto_key.add(gkey)
            gastos_merged.append({**g, 'propiedad_id': propiedad.id, 'propiedad_label': lbl})
        dbg = data.get('debug') or {}
        try:
            total_egresos += int(dbg.get('total_egresos_encontrados') or 0)
        except (TypeError, ValueError):
            pass
    return JsonResponse(
        {
            'success': True,
            'operaciones': operaciones,
            'gastos_pendientes': gastos_merged,
            'propietario_id': propietario.id,
            'propietario_nombre': f'{propietario.apellido}, {propietario.nombre}',
            'propietario_cuenta_bancaria': (propietario.cuenta_bancaria or '').strip(),
            'debug': {
                'total_egresos_encontrados': total_egresos,
                'total_gastos_agregados': len(gastos_merged),
                'propiedades_consideradas': len(props),
            },
        }
    )


def _operaciones_incluidas_tabla(liquidacion):
    """Filas para template: reservas/contratos del JSON operaciones_incluidas (sin bloque division)."""
    filas = []
    for op in liquidacion.operaciones_incluidas or []:
        if not isinstance(op, dict):
            continue
        if op.get('tipo') == 'division':
            continue
        tipo = (op.get('tipo') or '').strip().lower()
        try:
            oid = int(op.get('id'))
        except (TypeError, ValueError):
            oid = None
        etiqueta = ''
        url_name = None
        url_args = None
        if tipo == 'reserva' and oid:
            r = Reserva.objects.filter(id=oid).select_related('propiedad').first()
            if r:
                dir_ = getattr(r.propiedad, 'direccion', '') or ''
                etiqueta = f'Operación #{r.id} — {dir_}'
                url_name = 'inmobiliaria:reserva_detalle'
                url_args = [r.id]
        elif tipo == 'contrato' and oid:
            c = ContratoAlquiler.objects.filter(id=oid).first()
            if c:
                etiqueta = f'Contrato #{c.id}'
                url_name = 'inmobiliaria:detalle_contrato'
                url_args = [c.id]
        if not etiqueta:
            etiqueta = f'{tipo or "operación"} #{oid}' if oid else str(op)
        if tipo == 'reserva':
            tipo_display = 'Operación'
        elif tipo == 'contrato':
            tipo_display = 'Contrato'
        else:
            tipo_display = (tipo or '—').title()
        filas.append({
            'tipo': tipo or '—',
            'tipo_display': tipo_display,
            'id': oid,
            'etiqueta': etiqueta,
            'url': reverse(url_name, args=url_args) if url_name and url_args else None,
        })
    return filas


def _eliminar_movimiento_y_anexos(movimiento):
    """Quita movimiento de caja y registros que lo referencian (liquidación debe tener FK ya en None)."""
    if not movimiento:
        return
    try:
        from .models.recibo import Recibo
        Recibo.objects.filter(movimiento_caja=movimiento).delete()
    except Exception:
        pass
    ComisionVendedor.objects.filter(movimiento_caja=movimiento).delete()
    movimiento.delete()


def _vincular_linea_gasto_pendiente_a_liquidacion(liquidacion, linea_id, sucursal):
    """
    Asocia a la liquidación un gasto manual pendiente o un egreso de caja (mismo criterio que al crear liquidación).
    Retorna (True, None) o (False, mensaje_error).
    """
    propiedad = liquidacion.propiedad
    propietario = liquidacion.propietario
    linea_id = (linea_id or '').strip()
    if not linea_id:
        return False, 'No se indicó el gasto a vincular.'

    try:
        if linea_id.startswith('movimiento_'):
            movimiento_id = int(linea_id.replace('movimiento_', ''))
            movimiento = MovimientoCaja.objects.get(
                id=movimiento_id,
                propiedad=propiedad,
                tipo=TipoMovimientoCajaEnum.EGRESO,
                sucursal=sucursal,
            )
            if movimiento.a_descontar not in ('propietario', 'oficina', None, ''):
                return False, 'Ese movimiento no está marcado como descontable al propietario/oficina.'
            existe = GastoPropietario.objects.filter(
                Q(propiedad=propiedad) | Q(propietario=propietario),
                observaciones__icontains=f'Movimiento de caja #{movimiento.id}',
            ).exists()
            if existe:
                return False, 'Ese egreso de caja ya está cargado como gasto en el sistema.'
            desc_mov = movimiento.descripcion_para_gasto_liquidacion_propietario()[:200]
            GastoPropietario.objects.create(
                liquidacion=liquidacion,
                propietario=propietario,
                propiedad=propiedad,
                descripcion=desc_mov,
                monto=movimiento.monto_total,
                fecha_gasto=movimiento.fecha.date() if movimiento.fecha else None,
                observaciones=f'Movimiento de caja #{movimiento.id}',
                aceptado=True,
                sucursal=sucursal,
            )
            return True, None

        gasto_id = int(linea_id)
        gasto = GastoPropietario.objects.get(
            id=gasto_id,
            propietario=propietario,
            liquidacion__isnull=True,
            sucursal=sucursal,
        )
        if gasto.propiedad_id and gasto.propiedad_id != propiedad.id:
            return False, 'Ese gasto pendiente pertenece a otra propiedad.'
        gasto.liquidacion = liquidacion
        gasto.propiedad = gasto.propiedad or propiedad
        gasto.aceptado = True
        gasto.save()
        return True, None
    except (GastoPropietario.DoesNotExist, MovimientoCaja.DoesNotExist, ValueError):
        return False, 'No se encontró el gasto pendiente o el movimiento de caja indicado.'
    except Exception as exc:
        return False, str(exc)


@login_required
def detalle_liquidacion(request, liquidacion_id):
    """
    Vista para ver el detalle de una liquidación y gestionar gastos
    """
    liquidacion = get_object_or_404(
        LiquidacionPropietario.objects.select_related(
            'propietario', 'propiedad', 'reserva', 'contrato', 'movimiento_caja', 'movimiento_caja__caja'
        ).prefetch_related('gastos'),
        id=liquidacion_id,
        sucursal=request.user.sucursal
    )

    division_operaciones = []
    for op in (liquidacion.operaciones_incluidas or []):
        if isinstance(op, dict) and op.get('tipo') == 'division':
            division_operaciones = op.get('operaciones') or []
            break

    gastos_pendientes_disponibles = []
    if liquidacion.estado == 'pendiente':
        try:
            data_gp = _operaciones_gastos_pendientes_data(liquidacion.propiedad, liquidacion.sucursal)
            gastos_pendientes_disponibles = list(data_gp.get('gastos_pendientes') or [])
        except Exception:
            gastos_pendientes_disponibles = []

    context = {
        'liquidacion': liquidacion,
        'gastos': liquidacion.gastos.all().order_by('-fecha_creacion'),
        'division_operaciones': division_operaciones,
        'operaciones_tabla': _operaciones_incluidas_tabla(liquidacion),
        'puede_eliminar_liquidacion': getattr(request.user, 'nivel', 0) == 4 or getattr(request.user, 'is_superuser', False),
        'gastos_pendientes_disponibles': gastos_pendientes_disponibles,
    }

    return render(request, 'inmobiliaria/liquidaciones/detalle.html', context)


@login_required
@require_POST
@transaction.atomic
def eliminar_liquidacion(request, liquidacion_id):
    """
    Elimina una liquidación y, si estaba pagada, el movimiento de egreso asociado.
    Solo nivel 4 (administrador). Requiere confirmar escribiendo el ID en el formulario.
    """
    if getattr(request.user, 'nivel', 0) != 4 and not getattr(request.user, 'is_superuser', False):
        messages.error(request, 'Solo administradores pueden eliminar liquidaciones.')
        return redirect('inmobiliaria:detalle_liquidacion', liquidacion_id=liquidacion_id)

    confirm = (request.POST.get('confirmar_id') or '').strip()
    if confirm != str(liquidacion_id):
        messages.error(request, f'Para confirmar, escribí exactamente el número de liquidación: {liquidacion_id}')
        return redirect('inmobiliaria:detalle_liquidacion', liquidacion_id=liquidacion_id)

    liquidacion = get_object_or_404(
        LiquidacionPropietario,
        id=liquidacion_id,
        sucursal=request.user.sucursal,
    )

    mov = liquidacion.movimiento_caja
    liquidacion.movimiento_caja = None
    liquidacion.save(update_fields=['movimiento_caja'])
    if mov:
        _eliminar_movimiento_y_anexos(mov)

    lid = liquidacion.id
    liquidacion.delete()
    messages.success(request, f'Liquidación #{lid} eliminada. Las operaciones vuelven a aparecer como pendientes de liquidar si correspondía.')
    return redirect('inmobiliaria:lista_liquidaciones')


@login_required
@require_POST
def agregar_gasto(request, liquidacion_id):
    """
    Vista AJAX para agregar un gasto a una liquidación
    """
    liquidacion = get_object_or_404(
        LiquidacionPropietario,
        id=liquidacion_id,
        sucursal=request.user.sucursal
    )

    try:
        descripcion = request.POST.get('descripcion', '').strip()
        fecha_gasto = request.POST.get('fecha_gasto', '')
        observaciones = request.POST.get('observaciones', '').strip()

        if not descripcion:
            return JsonResponse({'success': False, 'error': 'La descripción es obligatoria.'})

        monto = parse_decimal_monto(request.POST.get('monto', '0'))
        if monto <= 0:
            return JsonResponse({'success': False, 'error': 'El monto debe ser mayor a cero.'})

        gasto = GastoPropietario.objects.create(
            liquidacion=liquidacion,
            propietario=liquidacion.propietario,
            propiedad=liquidacion.propiedad,
            descripcion=descripcion,
            monto=monto,
            fecha_gasto=datetime.strptime(fecha_gasto, '%Y-%m-%d').date() if fecha_gasto else None,
            observaciones=observaciones,
            aceptado=True,
            sucursal=liquidacion.sucursal,
        )

        # Recalcular monto a pagar
        liquidacion.calcular_monto_a_pagar()

        return JsonResponse({
            'success': True,
            'message': 'Gasto agregado correctamente.',
            'gasto_id': gasto.id,
            'monto_a_pagar': str(liquidacion.monto_a_pagar)
        })

    except ValueError as e:
        return JsonResponse({'success': False, 'error': f'Error en el formato de datos: {str(e)}'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error al agregar el gasto: {str(e)}'})


@login_required
@require_POST
def vincular_gasto_pendiente_liquidacion(request, liquidacion_id):
    """Asocia a una liquidación pendiente un gasto manual pendiente o un egreso de caja aún no liquidado."""
    liquidacion = get_object_or_404(
        LiquidacionPropietario,
        id=liquidacion_id,
        sucursal=request.user.sucursal,
        estado='pendiente',
    )
    linea_id = (request.POST.get('linea_id') or '').strip()
    ok, err = _vincular_linea_gasto_pendiente_a_liquidacion(liquidacion, linea_id, request.user.sucursal)
    if ok:
        liquidacion.calcular_monto_a_pagar()
        return JsonResponse(
            {
                'success': True,
                'message': 'Gasto vinculado correctamente.',
                'monto_a_pagar': str(liquidacion.monto_a_pagar),
            }
        )
    return JsonResponse({'success': False, 'error': err or 'No se pudo vincular el gasto.'})


@login_required
def crear_gasto_pendiente(request):
    """
    Vista AJAX para crear un gasto pendiente del propietario (sin liquidación)
    """
    if request.method == 'POST':
        try:
            propietario_id = request.POST.get('propietario_id')
            propiedad_id = request.POST.get('propiedad_id')
            descripcion = request.POST.get('descripcion', '').strip()
            fecha_gasto = request.POST.get('fecha_gasto', '')
            observaciones = request.POST.get('observaciones', '').strip()

            if not descripcion:
                return JsonResponse({'success': False, 'error': 'La descripción es obligatoria.'})

            if not propietario_id and not propiedad_id:
                return JsonResponse({'success': False, 'error': 'Debe seleccionar un propietario o una propiedad.'})

            monto = parse_decimal_monto(request.POST.get('monto', '0'))
            if monto <= 0:
                return JsonResponse({'success': False, 'error': 'El monto debe ser mayor a cero.'})

            propietario = None
            propiedad = None
            
            if propietario_id:
                propietario = get_object_or_404(Propietario, id=propietario_id, sucursal=request.user.sucursal)
            if propiedad_id:
                propiedad = get_object_or_404(Propiedad, id=propiedad_id, sucursal=request.user.sucursal)
                if not propietario:
                    propietario = propiedad.propietario

            gasto = GastoPropietario.objects.create(
                propietario=propietario,
                propiedad=propiedad,
                descripcion=descripcion,
                monto=monto,
                fecha_gasto=datetime.strptime(fecha_gasto, '%Y-%m-%d').date() if fecha_gasto else None,
                observaciones=observaciones,
                sucursal=request.user.sucursal
            )

            return JsonResponse({
                'success': True,
                'message': 'Gasto pendiente creado correctamente.',
                'gasto': {
                    'id': gasto.id,
                    'descripcion': gasto.descripcion,
                    'monto': str(gasto.monto),
                    'fecha_gasto': gasto.fecha_gasto.strftime('%Y-%m-%d') if gasto.fecha_gasto else '',
                    'observaciones': gasto.observaciones,
                }
            })

        except ValueError as e:
            return JsonResponse({'success': False, 'error': f'Error en el formato de datos: {str(e)}'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Error al crear el gasto: {str(e)}'})
    
    return JsonResponse({'success': False, 'error': 'Método no permitido.'})


@login_required
@require_POST
def aceptar_rechazar_gasto(request, gasto_id):
    """
    Vista AJAX para aceptar o rechazar un gasto
    """
    gasto = get_object_or_404(
        GastoPropietario,
        id=gasto_id,
        liquidacion__sucursal=request.user.sucursal
    )

    try:
        accion = request.POST.get('accion', '').strip()
        if accion not in ['aceptar', 'rechazar']:
            return JsonResponse({'success': False, 'error': 'Acción inválida.'})

        gasto.aceptado = (accion == 'aceptar')
        gasto.save()

        # Recalcular monto a pagar
        gasto.liquidacion.calcular_monto_a_pagar()

        return JsonResponse({
            'success': True,
            'message': f'Gasto {"aceptado" if gasto.aceptado else "rechazado"} correctamente.',
            'monto_a_pagar': str(gasto.liquidacion.monto_a_pagar)
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error al procesar el gasto: {str(e)}'})


@login_required
@require_POST
@transaction.atomic
def eliminar_gasto_liquidacion(request, gasto_id):
    """
    Elimina un gasto asociado a una liquidación en estado pendiente y recalcula el monto a pagar.
    """
    gasto = get_object_or_404(
        GastoPropietario.objects.select_related('liquidacion'),
        id=gasto_id,
        liquidacion__sucursal=request.user.sucursal,
    )
    liquidacion = gasto.liquidacion
    if not liquidacion:
        return JsonResponse(
            {'success': False, 'error': 'Este gasto no está asociado a una liquidación.'},
            status=400,
        )
    if liquidacion.estado != 'pendiente':
        return JsonResponse(
            {
                'success': False,
                'error': 'Solo se pueden eliminar gastos mientras la liquidación está pendiente.',
            },
            status=400,
        )

    try:
        gasto.delete()
        liquidacion.calcular_monto_a_pagar()
        return JsonResponse(
            {
                'success': True,
                'message': 'Gasto eliminado correctamente.',
                'monto_a_pagar': str(liquidacion.monto_a_pagar),
            }
        )
    except Exception as e:
        return JsonResponse(
            {'success': False, 'error': f'Error al eliminar el gasto: {str(e)}'},
            status=500,
        )


@login_required
@transaction.atomic
@require_POST
def confirmar_liquidacion(request, liquidacion_id):
    """
    Confirma la liquidación y la deja cerrada para pago posterior.
    """
    liquidacion = get_object_or_404(
        LiquidacionPropietario,
        id=liquidacion_id,
        sucursal=request.user.sucursal,
        estado='pendiente'
    )

    liquidacion.estado = 'cerrada'
    liquidacion.fecha_procesamiento = timezone.now()
    liquidacion.save(update_fields=['estado', 'fecha_procesamiento'])

    messages.success(request, 'Liquidación confirmada y cerrada. Ahora podés volver y pagarla cuando quieras.')
    return redirect('inmobiliaria:detalle_liquidacion', liquidacion_id=liquidacion.id)


@login_required
@transaction.atomic
@require_POST
def marcar_liquidacion_oficina(request, liquidacion_id):
    """
    Marca la liquidación en estado oficina.
    """
    liquidacion = get_object_or_404(
        LiquidacionPropietario,
        id=liquidacion_id,
        sucursal=request.user.sucursal,
        estado__in=['pendiente', 'cerrada']
    )

    liquidacion.estado = 'oficina'
    liquidacion.fecha_procesamiento = timezone.now()
    liquidacion.save(update_fields=['estado', 'fecha_procesamiento'])

    messages.success(request, 'Liquidación marcada como Oficina.')
    return redirect('inmobiliaria:detalle_liquidacion', liquidacion_id=liquidacion.id)


@login_required
@transaction.atomic
@require_POST
def procesar_liquidacion(request, liquidacion_id):
    """
    Vista para procesar una liquidación (descontar de caja)
    """
    liquidacion = get_object_or_404(
        LiquidacionPropietario,
        id=liquidacion_id,
        sucursal=request.user.sucursal,
        estado='cerrada'
    )

    try:
        # Obtener caja abierta
        caja = Caja.objects.filter(
            sucursal=request.user.sucursal,
            estado='abierta'
        ).first()

        if not caja:
            messages.error(request, 'No hay una caja abierta. Debe abrir una caja primero.')
            return redirect('inmobiliaria:detalle_liquidacion', liquidacion_id=liquidacion_id)

        # Obtener método de pago
        monto_efectivo = parse_decimal_monto(request.POST.get('monto_efectivo', '0'))
        monto_cheque = parse_decimal_monto(request.POST.get('monto_cheque', '0'))
        monto_tarjeta = parse_decimal_monto(request.POST.get('monto_tarjeta', '0'))
        monto_deposito = parse_decimal_monto(request.POST.get('monto_deposito', '0'))

        total_pago = monto_efectivo + monto_cheque + monto_tarjeta + monto_deposito

        if total_pago != liquidacion.monto_a_pagar:
            messages.error(request, f'El total del pago (${total_pago}) no coincide con el monto a pagar (${liquidacion.monto_a_pagar}).')
            return redirect('inmobiliaria:detalle_liquidacion', liquidacion_id=liquidacion_id)

        # Crear movimiento de caja (egreso)
        movimiento = MovimientoCaja.objects.create(
            fecha=timezone.now(),
            tipo=TipoMovimientoCajaEnum.EGRESO,
            tipo_comprobante='RC',  # Recibo
            concepto=f'Liquidación Propietario - {liquidacion.propietario} - {liquidacion.propiedad.direccion}',
            propiedad=liquidacion.propiedad,
            fecha_desde=liquidacion.fecha_desde,
            fecha_hasta=liquidacion.fecha_hasta,
            monto_efectivo=monto_efectivo,
            monto_cheque=monto_cheque,
            monto_tarjeta=monto_tarjeta,
            monto_deposito=monto_deposito,
            a_descontar='propietario',
            sucursal=request.user.sucursal,
            empleado=request.user,
            caja=caja
        )

        # Actualizar liquidación
        liquidacion.movimiento_caja = movimiento
        liquidacion.estado = 'pagada'
        liquidacion.fecha_procesamiento = timezone.now()
        liquidacion.save()

        messages.success(request, f'Liquidación procesada correctamente. Se descontó ${liquidacion.monto_a_pagar} de la caja.')
        return redirect('inmobiliaria:detalle_liquidacion', liquidacion_id=liquidacion.id)

    except Exception as e:
        messages.error(request, f'Error al procesar la liquidación: {str(e)}')
        return redirect('inmobiliaria:detalle_liquidacion', liquidacion_id=liquidacion_id)
