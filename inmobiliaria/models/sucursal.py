from django.db import models

class Sucursal(models.Model):
    SUCURSALES = [
        ('MORENO', 'Sucursal Moreno'),
        ('COLON', 'Sucursal Colon'),
    ]

    nombre = models.CharField(max_length=50, choices=SUCURSALES, unique=True)
    direccion = models.CharField(max_length=255)
    telefono = models.CharField(max_length=20)
    email = models.EmailField()
    
    class Meta:
        verbose_name = "Sucursal"
        verbose_name_plural = "Sucursales"

    def __str__(self):
        return self.get_nombre_display()
