"""
Pasa a noviembre (mismo día) los GastoPropietario de Comisión Gestión Cobranzas
que quedaron con fecha en octubre.

Uso:
  python manage.py mover_gestion_cobranza_mes --dry-run
  python manage.py mover_gestion_cobranza_mes
  python manage.py mover_gestion_cobranza_mes --sucursal Colon
"""
from calendar import monthrange
from datetime import date, datetime, time

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from inmobiliaria.models import GastoPropietario, Sucursal


def _norm(s):
    return (s or '').strip().lower()


def _es_gestion_cobranza(g):
    if str(g.concepto_caja_id or '').strip() == '19':
        return True
    n = _norm(g.descripcion)
    return 'gestion cobran' in n or 'gestión cobran' in n


def _fecha_efectiva(g):
    if g.fecha_gasto:
        return g.fecha_gasto
    fc = g.fecha_creacion
    if not fc:
        return None
    if timezone.is_aware(fc):
        fc = timezone.localtime(fc)
    return fc.date()


def _mover_a_noviembre(d):
    """Misma fecha del mes 11; si el día no existe (p. ej. 31), usa el último día."""
    if not d or d.month != 10:
        return d
    ultimo = monthrange(d.year, 11)[1]
    return date(d.year, 11, min(d.day, ultimo))


class Command(BaseCommand):
    help = (
        'Mueve Comisión Gestión Cobranzas (concepto 19) de octubre a noviembre '
        '(mismo día) en la sucursal indicada (default: Colón).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--sucursal',
            default='Colon',
            help='Nombre o fragmento de la sucursal (default: Colon)',
        )
        parser.add_argument(
            '--anio',
            type=int,
            default=2026,
            help='Año del octubre a mover (default: 2026)',
        )
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        dry = options['dry-run']
        anio = options['anio']
        nombre = (options['sucursal'] or 'Colon').strip()

        suc = (
            Sucursal.objects.filter(nombre__icontains=nombre)
            .order_by('id')
            .first()
        )
        if not suc:
            self.stderr.write(self.style.ERROR(f'No hay sucursal que coincida con «{nombre}».'))
            return

        desde = date(anio, 10, 1)
        hasta = date(anio, 10, 31)

        qs = (
            GastoPropietario.objects.filter(sucursal=suc)
            .filter(
                Q(concepto_caja_id='19')
                | Q(descripcion__icontains='gestion cobran')
                | Q(descripcion__icontains='gestión cobran')
            )
            .filter(
                Q(fecha_gasto__gte=desde, fecha_gasto__lte=hasta)
                | Q(
                    fecha_gasto__isnull=True,
                    fecha_creacion__date__gte=desde,
                    fecha_creacion__date__lte=hasta,
                )
            )
            .select_related('liquidacion', 'propiedad')
            .order_by('id')
        )

        candidatos = [g for g in qs if _es_gestion_cobranza(g)]
        if not candidatos:
            self.stdout.write(
                f'[{suc.nombre}] No hay gestión cobranza en octubre {anio}.'
            )
            return

        self.stdout.write(
            f'[{suc.nombre}] {len(candidatos)} gasto(s) a pasar a noviembre '
            f'{"(dry-run)" if dry else ""}:'
        )

        actualizados = 0
        for g in candidatos:
            fe = _fecha_efectiva(g)
            nueva = _mover_a_noviembre(fe)
            if not fe or not nueva or nueva == fe:
                continue
            liq = g.liquidacion_id or '—'
            prop = getattr(g.propiedad, 'direccion', None) or '—'
            self.stdout.write(
                f'  gasto #{g.id} liq #{liq} {prop}: {fe} → {nueva}  ${g.monto}'
            )
            if dry:
                actualizados += 1
                continue

            g.fecha_gasto = nueva
            # Si la creación quedó en octubre, corrige el datetime al mismo día/hora en nov.
            updates = ['fecha_gasto']
            fc = g.fecha_creacion
            if fc:
                if timezone.is_aware(fc):
                    local = timezone.localtime(fc)
                else:
                    local = fc
                if local.date().month == 10 and local.date().year == anio:
                    nuevo_dt = datetime.combine(
                        nueva, local.time() if hasattr(local, 'time') else time(12, 0)
                    )
                    if timezone.is_aware(fc):
                        nuevo_dt = timezone.make_aware(
                            nuevo_dt, timezone.get_current_timezone()
                        )
                    # fecha_creacion es auto_now_add: update directo en BD
                    GastoPropietario.objects.filter(pk=g.pk).update(
                        fecha_gasto=nueva,
                        fecha_creacion=nuevo_dt,
                    )
                    actualizados += 1
                    continue

            g.save(update_fields=updates)
            actualizados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Listo: {actualizados} registro(s)'
                + (' (simulado)' if dry else ' actualizado(s).')
            )
        )
