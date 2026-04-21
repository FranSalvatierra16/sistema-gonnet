from django.db import models
from django.db.models import Sum
from django.utils import timezone
from decimal import Decimal
from .persona import Vendedor
from .caja import MovimientoCaja, TipoMovimientoCajaEnum


class ValeVendedor(models.Model):
    """
    Modelo para registrar los vales (préstamos) otorgados a vendedores
    Los vales se descuentan del efectivo de caja y se restan de las comisiones del vendedor
    """
    vendedor = models.ForeignKey(
        Vendedor,
        on_delete=models.CASCADE,
        related_name='vales',
        verbose_name="Vendedor"
    )
    
    movimiento_caja = models.ForeignKey(
        MovimientoCaja,
        on_delete=models.CASCADE,
        related_name='vales',
        verbose_name="Movimiento de Caja",
        null=True,
        blank=True
    )
    
    tipo_vale = models.CharField(
        max_length=2,
        choices=TipoMovimientoCajaEnum.choices,
        default=TipoMovimientoCajaEnum.EGRESO,
        verbose_name="Tipo de vale",
        help_text="EG: dinero que sale de caja hacia el productor. IN: dinero que ingresa a caja desde el productor.",
    )

    # Monto del vale
    monto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Monto del Vale"
    )
    
    # Información adicional
    concepto = models.CharField(
        max_length=200,
        verbose_name="Concepto",
        default="Vale"
    )
    observaciones = models.TextField(
        blank=True,
        verbose_name="Observaciones"
    )
    
    # Fechas
    fecha = models.DateTimeField(
        verbose_name="Fecha del Vale"
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Creación"
    )
    
    # Usuario que otorgó el vale
    usuario_creador = models.ForeignKey(
        Vendedor,
        on_delete=models.SET_NULL,
        null=True,
        related_name='vales_otorgados',
        verbose_name="Usuario que Otorgó el Vale"
    )
    
    class Meta:
        verbose_name = "Vale de Vendedor"
        verbose_name_plural = "Vales de Vendedores"
        ordering = ['-fecha']
    
    def __str__(self):
        return f"Vale {self.id} - {self.vendedor.nombre_completo_vendedor()} - ${self.monto}"
    
    @staticmethod
    def monto_total_movimiento(movimiento):
        """Suma de medios de pago del movimiento (Decimal, coherente con caja)."""
        return (
            Decimal(str(movimiento.monto_efectivo or 0))
            + Decimal(str(movimiento.monto_cheque or 0))
            + Decimal(str(movimiento.monto_tarjeta or 0))
            + Decimal(str(movimiento.monto_deposito or 0))
        )

    @classmethod
    def crear_desde_movimiento(
        cls,
        movimiento,
        vendedor,
        usuario_creador=None,
        observaciones="",
    ):
        """
        Registra un vale ligado a un movimiento de caja ya guardado (mismos medios y tipo IN/EG).
        """
        monto = cls.monto_total_movimiento(movimiento)
        if monto <= 0:
            raise ValueError("El movimiento no tiene importe total mayor a cero.")
        tipo = movimiento.tipo
        if tipo not in (TipoMovimientoCajaEnum.INGRESO, TipoMovimientoCajaEnum.EGRESO):
            raise ValueError("Tipo de movimiento inválido para vale.")
        base = (movimiento.concepto or "").strip()[:120] or "Movimiento caja"
        etiqueta = "Egreso" if tipo == TipoMovimientoCajaEnum.EGRESO else "Ingreso"
        concepto = f"Vale {etiqueta} — {base}"[:200]
        return cls.objects.create(
            vendedor=vendedor,
            movimiento_caja=movimiento,
            monto=monto,
            tipo_vale=tipo,
            concepto=concepto,
            observaciones=observaciones or "",
            usuario_creador=usuario_creador,
            fecha=timezone.now(),
        )

    @classmethod
    def crear_vale(cls, vendedor, monto, caja, concepto="Vale", observaciones="", usuario_creador=None):
        """
        Crea un vale de egreso y su movimiento de caja asociado (efectivo).
        """
        movimiento = MovimientoCaja.objects.create(
            caja=caja,
            sucursal=vendedor.sucursal,
            tipo=TipoMovimientoCajaEnum.EGRESO,
            concepto=f"Vale para {vendedor.nombre_completo_vendedor()} - {concepto}",
            monto_efectivo=monto,
            empleado=usuario_creador or vendedor,
        )
        return cls.objects.create(
            vendedor=vendedor,
            movimiento_caja=movimiento,
            monto=monto,
            tipo_vale=TipoMovimientoCajaEnum.EGRESO,
            concepto=concepto,
            observaciones=observaciones,
            usuario_creador=usuario_creador,
            fecha=timezone.now(),
        )
    
    def get_mes_año(self):
        """
        Retorna el mes y año del vale para agrupación
        """
        return self.fecha.strftime('%Y-%m')

    @classmethod
    def total_saldo_para_comisiones(cls, vendedor):
        """
        Efecto neto de vales sobre el neto comisiones: egresos suman, ingresos restan.
        """
        eg = (
            cls.objects.filter(vendedor=vendedor, tipo_vale=TipoMovimientoCajaEnum.EGRESO).aggregate(
                t=Sum("monto")
            )["t"]
            or Decimal("0")
        )
        ing = (
            cls.objects.filter(vendedor=vendedor, tipo_vale=TipoMovimientoCajaEnum.INGRESO).aggregate(
                t=Sum("monto")
            )["t"]
            or Decimal("0")
        )
        return eg - ing

