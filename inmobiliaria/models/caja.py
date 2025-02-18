from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal

class Caja(models.Model):
    ESTADO_CHOICES = [
        ('abierta', 'Abierta'),
        ('cerrada', 'Cerrada')
    ]
    
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

    def __str__(self):
        return f"Caja #{self.id} - {self.fecha_apertura.strftime('%d/%m/%Y')}"

class ConceptoMovimiento(models.Model):
    TIPO_CHOICES = [
        ('ingreso', 'Ingreso'),
        ('egreso', 'Egreso')
    ]
    
    nombre = models.CharField(max_length=100)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()})"

class MovimientoCaja(models.Model):
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('confirmado', 'Confirmado'),
        ('anulado', 'Anulado')
    ]
    
    caja = models.ForeignKey(Caja, on_delete=models.PROTECT, related_name='movimientos')
    concepto = models.ForeignKey(ConceptoMovimiento, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    descripcion = models.TextField()
    comprobante = models.FileField(upload_to='comprobantes/', null=True, blank=True)
    empleado = models.ForeignKey(User, on_delete=models.PROTECT)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='pendiente')
    referencia = models.CharField(max_length=100, blank=True)  # Para duplicados/referencias
    
    def __str__(self):
        return f"{self.concepto} - ${self.monto} - {self.fecha.strftime('%d/%m/%Y')}"

class ValePersonal(models.Model):
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('aprobado', 'Aprobado'),
        ('rechazado', 'Rechazado'),
        ('pagado', 'Pagado')
    ]
    
    empleado = models.ForeignKey(User, on_delete=models.PROTECT, related_name='vales')
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    fecha_aprobacion = models.DateTimeField(null=True, blank=True)
    aprobado_por = models.ForeignKey(
        User, 
        on_delete=models.PROTECT, 
        related_name='vales_aprobados',
        null=True, 
        blank=True
    )
    motivo = models.TextField()
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='pendiente')
    movimiento_caja = models.OneToOneField(
        MovimientoCaja, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )

    def __str__(self):
        return f"Vale {self.empleado} - ${self.monto}"

class ComisionVenta(models.Model):
    venta = models.ForeignKey('VentaPropiedad', on_delete=models.PROTECT)
    vendedor = models.ForeignKey(User, on_delete=models.PROTECT)
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_calculo = models.DateTimeField(auto_now_add=True)
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