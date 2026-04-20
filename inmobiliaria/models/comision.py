from django.db import models
from django.utils import timezone
from decimal import Decimal
from .persona import Vendedor
from .propiedad import Reserva
from .caja import MovimientoCaja

# Roles para varias líneas de comisión por movimiento (p. ej. honorarios)
ROL_COMISION_GENERAL = 'general'
ROL_COMISION_FICHAJE = 'fichaje'
ROL_COMISION_OP_DIA = 'operacion_dia'
ROL_COMISION_OP_INVIERNO = 'operacion_invierno'
ROL_COMISION_OP_24 = 'operacion_24_meses'


def clasificar_tipo_operacion_reserva(reserva):
    """
    Clasifica la reserva para reglas de comisión: alquiler largo (24), invierno o por día.
    Criterios alineados con porcentaje_comision_para_reserva / invierno en Vendedor.
    """
    prop = reserva.propiedad
    try:
        dias = (reserva.fecha_fin - reserva.fecha_inicio).days
    except (TypeError, AttributeError):
        dias = 0
    if dias >= 600:
        return '24'
    if (
        dias < 600
        and dias >= 14
        and getattr(prop, 'habilitar_invierno', False)
    ):
        try:
            mes_ini = reserva.fecha_inicio.month
        except AttributeError:
            mes_ini = 0
        if mes_ini in (4, 5, 6, 7, 8, 9, 10):
            return 'invierno'
    return 'dia'


def pct_comision_normal_alquiler_dia(vendedor):
    """% comisión 'normal' (alquiler por día): campo comision o default de sucursal."""
    if vendedor.comision is not None:
        return vendedor.comision
    default = getattr(vendedor.sucursal, 'porcentaje_comision_default', None)
    if default is not None:
        return default
    return Decimal('0')


def registrar_comisiones_honorarios_movimiento_reserva(reserva, movimiento_caja, honorarios_monto):
    """
    Cuando en el movimiento hay honorarios (concepto 25), registra:
    - Comisión por primer/segundo fichaje del vendedor de la operación sobre el monto de honorarios.
    - Según tipo de operación: % invierno o % 24 meses sobre honorarios, o % comisión normal sobre precio total (día).
    Si honorarios_monto es 0, no hace nada (el llamador usa la comisión general única sobre la reserva).
    """
    if (
        not reserva
        or not reserva.vendedor
        or not movimiento_caja
        or honorarios_monto is None
        or honorarios_monto <= 0
    ):
        return []

    if getattr(reserva, 'eliminada', False) or getattr(reserva, 'estado', None) == 'cancelada':
        return []

    vend = reserva.vendedor
    prop = reserva.propiedad
    creadas = []

    tipo_fichaje = getattr(prop, 'tipo_fichaje', None) or 'primer'
    if tipo_fichaje == 'segundo':
        pct_fichaje = vend.comision_segundo_fichaje
    else:
        pct_fichaje = vend.comision_primer_fichaje

    if pct_fichaje is not None and pct_fichaje > 0:
        c = ComisionVendedor.crear_comision_linea(
            vendedor=vend,
            reserva=reserva,
            movimiento_caja=movimiento_caja,
            monto_base=honorarios_monto,
            porcentaje_comision=pct_fichaje,
            concepto=f'Op. {reserva.id} — comisión fichaje ({tipo_fichaje}) sobre honorarios',
            rol_comision=ROL_COMISION_FICHAJE,
        )
        if c:
            creadas.append(c)

    tipo_op = clasificar_tipo_operacion_reserva(reserva)

    if tipo_op == 'dia':
        pct = pct_comision_normal_alquiler_dia(vend)
        base = reserva.precio_total or Decimal('0')
        if pct > 0 and base > 0:
            c = ComisionVendedor.crear_comision_linea(
                vendedor=vend,
                reserva=reserva,
                movimiento_caja=movimiento_caja,
                monto_base=base,
                porcentaje_comision=pct,
                concepto=f'Op. {reserva.id} — comisión alquiler por día (sobre total reserva)',
                rol_comision=ROL_COMISION_OP_DIA,
            )
            if c:
                creadas.append(c)

    elif tipo_op == 'invierno':
        pct = vend.comision_invierno
        if pct is not None and pct > 0:
            c = ComisionVendedor.crear_comision_linea(
                vendedor=vend,
                reserva=reserva,
                movimiento_caja=movimiento_caja,
                monto_base=honorarios_monto,
                porcentaje_comision=pct,
                concepto=f'Op. {reserva.id} — comisión invierno (sobre honorarios)',
                rol_comision=ROL_COMISION_OP_INVIERNO,
            )
            if c:
                creadas.append(c)

    elif tipo_op == '24':
        pct = vend.comision_alquiler_24_meses
        if pct is not None and pct > 0:
            c = ComisionVendedor.crear_comision_linea(
                vendedor=vend,
                reserva=reserva,
                movimiento_caja=movimiento_caja,
                monto_base=honorarios_monto,
                porcentaje_comision=pct,
                concepto=f'Op. {reserva.id} — comisión alquiler 24 meses (sobre honorarios)',
                rol_comision=ROL_COMISION_OP_24,
            )
            if c:
                creadas.append(c)

    return creadas


class ComisionVendedorQuerySet(models.QuerySet):
    """
    Comisiones que deben sumar en totales: no anuladas y cuya reserva sigue vigente.
    """

    def que_suman(self):
        return (
            self.exclude(estado='cancelada')
            .exclude(reserva__estado='cancelada')
            .exclude(reserva__eliminada=True)
        )


class ComisionVendedor(models.Model):
    """
    Modelo para registrar las comisiones ganadas por los vendedores en cada operación
    """
    vendedor = models.ForeignKey(
        Vendedor, 
        on_delete=models.CASCADE, 
        related_name='comisiones',
        verbose_name="Vendedor"
    )
    reserva = models.ForeignKey(
        Reserva, 
        on_delete=models.CASCADE, 
        related_name='comisiones_vendedor',
        verbose_name="Reserva"
    )
    movimiento_caja = models.ForeignKey(
        MovimientoCaja,
        on_delete=models.CASCADE,
        related_name='comisiones_vendedor',
        verbose_name="Movimiento de Caja",
        null=True,
        blank=True
    )
    
    # Montos de la operación
    monto_total_operacion = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        verbose_name="Monto Total de la Operación"
    )
    porcentaje_comision = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        verbose_name="Porcentaje de Comisión (%)"
    )
    monto_comision = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        verbose_name="Monto de Comisión"
    )
    
    # Información adicional
    concepto_operacion = models.CharField(
        max_length=200,
        verbose_name="Concepto de la Operación"
    )
    rol_comision = models.CharField(
        max_length=32,
        default=ROL_COMISION_GENERAL,
        verbose_name='Rol de comisión',
        help_text='Permite varias líneas por movimiento (fichaje, operación día/invierno/24 meses).',
    )
    fecha_operacion = models.DateTimeField(
        default=timezone.now,
        verbose_name="Fecha de la Operación"
    )
    fecha_calculo = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Cálculo"
    )
    
    # Estado de la comisión
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('confirmada', 'Confirmada'),
        ('pagada', 'Pagada'),
        ('cancelada', 'Cancelada'),
    ]
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='confirmada',
        verbose_name="Estado"
    )
    
    # Observaciones
    observaciones = models.TextField(
        blank=True,
        verbose_name="Observaciones"
    )
    
    objects = ComisionVendedorQuerySet.as_manager()

    class Meta:
        verbose_name = "Comisión de Vendedor"
        verbose_name_plural = "Comisiones de Vendedores"
        ordering = ['-fecha_operacion']
        unique_together = ['vendedor', 'reserva', 'movimiento_caja', 'rol_comision']
    
    def __str__(self):
        return f"Comisión {self.id} - {self.vendedor.nombre_completo_vendedor()} - ${self.monto_comision}"
    
    def save(self, *args, **kwargs):
        # Calcular automáticamente el monto de comisión si no está definido
        if not self.monto_comision and self.monto_total_operacion and self.porcentaje_comision:
            self.monto_comision = (self.monto_total_operacion * self.porcentaje_comision) / Decimal('100')
        super().save(*args, **kwargs)
    
    @classmethod
    def crear_comision_linea(
        cls,
        vendedor,
        reserva,
        movimiento_caja,
        monto_base,
        porcentaje_comision,
        concepto,
        rol_comision=ROL_COMISION_GENERAL,
    ):
        """
        Crea una línea de comisión con base y % explícitos (p. ej. honorarios + rol fichaje).
        """
        if porcentaje_comision is None or porcentaje_comision <= 0:
            return None
        if monto_base is None or monto_base <= 0:
            return None

        if getattr(reserva, 'eliminada', False) or getattr(reserva, 'estado', None) == 'cancelada':
            return None

        comision_existente = cls.objects.filter(
            vendedor=vendedor,
            reserva=reserva,
            movimiento_caja=movimiento_caja,
            rol_comision=rol_comision,
        ).first()

        if comision_existente:
            return comision_existente

        return cls.objects.create(
            vendedor=vendedor,
            reserva=reserva,
            movimiento_caja=movimiento_caja,
            monto_total_operacion=monto_base,
            porcentaje_comision=porcentaje_comision,
            concepto_operacion=(concepto or f'Operación {reserva.id}')[:200],
            rol_comision=rol_comision,
            fecha_operacion=movimiento_caja.fecha if movimiento_caja else timezone.now(),
        )

    @classmethod
    def crear_comision(cls, vendedor, reserva, movimiento_caja, monto_total, concepto=""):
        """
        Comisión única "general" según tipo de reserva (sin desglose por honorarios).
        """
        pct = vendedor.porcentaje_comision_para_reserva(reserva)
        if pct is None or pct <= 0:
            return None

        if getattr(reserva, 'eliminada', False) or getattr(reserva, 'estado', None) == 'cancelada':
            return None

        comision_existente = cls.objects.filter(
            vendedor=vendedor,
            reserva=reserva,
            movimiento_caja=movimiento_caja,
            rol_comision=ROL_COMISION_GENERAL,
        ).first()

        if comision_existente:
            return comision_existente

        return cls.crear_comision_linea(
            vendedor=vendedor,
            reserva=reserva,
            movimiento_caja=movimiento_caja,
            monto_base=monto_total,
            porcentaje_comision=pct,
            concepto=concepto or f'Operación {reserva.id}',
            rol_comision=ROL_COMISION_GENERAL,
        )
    
    def get_monto_comision_mensual(self, año, mes):
        """
        Obtiene el monto de comisión para un mes específico (no suma anuladas / reservas canceladas).
        """
        return (
            ComisionVendedor.objects.filter(
                vendedor=self.vendedor,
                fecha_operacion__year=año,
                fecha_operacion__month=mes,
            )
            .que_suman()
            .aggregate(total=models.Sum('monto_comision'))['total']
            or Decimal('0')
        )
