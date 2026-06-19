from django.db import models
from django.db.models import Sum
from django.utils import timezone
from decimal import Decimal
from .persona import Propietario
from .propiedad import Reserva, Propiedad
from .caja import MovimientoCaja
from .contrato import ContratoAlquiler


class LiquidacionPropietario(models.Model):
    """
    Modelo para gestionar las liquidaciones de pagos a propietarios.
    Cuando se alquila una propiedad, parte del dinero va al propietario y parte a la inmobiliaria.
    """
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('cerrada', 'Cerrada'),
        ('pagada', 'Pagada'),
        ('oficina', 'Oficina'),
        ('procesada', 'Procesada (legacy)'),
        ('cancelada', 'Cancelada'),
    ]

    # Relaciones
    propietario = models.ForeignKey(
        Propietario,
        on_delete=models.CASCADE,
        related_name='liquidaciones',
        verbose_name="Propietario"
    )
    propiedad = models.ForeignKey(
        Propiedad,
        on_delete=models.CASCADE,
        related_name='liquidaciones',
        verbose_name="Propiedad"
    )
    reserva = models.ForeignKey(
        Reserva,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='liquidaciones',
        verbose_name="Reserva"
    )
    contrato = models.ForeignKey(
        ContratoAlquiler,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='liquidaciones',
        verbose_name="Contrato"
    )
    movimiento_caja = models.ForeignKey(
        MovimientoCaja,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='liquidaciones',
        verbose_name="Movimiento de Caja"
    )

    # Montos
    monto_total_operacion = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Monto Total de la Operación",
        help_text="Monto total recibido del inquilino"
    )
    monto_propietario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Monto para el Propietario",
        help_text="Monto que corresponde pagar al propietario"
    )
    monto_inmobiliaria = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Monto para la Inmobiliaria",
        help_text="Monto que corresponde a la inmobiliaria (comisión)"
    )
    monto_cochera = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Monto cochera",
        help_text="Importe de cochera en la liquidación (opcional)",
    )
    monto_fondo_mantenimiento = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Fondo de mantenimiento",
        help_text="Importe de fondo de mantenimiento en la liquidación (opcional)",
    )
    comision_locador = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Comisión locador",
        help_text="Primera operación (9/24 meses): comisión a cargo del locador.",
    )
    comision_locatario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name="Comisión locatario",
        help_text="Primera operación (9/24 meses): honorarios / comisión locatario.",
    )
    monto_gastos = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Total de Gastos",
        help_text="Suma de gastos aceptados del propietario"
    )
    monto_a_pagar = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Monto a Pagar",
        help_text="Monto final a pagar al propietario (monto_propietario + cochera − gastos − fondo de mantenimiento)"
    )

    # Estado y fechas
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='pendiente',
        verbose_name="Estado"
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Creación"
    )
    fecha_procesamiento = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de Procesamiento"
    )
    fecha_desde = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha Desde",
        help_text="Fecha de inicio del período liquidado"
    )
    fecha_hasta = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha Hasta",
        help_text="Fecha de fin del período liquidado"
    )

    # Información adicional
    observaciones = models.TextField(
        blank=True,
        verbose_name="Observaciones"
    )
    # Reservas/contratos incluidos cuando la liquidación agrupa varias filas (formulario /liquidaciones/crear/)
    operaciones_incluidas = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Operaciones incluidas",
        help_text='Lista de {"tipo": "reserva"|"contrato", "id": <pk>} para excluir del listado de pendientes',
    )
    sucursal = models.ForeignKey(
        'Sucursal',
        on_delete=models.CASCADE,
        related_name='liquidaciones',
        verbose_name="Sucursal"
    )
    usuario_creacion = models.ForeignKey(
        'Vendedor',
        on_delete=models.SET_NULL,
        null=True,
        related_name='liquidaciones_creadas',
        verbose_name="Usuario que creó la liquidación"
    )

    def save(self, *args, **kwargs):
        # Neto al propietario: alquiler + cochera, menos gastos y fondo retenido
        prop = self.monto_propietario if self.monto_propietario is not None else Decimal('0')
        cochera = self.monto_cochera if self.monto_cochera is not None else Decimal('0')
        gastos = self.monto_gastos if self.monto_gastos is not None else Decimal('0')
        fondo = self.monto_fondo_mantenimiento if self.monto_fondo_mantenimiento is not None else Decimal('0')
        neto = prop + cochera - gastos - fondo
        self.monto_a_pagar = neto if neto > 0 else Decimal('0')

        # Calcular monto de inmobiliaria solo si no fue informado (cochera no participa del reparto inmobiliaria)
        if (
            self.monto_total_operacion
            and self.monto_propietario is not None
            and self.monto_inmobiliaria is None
        ):
            self.monto_inmobiliaria = self.monto_total_operacion - self.monto_propietario

        super().save(*args, **kwargs)

    def calcular_monto_a_pagar(self):
        """Recalcula el monto a pagar según gastos aceptados y fondo de mantenimiento."""
        gastos_aceptados = self.gastos.filter(aceptado=True).aggregate(
            total=models.Sum('monto')
        )['total'] or Decimal('0')
        fondo = self.monto_fondo_mantenimiento or Decimal('0')
        cochera = self.monto_cochera or Decimal('0')
        self.monto_gastos = gastos_aceptados
        neto = self.monto_propietario + cochera - gastos_aceptados - fondo
        self.monto_a_pagar = neto if neto > 0 else Decimal('0')
        self.save(update_fields=['monto_gastos', 'monto_a_pagar'])

    def __str__(self):
        return f"Liquidación {self.id} - {self.propietario} - {self.propiedad} - ${self.monto_a_pagar}"

    class Meta:
        verbose_name = "Liquidación Propietario"
        verbose_name_plural = "Liquidaciones Propietarios"
        ordering = ['-fecha_creacion']


class GastoPropietario(models.Model):
    """
    Modelo para registrar gastos del propietario (luz, gas, etc.)
    que se pueden descontar de la liquidación.
    """
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('aceptado', 'Aceptado'),
        ('rechazado', 'Rechazado'),
    ]

    liquidacion = models.ForeignKey(
        LiquidacionPropietario,
        on_delete=models.CASCADE,
        related_name='gastos',
        verbose_name="Liquidación",
        null=True,
        blank=True,
        help_text="Si está vacío, es un gasto pendiente del propietario"
    )
    propietario = models.ForeignKey(
        Propietario,
        on_delete=models.CASCADE,
        related_name='gastos_pendientes',
        verbose_name="Propietario",
        null=True,
        blank=True,
        help_text="Propietario al que pertenece el gasto (si no hay liquidación)"
    )
    propiedad = models.ForeignKey(
        Propiedad,
        on_delete=models.CASCADE,
        related_name='gastos_pendientes',
        verbose_name="Propiedad",
        null=True,
        blank=True,
        help_text="Propiedad relacionada con el gasto"
    )
    descripcion = models.CharField(
        max_length=200,
        verbose_name="Descripción",
        help_text="Descripción del gasto (ej: Luz, Gas, Mantenimiento)"
    )
    monto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Monto"
    )
    fecha_gasto = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha del Gasto"
    )
    aceptado = models.BooleanField(
        default=False,
        verbose_name="Aceptado",
        help_text="Si está aceptado, se descuenta del monto a pagar"
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Creación"
    )
    observaciones = models.TextField(
        blank=True,
        verbose_name="Observaciones"
    )
    sucursal = models.ForeignKey(
        'Sucursal',
        on_delete=models.CASCADE,
        related_name='gastos_propietario',
        verbose_name="Sucursal",
        null=True,
        blank=True
    )

    def save(self, *args, **kwargs):
        # Si no hay liquidación pero hay propietario, obtener la sucursal del propietario
        if not self.sucursal and self.propietario:
            self.sucursal = self.propietario.sucursal
        elif not self.sucursal and self.liquidacion:
            self.sucursal = self.liquidacion.sucursal
        super().save(*args, **kwargs)
        # Recalcular monto a pagar de la liquidación si está asociado
        if self.liquidacion:
            self.liquidacion.calcular_monto_a_pagar()

    def __str__(self):
        estado = "Aceptado" if self.aceptado else "Pendiente"
        return f"{self.descripcion} - ${self.monto} ({estado})"

    class Meta:
        verbose_name = "Gasto Propietario"
        verbose_name_plural = "Gastos Propietarios"
        ordering = ['-fecha_creacion']

