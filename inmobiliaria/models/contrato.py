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
    vendedor = models.ForeignKey(
        'Vendedor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contratos',
    )
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
    ESTADO_CONFIRMACION_CARATULA_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('confirmada', 'Confirmada'),
    ]
    estado_confirmacion_caratula = models.CharField(
        max_length=12,
        choices=ESTADO_CONFIRMACION_CARATULA_CHOICES,
        default='pendiente',
        verbose_name='Estado carátula',
        help_text='Revisión administrativa de la carátula (independiente de comisiones y pagos).',
    )
    caratula_comision_locador = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Comisión locador (carátula)',
        help_text='Override manual desde carátula cuando aún no hay liquidación al propietario.',
    )
    caratula_comision_locatario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Comisión locatario (carátula)',
        help_text='Override manual desde carátula cuando aún no hay liquidación al propietario.',
    )

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

    def categoria_tipo_operacion(self):
        """
        Cómo se dio de alta el contrato (módulo invierno vs 24 meses), no solo la duración del plan.
        Un plan de 36 meses activado por AlquilerMeses sigue siendo «24 meses».
        """
        if self.es_contrato_invierno() or int(self.duracion_meses or 0) == 9:
            return 'invierno'
        if int(self.duracion_meses or 0) == 6:
            return '6'
        if int(self.duracion_meses or 0) >= 9:
            return '24'
        return 'otro'

    def etiqueta_tipo_operacion_caratula(self):
        cat = self.categoria_tipo_operacion()
        if cat == 'invierno':
            return 'Invierno (9 meses)'
        if cat == '6':
            return '6 meses'
        if cat == '24':
            return '24 meses'
        dm = int(self.duracion_meses or 0)
        return f'Contrato {dm} meses' if dm else 'Contrato'

    def codigo_tipo_movimiento_caratula(self):
        cat = self.categoria_tipo_operacion()
        if cat == 'invierno':
            return 'invierno'
        if cat == '24':
            return 'meses_24'
        if cat == '6':
            return 'meses_6'
        return 'otros'

    @property
    def fecha_entrada_departamento(self):
        """Día de ingreso / posesión del inquilino."""
        return self.fecha_inicio

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

    def esta_vencido(self, hoy=None):
        hoy = hoy or timezone.localdate()
        return bool(self.fecha_fin and self.fecha_fin < hoy)

    def finalizar_si_vencido(self, hoy=None):
        """Pasa a finalizado cuando ya pasó la fecha de fin (no rescindido)."""
        hoy = hoy or timezone.localdate()
        if self.estado in ('reservado', 'activo') and self.esta_vencido(hoy):
            self.estado = 'finalizado'
            self.save(update_fields=['estado'])
            # Contrato largo: liberar ficha 24 meses si no queda otro vigente.
            if self.duracion_meses != 9 and self.propiedad_id:
                from inmobiliaria.models.propiedad import liberar_info_meses_si_sin_contrato_vigente

                liberar_info_meses_si_sin_contrato_vigente(self.propiedad)
            return True
        return False

    @classmethod
    def finalizar_vencidos(cls, *, propiedad=None, inquilino=None, sucursal=None, hoy=None):
        hoy = hoy or timezone.localdate()
        qs = cls.objects.filter(estado__in=['reservado', 'activo'], fecha_fin__lt=hoy)
        if propiedad is not None:
            qs = qs.filter(propiedad=propiedad)
        if inquilino is not None:
            qs = qs.filter(inquilino=inquilino)
        if sucursal is not None:
            qs = qs.filter(sucursal=sucursal)
        propiedad_ids = list(
            qs.exclude(duracion_meses=9)
            .values_list('propiedad_id', flat=True)
            .distinct()
        )
        updated = qs.update(estado='finalizado')
        if propiedad_ids:
            from inmobiliaria.models.propiedad import (
                Propiedad,
                liberar_info_meses_si_sin_contrato_vigente,
            )

            for prop in Propiedad.objects.filter(id__in=propiedad_ids):
                liberar_info_meses_si_sin_contrato_vigente(prop)
        return updated

    @classmethod
    def queryset_vigentes(cls):
        """Contratos que aún bloquean la misma propiedad/inquilino o la disponibilidad."""
        hoy = timezone.localdate()
        return cls.objects.filter(
            estado__in=['reservado', 'activo'],
            fecha_fin__gte=hoy,
        )

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
        """True si hay abono/crédito a cuenta (parcial o que ya cubre el mes sin marcar pagada)."""
        if self.estado not in ('pendiente', 'vencida'):
            return False
        cred = Decimal(str(self.credito_aplicado or 0))
        return cred > Decimal('0.05')

    def cubierta_por_credito(self) -> bool:
        """True si el crédito ya cubre el total y aún no se cobró el mes en un recibo propio."""
        if self.estado not in ('pendiente', 'vencida'):
            return False
        tol = Decimal('0.05')
        obligacion = Decimal(str(self.monto_total or 0))
        if obligacion <= tol:
            return False
        cred = Decimal(str(self.credito_aplicado or 0))
        return cred + tol >= obligacion


ESTADOS_COBRO_CONTRATO = (
    ('completo', 'Completo'),
    ('en_fecha', 'En fecha'),
    ('debe_mes_actual', 'Debe mes actual'),
    ('debe_atrasados', 'Debe atrasados'),
)

_ESTADOS_CUOTA_IMPAGA = frozenset({'pendiente', 'vencida'})


def clasificar_estado_cobro_contrato(contrato, hoy=None):
    """
    Clasifica el estado de cobro de un contrato (mutuamente excluyente).

    Retorna dict con:
      - clave: completo | en_fecha | debe_mes_actual | debe_atrasados | sin_cuotas
      - label, detalle, cuotas_atrasadas, cuota_mes_actual, proxima_impaga
    """
    if hoy is None:
        hoy = timezone.localdate()
    anio_mes = (hoy.year, hoy.month)

    try:
        cuotas = list(contrato.cuotas.all())
    except Exception:
        cuotas = []

    if not cuotas:
        return {
            'clave': 'sin_cuotas',
            'label': 'Sin plan de cuotas',
            'detalle': 'Sin plan de cuotas',
            'cuotas_atrasadas': 0,
            'cuota_mes_actual': None,
            'proxima_impaga': None,
        }

    cuotas.sort(key=lambda c: (c.fecha_vencimiento or hoy, c.numero_cuota or 0))

    def _es_impaga(c):
        return (c.estado or '') in _ESTADOS_CUOTA_IMPAGA

    def _ym(c):
        fv = c.fecha_vencimiento
        if not fv:
            return None
        return (fv.year, fv.month)

    impagas = [c for c in cuotas if _es_impaga(c)]
    proxima_impaga = impagas[0] if impagas else None

    if not impagas:
        return {
            'clave': 'completo',
            'label': 'Completo',
            'detalle': 'Todas las cuotas pagadas',
            'cuotas_atrasadas': 0,
            'cuota_mes_actual': None,
            'proxima_impaga': None,
        }

    atrasadas = []
    del_mes = []
    for c in impagas:
        ym = _ym(c)
        if ym is None:
            continue
        if ym < anio_mes:
            atrasadas.append(c)
        elif ym == anio_mes:
            del_mes.append(c)

    cuota_mes_actual = del_mes[0] if del_mes else None

    if atrasadas:
        n = len(atrasadas)
        prox = atrasadas[0]
        detalle = (
            f'Debe {n} mes{"es" if n != 1 else ""} atrasado{"s" if n != 1 else ""}'
            f' · próxima {prox.fecha_vencimiento.strftime("%d/%m/%Y")}'
        )
        return {
            'clave': 'debe_atrasados',
            'label': 'Debe atrasados',
            'detalle': detalle,
            'cuotas_atrasadas': n,
            'cuota_mes_actual': cuota_mes_actual,
            'proxima_impaga': proxima_impaga,
        }

    if del_mes:
        c = del_mes[0]
        detalle = (
            f'Debe cuota {c.numero_cuota}/{contrato.duracion_meses or "?"} '
            f'del mes · vence {c.fecha_vencimiento.strftime("%d/%m/%Y")}'
        )
        return {
            'clave': 'debe_mes_actual',
            'label': 'Debe mes actual',
            'detalle': detalle,
            'cuotas_atrasadas': 0,
            'cuota_mes_actual': c,
            'proxima_impaga': proxima_impaga,
        }

    # Impagas solo futuras → al día hasta mes actual
    detalle = 'Pagado hasta el mes actual'
    if proxima_impaga and proxima_impaga.fecha_vencimiento:
        detalle += f' · próxima {proxima_impaga.fecha_vencimiento.strftime("%d/%m/%Y")}'
    return {
        'clave': 'en_fecha',
        'label': 'En fecha',
        'detalle': detalle,
        'cuotas_atrasadas': 0,
        'cuota_mes_actual': None,
        'proxima_impaga': proxima_impaga,
    }

class ObservacionCobroInquilino(models.Model):
    """
    Gasto/observación a cobrar al inquilino (concepto + monto).
    Pendiente hasta que se cobre en un recibo de cuota; al cobrarse deja de listarse.
    """

    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_COBRADO = 'cobrado'
    ESTADO_CHOICES = (
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_COBRADO, 'Cobrado'),
    )
    MONEDA_CHOICES = (
        ('ARS', 'Pesos (ARS)'),
        ('USD', 'Dólares (USD)'),
    )

    contrato = models.ForeignKey(
        ContratoAlquiler,
        on_delete=models.CASCADE,
        related_name='observaciones_cobro',
    )
    cuota = models.ForeignKey(
        'CuotaMensual',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='observaciones_cobro',
        help_text='Mes/cuota al que corresponde este gasto a cobrar.',
    )
    sucursal = models.ForeignKey(
        'Sucursal',
        on_delete=models.CASCADE,
        related_name='observaciones_cobro_inquilino',
    )
    concepto_caja_id = models.CharField(
        max_length=20,
        verbose_name='ID concepto de caja',
    )
    concepto_nombre = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name='Nombre del concepto',
    )
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    moneda = models.CharField(max_length=3, choices=MONEDA_CHOICES, default='ARS')
    detalle = models.CharField(max_length=400, blank=True, default='')
    fecha = models.DateField(
        default=timezone.localdate,
        verbose_name='Fecha',
        help_text='Fecha del gasto/observación (por defecto el día en que se carga).',
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default=ESTADO_PENDIENTE,
        db_index=True,
    )
    movimiento_cobro = models.ForeignKey(
        MovimientoCaja,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='observaciones_cobro_inquilino',
    )
    gasto_propietario = models.ForeignKey(
        'GastoPropietario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='observaciones_cobro_origen',
        help_text='Gasto/ingreso pendiente generado al cobrar, para liquidar al propietario.',
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='observaciones_cobro_creadas',
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    cobrado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Observación cobro inquilino'
        verbose_name_plural = 'Observaciones cobro inquilino'
        ordering = ['-creado_en', '-id']

    def __str__(self):
        return (
            f'Obs #{self.id} CT{self.contrato_id} '
            f'{self.concepto_caja_id} ${self.monto} ({self.estado})'
        )
