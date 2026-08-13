"""
Portal público Gonnet (/web/): landing, búsqueda temporario, ficha y consulta (lead).
No requiere login. No crea Reserva — opción A.
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from inmobiliaria.models import ImagenPropiedad, Propiedad
from inmobiliaria.models.portal_web import ConsultaWeb
from inmobiliaria.portal_servicio import (
    buscar_temporario_portal,
    parse_fecha_portal,
    qs_destacadas_portal,
    qs_propiedades_portal,
    titulo_publico_propiedad,
)


def _ctx_base(**extra):
    ctx = {
        'portal_nombre': 'Nestor Oscar Gonnet Propiedades',
        'portal_tagline': 'Excelencia y trayectoria en gestión inmobiliaria de alta gama.',
    }
    ctx.update(extra)
    return ctx


@require_http_methods(['GET'])
def portal_home(request):
    destacadas = []
    for p in qs_destacadas_portal(12):
        fotos = getattr(p, 'fotos_ordenadas', None) or []
        destacadas.append({
            'propiedad': p,
            'titulo': titulo_publico_propiedad(p),
            'foto': fotos[0] if fotos else None,
            'fotos': fotos[:6],
        })
    return render(request, 'portal/home.html', _ctx_base(
        destacadas=destacadas,
        form_ficha=request.GET.get('ficha', ''),
        form_ambientes=request.GET.get('ambientes', ''),
        form_desde=request.GET.get('desde', ''),
        form_hasta=request.GET.get('hasta', ''),
        form_sucursal=request.GET.get('sucursal', ''),
    ))


@require_http_methods(['GET'])
def portal_buscar(request):
    ficha = (request.GET.get('ficha') or '').strip()
    ambientes = (request.GET.get('ambientes') or '').strip()
    desde = parse_fecha_portal(request.GET.get('desde'))
    hasta = parse_fecha_portal(request.GET.get('hasta'))
    sucursal = (request.GET.get('sucursal') or '').strip().lower()
    error = ''
    resultados = []

    if not desde or not hasta:
        error = 'Indicá fechas Desde y Hasta para buscar disponibilidad.'
    elif hasta <= desde:
        error = 'La fecha Hasta debe ser posterior a Desde.'
    else:
        resultados = buscar_temporario_portal(
            fecha_inicio=desde,
            fecha_fin=hasta,
            ficha=ficha,
            ambientes=ambientes or None,
        )
        if sucursal in ('colon', 'colón'):
            resultados = [
                r for r in resultados
                if 'colon' in (r.get('sucursal_nombre') or '').lower()
            ]
        elif sucursal == 'corrientes':
            resultados = [
                r for r in resultados
                if 'corrientes' in (r.get('sucursal_nombre') or '').lower()
            ]

    for r in resultados:
        r['titulo'] = titulo_publico_propiedad(r['propiedad'])

    return render(request, 'portal/buscar.html', _ctx_base(
        resultados=resultados,
        error=error,
        form_ficha=ficha,
        form_ambientes=ambientes,
        form_desde=request.GET.get('desde', ''),
        form_hasta=request.GET.get('hasta', ''),
        form_sucursal=request.GET.get('sucursal', ''),
        fecha_desde=desde,
        fecha_hasta=hasta,
        total=len(resultados),
    ))


@require_http_methods(['GET', 'POST'])
def portal_ficha(request, propiedad_id):
    prop = get_object_or_404(qs_propiedades_portal(), pk=propiedad_id)
    fotos = list(
        ImagenPropiedad.objects.filter(propiedad=prop).order_by('orden', 'id')[:20]
    )
    desde = parse_fecha_portal(request.GET.get('desde') or request.POST.get('fecha_desde'))
    hasta = parse_fecha_portal(request.GET.get('hasta') or request.POST.get('fecha_hasta'))
    precio_estimado = None
    disponible = None

    if desde and hasta and hasta > desde:
        hallados = buscar_temporario_portal(
            fecha_inicio=desde,
            fecha_fin=hasta,
            ficha=str(prop.id),
            limite=1,
        )
        if hallados and hallados[0]['propiedad'].id == prop.id:
            disponible = True
            precio_estimado = hallados[0]['precio_total']
        else:
            disponible = False

    if request.method == 'POST':
        nombre = (request.POST.get('nombre') or '').strip()
        email = (request.POST.get('email') or '').strip()
        telefono = (request.POST.get('telefono') or '').strip()
        mensaje = (request.POST.get('mensaje') or '').strip()
        if not nombre:
            messages.error(request, 'Ingresá tu nombre.')
        elif not email and not telefono:
            messages.error(request, 'Dejanos un email o un teléfono para contactarte.')
        else:
            ConsultaWeb.objects.create(
                nombre=nombre,
                email=email,
                telefono=telefono,
                mensaje=mensaje,
                fecha_desde=desde,
                fecha_hasta=hasta,
                propiedad=prop,
                ficha=str(prop.id),
                sucursal_preferida=getattr(getattr(prop, 'sucursal', None), 'nombre', '') or '',
                ambientes=prop.ambientes,
                tipo_operacion='alquiler_temporario',
            )
            messages.success(
                request,
                '¡Gracias! Recibimos tu consulta. Te vamos a contactar a la brevedad.',
            )
            return redirect(
                reverse('inmobiliaria:portal_ficha', args=[prop.id])
                + (f'?desde={desde}&hasta={hasta}' if desde and hasta else '')
            )

    return render(request, 'portal/ficha.html', _ctx_base(
        propiedad=prop,
        titulo=titulo_publico_propiedad(prop),
        fotos=fotos,
        fecha_desde=desde,
        fecha_hasta=hasta,
        form_desde=request.GET.get('desde', '') or (desde.isoformat() if desde else ''),
        form_hasta=request.GET.get('hasta', '') or (hasta.isoformat() if hasta else ''),
        disponible=disponible,
        precio_estimado=precio_estimado,
    ))


@require_http_methods(['GET', 'POST'])
def portal_contacto(request):
    if request.method == 'POST':
        nombre = (request.POST.get('nombre') or '').strip()
        email = (request.POST.get('email') or '').strip()
        telefono = (request.POST.get('telefono') or '').strip()
        mensaje = (request.POST.get('mensaje') or '').strip()
        ficha = (request.POST.get('ficha') or '').strip()
        desde = parse_fecha_portal(request.POST.get('fecha_desde'))
        hasta = parse_fecha_portal(request.POST.get('fecha_hasta'))
        prop = None
        if ficha:
            prop = qs_propiedades_portal().filter(pk=ficha).first()
        if not nombre:
            messages.error(request, 'Ingresá tu nombre.')
        elif not email and not telefono:
            messages.error(request, 'Dejanos un email o un teléfono.')
        else:
            ConsultaWeb.objects.create(
                nombre=nombre,
                email=email,
                telefono=telefono,
                mensaje=mensaje,
                fecha_desde=desde,
                fecha_hasta=hasta,
                propiedad=prop,
                ficha=ficha,
                sucursal_preferida=(request.POST.get('sucursal') or '').strip(),
                tipo_operacion=(request.POST.get('tipo_operacion') or 'alquiler_temporario'),
            )
            messages.success(request, '¡Gracias! Recibimos tu mensaje.')
            return redirect('inmobiliaria:portal_contacto')

    return render(request, 'portal/contacto.html', _ctx_base(
        form_ficha=request.GET.get('ficha', ''),
        form_desde=request.GET.get('desde', ''),
        form_hasta=request.GET.get('hasta', ''),
    ))


@login_required
@require_http_methods(['GET'])
def portal_consultas_staff(request):
    """Listado interno de leads del portal."""
    qs = ConsultaWeb.objects.select_related('propiedad', 'propiedad__sucursal')[:200]
    return render(request, 'portal/consultas_staff.html', {
        'consultas': qs,
    })
