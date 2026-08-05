import re
from datetime import date
from decimal import Decimal

from django.db import models
from django.db.models import Sum
from django.utils import timezone

from .persona import Vendedor
from .caja import MovimientoCaja, TipoMovimientoCajaEnum

_MESES_ES_A_NUM = {
    'enero': 1,
    'febrero': 2,
    'marzo': 3,
    'abril': 4,
    'mayo': 5,
    'junio': 6,
    'julio': 7,
    'agosto': 8,
    'septiembre': 9,
    'setiembre': 9,
    'octubre': 10,
    'noviembre': 11,
    'diciembre': 12,
}

# Ej: "INGRESO VALE P/ PAGO SUELDO JUNIO DE 2026"
_RE_PAGO_SUELDO_MES = re.compile(
    r'pago\s+sueldo\s+'
    r'(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)'
    r'(?:\s+de)?\s+(\d{4})',
    re.IGNORECASE,
)


def parse_mes_pago_sueldo_desde_texto(texto):
    """Devuelve 'YYYY-MM' si el texto menciona pago de sueldo de un mes, o None."""
    if not texto:
        return None
    m = _RE_PAGO_SUELDO_MES.search(str(texto))
    if not m:
        return None
    mes = _MESES_ES_A_NUM.get(m.group(1).lower())
    if not mes:
        return None
    try:
        anio = int(m.group(2))
    except (TypeError, ValueError):
        return None
    return f'{anio:04d}-{mes:02d}'


def _fecha_solo_dia(valor):
    if valor is None:
        return None
    if isinstance(valor, date) and not hasattr(valor, 'hour'):
        return valor
    try:
        return timezone.localtime(valor).date() if timezone.is_aware(valor) else valor.date()
    except Exception:
        try:
            return valor.date()
        except Exception:
            return None


def mapa_mes_imputacion_vales(vales):
    """
    Mes YYYY-MM al que imputar cada vale en el resumen vs comisiones.

    Un ingreso de «pago sueldo MES AÑO» y los egresos desde el 1° de ese mes
    hasta la fecha del ingreso se imputan a ese mes de sueldo (no al mes
    calendario del movimiento). Así el descuento del recibo no deja el vale
    viejo restando en el mes del pago.
    """
    vales_list = list(vales)
    imputacion = {}
    claimed = set()

    ingresos_sueldo = []
    for vale in vales_list:
        if (getattr(vale, 'tipo_vale', None) or TipoMovimientoCajaEnum.EGRESO) != TipoMovimientoCajaEnum.INGRESO:
            continue
        texto = f'{vale.concepto or ""} {vale.observaciones or ""}'
        mes_sueldo = parse_mes_pago_sueldo_desde_texto(texto)
        if mes_sueldo and vale.fecha:
            ingresos_sueldo.append((vale, mes_sueldo))

    ingresos_sueldo.sort(key=lambda item: item[0].fecha or timezone.now())

    for ingreso, mes_sueldo in ingresos_sueldo:
        try:
            anio_i, mes_i = mes_sueldo.split('-', 1)
            inicio = date(int(anio_i), int(mes_i), 1)
        except (TypeError, ValueError):
            continue
        fin = _fecha_solo_dia(ingreso.fecha)
        if not fin:
            continue

        imputacion[ingreso.pk] = mes_sueldo
        claimed.add(ingreso.pk)

        for vale in vales_list:
            if vale.pk in claimed:
                continue
            if (getattr(vale, 'tipo_vale', None) or TipoMovimientoCajaEnum.EGRESO) != TipoMovimientoCajaEnum.EGRESO:
                continue
            vd = _fecha_solo_dia(vale.fecha)
            if vd is None:
                continue
            if inicio <= vd <= fin:
                imputacion[vale.pk] = mes_sueldo
                claimed.add(vale.pk)

    for vale in vales_list:
        if vale.pk in imputacion:
            continue
        vd = _fecha_solo_dia(vale.fecha)
        if vd is None:
            continue
        imputacion[vale.pk] = vd.strftime('%Y-%m')

    return imputacion


class TipoBeneficiarioVale(models.TextChoices):
    VENDEDOR = 'vendedor', 'Vendedor / productor'
    OTRO = 'otro', 'Otra persona'


class ValeVendedor(models.Model):
    """
    Registra vales (préstamos / devoluciones) ligados a caja.
    Pueden imputarse a un vendedor (descuentan comisiones) o a otra persona.
    """

    tipo_beneficiario = models.CharField(
        max_length=20,
        choices=TipoBeneficiarioVale.choices,
        default=TipoBeneficiarioVale.VENDEDOR,
        verbose_name='Tipo de beneficiario',
    )
    vendedor = models.ForeignKey(
        Vendedor,
        on_delete=models.CASCADE,
        related_name='vales',
        verbose_name='Vendedor',
        null=True,
        blank=True,
    )
    beneficiario_nombre = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Nombre beneficiario',
    )
    beneficiario_apellido = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Apellido beneficiario',
    )
    beneficiario_dni = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='DNI beneficiario',
    )

    movimiento_caja = models.ForeignKey(
        MovimientoCaja,
        on_delete=models.CASCADE,
        related_name='vales',
        verbose_name='Movimiento de Caja',
        null=True,
        blank=True,
    )

    tipo_vale = models.CharField(
        max_length=2,
        choices=TipoMovimientoCajaEnum.choices,
        default=TipoMovimientoCajaEnum.EGRESO,
        verbose_name='Tipo de vale',
        help_text='EG: dinero que sale de caja hacia el beneficiario. IN: dinero que ingresa a caja.',
    )

    monto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name='Monto del Vale',
    )

    concepto = models.CharField(
        max_length=200,
        verbose_name='Concepto',
        default='Vale',
    )
    observaciones = models.TextField(
        blank=True,
        verbose_name='Observaciones',
    )

    fecha = models.DateTimeField(
        verbose_name='Fecha del Vale',
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de Creación',
    )

    usuario_creador = models.ForeignKey(
        Vendedor,
        on_delete=models.SET_NULL,
        null=True,
        related_name='vales_otorgados',
        verbose_name='Usuario que Otorgó el Vale',
    )

    class Meta:
        verbose_name = 'Vale'
        verbose_name_plural = 'Vales'
        ordering = ['-fecha']

    def nombre_beneficiario(self):
        if self.vendedor_id:
            return self.vendedor.nombre_completo_vendedor()
        apellido = (self.beneficiario_apellido or '').strip()
        nombre = (self.beneficiario_nombre or '').strip()
        if apellido and nombre:
            texto = f'{apellido}, {nombre}'
        else:
            texto = apellido or nombre
        dni = (self.beneficiario_dni or '').strip()
        if dni:
            texto = f'{texto} (DNI {dni})' if texto else f'DNI {dni}'
        return texto or 'Sin beneficiario'

    def __str__(self):
        return f'Vale {self.id} - {self.nombre_beneficiario()} - ${self.monto}'

    @staticmethod
    def monto_total_movimiento(movimiento):
        """Suma de medios de pago del movimiento (ARS + USD efectivo)."""
        return (
            Decimal(str(movimiento.monto_efectivo or 0))
            + Decimal(str(movimiento.monto_cheque or 0))
            + Decimal(str(movimiento.monto_tarjeta or 0))
            + Decimal(str(movimiento.monto_deposito or 0))
            + Decimal(str(getattr(movimiento, 'monto_dolares', None) or 0))
        )

    @classmethod
    def _validar_beneficiario(cls, *, tipo_beneficiario, vendedor=None,
                              beneficiario_nombre='', beneficiario_apellido=''):
        if tipo_beneficiario == TipoBeneficiarioVale.VENDEDOR:
            if not vendedor:
                raise ValueError('Debe indicar un vendedor.')
            return
        nom = (beneficiario_nombre or '').strip()
        ape = (beneficiario_apellido or '').strip()
        if not nom and not ape:
            raise ValueError('Indicá nombre o apellido del beneficiario.')

    @classmethod
    def crear_desde_movimiento(
        cls,
        movimiento,
        vendedor=None,
        usuario_creador=None,
        observaciones='',
        tipo_beneficiario=TipoBeneficiarioVale.VENDEDOR,
        beneficiario_nombre='',
        beneficiario_apellido='',
        beneficiario_dni='',
    ):
        """Registra un vale ligado a un movimiento de caja ya guardado."""
        cls._validar_beneficiario(
            tipo_beneficiario=tipo_beneficiario,
            vendedor=vendedor,
            beneficiario_nombre=beneficiario_nombre,
            beneficiario_apellido=beneficiario_apellido,
        )
        monto = cls.monto_total_movimiento(movimiento)
        if monto <= 0:
            raise ValueError('El movimiento no tiene importe total mayor a cero.')
        tipo = movimiento.tipo
        if tipo not in (TipoMovimientoCajaEnum.INGRESO, TipoMovimientoCajaEnum.EGRESO):
            raise ValueError('Tipo de movimiento inválido para vale.')
        base = (movimiento.concepto or '').strip()[:120] or 'Movimiento caja'
        etiqueta = 'Egreso' if tipo == TipoMovimientoCajaEnum.EGRESO else 'Ingreso'
        concepto = f'Vale {etiqueta} — {base}'[:200]
        return cls.objects.create(
            tipo_beneficiario=tipo_beneficiario,
            vendedor=vendedor,
            beneficiario_nombre=(beneficiario_nombre or '').strip(),
            beneficiario_apellido=(beneficiario_apellido or '').strip(),
            beneficiario_dni=(beneficiario_dni or '').strip(),
            movimiento_caja=movimiento,
            monto=monto,
            tipo_vale=tipo,
            concepto=concepto,
            observaciones=observaciones or '',
            usuario_creador=usuario_creador,
            fecha=timezone.now(),
        )

    @classmethod
    def crear_vale(
        cls,
        monto,
        caja,
        concepto='Vale',
        observaciones='',
        usuario_creador=None,
        vendedor=None,
        tipo_beneficiario=TipoBeneficiarioVale.VENDEDOR,
        beneficiario_nombre='',
        beneficiario_apellido='',
        beneficiario_dni='',
    ):
        """Crea un vale de egreso y su movimiento de caja asociado (efectivo)."""
        cls._validar_beneficiario(
            tipo_beneficiario=tipo_beneficiario,
            vendedor=vendedor,
            beneficiario_nombre=beneficiario_nombre,
            beneficiario_apellido=beneficiario_apellido,
        )
        sucursal = vendedor.sucursal if vendedor else caja.sucursal
        vale_tmp = cls(
            tipo_beneficiario=tipo_beneficiario,
            vendedor=vendedor,
            beneficiario_nombre=(beneficiario_nombre or '').strip(),
            beneficiario_apellido=(beneficiario_apellido or '').strip(),
            beneficiario_dni=(beneficiario_dni or '').strip(),
        )
        label = vale_tmp.nombre_beneficiario()
        movimiento = MovimientoCaja.objects.create(
            caja=caja,
            sucursal=sucursal,
            tipo=TipoMovimientoCajaEnum.EGRESO,
            concepto=f'Vale para {label} - {concepto}',
            monto_efectivo=monto,
            empleado=usuario_creador or vendedor,
        )
        return cls.objects.create(
            tipo_beneficiario=tipo_beneficiario,
            vendedor=vendedor,
            beneficiario_nombre=(beneficiario_nombre or '').strip(),
            beneficiario_apellido=(beneficiario_apellido or '').strip(),
            beneficiario_dni=(beneficiario_dni or '').strip(),
            movimiento_caja=movimiento,
            monto=monto,
            tipo_vale=TipoMovimientoCajaEnum.EGRESO,
            concepto=concepto,
            observaciones=observaciones,
            usuario_creador=usuario_creador,
            fecha=timezone.now(),
        )

    def get_mes_año(self):
        return self.fecha.strftime('%Y-%m')

    @classmethod
    def total_saldo_para_comisiones(cls, vendedor):
        """Efecto neto de vales del vendedor sobre comisiones (solo tipo vendedor)."""
        eg = (
            cls.objects.filter(
                vendedor=vendedor,
                tipo_beneficiario=TipoBeneficiarioVale.VENDEDOR,
                tipo_vale=TipoMovimientoCajaEnum.EGRESO,
            ).aggregate(t=Sum('monto'))['t']
            or Decimal('0')
        )
        ing = (
            cls.objects.filter(
                vendedor=vendedor,
                tipo_beneficiario=TipoBeneficiarioVale.VENDEDOR,
                tipo_vale=TipoMovimientoCajaEnum.INGRESO,
            ).aggregate(t=Sum('monto'))['t']
            or Decimal('0')
        )
        return eg - ing

    def mes_key_calendario(self):
        vd = _fecha_solo_dia(self.fecha)
        return vd.strftime('%Y-%m') if vd else None
