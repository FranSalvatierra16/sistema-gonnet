"""Utilidades compartidas para lotes de disponibilidad masiva."""
from collections import defaultdict

from django.db.models import Max


def _modelos(apps=None):
    if apps:
        return (
            apps.get_model('inmobiliaria', 'Sucursal'),
            apps.get_model('inmobiliaria', 'Disponibilidad'),
            apps.get_model('inmobiliaria', 'Propiedad'),
            apps.get_model('inmobiliaria', 'LoteDisponibilidadMasiva'),
        )
    from inmobiliaria.models import Disponibilidad, LoteDisponibilidadMasiva, Propiedad, Sucursal

    return Sucursal, Disponibilidad, Propiedad, LoteDisponibilidadMasiva


def detectar_ultima_masiva(sucursal, Disponibilidad, min_deptos=5, solo_manual=False):
    """
    Agrupa disponibilidades por rango de fechas y devuelve el grupo más grande
    (desempate: ID de disponibilidad más alto).
    """
    qs = Disponibilidad.objects.filter(propiedad__sucursal=sucursal)
    if solo_manual:
        qs = qs.filter(es_manual=True)

    filas = qs.values('fecha_inicio', 'fecha_fin', 'propiedad_id').annotate(
        max_disp_id=Max('id')
    )

    grupos = defaultdict(lambda: {'prop_ids': set(), 'max_disp_id': 0})
    for fila in filas:
        key = (fila['fecha_inicio'], fila['fecha_fin'])
        g = grupos[key]
        g['prop_ids'].add(fila['propiedad_id'])
        g['max_disp_id'] = max(g['max_disp_id'], fila['max_disp_id'])

    candidatos = [
        (fi, ff, g['prop_ids'], g['max_disp_id'])
        for (fi, ff), g in grupos.items()
        if len(g['prop_ids']) >= min_deptos
    ]
    if not candidatos:
        return None

    fi, ff, prop_ids, max_disp_id = max(candidatos, key=lambda x: (len(x[2]), x[3]))
    return {
        'fecha_inicio_origen': fi,
        'fecha_fin_origen': ff,
        'propiedad_ids': sorted(prop_ids, key=str),
        'cantidad': len(prop_ids),
        'max_disp_id': max_disp_id,
    }


def fechas_verano_2027(fi_origen, ff_origen):
    """Misma ventana estacional desplazada al verano 2027."""
    delta = 2027 - ff_origen.year
    return (
        fi_origen.replace(year=fi_origen.year + delta),
        ff_origen.replace(year=ff_origen.year + delta),
    )


def recuperar_lote_corrientes_verano_2027(
    nombre='Verano 2027',
    min_deptos=5,
    force=False,
    apps=None,
    sucursal=None,
):
    """
    Detecta la última masiva en Corrientes y crea el lote en el historial.
    Devuelve dict con ok, mensaje y lote_id (si se creó).
    """
    Sucursal, Disponibilidad, Propiedad, LoteDisponibilidadMasiva = _modelos(apps)

    if sucursal is None:
        sucursal = Sucursal.objects.filter(nombre__icontains='corrientes').first()
    if not sucursal:
        return {'ok': False, 'mensaje': 'No se encontró la sucursal Corrientes.'}

    if not force and LoteDisponibilidadMasiva.objects.filter(
        sucursal=sucursal, nombre=nombre
    ).exists():
        existente = LoteDisponibilidadMasiva.objects.filter(
            sucursal=sucursal, nombre=nombre
        ).first()
        return {
            'ok': True,
            'mensaje': f'El lote «{nombre}» ya existía (#{existente.pk}).',
            'lote_id': existente.pk,
            'creado': False,
        }

    masiva = detectar_ultima_masiva(
        sucursal, Disponibilidad, min_deptos=min_deptos, solo_manual=True
    )
    if not masiva:
        masiva = detectar_ultima_masiva(
            sucursal, Disponibilidad, min_deptos=min_deptos, solo_manual=False
        )
    if not masiva:
        return {
            'ok': False,
            'mensaje': (
                f'No se encontró ninguna carga masiva con al menos {min_deptos} '
                f'departamentos en Corrientes.'
            ),
        }

    fi_origen = masiva['fecha_inicio_origen']
    ff_origen = masiva['fecha_fin_origen']
    fecha_inicio, fecha_fin = fechas_verano_2027(fi_origen, ff_origen)

    prop_ids = masiva['propiedad_ids']
    props_validas = list(
        Propiedad.objects.filter(id__in=prop_ids, sucursal=sucursal).values_list('id', flat=True)
    )

    lote = LoteDisponibilidadMasiva.objects.create(
        sucursal=sucursal,
        nombre=nombre,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        cantidad_creadas=masiva['cantidad'],
        cantidad_errores=0,
        notas=(
            f'Recuperado automáticamente desde la última masiva detectada '
            f'({fi_origen} → {ff_origen}, {masiva["cantidad"]} deptos).'
        ),
    )
    if props_validas:
        lote.propiedades.set(props_validas)

    return {
        'ok': True,
        'mensaje': (
            f'Lote «{nombre}» creado con {len(props_validas)} departamentos '
            f'({fecha_inicio} → {fecha_fin}).'
        ),
        'lote_id': lote.pk,
        'creado': True,
        'deptos': len(props_validas),
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
    }
