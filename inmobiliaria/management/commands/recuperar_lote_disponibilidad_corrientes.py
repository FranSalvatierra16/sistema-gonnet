"""Recupera la última disponibilidad masiva de Corrientes y la guarda en el historial."""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Max

from inmobiliaria.models import Disponibilidad, LoteDisponibilidadMasiva, Propiedad, Sucursal


def _detectar_ultima_masiva_corrientes(sucursal, min_deptos=10):
    """
    Agrupa disponibilidades manuales por rango de fechas y devuelve el lote
    con más departamentos (desempate: ID de disponibilidad más alto = más reciente).
    """
    filas = (
        Disponibilidad.objects.filter(
            propiedad__sucursal=sucursal,
            es_manual=True,
        )
        .values('fecha_inicio', 'fecha_fin', 'propiedad_id')
        .annotate(max_disp_id=Max('id'))
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

    fi, ff, prop_ids, max_disp_id = max(
        candidatos,
        key=lambda x: (len(x[2]), x[3]),
    )
    return {
        'fecha_inicio_origen': fi,
        'fecha_fin_origen': ff,
        'propiedad_ids': sorted(prop_ids),
        'cantidad': len(prop_ids),
        'max_disp_id': max_disp_id,
    }


def _fechas_verano_2027(fi_origen, ff_origen):
    """Misma ventana estacional que la masiva detectada, desplazada al verano 2027."""
    delta = 2027 - ff_origen.year
    return (
        fi_origen.replace(year=fi_origen.year + delta),
        ff_origen.replace(year=ff_origen.year + delta),
    )


class Command(BaseCommand):
    help = (
        'Detecta la última carga masiva de disponibilidades en Corrientes '
        'y la registra en LoteDisponibilidadMasiva (historial).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--nombre',
            default='Verano 2027',
            help='Nombre del lote en el historial (default: Verano 2027).',
        )
        parser.add_argument(
            '--min-deptos',
            type=int,
            default=10,
            help='Mínimo de departamentos para considerar una carga masiva.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo muestra qué se crearía, sin guardar.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Crear aunque ya exista un lote con el mismo nombre en Corrientes.',
        )

    def handle(self, *args, **options):
        nombre = (options['nombre'] or '').strip()[:200]
        if not nombre:
            self.stderr.write(self.style.ERROR('El nombre del lote no puede estar vacío.'))
            return

        sucursal = Sucursal.objects.filter(nombre__icontains='corrientes').first()
        if not sucursal:
            self.stderr.write(self.style.ERROR('No se encontró la sucursal Corrientes.'))
            return

        if not options['force']:
            existente = LoteDisponibilidadMasiva.objects.filter(
                sucursal=sucursal,
                nombre=nombre,
            ).first()
            if existente:
                self.stdout.write(
                    self.style.WARNING(
                        f'Ya existe el lote «{nombre}» (#{existente.pk}) '
                        f'({existente.fecha_inicio} → {existente.fecha_fin}). '
                        f'Usá --force para crear otro igual.'
                    )
                )
                return

        masiva = _detectar_ultima_masiva_corrientes(sucursal, min_deptos=options['min_deptos'])
        if not masiva:
            self.stderr.write(
                self.style.ERROR(
                    f'No se encontró ninguna masiva con al menos {options["min_deptos"]} '
                    f'departamentos en Corrientes.'
                )
            )
            return

        fi_origen = masiva['fecha_inicio_origen']
        ff_origen = masiva['fecha_fin_origen']
        fecha_inicio, fecha_fin = _fechas_verano_2027(fi_origen, ff_origen)

        prop_ids = masiva['propiedad_ids']
        props_validas = list(
            Propiedad.objects.filter(id__in=prop_ids, sucursal=sucursal).values_list('id', flat=True)
        )
        faltantes = len(prop_ids) - len(props_validas)

        self.stdout.write(f'Sucursal: {sucursal.nombre} (id={sucursal.pk})')
        self.stdout.write(
            f'Masiva detectada: {fi_origen} → {ff_origen} — '
            f'{masiva["cantidad"]} deptos (max disp id={masiva["max_disp_id"]})'
        )
        self.stdout.write(
            f'Lote a crear: «{nombre}» — {fecha_inicio} → {fecha_fin} — '
            f'{len(props_validas)} deptos'
        )
        if faltantes:
            self.stdout.write(
                self.style.WARNING(f'{faltantes} propiedad(es) del grupo ya no están en Corrientes.')
            )

        if options['dry_run']:
            self.stdout.write(self.style.NOTICE('Dry-run: no se guardó nada.'))
            return

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

        self.stdout.write(
            self.style.SUCCESS(
                f'Lote «{nombre}» creado (#{lote.pk}) con {len(props_validas)} departamentos.'
            )
        )
