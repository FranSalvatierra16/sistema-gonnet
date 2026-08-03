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

    # Comisión de vendedores: valor por sucursal si el vendedor no tiene % propio
    porcentaje_comision_default = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Comisión vendedores (%)",
        help_text="Porcentaje por defecto para operaciones de esta sucursal. Si el vendedor tiene % propio, se usa el del vendedor.",
    )

    # Piso de comisión del productor por operación (se reparte según % de participación).
    # Ej.: $10.000 y 50/50 → $5.000 c/u. Si el % da más, se paga lo del %.
    comision_minima_operacion = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('10000.00'),
        verbose_name='Comisión mínima por operación',
        help_text=(
            'Importe mínimo total de comisión de productor por operación. '
            'Si hay varios productores, se reparte según su % de participación '
            '(p. ej. $10.000 al 50/50 → $5.000 c/u). 0 = sin mínimo.'
        ),
    )

    vacaciones_invierno_desde = models.DateField(
        null=True,
        blank=True,
        verbose_name='Vacaciones de invierno — desde',
        help_text='Día y mes de inicio (el año se ignora; se repite cada año). Vacío = todo julio.',
    )
    vacaciones_invierno_hasta = models.DateField(
        null=True,
        blank=True,
        verbose_name='Vacaciones de invierno — hasta',
        help_text='Día y mes de fin inclusive. Debe cargarse junto con «desde».',
    )

    def __str__(self):
        return self.nombre
    
    def _prefijo_recibo_formateado(self):
        """Prefijo con 3 dígitos (ej. 7 → 007)."""
        if self.prefijo_recibo is None:
            return ''
        return f'{int(self.prefijo_recibo):03d}'

    def generar_numero_recibo(self):
        """
        Genera el próximo número de recibo automáticamente.
        Formato: PPP-NN (ej: 007-01, 007-978).
        Usa UPDATE atómico para evitar números duplicados con instancias en caché.
        """
        from django.db.models import F

        if not self.usar_numeracion_automatica or self.prefijo_recibo is None:
            return None

        updated = Sucursal.objects.filter(pk=self.pk).update(
            ultimo_numero_recibo=F('ultimo_numero_recibo') + 1
        )
        if not updated:
            return None
        self.refresh_from_db(fields=['ultimo_numero_recibo'])
        return f'{self._prefijo_recibo_formateado()}-{self.ultimo_numero_recibo:02d}'

    def obtener_proximo_numero_recibo(self):
        """Próximo número sin incrementar el contador (vista previa)."""
        if not self.usar_numeracion_automatica or self.prefijo_recibo is None:
            return None

        proximo_numero = self.ultimo_numero_recibo + 1
        return f'{self._prefijo_recibo_formateado()}-{proximo_numero:02d}'

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
    titular = models.CharField(max_length=200, help_text="Titular de la cuenta")
    alias = models.CharField(
        max_length=100,
        help_text="CBU, CVU o alias para transferencias (ej: 22 dígitos o MI.ALIAS.MP)",
    )
    numero_cuenta = models.CharField(
        max_length=50,
        blank=True,
        help_text="Número de cuenta (opcional, solo referencia)",
    )
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
    saldo_inicial = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Saldo inicial',
        help_text='Saldo de corte al 08/06/2026 para reportes (no editable después de cargarlo).',
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Cuenta Bancaria"
        verbose_name_plural = "Cuentas Bancarias"
        ordering = ['nombre_banco', 'alias']
        
    def __str__(self):
        extra = (self.numero_cuenta or '').strip()
        sufijo = f" · Cuenta {extra}" if extra else ''
        return f"{self.nombre_banco} — {self.titular} — {self.alias}{sufijo}"
    
    @property
    def field_name(self):
        """Genera el nombre del campo dinámico para el formulario"""
        return f"monto_deposito_{self.id}"
