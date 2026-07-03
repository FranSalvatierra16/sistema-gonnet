"""
Repara el lote Marconi 18/07–02/08: pagadas en efectivo (recibo 25/06), sin sindicato.

  python manage.py desmarcar_sindicato_marconi --dry-run
  python manage.py desmarcar_sindicato_marconi
"""
from django.core.management.base import BaseCommand

from inmobiliaria.caja_devolucion_deposito import (
    RANGO_EXCLUIDO_SINDICATO_MARCONI,
    _cliente_es_marconi,
    reparar_reserva_lote_pago_efectivo_marconi,
)
from inmobiliaria.models import Reserva


class Command(BaseCommand):
    help = 'Marca pagadas (efectivo 25/06) las operaciones Marconi del 18/07 al 02/08/2026'

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

        reparadas = 0
        propiedades: set[int] = set()

        for reserva in sorted(reservas, key=lambda r: r.id):
            antes = (reserva.estado, str(reserva.senia or 0), reserva.es_alquiler_sindicato)
            if dry_run:
                self.stdout.write(
                    f'  #{reserva.id} {getattr(reserva.propiedad, "direccion", "?")}: '
                    f'{antes[0]}/seña={antes[1]}/sind={antes[2]} → pagada completa, recibo 25/06'
                )
                reparadas += 1
                continue

            if reparar_reserva_lote_pago_efectivo_marconi(reserva):
                reserva.refresh_from_db(fields=['estado', 'senia', 'es_alquiler_sindicato'])
                despues = (reserva.estado, str(reserva.senia or 0), reserva.es_alquiler_sindicato)
                self.stdout.write(
                    f'  #{reserva.id} {getattr(reserva.propiedad, "direccion", "?")}: '
                    f'{antes[0]}/{antes[1]}/sind={antes[2]} → '
                    f'{despues[0]}/{despues[1]}/sind={despues[2]}'
                )
                if reserva.propiedad_id:
                    propiedades.add(reserva.propiedad_id)
                reparadas += 1

        if not dry_run and propiedades:
            for pid in propiedades:
                primera = (
                    Reserva.objects.filter(propiedad_id=pid, eliminada=False)
                    .order_by('fecha_inicio')
                    .first()
                )
                if primera:
                    primera.reconstruir_historial_cronologico()

        prefijo = '[dry-run] ' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(f'{prefijo}Listo: {reparadas} operación(es) reparada(s).')
        )
