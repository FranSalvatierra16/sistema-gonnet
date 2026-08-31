"""Utilidades compartidas para lotes de disponibilidad masiva."""
from collections import defaultdict
from datetime import date

from django.db.models import Max

# Última masiva de Corrientes: disponibilidades con inicio desde esta fecha.
FECHA_INICIO_MASIVA_CORRIENTES = date(2026, 12, 15)


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


def detectar_ultima_masiva(
    sucursal,
    Disponibilidad,
    min_deptos=5,
    solo_manual=False,
    fecha_inicio_desde=None,
):
    """
    Agrupa disponibilidades por rango de fechas y devuelve el grupo más grande
    (desempate: ID de disponibilidad más alto = más reciente).
    """
    qs = Disponibilidad.objects.filter(propiedad__sucursal=sucursal)
    if solo_manual:
        qs = qs.filter(es_manual=True)
    if fecha_inicio_desde:
        qs = qs.filter(fecha_inicio__gte=fecha_inicio_desde)

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
        'fecha_inicio': fi,
        'fecha_fin': ff,
        'propiedad_ids': sorted(prop_ids, key=str),
        'cantidad': len(prop_ids),
        'max_disp_id': max_disp_id,
    }


def _buscar_masiva_corrientes(sucursal, Disponibilidad, min_deptos=5, fecha_inicio_desde=None):
    """Detecta la masiva; si no hay desde la fecha pedida, prueba sin filtro de fecha."""
    if fecha_inicio_desde is None:
        fecha_inicio_desde = FECHA_INICIO_MASIVA_CORRIENTES

    for solo_manual in (True, False):
        masiva = detectar_ultima_masiva(
            sucursal,
            Disponibilidad,
            min_deptos=min_deptos,
            solo_manual=solo_manual,
            fecha_inicio_desde=fecha_inicio_desde,
        )
        if masiva:
            return masiva

    if fecha_inicio_desde is not None:
        for solo_manual in (True, False):
            masiva = detectar_ultima_masiva(
                sucursal,
                Disponibilidad,
                min_deptos=min_deptos,
                solo_manual=solo_manual,
                fecha_inicio_desde=None,
            )
            if masiva:
                return masiva
    return None


def recuperar_ultima_masiva_corrientes(
    nombre='Verano 2027',
    min_deptos=5,
    force=False,
    actualizar_si_existe=True,
    apps=None,
    sucursal=None,
    fecha_inicio_desde=None,
):
    """
    Detecta la última masiva en Corrientes (desde 15/12/2026) y guarda/actualiza el lote.
    Usa las fechas reales detectadas en la base.
    """
    Sucursal, Disponibilidad, Propiedad, LoteDisponibilidadMasiva = _modelos(apps)

    if sucursal is None:
        sucursal = Sucursal.objects.filter(nombre__icontains='corrientes').first()
    if not sucursal:
        return {'ok': False, 'mensaje': 'No se encontró la sucursal Corrientes.'}

    if fecha_inicio_desde is None:
        fecha_inicio_desde = FECHA_INICIO_MASIVA_CORRIENTES

    existente = LoteDisponibilidadMasiva.objects.filter(
        sucursal=sucursal, nombre=nombre
    ).first()
    if existente and not force and not actualizar_si_existe:
        return {
            'ok': True,
            'mensaje': f'El lote «{nombre}» ya existía (#{existente.pk}).',
            'lote_id': existente.pk,
            'creado': False,
        }

    masiva = _buscar_masiva_corrientes(
        sucursal, Disponibilidad, min_deptos=min_deptos, fecha_inicio_desde=fecha_inicio_desde
    )
    if not masiva:
        return {
            'ok': False,
            'mensaje': (
                f'No se encontró ninguna carga masiva desde {fecha_inicio_desde.strftime("%d/%m/%Y")} '
                f'con al menos {min_deptos} departamentos en Corrientes.'
            ),
        }

    fecha_inicio = masiva['fecha_inicio']
    fecha_fin = masiva['fecha_fin']
    prop_ids = masiva['propiedad_ids']
    props_validas = list(
        Propiedad.objects.filter(id__in=prop_ids, sucursal=sucursal).values_list('id', flat=True)
    )
    notas = (
        f'Recuperado automáticamente ({masiva["cantidad"]} deptos, '
        f'disp max id={masiva["max_disp_id"]}).'
    )

    if existente and not force:
        existente.fecha_inicio = fecha_inicio
        existente.fecha_fin = fecha_fin
        existente.cantidad_creadas = masiva['cantidad']
        existente.notas = notas
        existente.save(update_fields=['fecha_inicio', 'fecha_fin', 'cantidad_creadas', 'notas'])
        if props_validas:
            existente.propiedades.set(props_validas)
        return {
            'ok': True,
            'mensaje': (
                f'Lote «{nombre}» actualizado — {len(props_validas)} deptos, '
                f'{fecha_inicio.strftime("%d/%m/%Y")} → {fecha_fin.strftime("%d/%m/%Y")}.'
            ),
            'lote_id': existente.pk,
            'creado': False,
            'actualizado': True,
            'deptos': len(props_validas),
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
        }

    if existente and force:
        existente.delete()

    lote = LoteDisponibilidadMasiva.objects.create(
        sucursal=sucursal,
        nombre=nombre,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        cantidad_creadas=masiva['cantidad'],
        cantidad_errores=0,
        notas=notas,
    )
    if props_validas:
        lote.propiedades.set(props_validas)

    return {
        'ok': True,
        'mensaje': (
            f'Lote «{nombre}» creado con {len(props_validas)} departamentos '
            f'({fecha_inicio.strftime("%d/%m/%Y")} → {fecha_fin.strftime("%d/%m/%Y")}).'
        ),
        'lote_id': lote.pk,
        'creado': True,
        'deptos': len(props_validas),
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
    }


# Alias retrocompatible
recuperar_lote_corrientes_verano_2027 = recuperar_ultima_masiva_corrientes
