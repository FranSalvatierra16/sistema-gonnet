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
