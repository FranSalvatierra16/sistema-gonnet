"""
Catálogo de conceptos de caja compartido entre sucursales.

- Globales (sucursal nula).
- Sucursal de referencia (nombre contiene «Corrientes»), como lista maestra común.
- Además, los conceptos dados de alta en la sucursal del usuario (p. ej. «90 - Vale»
  en Sucursal Prueba), para que sigan apareciendo en búsqueda y movimientos.

Si no hay sucursal de referencia, solo globales + sucursal actual.
"""
from django.db.models import Q

from .models.sucursal import Sucursal


def get_sucursal_referencia_catalogo_conceptos_caja():
    """Sucursal cuyos conceptos se usan como lista maestra para el resto."""
    return Sucursal.objects.filter(nombre__icontains='corrientes').order_by('pk').first()


def q_conceptos_caja_visibles(sucursal_actual):
    """
    Condición ORM para listar/validar conceptos de caja desde cualquier sucursal.
    """
    ref = get_sucursal_referencia_catalogo_conceptos_caja()
    sid = getattr(sucursal_actual, 'pk', None)
    if ref and sid:
        return (
            Q(sucursal__isnull=True)
            | Q(sucursal_id=ref.pk)
            | Q(sucursal_id=sid)
        )
    if ref and not sid:
        return Q(sucursal__isnull=True) | Q(sucursal_id=ref.pk)
    if sid is None:
        return Q(pk__isnull=False)
    return Q(sucursal__isnull=True) | Q(sucursal_id=sid)


def sucursal_destino_nuevo_concepto_caja(sucursal_actual):
    """FK sucursal al crear conceptos nuevos: la de referencia si existe, si no la del usuario."""
    return get_sucursal_referencia_catalogo_conceptos_caja() or sucursal_actual


def proximo_id_numerico_libre_concepto_caja():
    """
    Menor entero positivo no usado como id numérico de concepto (1, 2, 3…).
    El id es PK global: cuenta todos los conceptos de todas las sucursales.
    Ignora ids alfabéticos (ej. RE).
    """
    from .models.caja import Concepto

    usados = set()
    for cid in Concepto.objects.values_list('id', flat=True):
        s = str(cid or '').strip()
        if s.isdigit():
            usados.add(int(s))
    n = 1
    while n in usados:
        n += 1
    return str(n)


def proximo_id_numerico_libre_catalogo_visible(sucursal_actual):
    """
    Menor entero que no aparece en el catálogo visible del usuario (solo referencia visual).
    Puede ser menor que proximo_id_numerico_libre_concepto_caja() si hay ids en otras sucursales.
    """
    from .models.caja import Concepto

    usados = set()
    for cid in Concepto.objects.filter(q_conceptos_caja_visibles(sucursal_actual)).values_list('id', flat=True):
        s = str(cid or '').strip()
        if s.isdigit():
            usados.add(int(s))
    n = 1
    while n in usados:
        n += 1
    return str(n)


CONCEPTO_PAGO_LIQUIDACION_ID = '1'


def concepto_pago_liquidacion_catalogo(sucursal):
    """Concepto 1 (Pago liquidacion) para egresos de liquidación a propietario."""
    from .models.caja import Concepto

    cat = Concepto.objects.filter(
        q_conceptos_caja_visibles(sucursal),
        id=CONCEPTO_PAGO_LIQUIDACION_ID,
    ).first()
    if cat:
        return {'id': str(cat.id), 'nombre': cat.nombre or 'Pago liquidacion'}
    cat = (
        Concepto.objects.filter(q_conceptos_caja_visibles(sucursal))
        .filter(
            Q(nombre__icontains='pago liquidacion')
            | Q(nombre__icontains='pago liquidación')
        )
        .first()
    )
    if cat:
        return {'id': str(cat.id), 'nombre': cat.nombre or ''}
    return {'id': CONCEPTO_PAGO_LIQUIDACION_ID, 'nombre': 'Pago liquidacion'}
