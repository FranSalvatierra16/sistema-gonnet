from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import Q, Max
from django.utils.timezone import now
from django.conf import settings
from django.db.models.signals import post_delete
from django.dispatch import receiver

import datetime
from decimal import Decimal
from .persona import Propietario, Inquilino, Vendedor
from .sucursal import Sucursal
import uuid
import os
from datetime import date, timedelta

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
    ('lote', 'Lote'),
    ('cochera', 'Cochera'),
    ('edificio', 'Edificio'),
    ('inmueble_en_block', 'Inmueble en Block'),
    ('duplex', 'Dúplex'),
    ('emprendimiento', 'Emprendimiento'),
    ('cabaña', 'Cabaña'), 
    ('casaquinta', 'Casa Quinta'),
    ('deposito', 'Depósito'), 
]

ESTADOS_RESERVA_OCUPAN_DISPONIBILIDAD = [
    'confirmada',
    'confirmada_no_pagada',
    'pagada',
]


class HistorialDisponibilidad(models.Model):
    ESTADO_CHOICES = [
        ('libre', 'Libre'),
        ('reservado', 'Reservado'),
        ('alquilado', 'Operación'),
        ('alquiler_sindicato', 'Alquiler sindicato'),
    ]

    propiedad = models.ForeignKey(
        'Propiedad', 
        on_delete=models.CASCADE, 
        related_name='historial_disponibilidad'
    )
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    estado = models.CharField(
        max_length=20, 
        choices=ESTADO_CHOICES, 
        default='libre'
    )
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    reserva = models.ForeignKey(
        'Reserva', 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='historiales_disponibilidad'
    )
    es_principal = models.BooleanField(
        default=False,
        help_text='True si es una disponibilidad creada manualmente, False si es automática (fragmentación)'
    )

    class Meta:
        verbose_name = _("Historial de Disponibilidad")
        verbose_name_plural = _("Historial de Disponibilidades")
        ordering = ['fecha_inicio', 'fecha_fin']  # ✅ ORDENAR POR FECHA CRONOLÓGICA

    def __str__(self):
        return f"{self.propiedad} - {self.estado} - {self.fecha_inicio} al {self.fecha_fin}"

class PropiedadManager(models.Manager):
    """Por defecto excluye propiedades marcadas como eliminadas (soft delete)."""
    def get_queryset(self):
        return super().get_queryset().filter(eliminada=False)


class Propiedad(models.Model):
    DIRECCION_MAX_LENGTH = 255
    UBICACION_MAX_LENGTH = 255
    DEPARTAMENTO_CHOICES = [(chr(i), chr(i)) for i in range(ord('A'), ord('Z')+1)]
    ID_MAX_LENGTH = 255 # Define un tamaño máximo para el campo id
    id = models.CharField(max_length=ID_MAX_LENGTH, primary_key=True, unique=True, null=False, blank=False)
    direccion = models.CharField(max_length=DIRECCION_MAX_LENGTH)
    titulo = models.CharField(
        max_length=255, 
        null=True, 
        blank=True,
        verbose_name="Título descriptivo",
        help_text="Nombre o título para identificar fácilmente la propiedad"
    )
    ubicacion = models.CharField(max_length=UBICACION_MAX_LENGTH)
    descripcion = models.TextField(blank=True)
    anotaciones = models.TextField(
        blank=True, 
        null=True,
        verbose_name="Anotaciones",
        help_text="Notas y observaciones sobre la propiedad"
    )
    tipo_inmueble = models.CharField(max_length=20, choices=TIPOS_INMUEBLES, default='departamento')
    vista = models.CharField(max_length=20, choices=TIPOS_VISTA, default='a_la_calle')
    piso = models.CharField(
        max_length=10,
        blank=True,
        default='',
        verbose_name="Piso",
        help_text="Opcional (ej. lotes o terrenos sin piso). Número o descripción (PB, 1, 15…)",
    )
    departamento = models.CharField(
        max_length=10,
        blank=True,
        default='',
        verbose_name="Departamento",
        help_text="Opcional. Número o letra de departamento si aplica",
    )
    ambientes = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Ambientes",
        help_text="Opcional (ej. lotes sin definición de ambientes)",
    )
    valoracion = models.CharField(max_length=20, choices=TIPOS_VALORACION, default='bueno')
    cuenta_bancaria = models.CharField(max_length=100, blank=True, help_text="Número de cuenta bancaria para depósitos")
    propietario = models.ForeignKey(Propietario, on_delete=models.CASCADE, related_name='propiedades')  
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='propiedades')# Cambiado a obligatorio
    porcentaje_propietario = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=85.00,
        null=True,
        blank=True,
        verbose_name="Porcentaje para Propietario (%)",
        help_text="Porcentaje del monto total que corresponde al propietario (ej: 85% = 85.00). El resto es para la inmobiliaria."
    )
    llave = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Llave",
        help_text="Número de llave o texto (ej. «coordinar» si el depto está ocupado y no hay llave física).",
    )
    numero_por_propietario = models.PositiveIntegerField(null=True, blank=True, verbose_name="Número de propiedad")
    cantidad_personas = models.PositiveIntegerField(null=True, blank=True, verbose_name="Cantidad de personas")
    camas = models.CharField(max_length=255, null=True, blank=True, verbose_name="Camas", help_text="Descripción de las camas (ej: 1 cama matrimonial, 2 camas individuales, etc.)")
    
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
    directv_prepago = models.BooleanField(default=False, verbose_name="DirecTV prepago")
    ventilador = models.BooleanField(default=False, verbose_name="Ventilador")
    aire = models.BooleanField(default=False, verbose_name="Aire acondicionado")
    cable = models.BooleanField(default=False, verbose_name="Cable")
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
    es_propiedad_oficina = models.BooleanField(
        default=False,
        verbose_name='Propiedad oficina',
        help_text='Propiedad de la inmobiliaria. En invierno y 24 meses aplica el % «propiedad oficina» del vendedor.',
    )

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

    class TipoFichaje(models.TextChoices):
        PRIMER = 'primer', 'Primer fichaje'
        SEGUNDO = 'segundo', 'Segundo fichaje'

    tipo_fichaje = models.CharField(
        max_length=10,
        choices=TipoFichaje.choices,
        default=TipoFichaje.PRIMER,
        verbose_name='Tipo de fichaje',
        help_text='Indica si la comisión por fichaje de la operación corresponde al primer o al segundo fichaje (según % del vendedor).',
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

    eliminada = models.BooleanField(
        default=False,
        verbose_name="Eliminada",
        help_text="Si está marcada, la propiedad no se muestra en listados pero se puede recuperar."
    )
    fecha_eliminacion = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de eliminación"
    )

    objects = PropiedadManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = "Propiedad"
        verbose_name_plural = "Propiedades"
        constraints = [
            models.UniqueConstraint(
                fields=["propietario", "numero_por_propietario"],
                name="unique_num_x_prop",
                condition=models.Q(numero_por_propietario__isnull=False)  # Solo aplicar constraint si no es None
            )
        ]

    def __str__(self):
        return f"{self.id} - {self.direccion}"

    def reservas_que_ocupan_disponibilidad(self):
        """Reservas activas que bloquean fechas (excluye alquiler sindicato e eliminadas)."""
        return self.reservas.filter(
            estado__in=ESTADOS_RESERVA_OCUPAN_DISPONIBILIDAD,
            eliminada=False,
            es_alquiler_sindicato=False,
        )

    def esta_disponible_en_fecha(self, fecha_inicio, fecha_fin):
        """Verifica si una propiedad está disponible entre las fechas dadas, reconociendo disponibilidades contiguas."""
        if not fecha_inicio or not fecha_fin:
            return False

        # ✅ MEJORADO: Verificar cobertura completa con disponibilidades contiguas
        # 1️⃣ Buscar TODAS las disponibilidades que se superponen con el período
        disponibilidades_superpuestas = self.disponibilidades.filter(
            fecha_inicio__lt=fecha_fin,   # Empieza antes de que termine la búsqueda
            fecha_fin__gt=fecha_inicio,   # Termina después de que empiece la búsqueda
        ).order_by('fecha_inicio')
        
        # 2️⃣ Verificar si las disponibilidades cubren TODO el rango (permitiendo contiguas)
        periodo_cubierto = False
        if disponibilidades_superpuestas.exists():
            # Verificar si las disponibilidades contiguas cubren todo el rango
            disponibilidades_list = list(disponibilidades_superpuestas)
            
            # Ordenar por fecha de inicio
            disponibilidades_list.sort(key=lambda d: d.fecha_inicio)
            
            # Verificar cobertura continua
            cobertura_inicio = disponibilidades_list[0].fecha_inicio
            cobertura_fin = disponibilidades_list[0].fecha_fin
            
            for i in range(1, len(disponibilidades_list)):
                disp_actual = disponibilidades_list[i]
                # Si la disponibilidad actual empieza el mismo día o antes que termine la anterior
                # (permitiendo fechas contiguas como 07-11 y 11-15)
                if disp_actual.fecha_inicio <= cobertura_fin:
                    # Extender la cobertura
                    cobertura_fin = max(cobertura_fin, disp_actual.fecha_fin)
                else:
                    # Hay un hueco
                    break
            
            # Verificar si la cobertura completa incluye el período buscado
            if cobertura_inicio <= fecha_inicio and cobertura_fin >= fecha_fin:
                periodo_cubierto = True

        # 3️⃣ Verificar si hay reservas que se superpongan (sin alquiler sindicato)
        reservas_superpuestas = self.reservas_que_ocupan_disponibilidad().filter(
            fecha_inicio__lt=fecha_fin,
            fecha_fin__gt=fecha_inicio,
        ).exists()

        # La propiedad está disponible si:
        # 1. El período está cubierto por disponibilidades (contiguas o no)
        # 2. Y no hay reservas que se superpongan
        return periodo_cubierto and not reservas_superpuestas
    
    def obtener_historial_cronologico(self):
        """
        Obtiene el historial de disponibilidad ordenado cronológicamente
        """
        return self.historial_disponibilidad.all().order_by('fecha_inicio', 'fecha_fin')
    
    def reconstruir_historial_si_necesario(self):
        """
        Reconstruye el historial solo si está vacío o incompleto
        """
        # Contar disponibilidades + reservas activas
        total_disponibilidades = self.disponibilidades.count()
        # Excluir reservas eliminadas
        total_reservas = self.reservas.filter(
            estado__in=['confirmada', 'confirmada_no_pagada', 'pagada'],
            eliminada=False
        ).count()
        total_esperado = total_disponibilidades + total_reservas
        
        # Contar entradas de historial actual
        total_historial = self.historial_disponibilidad.count()
        
        # Si no coinciden, reconstruir
        if total_historial != total_esperado:
            # print(f"🔄 Reconstruyendo historial (actual: {total_historial}, esperado: {total_esperado})")
            # Crear una reserva dummy para usar el método de reconstrucción
            # Excluir reservas eliminadas
            reservas_activas = self.reservas.filter(eliminada=False)
            if reservas_activas.exists():
                primera_reserva = reservas_activas.first()
                primera_reserva.reconstruir_historial_cronologico()
            else:
                # Sin reservas: rangos unidos para no duplicar por solapamiento
                HistorialDisponibilidad.objects.filter(propiedad=self).delete()
                disps = list(self.disponibilidades.filter(es_manual=True).order_by('fecha_inicio').values_list('fecha_inicio', 'fecha_fin'))
                rangos = []
                for ini, fin in disps:
                    if rangos and ini <= rangos[-1][1]:
                        rangos[-1] = (rangos[-1][0], max(rangos[-1][1], fin))
                    else:
                        rangos.append((ini, fin))
                for fecha_inicio, fecha_fin in rangos:
                    HistorialDisponibilidad.objects.create(
                        propiedad=self,
                        fecha_inicio=fecha_inicio,
                        fecha_fin=fecha_fin,
                        estado='libre'
                    )

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
        # Detectar si se cambió el propietario
        propietario_cambio = False
        if self.pk and self.propietario:
            try:
                # Obtener la instancia actual de la base de datos
                instancia_anterior = Propiedad.objects.get(pk=self.pk)
                if instancia_anterior.propietario_id != self.propietario_id:
                    propietario_cambio = True
            except Propiedad.DoesNotExist:
                pass  # Es una nueva propiedad
        
        # Si el número no está asignado (None) y hay un propietario, calcúlalo automáticamente
        # O si cambió el propietario y el número actual ya existe para el nuevo propietario
        if self.propietario:
            if self.numero_por_propietario is None:
                # Asignar automáticamente el siguiente número
                recalcular_numero = True
            elif propietario_cambio:
                # Verificar si el número actual ya existe para el nuevo propietario
                existe_numero = Propiedad.objects.filter(
                    propietario=self.propietario,
                    numero_por_propietario=self.numero_por_propietario
                ).exclude(pk=self.pk).exists()
                recalcular_numero = existe_numero
            else:
                recalcular_numero = False
            
            if recalcular_numero:
                with transaction.atomic():
                    # Buscar el último número que no sea None para este propietario
                    ultimo = (
                        Propiedad.objects
                        .filter(propietario=self.propietario, numero_por_propietario__isnull=False)
                        .exclude(pk=self.pk)  # Excluir la propiedad actual si es una actualización
                        .select_for_update()
                        .aggregate(m=Max("numero_por_propietario"))
                    )["m"]
                    
                    if ultimo is None:
                        # Si no hay números asignados, empezar desde 1
                        siguiente_numero = 1
                    else:
                        siguiente_numero = ultimo + 1
                    
                    # Verificar que el número calculado no exista ya (por si hay huecos)
                    while Propiedad.objects.filter(
                        propietario=self.propietario,
                        numero_por_propietario=siguiente_numero
                    ).exclude(pk=self.pk).exists():
                        siguiente_numero += 1
                    
                    self.numero_por_propietario = siguiente_numero

        super().save(*args, **kwargs)
        if self._state.adding:
            self.crear_precios_iniciales()

    @transaction.atomic
    def crear_precios_iniciales(self):
        for tipo_choice in TipoPrecio.choices:
            tipo_key = tipo_choice[0]
            Precio.objects.get_or_create(
                propiedad=self,
                tipo_precio=tipo_key,
                defaults={
                    'precio_total': 0, 
                    'precio_por_dia': 0, 
                    'precio_toma': 0,
                    'precio_dia_toma': 0,
                    'ajuste_porcentaje': 0
                }
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
        # Precio invierno no es obligatorio aunque invierno esté habilitado

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
        related_name='imagenes'  # Cambiado de 'imagenes_propiedad' a 'imagenes'
    )
    imagen = models.ImageField(upload_to='propiedades/')
    orden = models.PositiveIntegerField(default=1)  # Cambiado de IntegerField a PositiveIntegerField
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
    estado = models.CharField(max_length=20, choices=[('en_espera', 'En Espera'), ('confirmada', 'Confirmada'), ('confirmada_no_pagada', 'Confirmada No Pagada'), ('pagada', 'Pagada')], default='en_espera')
    sucursal = models.ForeignKey(
        'Sucursal',  # Asegúrate de que Sucursal esté importado
        on_delete=models.CASCADE,
        related_name='reservas_sucursal',
        null=True  # Permitimos null temporalmente para la migración
    )

    deposito_garantia = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    es_alquiler_sindicato = models.BooleanField(
        default=False,
        verbose_name='Alquiler sindicato',
        help_text='Figura en el historial pero no bloquea la disponibilidad de la propiedad.',
    )
    eliminada = models.BooleanField(default=False)
    fecha_eliminacion = models.DateTimeField(null=True, blank=True)
    usuario_eliminacion = models.ForeignKey('Vendedor', on_delete=models.SET_NULL, null=True, blank=True, related_name='reservas_eliminadas')
    # Campos para tracking de ediciones de fechas
    fecha_inicio_original = models.DateField(null=True, blank=True, verbose_name="Fecha inicio original")
    fecha_fin_original = models.DateField(null=True, blank=True, verbose_name="Fecha fin original")
    fue_editada = models.BooleanField(default=False, verbose_name="Fue editada")
    liq_monto_propietario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Monto propietario (liquidación)',
        help_text='Override manual desde carátula antes de liquidar.',
    )
    liq_monto_inmobiliaria = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Monto inmobiliaria (liquidación)',
        help_text='Override manual desde carátula antes de liquidar.',
    )
    liq_monto_cochera = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Monto cochera (liquidación)',
    )
    liq_monto_fondo = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Fondo mantenimiento (liquidación)',
    )

    def montos_liquidacion_efectivos(self, total, prop, inm):
        """Aplica overrides guardados en carátula sobre montos calculados."""
        coch = Decimal(str(self.liq_monto_cochera or 0))
        fondo = Decimal(str(self.liq_monto_fondo or 0))
        if self.liq_monto_propietario is not None:
            prop = Decimal(str(self.liq_monto_propietario)).quantize(Decimal('0.01'))
        if self.liq_monto_inmobiliaria is not None:
            inm = Decimal(str(self.liq_monto_inmobiliaria)).quantize(Decimal('0.01'))
        return total, prop, inm, coch, fondo

    def save(self, *args, **kwargs):
        # Asegúrate de que la sucursal esté establecida si no está definida
        if not self.sucursal and self.propiedad:
            self.sucursal = self.propiedad.sucursal

        is_new = self._state.adding

        # 🚨 TEMPORALMENTE DESHABILITADO - PERMITIR TODAS LAS RESERVAS
        # Verificar disponibilidad antes de guardar
        if is_new:
            # TEMPORALMENTE: Siempre permitir reservas para no bloquear el sistema
            disponible = True
            
            # TODO: Investigar problema de validación después
            # if not self.propiedad.disponibilidades.exists():
            #     disponible = True
            # else:
            #     disponible = self.propiedad.esta_disponible_en_fecha(self.fecha_inicio, self.fecha_fin)
            #     
            # if not disponible:
            #     raise ValidationError('La propiedad no está disponible para las fechas seleccionadas.')

        super().save(*args, **kwargs)

        if is_new:
            self.cuota_pendiente = self.precio_total
            self.senia = 0
            
            # Actualizar el historial de disponibilidad
            self.actualizar_historial_disponibilidad()

    def actualizar_historial_disponibilidad(self):
        """
        ✅ HISTORIAL COMPLETO: Crea historial fragmentado pero NO modifica disponibilidades
        
        MANTIENE: Las disponibilidades manuales intactas
        CREA: Historial cronológico fragmentado (libre/reservado/operación)
        """
        with transaction.atomic():
            # print(f"📋 ACTUALIZANDO HISTORIAL para reserva {self.fecha_inicio} al {self.fecha_fin}")
            
            # ❌ NO FRAGMENTAR DISPONIBILIDADES - mantienen como están
            # ✅ RECONSTRUIR historial completo cronológicamente con fragmentación visual
            self.reconstruir_historial_cronologico()
            
            # print(f"✅ HISTORIAL FRAGMENTADO ACTUALIZADO (disponibilidades intactas) para reserva {self.id}")
    
    def reconstruir_historial_cronologico(self):
        """
        ✅ Fragmenta las disponibilidades manuales con las reservas.
        Primero une rangos superpuestos de disponibilidades para no crear entradas duplicadas.
        """
        # 1️⃣ LIMPIAR historial existente
        HistorialDisponibilidad.objects.filter(propiedad=self.propiedad).delete()

        # 2️⃣ OBTENER disponibilidades manuales y reservas
        disponibilidades_manuales = self.propiedad.disponibilidades.filter(es_manual=True).order_by('fecha_inicio')
        reservas = self.propiedad.reservas.filter(
            estado__in=ESTADOS_RESERVA_OCUPAN_DISPONIBILIDAD,
            eliminada=False,
            es_alquiler_sindicato=False,
        ).order_by('fecha_inicio')
        reservas_sindicato = self.propiedad.reservas.filter(
            es_alquiler_sindicato=True,
            eliminada=False,
            estado__in=ESTADOS_RESERVA_OCUPAN_DISPONIBILIDAD,
        ).order_by('fecha_inicio')

        # 3️⃣ Unir rangos superpuestos: evita duplicados cuando hay disponibilidades que se solapan
        rangos_union = []
        for disp in disponibilidades_manuales:
            inicio, fin = disp.fecha_inicio, disp.fecha_fin
            if not rangos_union:
                rangos_union.append((inicio, fin))
                continue
            ult_inicio, ult_fin = rangos_union[-1]
            if inicio <= ult_fin:
                rangos_union[-1] = (ult_inicio, max(ult_fin, fin))
            else:
                rangos_union.append((inicio, fin))

        # 4️⃣ Fragmentar cada rango unido (una sola vez por rango de fechas)
        for fecha_inicio, fecha_fin in rangos_union:
            reservas_en_rango = reservas.filter(
                fecha_inicio__lt=fecha_fin,
                fecha_fin__gt=fecha_inicio
            ).order_by('fecha_inicio')

            if not reservas_en_rango.exists():
                HistorialDisponibilidad.objects.create(
                    propiedad=self.propiedad,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    estado='libre',
                    reserva=None
                )
            else:
                self._fragmentar_rango_con_reservas(fecha_inicio, fecha_fin, reservas_en_rango)

        for reserva_sind in reservas_sindicato:
            HistorialDisponibilidad.objects.create(
                propiedad=self.propiedad,
                fecha_inicio=reserva_sind.fecha_inicio,
                fecha_fin=reserva_sind.fecha_fin,
                estado='alquiler_sindicato',
                reserva=reserva_sind,
            )
    
    def _fragmentar_rango_con_reservas(self, fecha_inicio, fecha_fin, reservas_en_rango):
        """Fragmenta un rango (fecha_inicio, fecha_fin) en períodos libres y ocupados por reservas."""
        fecha_actual = fecha_inicio

        for reserva in reservas_en_rango:
            if fecha_actual < reserva.fecha_inicio:
                HistorialDisponibilidad.objects.create(
                    propiedad=self.propiedad,
                    fecha_inicio=fecha_actual,
                    fecha_fin=reserva.fecha_inicio,
                    estado='libre',
                    reserva=None
                )

            inicio_reserva = max(reserva.fecha_inicio, fecha_inicio)
            fin_reserva = min(reserva.fecha_fin, fecha_fin)

            tiene_pagos = (
                reserva.estado == 'pagada' or
                (hasattr(reserva, 'senia') and reserva.senia and reserva.senia > 0) or
                (hasattr(reserva, 'senia_pagada') and reserva.senia_pagada and reserva.senia_pagada > 0) or
                reserva.recibos.exists() or
                reserva.pagos.exists()
            )
            estado = 'alquilado' if tiene_pagos else 'reservado'
            HistorialDisponibilidad.objects.create(
                propiedad=self.propiedad,
                fecha_inicio=inicio_reserva,
                fecha_fin=fin_reserva,
                estado=estado,
                reserva=reserva
            )

            fecha_actual = max(fecha_actual, reserva.fecha_fin)

        if fecha_actual < fecha_fin:
            HistorialDisponibilidad.objects.create(
                propiedad=self.propiedad,
                fecha_inicio=fecha_actual,
                fecha_fin=fecha_fin,
                estado='libre',
                reserva=None
            )

    def _fragmentar_disponibilidad_con_reservas(self, disponibilidad, reservas_en_disponibilidad):
        """Fragmenta una disponibilidad manual en períodos libres y ocupados (usa rango unificado)."""
        self._fragmentar_rango_con_reservas(
            disponibilidad.fecha_inicio,
            disponibilidad.fecha_fin,
            reservas_en_disponibilidad
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
        
        # Reconstruir historial completo para reflejar el cambio de estado
        self.reconstruir_historial_cronologico()
        
    def cancelar_reserva(self):
        """
        Cancela una reserva y restaura las disponibilidades
        """
        from datetime import timedelta
        from django.db.models import Q
        
        with transaction.atomic():
            # print(f"❌ CANCELANDO reserva {self.id}: {self.fecha_inicio} al {self.fecha_fin}")
            
            # 1️⃣ Marcar reserva como cancelada
            self.estado = 'cancelada'
            self.save()

            # Anular comisiones de esta operación (no deben sumar en totales)
            from .comision import ComisionVendedor
            ComisionVendedor.objects.filter(reserva_id=self.pk).update(estado='cancelada')
            
            # 2️⃣ Buscar disponibilidades adyacentes para posible fusión
            disponibilidades_adyacentes = Disponibilidad.objects.filter(
                propiedad=self.propiedad
            ).filter(
                Q(fecha_fin=self.fecha_inicio - timedelta(days=1)) |  # Anterior
                Q(fecha_inicio=self.fecha_fin + timedelta(days=1))    # Posterior
            ).order_by('fecha_inicio')
            
            print(f"🔍 Disponibilidades adyacentes encontradas: {disponibilidades_adyacentes.count()}")
            
            # 3️⃣ Crear nueva disponibilidad para el período cancelado
            nueva_disponibilidad = Disponibilidad.objects.create(
                propiedad=self.propiedad,
                fecha_inicio=self.fecha_inicio,
                fecha_fin=self.fecha_fin
            )
            print(f"➕ Nueva disponibilidad creada: {self.fecha_inicio} al {self.fecha_fin}")
            
            # 4️⃣ Fusionar disponibilidades contiguas
            nueva_disponibilidad.fusionar_disponibilidades_contiguas()
            
            # 5️⃣ Reconstruir historial cronológico
            self.reconstruir_historial_cronologico()
            
            # print(f"✅ Reserva {self.id} cancelada y disponibilidades restauradas")

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
    es_manual = models.BooleanField(
        default=True,
        help_text='True si fue creada manualmente, False si fue generada automáticamente'
    )
    
    # Campos para registrar pagos adelantados (informativo)
    asegurado = models.BooleanField(
        default=False,
        verbose_name='Asegurado',
        help_text='Indica si se realizó un pago adelantado'
    )
    monto_asegurado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Monto Asegurado',
        help_text='Monto del pago adelantado'
    )
    moneda_asegurado = models.CharField(
        max_length=10,
        choices=[
            ('ARS', 'Pesos'),
            ('USD', 'Dólares')
        ],
        null=True,
        blank=True,
        default='ARS',
        verbose_name='Moneda'
    )

    def save(self, *args, **kwargs):
        from datetime import timedelta
        
        if not hasattr(self, 'propiedad') or not self.propiedad:
            raise ValidationError(_('La propiedad es requerida.'))
            
        if self.fecha_inicio and self.fecha_fin and self.fecha_inicio > self.fecha_fin:
            raise ValidationError(_('La fecha de inicio no puede ser posterior a la fecha de fin.'))

        is_new = self._state.adding
        
        # ✅ PERMITIR solapamientos - las disponibilidades se fusionarán automáticamente
        # (El sistema de fragmentación se encarga de manejar los solapamientos)
        
        super().save(*args, **kwargs)
        
        if is_new:
            print(f"➕ Nueva disponibilidad creada: {self.fecha_inicio} al {self.fecha_fin}")
            # El historial se actualizará automáticamente mediante reconstruir_historial_cronologico
            # cuando sea necesario (ej: al crear una reserva)
    
    def fusionar_disponibilidades_contiguas(self):
        """
        Fusiona disponibilidades contiguas o superpuestas de la misma propiedad
        """
        from datetime import timedelta
        
        with transaction.atomic():
            disponibilidades = Disponibilidad.objects.filter(
                propiedad=self.propiedad
            ).order_by('fecha_inicio')
            
            if disponibilidades.count() <= 1:
                return
            
            print(f"🔗 Fusionando disponibilidades contiguas para propiedad {self.propiedad.id}")
            
            disponibilidades_fusionadas = []
            actual = None
            
            for disp in disponibilidades:
                if actual is None:
                    actual = {
                        'fecha_inicio': disp.fecha_inicio,
                        'fecha_fin': disp.fecha_fin,
                        'objetos': [disp]
                    }
                elif disp.fecha_inicio <= actual['fecha_fin'] + timedelta(days=1):
                    # Contigua o superpuesta - fusionar
                    actual['fecha_fin'] = max(actual['fecha_fin'], disp.fecha_fin)
                    actual['objetos'].append(disp)
                else:
                    # Nueva disponibilidad separada
                    disponibilidades_fusionadas.append(actual)
                    actual = {
                        'fecha_inicio': disp.fecha_inicio,
                        'fecha_fin': disp.fecha_fin,
                        'objetos': [disp]
                    }
            
            if actual:
                disponibilidades_fusionadas.append(actual)
            
            # Eliminar disponibilidades originales y crear fusionadas
            for fusion in disponibilidades_fusionadas:
                if len(fusion['objetos']) > 1:
                    print(f"   🔗 Fusionando {len(fusion['objetos'])} disponibilidades en: {fusion['fecha_inicio']} al {fusion['fecha_fin']}")
                    
                    # Eliminar originales
                    for obj in fusion['objetos']:
                        obj.delete()
                    
                    # Crear fusionada
                    Disponibilidad.objects.create(
                        propiedad=self.propiedad,
                        fecha_inicio=fusion['fecha_inicio'],
                        fecha_fin=fusion['fecha_fin']
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
    FINDE_LARGO = 'FINDE_LARGO', _('Finde largo (5 noches)')
    SEMANA_SANTA = 'SEMANA_SANTA', _('Semana Santa (5 noches)')
    CARNAVALES = 'CARNAVALES', _('Carnavales (5 noches)')

    ESTUDIANTE = 'ESTUDIANTE', _('Estudiante')
    

class Precio(models.Model):
    propiedad = models.ForeignKey(Propiedad, on_delete=models.CASCADE, related_name='precios')
    tipo_precio = models.CharField(max_length=20, choices=TipoPrecio.choices)
    
    # Precios por día

    precio_toma = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        blank=True, 
        null=True,
        verbose_name="Precio Toma"
    )
    
    # Precios por toma
    precio_dia_toma = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        blank=True, 
        null=True,
        verbose_name="Precio dia: Toma"
    )
    precio_por_dia = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        blank=True, 
        null=True,
        verbose_name="Precio por día"
    )
    
    # Precios por propietario
  
    # Precio total (calculado)
    precio_total = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        blank=True, 
        null=True,
        verbose_name="Precio total"
    )
    
    ajuste_porcentaje = models.DecimalField(
        max_digits=7,
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
            elif self.tipo_precio == 'FINDE_LARGO' or self.tipo_precio == 'SEMANA_SANTA' or self.tipo_precio == 'CARNAVALES':
                base_price = self.precio_por_dia * 5
            elif self.tipo_precio == 'TEMPORADA_BAJA':
                base_price = self.precio_por_dia * 15
            else:
                base_price = self.precio_por_dia * dias

        # Aplicar ajuste porcentual si se ha establecido
        if self.ajuste_porcentaje != 0:
            base_price *= (1 - self.ajuste_porcentaje / 100)

        return round(base_price, 2)

    def save(self, *args, **kwargs):
        # ✅ LÓGICA MEJORADA: Respetar precio_total manual del usuario
        from decimal import Decimal
        
        update_fields = kwargs.get('update_fields', [])
        skip_calculation = kwargs.get('skip_price_calculation', False)
        
        # Si el usuario está editando y no es una creación nueva
        is_updating = self.pk is not None
        
        # Calcular precio automático (para comparar)
        precio_automatico = None
        if self.precio_por_dia is not None and not skip_calculation:
            # Calcular el precio total basado en el tipo de precio
            if 'QUINCENA' in self.tipo_precio or self.tipo_precio == 'VACACIONES_INVIERNO':
                if 'ENERO' in self.tipo_precio or 'MARZO' in self.tipo_precio or 'DICIEMBRE' in self.tipo_precio:
                    base_price = self.precio_por_dia * 16
                else:
                    base_price = self.precio_por_dia * 15
            elif self.tipo_precio == 'FINDE_LARGO' or self.tipo_precio == 'SEMANA_SANTA' or self.tipo_precio == 'CARNAVALES':
                base_price = self.precio_por_dia * 5
            elif self.tipo_precio == 'TEMPORADA_BAJA':
                base_price = self.precio_por_dia * 15
            else:
                base_price = self.precio_por_dia

            # Aplicar ajuste porcentual si se ha establecido
            if base_price is not None and self.ajuste_porcentaje != 0:
                base_price *= (1 - self.ajuste_porcentaje / 100)
            
            precio_automatico = round(base_price, 2) if base_price is not None else None
        
        # Convertir a Decimal para comparación precisa
        precio_total_actual = Decimal(str(self.precio_total)) if self.precio_total else Decimal('0')
        precio_auto_decimal = Decimal(str(precio_automatico)) if precio_automatico is not None else None
        
        # print(f"🔍 DECISIÓN en save() - tipo_precio: {self.tipo_precio}")
        # print(f"   - is_updating: {is_updating}")
        # print(f"   - precio_total recibido: {precio_total_actual}")
        # print(f"   - precio_automatico calculado: {precio_auto_decimal}")
        # print(f"   - precio_por_dia: {self.precio_por_dia}")
        # print(f"   - update_fields: {update_fields}")
        
        # ✅ DECISIÓN: ¿Usar precio automático o manual?
        # Si precio_total es diferente del automático → ES MANUAL → RESPETAR
        if precio_auto_decimal is not None:
            # Permitir una pequeña diferencia de redondeo (0.01)
            diferencia = abs(precio_total_actual - precio_auto_decimal)
            
            if diferencia > Decimal('0.01'):
                # Es un valor MANUAL, respetar el del usuario
                #                 # print(f"🖊️  ✅ PRECIO MANUAL detectado: {precio_total_actual} (auto sería {precio_auto_decimal})")
                # print(f"   → Respetando valor manual del usuario")
                # NO modificar precio_total, ya tiene el valor correcto
                pass
            elif precio_total_actual == Decimal('0') and not is_updating:
                # Es una creación nueva y está vacío, usar el automático
                self.precio_total = precio_automatico
                # print(f"🔢 PRECIO AUTOMÁTICO aplicado: {precio_automatico} (creación nueva)")
            else:
                # Es igual o muy cercano al automático, está bien como está
                # print(f"⚖️  Precio igual al automático: {precio_total_actual}")
                pass
        elif not is_updating:
            # Es una creación nueva sin precio_por_dia, dejar en 0
            # print(f"⚠️  Creación nueva sin precio_por_dia")
            pass

        # Remover el parámetro personalizado antes de llamar al save padre
        kwargs.pop('skip_price_calculation', None)
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
        ('tarjeta', 'Tarjeta'),
        ('cheque', 'Cheque'),
        ('qr', 'QR'),
    ]

    reserva = models.ForeignKey('Reserva', on_delete=models.CASCADE, related_name='pagos')
    codigo = models.CharField(max_length=10, unique=True, editable=False)
    fecha = models.DateField(auto_now_add=True)
    forma_pago = models.CharField(max_length=20, choices=FORMA_PAGO_CHOICES)
    concepto = models.ForeignKey('ConceptoPago', on_delete=models.PROTECT)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Campo para tipo de tarjeta
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
    
    # Campo para destino de transferencia
    destino_deposito = models.CharField(
        max_length=10,
        choices=[
            ('galicia', 'Galicia'),
            ('mp', 'Mercado Pago')
        ],
        null=True,
        blank=True,
        verbose_name="Destino de la Transferencia"
    )

    def clean(self):
        super().clean()
        if not self.pk:  # Solo validar al crear un nuevo pago
            # Verificar que el monto no supere la cuota pendiente
            if self.monto > self.reserva.cuota_pendiente:
                raise ValidationError({
                    'monto': f'El monto del pago (${self.monto}) no puede superar el saldo pendiente (${self.reserva.cuota_pendiente})'
                })
        if self.forma_pago == 'tarjeta' and not self.tipo_tarjeta:
            raise ValidationError({
                'tipo_tarjeta': 'El tipo de tarjeta es requerido para pagos con tarjeta'
            })
        if self.forma_pago in ['transferencia', 'qr'] and not self.destino_deposito:
            raise ValidationError({
                'destino_deposito': 'El destino de la transferencia es requerido para pagos por transferencia o QR'
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
    metros_cuadrados = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Metros cuadrados"
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


class AlquilerInvierno(models.Model):
    ESTADO_CHOICES = [
        ('disponible', 'Disponible'),
        ('reservado', 'Reservado'),
        ('ocupado', 'Ocupado'),
    ]

    propiedad = models.OneToOneField(
        Propiedad,
        on_delete=models.CASCADE,
        related_name='info_invierno'
    )
    disponible = models.BooleanField(
        default=False,
        verbose_name="Disponible para alquiler invierno"
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
    precio_autorizacion = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Precio de autorización"
    )
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Alquiler Invierno - {self.propiedad}"

    class Meta:
        verbose_name = "Alquiler Invierno"
        verbose_name_plural = "Alquileres Invierno"


def _contrato_alquiler_es_invierno(contrato):
    if contrato is None:
        return False
    if hasattr(contrato, 'es_contrato_invierno') and contrato.es_contrato_invierno():
        return True
    return int(getattr(contrato, 'duracion_meses', 0) or 0) == 9


def _contrato_alquiler_es_largo_plazo(contrato):
    if contrato is None:
        return False
    if _contrato_alquiler_es_invierno(contrato):
        return False
    return int(getattr(contrato, 'duracion_meses', 0) or 0) >= 9


def invierno_bloquea_alquiler_largo(propiedad):
    """True si la ficha invierno o un contrato invierno vigente impide ofrecer 24 meses."""
    try:
        info = propiedad.info_invierno
    except AlquilerInvierno.DoesNotExist:
        info = None
    if info and info.disponible and info.estado in ('reservado', 'ocupado'):
        return True
    from inmobiliaria.models.contrato import ContratoAlquiler

    for contrato in ContratoAlquiler.objects.filter(
        propiedad=propiedad,
        estado__in=('reservado', 'activo'),
    ):
        if _contrato_alquiler_es_invierno(contrato):
            return True
    return False


def largo_plazo_bloquea_invierno(propiedad):
    """True si hay contrato largo vigente o ficha 24 meses reservada/ocupada."""
    try:
        info = propiedad.info_meses
    except AlquilerMeses.DoesNotExist:
        info = None
    if info and info.disponible and info.estado in ('reservado', 'ocupado'):
        return True
    from inmobiliaria.models.contrato import ContratoAlquiler

    for contrato in ContratoAlquiler.objects.filter(
        propiedad=propiedad,
        estado__in=('reservado', 'activo'),
    ):
        if _contrato_alquiler_es_largo_plazo(contrato):
            return True
    return False


def desactivar_24_meses_si_invierno_ocupado(propiedad):
    """Desactiva la modalidad 24 meses mientras invierno esté reservado u ocupado."""
    if not invierno_bloquea_alquiler_largo(propiedad):
        return False
    try:
        info_meses = propiedad.info_meses
    except AlquilerMeses.DoesNotExist:
        return False
    if not info_meses.disponible:
        return False
    info_meses.disponible = False
    info_meses.save(update_fields=['disponible'])
    return True


def desactivar_invierno_si_largo_plazo_ocupado(propiedad):
    """Desactiva invierno mientras haya contrato/reserva de alquiler largo."""
    if not largo_plazo_bloquea_invierno(propiedad):
        return False
    try:
        info_inv = propiedad.info_invierno
    except AlquilerInvierno.DoesNotExist:
        return False
    if not info_inv.disponible:
        return False
    info_inv.disponible = False
    info_inv.save(update_fields=['disponible'])
    return True


def reactivar_24_meses_si_invierno_libre(propiedad):
    """Vuelve a habilitar 24 meses cuando invierno quedó libre y no hay contrato largo."""
    if invierno_bloquea_alquiler_largo(propiedad) or largo_plazo_bloquea_invierno(propiedad):
        return False
    try:
        info_meses = propiedad.info_meses
    except AlquilerMeses.DoesNotExist:
        return False
    if info_meses.disponible:
        return False
    update_fields = ['disponible']
    info_meses.disponible = True
    if info_meses.estado not in ('reservado', 'ocupado'):
        info_meses.estado = 'disponible'
        update_fields.append('estado')
    info_meses.save(update_fields=update_fields)
    return True


def reactivar_invierno_si_largo_plazo_libre(propiedad):
    if largo_plazo_bloquea_invierno(propiedad) or invierno_bloquea_alquiler_largo(propiedad):
        return False
    try:
        info_inv = propiedad.info_invierno
    except AlquilerInvierno.DoesNotExist:
        return False
    if info_inv.disponible:
        return False
    update_fields = ['disponible']
    info_inv.disponible = True
    if info_inv.estado not in ('reservado', 'ocupado'):
        info_inv.estado = 'disponible'
        update_fields.append('estado')
    info_inv.save(update_fields=update_fields)
    return True


def sincronizar_exclusion_invierno_24_meses(propiedad):
    """Mantiene excluyentes invierno y 24 meses según fichas y contratos vigentes."""
    desactivar_24_meses_si_invierno_ocupado(propiedad)
    desactivar_invierno_si_largo_plazo_ocupado(propiedad)


@receiver(post_delete, sender=Propiedad)
def reordenar_numeros_por_propietario(sender, instance, **kwargs):
    propiedades = Propiedad.objects.filter(propietario=instance.propietario).order_by('numero_por_propietario')
    for idx, propiedad in enumerate(propiedades, start=1):
        if propiedad.numero_por_propietario != idx:
            propiedad.numero_por_propietario = idx
            propiedad.save(update_fields=['numero_por_propietario'])