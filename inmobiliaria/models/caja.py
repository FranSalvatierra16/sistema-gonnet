from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal

class TipoMovimientoCajaEnum(models.TextChoices):
    INGRESO = 'IN', 'Ingreso'
    EGRESO = 'EG', 'Egreso'

class Caja(models.Model):
    ESTADO_CHOICES = [
        ('abierta', 'Abierta'),
        ('cerrada', 'Cerrada')
    ]
    
    numero = models.AutoField(primary_key=True)
    sucursal = models.ForeignKey(
        'Sucursal',
        on_delete=models.PROTECT,
        related_name='cajas'
    )
    fecha_apertura = models.DateTimeField(default=timezone.now)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    saldo_inicial = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    saldo_final = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='abierta')
    usuario_apertura = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='cajas_abiertas'
    )
    usuario_cierre = models.ForeignKey(
        settings.AUTH_USER_MODEL,
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
        ('egreso', 'Egreso'),
    ]
    
    TIPO_COMPROBANTE_CHOICES = [
        ('recibo', 'Recibo'),
        ('liquidacion', 'Liquidación'),
        ('gasto', 'Gasto'),
        ('otro', 'Otro'),
    ]
    
    A_DESCONTAR_CHOICES = [
        ('propietario', 'Propietario'),
        ('inquilino', 'Inquilino'),
        ('oficina', 'Oficina'),
    ]
    
    caja = models.ForeignKey('Caja', on_delete=models.PROTECT, related_name='movimientos')
    fecha = models.DateTimeField(default=timezone.now)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    tipo_comprobante = models.CharField(max_length=20, choices=TIPO_COMPROBANTE_CHOICES)
    numero_liquidacion = models.CharField(max_length=50, blank=True)
    cuenta = models.ForeignKey('Cuenta', on_delete=models.PROTECT, null=True, blank=True)
    propiedad = models.ForeignKey('Propiedad', on_delete=models.PROTECT, null=True, blank=True)
    concepto = models.ForeignKey('Concepto', on_delete=models.PROTECT)
    
    monto_efectivo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    monto_cheque = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    monto_tarjeta = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    monto_deposito = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    monto_qr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    banco = models.ForeignKey('Banco', on_delete=models.PROTECT, null=True, blank=True)
    a_descontar = models.CharField(max_length=20, choices=A_DESCONTAR_CHOICES, null=True, blank=True)
    con_iva = models.BooleanField(default=False)
    pasa_liquidaciones = models.BooleanField(default=False)
    
    fecha_desde = models.DateField(null=True, blank=True)
    fecha_hasta = models.DateField(null=True, blank=True)
    
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    observaciones = models.TextField(blank=True)
    
    @property
    def monto_total(self):
        return (
            self.monto_efectivo +
            self.monto_cheque +
            self.monto_tarjeta +
            self.monto_deposito +
            self.monto_qr
        )

    def __str__(self):
        return f"{self.get_tipo_display()} - ${self.monto_total} - {self.concepto}"
    
    class Meta:
        db_table = 'inmobiliaria_movimientocaja'
        ordering = ['-fecha']

class Concepto(models.Model):
    nombre = models.CharField(max_length=200)
    
    def __str__(self):
        return self.nombre

class Banco(models.Model):
    nombre = models.CharField(max_length=100)
    
    def __str__(self):
        return self.nombre
