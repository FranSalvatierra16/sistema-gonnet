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
    """Señal para crear automáticamente una caja y cuentas bancarias cuando se crea una sucursal"""
    if created:  # Solo si es una nueva sucursal
        User = get_user_model()
        usuario = User.objects.filter(is_superuser=True).first()
        if not usuario:
            usuario = User.objects.first()
            
        if usuario:
            instance.crear_caja_inicial(usuario)
        
        # Crear cuentas bancarias por defecto
        CuentaBancaria.crear_cuentas_por_defecto(instance)


class CuentaBancaria(models.Model):
    """
    Modelo para manejar cuentas bancarias por sucursal
    Permite agregar dinámicamente cuentas como Galicia, Mercado Pago, Banco Provincia, etc.
    """
    TIPO_CUENTA_CHOICES = [
        ('banco', 'Banco'),
        ('billetera', 'Billetera Digital'),
        ('efectivo', 'Efectivo'),
        ('otro', 'Otro'),
    ]
    
    sucursal = models.ForeignKey(
        Sucursal, 
        on_delete=models.CASCADE, 
        related_name='cuentas_bancarias'
    )
    nombre = models.CharField(
        max_length=100,
        help_text="Nombre de la cuenta (ej: Galicia, Mercado Pago, Banco Provincia)"
    )
    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CUENTA_CHOICES,
        default='banco'
    )
    numero_cuenta = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Número de cuenta (opcional)"
    )
    cbu_alias = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="CBU o Alias (opcional)"
    )
    activa = models.BooleanField(
        default=True,
        help_text="Si está activa aparecerá en los formularios de pago"
    )
    orden = models.PositiveIntegerField(
        default=0,
        help_text="Orden de aparición en los formularios"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['sucursal', 'orden', 'nombre']
        unique_together = ['sucursal', 'nombre']
        verbose_name = 'Cuenta Bancaria'
        verbose_name_plural = 'Cuentas Bancarias'
    
    def __str__(self):
        return f"{self.sucursal.nombre} - {self.nombre}"
    
    @classmethod
    def crear_cuentas_por_defecto(cls, sucursal):
        """Crear cuentas por defecto para una nueva sucursal"""
        cuentas_defecto = [
            {'nombre': 'Galicia', 'tipo': 'banco', 'orden': 1},
            {'nombre': 'Mercado Pago', 'tipo': 'billetera', 'orden': 2},
        ]
        
        for cuenta_data in cuentas_defecto:
            cls.objects.get_or_create(
                sucursal=sucursal,
                nombre=cuenta_data['nombre'],
                defaults={
                    'tipo': cuenta_data['tipo'],
                    'orden': cuenta_data['orden'],
                    'activa': True
                }
            )
