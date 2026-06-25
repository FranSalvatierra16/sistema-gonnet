from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
from .caja import MovimientoCaja

# Tipo de operación
class TipoOperacion(models.TextChoices):
    RESERVA_TEMPORAL = 'temporal', 'Reserva Temporal (días)'
    ALQUILER_MENSUAL = 'mensual', 'Alquiler Mensual'
    ALQUILER_INVIERNO = 'invierno', 'Alquiler Invierno (9 meses)'

# Contrato de alquiler (operación principal)
class ContratoAlquiler(models.Model):
    propiedad = models.ForeignKey('Propiedad', on_delete=models.CASCADE, related_name='contratos')
    inquilino = models.ForeignKey('Inquilino', on_delete=models.CASCADE, related_name='contratos', help_text='Inquilino principal (el primero si hay varios)')
    vendedor = models.ForeignKey('Vendedor', on_delete=models.CASCADE, related_name='contratos')
    # Varios inquilinos por contrato (el primero coincide con inquilino); carrera por inquilino vía through
    inquilinos = models.ManyToManyField(
        'Inquilino',
        through='ContratoInquilino',
        related_name='contratos_como_inquilino',
        blank=True,
        verbose_name='Inquilinos',
        help_text='Todos los inquilinos del contrato'
    )
    
    # Fechas del contrato
    fecha_operacion = models.DateField(default=timezone.now, help_text='Fecha en que se realiza la operación')
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    duracion_meses = models.PositiveIntegerField()  # 24 meses
    dia_vencimiento = models.PositiveIntegerField(default=5, help_text='Día del mes para vencimiento de cuotas (1-28)')
    
    # Montos
    MONEDA_CUOTA_CHOICES = [
        ('ARS', 'Pesos (ARS)'),
        ('USD', 'Dólares (USD)'),
    ]
    moneda = models.CharField(
        max_length=3,
        choices=MONEDA_CUOTA_CHOICES,
        default='ARS',
        verbose_name='Moneda de cuotas',
        help_text='Moneda en la que se expresan el precio mensual y las cuotas del plan.',
    )
    precio_mensual = models.DecimalField(max_digits=10, decimal_places=2)
    precio_segundo_cuatrimestre = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name='Precio 2do cuatrimestre (contrato estudiante 9 meses)'
    )
    deposito_garantia = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    gastos_adicionales = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    honorarios_referencia = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name='Honorarios (referencia)',
        help_text='Monto informado al crear el contrato; precarga en operación principal.',
    )
    sellados_referencia = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name='Sellados (referencia)',
        help_text='Monto informado al crear el contrato; precarga en operación principal.',
    )
    neto_a_posesion_referencia = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Neto a la posesión (referencia)',
        help_text='Saldo neto de la operación inicial (recibo): total a abonar menos lo efectivamente pagado.',
    )
    # Opcional: aumentos cada 3 meses. Lista alineada a trimestres 2, 3, … (índice 0 = meses 4–6).
    # null en un elemento o ausencia = repetir el monto del trimestre anterior (arranca en precio_mensual).
    precios_bloques = models.JSONField(
        null=True,
        blank=True,
        verbose_name='Precios por trimestre (opcional)',
        help_text='Opcional: importes por bloque de 3 meses desde el 2.º trimestre; vacío = mismo valor que el trimestre anterior.',
    )

    # Estado del contrato
    ESTADO_CHOICES = [
        ('reservado', 'Reservado'),
        ('activo', 'Activo'),
        ('finalizado', 'Finalizado'),
        ('rescindido', 'Rescindido')
    ]
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='reservado')
    fecha_cancelacion = models.DateField(null=True, blank=True)
    motivo_cancelacion = models.TextField(blank=True)
    
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    sucursal = models.ForeignKey('Sucursal', on_delete=models.CASCADE)
    operacion_principal = models.BooleanField(default=False, help_text='Indica si ya se realizó la operación principal (depósito + primer mes)')

    # Garantes: inquilinos seleccionados como garantes (varios por contrato)
    garantes = models.ManyToManyField(
        'Inquilino',
        related_name='contratos_como_garante',
        blank=True,
        verbose_name='Garantes'
    )
    # Carrera del inquilino principal (legacy; se usa si no hay through con carreras)
    carrera = models.CharField(max_length=200, blank=True, verbose_name='Carrera')

    # Datos del garante en texto (legacy; se usa si no hay garantes M2M)
    garante_nombre = models.CharField(max_length=100, blank=True)
    garante_apellido = models.CharField(max_length=100, blank=True)
    garante_dni = models.CharField(max_length=20, blank=True)
    garante_celular = models.CharField(max_length=30, blank=True)
    garante_email = models.EmailField(max_length=120, blank=True)
    garante_domicilio = models.CharField(max_length=200, blank=True)
    numero_carpeta = models.CharField(
        max_length=8,
        blank=True,
        default='',
        verbose_name='Nº carpeta',
        help_text='Número de carpeta física para contratos invierno / 24 meses.',
    )

    class Meta:
        verbose_name = 'Contrato de Alquiler'
        verbose_name_plural = 'Contratos de Alquiler'
        ordering = ['-fecha_creacion']
    
    def __str__(self):
        return f"Contrato {self.id} - {self.propiedad.direccion}"
    
    def total_pagado(self):
        """Calcula el total pagado de todas las cuotas"""
        return sum(cuota.monto_total for cuota in self.cuotas.filter(estado='pagada'))
    
    def cuotas_vencidas(self):
        """Devuelve las cuotas vencidas"""
        return self.cuotas.filter(
            estado='pendiente',
            fecha_vencimiento__lt=timezone.now().date()
        )
    
    def proxima_cuota(self):
        """Devuelve la próxima cuota a pagar"""
        return self.cuotas.filter(estado='pendiente').order_by('fecha_vencimiento').first()

    def es_contrato_invierno(self):
        """Temporada invierno / estudiante (9 meses o equivalente en el plan de cuotas)."""
        d = int(self.duracion_meses or 0)
        if 0 < d <= 9:
            return True
        try:
            if self.precio_segundo_cuatrimestre is not None:
                if Decimal(str(self.precio_segundo_cuatrimestre)) > 0:
                    return True
        except Exception:
            pass
        try:
            if self.cuotas.count() == 9 and d != 24:
                return True
        except Exception:
            pass
        return False

    @property
    def etiqueta_recibo_tipo_contrato(self):
        """Texto del encabezado del recibo según tipo de contrato."""
        if self.es_contrato_invierno():
            return 'CONTRATO INVIERNO'
        d = int(self.duracion_meses or 0)
        if d == 24:
            return 'CONTRATO 24M'
        if d > 0:
            return f'CONTRATO {d}M'
        return 'CONTRATO'

    def cancelar(self, motivo):
        """Cancela el contrato y marca la propiedad como disponible"""
        self.estado = 'rescindido'
        self.fecha_cancelacion = timezone.now().date()
        self.motivo_cancelacion = motivo
        self.save()
        
        # Marcar la propiedad como disponible
        self.propiedad.info_meses.estado = 'disponible'
        self.propiedad.info_meses.save()

# Through: inquilino en contrato con su carrera (contrato estudiante)
class ContratoInquilino(models.Model):
    contrato = models.ForeignKey(ContratoAlquiler, on_delete=models.CASCADE, related_name='contrato_inquilinos')
    inquilino = models.ForeignKey('Inquilino', on_delete=models.CASCADE, related_name='contrato_inquilino_set')
    carrera = models.CharField(max_length=200, blank=True, verbose_name='Carrera del inquilino')

    class Meta:
        unique_together = ('contrato', 'inquilino')
        ordering = ['contrato', 'id']

    def __str__(self):
        return f"{self.contrato_id} - {self.inquilino} ({self.carrera or '-'})"


# Cuotas mensuales individuales
class CuotaMensual(models.Model):
    contrato = models.ForeignKey(ContratoAlquiler, on_delete=models.CASCADE, related_name='cuotas')
    numero_cuota = models.PositiveIntegerField()  # 1, 2, 3... hasta 24
    
    # Fechas
    fecha_vencimiento = models.DateField()
    fecha_pago = models.DateField(null=True, blank=True)
    
    # Montos
    monto_base = models.DecimalField(max_digits=10, decimal_places=2)
    recargo_mora = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    descuento = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    monto_total = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Estado de pago
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('pagada', 'Pagada'),
        ('vencida', 'Vencida'),
        ('pagada_con_mora', 'Pagada con Mora')
    ]
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    
    # Relación con movimiento de caja
    movimiento = models.ForeignKey(MovimientoCaja, on_delete=models.SET_NULL, null=True, blank=True)

    credito_aplicado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Crédito aplicado (excedente de pago anterior)',
        help_text='Importe cubierto por un cobro anterior mayor al saldo; reduce lo que falta pagar de esta cuota.',
    )
    credito_origen_numero_cuota = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Crédito procedente de cuota N',
        help_text='Número de cuota cuyo pago con excedente generó este crédito; se limpia al anular ese cobro.',
    )

    class Meta:
        verbose_name = 'Cuota Mensual'
        verbose_name_plural = 'Cuotas Mensuales'
        ordering = ['contrato', 'numero_cuota']
        unique_together = ('contrato', 'numero_cuota')
    
    def __str__(self):
        return f"Cuota {self.numero_cuota}/{self.contrato.duracion_meses} - {self.contrato.propiedad.direccion}"
    
    def dias_vencido(self):
        """Calcula los días de vencimiento"""
        if self.estado == 'pendiente' and self.fecha_vencimiento < timezone.now().date():
            return (timezone.now().date() - self.fecha_vencimiento).days
        return 0
    
    def calcular_mora(self, tasa_mora_diaria=0.01):
        """Calcula el recargo por mora (1% diario por defecto)"""
        dias = self.dias_vencido()
        if dias > 0:
            return self.monto_base * Decimal(str(tasa_mora_diaria)) * Decimal(str(dias))
        return Decimal('0')

    def actualizar_monto_total(self):
        """Actualiza el monto total considerando mora y descuentos"""
        self.monto_total = self.monto_base + self.recargo_mora - self.descuento
        self.save()

    def saldo_para_cobro(self):
        """Saldo pendiente en moneda de la cuota (monto_total menos crédito por excedente de pagos anteriores)."""
        if self.estado not in ('pendiente', 'vencida'):
            return Decimal('0')
        tot = Decimal(str(self.monto_total or 0))
        cred = Decimal(str(self.credito_aplicado or 0))
        return max(Decimal('0'), tot - cred)

    def tiene_adelanto_abonado(self) -> bool:
        """True si hay abono parcial a cuenta (aún falta saldo por cobrar)."""
        if self.estado not in ('pendiente', 'vencida'):
            return False
        tol = Decimal('0.05')
        if self.saldo_para_cobro() <= tol:
            return False
        cred = Decimal(str(self.credito_aplicado or 0))
        return cred > tol