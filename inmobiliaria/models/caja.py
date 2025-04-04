from django.db import models
from django.conf import settings
from django.utils import timezone

class Caja(models.Model):
    ESTADO_CHOICES = [
        ('abierta', 'Abierta'),
        ('cerrada', 'Cerrada')
    ]
    
    sucursal = models.ForeignKey(
        'Sucursal',
        on_delete=models.PROTECT,
        related_name='cajas'
    )
    fecha_apertura = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    empleado_apertura = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # Cambiado de User a AUTH_USER_MODEL
        on_delete=models.PROTECT,
        related_name='cajas_abiertas'
    )
    empleado_cierre = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # Cambiado de User a AUTH_USER_MODEL
        on_delete=models.PROTECT,
        related_name='cajas_cerradas',
        null=True, 
        blank=True
    )
    saldo_inicial = models.DecimalField(max_digits=10, decimal_places=2)
    saldo_final = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='abierta')
    observaciones = models.TextField(blank=True)

    class Meta:
        unique_together = ['sucursal', 'estado']

    def __str__(self):
        return f"Caja {self.sucursal} - {self.fecha_apertura.strftime('%d/%m/%Y')}"

    def get_saldo_actual(self):
        saldo = self.saldo_inicial
        for movimiento in self.movimientos.filter(estado='confirmado'):
            if movimiento.tipo == 'ingreso':
                saldo += movimiento.monto
            else:
                saldo -= movimiento.monto
        return saldo
