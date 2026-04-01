"""
Lógica compartida para dejar la caja de una sucursal en cero: cierra abiertas y abre una nueva sin movimientos.
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from inmobiliaria.models import Caja


def reset_caja_sucursal_desde_cero(sucursal, usuario, observacion_cierre_extra='[Cierre automático reset caja]'):
    """
    Cierra todas las cajas abiertas de la sucursal y crea una nueva con saldo_inicial=0.

    No elimina movimientos: quedan asociados a las cajas cerradas.

    Returns:
        tuple: (nueva_caja, lista de cajas cerradas)
    """
    abiertas = list(
        Caja.objects.filter(sucursal=sucursal, estado='abierta').order_by('numero')
    )
    cerradas = []

    with transaction.atomic():
        for caja in abiertas:
            saldo_final = caja.get_saldo_actual()
            caja.fecha_cierre = timezone.now()
            caja.estado = 'cerrada'
            caja.saldo_final = saldo_final
            caja.usuario_cierre = usuario
            extra = observacion_cierre_extra.strip()
            if extra:
                caja.observaciones_cierre = (
                    (caja.observaciones_cierre or '').strip() + '\n' + extra
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
            cerradas.append(caja)

        nueva = Caja.objects.create(
            sucursal=sucursal,
            saldo_inicial=Decimal('0.00'),
            estado='abierta',
            usuario_apertura=usuario,
            observaciones_apertura='Apertura tras reset de caja (saldo desde cero)',
        )

    return nueva, cerradas
