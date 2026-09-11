"""
Repara saldos distorsionados de un contrato (mora automática, recibos sin imputar).

Uso:
  python manage.py reparar_cobranza_contrato 230 --dry-run
  python manage.py reparar_cobranza_contrato 230
  python manage.py reparar_cobranza_contrato 230 --mayo 525200
  python manage.py reparar_cobranza_contrato 230 --mover-adelanto 1 2
  python manage.py reparar_cobranza_contrato 230 --recibo-mes junio --numero-recibo 0001-150
  python manage.py reparar_cobranza_contrato 230 --set-credito 5 23518
  python manage.py reparar_cobranza_contrato 230 --dejar-adelanto 5 568900 548718
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from inmobiliaria.models import ContratoAlquiler
from inmobiliaria.cuotas_imputacion import (
    dejar_cuota_en_adelanto_parcial,
    limpiar_mora_automatica_cuotas,
    marcar_cuota_pagada_desde_recibo_mes,
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
        parser.add_argument(
            '--recibo-mes',
            type=str,
            default='',
            help='Marca pagada la cuota del mes usando un recibo (ej. junio).',
        )
        parser.add_argument(
            '--numero-recibo',
            type=str,
            default='',
            help='Número de recibo a usar con --recibo-mes (ej. 0001-150).',
        )
        parser.add_argument(
            '--anio',
            type=int,
            default=None,
            help='Año de la cuota al usar --recibo-mes (opcional).',
        )
        parser.add_argument(
            '--set-credito',
            nargs=2,
            metavar=('CUOTA', 'MONTO'),
            help='Solo fija credito_aplicado de la cuota N al monto (ej. 5 23518). No toca el resto.',
        )
        parser.add_argument(
            '--dejar-adelanto',
            nargs=3,
            metavar=('CUOTA', 'MONTO', 'CREDITO'),
            help=(
                'Deja la cuota como adelanto parcial (ej. 5 568900 548718 = '
                'cuota 568900 con a favor 23518+525200; saldo ~20182). No toca otras cuotas.'
            ),
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

        dejar = options.get('dejar_adelanto')
        set_credito = options.get('set_credito')
        solo_puntual = (dejar or set_credito) and not (
            options.get('mayo')
            or options.get('mover_adelanto')
            or options.get('recibo_mes')
        )
        if solo_puntual:
            if dejar:
                self._dejar_adelanto(contrato, dejar[0], dejar[1], dejar[2])
            if set_credito and not dejar:
                self._fijar_credito(contrato, set_credito[0], set_credito[1])
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

        recibo_mes = (options.get('recibo_mes') or '').strip()
        if recibo_mes:
            mov = self._buscar_movimiento(contrato, options.get('numero_recibo') or '')
            if not mov:
                raise CommandError(
                    'No se encontró el movimiento/recibo. Pasá --numero-recibo 0001-150 '
                    'o verificá que el concepto diga Contrato #230.'
                )
            try:
                res = marcar_cuota_pagada_desde_recibo_mes(
                    contrato, mov, mes_nombre=recibo_mes, anio=options.get('anio')
                )
            except ValueError as e:
                raise CommandError(str(e)) from e
            self.stdout.write(
                self.style.SUCCESS(
                    f'Recibo → cuota {res["cuota_numero"]} (mes {res["mes"]}/{res["anio"]}): '
                    f'${res["importe"]} estado={res["estado"]}'
                )
            )

        mover = options.get('mover_adelanto')
        if mover:
            res = mover_credito_adelanto_entre_cuotas(contrato, mover[0], mover[1])
            self.stdout.write(
                self.style.SUCCESS(
                    f'Adelanto ${res["monto"]} movido: cuota {res["desde"]} → {res["hacia"]} '
                    f'(saldo destino ${res["saldo_destino"]})'
                )
            )

        if dejar:
            self._dejar_adelanto(contrato, dejar[0], dejar[1], dejar[2])
        elif set_credito:
            self._fijar_credito(contrato, set_credito[0], set_credito[1])

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

    def _dejar_adelanto(self, contrato, numero_raw, monto_raw, credito_raw):
        from inmobiliaria.decimal_utils import parse_decimal_monto

        try:
            numero = int(str(numero_raw).strip())
        except (TypeError, ValueError) as e:
            raise CommandError('Número de cuota inválido.') from e
        try:
            res = dejar_cuota_en_adelanto_parcial(
                contrato,
                numero,
                parse_decimal_monto(str(monto_raw)),
                parse_decimal_monto(str(credito_raw)),
            )
        except ValueError as e:
            raise CommandError(str(e)) from e
        self.stdout.write(
            self.style.SUCCESS(
                f'Cuota {res["cuota_numero"]}: monto ${res["monto"]}, a favor ${res["credito"]}, '
                f'saldo a cobrar ${res["saldo"]} ({res["estado"]}). Nada más modificado.'
            )
        )

    def _fijar_credito(self, contrato, numero_raw, monto_raw):
        from inmobiliaria.decimal_utils import parse_decimal_monto

        try:
            numero = int(str(numero_raw).strip())
        except (TypeError, ValueError) as e:
            raise CommandError('Número de cuota inválido.') from e
        monto = parse_decimal_monto(str(monto_raw))
        if monto < 0:
            raise CommandError('El monto a favor no puede ser negativo.')
        cuota = contrato.cuotas.filter(numero_cuota=numero).first()
        if not cuota:
            raise CommandError(f'No existe la cuota {numero}.')
        anterior = Decimal(str(cuota.credito_aplicado or 0))
        cuota.credito_aplicado = monto
        cuota.save(update_fields=['credito_aplicado'])
        self.stdout.write(
            self.style.SUCCESS(
                f'Cuota {numero}: a favor ${anterior} → ${monto} '
                f'(saldo a cobrar ${cuota.saldo_para_cobro()}). Nada más modificado.'
            )
        )

    def _buscar_movimiento(self, contrato, numero_recibo: str):
        from inmobiliaria.models.caja import MovimientoCaja, TipoMovimientoCajaEnum

        qs = MovimientoCaja.objects.filter(
            propiedad_id=contrato.propiedad_id,
            tipo=TipoMovimientoCajaEnum.INGRESO,
            fecha_eliminacion__isnull=True,
            concepto__icontains=f'Contrato #{contrato.id}',
        ).select_related('recibo').order_by('-fecha', '-id')

        numero = (numero_recibo or '').strip()
        if numero:
            # Coincide por número de recibo o por liquidación
            for mov in qs[:80]:
                rec = getattr(mov, 'recibo', None)
                rn = (getattr(rec, 'numero_recibo', None) or '').strip() if rec else ''
                nl = (getattr(mov, 'numero_liquidacion', None) or '').strip()
                if numero in rn or numero in nl or rn.endswith(numero) or nl.endswith(numero):
                    return mov
            # Fallback: búsqueda directa
            mov = (
                MovimientoCaja.objects.filter(
                    propiedad_id=contrato.propiedad_id,
                    tipo=TipoMovimientoCajaEnum.INGRESO,
                    fecha_eliminacion__isnull=True,
                    recibo__numero_recibo__icontains=numero,
                )
                .select_related('recibo')
                .order_by('-fecha', '-id')
                .first()
            )
            if mov:
                return mov
            return (
                MovimientoCaja.objects.filter(
                    propiedad_id=contrato.propiedad_id,
                    tipo=TipoMovimientoCajaEnum.INGRESO,
                    fecha_eliminacion__isnull=True,
                    numero_liquidacion__icontains=numero,
                )
                .order_by('-fecha', '-id')
                .first()
            )

        # Sin número: primer ingreso con líneas de alquiler / mes junio en detalle
        for mov in qs[:40]:
            detalle = (getattr(mov, 'concepto_detalle', None) or '').lower()
            if '1290' in detalle or 'alquiler a cobrar' in detalle or 'junio' in detalle:
                return mov
        return qs.first()
