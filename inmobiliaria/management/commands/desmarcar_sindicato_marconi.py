"""
Quita la marca de alquiler sindicato a operaciones Marconi del rango 18/07–02/08/2026.

  python manage.py desmarcar_sindicato_marconi --dry-run
  python manage.py desmarcar_sindicato_marconi
"""
from django.core.management.base import BaseCommand

from inmobiliaria.caja_devolucion_deposito import (
    RANGO_EXCLUIDO_SINDICATO_MARCONI,
    _cliente_es_marconi,
    sincronizar_senia_reserva_desde_movimientos,
)
from inmobiliaria.models import Reserva


class Command(BaseCommand):
    help = 'Desmarca como sindicato las operaciones Marconi del 18/07 al 02/08/2026'

    def add_arguments(self, parser):
        parser.add_argument('--sucursal-id', type=int, help='Limitar a una sucursal')
        parser.add_argument('--dry-run', action='store_true', help='Solo mostrar cambios')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        sucursal_id = options.get('sucursal_id')
        fi, ff = RANGO_EXCLUIDO_SINDICATO_MARCONI

        qs = Reserva.objects.filter(
            eliminada=False,
            fecha_inicio=fi,
            fecha_fin=ff,
        ).select_related('propiedad', 'cliente', 'sucursal')
        if sucursal_id:
            qs = qs.filter(sucursal_id=sucursal_id)

        reservas = [r for r in qs if _cliente_es_marconi(r)]
        if not reservas:
            self.stdout.write('No se encontraron reservas Marconi en ese rango de fechas.')
            return

        self.stdout.write(
            f'Rango {fi.strftime("%d/%m/%Y")}–{ff.strftime("%d/%m/%Y")}: '
            f'{len(reservas)} reserva(s) Marconi'
        )

        cambiadas = 0
        propiedades: set[int] = set()

        for reserva in sorted(reservas, key=lambda r: r.id):
            antes = reserva.es_alquiler_sindicato
            if dry_run:
                self.stdout.write(
                    f'  #{reserva.id} {getattr(reserva.propiedad, "direccion", "?")}: '
                    f'sindicato={antes} → False'
                )
                cambiadas += 1
                continue

            if reserva.es_alquiler_sindicato:
                reserva.es_alquiler_sindicato = False
                reserva.save(update_fields=['es_alquiler_sindicato'])
            sincronizar_senia_reserva_desde_movimientos(reserva)
            reserva.reconstruir_historial_cronologico()
            if reserva.propiedad_id:
                propiedades.add(reserva.propiedad_id)
            if antes:
                self.stdout.write(
                    f'  #{reserva.id} {getattr(reserva.propiedad, "direccion", "?")}: '
                    f'desmarcada (estado={reserva.estado}, seña={reserva.senia})'
                )
                cambiadas += 1

        prefijo = '[dry-run] ' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(f'{prefijo}Listo: {cambiadas} operación(es) desmarcada(s).')
        )
