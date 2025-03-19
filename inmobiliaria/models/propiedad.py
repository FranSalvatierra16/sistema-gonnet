from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import Q
from django.utils.timezone import now
from django.conf import settings
from django.utils import timezone

import datetime
from .persona import Propietario, Inquilino, Vendedor
from .sucursal import Sucursal
import uuid
import os

# Definiciones de tipos de vista, valoración e inmuebles
TIPOS_VISTA = [
    ('a_la_calle', 'A la calle'),
    ('contrafrente', 'Contrafrente'),
    ('lateral', 'Lateral'),
]

TIPOS_VALORACION = [
    ('excelente', 'Excelente'),
    ('muy_bueno', 'Muy bueno'),
    ('bueno', 'Bueno'),
    ('regular', 'Regular'),
    ('malo', 'Malo'),
]

TIPOS_INMUEBLES = [
    ('campo', 'Campo'),
    ('casa-chalet', 'Casa - Chalet'),
    ('departamento', 'Departamento'),
    ('fondo_de_comercio', 'Fondo de Comercio'),
    ('galpon', 'Galpón'),
    ('hotel', 'Hotel'),
    ('local', 'Local'),
    ('oficina', 'Oficina'),
    ('ph', 'PH'),
    ('quinta', 'Quinta'),
    ('terreno', 'Terreno'),
    ('cochera', 'Cochera'),
    ('edificio', 'Edificio'),
    ('inmueble_en_block', 'Inmueble en Block'),
    ('duplex', 'Dúplex'),
    ('emprendimiento', 'Emprendimiento'),
    ('cabaña', 'Cabaña'), 
    ('casaquinta', 'Casa Quinta'),
    ('deposito', 'Depósito'), 
]

class HistorialDisponibilidad(models.Model):
    ESTADO_CHOICES = [
        ('disponible', 'Disponible'),
        ('reservada', 'Reservada'),
        ('alquilada', 'Alquilada'),
        ('vendida', 'Vendida'),
        ('no_disponible', 'No Disponible')
    ]

    propiedad = models.ForeignKey(
        'Propiedad',
        on_delete=models.CASCADE,
        related_name='historial_disponibilidad'
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='disponible'
    )

    def __str__(self):
        return f"{self.propiedad} - {self.estado}"

    @classmethod
    def registrar_cambio(cls, propiedad, estado):
        return cls.objects.create(
            propiedad=propiedad,
            estado=estado
        )

class Propiedad(models.Model):
    DIRECCION_MAX_LENGTH = 255
    UBICACION_MAX_LENGTH = 255
    DEPARTAMENTO_CHOICES = [(chr(i), chr(i)) for i in range(ord('A'), ord('Z')+1)]
    ID_MAX_LENGTH = 255 # Define un tamaño máximo para el campo id
    id = models.CharField(max_length=ID_MAX_LENGTH, primary_key=True, unique=True, null=False, blank=False)
    direccion = models.CharField(max_length=DIRECCION_MAX_LENGTH)
    ubicacion = models.CharField(max_length=UBICACION_MAX_LENGTH)
    descripcion = models.TextField(blank=True)
    tipo_inmueble = models.CharField(max_length=20, choices=TIPOS_INMUEBLES, default='departamento')
    vista = models.CharField(max_length=20, choices=TIPOS_VISTA, default='a_la_calle')
    piso = models.CharField(
        max_length=10,
        verbose_name="Piso",
        help_text="Número o descripción del piso (ej: PB, 1, 15, etc.)"
    )
    departamento = models.CharField(
        max_length=10,
        verbose_name="Departamento",
        help_text="Número o letra del departamento"
    )
    ambientes = models.IntegerField()
    valoracion = models.CharField(max_length=20, choices=TIPOS_VALORACION, default='bueno')
    cuenta_bancaria = models.CharField(max_length=100, blank=True, help_text="Número de cuenta bancaria para depósitos")
    propietario = models.ForeignKey(Propietario, on_delete=models.CASCADE, related_name='propiedades')  
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='propiedades')# Cambiado a obligatorio
    llave = models.IntegerField(unique=True, null=True, blank=True, verbose_name="Número de llave")
    
    # Resto del código permanece igual
    
    # precio_diario = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Precio por día")
    # habilitar_precio_diario = models.BooleanField(default=False, verbose_name="Habilitar precio por día")
    # precio_venta = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Precio por venta")
    # habilitar_precio_venta = models.BooleanField(default=False, verbose_name="Habilitar precio por venta")
    # precio_alquiler = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Precio por alquiler")
    # habilitar_precio_alquiler = models.BooleanField(default=False, verbose_name="Habilitar precio por alquiler")

    # Atributos adicionales
    amoblado = models.BooleanField(default=False)
    cochera = models.BooleanField(default=False)
    tv_smart = models.BooleanField(default=False)
    wifi = models.BooleanField(default=False)
    dependencia = models.BooleanField(default=False)
    patio = models.BooleanField(default=False)
    parrilla = models.BooleanField(default=False)
    piscina = models.BooleanField(default=False)
    reciclado = models.BooleanField(default=False)
    a_estrenar = models.BooleanField(default=False)
    terraza = models.BooleanField(default=False)
    balcon = models.BooleanField(default=False)
    baulera = models.BooleanField(default=False)
    lavadero = models.BooleanField(default=False)
    seguridad = models.BooleanField(default=False)
    vista_al_Mar = models.BooleanField(default=False)
    vista_panoramica = models.BooleanField(default=False)
    apto_credito = models.BooleanField(default=False)

    # Campos para habilitar diferentes tipos de alquiler/venta
    habilitar_venta = models.BooleanField(default=False, verbose_name="Habilitar para Venta")
    habilitar_23_meses = models.BooleanField(default=False, verbose_name="Habilitar para 24 Meses")
    habilitar_invierno = models.BooleanField(default=False, verbose_name="Habilitar para Invierno")

    # Precios para cada tipo
    precio_venta = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True,
        verbose_name="Precio de Venta"
    )
    precio_23_meses = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True,
        verbose_name="Precio 23 Meses"
    )
    precio_invierno = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True,
        verbose_name="Precio Invierno"
    )

    fichado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='propiedades_fichadas'
    )
    fecha_fichado = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de fichado"
    )

    TIPO_CLIENTE_CHOICES = [
        ('PARTICULAR', 'Particular'),
        ('EMPRESA', 'Empresa'),
        ('ESTUDIANTE', 'Estudiante'),
    ]
    
    tipo_cliente = models.CharField(
        max_length=20,
        choices=TIPO_CLIENTE_CHOICES,
        default='PARTICULAR'
    )

    class Meta:
        verbose_name = "Propiedad"
        verbose_name_plural = "Propiedades"

    def __str__(self):
        return f"{self.id} - {self.direccion}"

    def esta_disponible_en_fecha(self, fecha_inicio, fecha_fin):
        """Verifica si una propiedad está disponible entre las fechas dadas."""
        if not fecha_inicio or not fecha_fin:
            return False

        # Verificar si hay disponibilidades que cubran el período
        disponibilidades = self.disponibilidades.filter(
            fecha_inicio__lte=fecha_fin,
            fecha_fin__gte=fecha_inicio
        ).exists()

        # Verificar si hay reservas que se superpongan
        reservas_superpuestas = self.reservas.filter(
            fecha_inicio__lte=fecha_fin,
            fecha_fin__gte=fecha_inicio
        ).exists()

        # La propiedad está disponible si:
        # 1. No hay disponibilidades específicas definidas (está siempre disponible) O hay una 
        # disponibilidad que cubre el período
        # 2. Y no hay reservas que se superpongan
        return (not self.disponibilidades.exists() or disponibilidades) and not reservas_superpuestas

    # def clean(self):
    #     super().clean()

    #     precios_habilitados = [
    #         self.habilitar_precio_diario,
    #         self.habilitar_precio_venta,
    #         self.habilitar_precio_alquiler
    #     ]

    #     if not any(precios_habilitados):
    #         raise ValidationError(_('Debe habilitar al menos un tipo de precio.'))

    #     if self.habilitar_precio_diario and not self.precio_diario:
    #         raise ValidationError(_('Debe ingresar un precio por día si está habilitado.'))

    #     if self.habilitar_precio_venta and not self.precio_venta:
    #         raise ValidationError(_('Debe ingresar un precio de venta si está habilitado.'))

    #     if self.habilitar_precio_alquiler and not self.precio_alquiler:
    #         raise ValidationError(_('Debe ingresar un precio de alquiler si está habilitado.'))

    def save(self, *args, **kwargs):
        creating = self._state.adding 
        is_new = self._state.adding# Detectar si es una creación
        super().save(*args, **kwargs)
    
        if creating:
            self.crear_precios_iniciales()
      

    @transaction.atomic
    def crear_precios_iniciales(self):
        tipos_de_precios = [
            TipoPrecio.QUINCENA_1_DICIEMBRE, TipoPrecio.QUINCENA_2_DICIEMBRE,
            TipoPrecio.QUINCENA_1_ENERO, TipoPrecio.QUINCENA_2_ENERO,
            TipoPrecio.QUINCENA_1_FEBRERO, TipoPrecio.QUINCENA_2_FEBRERO,
            TipoPrecio.QUINCENA_1_MARZO, TipoPrecio.QUINCENA_2_MARZO,
            TipoPrecio.FINDE_LARGO,
            TipoPrecio.TEMPORADA_BAJA, TipoPrecio.VACACIONES_INVIERNO, 
        ]
        for tipo in tipos_de_precios:
            Precio.objects.get_or_create(
                propiedad=self,
                tipo_precio=tipo,
                defaults={'precio_total': 0, 'precio_por_dia': 0, 'ajuste_porcentaje': 0}
            )
  

    class Meta:
        verbose_name = "Propiedad"
        verbose_name_plural = "Propiedades"

    def __str__(self):
        return f"{self.direccion}"        

    def clean(self):
        super().clean()
        # Validar que si un tipo está habilitado, tenga precio
        if self.habilitar_venta and not self.precio_venta:
            raise ValidationError({'precio_venta': 'Debe ingresar un precio de venta si está habilitado.'})
        if self.habilitar_23_meses and not self.precio_23_meses:
            raise ValidationError({'precio_23_meses': 'Debe ingresar un precio para 23 meses si está habilitado.'})
        if self.habilitar_invierno and not self.precio_invierno:
            raise ValidationError({'precio_invierno': 'Debe ingresar un precio de invierno si está habilitado.'})

    def fichar(self, usuario):
        """Método para fichar una propiedad"""
        self.fichado_por = usuario
        self.fecha_fichado = timezone.now()
        self.save()

    def desfichar(self):
        """Método para desfichar una propiedad"""
        self.fichado_por = None
        self.fecha_fichado = None
        self.save()

class ImagenPropiedad(models.Model):
    propiedad = models.ForeignKey(
        Propiedad, 
        on_delete=models.CASCADE,
        related_name='imagenes_propiedad'
    )
    imagen = models.ImageField(upload_to='propiedades/')
    orden = models.IntegerField(default=0)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['orden']
        verbose_name = 'Imagen de propiedad'
        verbose_name_plural = 'Imágenes de propiedades'

    def __str__(self):
        return f"Imagen {self.orden} de {self.propiedad}"


class Reserva(models.Model):
    propiedad = models.ForeignKey(Propiedad, on_delete=models.CASCADE, related_name='reservas')
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    hora_ingreso = models.TimeField(default=datetime.time(15, 0))
    hora_egreso = models.TimeField(default=datetime.time(10, 0))
    fecha_creacion = models.DateTimeField(default=now)
    vendedor = models.ForeignKey(Vendedor, on_delete=models.SET_NULL, null=True, related_name='reservas_vendedor')
    cliente = models.ForeignKey(Inquilino, on_delete=models.SET_NULL, null=True, related_name='reservas_cliente')
    precio_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    senia = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cuota_pendiente = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estado = models.CharField(max_length=20, choices=[('en_espera', 'En Espera'), ('confirmada', 'Confirmada'), ('pagada', 'Pagada')], default='en_espera')
    sucursal = models.ForeignKey(
        'Sucursal',  # Asegúrate de que Sucursal esté importado
        on_delete=models.CASCADE,
        related_name='reservas_sucursal',
        null=True  # Permitimos null temporalmente para la migración
    )

    deposito_garantia = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        # Asegúrate de que la sucursal esté establecida si no está definida
        if not self.sucursal and self.propiedad:
            self.sucursal = self.propiedad.sucursal

        is_new = self._state.adding

        # Verificar disponibilidad antes de guardar
        if is_new:
            # Si no hay disponibilidades definidas, asumimos que está disponible
            if not self.propiedad.disponibilidades.exists():
                disponible = True
            else:
                disponible = self.propiedad.esta_disponible_en_fecha(self.fecha_inicio, self.fecha_fin)
                
            if not disponible:
                raise ValidationError('La propiedad no está disponible para las fechas seleccionadas.')

        super().save(*args, **kwargs)

        if is_new:
            self.cuota_pendiente = self.precio_total
            self.senia = 0
            
            # Actualizar el historial de disponibilidad
            HistorialDisponibilidad.registrar_cambio(
                propiedad=self.propiedad,
                estado='reservada'
            )

    def actualizar_saldos(self):
        """Actualiza los saldos basados en los pagos realizados"""
        from django.db.models import Sum
        # Calcular el total de pagos
        total_pagado = self.pagos.aggregate(Sum('monto'))['monto__sum'] or 0
        
        # Actualizar seña (total pagado) y cuota pendiente
        self.senia = total_pagado
        self.cuota_pendiente = self.precio_total - total_pagado
        
        # Guardar los cambios
        self.save()

    def terminar_reserva(self):
        """Método para terminar una reserva"""
        self.estado = 'pagada'
        self.save()
        
        # Actualizar el historial de disponibilidad
        historial = HistorialDisponibilidad.objects.filter(
            propiedad=self.propiedad,
            fecha_inicio=self.fecha_inicio,
            fecha_fin=self.fecha_fin,
            estado='reservada'
        ).first()
        
        if historial:
            historial.estado = 'alquilada'
            historial.save()

    def __str__(self):
        return f"Reserva {self.id} - {self.propiedad}"

class Disponibilidad(models.Model):
    propiedad = models.ForeignKey(
        'Propiedad', 
        on_delete=models.CASCADE, 
        related_name='disponibilidades'
    )
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()

    def save(self, *args, **kwargs):
        if not hasattr(self, 'propiedad') or not self.propiedad:
            raise ValidationError(_('La propiedad es requerida.'))
            
        if self.fecha_inicio and self.fecha_fin and self.fecha_inicio > self.fecha_fin:
            raise ValidationError(_('La fecha de inicio no puede ser posterior a la fecha de fin.'))

        is_new = self._state.adding
        
        # Verificar solapamiento
        solapamiento = Disponibilidad.objects.filter(
            propiedad=self.propiedad,
            fecha_fin__gte=self.fecha_inicio,
            fecha_inicio__lte=self.fecha_fin
        )
        
        if self.pk:  # Si es una edición
            solapamiento = solapamiento.exclude(pk=self.pk)
            
        if solapamiento.exists():
            raise ValidationError(_('Ya existe una disponibilidad para el rango de fechas seleccionado.'))

        super().save(*args, **kwargs)
        
        # Actualizar el historial de disponibilidad
        HistorialDisponibilidad.registrar_cambio(
            propiedad=self.propiedad,
            estado='disponible'
        )

    class Meta:
        verbose_name = _("Disponibilidad")
        verbose_name_plural = _("Disponibilidades")
        ordering = ['fecha_inicio']

    def __str__(self):
        return f"{self.propiedad} - {self.fecha_inicio} al {self.fecha_fin}"



class TipoPrecio(models.TextChoices):
    QUINCENA_1_DICIEMBRE = 'QUINCENA_1_DICIEMBRE', _('1ra quincena Diciembre')
    QUINCENA_2_DICIEMBRE = 'QUINCENA_2_DICIEMBRE', _('2da quincena Diciembre')
    QUINCENA_1_ENERO = 'QUINCENA_1_ENERO', _('1ra quincena Enero')
    QUINCENA_2_ENERO = 'QUINCENA_2_ENERO', _('2da quincena Enero')
    QUINCENA_1_FEBRERO = 'QUINCENA_1_FEBRERO', _('1ra quincena Febrero')
    QUINCENA_2_FEBRERO = 'QUINCENA_2_FEBRERO', _('2da quincena Febrero')
    QUINCENA_1_MARZO = 'QUINCENA_1_MARZO', _('1ra quincena Marzo')
    QUINCENA_2_MARZO = 'QUINCENA_2_MARZO', _('2da quincena Marzo')
    TEMPORADA_BAJA = 'TEMPORADA_BAJA', _('Temporada baja')
    VACACIONES_INVIERNO = 'VACACIONES_INVIERNO', _('Vacaciones Invierno')
    FINDE_LARGO = 'FINDE_LARGO', _('Finde largo')
    DICIEMBRE = 'DICIEMBRE', _('Diciembre')
    ENERO = 'ENERO', _('Enero')
    FEBRERO = 'FEBRERO', _('Febrero')
    MARZO = 'MARZO', _('Marzo')
    ESTUDIANTE = 'ESTUDIANTE', _('Estudiante')
    

class Precio(models.Model):
    propiedad = models.ForeignKey(Propiedad, on_delete=models.CASCADE, related_name='precios')
    tipo_precio = models.CharField(max_length=20, choices=TipoPrecio.choices)
    
    # Precios por día

    precio_toma = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        blank=True, 
        null=True,
        verbose_name="Precio Toma"
    )
    
    # Precios por toma
    precio_dia_toma = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        blank=True, 
        null=True,
        verbose_name="Precio dia: Toma"
    )
    precio_por_dia = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        blank=True, 
        null=True,
        verbose_name="Precio por día"
    )
    
    # Precios por propietario
  
    # Precio total (calculado)
    precio_total = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        blank=True, 
        null=True,
        verbose_name="Precio total"
    )
    
    ajuste_porcentaje = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0,
        verbose_name="Ajuste (%)"
    )

    class Meta:
        unique_together = ('propiedad', 'tipo_precio')

    def calcular_precio_total(self, fecha_inicio, fecha_fin):
        dias = (fecha_fin - fecha_inicio).days + 1
        base_price = 0

        if self.precio_por_dia:
            if 'QUINCENA' in self.tipo_precio or self.tipo_precio == 'VACACIONES_INVIERNO':
                if 'ENERO' in self.tipo_precio or 'MARZO' in self.tipo_precio or 'DICIEMBRE' in self.tipo_precio:
                    base_price = self.precio_por_dia * 16
                else:
                    base_price = self.precio_por_dia * 15
            elif self.tipo_precio == 'FINDE_LARGO':
                base_price = self.precio_por_dia * 4
            elif self.tipo_precio == 'TEMPORADA_BAJA':
                base_price = self.precio_por_dia * dias
            else:
                base_price = self.precio_por_dia * dias

        # Aplicar ajuste porcentual si se ha establecido
        if self.ajuste_porcentaje != 0:
            base_price *= (1 - self.ajuste_porcentaje / 100)

        return round(base_price, 2)

    def save(self, *args, **kwargs):
        if self.precio_por_dia is not None:
            # Calcular el precio total basado en el tipo de precio
            if 'QUINCENA' in self.tipo_precio or self.tipo_precio == 'VACACIONES_INVIERNO':
                if 'ENERO' in self.tipo_precio or 'MARZO' in self.tipo_precio or 'DICIEMBRE' in self.tipo_precio:
                    base_price = self.precio_por_dia * 16
                else:
                    base_price = self.precio_por_dia * 15
            elif self.tipo_precio == 'FINDE_LARGO':
                base_price = self.precio_por_dia * 4
            elif self.tipo_precio == 'TEMPORADA_BAJA':
                base_price = None  # No calcular precio total para días individuales
            else:
                base_price = self.precio_por_dia

            # Aplicar ajuste porcentual si se ha establecido
            if base_price is not None and self.ajuste_porcentaje != 0:
                base_price *= (1 - self.ajuste_porcentaje / 100)

            self.precio_total = round(base_price, 2) if base_price is not None else None

        super().save(*args, **kwargs)
class ConceptoPago(models.Model):
    codigo = models.CharField(max_length=10, unique=True)
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True)
    
    class Meta:
        ordering = ['codigo']
        verbose_name = "Concepto de Pago"
        verbose_name_plural = "Conceptos de Pago"

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

class Pago(models.Model):
    FORMA_PAGO_CHOICES = [
        ('efectivo', 'Efectivo'),
        ('transferencia', 'Transferencia'),
        ('tarjeta_credito', 'Tarjeta de Crédito'),
        ('tarjeta_debito', 'Tarjeta de Débito'),
        ('cheque', 'Cheque'),
        ('qr', 'QR'),
    ]

    reserva = models.ForeignKey('Reserva', on_delete=models.CASCADE, related_name='pagos')
    codigo = models.CharField(max_length=10, unique=True, editable=False)
    fecha = models.DateField(auto_now_add=True)
    forma_pago = models.CharField(max_length=20, choices=FORMA_PAGO_CHOICES)
    concepto = models.ForeignKey('ConceptoPago', on_delete=models.PROTECT)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Nuevos campos para tarjetas
    numero_tarjeta = models.CharField(
        max_length=16, 
        blank=True, 
        null=True,
        verbose_name="Número de Tarjeta",
        help_text="Últimos 4 dígitos de la tarjeta"
    )
    tipo_tarjeta = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Tipo de Tarjeta",
        choices=[
            ('visa', 'Visa'),
            ('mastercard', 'Mastercard'),
            ('american_express', 'American Express'),
            ('otro', 'Otro')
        ]
    )

    def clean(self):
        super().clean()
        if not self.pk:  # Solo validar al crear un nuevo pago
            # Verificar que el monto no supere la cuota pendiente
            if self.monto > self.reserva.cuota_pendiente:
                raise ValidationError({
                    'monto': f'El monto del pago (${self.monto}) no puede superar el saldo pendiente (${self.reserva.cuota_pendiente})'
                })
        if 'tarjeta' in self.forma_pago and not self.numero_tarjeta:
            raise ValidationError({
                'numero_tarjeta': 'El número de tarjeta es requerido para pagos con tarjeta'
            })
        if 'tarjeta' in self.forma_pago and not self.tipo_tarjeta:
            raise ValidationError({
                'tipo_tarjeta': 'El tipo de tarjeta es requerido para pagos con tarjeta'
            })

    def save(self, *args, **kwargs):
        # Si se proporciona un número de tarjeta completo, guardar solo los últimos 4 dígitos
        self.clean()  # Ejecutar validaciones
        if not self.pk:  # Si es un nuevo pago
            ultimo_pago = Pago.objects.order_by('-id').first()
            numero = (ultimo_pago.id + 1) if ultimo_pago else 1
            self.codigo = f'PAG{numero:06d}'
        if self.numero_tarjeta and len(self.numero_tarjeta) > 4:
            self.numero_tarjeta = self.numero_tarjeta[-4:]
        super().save(*args, **kwargs)
        self.reserva.actualizar_saldos()

    def delete(self, *args, **kwargs):
        reserva = self.reserva
        super().delete(*args, **kwargs)
        reserva.actualizar_saldos()  # Actualizar saldos después de eliminar

    class Meta:
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.codigo} - {self.concepto.nombre} - ${self.monto}"
class VentaPropiedad(models.Model):
    ESTADO_CHOICES = [
        ('disponible', 'Disponible'),
        ('reservado', 'Reservado'),
        ('vendido', 'Vendido'),
    ]

    propiedad = models.OneToOneField(
        Propiedad,
        on_delete=models.CASCADE,
        related_name='info_venta'
    )
    en_venta = models.BooleanField(
        default=False,
        verbose_name="Disponible para venta"
    )
    precio_venta = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Precio de venta"
    )
    precio_autorizacion = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Precio de autorización"
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='disponible',
        verbose_name="Estado de la venta"
    )
    precio_expensas = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Precio de expensas"
    )
    escribania = models.TextField(
        blank=True,
        verbose_name="Información de escribanía"
    )
    observaciones = models.TextField(
        blank=True,
        verbose_name="Observaciones"
    )
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Información de venta - {self.propiedad}"

class AlquilerMeses(models.Model):
    ESTADO_CHOICES = [
        ('disponible', 'Disponible'),
        ('reservado', 'Reservado'),
        ('ocupado', 'Ocupado'),
    ]

    propiedad = models.OneToOneField(
        Propiedad,
        on_delete=models.CASCADE,
        related_name='info_meses'
    )
    disponible = models.BooleanField(
        default=False,
        verbose_name="Disponible para alquiler 24 meses"
    )
    precio_mensual = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Precio mensual"
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='disponible',
        verbose_name="Estado del alquiler"
    )
    fecha_inicio = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de inicio"
    )
    fecha_fin = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de fin"
    )
    precio_expensas = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Precio de expensas"
    )
    observaciones = models.TextField(
        blank=True,
        verbose_name="Observaciones"
    )
    # Fechas opcionales que se establecerán al hacer la reserva
    fecha_inicio = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de inicio"
    )
    fecha_fin = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de fin"
    )
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Alquiler 24 meses - {self.propiedad}"

    class Meta:
        verbose_name = "Alquiler 24 meses"
        verbose_name_plural = "Alquileres 24 meses"