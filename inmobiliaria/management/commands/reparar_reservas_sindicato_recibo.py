"""
Corrige reservas sindicato con cobro en caja/recibo que quedaron como «Reservado».

Uso general:
  python manage.py reparar_reservas_sindicato_recibo --dry-run
  python manage.py reparar_reservas_sindicato_recibo

Lote 18/07 → 02/08 cobrado el 25/06 (sindicato Marconi):
  python manage.py reparar_reservas_sindicato_recibo \\
    --fecha-inicio 2026-07-18 --fecha-fin 2026-08-02 \\
    --fecha-pago 2026-06-25 --marcar-sindicato --dry-run
  python manage.py reparar_reservas_sindicato_recibo \\
    --fecha-inicio 2026-07-18 --fecha-fin 2026-08-02 \\
    --fecha-pago 2026-06-25 --marcar-sindicato
"""
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand

from inmobiliaria.caja_devolucion_deposito import (
    sincronizar_senia_reserva_desde_movimientos,
    total_senia_pagada_reserva,
)
from inmobiliaria.models import HistorialDisponibilidad, Recibo, Reserva


def _parse_date(raw: str | None):
    if not raw:
        return None
    return datetime.strptime(raw.strip(), '%Y-%m-%d').date()


def _realinear_recibo_propiedad(reserva, fecha_pago, *, dry_run: bool) -> bool:
    """Si hay recibo de la propiedad en fecha de pago, lo vincula a esta reserva."""
    if Recibo.objects.filter(reserva_id=reserva.id).exists():
        return False
    rec = (
        Recibo.objects.filter(
            propiedad_id=reserva.propiedad_id,
            fecha_emision__date=fecha_pago,
        )
        .order_by('-fecha_emision', '-id')
        .first()
    )
    if not rec:
        return False
    if dry_run:
        return True
    rec.reserva_id = reserva.id
    rec.save(update_fields=['reserva_id'])
    return True


class Command(BaseCommand):
    help = 'Sincroniza seña/estado desde caja/recibos y alinea sindicato (lote por fechas opcional)'

    def add_arguments(self, parser):
        parser.add_argument('--sucursal-id', type=int, help='Limitar a una sucursal')
        parser.add_argument('--fecha-inicio', type=str, help='Fecha ingreso alquiler (YYYY-MM-DD)')
        parser.add_argument('--fecha-fin', type=str, help='Fecha egreso alquiler (YYYY-MM-DD)')
        parser.add_argument(
            '--fecha-pago',
            type=str,
            help='Fecha del recibo/cobro en caja (YYYY-MM-DD), p. ej. 2026-06-25',
        )
        parser.add_argument(
            '--marcar-sindicato',
            action='store_true',
            help='Marca es_alquiler_sindicato=True y reconstruye historial',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo mostrar qué se actualizaría',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        sucursal_id = options.get('sucursal_id')
        fecha_inicio = _parse_date(options.get('fecha_inicio'))
        fecha_fin = _parse_date(options.get('fecha_fin'))
        fecha_pago = _parse_date(options.get('fecha_pago'))
        marcar_sindicato = options['marcar_sindicato']

        reservas_qs = Reserva.objects.filter(eliminada=False).select_related(
            'propiedad', 'sucursal'
        )
        if sucursal_id:
            reservas_qs = reservas_qs.filter(sucursal_id=sucursal_id)

        if fecha_inicio and fecha_fin:
            reservas_qs = reservas_qs.filter(fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
            self.stdout.write(
                f'Lote: ingreso {fecha_inicio} → egreso {fecha_fin} '
                f'({reservas_qs.count()} reserva(s))'
            )
        else:
            ids_recibo = set(
                Recibo.objects.filter(reserva_id__in=reservas_qs.values('id'))
                .values_list('reserva_id', flat=True)
                .distinct()
            )
            ids_sindicato_hist = set(
                HistorialDisponibilidad.objects.filter(
                    reserva_id__isnull=False,
                    estado='alquiler_sindicato',
                ).values_list('reserva_id', flat=True)
            )
            ids_objetivo = ids_recibo | ids_sindicato_hist
            if not ids_objetivo:
                self.stdout.write('No hay reservas con recibo ni historial sindicato.')
                return
            reservas_qs = reservas_qs.filter(id__in=ids_objetivo)
            self.stdout.write(f'Reservas a revisar: {reservas_qs.count()}')

        flag_actualizados = 0
        sync_count = 0
        recibos_realineados = 0
        propiedades_historial: set[int] = set()

        for reserva in reservas_qs.order_by('id'):
            antes = (reserva.estado, str(reserva.senia or 0), reserva.es_alquiler_sindicato)
            if fecha_pago and _realinear_recibo_propiedad(reserva, fecha_pago, dry_run=dry_run):
                recibos_realineados += 1

            if marcar_sindicato and not reserva.es_alquiler_sindicato:
                flag_actualizados += 1
                if not dry_run:
                    reserva.es_alquiler_sindicato = True
                    reserva.save(update_fields=['es_alquiler_sindicato'])

            if dry_run:
                total = total_senia_pagada_reserva(reserva)
                self.stdout.write(
                    f'  #{reserva.id} {getattr(reserva.propiedad, "direccion", "?")}: '
                    f'estado={reserva.estado} senia={reserva.senia} '
                    f'→ cobrado={total} sindicato={marcar_sindicato or reserva.es_alquiler_sindicato}'
                )
                sync_count += 1
                continue

            total = sincronizar_senia_reserva_desde_movimientos(reserva)
            reserva.refresh_from_db(
                fields=['estado', 'senia', 'cuota_pendiente', 'es_alquiler_sindicato']
            )
            despues = (reserva.estado, str(reserva.senia or 0), reserva.es_alquiler_sindicato)
            if despues != antes or total > Decimal('0.01'):
                self.stdout.write(
                    f'  #{reserva.id} {getattr(reserva.propiedad, "direccion", "?")}: '
                    f'{antes[0]}/{antes[1]} → {despues[0]}/{despues[1]} (cobrado={total})'
                )
            if marcar_sindicato and reserva.propiedad_id:
                propiedades_historial.add(reserva.propiedad_id)
            sync_count += 1

        if marcar_sindicato and not dry_run and propiedades_historial:
            for pid in propiedades_historial:
                primera = (
                    Reserva.objects.filter(propiedad_id=pid, eliminada=False)
                    .order_by('fecha_inicio')
                    .first()
                )
                if primera:
                    primera.reconstruir_historial_cronologico()

        prefijo = '[dry-run] ' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(
                f'{prefijo}Listo: {sync_count} reserva(s), '
                f'{flag_actualizados} marcada(s) sindicato, '
                f'{recibos_realineados} recibo(s) realineado(s).'
            )
        )
