"""
Geocodificación y marcadores del mapa del portal público.
Usa Google Geocoding si hay GOOGLE_MAPS_API_KEY; si no, Nominatim (OpenStreetMap).
"""
from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)

MAR_DEL_PLATA_LAT = -38.0055
MAR_DEL_PLATA_LNG = -57.5426
NOMINATIM_SLEEP_SEC = 1.1

# Centroides de zonas habituales (si todavía no hay geocodificación exacta).
ZONAS_MDP = (
    ('punta mogotes', (-38.0865, -57.5468)),
    ('playa grande', (-38.0168, -57.5332)),
    ('playa chica', (-38.0128, -57.5324)),
    ('stella maris', (-38.0189, -57.5315)),
    ('la perla', (-37.9992, -57.5418)),
    ('los troncos', (-38.0104, -57.5488)),
    ('güemes', (-38.0084, -57.5364)),
    ('guemes', (-38.0084, -57.5364)),
    ('plaza mitre', (-38.0024, -57.5466)),
    ('constitucion', (-38.0210, -57.5485)),
    ('constitución', (-38.0210, -57.5485)),
    ('alem', (-37.9918, -57.5482)),
    ('pueyrredon', (-38.0005, -57.5530)),
    ('pueyrredón', (-38.0005, -57.5530)),
    ('independencia', (-38.0048, -57.5440)),
    ('san martin', (-38.0028, -57.5455)),
    ('san martín', (-38.0028, -57.5455)),
    ('centro', (-37.9978, -57.5498)),
    ('gascón', (-38.0122, -57.5348)),
    ('gascon', (-38.0122, -57.5348)),
    ('luro', (-38.0032, -57.5485)),
    ('moreno', (-38.0056, -57.5472)),
    ('colon', (-38.0015, -57.5448)),
    ('colón', (-38.0015, -57.5448)),
    ('santa fe', (-38.0065, -57.5460)),
    ('chauspe', (-38.0250, -57.5500)),
    ('bosque', (-38.0080, -57.5550)),
    ('parque luro', (-38.0300, -57.5650)),
    ('san carlos', (-38.0400, -57.5550)),
    ('las americas', (-37.9800, -57.5450)),
    ('las américas', (-37.9800, -57.5450)),
)


def _en_tierra_mdp(lat, lng) -> bool:
    try:
        lat_f, lng_f = float(lat), float(lng)
    except (TypeError, ValueError):
        return False
    return -38.12 <= lat_f <= -37.93 and -57.64 <= lng_f <= -57.534


def google_maps_api_key():
    return (getattr(settings, 'GOOGLE_MAPS_API_KEY', '') or '').strip()


def _to_decimal(value):
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def propiedad_tiene_coordenadas(prop):
    return prop.latitud is not None and prop.longitud is not None


def coords_aproximadas_zona(texto):
    import re
    t = ' ' + (texto or '').strip().lower() + ' '
    t = (
        t.replace('á', 'a').replace('é', 'e').replace('í', 'i')
        .replace('ó', 'o').replace('ú', 'u')
    )
    mejor = None
    largo = 0
    for nombre, coords in ZONAS_MDP:
        n = nombre.lower().replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
        if re.search(r'(?:^|[^a-z0-9])' + re.escape(n) + r'(?:$|[^a-z0-9])', t) and len(n) >= largo:
            mejor = coords
            largo = len(n)
    return mejor


# Ejes calle→altura (OSM) para no confundir calles paralelas (Santa Fe ≠ Entre Ríos).
EJES_CALLE_MDP = {
    'santa fe': [
        (1500, -37.9984392, -57.5431471),
        (1700, -38.0004018, -57.5446813),
        (2000, -38.0027694, -57.5466145),
        (2200, -38.0044579, -57.5479372),
        (2500, -38.0067920, -57.5499710),
    ],
    'corrientes': [
        (1700, -38.0009060, -57.5437024),
        (2000, -38.0032733, -57.5456220),
        (2200, -38.0049484, -57.5469686),
        (2500, -38.0073340, -57.5488950),
    ],
    'entre rios': [
        (1700, -38.0014443, -57.5427232),
        (2000, -38.0038055, -57.5446116),
        (2200, -38.0054320, -57.5459527),
        (2500, -38.0078440, -57.5479940),
    ],
    'colon': [
        (1200, -38.0107255, -57.5361157),
        (1500, -38.0092007, -57.5391691),
        (1700, -38.0082395, -57.5410839),
        (2000, -38.0066797, -57.5441389),
        (2200, -38.0057017, -57.5460663),
        (2500, -38.0041949, -57.5490748),
    ],
    'gascon': [
        (1200, -38.0131260, -57.5381140),
        (1500, -38.0115940, -57.5411390),
        (1700, -38.0106431, -57.5430366),
        (2000, -38.0090770, -57.5461080),
        (2200, -38.0080630, -57.5481310),
        (2500, -38.0065610, -57.5510970),
    ],
    'mitre': [
        (1200, -37.9943396, -57.5454028),
        (1500, -37.9967315, -57.5473702),
        (1700, -37.9983736, -57.5488496),
        (2000, -38.0007585, -57.5506632),
        (2200, -38.0024121, -57.5519335),
        (2500, -38.0048470, -57.5539160),
    ],
    'almirante brown': [
        (1200, -38.0115642, -57.5368006),
        (1500, -38.0100950, -57.5399370),
        (1700, -38.0091120, -57.5418520),
        (2000, -38.0075590, -57.5448790),
        (2200, -38.0065473, -57.5467663),
        (2500, -38.0050040, -57.5498270),
    ],
    'luro': [
        (2200, -38.0008133, -57.5421639),
        (2500, -37.9993077, -57.5451388),
    ],
}


def _fold_txt(texto: str) -> str:
    t = (texto or '').lower()
    for a, b in (('á', 'a'), ('é', 'e'), ('í', 'i'), ('ó', 'o'), ('ú', 'u')):
        t = t.replace(a, b)
    return t


def coords_por_calle_altura(texto: str):
    """Si el texto es «Calle NNNN» conocida, interpola sobre el eje OSM."""
    import re
    t = _fold_txt(normalizar_direccion_mdp(texto))
    m = re.search(r'\b(\d{2,5})\b', t)
    if not m:
        return None
    numero = int(m.group(1))
    calle = None
    largo = 0
    for nombre in EJES_CALLE_MDP:
        if re.search(r'(?:^|[^a-z0-9])' + re.escape(nombre) + r'(?:$|[^a-z0-9])', t):
            if len(nombre) >= largo:
                calle = nombre
                largo = len(nombre)
    if not calle:
        return None
    eje = EJES_CALLE_MDP[calle]
    if numero <= eje[0][0]:
        return _to_decimal(eje[0][1]), _to_decimal(eje[0][2])
    if numero >= eje[-1][0]:
        return _to_decimal(eje[-1][1]), _to_decimal(eje[-1][2])
    for i in range(len(eje) - 1):
        a, b = eje[i], eje[i + 1]
        if a[0] <= numero <= b[0]:
            frac = (numero - a[0]) / (b[0] - a[0])
            lat = a[1] + (b[1] - a[1]) * frac
            lng = a[2] + (b[2] - a[2]) * frac
            return _to_decimal(lat), _to_decimal(lng)
    return None


def normalizar_direccion_mdp(texto: str) -> str:
    """«Corrientes al 2200 — Piso 3» → «Corrientes 2200»."""
    import re
    t = (texto or '').strip()
    if not t:
        return ''
    t = re.sub(r'\s*[-–—]\s*piso\s+\S+.*', '', t, flags=re.I)
    t = re.sub(r'\s*[-–—]\s*dpto\.?\s+\S+.*', '', t, flags=re.I)
    t = re.sub(r'\s*piso\s+\S+', '', t, flags=re.I)
    t = re.sub(r'\s*(dpto|depto|departamento)\.?\s+\S+', '', t, flags=re.I)
    t = re.sub(
        r'\b(?:al|n[°ºo.]?|nro\.?|num\.?|numero)\s*(\d{2,5})\b',
        r' \1 ',
        t,
        flags=re.I,
    )
    t = re.sub(r'\s+e\s+', ' y ', t, flags=re.I)
    return re.sub(r'\s+', ' ', t).strip()


def mejor_texto_direccion_prop(prop) -> str:
    direccion = normalizar_direccion_mdp(getattr(prop, 'direccion', None) or '')
    ubicacion = normalizar_direccion_mdp(getattr(prop, 'ubicacion', None) or '')
    if not direccion:
        return ubicacion
    if not ubicacion:
        return direccion
    import re
    dir_tiene_nro = bool(re.search(r'\b\d{2,5}\b', direccion))
    ubi_tiene_nro = bool(re.search(r'\b\d{2,5}\b', ubicacion))
    if ubi_tiene_nro and not dir_tiene_nro:
        return ubicacion
    if dir_tiene_nro:
        return direccion
    if ' y ' in ubicacion.lower() and ' y ' not in direccion.lower():
        return ubicacion
    return direccion


def direccion_para_geocodificar(prop) -> str:
    texto = mejor_texto_direccion_prop(prop)
    extra = 'Mar del Plata, Buenos Aires, Argentina'
    low = texto.lower()
    if 'mar del plata' not in low and 'mardelplata' not in low:
        texto = f'{texto}, {extra}' if texto else extra
    return texto


def _http_json(url, *, headers=None, timeout=12):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode('utf-8', errors='replace')
    return json.loads(raw)


def geocodificar_direccion(texto: str):
    query = (texto or '').strip()
    if not query:
        return None
    por_eje = coords_por_calle_altura(query)
    if por_eje and por_eje[0] is not None:
        return por_eje
    key = google_maps_api_key()
    if key:
        params = urllib.parse.urlencode({
            'address': query,
            'key': key,
            'language': 'es',
            'region': 'ar',
            'bounds': '-38.12,-57.64|-37.93,-57.534',
        })
        url = f'https://maps.googleapis.com/maps/api/geocode/json?{params}'
        try:
            data = _http_json(url)
        except Exception:
            logger.exception('Google Geocoding falló')
            data = None
        if data and data.get('status') == 'OK' and data.get('results'):
            loc = data['results'][0].get('geometry', {}).get('location') or {}
            lat, lng = loc.get('lat'), loc.get('lng')
            if lat is not None and lng is not None and _en_tierra_mdp(lat, lng):
                return _to_decimal(lat), _to_decimal(lng)
    encoded = urllib.parse.quote(query)
    url = (
        'https://nominatim.openstreetmap.org/search'
        f'?q={encoded}&format=json&limit=1&addressdetails=0'
    )
    try:
        data = _http_json(
            url,
            headers={
                'User-Agent': 'GonnetPropiedadesPortal/1.0 (busqueda-mapa)',
                'Accept-Language': 'es',
            },
        )
    except Exception:
        logger.exception('Nominatim falló')
        return None
    if isinstance(data, list) and data:
        lat, lng = data[0].get('lat'), data[0].get('lon')
        if _en_tierra_mdp(lat, lng):
            return _to_decimal(lat), _to_decimal(lng)
    return None


def actualizar_coordenadas_propiedad(prop, *, force=False, sleep_nominatim=False):
    """Completa lat/lng si faltan o si force=True. Devuelve True si guardó."""
    if not force and propiedad_tiene_coordenadas(prop):
        return False
    coords = geocodificar_direccion(direccion_para_geocodificar(prop))
    if sleep_nominatim and not google_maps_api_key():
        time.sleep(NOMINATIM_SLEEP_SEC)
    if not coords or coords[0] is None or coords[1] is None:
        return False
    prop.latitud, prop.longitud = coords
    prop.save(update_fields=['latitud', 'longitud'])
    return True


def _jitter(prop_id, lat, lng):
    """Separación mínima entre deptos del mismo edificio (no desplaza de cuadra)."""
    h = abs(hash(str(prop_id))) % 9
    dlat = ((h % 3) - 1) * Decimal('0.00004')
    dlng = ((h // 3) - 1) * Decimal('0.00004')
    return float(Decimal(str(lat)) + dlat), float(Decimal(str(lng)) + dlng)


def markers_portal_resultados(resultados, request):
    qs = request.GET.urlencode()
    items = []
    for r in resultados:
        prop = r.get('propiedad')
        if not prop:
            continue
        lat = lng = None
        if propiedad_tiene_coordenadas(prop):
            lat, lng = _jitter(prop.id, prop.latitud, prop.longitud)
        else:
            por_eje = coords_por_calle_altura(mejor_texto_direccion_prop(prop))
            if por_eje and por_eje[0] is not None:
                lat, lng = _jitter(prop.id, por_eje[0], por_eje[1])
            else:
                aprox = coords_aproximadas_zona(mejor_texto_direccion_prop(prop))
                if aprox:
                    lat, lng = _jitter(prop.id, aprox[0], aprox[1])
        url = reverse('inmobiliaria:portal_ficha', args=[prop.id])
        if qs:
            url = f'{url}?{qs}'
        precio = r.get('precio_total')
        precio_txt = ''
        if precio is not None:
            try:
                precio_txt = f'$ {int(round(float(precio))):,}'.replace(',', '.')
            except (TypeError, ValueError):
                precio_txt = ''
            label = (r.get('precio_label') or '').strip()
            if label:
                precio_txt = f'{precio_txt}{label}'
        fotos = r.get('fotos') or []
        foto_url = ''
        if fotos:
            try:
                foto_url = fotos[0].imagen.url
            except Exception:
                foto_url = ''
        texto_mapa = mejor_texto_direccion_prop(prop)
        items.append({
            'id': str(prop.id),
            'titulo': r.get('titulo') or f'Ficha {prop.id}',
            'ubicacion': (r.get('ubicacion') or '')[:120],
            'direccion': (getattr(prop, 'direccion', None) or '')[:120],
            'textoMapa': texto_mapa,
            'query': direccion_para_geocodificar(prop),
            'lat': lat,
            'lng': lng,
            'precio': precio_txt or 'Consultar',
            'url': url,
            'foto': foto_url,
        })
    return items


def completar_coordenadas_resultados(resultados, limite=12):
    """Geocodifica y guarda un lote de resultados sin pin, para no trabar la búsqueda."""
    hechos = 0
    for r in resultados:
        if hechos >= limite:
            break
        prop = r.get('propiedad')
        if not prop or propiedad_tiene_coordenadas(prop):
            continue
        try:
            if actualizar_coordenadas_propiedad(prop, force=False):
                hechos += 1
        except Exception:
            logger.exception('completar_coordenadas_resultados ficha=%s', getattr(prop, 'id', ''))
    return hechos
