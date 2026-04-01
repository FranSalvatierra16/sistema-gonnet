"""
Cierra las cajas abiertas de sucursales indicadas y abre una caja nueva con saldo inicial 0.

No elimina movimientos ni recibos: el historial queda en las cajas cerradas.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from inmobiliaria.models import Caja, Sucursal


class Command(BaseCommand):
    help = (
        'Cierra cajas abiertas de las sucursales dadas y crea una caja nueva con saldo 0. '
        'Por defecto: Colon y Corrientes (coincidencia insensible a mayúsculas).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'nombres',
            nargs='*',
            default=['Colon', 'Corrientes'],
            help='Nombres de sucursal (ej: Colon Corrientes)',
        )
        parser.add_argument(
            '--usuario-id',
            type=int,
            default=None,
            help='ID de usuario para apertura de la nueva caja (por defecto: primer staff o superuser)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo muestra qué haría, sin guardar',
        )

    def handle(self, *args, **options):
        nombres = options['nombres']
        dry_run = options['dry_run']
        usuario_id = options['usuario_id']

        User = get_user_model()
        if usuario_id:
            usuario = User.objects.filter(pk=usuario_id).first()
            if not usuario:
                self.stderr.write(self.style.ERROR(f'No existe usuario id={usuario_id}'))
                return
        else:
            usuario = (
                User.objects.filter(is_staff=True).order_by('id').first()
                or User.objects.filter(is_superuser=True).order_by('id').first()
                or User.objects.order_by('id').first()
            )
            if not usuario:
                self.stderr.write(self.style.ERROR('No hay ningún usuario en la base para abrir la caja.'))
                return

        sucursales = []
        for nombre in nombres:
            s = Sucursal.objects.filter(nombre__iexact=nombre.strip()).first()
            if not s:
                s = Sucursal.objects.filter(nombre__icontains=nombre.strip()).first()
            if not s:
                self.stderr.write(self.style.WARNING(f'No se encontró sucursal: {nombre}'))
                continue
            sucursales.append(s)

        if not sucursales:
            self.stderr.write(self.style.ERROR('No hay sucursales válidas para procesar.'))
            return

        self.stdout.write(f'Usuario apertura/cierre: {usuario} (id={usuario.pk})')
        if dry_run:
            self.stdout.write(self.style.WARNING('MODO DRY-RUN (no se guarda nada)'))

        for sucursal in sucursales:
            abiertas = list(Caja.objects.filter(sucursal=sucursal, estado='abierta').order_by('numero'))
            self.stdout.write(f'\n--- {sucursal.nombre} (id={sucursal.pk}) ---')
            self.stdout.write(f'  Cajas abiertas: {len(abiertas)}')

            for caja in abiertas:
                saldo = caja.get_saldo_actual()
                self.stdout.write(f'  Cerrar caja #{caja.numero} saldo_actual≈ {saldo}')

            if dry_run:
                self.stdout.write('  [dry-run] Crearía nueva caja saldo_inicial=0.00')
                continue

            with transaction.atomic():
                for caja in abiertas:
                    saldo_final = caja.get_saldo_actual()
                    caja.fecha_cierre = timezone.now()
                    caja.estado = 'cerrada'
                    caja.saldo_final = saldo_final
                    caja.usuario_cierre = usuario
                    caja.observaciones_cierre = (
                        (caja.observaciones_cierre or '').strip()
                        + '\n[Cierre automático reset_caja_sucursales]'
                    ).strip()
                    caja.save(
                        update_fields=[
                            'fecha_cierre',
                            'estado',
                            'saldo_final',
                            'usuario_cierre',
                            'observaciones_cierre',
                        ]
                    )

                nueva = Caja.objects.create(
                    sucursal=sucursal,
                    saldo_inicial=Decimal('0.00'),
                    estado='abierta',
                    usuario_apertura=usuario,
                    observaciones_apertura='Apertura tras reset de caja (saldo desde cero)',
                )
                self.stdout.write(self.style.SUCCESS(f'  Nueva caja abierta: #{nueva.numero} saldo_inicial=0'))

        self.stdout.write(self.style.SUCCESS('\nListo.'))
