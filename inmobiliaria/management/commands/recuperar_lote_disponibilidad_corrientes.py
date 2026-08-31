"""Recupera la última disponibilidad masiva de Corrientes y la guarda en el historial."""
from django.core.management.base import BaseCommand

from inmobiliaria.disponibilidad_masiva_utils import recuperar_lote_corrientes_verano_2027


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
            help='Crear aunque ya exista un lote con el mismo nombre en Corrientes.',
        )

    def handle(self, *args, **options):
        nombre = (options['nombre'] or '').strip()[:200]
        if not nombre:
            self.stderr.write(self.style.ERROR('El nombre del lote no puede estar vacío.'))
            return

        if options['dry_run']:
            from inmobiliaria.disponibilidad_masiva_utils import (
                _modelos,
                detectar_ultima_masiva,
                fechas_verano_2027,
            )

            _, Disponibilidad, Propiedad, LoteDisponibilidadMasiva = _modelos()
            Sucursal, _, _, _ = _modelos()
            sucursal = Sucursal.objects.filter(nombre__icontains='corrientes').first()
            if not sucursal:
                self.stderr.write(self.style.ERROR('No se encontró Corrientes.'))
                return
            masiva = detectar_ultima_masiva(
                sucursal, Disponibilidad, min_deptos=options['min_deptos'], solo_manual=True
            ) or detectar_ultima_masiva(
                sucursal, Disponibilidad, min_deptos=options['min_deptos'], solo_manual=False
            )
            if not masiva:
                self.stderr.write(self.style.ERROR('No se detectó ninguna masiva.'))
                return
            fi, ff = fechas_verano_2027(masiva['fecha_inicio_origen'], masiva['fecha_fin_origen'])
            self.stdout.write(
                f'Dry-run: «{nombre}» {fi} → {ff}, {masiva["cantidad"]} deptos '
                f'(origen {masiva["fecha_inicio_origen"]} → {masiva["fecha_fin_origen"]})'
            )
            return

        result = recuperar_lote_corrientes_verano_2027(
            nombre=nombre,
            min_deptos=options['min_deptos'],
            force=options['force'],
        )
        if result['ok']:
            self.stdout.write(self.style.SUCCESS(result['mensaje']))
        else:
            self.stderr.write(self.style.ERROR(result['mensaje']))
