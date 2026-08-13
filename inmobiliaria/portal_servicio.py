"""
Búsqueda pública de alquiler temporario (Colón + Corrientes).
Reutiliza la lógica de disponibilidad/precios del backoffice; no crea reservas.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.db.models import Prefetch, Q

from inmobiliaria.busqueda_propiedades_reserva import (
    calcular_precio_total_reserva_fechas,
    cargar_contexto_bulk_busqueda,
    contrato_solapa_rango,
    mapa_precios_propiedad,
    periodo_cubierto_por_disponibilidad_forzada,
    periodo_cubierto_por_disponibilidades,
    reservas_solapan_rango,
)
from inmobiliaria.models import ImagenPropiedad, Precio, Propiedad
from inmobiliaria.models.propiedad import ESTADOS_RESERVA_OCUPAN_DISPONIBILIDAD
from inmobiliaria.precio_temporada_reserva import rango_vacaciones_invierno_sucursal


Q_SUCURSALES_PORTAL = (
    Q(sucursal__nombre__icontains='colon')
    | Q(sucursal__nombre__icontains='corrientes')
)


def parse_fecha_portal(s):
    if not s:
        return None
    st = str(s).strip()[:10]
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(st, fmt).date()
        except ValueError:
            continue
    return None


def qs_propiedades_portal():
    return (
        Propiedad.objects.filter(Q_SUCURSALES_PORTAL, publicar_web=True)
        .select_related('sucursal')
        .prefetch_related(
            Prefetch(
                'imagenes',
                queryset=ImagenPropiedad.objects.order_by('orden', 'id'),
                to_attr='fotos_ordenadas',
            ),
            Prefetch('precios', queryset=Precio.objects.all(), to_attr='todos_precios'),
        )
    )


def qs_destacadas_portal(limit=12):
    return qs_propiedades_portal().filter(destacada_web=True).order_by('id')[:limit]


def _vacaciones_invierno_sucursal(sucursal):
    return rango_vacaciones_invierno_sucursal(sucursal)

def buscar_temporario_portal(*, fecha_inicio, fecha_fin, ficha='', ambientes=None, limite=80):
    """
    Propiedades publicadas en Colón/Corrientes disponibles en el rango.
    Retorna lista de dicts: {propiedad, precio_total, noches, foto}.
    """
    if not fecha_inicio or not fecha_fin or fecha_fin <= fecha_inicio:
        return []

    qs = qs_propiedades_portal()
    if ficha:
        qs = qs.filter(id__icontains=str(ficha).strip())
    if ambientes:
        try:
            qs = qs.filter(ambientes=int(ambientes))
        except (TypeError, ValueError):
            pass

    props = list(qs[:400])
    if not props:
        return []

    ids = [p.id for p in props]
    ctx = cargar_contexto_bulk_busqueda(ids, fecha_inicio, fecha_fin)
    resultados = []
    noches = (fecha_fin - fecha_inicio).days

    for prop in props:
        disp = ctx['disp_por_prop'].get(prop.id, [])
        cubierto, _, _ = periodo_cubierto_por_disponibilidades(disp, fecha_inicio, fecha_fin)
        forzado, _, _ = periodo_cubierto_por_disponibilidad_forzada(disp, fecha_inicio, fecha_fin)
        if not cubierto and not forzado:
            continue

        if contrato_solapa_rango(ctx['contratos_por_prop'].get(prop.id, []), fecha_inicio, fecha_fin):
            continue

        reservas = ctx['reservas_por_prop'].get(prop.id, [])
        bloquean = [
            r
            for r in reservas_solapan_rango(reservas, fecha_inicio, fecha_fin)
            if (r.estado in ESTADOS_RESERVA_OCUPAN_DISPONIBILIDAD)
            and not getattr(r, 'es_alquiler_sindicato', False)
        ]
        if bloquean and not forzado:
            continue

        precios_map = mapa_precios_propiedad(prop)
        vac = _vacaciones_invierno_sucursal(getattr(prop, 'sucursal', None))
        precio = calcular_precio_total_reserva_fechas(
            fecha_inicio, fecha_fin, precios_map, vacaciones_invierno=vac
        )
        fotos = getattr(prop, 'fotos_ordenadas', None) or []
        foto = fotos[0] if fotos else None
        resultados.append({
            'propiedad': prop,
            'precio_total': precio or Decimal('0'),
            'noches': noches,
            'foto': foto,
            'sucursal_nombre': getattr(getattr(prop, 'sucursal', None), 'nombre', '') or '',
        })
        if len(resultados) >= limite:
            break

    resultados.sort(key=lambda r: (r['precio_total'] or Decimal('0'), r['propiedad'].id))
    return resultados


def titulo_publico_propiedad(prop):
    t = (getattr(prop, 'titulo', None) or '').strip()
    if t:
        return t
    partes = [(prop.direccion or '').strip()]
    if getattr(prop, 'piso', None):
        partes.append(f'Piso {prop.piso}')
    if getattr(prop, 'departamento', None):
        partes.append(f'Dpto {prop.departamento}')
    return ' · '.join(p for p in partes if p) or f'Ficha {prop.id}'
