"""Módulo Oficina: gastos, categorías y acceso a honorarios, vales, comisiones y cartera."""
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from inmobiliaria.models import (
    Caja,
    CarteraPropiedadUsuario,
    CategoriaGastoOficina,
    ComisionVendedor,
    GastoOficina,
    LiquidacionPropietario,
    ValeVendedor,
)
from inmobiliaria.models.persona import usuario_es_nivel_administracion
from inmobiliaria.oficina_gastos import asegurar_categorias_base


def _parse_fecha(s):
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _puede_oficina(user):
    return usuario_es_nivel_administracion(user)


def _arbol_categorias(sucursal):
    raices = (
        CategoriaGastoOficina.objects.filter(sucursal=sucursal, parent__isnull=True)
        .prefetch_related('subcategorias')
        .order_by('orden', 'nombre')
    )
    arbol = []
    for raiz in raices:
        hijos = list(raiz.subcategorias.order_by('orden', 'nombre'))
        arbol.append({'categoria': raiz, 'hijos': hijos})
    return arbol


def _totales_gastos_por_raiz(qs_gastos):
    totales = defaultdict(lambda: Decimal('0'))
    for g in qs_gastos.select_related('categoria', 'categoria__parent'):
        raiz = g.categoria_raiz
        nombre = raiz.nombre if raiz else 'Sin categoría'
        totales[nombre] += g.monto or Decimal('0')
    return dict(totales)


@login_required
def oficina_dashboard(request):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    sucursal = request.user.sucursal
    asegurar_categorias_base(sucursal)

    today = timezone.localdate()
    mes_ini = today.replace(day=1)

    gastos_mes = GastoOficina.objects.filter(
        sucursal=sucursal,
        fecha__gte=mes_ini,
        fecha__lte=today,
    )
    total_gastos_mes = gastos_mes.aggregate(t=Sum('monto'))['t'] or Decimal('0')
    totales_por_categoria = _totales_gastos_por_raiz(gastos_mes)

    honorarios_mes = LiquidacionPropietario.objects.filter(
        sucursal=sucursal,
    ).exclude(estado='cancelada')
    # Aproximación ingresos mes: liquidaciones creadas en el mes
    honorarios_mes = honorarios_mes.filter(
        fecha_creacion__date__gte=mes_ini,
        fecha_creacion__date__lte=today,
    )
    ingresos_mes = Decimal('0')
    for liq in honorarios_mes.only(
        'monto_inmobiliaria', 'monto_cochera', 'monto_fondo_mantenimiento'
    ):
        ingresos_mes += (
            Decimal(str(liq.monto_inmobiliaria or 0))
            + Decimal(str(liq.monto_cochera or 0))
            + Decimal(str(liq.monto_fondo_mantenimiento or 0))
        )

    comisiones_pendientes = ComisionVendedor.objects.filter(
        vendedor__sucursal=sucursal,
        estado='pendiente',
    ).count()
    vales_abiertos = ValeVendedor.objects.filter(
        vendedor__sucursal=sucursal,
    ).count()
    propiedades_cartera = CarteraPropiedadUsuario.objects.filter(
        propiedad__sucursal=sucursal,
    ).values('propiedad').distinct().count()

    return render(
        request,
        'inmobiliaria/oficina/dashboard.html',
        {
            'total_gastos_mes': total_gastos_mes,
            'ingresos_honorarios_mes': ingresos_mes,
            'totales_por_categoria': sorted(totales_por_categoria.items()),
            'comisiones_pendientes': comisiones_pendientes,
            'vales_count': vales_abiertos,
            'propiedades_cartera': propiedades_cartera,
            'mes_label': mes_ini.strftime('%B %Y'),
        },
    )


@login_required
def oficina_gastos(request):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    sucursal = request.user.sucursal
    asegurar_categorias_base(sucursal)

    fecha_desde_s = (request.GET.get('fecha_desde') or '').strip()
    fecha_hasta_s = (request.GET.get('fecha_hasta') or '').strip()
    categoria_id = (request.GET.get('categoria') or '').strip()
    q = (request.GET.get('q') or '').strip()

    today = timezone.localdate()
    if not fecha_desde_s and not fecha_hasta_s:
        fecha_desde_s = today.replace(day=1).isoformat()
        fecha_hasta_s = today.isoformat()

    dr_desde = _parse_fecha(fecha_desde_s)
    dr_hasta = _parse_fecha(fecha_hasta_s)
    if dr_desde and dr_hasta and dr_hasta < dr_desde:
        dr_desde, dr_hasta = dr_hasta, dr_desde
        fecha_desde_s, fecha_hasta_s = dr_desde.isoformat(), dr_hasta.isoformat()

    qs = GastoOficina.objects.filter(sucursal=sucursal).select_related(
        'categoria', 'categoria__parent', 'usuario_creacion', 'vendedor', 'movimiento_caja'
    )
    if dr_desde:
        qs = qs.filter(fecha__gte=dr_desde)
    if dr_hasta:
        qs = qs.filter(fecha__lte=dr_hasta)
    if categoria_id.isdigit():
        cat = CategoriaGastoOficina.objects.filter(
            sucursal=sucursal, id=int(categoria_id)
        ).first()
        if cat:
            hijos_ids = list(
                CategoriaGastoOficina.objects.filter(sucursal=sucursal, parent=cat).values_list(
                    'id', flat=True
                )
            )
            ids = [cat.id] + hijos_ids
            qs = qs.filter(categoria_id__in=ids)
    if q:
        qs = qs.filter(descripcion__icontains=q)

    total = qs.aggregate(t=Sum('monto'))['t'] or Decimal('0')
    gastos = list(qs.order_by('-fecha', '-id')[:500])
    totales_por_categoria = _totales_gastos_por_raiz(qs)

    raices_filtro = CategoriaGastoOficina.objects.filter(
        sucursal=sucursal, parent__isnull=True, activa=True
    ).order_by('orden', 'nombre')

    caja_abierta = (
        Caja.objects.filter(sucursal=sucursal, estado='abierta')
        .order_by('-fecha_apertura')
        .first()
    )

    return render(
        request,
        'inmobiliaria/oficina/gastos_lista.html',
        {
            'gastos': gastos,
            'total': total,
            'totales_por_categoria': sorted(totales_por_categoria.items()),
            'fecha_desde': fecha_desde_s,
            'fecha_hasta': fecha_hasta_s,
            'categoria_filtro': categoria_id,
            'q': q,
            'raices_filtro': raices_filtro,
            'caja_abierta': caja_abierta,
        },
    )


@login_required
@require_POST
def oficina_gasto_crear(request):
    """Los gastos se cargan desde Nuevo movimiento de caja, no desde este panel."""
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    messages.info(
        request,
        'Los gastos de oficina se registran desde Caja → Nuevo movimiento, '
        'marcando «Gasto de oficina».',
    )
    return redirect('inmobiliaria:oficina_gastos')


@login_required
@require_POST
def oficina_gasto_eliminar(request, gasto_id):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    gasto = get_object_or_404(
        GastoOficina.objects.select_related('movimiento_caja'),
        id=gasto_id,
        sucursal=request.user.sucursal,
    )
    if gasto.movimiento_caja_id:
        messages.error(
            request,
            f'Este gasto está vinculado al movimiento de caja #{gasto.movimiento_caja_id}. '
            'Eliminá o anulá el movimiento desde la caja.',
        )
        return redirect('inmobiliaria:oficina_gastos')
    gasto.delete()
    messages.success(request, 'Gasto eliminado.')
    return redirect('inmobiliaria:oficina_gastos')


@login_required
def oficina_categorias(request):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    sucursal = request.user.sucursal
    asegurar_categorias_base(sucursal)

    return render(
        request,
        'inmobiliaria/oficina/categorias.html',
        {
            'arbol': _arbol_categorias(sucursal),
        },
    )


@login_required
@require_POST
def oficina_categoria_crear(request):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    sucursal = request.user.sucursal
    nombre = (request.POST.get('nombre') or '').strip()
    parent_id = (request.POST.get('parent_id') or '').strip()

    if not nombre:
        messages.error(request, 'El nombre es obligatorio.')
        return redirect('inmobiliaria:oficina_categorias')

    parent = None
    if parent_id.isdigit():
        parent = get_object_or_404(
            CategoriaGastoOficina,
            id=int(parent_id),
            sucursal=sucursal,
            parent__isnull=True,
        )

    if CategoriaGastoOficina.objects.filter(
        sucursal=sucursal, parent=parent, nombre__iexact=nombre
    ).exists():
        messages.error(request, 'Ya existe una categoría con ese nombre.')
        return redirect('inmobiliaria:oficina_categorias')

    CategoriaGastoOficina.objects.create(
        sucursal=sucursal,
        parent=parent,
        nombre=nombre,
    )
    messages.success(
        request,
        'Subcategoría creada.' if parent else 'Categoría creada.',
    )
    return redirect('inmobiliaria:oficina_categorias')


@login_required
@require_POST
def oficina_categoria_toggle(request, categoria_id):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    cat = get_object_or_404(CategoriaGastoOficina, id=categoria_id, sucursal=request.user.sucursal)
    cat.activa = not cat.activa
    cat.save(update_fields=['activa'])
    if cat.parent_id is None:
        CategoriaGastoOficina.objects.filter(sucursal=cat.sucursal, parent=cat).update(
            activa=cat.activa
        )
    messages.success(request, 'Categoría actualizada.')
    return redirect('inmobiliaria:oficina_categorias')
