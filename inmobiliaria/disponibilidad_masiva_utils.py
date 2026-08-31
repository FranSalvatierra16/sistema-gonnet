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
        ids_previos = set(existente.propiedades.values_list('id', flat=True))
        ids_errores = {
            str(e.get('propiedad_id'))
            for e in (existente.detalle_errores or [])
            if e.get('propiedad_id')
        }
        todos_ids = set(props_validas) | ids_previos | ids_errores

        existente.fecha_inicio = fecha_inicio
        existente.fecha_fin = fecha_fin
        existente.cantidad_creadas = masiva['cantidad']
        existente.notas = notas
        existente.propiedades.set(list(todos_ids))
        existente.save(update_fields=['fecha_inicio', 'fecha_fin', 'cantidad_creadas', 'notas'])
        inferir_y_guardar_errores_lote(existente, Disponibilidad=Disponibilidad, Propiedad=Propiedad)
        n_errores = existente.cantidad_errores
        return {
            'ok': True,
            'mensaje': (
                f'Lote «{nombre}» actualizado — {len(todos_ids)} deptos en total, '
                f'{masiva["cantidad"]} con disponibilidad'
                + (f', {n_errores} con error' if n_errores else '')
                + f' ({fecha_inicio.strftime("%d/%m/%Y")} → {fecha_fin.strftime("%d/%m/%Y")}).'
            ),
            'lote_id': existente.pk,
            'creado': False,
            'actualizado': True,
            'deptos': len(todos_ids),
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


def sanitizar_errores_lote(errores_detallados):
    """Normaliza el detalle de errores para guardarlo en JSON."""
    resultado = []
    for e in errores_detallados or []:
        resultado.append({
            'propiedad_id': str(e.get('propiedad_id', '')),
            'direccion': e.get('direccion', '') or 'Desconocida',
            'piso': e.get('piso', '-') or '-',
            'departamento': e.get('departamento', '-') or '-',
            'error': e.get('error', 'Error desconocido'),
            'tipo': e.get('tipo', 'error_general'),
        })
    return resultado


def clasificar_propiedades_lote(lote, propiedades_qs, Disponibilidad=None):
    """
    Separa deptos exitosos y fallidos de un lote.
    Usa detalle_errores guardado; si falta, infiere por disponibilidad creada.
    """
    if Disponibilidad is None:
        from inmobiliaria.models import Disponibilidad as DispModel
        Disponibilidad = DispModel

    props_by_id = {str(p.id): p for p in propiedades_qs}
    errores_map = {
        str(e.get('propiedad_id')): e for e in (lote.detalle_errores or []) if e.get('propiedad_id')
    }

    exitosas = []
    fallidas = []
    vistos = set()

    for propiedad in propiedades_qs:
        pid = str(propiedad.id)
        vistos.add(pid)
        if pid in errores_map:
            fallidas.append({
                'propiedad': propiedad,
                'error': errores_map[pid].get('error', 'Error'),
            })
            continue
        tiene_disp = Disponibilidad.objects.filter(
            propiedad_id=propiedad.id,
            fecha_inicio=lote.fecha_inicio,
            fecha_fin=lote.fecha_fin,
        ).exists()
        if tiene_disp:
            exitosas.append(propiedad)
        else:
            fallidas.append({
                'propiedad': propiedad,
                'error': 'Sin disponibilidad creada para estas fechas',
            })

    for pid, err in errores_map.items():
        if pid in vistos:
            continue
        fallidas.append({
            'propiedad': props_by_id.get(pid),
            'propiedad_id': pid,
            'direccion': err.get('direccion', 'Desconocida'),
            'piso': err.get('piso', '-'),
            'departamento': err.get('departamento', '-'),
            'error': err.get('error', 'Error'),
        })

    return exitosas, fallidas


def inferir_y_guardar_errores_lote(lote, Disponibilidad=None, Propiedad=None):
    """Completa detalle_errores en lotes viejos sin detalle persistido."""
    if lote.detalle_errores:
        return lote.detalle_errores

    if Disponibilidad is None or Propiedad is None:
        from inmobiliaria.models import Disponibilidad as DispModel, Propiedad as PropModel
        Disponibilidad = DispModel
        Propiedad = PropModel

    _, fallidas = clasificar_propiedades_lote(
        lote, lote.propiedades.all(), Disponibilidad=Disponibilidad
    )
    if not fallidas:
        return []

    detalle = []
    for item in fallidas:
        p = item.get('propiedad')
        detalle.append({
            'propiedad_id': str(p.id) if p else item.get('propiedad_id', ''),
            'direccion': p.direccion if p else item.get('direccion', 'Desconocida'),
            'piso': (p.piso or '-') if p else item.get('piso', '-'),
            'departamento': (p.departamento or '-') if p else item.get('departamento', '-'),
            'error': item.get('error', 'Error'),
            'tipo': 'inferido',
        })

    lote.detalle_errores = detalle
    lote.cantidad_errores = len(detalle)
    lote.save(update_fields=['detalle_errores', 'cantidad_errores'])
    return detalle

