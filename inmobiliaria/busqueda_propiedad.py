"""Búsqueda y orden de propiedades (caja, liquidaciones, gastos)."""
import re

from django.db.models import Q

from inmobiliaria.busqueda_persona import q_busqueda_persona

_PREFIJO_DEPTO_RE = re.compile(
    r'^(?:deptos?|dptos?|departamentos?|dep\.?)\s*([a-z0-9]{1,4})$',
    re.IGNORECASE,
)
_TOKEN_DEPTO_RE = re.compile(r'^[a-z0-9]{1,3}$', re.IGNORECASE)


def _normalizar_departamento(valor):
    v = (valor or '').strip().upper()
    return v or None


def parse_termino_busqueda_propiedad(termino):
    """
    Interpreta consultas como «deptos G», «Marbella G» o «Corrientes 1854».
    Devuelve dict con modo, departamento opcional y texto libre restante.
    """
    termino = (termino or '').strip()
    if not termino:
        return {'modo': 'vacio', 'departamento': None, 'texto_libre': ''}

    m_pref = _PREFIJO_DEPTO_RE.match(termino)
    if m_pref:
        return {
            'modo': 'depto',
            'departamento': _normalizar_departamento(m_pref.group(1)),
            'texto_libre': '',
        }

    if len(termino) == 1 and termino.isalpha():
        return {
            'modo': 'depto',
            'departamento': termino.upper(),
            'texto_libre': '',
        }

    partes = termino.split()
    if len(partes) >= 2 and _TOKEN_DEPTO_RE.match(partes[-1]):
        candidato = partes[-1]
        if len(candidato) <= 3:
            return {
                'modo': 'mixto',
                'departamento': _normalizar_departamento(candidato),
                'texto_libre': ' '.join(partes[:-1]).strip(),
            }

    return {'modo': 'general', 'departamento': None, 'texto_libre': termino}


def _q_texto_propiedad(texto):
    texto = (texto or '').strip()
    if not texto:
        return Q()
    q = (
        Q(direccion__icontains=texto)
        | Q(ubicacion__icontains=texto)
        | Q(titulo__icontains=texto)
        | Q(piso__icontains=texto)
        | Q(departamento__icontains=texto)
    )
    if texto.isascii() and texto.isdigit():
        try:
            q |= Q(numero_por_propietario=int(texto))
        except (TypeError, ValueError):
            pass
    return q


def _parece_busqueda_propietario(termino, parsed):
    if parsed['modo'] in ('depto', 'mixto'):
        return False
    texto = (parsed.get('texto_libre') or '').strip()
    if not texto:
        return False
    if ',' in texto:
        return True
    partes = texto.split()
    if len(partes) >= 2:
        return True
    if len(texto) == 1 and texto.isalpha():
        return False
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

    if modo == 'depto' and depto:
        return Q(departamento__iexact=depto)

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


def ordenar_propiedades(qs_or_list):
    """Ordena queryset o lista de Propiedad por dirección, piso y depto."""
    items = list(qs_or_list)
    items.sort(key=clave_orden_propiedad)
    return items


def limite_busqueda_propiedad(termino):
    """Más resultados cuando se buscan todos los deptos de una letra/edificio."""
    parsed = parse_termino_busqueda_propiedad(termino)
    if parsed['modo'] == 'depto':
        return 200
    if parsed['modo'] == 'mixto' and parsed.get('departamento'):
        return 120
    return 80
