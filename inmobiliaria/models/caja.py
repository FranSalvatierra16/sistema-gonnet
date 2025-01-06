from django.db import models

class TipoMovimientoCajaEnum(models.TextChoices):
    INGRESO = 'IN', 'Ingreso'
    EGRESO = 'EG', 'Egreso'

class Caja(models.Model):
    saldo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Caja - Saldo: ${self.saldo}"

class TipoMovimientoCaja(models.Model):
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
    tipo = models.ForeignKey(TipoMovimientoCaja, on_delete=models.PROTECT)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    descripcion = models.TextField(blank=True)
    categoria = models.CharField(max_length=100, blank=True)
    comprobante = models.CharField(max_length=100, blank=True)
    sucursal = models.ForeignKey('Sucursal', on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.tipo} - ${self.monto} - {self.fecha.strftime('%d/%m/%Y')}"
