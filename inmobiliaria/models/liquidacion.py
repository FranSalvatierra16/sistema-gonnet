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

    MONEDA_CHOICES = [
        ('ARS', 'Pesos (ARS)'),
        ('USD', 'Dólares (USD)'),
    ]
    moneda = models.CharField(
        max_length=3,
        choices=MONEDA_CHOICES,
        default='ARS',
        verbose_name='Moneda',
        help_text='Moneda en la que se expresan los montos de esta liquidación.',
    )
    cotizacion_dolar = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Cotización del dólar',
        help_text='Cotización ARS por USD del día al crear la liquidación (opcional).',
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
        help_text="Monto final a pagar al propietario (monto_propietario − gastos − fondo de mantenimiento; la cochera no se incluye)"
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

    def _recalcular_monto_a_pagar_fields(self):
        """Neto al propietario: alquiler + ingresos − egresos − fondo (cochera y comisiones aparte)."""
        prop = self.monto_propietario if self.monto_propietario is not None else Decimal('0')
        fondo = self.monto_fondo_mantenimiento if self.monto_fondo_mantenimiento is not None else Decimal('0')
        ingresos = Decimal('0')
        egresos = Decimal('0')
        if self.pk:
            for g in self.gastos.filter(aceptado=True):
                m = g.monto if g.monto is not None else Decimal('0')
                if g.tipo_movimiento == 'ingreso':
                    ingresos += m
                else:
                    egresos += m
        else:
            egresos = self.monto_gastos if self.monto_gastos is not None else Decimal('0')
        neto = prop - egresos - fondo + ingresos
        self.monto_gastos = egresos
        self.monto_a_pagar = neto.quantize(Decimal('0.01'))

    def save(self, *args, **kwargs):
        self._recalcular_monto_a_pagar_fields()

        # Calcular monto de inmobiliaria solo si no fue informado (cochera no participa del reparto inmobiliaria)
        if (
            self.monto_total_operacion
            and self.monto_propietario is not None
            and self.monto_inmobiliaria is None
        ):
            self.monto_inmobiliaria = self.monto_total_operacion - self.monto_propietario

        super().save(*args, **kwargs)

    def calcular_monto_a_pagar(self):
        """Recalcula el monto a pagar según movimientos aceptados y fondo de mantenimiento."""
        self._recalcular_monto_a_pagar_fields()
        self.save(update_fields=['monto_gastos', 'monto_a_pagar'])
        self.sync_gasto_saldo_negativo_pendiente()

    def sync_gasto_saldo_negativo_pendiente(self):
        """Si el saldo es negativo, genera gasto pendiente para descontar en la próxima liquidación."""
        return sync_gasto_saldo_negativo_liquidacion(self)

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
    TIPO_MOVIMIENTO_CHOICES = [
        ('egreso', 'Egreso'),
        ('ingreso', 'Ingreso'),
    ]
    EFECTO_INQUILINO_CHOICES = [
        ('favor', 'A favor del inquilino'),
        ('contra', 'En contra del inquilino'),
    ]
    OPERACION_MONTO_CHOICES = [
        ('resta', 'Resta'),
        ('suma', 'Suma'),
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
        help_text="Nombre del concepto de caja"
    )
    concepto_caja_id = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='Concepto caja',
        help_text='ID del concepto del catálogo de caja',
    )
    monto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Monto"
    )
    moneda = models.CharField(
        max_length=3,
        choices=LiquidacionPropietario.MONEDA_CHOICES,
        default='ARS',
        verbose_name='Moneda',
    )
    tipo_movimiento = models.CharField(
        max_length=10,
        choices=TIPO_MOVIMIENTO_CHOICES,
        default='egreso',
        verbose_name='Tipo de movimiento',
    )
    efecto_inquilino = models.CharField(
        max_length=10,
        choices=EFECTO_INQUILINO_CHOICES,
        default='contra',
        verbose_name='Efecto sobre el inquilino',
    )
    operacion_monto = models.CharField(
        max_length=10,
        choices=OPERACION_MONTO_CHOICES,
        default='resta',
        verbose_name='Operación',
        help_text='Suma aumenta lo que se paga al propietario; resta lo descuenta.',
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

    def monto_signed(self):
        """Impacto neto del movimiento sobre el monto a pagar al propietario."""
        m = self.monto if self.monto is not None else Decimal('0')
        if self.tipo_movimiento == 'ingreso':
            return m
        return -m

    def save(self, *args, **kwargs):
        if self.tipo_movimiento == 'ingreso':
            self.operacion_monto = 'suma'
            self.efecto_inquilino = 'favor'
        else:
            self.operacion_monto = 'resta'
            self.efecto_inquilino = 'contra'
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


def marcador_gasto_liquidacion_pendiente(liquidacion_id):
    return f'liquidacion_pendiente_origen:{int(liquidacion_id)}'


def asegurar_gastos_saldo_negativo_propiedad(propiedad, sucursal=None):
    """
    Genera/actualiza gastos pendientes por liquidaciones con saldo negativo de la propiedad.
    Se invoca al listar pendientes para crear liquidación (no hace falta abrir cada detalle).
    """
    if not propiedad:
        return

    qs = (
        LiquidacionPropietario.objects.filter(propiedad=propiedad)
        .exclude(estado='cancelada')
        .prefetch_related('gastos')
    )
    if sucursal is not None:
        qs = qs.filter(sucursal=sucursal)

    for liq in qs:
        monto_prev = liq.monto_a_pagar
        gastos_prev = liq.monto_gastos
        liq._recalcular_monto_a_pagar_fields()
        if monto_prev != liq.monto_a_pagar or gastos_prev != liq.monto_gastos:
            liq.save(update_fields=['monto_gastos', 'monto_a_pagar'])
        if (liq.monto_a_pagar or Decimal('0')) < Decimal('0'):
            sync_gasto_saldo_negativo_liquidacion(liq)


def sync_gasto_saldo_negativo_liquidacion(liquidacion):
    """
    Liquidación con saldo negativo (propietario debe a la inmobiliaria):
    crea/actualiza un GastoPropietario pendiente para descontar en la próxima liquidación.
    """
    if not liquidacion or not liquidacion.pk:
        return None

    marker = marcador_gasto_liquidacion_pendiente(liquidacion.id)
    estados_con_deuda_descontable = ('pendiente', 'cerrada', 'pagada', 'oficina', 'procesada')

    pendientes_qs = GastoPropietario.objects.filter(
        liquidacion__isnull=True,
        sucursal=liquidacion.sucursal,
        observaciones__contains=marker,
    )
    cobrado_en_otra = GastoPropietario.objects.filter(
        observaciones__contains=marker,
        liquidacion__isnull=False,
    ).exists()

    if liquidacion.estado == 'cancelada' or liquidacion.estado not in estados_con_deuda_descontable:
        pendientes_qs.delete()
        return None

    if cobrado_en_otra:
        pendientes_qs.delete()
        return None

    monto = liquidacion.monto_a_pagar
    if monto is None or monto >= Decimal('0'):
        pendientes_qs.delete()
        return None

    deuda = abs(monto).quantize(Decimal('0.01'))
    if deuda <= Decimal('0'):
        pendientes_qs.delete()
        return None

    fp = liquidacion.fecha_procesamiento or liquidacion.fecha_creacion
    try:
        fecha_g = timezone.localtime(fp).date() if fp else timezone.now().date()
    except Exception:
        fecha_g = timezone.now().date()

    obs = (
        f'{marker}\n'
        f'Saldo en contra del propietario'
    )

    existing = pendientes_qs.first()
    if existing:
        existing.monto = deuda
        existing.descripcion = f'Liquidación Nº {liquidacion.id} — saldo en contra propietario'
        existing.propietario = liquidacion.propietario
        existing.propiedad = liquidacion.propiedad
        existing.moneda = getattr(liquidacion, 'moneda', 'ARS') or 'ARS'
        existing.tipo_movimiento = 'egreso'
        existing.fecha_gasto = fecha_g
        existing.observaciones = obs
        existing.save()
        return existing

    return GastoPropietario.objects.create(
        liquidacion=None,
        propietario=liquidacion.propietario,
        propiedad=liquidacion.propiedad,
        descripcion=f'Liquidación Nº {liquidacion.id} — saldo en contra propietario',
        monto=deuda,
        moneda=getattr(liquidacion, 'moneda', 'ARS') or 'ARS',
        tipo_movimiento='egreso',
        observaciones=obs,
        fecha_gasto=fecha_g,
        aceptado=False,
        sucursal=liquidacion.sucursal,
    )


def eliminar_gastos_pendientes_liquidacion_origen(liquidacion_id, sucursal=None):
    """Quita gastos pendientes generados por una liquidación (p. ej. al borrar la liquidación)."""
    marker = marcador_gasto_liquidacion_pendiente(liquidacion_id)
    qs = GastoPropietario.objects.filter(
        liquidacion__isnull=True,
        observaciones__contains=marker,
    )
    if sucursal is not None:
        qs = qs.filter(sucursal=sucursal)
    qs.delete()

