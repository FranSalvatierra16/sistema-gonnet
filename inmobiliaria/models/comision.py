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


def rol_comision_al_crear_linea_unica(vendedor, reserva):
    """
    Rol coherente con porcentaje_comision_para_reserva() cuando hay una sola línea
    (pago sin honorarios desglosados). Debe seguir el mismo orden de prioridad que Vendedor.porcentaje_comision_para_reserva.
    """
    if not reserva or not getattr(reserva, 'propiedad_id', None):
        return ROL_COMISION_GENERAL
    prop = reserva.propiedad
    try:
        dias = (reserva.fecha_fin - reserva.fecha_inicio).days
    except (TypeError, AttributeError):
        dias = 0
    es_alquiler_largo = dias >= 600
    if es_alquiler_largo and vendedor.comision_alquiler_24_meses is not None:
        return ROL_COMISION_OP_24
    if (
        vendedor.comision_invierno is not None
        and dias < 600
        and dias >= 14
        and getattr(prop, 'habilitar_invierno', False)
    ):
        try:
            mes_ini = reserva.fecha_inicio.month
        except AttributeError:
            mes_ini = 0
        if mes_ini in (4, 5, 6, 7, 8, 9, 10):
            return ROL_COMISION_OP_INVIERNO
    tipo = getattr(prop, 'tipo_fichaje', None) or 'primer'
    if tipo == 'segundo' and vendedor.comision_segundo_fichaje is not None:
        return ROL_COMISION_FICHAJE
    if tipo == 'primer' and vendedor.comision_primer_fichaje is not None:
        return ROL_COMISION_FICHAJE
    return ROL_COMISION_GENERAL


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


def _pct_operacion_dia_o_fallback_despues_fichaje(vendedor, hubo_regla_fichaje):
    """
    % para la línea «operación por día» sobre el total de la reserva (desacoplado del % fichaje).

    Si ya corre comisión por fichaje sobre honorarios y el vendedor no tiene % de comisión por día cargado,
    se usa el default de sucursal o 1% para no perder la comisión por la reserva en sí.
    """
    pct = pct_comision_normal_alquiler_dia(vendedor)
    if pct is not None and pct > 0:
        return pct
    if hubo_regla_fichaje:
        d = getattr(vendedor.sucursal, 'porcentaje_comision_default', None)
        if d is not None and d > 0:
            return d
        return Decimal('1')
    return Decimal('0')


def _crear_linea_operacion_por_dia(
    vendedor, reserva, movimiento_caja, honorarios_monto, creadas, pct_override=None
):
    """
    Comisión de operación «por día»: % comisión por día (campo comisión / default sucursal) sobre el total
    de la reserva; si no hay precio_total cargado, usa el monto de honorarios de este pago.
    """
    pct = pct_override if pct_override is not None else pct_comision_normal_alquiler_dia(vendedor)
    if pct is None or pct <= 0:
        return
    base = reserva.precio_total or Decimal('0')
    if base <= 0:
        base = honorarios_monto or Decimal('0')
    if base <= 0:
        return
    c = ComisionVendedor.crear_comision_linea(
        vendedor=vendedor,
        reserva=reserva,
        movimiento_caja=movimiento_caja,
        monto_base=base,
        porcentaje_comision=pct,
        concepto=f'Op. {reserva.id} — comisión alquiler por día (sobre total reserva)',
        rol_comision=ROL_COMISION_OP_DIA,
    )
    if c:
        creadas.append(c)


def registrar_comisiones_honorarios_movimiento_reserva(reserva, movimiento_caja, honorarios_monto):
    """
    Cuando en el movimiento hay honorarios (concepto 25), registra:
    - Comisión por primer/segundo fichaje del vendedor de la operación sobre el monto de honorarios.
    - Según tipo de operación: % invierno o % 24 meses sobre honorarios, o % comisión normal sobre precio total (día).
    Si hubo regla de fichaje y el vendedor no tiene % de comisión por día ni default de sucursal, la línea
    «operación por día» usa el default de sucursal o 1% para no omitir la comisión por la reserva.
    Si honorarios_monto es 0, no hace nada (el llamador usa la comisión por día única sobre la reserva).
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

    hubo_regla_fichaje = pct_fichaje is not None and pct_fichaje > 0
    if hubo_regla_fichaje:
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
    pct_op_dia = _pct_operacion_dia_o_fallback_despues_fichaje(vend, hubo_regla_fichaje)
    pct_op_dia_kw = pct_op_dia if pct_op_dia and pct_op_dia > 0 else None

    if tipo_op == 'dia':
        _crear_linea_operacion_por_dia(
            vend, reserva, movimiento_caja, honorarios_monto, creadas, pct_override=pct_op_dia_kw
        )

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
        else:
            # Propiedad con invierno habilitado pero sin % invierno: tratar como operación por día
            _crear_linea_operacion_por_dia(
                vend, reserva, movimiento_caja, honorarios_monto, creadas, pct_override=pct_op_dia_kw
            )

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
        else:
            _crear_linea_operacion_por_dia(
                vend, reserva, movimiento_caja, honorarios_monto, creadas, pct_override=pct_op_dia_kw
            )

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

    def etiqueta_tipo_comision(self):
        """
        Texto legible para listados (primer/segundo fichaje, alquiler por día, invierno, 24 meses, comisión por día).
        """
        rol_raw = self.rol_comision or ROL_COMISION_GENERAL
        try:
            rol = (rol_raw.strip() if isinstance(rol_raw, str) else str(rol_raw).strip()) or ROL_COMISION_GENERAL
        except (AttributeError, TypeError):
            rol = ROL_COMISION_GENERAL
        if rol == ROL_COMISION_FICHAJE:
            res = getattr(self, 'reserva', None)
            prop = getattr(res, 'propiedad', None) if res else None
            tf = (getattr(prop, 'tipo_fichaje', None) or 'primer')
            if tf == 'segundo':
                return 'Comisión por segundo fichaje'
            return 'Comisión por primer fichaje'
        if rol == ROL_COMISION_OP_DIA:
            return 'Comisión por alquiler por día'
        if rol == ROL_COMISION_OP_INVIERNO:
            return 'Comisión por alquiler invierno'
        if rol == ROL_COMISION_OP_24:
            return 'Comisión por alquiler 24 meses'
        return 'Comisión por día'

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
        Una sola línea de comisión según tipo de reserva (sin desglose por honorarios).
        El rol refleja la misma regla que el % (fichaje, invierno, 24 meses o comisión por día).
        """
        pct = vendedor.porcentaje_comision_para_reserva(reserva)
        if pct is None or pct <= 0:
            return None

        if getattr(reserva, 'eliminada', False) or getattr(reserva, 'estado', None) == 'cancelada':
            return None

        rol = rol_comision_al_crear_linea_unica(vendedor, reserva)

        comision_existente = cls.objects.filter(
            vendedor=vendedor,
            reserva=reserva,
            movimiento_caja=movimiento_caja,
            rol_comision=rol,
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
            rol_comision=rol,
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


class MesComisionPagadoVendedor(models.Model):
    """
    Marca un mes calendario (año/mes) de un vendedor como liquidado/pagado al productor.
    Los totales «pendientes» del historial excluyen comisiones y vales de esos meses.
    """

    vendedor = models.ForeignKey(
        Vendedor,
        on_delete=models.CASCADE,
        related_name='meses_comision_pagados',
        verbose_name='Vendedor',
    )
    anio = models.PositiveIntegerField(verbose_name='Año')
    mes = models.PositiveSmallIntegerField(verbose_name='Mes', help_text='1–12')
    creado_en = models.DateTimeField(auto_now_add=True, verbose_name='Marcado el')

    class Meta:
        verbose_name = 'Mes comisiones/vales pagado (vendedor)'
        verbose_name_plural = 'Meses comisiones/vales pagados'
        unique_together = [('vendedor', 'anio', 'mes')]
        ordering = ['-anio', '-mes']

    def __str__(self):
        return f'{self.vendedor_id} {self.anio}-{self.mes:02d} pagado'

    def mes_key(self):
        return f'{self.anio:04d}-{self.mes:02d}'
