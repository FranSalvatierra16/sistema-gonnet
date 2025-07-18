from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal

class TipoMovimientoCajaEnum(models.TextChoices):
    INGRESO = 'IN', 'Ingreso'
    EGRESO = 'EG', 'Egreso'

class TipoComprobanteEnum(models.TextChoices):
    RECIBO = 'RC', 'Recibo'
    LIQUIDACION = 'LQ', 'Liquidación'
    GASTO = 'GS', 'Gasto'
    OTRO = 'OT', 'Otro'

class TipoDescuentoEnum(models.TextChoices):
    PROPIETARIO = 'PR', 'Propietario'
    INQUILINO = 'IN', 'Inquilino'
    OFICINA = 'OF', 'Oficina'

class Caja(models.Model):
    ESTADO_CHOICES = [
        ('abierta', 'Abierta'),
        ('cerrada', 'Cerrada'),
    ]
    
    numero = models.AutoField(primary_key=True)
    sucursal = models.ForeignKey('Sucursal', on_delete=models.PROTECT)
    fecha_apertura = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    saldo_inicial = models.DecimalField(max_digits=10, decimal_places=2)
    saldo_final = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='abierta')
    usuario_apertura = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='cajas_abiertas')
    usuario_cierre = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='cajas_cerradas', null=True, blank=True)
    observaciones_apertura = models.TextField(blank=True)
    observaciones_cierre = models.TextField(blank=True)

    def get_saldo_actual(self):
        saldo = Decimal(str(self.saldo_inicial))
        movimientos = MovimientoCaja.objects.filter(caja=self)
        
        for movimiento in movimientos:
            if movimiento.tipo == 'ingreso':
                saldo += movimiento.monto_total
            else:
                saldo -= movimiento.monto_total
        return saldo

    def __str__(self):
        return f"Caja #{self.numero} - {self.sucursal}"
    
    class Meta:
        db_table = 'inmobiliaria_caja'
        ordering = ['-fecha_apertura']

class MovimientoCaja(models.Model):
    fecha = models.DateTimeField(auto_now_add=True)
    tipo = models.CharField(
        max_length=2,
        choices=TipoMovimientoCajaEnum.choices,
        default=TipoMovimientoCajaEnum.INGRESO
    )
    tipo_comprobante = models.CharField(
        max_length=2,
        choices=TipoComprobanteEnum.choices,
        default=TipoComprobanteEnum.RECIBO
    )
    numero_liquidacion = models.CharField(max_length=50, blank=True)
    concepto = models.CharField(max_length=200, blank=True)
    cuenta = models.ForeignKey('Cuenta', on_delete=models.SET_NULL, null=True, blank=True)
    propiedad = models.ForeignKey('Propiedad', on_delete=models.SET_NULL, null=True, blank=True)
    fecha_desde = models.DateField(null=True, blank=True)
    fecha_hasta = models.DateField(null=True, blank=True)
    monto_efectivo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    monto_cheque = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    monto_tarjeta = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    monto_deposito = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    destino_deposito = models.CharField(
        max_length=10,
        choices=[
            ('galicia', 'Galicia'),
            ('mp', 'Mercado Pago')
        ],
        null=True,
        blank=True
    )
    a_descontar = models.CharField(
        max_length=20, 
        choices=[
            ('propietario', 'Propietario'),
            ('oficina', 'Oficina')
        ],
        default='oficina'
    )
    sucursal = models.ForeignKey('Sucursal', on_delete=models.CASCADE)
    empleado = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    caja = models.ForeignKey('Caja', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"{self.get_tipo_display()} - ${self.monto_efectivo + self.monto_cheque + self.monto_tarjeta + self.monto_deposito}"
    
    class Meta:
        db_table = 'inmobiliaria_movimientocaja'
        ordering = ['-fecha']

class Concepto(models.Model):
    id = models.CharField(max_length=20, primary_key=True)  # ID personalizado
    nombre = models.CharField(max_length=100)
    fecha_creacion = models.DateTimeField(default=timezone.now)  # Cambiado de auto_now_add a default
    sucursal = models.ForeignKey('Sucursal', on_delete=models.CASCADE, related_name='conceptos', null=True)  # null=True temporalmente

    class Meta:
        verbose_name = "Concepto"
        verbose_name_plural = "Conceptos"
        ordering = ['id']
        unique_together = ['id', 'sucursal']  # ID único por sucursal

    def __str__(self):
        return f"{self.id} - {self.nombre}"

class Banco(models.Model):
    nombre = models.CharField(max_length=100)
    
    def __str__(self):
        return self.nombre

class Registro(models.Model):
    # Datos básicos
    interno_caja = models.CharField(max_length=50, unique=True)
    fecha = models.DateTimeField(auto_now_add=True)
    tipo = models.CharField(
        max_length=2,
        choices=TipoMovimientoCajaEnum.choices,
        default=TipoMovimientoCajaEnum.INGRESO
    )
    
    # Comprobante
    tipo_comprobante = models.CharField(
        max_length=2,
        choices=TipoComprobanteEnum.choices
    )
    fecha_comprobante = models.DateField()
    
    # Montos
    liquidacion = models.DecimalField(max_digits=10, decimal_places=2)
    efectivo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cheques = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tarjeta = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deposito = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    qr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Referencias
    cuenta = models.ForeignKey('Cuenta', on_delete=models.SET_NULL, null=True)
    propiedad = models.ForeignKey('Propiedad', on_delete=models.SET_NULL, null=True)
    concepto = models.ForeignKey(Concepto, on_delete=models.SET_NULL, null=True)
    
    # Fechas de período
    fecha_desde = models.DateField(null=True, blank=True)
    fecha_hasta = models.DateField(null=True, blank=True)
    
    # Opciones adicionales
    tipo_descuento = models.CharField(
        max_length=2,
        choices=TipoDescuentoEnum.choices,
        null=True,
        blank=True
    )
    con_iva = models.BooleanField(default=False)
    pasa_liquidaciones = models.BooleanField(default=False)
    
    # Metadata
    sucursal = models.ForeignKey('Sucursal', on_delete=models.CASCADE)
    empleado = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    
    def __str__(self):
        return f"Interno {self.interno_caja} - {self.get_tipo_display()}"

class Cuenta(models.Model):
    numero = models.CharField(max_length=50)
    nombre = models.CharField(max_length=200)
    
    def __str__(self):
        return f"{self.numero} - {self.nombre}"

class BancoTarjeta(models.Model):
    nombre = models.CharField(max_length=100)
    
    def __str__(self):
        return self.nombre
