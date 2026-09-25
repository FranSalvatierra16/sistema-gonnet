"""Lista de dónde sale Gastos bancarios del cierre."""
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from inmobiliaria.models.caja import MovimientoCaja, TipoMovimientoCajaEnum
from inmobiliaria.models.oficina import GastoOficina
from inmobiliaria.models.sucursal import Sucursal
from inmobiliaria.oficina_gastos import (
    _importe_solo_lineas_concepto_id,
    _movimiento_es_concepto_id_estricto,
    _neto_gastos_oficina_desde_caja_mapeada,
    _parse_lineas_concepto_movimiento,
    _q_movimientos_por_concepto_id_estricto,
    resolver_categoria_oficina_por_ruta,
)
from django.db.models.functions import TruncDate


class Command(BaseCommand):
    help = 'Desglosa Gastos bancarios del resumen cierre'

    def add_arguments(self, parser):
        parser.add_argument('--sucursal', default='corrientes')
        parser.add_argument('--anio', type=int, default=2026)
        parser.add_argument('--mes', type=int, default=9)

    def handle(self, *args, **options):
        suc = Sucursal.objects.filter(nombre__icontains=options['sucursal']).first()
        if not suc:
            self.stderr.write('Sucursal no encontrada')
            return
        anio, mes = options['anio'], options['mes']
        fd = date(anio, mes, 1)
        if mes == 12:
            fh = date(anio, 12, 31)
        else:
            fh = date(anio, mes + 1, 1) - __import__('datetime').timedelta(days=1)

        cat = resolver_categoria_oficina_por_ruta(suc, 'Ingresos', 'Gastos bancarios')
        self.stdout.write(f'Sucursal: {suc.nombre} ({suc.id})  rango {fd}..{fh}')
        self.stdout.write(f'Categoría: {cat}')

        netos = _neto_gastos_oficina_desde_caja_mapeada(suc, fd, fh)
        neto = netos.get(cat.id, Decimal('0')) if cat else Decimal('0')
        self.stdout.write(f'Neto desde caja (concepto 22): ${neto}')

        extras = Decimal('0')
        if cat:
            for g in GastoOficina.objects.filter(
                sucursal=suc,
                categoria=cat,
                fecha__gte=fd,
                fecha__lte=fh,
                movimiento_caja__isnull=True,
            ).exclude(observaciones__icontains='Vinculado automáticamente'):
                extras += Decimal(str(g.monto or 0))
                self.stdout.write(
                    f'  MANUAL GO#{g.id} {g.fecha} ${g.monto} {(g.descripcion or "")[:60]}'
                )
        self.stdout.write(f'Manuales (sin mov auto): ${extras}')
        self.stdout.write(f'TOTAL cierre ≈ ${neto + extras}')

        self.stdout.write('--- Movimientos concepto 22 ---')
        qs = (
            MovimientoCaja.objects.filter(sucursal=suc)
            .annotate(fday=TruncDate('fecha'))
            .filter(fday__gte=fd, fday__lte=fh)
            .filter(_q_movimientos_por_concepto_id_estricto('22'))
            .order_by('fecha', 'id')
        )
        total = Decimal('0')
        for m in qs:
            if not _movimiento_es_concepto_id_estricto(m, '22'):
                continue
            lineas = _parse_lineas_concepto_movimiento(m)
            if lineas:
                importe = _importe_solo_lineas_concepto_id(m, '22')
            else:
                importe = abs(Decimal(str(m.monto_total or 0)))
            if m.tipo == TipoMovimientoCajaEnum.INGRESO:
                aporte = -importe
            else:
                aporte = importe
            total += aporte
            self.stdout.write(
                f'  M#{m.id} {m.fday} {m.tipo} importe={importe} aporte={aporte} '
                f'{(m.concepto or "")[:70]}'
            )
        self.stdout.write(f'Suma aportes 22: ${total}')
