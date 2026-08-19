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


def direccion_para_geocodificar(prop) -> str:
    partes = [
        (getattr(prop, 'direccion', None) or '').strip(),
        (getattr(prop, 'ubicacion', None) or '').strip(),
    ]
    texto = ', '.join(p for p in partes if p)
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
    key = google_maps_api_key()
    if key:
        params = urllib.parse.urlencode({'address': query, 'key': key, 'language': 'es'})
        url = f'https://maps.googleapis.com/maps/api/geocode/json?{params}'
        try:
            data = _http_json(url)
        except Exception:
            logger.exception('Google Geocoding falló')
            data = None
        if data and data.get('status') == 'OK' and data.get('results'):
            loc = data['results'][0].get('geometry', {}).get('location') or {}
            lat, lng = loc.get('lat'), loc.get('lng')
            if lat is not None and lng is not None:
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
        return _to_decimal(data[0].get('lat')), _to_decimal(data[0].get('lon'))
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
    """Separa pines del mismo edificio para que no se tapen."""
    h = abs(hash(str(prop_id))) % 17
    dlat = ((h % 5) - 2) * Decimal('0.00012')
    dlng = ((h // 5) - 1) * Decimal('0.00012')
    return float(Decimal(str(lat)) + dlat), float(Decimal(str(lng)) + dlng)


def markers_portal_resultados(resultados, request):
    qs = request.GET.urlencode()
    items = []
    for r in resultados:
        prop = r.get('propiedad')
        if not prop or not propiedad_tiene_coordenadas(prop):
            continue
        lat, lng = _jitter(prop.id, prop.latitud, prop.longitud)
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
        items.append({
            'id': str(prop.id),
            'titulo': r.get('titulo') or f'Ficha {prop.id}',
            'ubicacion': (r.get('ubicacion') or '')[:120],
            'lat': lat,
            'lng': lng,
            'precio': precio_txt or 'Consultar',
            'url': url,
            'foto': foto_url,
        })
    return items
