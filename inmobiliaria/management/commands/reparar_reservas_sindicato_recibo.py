"""
Corrige reservas con recibo o sindicato que quedaron como «Reservado» sin seña.

Uso:
  python manage.py reparar_reservas_sindicato_recibo --dry-run
  python manage.py reparar_reservas_sindicato_recibo
  python manage.py reparar_reservas_sindicato_recibo --sucursal-id 1
"""
from django.core.management.base import BaseCommand

from inmobiliaria.caja_devolucion_deposito import sincronizar_senia_reserva_desde_movimientos
from inmobiliaria.models import HistorialDisponibilidad, Recibo, Reserva


class Command(BaseCommand):
    help = 'Sincroniza seña/estado desde recibos y alinea flag es_alquiler_sindicato desde historial'

    def add_arguments(self, parser):
        parser.add_argument('--sucursal-id', type=int, help='Limitar a una sucursal')
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo mostrar qué se actualizaría',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        sucursal_id = options.get('sucursal_id')

        reservas_qs = Reserva.objects.filter(eliminada=False)
        if sucursal_id:
            reservas_qs = reservas_qs.filter(sucursal_id=sucursal_id)

        ids_recibo = set(
            Recibo.objects.filter(reserva_id__in=reservas_qs.values('id'))
            .values_list('reserva_id', flat=True)
            .distinct()
        )
        ids_sindicato_hist = set(
            HistorialDisponibilidad.objects.filter(
                reserva_id__isnull=False,
                estado='alquiler_sindicato',
            )
            .values_list('reserva_id', flat=True)
            .distinct()
        )
        ids_objetivo = ids_recibo | ids_sindicato_hist

        if not ids_objetivo:
            self.stdout.write('No hay reservas con recibo ni historial sindicato.')
            return

        self.stdout.write(f'Reservas a revisar: {len(ids_objetivo)}')

        flag_actualizados = 0
        if ids_sindicato_hist and not dry_run:
            flag_actualizados = Reserva.objects.filter(
                id__in=ids_sindicato_hist,
                es_alquiler_sindicato=False,
            ).update(es_alquiler_sindicato=True)
        elif ids_sindicato_hist and dry_run:
            flag_actualizados = Reserva.objects.filter(
                id__in=ids_sindicato_hist,
                es_alquiler_sindicato=False,
            ).count()

        sync_count = 0
        for reserva in reservas_qs.filter(id__in=ids_objetivo).select_related('sucursal', 'propiedad'):
            antes = (reserva.estado, str(reserva.senia or 0))
            if dry_run:
                from inmobiliaria.caja_devolucion_deposito import total_senia_pagada_reserva

                total = total_senia_pagada_reserva(reserva)
                self.stdout.write(
                    f'  #{reserva.id}: estado={reserva.estado} senia={reserva.senia} '
                    f'→ cobrado detectado={total} sindicato={reserva.es_alquiler_sindicato}'
                )
                sync_count += 1
                continue
            total = sincronizar_senia_reserva_desde_movimientos(reserva)
            reserva.refresh_from_db(fields=['estado', 'senia', 'cuota_pendiente', 'es_alquiler_sindicato'])
            despues = (reserva.estado, str(reserva.senia or 0))
            if despues != antes or total > 0:
                self.stdout.write(
                    f'  #{reserva.id}: {antes[0]}/{antes[1]} → {despues[0]}/{despues[1]} '
                    f'(cobrado={total})'
                )
            sync_count += 1

        prefijo = '[dry-run] ' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(
                f'{prefijo}Listo: {sync_count} reserva(s) revisadas, '
                f'{flag_actualizados} flag(s) sindicato alineados.'
            )
        )
