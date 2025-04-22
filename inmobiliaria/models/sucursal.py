from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal

class Sucursal(models.Model):
    nombre = models.CharField(max_length=50, unique=True)
    direccion = models.CharField(max_length=255)
    telefono = models.CharField(max_length=20)
    email = models.EmailField()

    def __str__(self):
        return self.nombre

    def crear_caja_inicial(self, usuario):
        """Método para crear una caja inicial para la sucursal"""
        from .caja import Caja
        
        # Verificar si ya existe una caja abierta
        if not Caja.objects.filter(sucursal=self, estado='abierta').exists():
            return Caja.objects.create(
                sucursal=self,
                fecha_apertura=timezone.now(),
                saldo_inicial=Decimal('0.00'),
                estado='abierta',
                usuario_apertura=usuario,
                observaciones_apertura=f'Caja inicial para sucursal {self.nombre}'
            )
        return None

@receiver(post_save, sender=Sucursal)
def crear_caja_automatica(sender, instance, created, **kwargs):
    """Señal para crear automáticamente una caja cuando se crea una sucursal"""
    if created:  # Solo si es una nueva sucursal
        User = get_user_model()
        usuario = User.objects.filter(is_superuser=True).first()
        if not usuario:
            usuario = User.objects.first()
            
        if usuario:
            instance.crear_caja_inicial(usuario)
