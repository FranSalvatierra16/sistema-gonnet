"""
Corrige reservas sindicato con cobro en caja/recibo que quedaron como «Reservado».

Todos los lotes Marconi 2026 (junio + julio):
  python manage.py reparar_reservas_sindicato_recibo --lote-marconi --dry-run
  python manage.py reparar_reservas_sindicato_recibo --lote-marconi

Por fechas manuales:
  python manage.py reparar_reservas_sindicato_recibo \\
    --fecha-inicio 2026-06-17 --fecha-fin 2026-06-18 --fecha-pago 2026-06-25
"""
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Q

from inmobiliaria.caja_devolucion_deposito import (
    FECHA_CARGA_LOTE_MARCONI,
    LOTES_SINDICATO_MARCONI,
    config_lote_sindicato_marconi,
    es_reserva_lote_sindicato_marconi,
    sincronizar_senia_reserva_desde_movimientos,
    total_senia_pagada_reserva,
)
from inmobiliaria.models import HistorialDisponibilidad, Recibo, Reserva


def _parse_date(raw: str | None):
    if not raw:
        return None
    return datetime.strptime(raw.strip(), '%Y-%m-%d').date()


def _realinear_recibo_propiedad(reserva, fechas_pago, *, dry_run: bool) -> bool:
    if Recibo.objects.filter(reserva_id=reserva.id).exists():
        return False
    for fecha_pago in fechas_pago:
        rec = (
            Recibo.objects.filter(
                propiedad_id=reserva.propiedad_id,
                fecha_emision__date=fecha_pago,
            )
            .order_by('-fecha_emision', '-id')
            .first()
        )
        if not rec:
            continue
        if dry_run:
            return True
        rec.reserva_id = reserva.id
        rec.save(update_fields=['reserva_id'])
        return True
    return False


class Command(BaseCommand):
    help = 'Repara operaciones sindicato Marconi (lotes junio y julio 2026)'

    def add_arguments(self, parser):
        parser.add_argument('--sucursal-id', type=int, help='Limitar a una sucursal')
        parser.add_argument(
            '--lote-marconi',
            action='store_true',
            help='Todos los lotes Marconi: 17–18/06 y 18/07–02/08/2026',
        )
        parser.add_argument('--fecha-inicio', type=str, help='Fecha ingreso (YYYY-MM-DD)')
        parser.add_argument('--fecha-fin', type=str, help='Fecha egreso (YYYY-MM-DD)')
        parser.add_argument('--fecha-pago', type=str, help='Fecha del recibo/cobro (YYYY-MM-DD)')
        parser.add_argument('--dry-run', action='store_true', help='Solo mostrar cambios')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        sucursal_id = options.get('sucursal_id')
        lote_marconi = options['lote_marconi']

        fecha_inicio = _parse_date(options.get('fecha_inicio'))
        fecha_fin = _parse_date(options.get('fecha_fin'))
        fecha_pago_manual = _parse_date(options.get('fecha_pago'))

        reservas_qs = Reserva.objects.filter(eliminada=False).select_related(
            'propiedad', 'sucursal', 'cliente'
        )
        if sucursal_id:
            reservas_qs = reservas_qs.filter(sucursal_id=sucursal_id)

        if lote_marconi:
            q_lotes = Q()
            for lote in LOTES_SINDICATO_MARCONI:
                q_lotes |= Q(fecha_inicio=lote.fecha_ingreso, fecha_fin=lote.fecha_egreso)
            q_carga = Q(
                fecha_creacion__date=FECHA_CARGA_LOTE_MARCONI,
            ) & (
                Q(cliente__apellido__icontains='marconi')
                | Q(cliente__nombre__icontains='marconi')
            )
            reservas_qs = list(reservas_qs.filter(q_lotes | q_carga))
            reservas_qs = [r for r in reservas_qs if config_lote_sindicato_marconi(r)]
            self.stdout.write(
                'Lotes Marconi: '
                + ', '.join(l.etiqueta for l in LOTES_SINDICATO_MARCONI)
                + f' → {len(reservas_qs)} reserva(s)'
            )
        elif fecha_inicio and fecha_fin:
            reservas_qs = list(
                reservas_qs.filter(fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
            )
            self.stdout.write(f'Lote por fechas: {len(reservas_qs)} reserva(s)')
        else:
            ids_recibo = set(
                Recibo.objects.filter(reserva_id__in=reservas_qs.values('id'))
                .values_list('reserva_id', flat=True)
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
            reservas_qs = list(reservas_qs.filter(id__in=ids_objetivo))
            self.stdout.write(f'Reservas a revisar: {len(reservas_qs)}')

        if not reservas_qs:
            self.stdout.write('No se encontraron reservas para reparar.')
            return

        sync_count = 0
        recibos_realineados = 0
        propiedades_historial: set[int] = set()

        for reserva in sorted(reservas_qs, key=lambda r: r.id):
            antes = (reserva.estado, str(reserva.senia or 0), reserva.es_alquiler_sindicato)
            lote = config_lote_sindicato_marconi(reserva)
            fechas_pago = (
                lote.fechas_pago
                if lote
                else ((fecha_pago_manual,) if fecha_pago_manual else ())
            )
            if fechas_pago and _realinear_recibo_propiedad(
                reserva, fechas_pago, dry_run=dry_run
            ):
                recibos_realineados += 1

            if dry_run:
                total = total_senia_pagada_reserva(reserva)
                forzaria = es_reserva_lote_sindicato_marconi(reserva) and total <= Decimal('0.01')
                etiqueta_lote = lote.etiqueta if lote else '—'
                self.stdout.write(
                    f'  #{reserva.id} [{etiqueta_lote}] '
                    f'{getattr(reserva.propiedad, "direccion", "?")}: '
                    f'estado={reserva.estado} senia={reserva.senia} → cobrado={total}'
                    f'{" [forzaría pagada+sindicato]" if forzaria else ""}'
                )
                sync_count += 1
                continue

            total = sincronizar_senia_reserva_desde_movimientos(reserva)
            reserva.refresh_from_db(
                fields=['estado', 'senia', 'cuota_pendiente', 'es_alquiler_sindicato']
            )
            despues = (reserva.estado, str(reserva.senia or 0), reserva.es_alquiler_sindicato)
            if despues != antes or total > Decimal('0.01'):
                etiqueta_lote = lote.etiqueta if lote else '—'
                self.stdout.write(
                    f'  #{reserva.id} [{etiqueta_lote}] '
                    f'{getattr(reserva.propiedad, "direccion", "?")}: '
                    f'{antes[0]}/{antes[1]}/sind={antes[2]} → '
                    f'{despues[0]}/{despues[1]}/sind={despues[2]} (cobrado={total})'
                )
            if reserva.es_alquiler_sindicato and reserva.propiedad_id:
                propiedades_historial.add(reserva.propiedad_id)
            sync_count += 1

        if not dry_run and propiedades_historial:
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
                f'{recibos_realineados} recibo(s) realineado(s).'
            )
        )
