"""
Repara saldos distorsionados de un contrato (mora automática, recibos sin imputar).

Uso:
  python manage.py reparar_cobranza_contrato 230 --dry-run
  python manage.py reparar_cobranza_contrato 230
  python manage.py reparar_cobranza_contrato 230 --mayo 525200
  python manage.py reparar_cobranza_contrato 230 --mover-adelanto 1 2
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from inmobiliaria.models import ContratoAlquiler
from inmobiliaria.cuotas_imputacion import (
    limpiar_mora_automatica_cuotas,
    mover_credito_adelanto_entre_cuotas,
    reimputar_desde_recibos_existentes,
)


class Command(BaseCommand):
    help = 'Limpia mora inventada, reimputa recibos y puede mover adelantos entre cuotas.'

    def add_arguments(self, parser):
        parser.add_argument('contrato_id', type=int)
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument(
            '--mayo',
            type=str,
            default='',
            help='Si se indica, fija el monto_base de la cuota de mayo (ej. 525200).',
        )
        parser.add_argument(
            '--mover-adelanto',
            nargs=2,
            type=int,
            metavar=('DESDE', 'HACIA'),
            help='Mueve credito_aplicado de la cuota DESDE a la cuota HACIA (ej. 1 2 = mayo→junio).',
        )

    def handle(self, *args, **options):
        cid = options['contrato_id']
        contrato = (
            ContratoAlquiler.objects.filter(pk=cid)
            .select_related('propiedad', 'sucursal')
            .first()
        )
        if not contrato:
            raise CommandError(f'No existe contrato #{cid}')

        self.stdout.write(
            f'Contrato #{contrato.id} — {(contrato.propiedad.direccion if contrato.propiedad else "")} '
            f'({getattr(contrato.sucursal, "nombre", "")})'
        )
        for c in contrato.cuotas.all().order_by('numero_cuota'):
            fv = c.fecha_vencimiento.strftime('%d/%m/%Y') if c.fecha_vencimiento else '—'
            self.stdout.write(
                f'  {c.numero_cuota:02d} {fv} estado={c.estado} '
                f'base={c.monto_base} total={c.monto_total} mora={c.recargo_mora} '
                f'crédito={c.credito_aplicado} saldo={c.saldo_para_cobro()}'
            )

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('Dry-run: no se modificó nada.'))
            return

        n_mora = limpiar_mora_automatica_cuotas(contrato)
        n_reimp = reimputar_desde_recibos_existentes(contrato, timezone.localdate())

        mayo_raw = (options.get('mayo') or '').strip().replace('.', '').replace(',', '.')
        if mayo_raw:
            from inmobiliaria.decimal_utils import parse_decimal_monto

            monto_mayo = parse_decimal_monto(mayo_raw)
            for c in contrato.cuotas.filter(estado__in=['pendiente', 'vencida']):
                if c.fecha_vencimiento and c.fecha_vencimiento.month == 5:
                    c.monto_base = monto_mayo
                    c.recargo_mora = Decimal('0')
                    c.actualizar_monto_total()
                    self.stdout.write(self.style.SUCCESS(f'Mayo (cuota {c.numero_cuota}) → {monto_mayo}'))

        mover = options.get('mover_adelanto')
        if mover:
            res = mover_credito_adelanto_entre_cuotas(contrato, mover[0], mover[1])
            self.stdout.write(
                self.style.SUCCESS(
                    f'Adelanto ${res["monto"]} movido: cuota {res["desde"]} → {res["hacia"]} '
                    f'(saldo destino ${res["saldo_destino"]})'
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Listo: mora limpiada en {n_mora} cuota(s), reimputados {n_reimp} cobro(s).'
            )
        )
        for c in contrato.cuotas.all().order_by('numero_cuota')[:8]:
            fv = c.fecha_vencimiento.strftime('%d/%m/%Y') if c.fecha_vencimiento else '—'
            self.stdout.write(
                f'  {c.numero_cuota:02d} {fv} {c.estado} '
                f'base={c.monto_base} total={c.monto_total} crédito={c.credito_aplicado} '
                f'saldo={c.saldo_para_cobro()}'
            )
