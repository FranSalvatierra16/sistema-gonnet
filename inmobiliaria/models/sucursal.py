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
    
    # Configuración de numeración de recibos
    prefijo_recibo = models.CharField(
        max_length=4, 
        blank=True, 
        null=True,
        help_text="Prefijo de 4 dígitos para numeración de recibos (ej: 0004)"
    )
    ultimo_numero_recibo = models.PositiveIntegerField(
        default=40000000,
        help_text="Último número de recibo generado (8 dígitos)"
    )
    usar_numeracion_automatica = models.BooleanField(
        default=False,
        help_text="Activar numeración automática de recibos"
    )

    def __str__(self):
        return self.nombre
    
    def generar_numero_recibo(self):
        """
        Genera el próximo número de recibo automáticamente
        Formato: XXXX-XXXXXXXX (ej: 0004-40000001)
        """
        if not self.usar_numeracion_automatica or not self.prefijo_recibo:
            return None
            
        # Incrementar el contador
        self.ultimo_numero_recibo += 1
        self.save(update_fields=['ultimo_numero_recibo'])
        
        # Formatear número: asegurar 8 dígitos
        numero_formateado = f"{self.ultimo_numero_recibo:08d}"
        
        # Retornar formato completo: XXXX-XXXXXXXX
        return f"{self.prefijo_recibo}-{numero_formateado}"
    
    def obtener_proximo_numero_recibo(self):
        """
        Obtiene el próximo número sin incrementar el contador (para preview)
        """
        if not self.usar_numeracion_automatica or not self.prefijo_recibo:
            return None
            
        proximo_numero = self.ultimo_numero_recibo + 1
        numero_formateado = f"{proximo_numero:08d}"
        return f"{self.prefijo_recibo}-{numero_formateado}"

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
