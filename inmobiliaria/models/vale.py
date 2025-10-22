from django.db import models
from django.utils import timezone
from decimal import Decimal
from .persona import Vendedor
from .caja import MovimientoCaja


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
    
    @classmethod
    def crear_vale(cls, vendedor, monto, caja, concepto="Vale", observaciones="", usuario_creador=None):
        """
        Método helper para crear un vale y su movimiento de caja asociado
        """
        from .caja import TipoMovimientoCajaEnum
        
        try:
            print(f"🔍 DEBUG - Creando vale:")
            print(f"   Vendedor: {vendedor}")
            print(f"   Monto: {monto}")
            print(f"   Caja: {caja}")
            
            # Crear movimiento de caja (egreso en efectivo)
            movimiento = MovimientoCaja.objects.create(
                caja=caja,
                sucursal=vendedor.sucursal,
                tipo=TipoMovimientoCajaEnum.EGRESO,
                concepto=f"Vale para {vendedor.nombre_completo_vendedor()} - {concepto}",
                monto_efectivo=monto,
                monto_total=monto,
                empleado=usuario_creador or vendedor
            )
            print(f"✅ Movimiento creado: {movimiento.id}")
            
            # Crear el vale
            vale = cls.objects.create(
                vendedor=vendedor,
                movimiento_caja=movimiento,
                monto=monto,
                concepto=concepto,
                observaciones=observaciones,
                usuario_creador=usuario_creador,
                fecha=timezone.now()
            )
            print(f"✅ Vale creado: {vale.id}")
            
            return vale
            
        except Exception as e:
            print(f"❌ ERROR en crear_vale: {str(e)}")
            print(f"   Tipo de error: {type(e)}")
            import traceback
            traceback.print_exc()
            raise
    
    def get_mes_año(self):
        """
        Retorna el mes y año del vale para agrupación
        """
        return self.fecha.strftime('%Y-%m')

