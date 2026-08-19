"""
Portal público Gonnet (/web/): landing, búsqueda, ficha y consulta (lead).
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
from inmobiliaria.models.propiedad import TIPOS_INMUEBLES, TIPOS_VALORACION, TIPOS_VISTA
from inmobiliaria.portal_logo_data import LOGO_DATA_URI
from inmobiliaria.portal_geo import (
    completar_coordenadas_resultados,
    google_maps_api_key,
    markers_portal_resultados,
)
from inmobiliaria.portal_servicio import (
    OPERACION_LABELS,
    OPERACIONES_PORTAL,
    buscar_portal,
    buscar_temporario_portal,
    es_codigo_operacion,
    normalizar_operacion,
    parse_fecha_portal,
    qs_destacadas_portal,
    qs_propiedades_portal,
    titulo_publico_propiedad,
    usuario_gestiona_portal_web,
)

COMODIDADES_FILTRO = [
    ('cochera', 'Cochera'),
    ('parrilla', 'Parrilla'),
    ('reciclado', 'Reciclado'),
    ('terraza', 'Terraza'),
    ('baulera', 'Baulera'),
    ('seguridad', 'Seguridad'),
    ('vista_panoramica', 'Vista panorámica'),
    ('patio', 'Patio'),
    ('piscina', 'Piscina'),
    ('a_estrenar', 'A estrenar'),
    ('balcon', 'Balcón'),
    ('lavadero', 'Lavadero'),
    ('vista_al_Mar', 'Vista al mar'),
    ('apto_credito', 'Apto crédito'),
    ('amoblado', 'Amoblado'),
    ('wifi', 'WiFi'),
]


def _ctx_base(**extra):
    ctx = {
        'portal_nombre': 'Nestor Oscar Gonnet Propiedades',
        'portal_tagline': 'Excelencia y trayectoria en gestión inmobiliaria de alta gama.',
        'operaciones_portal': OPERACIONES_PORTAL,
        'portal_logo_src': LOGO_DATA_URI,
    }
    ctx.update(extra)
    return ctx


@require_http_methods(['GET', 'HEAD'])
def portal_logo(request):
    """Sirve el logo embebido (no depende de collectstatic/S3)."""
    import base64
    from django.http import HttpResponse

    raw = LOGO_DATA_URI.split(',', 1)[-1]
    resp = HttpResponse(base64.b64decode(raw), content_type='image/png')
    resp['Cache-Control'] = 'public, max-age=604800'
    return resp


@require_http_methods(['GET', 'HEAD'])
def portal_hero(request):
    """Sirve la foto hero de Mar del Plata desde el filesystem de la app."""
    from pathlib import Path
    from django.http import FileResponse, Http404

    base = Path(__file__).resolve().parent / 'static' / 'images'
    for name in ('hero-mardelplata.jpg', 'hero-mardelplata.png'):
        path = base / name
        if path.is_file():
            ctype = 'image/jpeg' if path.suffix.lower() in ('.jpg', '.jpeg') else 'image/png'
            resp = FileResponse(path.open('rb'), content_type=ctype)
            resp['Cache-Control'] = 'public, max-age=604800'
            return resp
    raise Http404('Hero no encontrado')


@require_http_methods(['GET', 'HEAD'])
def portal_mapa_js(request):
    from pathlib import Path
    from django.http import FileResponse, Http404

    path = Path(__file__).resolve().parent / 'static' / 'portal' / 'mapa-busqueda.js'
    if not path.is_file():
        raise Http404('mapa-busqueda.js')
    resp = FileResponse(path.open('rb'), content_type='application/javascript; charset=utf-8')
    resp['Cache-Control'] = 'no-cache'
    return resp


def _resolver_operacion(request):
    if request.GET.get('operacion'):
        return normalizar_operacion(request.GET.get('operacion'))
    tipo = (request.GET.get('tipo') or '').strip()
    if es_codigo_operacion(tipo):
        return normalizar_operacion(tipo)
    return 'alquiler_temporario'


def _resolver_tipo_inmueble(request):
    t = (request.GET.get('tipo_inmueble') or '').strip()
    if t:
        return t
    tipo = (request.GET.get('tipo') or '').strip()
    if tipo and not es_codigo_operacion(tipo):
        return tipo
    return ''


def _enriquecer_resultados(resultados):
    for r in resultados:
        r['titulo'] = titulo_publico_propiedad(r['propiedad'])
        prop = r['propiedad']
        r['ubicacion'] = (
            getattr(prop, 'ubicacion', None)
            or getattr(prop, 'direccion', None)
            or r.get('sucursal_nombre')
            or ''
        )
    return resultados


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
            'ubicacion': (
                getattr(p, 'ubicacion', None)
                or getattr(p, 'direccion', None)
                or ''
            ),
        })
    return render(request, 'portal/home.html', _ctx_base(
        destacadas=destacadas,
        form_ficha=request.GET.get('ficha', ''),
        form_ambientes=request.GET.get('ambientes', ''),
        form_desde=request.GET.get('desde', ''),
        form_hasta=request.GET.get('hasta', ''),
        form_operacion=normalizar_operacion(request.GET.get('operacion', '')),
        nav_active='inicio',
    ))


@require_http_methods(['GET'])
def portal_buscar(request):
    operacion = _resolver_operacion(request)
    ficha = (request.GET.get('ficha') or '').strip()
    ambientes = (request.GET.get('ambientes') or '').strip()
    q = (request.GET.get('q') or '').strip()
    tipo_raw = _resolver_tipo_inmueble(request)
    valoracion = (request.GET.get('valoracion') or '').strip()
    vista = (request.GET.get('vista') or '').strip()
    comodidades = [c for c in request.GET.getlist('comodidad') if c]
    desde = parse_fecha_portal(request.GET.get('desde') or request.GET.get('fecha_inicio'))
    hasta = parse_fecha_portal(request.GET.get('hasta') or request.GET.get('fecha_fin'))
    error = ''
    resultados = []

    if operacion == 'alquiler_temporario':
        if not desde or not hasta:
            error = 'Indicá fechas Desde y Hasta para buscar disponibilidad.'
        elif hasta <= desde:
            error = 'La fecha Hasta debe ser posterior a Desde.'
        else:
            resultados = buscar_portal(
                operacion=operacion,
                fecha_inicio=desde,
                fecha_fin=hasta,
                ficha=ficha,
                ambientes=ambientes or None,
                q=q,
                tipo_inmueble=tipo_raw,
                valoracion=valoracion,
                vista=vista,
                comodidades=comodidades,
            )
    else:
        resultados = buscar_portal(
            operacion=operacion,
            ficha=ficha,
            ambientes=ambientes or None,
            q=q,
            tipo_inmueble=tipo_raw,
            valoracion=valoracion,
            vista=vista,
            comodidades=comodidades,
        )

    _enriquecer_resultados(resultados)
    if resultados:
        completar_coordenadas_resultados(resultados, limite=5)
    markers = markers_portal_resultados(resultados, request)

    return render(request, 'portal/buscar.html', _ctx_base(
        resultados=resultados,
        error=error,
        form_ficha=ficha,
        form_ambientes=ambientes,
        form_q=q,
        form_tipo_inmueble=tipo_raw,
        form_valoracion=valoracion,
        form_vista=vista,
        form_comodidades=set(comodidades),
        form_desde=request.GET.get('desde') or request.GET.get('fecha_inicio') or '',
        form_hasta=request.GET.get('hasta') or request.GET.get('fecha_fin') or '',
        form_operacion=operacion,
        operacion_label=OPERACION_LABELS.get(operacion, 'Alquiler temporario'),
        fecha_desde=desde,
        fecha_hasta=hasta,
        total=len(resultados),
        markers=markers,
        markers_count=len(markers),
        google_maps_api_key=google_maps_api_key(),
        tipos_inmueble=TIPOS_INMUEBLES,
        tipos_valoracion=TIPOS_VALORACION,
        tipos_vista=TIPOS_VISTA,
        comodidades_filtro=COMODIDADES_FILTRO,
        requiere_fechas=(operacion == 'alquiler_temporario'),
        nav_active='buscar',
    ))


@require_http_methods(['GET', 'POST'])
def portal_ficha(request, propiedad_id):
    prop = get_object_or_404(qs_propiedades_portal(), pk=propiedad_id)
    fotos = list(
        ImagenPropiedad.objects.filter(propiedad=prop).order_by('orden', 'id')[:20]
    )
    operacion = normalizar_operacion(
        request.GET.get('operacion') or request.POST.get('operacion') or 'alquiler_temporario'
    )
    desde = parse_fecha_portal(request.GET.get('desde') or request.POST.get('fecha_desde'))
    hasta = parse_fecha_portal(request.GET.get('hasta') or request.POST.get('fecha_hasta'))
    precio_estimado = None
    precio_label = ''
    disponible = None

    if operacion == 'alquiler_temporario':
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
    elif operacion == 'venta':
        info = getattr(prop, 'info_venta', None)
        if info and info.en_venta and info.estado in ('disponible', 'reservado'):
            disponible = True
            precio_estimado = info.precio_venta
        else:
            disponible = False
    elif operacion == '24_meses':
        info = getattr(prop, 'info_meses', None)
        if info and info.disponible and (
            info.estado == 'disponible' or info.ofrecible_desde
        ):
            disponible = True
            precio_estimado = info.precio_mensual
            precio_label = '/mes'
        else:
            disponible = False
    elif operacion == 'invierno':
        info = getattr(prop, 'info_invierno', None)
        if info and info.disponible and info.estado == 'disponible':
            disponible = True
            precio_estimado = info.precio_mensual
            precio_label = '/mes'
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
                tipo_operacion=operacion,
            )
            messages.success(
                request,
                '¡Gracias! Recibimos tu consulta. Te vamos a contactar a la brevedad.',
            )
            qs = f'?operacion={operacion}'
            if desde and hasta:
                qs += f'&desde={desde}&hasta={hasta}'
            return redirect(reverse('inmobiliaria:portal_ficha', args=[prop.id]) + qs)

    return render(request, 'portal/ficha.html', _ctx_base(
        propiedad=prop,
        titulo=titulo_publico_propiedad(prop),
        fotos=fotos,
        fecha_desde=desde,
        fecha_hasta=hasta,
        form_desde=request.GET.get('desde', '') or (desde.isoformat() if desde else ''),
        form_hasta=request.GET.get('hasta', '') or (hasta.isoformat() if hasta else ''),
        form_operacion=operacion,
        operacion_label=OPERACION_LABELS.get(operacion, ''),
        requiere_fechas=(operacion == 'alquiler_temporario'),
        disponible=disponible,
        precio_estimado=precio_estimado,
        precio_label=precio_label,
        google_maps_api_key=google_maps_api_key(),
        mapa_lat=float(prop.latitud) if prop.latitud is not None else None,
        mapa_lng=float(prop.longitud) if prop.longitud is not None else None,
    ))


def _guardar_consulta_web(request, *, tipo_operacion_default='consulta'):
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
        return False
    if not email and not telefono:
        messages.error(request, 'Dejanos un email o un teléfono.')
        return False
    ConsultaWeb.objects.create(
        nombre=nombre,
        email=email,
        telefono=telefono,
        mensaje=mensaje,
        fecha_desde=desde,
        fecha_hasta=hasta,
        propiedad=prop,
        ficha=ficha,
        sucursal_preferida='',
        tipo_operacion=(request.POST.get('tipo_operacion') or tipo_operacion_default),
    )
    messages.success(request, '¡Gracias! Recibimos tu mensaje.')
    return True


@require_http_methods(['GET', 'POST'])
def portal_contacto(request):
    if request.method == 'POST':
        if _guardar_consulta_web(request, tipo_operacion_default='consulta'):
            return redirect('inmobiliaria:portal_contacto')

    return render(request, 'portal/contacto.html', _ctx_base(
        form_ficha=request.GET.get('ficha', ''),
        form_desde=request.GET.get('desde', ''),
        form_hasta=request.GET.get('hasta', ''),
        nav_active='contacto',
    ))


@require_http_methods(['GET', 'POST'])
def portal_quiero_vender(request):
    if request.method == 'POST':
        if _guardar_consulta_web(request, tipo_operacion_default='quiero_vender'):
            return redirect('inmobiliaria:portal_quiero_vender')

    return render(request, 'portal/quiero_vender.html', _ctx_base(
        nav_active='vender',
    ))


@require_http_methods(['GET'])
def portal_quienes_somos(request):
    return render(request, 'portal/quienes_somos.html', _ctx_base(
        nav_active='quienes',
    ))


@login_required
@require_http_methods(['GET'])
def portal_consultas_staff(request):
    """Listado interno de leads del portal. Solo productor autorizado."""
    if not usuario_gestiona_portal_web(request.user):
        messages.error(request, 'No tenés permiso para ver las consultas web.')
        return redirect('inmobiliaria:dashboard')
    qs = ConsultaWeb.objects.select_related('propiedad', 'propiedad__sucursal')[:200]
    return render(request, 'portal/consultas_staff.html', {
        'consultas': qs,
    })
