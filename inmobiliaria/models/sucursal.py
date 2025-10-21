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
    prefijo_recibo = models.PositiveIntegerField(
        blank=True, 
        null=True,
        help_text="Número identificador para numeración de recibos (ej: 1, 2, 100)"
    )
    ultimo_numero_recibo = models.PositiveIntegerField(
        default=1,
        help_text="Último número de recibo generado (contador secuencial)"
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
        Formato: X-XX (ej: 1-01, 1-1000)
        """
        if not self.usar_numeracion_automatica or self.prefijo_recibo is None:
            return None
            
        # Incrementar el contador
        self.ultimo_numero_recibo += 1
        self.save(update_fields=['ultimo_numero_recibo'])
        
        # Retornar formato simple: X-XX
        return f"{self.prefijo_recibo}-{self.ultimo_numero_recibo:02d}"
    
    def obtener_proximo_numero_recibo(self):
        """
        Obtiene el próximo número sin incrementar el contador (para preview)
        """
        if not self.usar_numeracion_automatica or self.prefijo_recibo is None:
            return None
            
        proximo_numero = self.ultimo_numero_recibo + 1
        return f"{self.prefijo_recibo}-{proximo_numero:02d}"

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


class CuentaBancaria(models.Model):
    """
    Modelo para almacenar las cuentas bancarias de cada sucursal
    """
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='cuentas_bancarias')
    nombre_banco = models.CharField(max_length=100, help_text="Nombre del banco (ej: Banco Provincia)")
    alias = models.CharField(max_length=100, blank=True, help_text="Alias de la cuenta (ej: GONNET-ALQUILERES)")
    numero_cuenta = models.CharField(max_length=50, help_text="Número de cuenta bancaria")
    tipo_cuenta = models.CharField(
        max_length=20,
        choices=[
            ('banco', 'Banco'),
            ('billetera', 'Billetera Virtual'),
        ],
        default='banco',
        help_text="Tipo de cuenta"
    )
    activa = models.BooleanField(default=True, help_text="Si la cuenta está activa para usar")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Cuenta Bancaria"
        verbose_name_plural = "Cuentas Bancarias"
        ordering = ['nombre_banco', 'alias']
        
    def __str__(self):
        return f"{self.nombre_banco} - {self.alias} ({self.numero_cuenta})"
    
    @property
    def field_name(self):
        """Genera el nombre del campo dinámico para el formulario"""
        return f"monto_deposito_{self.id}"
