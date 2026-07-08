"""
Lista operaciones de Corrientes que el sistema marcó o modificó sin cobro vinculado
(migraciones, lote Marconi, sindicato, sincronización histórica).

  python manage.py reportar_operaciones_automaticas_corrientes
  python manage.py reportar_operaciones_automaticas_corrientes --csv
"""
from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef, Q

from inmobiliaria.models import Recibo, Reserva, Sucursal


def _nombre_vendedor(reserva) -> str:
    v = getattr(reserva, 'vendedor', None)
    if not v:
        return '— sin productor —'
    ap = (getattr(v, 'apellido', None) or '').strip()
    nom = (getattr(v, 'nombre', None) or '').strip()
    return f'{ap}, {nom}'.strip(', ') or f'ID {v.id}'


class Command(BaseCommand):
    help = 'Reporta reservas de Corrientes tocadas por lógica automática del sistema'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sucursal',
            default='Corrientes',
            help='Nombre de sucursal (default: Corrientes)',
        )
        parser.add_argument('--csv', action='store_true', help='Salida separada por ;')

    def handle(self, *args, **options):
        sucursal = (
            Sucursal.objects.filter(nombre__icontains=options['sucursal'].strip())
            .order_by('pk')
            .first()
        )
        if not sucursal:
            self.stderr.write(self.style.ERROR('No se encontró la sucursal.'))
            return

        tiene_recibo = Exists(Recibo.objects.filter(reserva_id=OuterRef('pk')))
        base = Reserva.objects.filter(sucursal=sucursal, eliminada=False).select_related(
            'cliente', 'propiedad', 'vendedor'
        )

        # Criterio A: migración 0153 — lote Marconi julio 18/07 → 02/08/2026 (efectivo)
        fi_marconi_jul = date(2026, 7, 18)
        ff_marconi_jul = date(2026, 8, 2)
        lote_marconi_jul = base.filter(
            fecha_fin=ff_marconi_jul,
            fecha_inicio__gte=fi_marconi_jul,
        ).filter(
            Q(cliente__apellido__icontains='marconi') | Q(cliente__nombre__icontains='marconi')
        )

        # Criterio B: lote sindicato Marconi (jun/jul 2026) — fechas típicas del lote
        fechas_sindicato = (
            (date(2026, 6, 17), date(2026, 6, 18)),
            (date(2026, 7, 17), date(2026, 7, 18)),
        )
        q_sindicato_fechas = Q()
        for ing, egr in fechas_sindicato:
            q_sindicato_fechas |= Q(fecha_inicio=ing, fecha_fin=egr)
        lote_marconi_sindicato = base.filter(
            es_alquiler_sindicato=True,
        ).filter(
            Q(cliente__apellido__icontains='marconi') | Q(cliente__nombre__icontains='marconi')
        ).filter(q_sindicato_fechas)

        # Criterio C: pagada o sindicato con seña completa pero SIN recibo ni movimiento en concepto
        # (estado tocado por sync/migración, no por cobro normal en caja)
        pagada_sin_recibo = base.filter(
            Q(estado='pagada') | Q(es_alquiler_sindicato=True),
            senia__gt=Decimal('0.01'),
        ).annotate(_tiene_recibo=tiene_recibo).filter(_tiene_recibo=False)

        # Criterio D: carga masiva 25/06/2026 (mismo día que el lote Marconi en caja)
        carga_25_jun = base.filter(fecha_creacion__date=date(2026, 6, 25)).filter(
            Q(cliente__apellido__icontains='marconi') | Q(cliente__nombre__icontains='marconi')
        )

        grupos = [
            (
                'Lote Marconi julio (18/07–02/08/2026) — migración 0153 / efectivo',
                lote_marconi_jul.order_by('id'),
            ),
            (
                'Lote Marconi sindicato (17–18/06 y 17–18/07/2026)',
                lote_marconi_sindicato.order_by('id'),
            ),
            (
                'Carga masiva 25/06/2026 (cliente Marconi)',
                carga_25_jun.order_by('id'),
            ),
            (
                'Pagada o sindicato con seña pero sin recibo en sistema',
                pagada_sin_recibo.order_by('-id')[:200],
            ),
        ]

        vistos: set[int] = set()
        filas = []

        for titulo, qs in grupos:
            for r in qs:
                if r.id in vistos:
                    continue
                vistos.add(r.id)
                precio = Decimal(str(r.precio_total or 0))
                senia = Decimal(str(r.senia or 0))
                filas.append({
                    'grupo': titulo,
                    'id': r.id,
                    'direccion': (r.propiedad.direccion if r.propiedad_id else '—') or '—',
                    'cliente': (
                        f'{(r.cliente.apellido or "")}, {(r.cliente.nombre or "")}'.strip(', ')
                        if r.cliente_id
                        else '—'
                    ),
                    'periodo': f'{r.fecha_inicio} → {r.fecha_fin}',
                    'estado': r.estado or '',
                    'sindicato': 'sí' if r.es_alquiler_sindicato else 'no',
                    'senia': senia,
                    'precio': precio,
                    'productor': _nombre_vendedor(r),
                    'creada': (
                        r.fecha_creacion.strftime('%d/%m/%Y %H:%M')
                        if r.fecha_creacion
                        else '—'
                    ),
                    'nota': (
                        'Sin recibo: estado/seña probablemente ajustados por sistema'
                        if not Recibo.objects.filter(reserva_id=r.id).exists()
                        else 'Tiene recibo'
                    ),
                })

        if options['csv']:
            out = StringIO()
            cols = [
                'grupo', 'id', 'direccion', 'cliente', 'periodo', 'estado', 'sindicato',
                'senia', 'precio', 'productor', 'creada', 'nota',
            ]
            out.write(';'.join(cols) + '\n')
            for f in filas:
                out.write(';'.join(str(f[c]) for c in cols) + '\n')
            self.stdout.write(out.getvalue())
            return

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f'Sucursal: {sucursal.nombre} (ID {sucursal.id}) — '
                f'{len(filas)} operación(es) con indicios de ajuste automático\n'
            )
        )
        self.stdout.write(
            'Nota: las reservas las cargó un productor; lo automático fue marcar '
            'pagada/sindicato/seña sin cobro bien vinculado en caja.\n'
        )

        grupo_actual = None
        for f in filas:
            if f['grupo'] != grupo_actual:
                grupo_actual = f['grupo']
                self.stdout.write(self.style.WARNING(f'\n=== {grupo_actual} ==='))
            self.stdout.write(
                f"  #{f['id']:>5}  {f['direccion'][:40]:<40}  {f['periodo']}  "
                f"est={f['estado']} sind={f['sindicato']}  "
                f"${f['senia']}/${f['precio']}  prod: {f['productor']}  "
                f"creada {f['creada']}  ({f['nota']})"
            )

        if not filas:
            self.stdout.write(self.style.SUCCESS('No se encontraron candidatas con estos criterios.'))
