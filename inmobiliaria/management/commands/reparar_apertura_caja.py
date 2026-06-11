"""
Corrige la apertura de una caja abierta copiando los saldos del cierre de la caja anterior.

Ejemplo (Corrientes: caja 24 con saldos del cierre de la 23):
    python manage.py reparar_apertura_caja --sucursal Corrientes --desde 23 --hacia 24
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from inmobiliaria.caja_arqueo import (
    apertura_dict_desde_caja_cerrada,
    reparar_apertura_desde_caja_anterior,
    total_ars_desde_arqueo_dict,
)
from inmobiliaria.models import Caja, Sucursal


class Command(BaseCommand):
    help = 'Aplica a una caja abierta los saldos por medio del arqueo de cierre de otra caja (cerrada).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sucursal',
            required=True,
            help='Nombre de la sucursal (ej: Corrientes)',
        )
        parser.add_argument(
            '--desde',
            type=int,
            required=True,
            help='Número de la caja cerrada (origen del arqueo)',
        )
        parser.add_argument(
            '--hacia',
            type=int,
            required=True,
            help='Número de la caja abierta a corregir',
        )
        parser.add_argument(
            '--usuario-id',
            type=int,
            default=None,
            help='Usuario que registra el arqueo (default: primer superuser/staff)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo muestra los saldos que se aplicarían',
        )

    def handle(self, *args, **options):
        nombre = options['sucursal'].strip()
        sucursal = (
            Sucursal.objects.filter(nombre__iexact=nombre).first()
            or Sucursal.objects.filter(nombre__icontains=nombre).first()
        )
        if not sucursal:
            self.stderr.write(self.style.ERROR(f'No se encontró sucursal: {nombre}'))
            return

        desde = options['desde']
        hacia = options['hacia']
        caja_origen = Caja.objects.filter(numero=desde, sucursal=sucursal).first()
        caja_destino = Caja.objects.filter(numero=hacia, sucursal=sucursal).first()
        if not caja_origen:
            self.stderr.write(self.style.ERROR(f'No existe caja #{desde} en {sucursal.nombre}'))
            return
        if not caja_destino:
            self.stderr.write(self.style.ERROR(f'No existe caja #{hacia} en {sucursal.nombre}'))
            return

        apertura = apertura_dict_desde_caja_cerrada(caja_origen)
        total = total_ars_desde_arqueo_dict(apertura)

        self.stdout.write(f'Sucursal: {sucursal.nombre} (id={sucursal.pk})')
        self.stdout.write(f'Origen: Caja #{desde} ({caja_origen.estado})')
        self.stdout.write(f'Destino: Caja #{hacia} ({caja_destino.estado})')
        self.stdout.write('Saldos a aplicar (conteo de cierre):')
        self.stdout.write(f'  Efectivo ARS: {apertura["efectivo"]}')
        self.stdout.write(f'  Cheques:      {apertura["cheque"]}')
        self.stdout.write(f'  Tarjeta:      {apertura["tarjeta"]}')
        self.stdout.write(f'  USD:          {apertura["dolares"]}')
        for cid, monto in sorted((apertura.get('cuentas_json') or {}).items()):
            self.stdout.write(f'  Cuenta {cid}: {monto}')
        self.stdout.write(f'  Total ARS:    {total}')

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('DRY-RUN: no se guardó nada.'))
            return

        User = get_user_model()
        uid = options['usuario_id']
        if uid:
            usuario = User.objects.filter(pk=uid).first()
        else:
            usuario = (
                User.objects.filter(is_superuser=True).order_by('id').first()
                or User.objects.filter(is_staff=True).order_by('id').first()
                or User.objects.order_by('id').first()
            )
        if not usuario:
            self.stderr.write(self.style.ERROR('No hay usuario para registrar el arqueo.'))
            return

        caja, arqueo, _, total_final = reparar_apertura_desde_caja_anterior(
            sucursal, desde, hacia, usuario
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Caja #{caja.numero} reparada. saldo_inicial={caja.saldo_inicial} · '
                f'total ARS por medio={total_final} · arqueo_manual id={arqueo.pk}'
            )
        )
