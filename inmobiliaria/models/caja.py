from django.db import models
from django.contrib.auth.models import User

class Movimiento(models.Model):
    TIPO_CHOICES = [
        ('ingreso', 'Ingreso'),
        ('egreso', 'Egreso'),
    ]
    
    CATEGORIA_CHOICES = [
        ('alquiler', 'Alquiler'),
        ('venta', 'Venta'),
        ('comision', 'Comisión'),
        ('servicios', 'Servicios'),
        ('mantenimiento', 'Mantenimiento'),
        ('impuestos', 'Impuestos'),
        ('otros', 'Otros'),
    ]

    fecha = models.DateField(auto_now_add=True)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES)
    descripcion = models.TextField()
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    comprobante = models.FileField(upload_to='comprobantes/', null=True, blank=True)
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    sucursal = models.ForeignKey('Sucursal', on_delete=models.CASCADE)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-fecha', '-fecha_creacion']

    def __str__(self):
        return f"{self.fecha} - {self.get_tipo_display()} - ${self.monto}"
