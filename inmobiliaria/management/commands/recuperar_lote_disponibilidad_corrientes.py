"""Recupera la última disponibilidad masiva de Corrientes y la guarda en el historial."""
from django.core.management.base import BaseCommand

from inmobiliaria.disponibilidad_masiva_utils import (
    FECHA_INICIO_MASIVA_CORRIENTES,
    _modelos,
    _buscar_masiva_corrientes,
    recuperar_ultima_masiva_corrientes,
)


class Command(BaseCommand):
    help = (
        'Detecta la última carga masiva de disponibilidades en Corrientes '
        '(desde 15/12/2026) y la registra en LoteDisponibilidadMasiva.'
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
            default=5,
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
            help='Recrear aunque ya exista un lote con el mismo nombre.',
        )

    def handle(self, *args, **options):
        nombre = (options['nombre'] or '').strip()[:200]
        if not nombre:
            self.stderr.write(self.style.ERROR('El nombre del lote no puede estar vacío.'))
            return

        if options['dry_run']:
            _, Disponibilidad, _, _ = _modelos()
            Sucursal, _, _, _ = _modelos()
            sucursal = Sucursal.objects.filter(nombre__icontains='corrientes').first()
            if not sucursal:
                self.stderr.write(self.style.ERROR('No se encontró Corrientes.'))
                return
            masiva = _buscar_masiva_corrientes(
                sucursal, Disponibilidad, min_deptos=options['min_deptos']
            )
            if not masiva:
                self.stderr.write(self.style.ERROR('No se detectó ninguna masiva.'))
                return
            self.stdout.write(
                f'Dry-run: «{nombre}» {masiva["fecha_inicio"]} → {masiva["fecha_fin"]}, '
                f'{masiva["cantidad"]} deptos (desde {FECHA_INICIO_MASIVA_CORRIENTES})'
            )
            return

        result = recuperar_ultima_masiva_corrientes(
            nombre=nombre,
            min_deptos=options['min_deptos'],
            force=options['force'],
            actualizar_si_existe=not options['force'],
        )
        if result['ok']:
            self.stdout.write(self.style.SUCCESS(result['mensaje']))
        else:
            self.stderr.write(self.style.ERROR(result['mensaje']))
