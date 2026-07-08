import re

from django.db import models

# Abreviatura «RE» (= recibo) en tipo de comprobante o al inicio del texto de concepto
_RE_ABREV_RECIBO_INICIO = re.compile(r'^RE\s+', re.IGNORECASE)
from django.conf import settings
from django.utils import timezone
from decimal import Decimal

# Palabra "vale" / "vales" en nombre de concepto (caja) para registrar ValeVendedor automático.
_CONCEPTO_VALE_NOMBRE_RE = re.compile(r"\bvales?\b", re.IGNORECASE)

class TipoMovimientoCajaEnum(models.TextChoices):
    INGRESO = 'IN', 'Ingreso'
    EGRESO = 'EG', 'Egreso'

class TipoComprobanteEnum(models.TextChoices):
    RECIBO = 'RC', 'Recibo'
    LIQUIDACION = 'LQ', 'Liquidación'
    GASTO = 'GS', 'Gasto'
    OTRO = 'OT', 'Otro'

class TipoDescuentoEnum(models.TextChoices):
    PROPIETARIO = 'PR', 'Propietario'
    INQUILINO = 'IN', 'Inquilino'
    OFICINA = 'OF', 'Oficina'


class MovimientoCajaActivosManager(models.Manager):
    """Movimientos que siguen vigentes en la caja (no anulados)."""

    def get_queryset(self):
        return super().get_queryset().filter(fecha_eliminacion__isnull=True)


class Caja(models.Model):
    ESTADO_CHOICES = [
        ('abierta', 'Abierta'),
        ('cerrada', 'Cerrada'),
    ]
    
    numero = models.AutoField(primary_key=True)
    sucursal = models.ForeignKey('Sucursal', on_delete=models.PROTECT)
    fecha_apertura = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    # 14 dígitos: soporta saldos acumulados altos (10,2 overflow > ~100M)
    saldo_inicial = models.DecimalField(max_digits=14, decimal_places=2)
    saldo_final = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='abierta')
    usuario_apertura = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='cajas_abiertas')
    usuario_cierre = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='cajas_cerradas', null=True, blank=True)
    observaciones_apertura = models.TextField(blank=True)
    observaciones_cierre = models.TextField(blank=True)
    
    def get_saldo_actual(self):
        """Saldo = inicial + ingresos − egresos (una sola query agregada)."""
        from django.db.models import Sum, Case, When, F, Value, DecimalField
        from django.db.models.functions import Coalesce

        dec = DecimalField(max_digits=14, decimal_places=2)
        zero = Value(Decimal('0'), output_field=dec)
        movimientos = MovimientoCaja.objects.filter(caja=self)
        totales = movimientos.aggregate(
            ingresos=Coalesce(
                Sum(
                    Case(
                        When(
                            tipo=TipoMovimientoCajaEnum.INGRESO,
                            then=F('monto_efectivo') + F('monto_cheque') + F('monto_tarjeta') + F('monto_deposito'),
                        ),
                        default=zero,
                        output_field=dec,
                    )
                ),
                zero,
            ),
            egresos=Coalesce(
                Sum(
                    Case(
                        When(
                            tipo=TipoMovimientoCajaEnum.EGRESO,
                            then=F('monto_efectivo') + F('monto_cheque') + F('monto_tarjeta') + F('monto_deposito'),
                        ),
                        default=zero,
                        output_field=dec,
                    )
                ),
                zero,
            ),
        )
        return (
            Decimal(str(self.saldo_inicial or 0))
            + Decimal(str(totales['ingresos'] or 0))
            - Decimal(str(totales['egresos'] or 0))
        )

    def __str__(self):
        return f"Caja #{self.numero} - {self.sucursal}"
    
    class Meta:
        db_table = 'inmobiliaria_caja'
        unique_together = ('numero', 'sucursal')
        verbose_name = 'Caja'
        verbose_name_plural = 'Cajas'
        ordering = ['-fecha_apertura']


class CajaArqueoCierre(models.Model):
    """Conteo físico al cierre (superusuario): saldo por medio de pago / cuenta."""

    caja = models.OneToOneField(
        Caja,
        on_delete=models.CASCADE,
        related_name='arqueo_cierre',
    )
    efectivo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cheque = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tarjeta = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    dolares = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    deposito_galicia = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    deposito_mp = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cuentas_json = models.JSONField(default=dict, blank=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='arqueos_caja_registrados',
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inmobiliaria_caja_arqueo_cierre'
        verbose_name = 'Arqueo de cierre de caja'
        verbose_name_plural = 'Arqueos de cierre de caja'

    def __str__(self):
        return f'Arqueo caja #{self.caja_id} — ${self.total_ars()}'

    def total_ars(self):
        total = Decimal('0')
        for attr in ('efectivo', 'cheque', 'tarjeta', 'deposito_galicia', 'deposito_mp'):
            total += Decimal(str(getattr(self, attr, None) or 0))
        for val in (self.cuentas_json or {}).values():
            try:
                total += Decimal(str(val or 0))
            except Exception:
                pass
        return total

    def monto_cuenta(self, cuenta_id):
        raw = (self.cuentas_json or {}).get(str(cuenta_id))
        if raw is None:
            return Decimal('0')
        try:
            return Decimal(str(raw))
        except Exception:
            return Decimal('0')


class CajaArqueoManual(models.Model):
    """Conteo físico ajustado por super admin mientras la caja está abierta."""

    caja = models.OneToOneField(
        Caja,
        on_delete=models.CASCADE,
        related_name='arqueo_manual',
    )
    efectivo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cheque = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tarjeta = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    dolares = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    deposito_galicia = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    deposito_mp = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cuentas_json = models.JSONField(default=dict, blank=True)
    anteriores_json = models.JSONField(
        default=dict,
        blank=True,
        help_text='Saldos ANTERIOR por medio (fijos). El saldo actual = anterior + ingresos − egresos.',
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='arqueos_manuales_caja',
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inmobiliaria_caja_arqueo_manual'
        verbose_name = 'Arqueo manual de caja'
        verbose_name_plural = 'Arqueos manuales de caja'

    def __str__(self):
        return f'Arqueo manual caja #{self.caja_id} — ${self.total_ars()}'

    def total_ars(self):
        total = Decimal('0')
        for attr in ('efectivo', 'cheque', 'tarjeta', 'deposito_galicia', 'deposito_mp'):
            total += Decimal(str(getattr(self, attr, None) or 0))
        for val in (self.cuentas_json or {}).values():
            try:
                total += Decimal(str(val or 0))
            except Exception:
                pass
        return total

    def monto_cuenta(self, cuenta_id):
        raw = (self.cuentas_json or {}).get(str(cuenta_id))
        if raw is None:
            return Decimal('0')
        try:
            return Decimal(str(raw))
        except Exception:
            return Decimal('0')

    def como_dict_arqueo(self):
        return {
            'efectivo': self.efectivo,
            'cheque': self.cheque,
            'tarjeta': self.tarjeta,
            'dolares': self.dolares,
            'deposito_galicia': self.deposito_galicia,
            'deposito_mp': self.deposito_mp,
            'cuentas_json': self.cuentas_json or {},
        }


class MovimientoCaja(models.Model):
    fecha = models.DateTimeField(
        default=timezone.now,
        help_text='Fecha del movimiento (comprobante/transferencia). Puede ser anterior al día de carga en caja.',
    )
    tipo = models.CharField(
        max_length=2,
        choices=TipoMovimientoCajaEnum.choices,
        default=TipoMovimientoCajaEnum.INGRESO
    )
    tipo_comprobante = models.CharField(
        max_length=2,
        choices=TipoComprobanteEnum.choices,
        default=TipoComprobanteEnum.RECIBO
    )
    numero_liquidacion = models.CharField(max_length=50, blank=True)
    concepto = models.CharField(max_length=200, blank=True)
    concepto_detalle = models.TextField(blank=True, help_text='JSON completo de conceptos para recibos de contrato')
    cuenta = models.ForeignKey('Cuenta', on_delete=models.SET_NULL, null=True, blank=True)
    propiedad = models.ForeignKey('Propiedad', on_delete=models.SET_NULL, null=True, blank=True)
    fecha_desde = models.DateField(null=True, blank=True)
    fecha_hasta = models.DateField(null=True, blank=True)
    monto_efectivo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    monto_cheque = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    monto_tarjeta = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    monto_deposito = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    monto_dolares = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text='Dólares (USD) del movimiento: ingreso o egreso en efectivo dólar; no suma al total en ARS.',
    )
    destino_deposito = models.CharField(
        max_length=50,  # ✅ Aumentado para permitir "cuenta_1", "cuenta_2", etc.
        choices=[
            ('galicia', 'Galicia'),
            ('mp', 'Mercado Pago'),
            ('mixto', 'Mixto'),
        ],
        null=True,
        blank=True,
        help_text="Puede ser 'galicia', 'mp', 'mixto', o 'cuenta_X' para cuentas bancarias dinámicas"
    )
    # Datos opcionales de medios de pago (nuevo movimiento de caja)
    tarjeta_numero = models.CharField(
        max_length=32,
        blank=True,
        help_text='Referencia o últimos dígitos; opcional',
    )
    tarjeta_cupon = models.CharField(max_length=64, blank=True)
    tarjeta_tipo = models.CharField(
        max_length=10,
        blank=True,
        choices=[('credito', 'Crédito'), ('debito', 'Débito')],
        default='',
    )
    cheque_numero = models.CharField(max_length=32, blank=True)
    cheque_banco = models.CharField(max_length=100, blank=True)
    cheque_fecha_vencimiento = models.DateField(null=True, blank=True)
    fecha_transferencia = models.DateField(
        null=True,
        blank=True,
        verbose_name='Fecha transferencia/depósito',
        help_text='Fecha real en que se acreditó o envió la transferencia/depósito (conciliación bancaria).',
    )
    a_descontar = models.CharField(
        max_length=20,
        choices=[
            ('propietario', 'Propietario'),
            ('oficina', 'Oficina'),
            ('inquilino', 'Inquilino'),
        ],
        null=True,  # Hacemos el campo opcional
        blank=True,  # Permitimos que esté vacío
        help_text='Solo necesario para egresos'
    )
    monto_a_oficina = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text='Parte del total que corresponde a la oficina / depto.',
    )
    monto_a_propietario = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text='Parte del total que corresponde al propietario.',
    )
    monto_a_inquilino = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text='Parte del total que corresponde al inquilino.',
    )
    sucursal = models.ForeignKey('Sucursal', on_delete=models.CASCADE)
    empleado = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    caja = models.ForeignKey('Caja', on_delete=models.CASCADE, null=True, blank=True)
    
    # Campos para contratos de 24 meses
    honorarios = models.DecimalField(max_digits=14, decimal_places=2, default=0, blank=True)
    sellados = models.DecimalField(max_digits=14, decimal_places=2, default=0, blank=True)

    # Anulación en caja abierta: el registro permanece para auditoría y no entra en totales/saldo.
    fecha_eliminacion = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text='Si está informado, el movimiento fue anulado y no suma en el saldo de la caja.',
    )
    eliminado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='movimientos_caja_eliminados',
    )

    all_objects = models.Manager()
    objects = MovimientoCajaActivosManager()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Inicializar montos en 0 si son None (después de cargar desde DB)
        if hasattr(self, 'pk') and self.pk:
            self.monto_efectivo = self.monto_efectivo or 0
            self.monto_cheque = self.monto_cheque or 0
            self.monto_tarjeta = self.monto_tarjeta or 0
            self.monto_deposito = self.monto_deposito or 0
            self.monto_dolares = self.monto_dolares or 0

    def __str__(self):
        return f"{self.get_tipo_display()} - ${self.monto_total}"

    @property
    def fecha_banco_efectiva(self):
        """Fecha para conciliación bancaria: transferencia real o día del movimiento en caja."""
        if self.fecha_transferencia:
            return self.fecha_transferencia
        if self.fecha:
            dt = self.fecha
            if timezone.is_aware(dt):
                dt = timezone.localtime(dt)
            return dt.date()
        return None

    @property
    def monto_efectivo_safe(self):
        """Retorna monto_efectivo asegurando que nunca sea None"""
        return float(self.monto_efectivo or 0)
    
    @property
    def monto_cheque_safe(self):
        """Retorna monto_cheque asegurando que nunca sea None"""
        return float(self.monto_cheque or 0)
    
    @property
    def monto_tarjeta_safe(self):
        """Retorna monto_tarjeta asegurando que nunca sea None"""
        return float(self.monto_tarjeta or 0)
    
    @property
    def monto_deposito_safe(self):
        """Retorna monto_deposito asegurando que nunca sea None"""
        return float(self.monto_deposito or 0)

    @property
    def monto_total(self):
        """Calcula el monto total sumando todos los métodos de pago (solo ARS; USD va aparte en monto_dolares)."""
        return (
            self.monto_efectivo_safe +
            self.monto_cheque_safe +
            self.monto_tarjeta_safe +
            self.monto_deposito_safe
        )

    @property
    def monto_dolares_safe(self):
        return float(self.monto_dolares or 0)

    def concepto_sin_pipe_conceptos(self):
        """Texto descriptivo del concepto sin el sufijo estructurado |CONCEPTOS:…"""
        raw = (self.concepto or '').strip()
        if '|CONCEPTOS:' in raw:
            raw = raw.split('|CONCEPTOS:', 1)[0].strip()
        return raw

    def _texto_concepto_sin_abrev_re(self, texto):
        """«RE …» al inicio del texto libre → «RECIBO …» (solo presentación)."""
        if not texto:
            return texto
        t = texto.strip()
        if t.upper() == 'RE':
            return 'RECIBO'
        return _RE_ABREV_RECIBO_INICIO.sub('RECIBO ', t, count=1)

    def _tipo_comprobante_display_upper(self):
        try:
            raw = (self.get_tipo_comprobante_display() or '').strip().upper()
        except Exception:
            raw = ''
        clave = (self.tipo_comprobante or '').strip().upper()
        if clave == 'RE' or raw == 'RE':
            return 'RECIBO'
        return raw

    def concepto_catalogo_id(self):
        """ID del concepto de catálogo si el campo `concepto` guardó solo el código."""
        raw = self.concepto_sin_pipe_conceptos().strip()
        if not raw or '|CONCEPTOS:' in raw:
            return None
        if raw.lower().startswith('operaci'):
            return None
        if '\n' in raw:
            raw = raw.split('\n', 1)[0].strip()
        if ' — ' in raw:
            head = raw.split(' — ', 1)[0].strip()
            if head and not head.isdigit() and len(head) > 1:
                return None
            raw = head
        if len(raw) <= 20 and ' ' not in raw:
            return raw
        return None

    @property
    def nombre_concepto_catalogo(self):
        """Nombre legible del concepto (catálogo o texto ya guardado)."""
        cached = getattr(self, '_concepto_nombre_cache', None)
        if cached is not None:
            return cached
        raw = self.concepto_sin_pipe_conceptos().strip()
        if ' — ' in raw:
            head = raw.split(' — ', 1)[0].strip()
            if head and not head.isdigit():
                return self._texto_concepto_sin_abrev_re(head)[:120]
        cid = self.concepto_catalogo_id()
        if cid:
            try:
                c = Concepto.objects.filter(pk=cid).only('nombre').first()
                if c and (c.nombre or '').strip():
                    return (c.nombre or '').strip()[:120]
            except Exception:
                pass
            return ''
        if raw.isdigit():
            return ''
        first = raw.split('\n', 1)[0].strip()
        return self._texto_concepto_sin_abrev_re(first)[:120] if first else ''

    @classmethod
    def precargar_nombres_concepto(cls, movimientos, sucursal=None):
        ids = set()
        for m in movimientos:
            cid = m.concepto_catalogo_id()
            if cid:
                ids.add(cid)
        if not ids:
            for m in movimientos:
                m._concepto_nombre_cache = m.nombre_concepto_catalogo
            return
        qs = Concepto.objects.filter(id__in=ids)
        if sucursal is not None:
            qs = qs.filter(models.Q(sucursal=sucursal) | models.Q(sucursal__isnull=True))
        nmap = {(c.id or '').strip(): (c.nombre or '').strip() for c in qs.only('id', 'nombre')}
        for m in movimientos:
            cid = m.concepto_catalogo_id()
            if cid and cid in nmap and nmap[cid]:
                m._concepto_nombre_cache = nmap[cid][:120]
            else:
                m._concepto_nombre_cache = m.nombre_concepto_catalogo

    @property
    def listado_concepto_l1(self):
        """Primera línea del bloque «Concepto» (categoría, estilo listado de caja)."""
        texto = self.concepto_sin_pipe_conceptos().lower()
        if 'vale' in texto:
            return 'VALE PERSONAL'
        if 'devoluc' in texto and ('garant' in texto or 'deposito' in texto or 'depósito' in texto):
            return 'D.D.G.'
        clave = (self.tipo_comprobante or '').strip().upper()
        if clave == 'RE':
            clave = 'RC'
        if clave == 'LQ' or 'liquid' in texto:
            return 'LIQUIDACIONES'
        if clave == 'GS':
            return 'GASTOS'
        if clave == 'RC':
            if self.tipo == TipoMovimientoCajaEnum.INGRESO and self.propiedad_id:
                return 'ALQUILER A COBRAR'
            return 'RECIBO'
        if clave == 'OT':
            return 'OTROS'
        return self._tipo_comprobante_display_upper() or 'MOVIMIENTO'

    @property
    def listado_concepto_l2(self):
        """Segunda línea: dirección / referencia de propiedad."""
        if not self.propiedad_id:
            return ''
        try:
            prop = self.propiedad
            dir_ = (getattr(prop, 'direccion', None) or '').strip()
        except Exception:
            dir_ = ''
        if not dir_:
            return ''
        return f'{dir_.upper()} ({self.propiedad_id})'

    def _primer_texto_detalle_desde_json(self):
        raw = (self.concepto_detalle or '').strip()
        if not raw.startswith('{'):
            return ''
        try:
            import json

            data = json.loads(raw)
        except Exception:
            return ''
        tr = (data.get('mes_alquiler_texto_recibo') or '').strip()
        if tr:
            return self._texto_concepto_sin_abrev_re(tr)[:200]
        cons = data.get('conceptos')
        if isinstance(cons, list) and cons:
            first = cons[0]
            if isinstance(first, dict):
                for key in ('nombre', 'concepto', 'descripcion', 'label'):
                    v = first.get(key)
                    if v:
                        return self._texto_concepto_sin_abrev_re(str(v).strip())[:200]
        return ''

    @property
    def listado_detalle_l1(self):
        """Primera línea del bloque «Detalle» (nombre del concepto / operación)."""
        from_json = self._primer_texto_detalle_desde_json()
        if from_json:
            return from_json
        nombre = self.nombre_concepto_catalogo
        if nombre:
            return nombre
        t = self._texto_concepto_sin_abrev_re(self.concepto_sin_pipe_conceptos().strip())
        if not t:
            return '—'
        if '\n' in t:
            primera = self._texto_concepto_sin_abrev_re(t.split('\n', 1)[0].strip())
            return primera[:160]
        if len(t) > 120:
            return t[:117] + '...'
        return t

    @property
    def listado_detalle_observacion(self):
        """Texto libre del movimiento (detalle del formulario o segunda línea del concepto)."""
        raw = self.concepto_sin_pipe_conceptos().strip()
        if ' — ' in raw:
            tail = raw.split(' — ', 1)[1].strip()
            if tail:
                return tail[:200]
        if '\n' in raw:
            tail = raw.split('\n', 1)[1].strip()
            if tail:
                return tail[:200]
        return ''

    @property
    def listado_detalle_l2(self):
        """Segunda línea: comprobante, período, a quién corresponde."""
        parts = []
        base = self._texto_concepto_sin_abrev_re(self.concepto_sin_pipe_conceptos())
        if '\n' in base:
            second = self._texto_concepto_sin_abrev_re(base.split('\n', 1)[1].strip())
            if second:
                parts.append(second[:140])
        if self.numero_liquidacion:
            parts.append(str(self.numero_liquidacion).strip())
        if self.fecha_desde and self.fecha_hasta:
            parts.append(
                f"{self.fecha_desde.strftime('%d/%m/%Y')} — {self.fecha_hasta.strftime('%d/%m/%Y')}"
            )
        elif self.fecha_desde:
            parts.append(self.fecha_desde.strftime('%d/%m/%Y'))
        imput = self.etiqueta_imputacion_corresponde()
        if imput:
            parts.append(imput)
        elif self.a_descontar:
            try:
                parts.append(self.get_a_descontar_display().upper())
            except Exception:
                pass
        if not parts:
            return '—'
        return ' · '.join(parts)

    def etiqueta_imputacion_corresponde(self):
        """Texto del reparto oficina / propietario / inquilino si hay montos cargados."""
        from inmobiliaria.decimal_utils import format_monto_argentino

        bloques = []
        for etiqueta, val in (
            ('OF', getattr(self, 'monto_a_oficina', None)),
            ('PROP', getattr(self, 'monto_a_propietario', None)),
            ('INQ', getattr(self, 'monto_a_inquilino', None)),
        ):
            m = Decimal(str(val or 0))
            if m > 0:
                bloques.append(f'{etiqueta} ${format_monto_argentino(m)}')
        return ' · '.join(bloques)

    def _extraer_numero_operacion_desde_concepto(self):
        texto = self.concepto_sin_pipe_conceptos()
        if not texto:
            return ''
        for pat in (
            r'Operaci[oó]n\s*#?\s*(\d+)',
            r'Operacion\s*#?\s*(\d+)',
            r'Reserva\s*#?\s*(\d+)',
        ):
            m = re.search(pat, texto, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return ''

    @property
    def tipo_letra_listado(self):
        """I / E como en consulta de caja clásica."""
        return 'I' if (self.tipo or '').strip().upper() == TipoMovimientoCajaEnum.INGRESO else 'E'

    @property
    def numero_operacion_listado(self):
        """Nº de operación/reserva inferido del concepto; 0 si no hay."""
        n = self._extraer_numero_operacion_desde_concepto()
        return n if n else '0'

    @property
    def comprobante_listado(self):
        """Número de comprobante/recibo; formato por defecto si está vacío."""
        n = (self.numero_liquidacion or '').strip()
        if n:
            return n
        return '0000-00000000'

    @property
    def listado_detalle_tabla_secundario(self):
        """Línea secundaria de detalle sin repetir el nº de comprobante (ya va en columna propia)."""
        parts = []
        obs = (self.listado_detalle_observacion or '').strip()
        if obs:
            parts.append(obs)
        base = self._texto_concepto_sin_abrev_re(self.concepto_sin_pipe_conceptos())
        if '\n' in base:
            second = self._texto_concepto_sin_abrev_re(base.split('\n', 1)[1].strip())
            if second and second not in parts:
                parts.append(second[:140])
        if self.fecha_desde and self.fecha_hasta:
            parts.append(
                f"{self.fecha_desde.strftime('%d/%m/%Y')} — {self.fecha_hasta.strftime('%d/%m/%Y')}"
            )
        elif self.fecha_desde:
            parts.append(self.fecha_desde.strftime('%d/%m/%Y'))
        if self.a_descontar:
            try:
                parts.append(self.get_a_descontar_display().upper())
            except Exception:
                pass
        if not parts:
            return '—'
        return ' · '.join(parts)

    def _direccion_solo_resumen(self):
        """Dirección de la propiedad sin nº de ficha (resumen impreso)."""
        if self.propiedad_id:
            try:
                prop = self.propiedad
                dir_ = (getattr(prop, 'direccion', None) or '').strip()
                if dir_:
                    return dir_.upper()
            except Exception:
                pass
        l2 = (self.listado_concepto_l2 or '').strip()
        if l2 and '(' in l2:
            return l2.split('(', 1)[0].strip()
        return l2

    def _propietario_resumen_liquidacion(self):
        """Apellido y nombre del propietario (pago de liquidación)."""
        if self.propiedad_id:
            try:
                prop = self.propiedad
                po = getattr(prop, 'propietario', None)
                if po:
                    ap = (getattr(po, 'apellido', None) or '').strip()
                    nom = (getattr(po, 'nombre', None) or '').strip()
                    if ap and nom:
                        return f'{ap}, {nom}'
                    return ap or nom or ''
            except Exception:
                pass
        for fuente in (
            self.listado_detalle_l1 or '',
            self.concepto_sin_pipe_conceptos() or '',
        ):
            m = re.search(
                r'Pago\s+liquidaci[oó]n\s*#\s*\d+\s*[—\-–]\s*(.+)',
                fuente,
                re.I,
            )
            if m:
                tail = m.group(1).split('\n')[0].strip()
                if tail:
                    return tail[:120]
        return ''

    @property
    def listado_detalle_resumen_imprimir(self):
        """
        Detalle breve para el resumen de caja impreso (sin CBU, fechas ni texto largo).
        """
        cat = (self.listado_concepto_l1 or '').strip()
        cat_u = cat.upper()
        direccion = self._direccion_solo_resumen()

        if cat_u == 'ALQUILER A COBRAR':
            return direccion or '—'

        if cat_u == 'LIQUIDACIONES':
            prop = self._propietario_resumen_liquidacion()
            if prop and direccion:
                return f'{prop} — {direccion}'
            return prop or direccion or '—'

        det = (self.listado_detalle_l1 or '').strip()
        if det in ('—', cat):
            det = ''
        if direccion:
            if cat:
                return f'{cat}\n{direccion}'
            return direccion
        if det and det.upper() != cat_u:
            return f'{cat}\n{det}' if cat else det
        return cat or det or '—'

    def descripcion_para_gasto_liquidacion_propietario(self):
        """
        Texto legible para liquidaciones (egreso descontable al propietario).
        Usa el mismo criterio que el listado de caja (detalle / categoría) en lugar de solo «Egreso #id».
        """
        bits = []
        l1 = (self.listado_detalle_l1 or '').strip()
        if l1 and l1 != '—':
            bits.append(l1)
        l2 = (self.listado_detalle_l2 or '').strip()
        if l2 and l2 != '—':
            bits.append(l2)
        if not bits:
            base = self.concepto_sin_pipe_conceptos().strip()
            if base:
                bits.append(self._texto_concepto_sin_abrev_re(base))
        if not bits:
            sec = (self.listado_detalle_tabla_secundario or '').strip()
            if sec and sec != '—':
                bits.append(sec)
        if not bits:
            try:
                tipo_c = (self.get_tipo_comprobante_display() or '').strip() or (self.tipo_comprobante or '')
            except Exception:
                tipo_c = self.tipo_comprobante or ''
            suf = f' · {tipo_c}' if tipo_c else ''
            return f'Egreso de caja #{self.id}{suf} · ${self.monto_total}'
        return ' · '.join(bits)

    class Meta:
        db_table = 'inmobiliaria_movimientocaja'
        ordering = ['-fecha']
        default_manager_name = 'objects'
        base_manager_name = 'all_objects'

class Concepto(models.Model):
    id = models.CharField(max_length=20, primary_key=True)  # ID personalizado
    nombre = models.CharField(max_length=100)
    fecha_creacion = models.DateTimeField(default=timezone.now)  # Cambiado de auto_now_add a default
    sucursal = models.ForeignKey('Sucursal', on_delete=models.CASCADE, related_name='conceptos', null=True)  # null=True temporalmente

    class Meta:
        verbose_name = "Concepto"
        verbose_name_plural = "Conceptos"
        ordering = ['id']
        unique_together = ['id', 'sucursal']  # ID único por sucursal

    def __str__(self):
        return f"{self.id} - {self.nombre}"

    @property
    def etiqueta_numero_catalogo(self):
        """Texto del número en pantallas: el id «RE» se muestra como RECIBO."""
        cid = (self.id or '').strip().upper()
        if cid == 'RE':
            return 'RECIBO'
        return self.id or ''

    def indica_movimiento_vale_productor(self):
        """
        True si este concepto de caja debe asociar un ValeVendedor al grabar un movimiento
        con productor (id «90», que empiece por «vale» o nombre que contenga «vale»).
        """
        nid = (self.id or "").strip().lower()
        if nid in ("90",) or nid.startswith("vale"):
            return True
        return bool(_CONCEPTO_VALE_NOMBRE_RE.search(self.nombre or ""))

class Banco(models.Model):
    nombre = models.CharField(max_length=100)
    
    def __str__(self):
        return self.nombre

class Registro(models.Model):
    # Datos básicos
    interno_caja = models.CharField(max_length=50, unique=True)
    fecha = models.DateTimeField(auto_now_add=True)
    tipo = models.CharField(
        max_length=2,
        choices=TipoMovimientoCajaEnum.choices,
        default=TipoMovimientoCajaEnum.INGRESO
    )
    
    # Comprobante
    tipo_comprobante = models.CharField(
        max_length=2,
        choices=TipoComprobanteEnum.choices
    )
    fecha_comprobante = models.DateField()
    
    # Montos
    liquidacion = models.DecimalField(max_digits=10, decimal_places=2)
    efectivo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cheques = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tarjeta = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deposito = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    qr = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Referencias
    cuenta = models.ForeignKey('Cuenta', on_delete=models.SET_NULL, null=True)
    propiedad = models.ForeignKey('Propiedad', on_delete=models.SET_NULL, null=True)
    concepto = models.ForeignKey(Concepto, on_delete=models.SET_NULL, null=True)
    
    # Fechas de período
    fecha_desde = models.DateField(null=True, blank=True)
    fecha_hasta = models.DateField(null=True, blank=True)
    
    # Opciones adicionales
    tipo_descuento = models.CharField(
        max_length=2,
        choices=TipoDescuentoEnum.choices,
        null=True,
        blank=True
    )
    con_iva = models.BooleanField(default=False)
    pasa_liquidaciones = models.BooleanField(default=False)
    
    # Metadata
    sucursal = models.ForeignKey('Sucursal', on_delete=models.CASCADE)
    empleado = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    
    def __str__(self):
        return f"Interno {self.interno_caja} - {self.get_tipo_display()}"

class Cuenta(models.Model):
    numero = models.CharField(max_length=50)
    nombre = models.CharField(max_length=200)
    
    def __str__(self):
        return f"{self.numero} - {self.nombre}"

class BancoTarjeta(models.Model):
    nombre = models.CharField(max_length=100)
    
    def __str__(self):
        return self.nombre
