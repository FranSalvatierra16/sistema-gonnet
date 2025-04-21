from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal

class Caja(models.Model):
    ESTADO_CHOICES = [
        ('abierta', 'Abierta'),
        ('cerrada', 'Cerrada')
    ]
    
    numero = models.AutoField(primary_key=True)  # Número único de caja
    sucursal = models.ForeignKey(
        'Sucursal',
        on_delete=models.PROTECT,
        related_name='cajas'
    )
    fecha_apertura = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    saldo_inicial = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    saldo_final = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='abierta')
    usuario_apertura = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        related_name='cajas_abiertas'
    )
    usuario_cierre = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        related_name='cajas_cerradas',
        null=True,
        blank=True
    )
    observaciones_apertura = models.TextField(blank=True)
    observaciones_cierre = models.TextField(blank=True)
    
    def __str__(self):
        return f"Caja #{self.numero} - {self.sucursal} - {self.estado}"
    
    class Meta:
        db_table = 'inmobiliaria_caja'
        ordering = ['-fecha_apertura']

    def get_saldo_actual(self):
        saldo = self.saldo_inicial
        for movimiento in self.movimientos.filter(estado='confirmado'):
            if movimiento.tipo == 'ingreso':
                saldo += movimiento.monto
            else:
                saldo -= movimiento.monto
        return saldo

class MovimientoCaja(models.Model):
    TIPO_CHOICES = [
        ('ingreso', 'Ingreso'),
        ('egreso', 'Egreso')
    ]
    
    caja = models.ForeignKey(
        Caja,
        on_delete=models.PROTECT,
        related_name='movimientos'
    )
    fecha = models.DateTimeField(auto_now_add=True)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    concepto = models.CharField(max_length=200)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    comprobante = models.CharField(max_length=50, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT
    )
    observaciones = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.get_tipo_display()} - ${self.monto} - {self.concepto}"
    
    class Meta:
        db_table = 'inmobiliaria_movimientocaja'
        ordering = ['-fecha']
