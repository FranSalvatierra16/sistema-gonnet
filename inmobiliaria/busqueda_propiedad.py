"""Búsqueda y orden de propiedades (caja, liquidaciones, gastos)."""
import re
import unicodedata

from django.db.models import Q

from inmobiliaria.busqueda_persona import q_busqueda_persona

_PREFIJO_DEPTO_RE = re.compile(
    r'^(?:deptos?|dptos?|departamentos?|dep\.?)\s*([a-z0-9]{1,4})$',
    re.IGNORECASE,
)
# Depto típico: letra sola (G, F), o letra+dígito / dígito+letra (A1, 1A).
# NO 2 letras sueltas: «fe», «rio» forman calles («Santa Fe», «Entre Ríos»).
_TOKEN_DEPTO_RE = re.compile(r'^(?:[a-z]\d{0,2}|\d{1,2}[a-z])$', re.IGNORECASE)
_TOKEN_NUMERO_CALLE_RE = re.compile(r'^\d{2,6}[a-z]?$', re.IGNORECASE)
_SOLO_DIGITOS_RE = re.compile(r'\d+')

# Prefijos de calles compuestas: «santa fe», «san martín», «entre ríos»…
_PREFIJOS_CALLE_COMPUESTA = frozenset({
    'santa', 'san', 'entre', 'los', 'las', 'almirante', 'general',
    'pedro', 'hipolito', 'hipólito', 'avenida', 'av', 'avda', '3',
})
_CALLES_CONOCIDAS = frozenset({
    'santa fe', 'san martin', 'san martín', 'entre rios', 'entre ríos',
    'almirante brown', '3 de febrero', 'la costa', 'plaza mitre',
    'los troncos', 'playa grande', 'playa chica', 'punta mogotes',
})


def _normalizar_departamento(valor):
    v = (valor or '').strip().upper()
    return v or None


def _strip_accents(texto):
    texto = unicodedata.normalize('NFKD', texto or '')
    return ''.join(c for c in texto if not unicodedata.combining(c))


def _norm(texto):
    return _strip_accents((texto or '').strip().lower())


def parse_termino_busqueda_propiedad(termino):
    """
    Interpreta consultas como «deptos G», «Marbella G» o «Rivadavia 2476».
    Devuelve dict con modo, departamento/calle/número opcionales y texto libre.
    """
    termino = (termino or '').strip()
    if not termino:
        return {
            'modo': 'vacio',
            'departamento': None,
            'calle': None,
            'numero': None,
            'texto_libre': '',
        }

    m_pref = _PREFIJO_DEPTO_RE.match(termino)
    if m_pref:
        return {
            'modo': 'depto',
            'departamento': _normalizar_departamento(m_pref.group(1)),
            'calle': None,
            'numero': None,
            'texto_libre': '',
        }

    if len(termino) == 1 and termino.isalpha():
        return {
            'modo': 'depto',
            'departamento': termino.upper(),
            'calle': None,
            'numero': None,
            'texto_libre': '',
        }

    partes = termino.split()
    if len(partes) >= 2:
        ultimo = partes[-1]
        texto_norm = _norm(termino)
        # «Santa Fe», «San Martín», etc.: nunca tomar la última palabra como depto.
        es_calle_compuesta = (
            texto_norm in _CALLES_CONOCIDAS
            or any(c.startswith(texto_norm) for c in _CALLES_CONOCIDAS)
            or _norm(partes[0]) in _PREFIJOS_CALLE_COMPUESTA
        )
        # «Rivadavia 2476» / «Corrientes 1854»: calle + número (prioridad sobre depto).
        if _TOKEN_NUMERO_CALLE_RE.match(ultimo):
            return {
                'modo': 'calle_numero',
                'departamento': None,
                'calle': ' '.join(partes[:-1]).strip(),
                'numero': ultimo.upper(),
                'texto_libre': termino,
            }
        # «Marbella G» / «Torre 1A»: edificio + depto (una letra, no «fe»).
        if (
            not es_calle_compuesta
            and _TOKEN_DEPTO_RE.match(ultimo)
            and not ultimo.isdigit()
        ):
            return {
                'modo': 'mixto',
                'departamento': _normalizar_departamento(ultimo),
                'calle': None,
                'numero': None,
                'texto_libre': ' '.join(partes[:-1]).strip(),
            }

    return {
        'modo': 'general',
        'departamento': None,
        'calle': None,
        'numero': None,
        'texto_libre': termino,
    }


def _q_texto_propiedad(texto, *, priorizar_direccion=False):
    """
    Busca texto en campos de la ficha.
    Si priorizar_direccion=True, solo en dirección (para calle/número).
    """
    texto = (texto or '').strip()
    if not texto:
        return Q()
    if priorizar_direccion:
        return Q(direccion__icontains=texto)
    return (
        Q(direccion__icontains=texto)
        | Q(ubicacion__icontains=texto)
        | Q(titulo__icontains=texto)
        | Q(piso__icontains=texto)
        | Q(departamento__icontains=texto)
    )


def _q_calle_numero(calle, numero):
    """Calle y número deben aparecer en la dirección (no solo en ubicación)."""
    calle = (calle or '').strip()
    numero = (numero or '').strip()
    if not calle or not numero:
        return Q()
    # Match flexible del número: 2476, 2.476, N° 2476, etc. vía icontains del dígito.
    digitos = ''.join(_SOLO_DIGITOS_RE.findall(numero)) or numero
    q = Q(direccion__icontains=calle) & Q(direccion__icontains=digitos)
    # También el texto completo por si viene tal cual.
    q |= Q(direccion__icontains=f'{calle} {numero}')
    return q


def _parece_busqueda_propietario(termino, parsed):
    if parsed['modo'] in ('depto', 'mixto', 'calle_numero'):
        return False
    texto = (parsed.get('texto_libre') or '').strip()
    if not texto:
        return False
    if ',' in texto:
        return True
    texto_norm = _norm(texto)
    # Calles de dos palabras: no buscar propietario.
    if texto_norm in _CALLES_CONOCIDAS or any(c.startswith(texto_norm) for c in _CALLES_CONOCIDAS):
        return False
    partes = texto.split()
    if len(partes) >= 2 and _norm(partes[0]) in _PREFIJOS_CALLE_COMPUESTA:
        return False
    # Una sola palabra: apellido/nombre del propietario (ej. «Sacoa»).
    if len(partes) == 1:
        p = partes[0]
        if p.isdigit():
            return False
        return len(p) >= 3
    if len(partes) >= 2:
        return True
    return len(texto) >= 3


def q_busqueda_propiedad(termino):
    """Arma el Q de filtro para Propiedad según el término ingresado."""
    termino = (termino or '').strip()
    if not termino:
        return Q()

    if termino.isascii() and termino.isdigit():
        return Q(id=termino)

    parsed = parse_termino_busqueda_propiedad(termino)
    modo = parsed['modo']
    depto = parsed.get('departamento')
    texto = (parsed.get('texto_libre') or '').strip()
    calle = (parsed.get('calle') or '').strip()
    numero = (parsed.get('numero') or '').strip()

    if modo == 'depto' and depto:
        return Q(departamento__iexact=depto)

    if modo == 'calle_numero' and calle and numero:
        # Primero dirección; también ubicación por si la calle está ahí, pero exigiendo número en dirección.
        digitos = ''.join(_SOLO_DIGITOS_RE.findall(numero)) or numero
        return (
            _q_calle_numero(calle, numero)
            | (
                Q(ubicacion__icontains=calle)
                & Q(direccion__icontains=digitos)
            )
        )

    if modo == 'mixto':
        q = _q_texto_propiedad(texto)
        if depto:
            q &= Q(departamento__iexact=depto)
        return q

    q = _q_texto_propiedad(texto or termino)
    if _parece_busqueda_propietario(termino, parsed):
        q |= q_busqueda_persona(termino, incluir_id=False, prefix='propietario__')
        q |= Q(propietario__cuit__icontains=termino)
        q |= Q(propietario__email__icontains=termino)
    return q


def clave_orden_piso(piso):
    """Orden lógico de pisos: PB, 1, 2, 3… luego texto sin número."""
    s = (piso or '').strip().lower()
    if not s:
        return (1, 99999, '')
    if s in ('pb', 'planta baja', 'baja', '0', 'sótano', 'sotano'):
        return (0, 0, s)
    m = re.search(r'(\d+)', s)
    if m:
        return (0, int(m.group(1)), s)
    return (0, 50000, s)


def clave_orden_propiedad(propiedad):
    """Tupla para ordenar por dirección, piso y departamento."""
    direccion = (getattr(propiedad, 'direccion', None) or '').strip().lower()
    piso_key = clave_orden_piso(getattr(propiedad, 'piso', None))
    depto = (getattr(propiedad, 'departamento', None) or '').strip().lower()
    depto_num = re.search(r'(\d+)', depto)
    depto_key = (0, int(depto_num.group(1)), depto) if depto_num else (1, depto)
    prop_id = str(getattr(propiedad, 'id', '') or '')
    return (direccion, piso_key, depto_key, prop_id)


def _score_relevancia(propiedad, termino):
    """
    Menor = más relevante.
    Prioriza dirección sobre ubicación/título, y coincidencia al inicio de la calle.
    """
    parsed = parse_termino_busqueda_propiedad(termino)
    term = _norm(termino)
    calle = _norm(parsed.get('calle') or '')
    numero = _norm(parsed.get('numero') or '')
    texto = _norm(parsed.get('texto_libre') or termino)

    direccion = _norm(getattr(propiedad, 'direccion', None))
    ubicacion = _norm(getattr(propiedad, 'ubicacion', None))
    titulo = _norm(getattr(propiedad, 'titulo', None))

    digitos = ''.join(_SOLO_DIGITOS_RE.findall(numero)) if numero else ''
    busqueda_calle = calle or (texto if parsed['modo'] == 'general' else '')

    # 0: dirección empieza con la calle y (si hay) contiene el número
    if busqueda_calle and direccion.startswith(busqueda_calle):
        if not digitos or digitos in direccion:
            return (0, clave_orden_propiedad(propiedad))

    # 1: dirección contiene calle + número
    if busqueda_calle and digitos and busqueda_calle in direccion and digitos in direccion:
        return (1, clave_orden_propiedad(propiedad))

    # 2: dirección contiene el término o la calle
    if busqueda_calle and busqueda_calle in direccion:
        return (2, clave_orden_propiedad(propiedad))
    if term and term in direccion:
        return (2, clave_orden_propiedad(propiedad))

    # 3: título
    if busqueda_calle and busqueda_calle in titulo:
        return (3, clave_orden_propiedad(propiedad))

    # 4: solo ubicación (ej. «14 DE JULIO Y RIVADAVIA»)
    if busqueda_calle and busqueda_calle in ubicacion:
        return (4, clave_orden_propiedad(propiedad))
    if term and term in ubicacion:
        return (4, clave_orden_propiedad(propiedad))

    return (5, clave_orden_propiedad(propiedad))


def ordenar_propiedades(qs_or_list, termino=None):
    """
    Ordena queryset o lista de Propiedad.
    Si hay término de búsqueda, prioriza coincidencias en dirección.
    """
    items = list(qs_or_list)
    termino = (termino or '').strip()
    if termino:
        items.sort(key=lambda p: _score_relevancia(p, termino))
    else:
        items.sort(key=clave_orden_propiedad)
    return items


def limite_busqueda_propiedad(termino):
    """Más resultados cuando se buscan todos los deptos de una letra/edificio."""
    parsed = parse_termino_busqueda_propiedad(termino)
    if parsed['modo'] == 'depto':
        return 200
    if parsed['modo'] == 'mixto' and parsed.get('departamento'):
        return 120
    if parsed['modo'] == 'calle_numero':
        return 100
    return 80
