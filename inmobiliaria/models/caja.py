from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
from django.conf import settings

class TipoMovimientoCajaEnum(models.TextChoices):
    INGRESO = 'IN', 'Ingreso'
    EGRESO = 'EG', 'Egreso'

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
        User, 
        on_delete=models.PROTECT,
        related_name='cajas_abiertas'
    )
    empleado_cierre = models.ForeignKey(
        User, 
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
        unique_together = ['sucursal', 'estado']  # Solo una caja abierta por sucursal

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

class ConceptoMovimiento(models.Model):
    nombre = models.CharField(max_length=100)
    tipo = models.CharField(
        max_length=2,
        choices=TipoMovimientoCajaEnum.choices,
        default=TipoMovimientoCajaEnum.INGRESO
    )

    def __str__(self):
        return self.nombre

class MovimientoCaja(models.Model):
    fecha = models.DateTimeField(auto_now_add=True)
    tipo = models.ForeignKey(ConceptoMovimiento, on_delete=models.PROTECT)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    descripcion = models.TextField(blank=True)
    sucursal = models.ForeignKey('Sucursal', on_delete=models.CASCADE)
    comprobante = models.CharField(max_length=100, blank=True)
    empleado = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"{self.tipo} - ${self.monto} - {self.fecha.strftime('%d/%m/%Y')}"

class ValePersonal(models.Model):
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('aprobado', 'Aprobado'),
        ('rechazado', 'Rechazado'),
        ('pagado', 'Pagado')
    ]
    
    sucursal = models.ForeignKey('Sucursal', on_delete=models.CASCADE)
    fecha = models.DateTimeField(auto_now_add=True)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    descripcion = models.TextField()
    estado = models.CharField(max_length=20, default='pendiente')
    empleado = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='vales_solicitados'
    )
    aprobado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='vales_aprobados'
    )
    motivo = models.TextField()
    movimiento_caja = models.OneToOneField(
        MovimientoCaja, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )

    def __str__(self):
        return f"Vale {self.empleado} - ${self.monto}"

class ComisionVenta(models.Model):
    fecha = models.DateTimeField(auto_now_add=True)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comisiones'
    )
    propiedad = models.ForeignKey('Propiedad', on_delete=models.CASCADE)
    venta = models.ForeignKey('VentaPropiedad', on_delete=models.PROTECT)
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2)
    pagada = models.BooleanField(default=False)
    movimiento_caja = models.OneToOneField(
        MovimientoCaja, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )

    def __str__(self):
        return f"Comisión {self.vendedor} - Venta #{self.venta.id}"

class PagoAlquiler(models.Model):
    alquiler = models.ForeignKey('AlquilerMeses', on_delete=models.PROTECT)
    fecha_pago = models.DateTimeField(auto_now_add=True)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    movimiento_caja = models.OneToOneField(MovimientoCaja, on_delete=models.PROTECT)
    comision = models.DecimalField(max_digits=5, decimal_places=2)
    notificado_propietario = models.BooleanField(default=False)
    fecha_notificacion = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Pago Alquiler #{self.alquiler.id} - ${self.monto}" 