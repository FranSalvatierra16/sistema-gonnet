from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from decimal import Decimal
from datetime import datetime
from django.forms import inlineformset_factory
from django.template.loader import render_to_string
from django.contrib.auth import authenticate
from xhtml2pdf import pisa
from io import BytesIO
from .models import (
    Vendedor, Inquilino, Propietario, Propiedad, Reserva, 
    Disponibilidad, ImagenPropiedad, Precio, TipoPrecio, 
    Pago, ConceptoPago, HistorialDisponibilidad, VentaPropiedad, 
    AlquilerMeses, Caja, MovimientoCaja, Cuenta, Concepto, Sucursal,
    TipoMovimientoCajaEnum, ContratoAlquiler, CuotaMensual
)
from .forms import  VendedorUserCreationForm, VendedorChangeForm, InquilinoForm, PropietarioForm, PropiedadForm, ReservaForm,BuscarPropiedadesForm, DisponibilidadForm,PrecioForm, PrecioFormSet, PropietarioBuscarForm, InquilinoBuscarForm, SucursalForm, LoginForm, PropiedadSearchForm, VentaPropiedadForm, MovimientoCajaForm
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm, SetPasswordForm
from django.contrib.auth import login
from datetime import datetime, date, timedelta
from django.db.models import Q, Prefetch, Case, When, IntegerField, Sum, Max, F, Count
from django.core.exceptions import ValidationError
from django.forms import modelformset_factory
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from dateutil.parser import parse
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from django.views.decorators.http import require_POST, require_http_methods
import json
from django.db import models
from django.conf import settings
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import os
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth import get_user_model
from django.contrib.auth import update_session_auth_hash
from .utils import numero_a_palabras

import logging
logger = logging.getLogger(__name__)

import traceback  # Agregada esta importación
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from django import forms

# Formulario para recuperación de contraseña
class EmailForm(forms.Form):
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'ejemplo@correo.com',
            'autocomplete': 'email'
        })
    )

# index view
def index(request):
    if request.user.is_authenticated:
        return redirect('inmobiliaria:dashboard')
    else:
        return redirect('inmobiliaria:index')

# Vendedor views
@login_required
def dashboard(request):
    vendedor = None
    nivel = 0
    if request.user.is_authenticated and hasattr(request.user, 'vendedor'):
        vendedor = request.user.vendedor
        nivel = vendedor.nivel

    context = {
        'nivel_usuario': nivel,
        'vendedor': vendedor,
    }
    return render(request, 'inmobiliaria/dashboard.html', context)
@login_required
def vendedores(request):
    vendedores = Vendedor.objects.filter(sucursal=request.user.sucursal)
    return render(request, 'inmobiliaria/vendedores/lista.html', {'vendedores': vendedores})

@login_required
def vendedor_detalle(request, vendedor_id):
    vendedor = get_object_or_404(Vendedor, pk=vendedor_id)
    return render(request, 'inmobiliaria/vendedores/detalle.html', {'vendedor': vendedor})
@login_required
def vendedor_nuevo(request):
    if request.method == "POST":
        form = VendedorUserCreationForm(request.POST)
        if form.is_valid():
            vendedor = form.save()
            messages.success(request, 'Vendedor creado exitosamente.')
            return redirect('inmobiliaria:vendedor_detalle', vendedor_id=vendedor.id)
    else:
        form = VendedorUserCreationForm()
    return render(request, 'inmobiliaria/vendedores/formulario.html', {'form': form})

@login_required
def vendedor_editar(request, vendedor_id):
    vendedor = get_object_or_404(Vendedor, pk=vendedor_id)
    if request.method == "POST":
        form = VendedorChangeForm(request.POST, instance=vendedor)
        if form.is_valid():
            vendedor = form.save()
            messages.success(request, 'Vendedor actualizado exitosamente.')
            return redirect('inmobiliaria:vendedor_detalle', vendedor_id=vendedor.id)
    else:
        form = VendedorChangeForm(instance=vendedor)
    return render(request, 'inmobiliaria/vendedores/formulario.html', {'form': form, 'vendedor': vendedor})
@login_required
def vendedor_eliminar(request, vendedor_id):
    vendedor = get_object_or_404(Vendedor, pk=vendedor_id)
    if request.method == "POST":
        vendedor.delete()
        messages.success(request, 'Vendedor eliminado exitosamente.')
        return redirect('inmobiliaria:vendedores')
    return render(request, 'inmobiliaria/vendedores/confirmar_eliminar.html', {'vendedor': vendedor})

# Inquilino views
@login_required
def inquilinos(request):
    form = InquilinoBuscarForm(request.GET or None)
    inquilinos = Inquilino.objects.filter(sucursal=request.user.sucursal)
    

    if form.is_valid():
        termino = form.cleaned_data.get('termino')
        
        if termino:
            palabras = termino.split()
            query = Q()
            for palabra in palabras:
                query |= Q(nombre__icontains=palabra) | Q(apellido__icontains=palabra)
            query |= Q(dni__icontains=termino)
            inquilinos = inquilinos.filter(query)

    # Detectar si la solicitud es AJAX
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        inquilinos_data = [{
            'id': i.id,
            'dni': i.dni,
            'nombre': i.nombre,
            'apellido': i.apellido,
            'email': i.email
        } for i in inquilinos]
        return JsonResponse({'inquilinos': inquilinos_data})

    # Retornar la plantilla completa si no es AJAX
    return render(request, 'inmobiliaria/inquilinos/lista.html', {
        'form': form,
        'inquilinos': inquilinos
    })

@login_required
def inquilino_detalle(request, inquilino_id):
    inquilino = get_object_or_404(Inquilino, pk=inquilino_id)
    return render(request, 'inmobiliaria/inquilinos/detalle.html', {'inquilino': inquilino})

@login_required
def inquilino_nuevo(request):
    if request.method == "POST":
        form = InquilinoForm(request.POST, user=request.user)
        if form.is_valid():
            inquilino = form.save()
            messages.success(request, 'Inquilino creado exitosamente.')
            return redirect('inmobiliaria:inquilinos')
    else:
        form = InquilinoForm(user=request.user)
    return render(request, 'inmobiliaria/inquilinos/formulario.html', {'form': form})

@login_required
def inquilino_editar(request, inquilino_id):
    inquilino = get_object_or_404(Inquilino, pk=inquilino_id)
    if request.method == "POST":
        form = InquilinoForm(request.POST, instance=inquilino)
        if form.is_valid():
            inquilino = form.save()
            messages.success(request, 'Inquilino actualizado exitosamente.')
            return redirect('inmobiliaria:inquilino_detalle', inquilino_id=inquilino.id)
    else:
        form = InquilinoForm(instance=inquilino)
    return render(request, 'inmobiliaria/inquilinos/formulario.html', {'form': form, 'inquilino': inquilino})

@login_required
def inquilino_eliminar(request, inquilino_id):
    inquilino = get_object_or_404(Inquilino, pk=inquilino_id)
    if request.method == "POST":
        inquilino.delete()
        messages.success(request, 'Inquilino eliminado exitosamente.')
        return redirect('inmobiliaria:inquilinos')
    return render(request, 'inmobiliaria/inquilinos/confirmar_eliminar.html', {'inquilino': inquilino})

# Propietario views
@login_required
def propietarios(request):
    form = PropietarioBuscarForm(request.GET or None)
    
    # Determinar qué propietarios mostrar según el nivel del usuario
    if request.user.is_superuser or request.user.nivel == 4:
        propietarios = Propietario.objects.filter(sucursal=request.user.sucursal)
    else:
        # Filtrar por la sucursal del vendedor logueado
        propietarios = Propietario.objects.filter(sucursal=request.user.sucursal)

    if form.is_valid():
        termino = form.cleaned_data.get('termino')
        
        if termino:
            palabras = termino.split()
            query = Q()
            for palabra in palabras:
                query |= Q(nombre__icontains=palabra) | Q(apellido__icontains=palabra)
            query |= Q(dni__icontains=termino)
            propietarios = propietarios.filter(query)

    # Detectar si la solicitud es AJAX
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        propietarios_data = [{
            'id': p.id,
            'nombre': p.nombre,
            'apellido': p.apellido,
            'dni': p.dni,
            'cuenta_bancaria': p.cuenta_bancaria if hasattr(p, 'cuenta_bancaria') else '',
            'sucursal': p.sucursal.nombre  # Agregar el nombre de la sucursal si lo necesitas en la respuesta
        } for p in propietarios]
        return JsonResponse({'propietarios': propietarios_data})

    # Retornar la plantilla completa si no es AJAX
    context = {
        'form': form,
        'propietarios': propietarios,
        'sucursal_actual': request.user.sucursal.nombre if not request.user.is_superuser else 'Todas las sucursales'
    }
    
    return render(request, 'inmobiliaria/propietarios/lista.html', context)

@login_required
def propietario_detalle(request, propietario_id):
    propietario = get_object_or_404(Propietario, pk=propietario_id)
    return render(request, 'inmobiliaria/propietarios/detalle.html', {'propietario': propietario})

@login_required
def propietario_nuevo(request):
    if request.method == "POST":
        form = PropietarioForm(request.POST, user=request.user)
        if form.is_valid():
            propietario = form.save()
            messages.success(request, 'Propietario creado exitosamente.')
            return redirect('inmobiliaria:propietario_detalle', propietario_id=propietario.id)
    else:
        form = PropietarioForm(user=request.user)
    return render(request, 'inmobiliaria/propietarios/formulario.html', {'form': form})

@login_required
def propietario_editar(request, propietario_id):
    propietario = get_object_or_404(Propietario, pk=propietario_id)
    if request.method == "POST":
        form = PropietarioForm(request.POST, instance=propietario)
        if form.is_valid():
            propietario = form.save()
            messages.success(request, 'Propietario actualizado exitosamente.')
            return redirect('inmobiliaria:propietario_detalle', propietario_id=propietario.id)
    else:
        form = PropietarioForm(instance=propietario)
    return render(request, 'inmobiliaria/propietarios/formulario.html', {'form': form, 'propietario': propietario})

@login_required
def propietario_eliminar(request, propietario_id):
    propietario = get_object_or_404(Propietario, pk=propietario_id)
    if request.method == "POST":
        propietario.delete()
        messages.success(request, 'Propietario eliminado exitosamente.')
        return redirect('inmobiliaria:propietarios')
    return render(request, 'inmobiliaria/propietarios/confirmar_eliminar.html', {'propietario': propietario})
@login_required
def propiedades(request):
    form = PropiedadSearchForm(request.GET or None)
    # Obtener propiedades de la sucursal
    propiedades = Propiedad.objects.filter(sucursal=request.user.sucursal)

    if form.is_valid():
        query = form.cleaned_data.get('query')
        if query:
            propiedades = propiedades.filter(
                Q(direccion__icontains=query) |
                Q(id__icontains=query) |
                Q(propietario__nombre__icontains=query) |
                Q(propietario__apellido__icontains=query) |
                Q(fichado_por__nombre__icontains=query) |
                Q(fichado_por__apellido__icontains=query) |
                Q(fichado_por__username__icontains=query)
            )

    # Ordenar numéricamente por ID en Python
    propiedades_list = list(propiedades)
    propiedades_list.sort(key=lambda p: int(p.id) if p.id.isdigit() else float('inf'))

    return render(request, 'inmobiliaria/propiedades/lista.html', {
        'form': form,
        'propiedades': propiedades_list
    })

@login_required
def propiedad_detalle(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, pk=propiedad_id)
    # ✅ FILTRAR SOLO DISPONIBILIDADES MANUALES (no automáticas)
    disponibilidades = propiedad.disponibilidades.filter(es_manual=True)
    
    # Obtener el historial de disponibilidad
    historiales = HistorialDisponibilidad.objects.filter(
        propiedad=propiedad
    ).order_by('-fecha_actualizacion')
    
    # Obtener imágenes usando el related_name correcto
    imagenes = propiedad.imagenes.all()
    print("Propiedad ID:", propiedad_id)
    print("Número de imágenes encontradas:", imagenes.count())
    for imagen in imagenes:
        print("URL de imagen:", imagen.imagen.url if imagen.imagen else "No hay URL")

    # Definir el orden personalizado para los tipos de precio
    orden_tipo_precio = Case(
        When(tipo_precio=TipoPrecio.QUINCENA_1_DICIEMBRE, then=0),
        When(tipo_precio=TipoPrecio.QUINCENA_2_DICIEMBRE, then=1),
        When(tipo_precio=TipoPrecio.QUINCENA_1_ENERO, then=2),
        When(tipo_precio=TipoPrecio.QUINCENA_2_ENERO, then=3),
        When(tipo_precio=TipoPrecio.QUINCENA_1_FEBRERO, then=4),
        When(tipo_precio=TipoPrecio.QUINCENA_2_FEBRERO, then=5),
        When(tipo_precio=TipoPrecio.QUINCENA_1_MARZO, then=6),
        When(tipo_precio=TipoPrecio.QUINCENA_2_MARZO, then=7),
        When(tipo_precio=TipoPrecio.TEMPORADA_BAJA, then=8),
        When(tipo_precio=TipoPrecio.FINDE_LARGO, then=9),
        When(tipo_precio=TipoPrecio.VACACIONES_INVIERNO, then=10),
        output_field=IntegerField(),
    )

    # Obtener los precios ordenados
    precios = propiedad.precios.annotate(
        orden_tipo_precio=orden_tipo_precio
    ).order_by('orden_tipo_precio')

    # Debug de imágenes
    try:
        print("Imágenes de la propiedad:", [imagen.imagen.url for imagen in imagenes])
    except Exception as e:
        print("Error al acceder a las imágenes:", str(e))

    # ✅ Obtener información de venta si existe
    try:
        info_venta = propiedad.info_venta
    except VentaPropiedad.DoesNotExist:
        info_venta = None
    except Exception as e:
        info_venta = None

    # ✅ Obtener información de 24 meses si existe  
    try:
        info_meses = propiedad.info_meses
    except:
        info_meses = None

    context = {
        'propiedad': propiedad,
        'disponibilidades': disponibilidades,
        'precios': precios,
        'imagenes': imagenes,
        'historiales': historiales,  # Agregamos el historial al contexto
        'active_tab': request.GET.get('tab', 'alquiler'),  # default a 'alquiler'
        'info_venta': info_venta,  # ✅ Agregamos info_venta al contexto
        'info_meses': info_meses,  # ✅ Agregamos info_meses al contexto
    }
    
    return render(request, 'inmobiliaria/propiedades/detalle.html', context)

@login_required
def propiedad_nuevo(request):
    if request.method == 'POST':
        form = PropiedadForm(request.POST, request.FILES, user=request.user)
        propietario_form = PropietarioForm(user=request.user)
        if form.is_valid():
            propiedad = form.save()
            # Las imágenes ya se procesan en el método save() del formulario
            # No las proceses aquí para evitar duplicación
            messages.success(request, 'Propiedad creada exitosamente.')
            return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad.id)
    else:
        form = PropiedadForm(user=request.user)
        propietario_form = PropietarioForm(user=request.user)
    
    return render(request, 'inmobiliaria/propiedades/formulario.html', {
        'form': form,
        'propietario_form': propietario_form,
        'titulo': 'Nueva Propiedad',
        'imagenes': []  # Para el template
    })

@login_required
def propiedad_editar(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    imagenes = ImagenPropiedad.objects.filter(propiedad=propiedad).order_by('orden')
    
    if request.method == 'POST':
        form = PropiedadForm(request.POST, request.FILES, instance=propiedad, user=request.user)
        propietario_form = PropietarioForm(user=request.user)
        if form.is_valid():
            propiedad = form.save()  # El formulario se encarga de procesar las imágenes
            messages.success(request, 'Propiedad actualizada exitosamente.')
            return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad.id)
    else:
        form = PropiedadForm(instance=propiedad, user=request.user)
        propietario_form = PropietarioForm(user=request.user)
    
    return render(request, 'inmobiliaria/propiedades/formulario.html', {
        'form': form,
        'propietario_form': propietario_form,
        'propiedad': propiedad,
        'imagenes': imagenes,
        'titulo': 'Editar Propiedad'
    })

@login_required
def propiedad_eliminar(request, propiedad_id):
    try:
        propiedad = get_object_or_404(Propiedad, pk=propiedad_id)
        
        # Primero eliminar todas las imágenes asociadas
        imagenes = ImagenPropiedad.objects.filter(propiedad=propiedad)
        for imagen in imagenes:
            try:
                # Eliminar el archivo físico
                if imagen.imagen:
                    imagen.imagen.delete(save=False)
            except Exception as e:
                logger.error(f"Error al eliminar archivo de imagen {imagen.id}: {str(e)}")
            
        # Luego eliminar la propiedad
        nombre_propiedad = str(propiedad)
        propiedad.delete()
        
        messages.success(request, f'La propiedad "{nombre_propiedad}" ha sido eliminada exitosamente.')
        return redirect('inmobiliaria:propiedades')
        
    except Propiedad.DoesNotExist:
        messages.error(request, 'La propiedad no existe o ya fue eliminada.')
        return redirect('inmobiliaria:propiedades')
    except Exception as e:
        logger.error(f"Error al eliminar propiedad {propiedad_id}: {str(e)}")
        messages.error(request, f'Error al eliminar la propiedad: {str(e)}')
        return redirect('inmobiliaria:propiedades')
    
def register(request):
    if request.method == 'POST':
        form = VendedorUserCreationForm(request.POST)
        print("\n=== DATOS DEL FORMULARIO RECIBIDOS ===")
        print(f"Datos POST: {request.POST}")
        
        if form.is_valid():
            print("\n=== DATOS VALIDADOS ===")
            print(f"Username: {form.cleaned_data.get('username')}")
            print(f"DNI: {form.cleaned_data.get('dni')}")
            print(f"Nombre: {form.cleaned_data.get('nombre')}")
            print(f"Apellido: {form.cleaned_data.get('apellido')}")
            print(f"Email: {form.cleaned_data.get('email')}")
            print(f"Comisión: {form.cleaned_data.get('comision')}")
            print(f"Fecha Nacimiento: {form.cleaned_data.get('fecha_nacimiento')}")
            print(f"Nivel: {form.cleaned_data.get('nivel')}")
            print(f"Sucursal: {form.cleaned_data.get('sucursal')}")
            print(f"Password1 presente: {'password1' in form.cleaned_data}")
            print(f"Password2 presente: {'password2' in form.cleaned_data}")
            print(f"Passwords coinciden: {form.cleaned_data.get('password1') == form.cleaned_data.get('password2')}")
            
            vendedor = form.save()
            
            # Verificar que la contraseña se guardó correctamente
            print("\n=== VENDEDOR CREADO ===")
            print(f"ID: {vendedor.id}")
            print(f"Username: {vendedor.username}")
            print(f"Nombre completo: {vendedor.nombre} {vendedor.apellido}")
            print(f"Es activo: {vendedor.is_active}")
            print(f"Es staff: {vendedor.is_staff}")
            print(f"Es superusuario: {vendedor.is_superuser}")
            print(f"Sucursal asignada: {vendedor.sucursal}")
            print(f"Contraseña hasheada guardada: {bool(vendedor.password)}")
            print(f"Longitud del hash de la contraseña: {len(vendedor.password)}")
            
            # Verificar que podemos autenticar con la contraseña
            from django.contrib.auth import authenticate
            test_auth = authenticate(username=vendedor.username, 
                                  password=form.cleaned_data.get('password1'))
            print(f"Prueba de autenticación exitosa: {test_auth is not None}")
            
            messages.success(request, 'Registro exitoso. Ahora puedes iniciar sesión.')
            return redirect('inmobiliaria:login')
        else:
            print("\n=== ERRORES EN EL FORMULARIO ===")
            print(f"Errores: {form.errors}")
            if 'password1' in form.errors:
                print(f"Errores de password1: {form.errors['password1']}")
            if 'password2' in form.errors:
                print(f"Errores de password2: {form.errors['password2']}")
    else:
        form = VendedorUserCreationForm()
        print("\n=== NUEVO FORMULARIO CREADO ===")
        print("Método GET - Mostrando formulario vacío")
    
    return render(request, 'inmobiliaria/autenticacion/register.html', {'form': form})

@login_required
def crear_propietario_ajax(request):
    if request.method == "POST":
        form = PropietarioForm(request.POST, user=request.user)
        if form.is_valid():
            propietario = form.save()
           
            messages.success(request, 'Propietario creado exitosamente.')

            return JsonResponse({
                'success': True,
                'propietario_id': propietario.id,
                'propietario_nombre': f"{propietario.nombre} {propietario.apellido}"
            })
        else:
            # Asegurarse de que los errores se envíen de manera adecuada al frontend
            errors = {}
            for field, error_list in form.errors.items():
                errors[field] = error_list

            return JsonResponse({'success': False, 'errors': errors})


@receiver(user_logged_in)
def user_logged_in_handler(sender, request, user, **kwargs):
    if hasattr(user, 'vendedor'):
        request.session['nivel_usuario'] = user.vendedor.nivel
    else:
        request.session['nivel_usuario'] = 0  # Default level if not a vendedor

def ver_disponibilidad(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    
    # Obtener todas las reservas de la propiedad
    reservas = propiedad.reservas.all()
    
    # Obtener todas las disponibilidades de la propiedad
    disponibilidades = Disponibilidad.objects.filter(propiedad=propiedad)

    context = {
        'propiedad': propiedad,
        'reservas': reservas,
        'disponibilidades': disponibilidades,
    }

    return render(request, 'inmobiliaria/ver_disponibilidad.html', context)
@login_required                                                                 
def reservas(request):
    # ✅ Ordenar por ID descendente como en operaciones
    reservas = Reserva.objects.filter(sucursal=request.user.sucursal).order_by('-id')
    
    # ✅ Filtro de búsqueda por ID (opcional)
    search_id = request.GET.get('search_id', '').strip()
    if search_id:
        reservas = reservas.filter(id__icontains=search_id)
    
    return render(request, 'inmobiliaria/reserva/lista.html', {
        'reservas': reservas,
        'search_id': search_id
    })
def operaciones(request):
    # Obtener solo reservas pagadas (completas o con saldo pendiente) ordenadas por fecha más reciente
    reservas = Reserva.objects.filter(
        sucursal=request.user.sucursal,
        estado__in=['pagada', 'confirmada_no_pagada']
    ).prefetch_related('pagos').order_by('-id')
    
    # ✅ Filtro de búsqueda por ID
    search_id = request.GET.get('search_id', '').strip()
    if search_id:
        reservas = reservas.filter(id__icontains=search_id)
    
    # ✅ Filtro de pendientes de pago
    solo_pendientes = request.GET.get('solo_pendientes', '') == 'true'
    
    # Lista para almacenar solo las reservas con pagos
    reservas_con_pagos = []
    
    # ✅ Variables para estadísticas
    total_operaciones = 0
    operaciones_pendientes = 0
    
    # Calcular totales pagados para cada reserva y filtrar las que tienen pagos
    for reserva in reservas:
        # Buscar movimientos de caja relacionados con esta reserva
        movimientos = MovimientoCaja.objects.filter(
            propiedad=reserva.propiedad,
            tipo=TipoMovimientoCajaEnum.INGRESO,
            concepto__icontains=f"Operaci\u00f3n {reserva.id}"
        )
        
        # ❌ FILTRO: Si no hay movimientos de pago, no incluir en operaciones
        if not movimientos.exists():
            print(f"⚠️ OPERACIONES - Reserva {reserva.id} SIN PAGOS - No se incluye en operaciones")
            continue
        
        # ✅ LÓGICA SIMPLE: SALDO = PRECIO TOTAL - SEÑA DEL CASILLERO
        saldo_pendiente = reserva.precio_total - (reserva.senia or 0)
        
        print(f"💰 OPERACIONES - CÁLCULO DIRECTO:")
        print(f"   - Precio Total: ${reserva.precio_total}")
        print(f"   - Seña: ${reserva.senia or 0}")
        print(f"   - Saldo Pendiente: ${saldo_pendiente}")
        
        # ✅ VERIFICAR QUE HAYA AL MENOS ALGÚN PAGO REAL
        total_pagado = sum(
            mov.monto_efectivo + mov.monto_cheque + mov.monto_tarjeta + mov.monto_deposito
            for mov in movimientos
        )
        
        if total_pagado > 0:
            # ✅ CORREGIDO: total_pagado debe ser solo la seña (sin depósito)
            reserva.total_pagado = reserva.senia or 0  # Solo la seña
            reserva.saldo_pendiente = saldo_pendiente  # Ya está calculado correctamente
            reserva.total_senia_pagada = reserva.senia or 0
            reserva.total_deposito_pagado = reserva.deposito_garantia or 0
            
            # ✅ DETECTAR SI EL DEPÓSITO FUE PAGADO (concepto 10)
            deposito_pagado = False
            for movimiento in movimientos:
                if movimiento.concepto and "|CONCEPTOS:" in movimiento.concepto:
                    # Buscar concepto 10 en la estructura
                    concepto_parts = movimiento.concepto.split("|CONCEPTOS:", 1)
                    if len(concepto_parts) > 1:
                        conceptos_data = concepto_parts[1]
                        if "|10:" in conceptos_data:  # Concepto 10 presente
                            deposito_pagado = True
                            break
            
            # Agregar estado del depósito
            reserva.deposito_estado = 'pagado' if deposito_pagado else 'pendiente'
            
            print(f"✅ OPERACIONES - Reserva {reserva.id}: Precio Total: {reserva.precio_total}, Seña: {reserva.senia or 0}, Depósito: {reserva.deposito_garantia or 0} ({reserva.deposito_estado}), Saldo: {reserva.saldo_pendiente}")
            
            # Obtener el movimiento más reciente para el enlace del recibo
            reserva.movimiento_reciente = movimientos.first() if movimientos.exists() else None
            
            # ✅ OBTENER TODOS LOS RECIBOS DE ESTA RESERVA
            from .models.recibo import Recibo
            recibos_reserva = Recibo.objects.filter(reserva=reserva).order_by('-fecha_emision')
            reserva.todos_recibos = recibos_reserva
            
            print(f"🔍 DEBUG RECIBOS - Reserva {reserva.id}:")
            print(f"   - Cantidad de recibos: {recibos_reserva.count()}")
            print(f"   - QuerySet evaluado: {list(recibos_reserva.values('id', 'numero_recibo', 'monto_este_pago'))}")
            
            # ✅ VERIFICAR SI HAY MÚLTIPLES RECIBOS
            if recibos_reserva.count() > 1:
                print(f"🎯 MÚLTIPLES RECIBOS DETECTADOS: {recibos_reserva.count()} recibos")
                for i, recibo in enumerate(recibos_reserva):
                    print(f"   [{i+1}] {recibo.numero_recibo}: ${recibo.monto_este_pago:,.0f} (Movimiento {recibo.movimiento_caja.id})")
            elif recibos_reserva.count() == 1:
                recibo = recibos_reserva.first()
                print(f"📋 UN SOLO RECIBO: {recibo.numero_recibo}: ${recibo.monto_este_pago:,.0f}")
            else:
                print(f"❌ NO HAY RECIBOS para esta reserva")
            
            # ✅ Contar estadísticas
            total_operaciones += 1
            if saldo_pendiente > 0:
                operaciones_pendientes += 1
            
            # ✅ Aplicar filtro de pendientes si está activo
            if solo_pendientes and saldo_pendiente == 0:
                # Si solo queremos pendientes y esta está pagada completa, saltarla
                continue
            
            # Agregar a la lista de reservas con pagos
            reservas_con_pagos.append(reserva)
        else:
            print(f"❌ OPERACIONES - Reserva {reserva.id} SIN PAGOS REALES - No se incluye en operaciones")
    
    return render(request, 'inmobiliaria/reserva/operaciones.html', {
        'reservas': reservas_con_pagos,
        'search_id': search_id,
        'solo_pendientes': solo_pendientes,
        'total_operaciones': total_operaciones,
        'operaciones_pendientes': operaciones_pendientes,
        'operaciones_mostradas': len(reservas_con_pagos),
    })
def crear_reserva(request):

    if request.method == 'POST':
        propiedad_id = request.POST.get('propiedad_id')
        fecha_inicio_str = request.POST.get('fecha_inicio')
        fecha_fin_str = request.POST.get('fecha_fin')

        try:
            fecha_inicio = parse_date(fecha_inicio_str)
            fecha_fin = parse_date(fecha_fin_str)

            if not fecha_inicio or not fecha_fin:
                raise ValidationError('Las fechas proporcionadas no son válidas.')

            if fecha_inicio > fecha_fin:
                raise ValidationError('La fecha de inicio no puede ser posterior a la fecha de fin.')

            propiedad = get_object_or_404(Propiedad, id=propiedad_id)
            
            # Aquí puedes añadir la lógica para crear la reserva o validar disponibilidad
            reserva = form.save(commit=False)
            reserva.propiedad_id = propiedad_id
            reserva.vendedor = request.user
            # Asegúrate de que precio_total tenga un valor
            reserva.precio_total = form.cleaned_data.get('precio_total', 0)
            # La cuota_pendiente se establecerá automáticamente en el save()
            reserva.save()

        except (ValueError, ValidationError) as e:
            return render(request, 'inmobiliaria/reserva/error.html', {'error': str(e)})

        return redirect('inmobiliaria:confirmar_reserva')

    return redirect('inmobiliaria:buscar_propiedades')
def reserva_editar(request, reserva_id):
    reserva = get_object_or_404(Reserva, pk=reserva_id)
    
    if request.method == "POST":
        form = ReservaForm(request.POST, instance=reserva)
        
        if form.is_valid():
            reserva = form.save(commit=False)
            propiedad = reserva.propiedad
            fecha_inicio = reserva.fecha_inicio
            fecha_fin = reserva.fecha_fin

            # Validacin de temporadas
            hoy = date.today()
  

            # Guardar los cambios si pasa las validaciones de temporada
            reserva.save()
            messages.success(request, 'Reserva actualizada exitosamente.')
            return redirect('inmobiliaria:reserva_detalle', reserva_id=reserva.id)
    else:
        form = ReservaForm(instance=reserva)
    
    return render(request, 'inmobiliaria/reserva/crear_reserva.html', {'form': form, 'reserva': reserva})

@login_required
def reserva_eliminar(request, reserva_id):
    reserva = get_object_or_404(Reserva, pk=reserva_id)
    
    if request.method == "POST":
        try:
            # ✅ NUEVO: Cancelar la reserva primero para restaurar disponibilidades
            print(f"🗑️ ELIMINANDO RESERVA {reserva_id}: {reserva.fecha_inicio} al {reserva.fecha_fin}")
            print(f"   Propiedad: {reserva.propiedad.id} - {reserva.propiedad.direccion}")
            
            # Guardar datos para el mensaje
            fecha_inicio = reserva.fecha_inicio
            fecha_fin = reserva.fecha_fin
            propiedad_direccion = reserva.propiedad.direccion
            
            # 1️⃣ Cancelar la reserva (esto restaura las disponibilidades y reconstruye historial)
            reserva.cancelar_reserva()
            
            # 2️⃣ Ahora sí eliminar físicamente la reserva
            reserva.delete()
            
            print(f"✅ Reserva eliminada y disponibilidades restauradas: {fecha_inicio} al {fecha_fin}")
            messages.success(request, f'Reserva eliminada exitosamente. Las fechas del {fecha_inicio.strftime("%d/%m/%Y")} al {fecha_fin.strftime("%d/%m/%Y")} vuelven a estar disponibles.')
            
        except Exception as e:
            print(f"❌ Error al eliminar reserva: {e}")
            messages.error(request, f'Error al eliminar la reserva: {str(e)}')
            
        return redirect('inmobiliaria:reservas')  # Redirige a la lista de reservas después de eliminar
    
    return render(request, 'inmobiliaria/reserva/confirmar_eliminar.html', {'reserva': reserva})
def parse_fecha(fecha_str):
    try:
        # Dividir la fecha en sus componentes
        dia, mes, anio = fecha_str.split('/')
        
        # Convertir a enteros
        dia = int(dia)
        mes = int(mes)
        anio = int(anio)
        
        # Validar que los valores sean razonables
        if dia < 1 or dia > 31 or mes < 1 or mes > 12:
            raise ValidationError('Fecha inválida')
            
        # Crear la fecha en el formato correcto
        return date(anio, mes, dia)
        
    except (ValueError, TypeError, AttributeError):
        raise ValidationError('El formato de fecha debe ser DD/MM/YYYY')

def confirmar_reserva(request):
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Obtener datos del formulario
                propiedad_id = request.POST.get('propiedad_id')
                fecha_inicio_str = request.POST.get('fecha_inicio')
                fecha_fin_str = request.POST.get('fecha_fin')
                vendedor_id = request.POST.get('vendedor_id')
                inquilino_id = request.POST.get('inquilino_id')
                precio = request.POST.get('precio_total', '0')
                es_operacion_directa = request.POST.get('es_operacion_directa') == '1'

                # Convertir fechas
                try:
                    fecha_inicio = datetime.strptime(fecha_inicio_str, '%d/%m/%Y').date()
                    fecha_fin = datetime.strptime(fecha_fin_str, '%d/%m/%Y').date()
                except ValueError as e:
                    return JsonResponse({
                        'success': False,
                        'error': f'Error en el formato de las fechas: {str(e)}'
                    })

                # Obtener los objetos necesarios
                try:
                    propiedad = Propiedad.objects.get(id=propiedad_id)
                    vendedor = Vendedor.objects.get(id=vendedor_id)
                    inquilino = Inquilino.objects.get(id=inquilino_id)
                except (Propiedad.DoesNotExist, Vendedor.DoesNotExist, Inquilino.DoesNotExist) as e:
                    return JsonResponse({
                        'success': False,
                        'error': f'Error al obtener los datos: {str(e)}'
                    })

                # Verificar disponibilidad usando el método del modelo
                if not propiedad.esta_disponible_en_fecha(fecha_inicio, fecha_fin):
                    return JsonResponse({
                        'success': False,
                        'error': 'La propiedad no está disponible para las fechas seleccionadas.'
                    })

                # Verificar que no haya reservas en el período
                reservas_existentes = Reserva.objects.filter(
                    propiedad=propiedad,
                    fecha_inicio__lt=fecha_fin,
                    fecha_fin__gt=fecha_inicio,
                    estado__in=['confirmada', 'confirmada_no_pagada']
                )

                if reservas_existentes.exists():
                    return JsonResponse({
                        'success': False,
                        'error': 'El período seleccionado ya tiene una reserva'
                    })

                # 🔍 DEBUG: Ver qué precio llega del frontend
                print(f"🔍 PRECIO RECIBIDO DEL FRONTEND:")
                print(f"   - precio original: '{precio}' (tipo: {type(precio)})")
                
                # Limpiar el precio y convertirlo a float
                precio_limpio = precio.replace('$', '').replace(',', '').replace('.', '').strip()
                print(f"   - precio limpio: '{precio_limpio}'")
                
                try:
                    precio_float = float(precio_limpio)  # Ya no dividir por 100
                    print(f"   - precio float: {precio_float}")
                except ValueError:
                    print(f"   - ERROR: No se pudo convertir '{precio_limpio}' a float")
                    return JsonResponse({
                        'success': False,
                        'error': 'El precio no tiene un formato válido'
                    })

                # Crear la reserva
                reserva = Reserva.objects.create(
                    propiedad=propiedad,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    vendedor=vendedor,
                    cliente=inquilino,
                    precio_total=precio_float,
                    estado='confirmada' if es_operacion_directa else 'confirmada_no_pagada',
                    sucursal=request.user.sucursal  # Asignar la sucursal del usuario
                )

                # ✅ MANTENER DISPONIBILIDADES FIJAS - Solo actualizar historial
                print(f"✅ Reserva creada correctamente. ID: {reserva.id}")
                print(f"📋 Las disponibilidades se mantienen fijas, solo se actualiza el historial")

                # Si es operación directa, crear el movimiento de caja
                if es_operacion_directa:
                    # Crear el movimiento de caja aquí
                    caja_actual = Caja.objects.filter(
                        sucursal=request.user.sucursal,
                        fecha_cierre__isnull=True
                    ).first()

                    if not caja_actual:
                        return JsonResponse({
                            'success': False,
                            'error': 'No hay una caja abierta para registrar la operación'
                        })

                    MovimientoCaja.objects.create(
                        caja=caja_actual,
                        tipo=TipoMovimientoCajaEnum.INGRESO,
                        concepto='Alquiler por día',
                        monto_efectivo=precio_float,  # Ajustar según la forma de pago
                        descripcion=f'Alquiler por día - {propiedad.direccion}',
                        reserva=reserva
                    )

                # Determinar el estado asignado
                estado_asignado = 'confirmada' if es_operacion_directa else 'confirmada_no_pagada'
                tipo_operacion = 'Operación Directa' if es_operacion_directa else 'Reserva'
                
                return JsonResponse({
                    'success': True,
                    'reserva_id': reserva.id,
                    'estado_asignado': estado_asignado,
                    'tipo_operacion': tipo_operacion,
                    'mensaje_estado': f'{tipo_operacion} creada con estado: {estado_asignado}',
                    'redirect_url': reverse('inmobiliaria:ver_recibo', args=[reserva.id]) if es_operacion_directa else reverse('inmobiliaria:reserva_exitosa', args=[reserva.id])
                })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })

    return JsonResponse({
        'success': False,
        'error': 'Método no permitido'
    })

def consolidar_disponibilidades(propiedad):
    """
    Consolida disponibilidades adyacentes
    """
    disponibilidades = list(Disponibilidad.objects.filter(
        propiedad=propiedad
    ).order_by('fecha_inicio'))
    
    i = 0
    while i < len(disponibilidades) - 1:
        actual = disponibilidades[i]
        siguiente = disponibilidades[i + 1]
        
        # Si son adyacentes
        if actual.fecha_fin == siguiente.fecha_inicio:
            # Extender la disponibilidad actual
            actual.fecha_fin = siguiente.fecha_fin
            actual.save()
            # Eliminar la siguiente
            siguiente.delete()
            # Actualizar la lista
            disponibilidades = list(Disponibilidad.objects.filter(
                propiedad=propiedad
            ).order_by('fecha_inicio'))
        else:
            i += 1

def reserva_detalle(request, reserva_id):
    reserva = get_object_or_404(Reserva, pk=reserva_id)
    return render(request, 'inmobiliaria/reserva/detalle.html', {'reserva': reserva})
# inmobiliaria/views.py
def formato_fecha(fecha):
    return fecha.strftime('%d/%m/%Y') if fecha else ''


def calcular_disponibilidad_real(propiedad, disponibilidades, reservas, fecha_inicio, fecha_fin):
    """
    Calcula la disponibilidad real de una propiedad considerando las reservas existentes.
    Retorna el período disponible más amplio que incluya o se superponga con las fechas solicitadas.
    """
    from datetime import timedelta
    
    # Calcular la duración del período solicitado
    dias_solicitados = (fecha_fin - fecha_inicio).days + 1
    
    # Obtener todas las disponibilidades que tienen superposición REAL con el período solicitado
    # Evitar casos donde solo se "tocan" en un día
    disponibilidades_validas = disponibilidades.filter(
        fecha_inicio__lt=fecha_fin,     # La disponibilidad empieza ANTES del fin solicitado (no en el mismo día)
        fecha_fin__gt=fecha_inicio      # La disponibilidad termina DESPUÉS del inicio solicitado (no en el mismo día)
    )
    
    if not disponibilidades_validas.exists():
        print(f"🚫 No hay disponibilidades que se superpongan con el período {fecha_inicio} a {fecha_fin}")
        return None
    
    # Obtener todas las reservas confirmadas o pagadas que se superponen
    reservas_confirmadas = reservas.filter(
        Q(estado='confirmada') | Q(estado='pagada') | Q(estado='confirmada_no_pagada'),
        fecha_inicio__lt=fecha_fin,
        fecha_fin__gt=fecha_inicio
    )
    
    # Si no hay reservas, usar el rango completo de disponibilidad
    if not reservas_confirmadas.exists():
        primera_disponibilidad = disponibilidades_validas.order_by('fecha_inicio').first()
        ultima_disponibilidad = disponibilidades_validas.order_by('-fecha_fin').first()
        
        return {
            'inicio': primera_disponibilidad.fecha_inicio if primera_disponibilidad else fecha_inicio,
            'fin': ultima_disponibilidad.fecha_fin if ultima_disponibilidad else fecha_fin
        }
    
    # Buscar períodos libres entre las reservas
    periodos_libres = []
    
    # Para cada disponibilidad, encontrar los períodos no reservados
    for disponibilidad in disponibilidades_validas:
        inicio_disp = max(disponibilidad.fecha_inicio, fecha_inicio)
        fin_disp = min(disponibilidad.fecha_fin, fecha_fin)
        
        # Dividir este período según las reservas existentes
        reservas_en_periodo = reservas_confirmadas.filter(
            fecha_inicio__lt=fin_disp,
            fecha_fin__gt=inicio_disp
        ).order_by('fecha_inicio')
        
        if not reservas_en_periodo.exists():
            # No hay reservas en este período, verificar que cubra completamente las fechas solicitadas
            if disponibilidad.fecha_inicio <= fecha_inicio and disponibilidad.fecha_fin >= fecha_fin:
                # La disponibilidad completa cubre las fechas solicitadas, mostrar todo el período disponible
                periodos_libres.append({
                    'inicio': disponibilidad.fecha_inicio,  # Mostrar desde el inicio real de la disponibilidad
                    'fin': disponibilidad.fecha_fin,        # Hasta el fin real de la disponibilidad
                    'dias': (disponibilidad.fecha_fin - disponibilidad.fecha_inicio).days + 1
                })
        else:
            # Hay reservas, encontrar los huecos
            fecha_actual = inicio_disp
            
            for reserva in reservas_en_periodo:
                if fecha_actual < reserva.fecha_inicio:
                    # Hay un período libre antes de esta reserva
                    fin_periodo = reserva.fecha_inicio - timedelta(days=1)
                    if fecha_actual <= fin_periodo:
                        # Agregar cualquier período libre válido (sin exigir cobertura completa)
                        periodos_libres.append({
                            'inicio': fecha_actual,      # Mostrar desde el inicio real del período libre
                            'fin': fin_periodo,          # Hasta el fin real del período libre
                            'dias': (fin_periodo - fecha_actual).days + 1
                        })
                
                # Mover la fecha actual al final de la reserva
                fecha_actual = max(fecha_actual, reserva.fecha_fin + timedelta(days=1))
            
            # Verificar si hay un período libre después de la última reserva
            if fecha_actual <= disponibilidad.fecha_fin:
                # Agregar cualquier período libre válido (sin exigir cobertura completa)
                periodos_libres.append({
                    'inicio': fecha_actual,                    # Desde donde queda libre después de la reserva
                    'fin': disponibilidad.fecha_fin,          # Hasta el fin real de la disponibilidad
                    'dias': (disponibilidad.fecha_fin - fecha_actual).days + 1
                })
    
    if not periodos_libres:
        return None
    
    # Si hay períodos libres, devolver el más amplio o conveniente
    if periodos_libres:
        # Buscar el período que mejor cubra las fechas solicitadas o el más amplio
        mejor_periodo = max(periodos_libres, key=lambda p: p['dias'])
        print(f"✅ Período disponible encontrado: {mejor_periodo['inicio']} a {mejor_periodo['fin']} ({mejor_periodo['dias']} días)")
        return {
            'inicio': mejor_periodo['inicio'],
            'fin': mejor_periodo['fin']
        }
    
    print(f"🚫 No se encontraron períodos libres para {fecha_inicio} a {fecha_fin}")
    return None


@login_required
def buscar_propiedades_reserva(request):
    # FUNCIÓN: buscar_propiedades_reserva - cálculo día por día con temporadas ✅
    # Obtener la sucursal del vendedor logueado
    sucursal_vendedor = request.user.sucursal
    
    inquilinos = Inquilino.objects.filter(sucursal=sucursal_vendedor)
    form = BuscarPropiedadesForm(request.POST or None)
    inquilino_form = InquilinoForm(request.POST)
    propiedades_disponibles = []
    propiedades_sin_precio = []
    vendedores = Vendedor.objects.filter(sucursal=sucursal_vendedor)
    total_dias_reserva = 0

    fecha_inicio = None
    fecha_fin = None
    origen = None
    destino = None

    if form.is_valid():
        fecha_inicio = form.cleaned_data['fecha_inicio']
        fecha_fin = form.cleaned_data['fecha_fin']
        origen = form.cleaned_data['origen']
        destino = form.cleaned_data['destino']
        ver_todas = form.cleaned_data.get('ver_todas', False)

        # Filtrar propiedades según la opción seleccionada
        if ver_todas:
            propiedades = Propiedad.objects.all()
        else:
            propiedades = Propiedad.objects.filter(sucursal=sucursal_vendedor)

        # Prefetch los precios para cada propiedad
        propiedades = propiedades.prefetch_related(
            Prefetch('precios', queryset=Precio.objects.all(), to_attr='todos_precios')
        ).select_related('sucursal')

        # Aplicar filtros del formulario
        if origen:
            propiedades = propiedades.filter(ubicacion__icontains=origen)
        
        if destino:
            propiedades = propiedades.filter(ubicacion__icontains=destino)

        tipo_inmueble = form.cleaned_data.get('tipo_inmueble')
        if tipo_inmueble:
            propiedades = propiedades.filter(tipo_inmueble__in=tipo_inmueble)

        vista = form.cleaned_data.get('vista')
        if vista:
            propiedades = propiedades.filter(vista__in=vista)

        ambientes = form.cleaned_data.get('ambientes')
        if ambientes:
            propiedades = propiedades.filter(ambientes=ambientes)

        valoracion = form.cleaned_data.get('valoracion')
        if valoracion:
            propiedades = propiedades.filter(valoracion=valoracion)

        precio_min = form.cleaned_data.get('precio_min')
        if precio_min is not None:
            propiedades = propiedades.filter(precio__gte=precio_min)

        precio_max = form.cleaned_data.get('precio_max')
        if precio_max is not None:
            propiedades = propiedades.filter(precio__lte=precio_max)

        # Filtros booleanos
        caracteristicas_booleanas = [
            'amoblado', 'cochera', 'tv_smart', 'wifi', 'dependencia', 'patio',
            'parrilla', 'piscina', 'reciclado', 'a_estrenar', 'terraza', 'balcon',
            'baulera', 'lavadero', 'seguridad', 'vista_al_Mar', 'vista_panoramica', 'apto_credito'
        ]
        for caracteristica in caracteristicas_booleanas:
            if form.cleaned_data.get(caracteristica):
                propiedades = propiedades.filter(**{caracteristica: True})

        # ✅ LÓGICA SIMPLE: Buscar fechas libres entre disponibilidades y reservas
        for propiedad in propiedades:
            from datetime import timedelta
            print(f"🔍 PROCESANDO PROPIEDAD {propiedad.id}: {propiedad}")
            print(f"   🔎 Buscando disponibilidades que contengan {fecha_inicio} al {fecha_fin}")
            
            # 1️⃣ BUSCAR DISPONIBILIDADES QUE CONTENGAN EL PERÍODO
            disponibilidades = Disponibilidad.objects.filter(
                propiedad=propiedad,
                fecha_inicio__lte=fecha_inicio,
                fecha_fin__gte=fecha_fin,
            )
            
            if disponibilidades.exists():
                # 2️⃣ BUSCAR ÚLTIMA FECHA FINAL ANTES DEL PERÍODO BUSCADO
                # Combinar disponibilidades y reservas para encontrar la fecha más reciente
                
                # Fechas finales de disponibilidades que terminan antes del período
                disp_anteriores = Disponibilidad.objects.filter(
                    propiedad=propiedad,
                    fecha_fin__lt=fecha_inicio
                ).order_by('-fecha_fin').first()
                
                # Fechas finales de reservas que terminan antes del período
                reservas_anteriores = propiedad.reservas.filter(
                    fecha_fin__lt=fecha_inicio
                ).order_by('-fecha_fin').first()
                
                # Determinar la fecha final más reciente
                ultima_fecha_fin = None
                if disp_anteriores and reservas_anteriores:
                    ultima_fecha_fin = max(disp_anteriores.fecha_fin, reservas_anteriores.fecha_fin)
                elif disp_anteriores:
                    ultima_fecha_fin = disp_anteriores.fecha_fin
                elif reservas_anteriores:
                    ultima_fecha_fin = reservas_anteriores.fecha_fin
                
                # 3️⃣ BUSCAR PRIMERA FECHA INICIAL DESPUÉS DEL PERÍODO BUSCADO
                
                # Fechas iniciales de disponibilidades que empiezan después del período
                disp_posteriores = Disponibilidad.objects.filter(
                    propiedad=propiedad,
                    fecha_inicio__gt=fecha_fin
                ).order_by('fecha_inicio').first()
                
                # Fechas iniciales de reservas que empiezan después del período
                reservas_posteriores = propiedad.reservas.filter(
                    fecha_inicio__gt=fecha_fin
                ).order_by('fecha_inicio').first()
                
                # Determinar la fecha inicial más próxima
                proxima_fecha_inicio = None
                if disp_posteriores and reservas_posteriores:
                    proxima_fecha_inicio = min(disp_posteriores.fecha_inicio, reservas_posteriores.fecha_inicio)
                elif disp_posteriores:
                    proxima_fecha_inicio = disp_posteriores.fecha_inicio
                elif reservas_posteriores:
                    proxima_fecha_inicio = reservas_posteriores.fecha_inicio
                
                # 4️⃣ CALCULAR PERÍODO LIBRE
                disponibilidad_base = disponibilidades.first()
                
                fecha_disponible_desde = disponibilidad_base.fecha_inicio
                if ultima_fecha_fin:
                    # 🏨 LÓGICA HOTEL: Si reserva termina el 17, el 17 ya está disponible
                    fecha_disponible_desde = ultima_fecha_fin
                
                fecha_disponible_hasta = disponibilidad_base.fecha_fin
                if proxima_fecha_inicio:
                    # 🏨 LÓGICA HOTEL: Si próxima reserva empieza el 25, hasta el 25 está disponible
                    fecha_disponible_hasta = proxima_fecha_inicio
                
                # 5️⃣ ASIGNAR FECHAS CALCULADAS
                propiedad.disponibilidad_inicio = fecha_disponible_desde
                propiedad.disponibilidad_fin = fecha_disponible_hasta
                
                print(f"🎯 PROP {propiedad.id}: Libre desde {fecha_disponible_desde} hasta {fecha_disponible_hasta}")
                print(f"   📅 Asignado: disponibilidad_inicio={propiedad.disponibilidad_inicio}")
                print(f"   📅 Asignado: disponibilidad_fin={propiedad.disponibilidad_fin}")
                print(f"   📊 Disponibilidad base: {disponibilidad_base.fecha_inicio} al {disponibilidad_base.fecha_fin}")
                if ultima_fecha_fin:
                    print(f"   ⏪ Última fecha final anterior: {ultima_fecha_fin}")
                if proxima_fecha_inicio:
                    print(f"   ⏩ Próxima fecha inicial posterior: {proxima_fecha_inicio}")
            else:
                print(f"❌ PROP {propiedad.id}: NO tiene disponibilidades que contengan el período {fecha_inicio} al {fecha_fin}")
                disponibilidades = Disponibilidad.objects.none()
                
                # Para debugging: mostrar todas las disponibilidades de esta propiedad
                todas_disponibilidades = Disponibilidad.objects.filter(propiedad=propiedad)
                print(f"   📋 Disponibilidades existentes ({todas_disponibilidades.count()}):")
                for disp in todas_disponibilidades:
                    print(f"     - {disp.fecha_inicio} al {disp.fecha_fin}")

            # Obtener las reservas asociadas a la propiedad
            reservas = propiedad.reservas.filter(
                Q(fecha_inicio__lt=fecha_fin) & Q(fecha_fin__gt=fecha_inicio)
            )
            
            if reservas.filter(estado='pagada').exists():
                continue  # Saltar esta propiedad si ya tiene una reserva pagada

            # Verificar si existe una reserva que debe mostrarse en rojo
            reserva_confirmada_no_pagada = reservas.filter(Q(estado='confirmada_no_pagada') | Q(estado='confirmada') | Q(estado='en_espera')).first()

            # Evaluar la disponibilidad y las reservas de la propiedad
            if disponibilidades.exists() and not reservas.filter(estado='confirmada').exists():
                if reserva_confirmada_no_pagada:
                    propiedad.reserva = reserva_confirmada_no_pagada
                    propiedad.estado_reserva = 'confirmada_no_pagada'  # Siempre mostrar como confirmada_no_pagada en frontend
                    propiedad.precio_total_reserva = reserva_confirmada_no_pagada.precio_total
                else:
                    propiedad.estado_reserva = 'disponible'

                # Calcular el precio total de la reserva según las fechas seleccionadas
                precio_total = 0
                print('fecha de inicio',fecha_inicio)
                print('fecha de fin',fecha_fin)
                # Calcular noches, no días (del 13 al 15 = 2 noches)
                noches_reserva = (fecha_fin - fecha_inicio).days
                total_dias_reserva = noches_reserva

                # 🔍 DEBUGGING CRÍTICO: Ver todos los precios de esta propiedad
                print(f"🔍 DEBUGGING PRECIOS - Propiedad {propiedad.id} (fechas: {fecha_inicio} al {fecha_fin}):")
                todos_precios = Precio.objects.filter(propiedad=propiedad)
                print(f"   Total precios configurados: {todos_precios.count()}")
                for precio in todos_precios:
                    print(f"   - {precio.tipo_precio}: ${precio.precio_por_dia}")
                

                
                # ✅ LÓGICA ORIGINAL QUE FUNCIONABA (copiada exacta de views_temp.py)
                precio_mas_caro = 0
                primer_dia = True
                
                for single_date in (fecha_inicio + timedelta(n) for n in range(noches_reserva)):
                    # Determinar el tipo de precio según la fecha
                    tipo_precio = None
                    if single_date.month == 1:  # Enero
                        tipo_precio = 'QUINCENA_1_ENERO' if single_date.day <= 15 else 'QUINCENA_2_ENERO'
                    elif single_date.month == 2:  # Febrero
                        tipo_precio = 'QUINCENA_1_FEBRERO' if single_date.day <= 15 else 'QUINCENA_2_FEBRERO'
                    elif single_date.month == 3:  # Marzo
                        tipo_precio = 'QUINCENA_1_MARZO' if single_date.day <= 15 else 'QUINCENA_2_MARZO'
                    elif single_date.month == 7:  # Julio (Vacaciones de Invierno)
                        tipo_precio = 'VACACIONES_INVIERNO'
                    elif single_date.month == 12:  # Diciembre
                        tipo_precio = 'QUINCENA_1_DICIEMBRE' if single_date.day <= 15 else 'QUINCENA_2_DICIEMBRE'
                    else:
                        tipo_precio = 'TEMPORADA_BAJA'  # Asumir temporada baja para otros meses

                    # Obtener el precio para la propiedad y la quincena correspondiente
                    try:
                        precio = Precio.objects.get(propiedad=propiedad, tipo_precio=tipo_precio)
                        precio_dia = precio.precio_por_dia or 0
                        print(f"✅ {single_date}: {tipo_precio} = ${precio_dia}")
                    except Precio.DoesNotExist:
                        precio_dia = 0
                        print(f"❌ {single_date}: {tipo_precio} = NO EXISTE")

                    if precio_dia > precio_mas_caro:
                        precio_mas_caro = precio_dia

                    if not primer_dia:
                        precio_total += precio_dia
                    else:
                        primer_dia = False

                precio_final_calculado = precio_total + precio_mas_caro
                propiedad.precio_total_reserva = precio_final_calculado
                print(f"🔥 PROPIEDAD {propiedad.id}: precio_total={precio_total}, precio_mas_caro={precio_mas_caro}, FINAL={precio_final_calculado}")

                # Calcular la disponibilidad real considerando las reservas existentes
                disponibilidad_calculada = calcular_disponibilidad_real(
                    propiedad, disponibilidades, reservas, fecha_inicio, fecha_fin
                )
                
                if disponibilidad_calculada:
                    propiedad.disponibilidad_inicio = disponibilidad_calculada['inicio']
                    propiedad.disponibilidad_fin = disponibilidad_calculada['fin']
                else:
                    # Si no hay disponibilidad, usar la lógica original como fallback
                    if not reservas.exists():
                        primera_disponibilidad = disponibilidades.order_by('fecha_inicio').first()
                        ultima_disponibilidad = disponibilidades.order_by('-fecha_fin').first()

                        if primera_disponibilidad:
                            propiedad.disponibilidad_inicio = primera_disponibilidad.fecha_inicio
                        if ultima_disponibilidad:
                            propiedad.disponibilidad_fin = ultima_disponibilidad.fecha_fin

                    # Obtener la reserva más cercana antes de la fecha de inicio
                    reserva_cercana = propiedad.reservas.filter(fecha_fin__lte=fecha_inicio).order_by('-fecha_fin').first()
                    reserva_cercana_fin = propiedad.reservas.filter(fecha_inicio__gte=fecha_fin).order_by('fecha_inicio').first()

                    if reserva_cercana:
                        propiedad.disponibilidad_inicio = reserva_cercana.fecha_fin

                    if reserva_cercana_fin:
                        propiedad.disponibilidad_fin = reserva_cercana_fin.fecha_inicio

                if reserva_confirmada_no_pagada:
                    propiedad.disponibilidad_inicio = reserva_confirmada_no_pagada.fecha_inicio 
                    propiedad.disponibilidad_fin = reserva_confirmada_no_pagada.fecha_fin

                # Añadir la propiedad disponible a la lista
                dias_disponibles = (fecha_inicio - propiedad.disponibilidad_inicio).days
                propiedad.dias_disponibles = max(dias_disponibles, 0)
                propiedades_disponibles.append(propiedad)
                propiedades_disponibles.sort(key=lambda x: x.dias_disponibles)

                # Asegúrate de que todos los precios estén disponibles
                try:
                    # Función auxiliar para manejar tipos de precio no válidos
                    def get_precio_order(precio):
                        try:
                            return TipoPrecio[precio.tipo_precio].value
                        except KeyError:
                            # Si el tipo no existe en el enum, ponerlo al final
                            return 999
                        
                    propiedad.todos_precios = sorted(propiedad.todos_precios, key=get_precio_order)
                except Exception as e:
                    print(f"Error ordenando precios para propiedad {propiedad.id}: {e}")
                    # En caso de error, no ordenar los precios
                    pass

    # Alerta si hay propiedades sin precio
    alerta_sin_precio = len(propiedades_sin_precio) > 0
    print("las fechas de inicio y fin son ",fecha_inicio,fecha_fin)
    print("los dias de reserva son ",total_dias_reserva)

    # ❌ ELIMINADO: El cálculo duplicado que estaba sobrescribiendo el precio correcto
    # El precio ya se calculó correctamente arriba en las líneas 1132-1167

    # Obtener conceptos para el template
    conceptos = Concepto.objects.filter(
        Q(sucursal=sucursal_vendedor) | Q(sucursal__isnull=True)
    ).order_by('nombre')

    return render(request, 'inmobiliaria/reserva/buscar_propiedades.html', {
        'form': form,
        'propiedades_disponibles': propiedades_disponibles,
        'alerta_sin_precio': alerta_sin_precio,
        'fecha_inicio': fecha_inicio.strftime('%d/%m/%Y') if fecha_inicio else '',
        'fecha_fin': fecha_fin.strftime('%d/%m/%Y') if fecha_fin else '',
        'total_dias': total_dias_reserva,
        'inquilinos': Inquilino.objects.all().order_by('apellido', 'nombre'),
        'vendedores': vendedores,
        'tipos_precio': TipoPrecio,
        'conceptos': conceptos
    })

@login_required
def crear_disponibilidad(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    
    if request.method == 'POST':
        form = DisponibilidadForm(propiedad=propiedad, data=request.POST)
        if form.is_valid():
            try:
                # Crear una nueva instancia de Disponibilidad
                nueva_disponibilidad = Disponibilidad(
                    propiedad=propiedad,
                    fecha_inicio=form.cleaned_data['fecha_inicio'],
                    fecha_fin=form.cleaned_data['fecha_fin'],
                    es_manual=True  # Marcada explícitamente como manual
                )
                
                # Verificar solapamiento manualmente
                solapamiento = Disponibilidad.objects.filter(
                    propiedad=propiedad,
                    fecha_fin__gte=nueva_disponibilidad.fecha_inicio,
                    fecha_inicio__lte=nueva_disponibilidad.fecha_fin
                ).exists()
                
                if solapamiento:
                    messages.error(request, 'Ya existe una disponibilidad para estas fechas')
                else:
                    nueva_disponibilidad.save()
                    
                    # ✅ Las disponibilidades manuales no crean historial automáticamente
                    # El historial se gestiona por separado
                    
                    messages.success(request, 'Disponibilidad creada exitosamente')
                    return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad.id)
                    
            except Exception as e:
                messages.error(request, f'Error al crear la disponibilidad: {str(e)}')
    else:
        form = DisponibilidadForm(propiedad=propiedad)
    
    # Obtener disponibilidades existentes
    disponibilidades = Disponibilidad.objects.filter(propiedad=propiedad).order_by('fecha_inicio')
    
    return render(request, 'inmobiliaria/propiedades/crear_disponibilidad.html', {
        'form': form,
        'propiedad': propiedad,
        'disponibilidades': disponibilidades
    })

def reserva_exitosa(request, reserva_id):
    
    reserva = Reserva.objects.get(id=reserva_id)
    print("la reserva es ",reserva.precio_total)
    
    context = {
        'reserva': reserva
    }
    return render(request, 'inmobiliaria/reserva/reserva_exitosa.html', context)

@login_required
def finalizar_reserva_nueva(request, reserva_id):
    """
    Nueva vista para finalizar reserva basada en la carga de recibo
    """
    try:
        # Obtener la reserva
        reserva = get_object_or_404(Reserva, id=reserva_id, sucursal=request.user.sucursal)
        
        # 🚀 SOLUCIÓN: Si la reserva tiene precio 0, recalcularlo
        if reserva.precio_total == 0:
            print(f"⚠️ Reserva {reserva.id} tiene precio 0, recalculando...")
            recalcular_precio_reserva(reserva)
            # Refrescar desde la base de datos
            reserva.refresh_from_db()
        
        # Obtener la caja actual de la sucursal
        caja_actual = Caja.objects.filter(
            sucursal=request.user.sucursal,
            fecha_cierre__isnull=True
        ).first()
        
        if not caja_actual:
            messages.error(request, 'No hay una caja abierta. Debe abrir una caja primero.')
            return redirect('inmobiliaria:reservas')
        
        # Calcular información del próximo movimiento
        cantidad_movimientos = MovimientoCaja.objects.filter(caja=caja_actual).count()
        proximo_numero_movimiento = cantidad_movimientos + 1
        
        # Obtener conceptos de caja disponibles
        conceptos_caja = Concepto.objects.all()
        
        # ✅ CALCULAR SALDO PENDIENTE CONSIDERANDO SOLO LA SEÑA (NO EL DEPÓSITO)
        # Buscar todos los movimientos de caja pagados para esta reserva
        pagos_anteriores = MovimientoCaja.objects.filter(
            propiedad=reserva.propiedad,
            tipo=TipoMovimientoCajaEnum.INGRESO,
            concepto__icontains=f"Operaci\u00f3n {reserva.id}"
        )
        
        # ✅ LÓGICA SIMPLE: SALDO = PRECIO TOTAL - SEÑA (EL DEPÓSITO NO AFECTA)
        saldo_a_ocupar = reserva.precio_total - (reserva.senia or 0)
        
        print(f"✅ CÁLCULO FINALIZAR RESERVA:")
        print(f"   - Precio Total: ${reserva.precio_total}")
        print(f"   - Seña: ${reserva.senia or 0}")
        print(f"   - Saldo Pendiente: ${saldo_a_ocupar}")
        print(f"   - Depósito: ${reserva.deposito_garantia or 0}")

        
        # ✅ CALCULAR SEÑA PENDIENTE: Si ya pagó seña, mostrar 0
        senia_pendiente = 0  # Por defecto 0, porque si ya pagó seña no debe pagar más
        if (reserva.senia or 0) == 0:
            # Si no hay seña pagada aún, puede que necesite pagar algo
            # Pero normalmente en "finalizar reserva" ya se pagó todo
            senia_pendiente = 0
        
        print(f"✅ SEÑA PENDIENTE CALCULADA:")
        print(f"   - Seña ya pagada: ${reserva.senia or 0}")
        print(f"   - Seña pendiente a mostrar: ${senia_pendiente}")

        # Datos para el formulario (solo lectura)
        context = {
            'reserva': reserva,
            'cliente_id': reserva.cliente.id,
            'cliente_nombre': f"{reserva.cliente.nombre} {reserva.cliente.apellido}",
            'interno_caja': caja_actual.numero,
            'propiedad_id': reserva.propiedad.id,
            'propiedad_direccion': reserva.propiedad.direccion,
            'fecha_actual': datetime.now().strftime('%d/%m/%Y'),
            'numero_movimiento': proximo_numero_movimiento,
            'numero_recibo': '0000-00000000',  # Para completar
            'productor_id': request.user.id,
            'productor_nombre': f"{request.user.nombre} {request.user.apellido}",
            'conceptos_caja': conceptos_caja,
            'saldo_a_ocupar': saldo_a_ocupar,
            'senia_pendiente': senia_pendiente,  # ✅ NUEVO: Seña pendiente (0 si ya se pagó)
            'total_senia_pagada': reserva.senia or 0,  # ✅ SIMPLE: Del casillero
            'total_deposito_pagado': reserva.deposito_garantia or 0,  # ✅ SIMPLE: Del casillero
            'deposito_garantia': reserva.deposito_garantia,
            'fecha_desde': reserva.fecha_inicio.strftime('%d/%m/%Y'),
            'fecha_hasta': reserva.fecha_fin.strftime('%d/%m/%Y'),
        }
        
        return render(request, 'inmobiliaria/reserva/finalizar_reserva_nueva.html', context)
        
    except Exception as e:
        messages.error(request, f'Error al cargar la reserva: {str(e)}')
        return redirect('inmobiliaria:reservas')

@login_required
def terminar_reserva(request, reserva_id):
    try:
        reserva = get_object_or_404(Reserva, id=reserva_id)
        conceptos_pago = ConceptoPago.objects.all()
        pagos_previos = Pago.objects.filter(reserva=reserva).order_by('-fecha')
        
        # Verificar si hay pagos y actualizar el estado
        if pagos_previos.exists():
            reserva.estado = 'pagada'
            reserva.save()
        
        # Inicializar o actualizar cuota_pendiente si es necesario
        if reserva.cuota_pendiente is None or reserva.cuota_pendiente == 0:
            reserva.cuota_pendiente = reserva.precio_total
            reserva.save()
        
        if request.method == 'POST':
            try:
                with transaction.atomic():
                    # Obtener datos del formulario
                    monto = Decimal(request.POST.get('monto', '0'))
                    forma_pago = request.POST.get('forma_pago')
                    concepto_id = request.POST.get('concepto')
                    deposito = Decimal(request.POST.get('deposito', '0'))
                    
                    # Validaciones
                    if monto <= 0:
                        raise ValueError('El monto debe ser mayor que cero')
                    
                    if monto > reserva.cuota_pendiente:
                        raise ValueError('El monto no puede ser mayor al saldo pendiente')
                    
                    # Obtener el concepto
                    concepto = get_object_or_404(ConceptoPago, id=concepto_id)
                    
                    # Obtener datos adicionales de tarjeta si es necesario
                    numero_tarjeta = None
                    tipo_tarjeta = None
                    if 'tarjeta' in forma_pago:
                        numero_tarjeta = request.POST.get('numero_tarjeta')
                        tipo_tarjeta = request.POST.get('tipo_tarjeta')
                        
                        if not numero_tarjeta or not tipo_tarjeta:
                            raise ValueError('Los datos de la tarjeta son requeridos')
                    
                    # Crear el pago con los datos adicionales
                    pago = Pago.objects.create(
                        reserva=reserva,
                        monto=monto,
                        forma_pago=forma_pago,
                        concepto=concepto,
                        numero_tarjeta=numero_tarjeta,
                        tipo_tarjeta=tipo_tarjeta
                    )
                    
                    # Calcular total pagado y actualizar saldo pendiente
                    total_pagado = Pago.objects.filter(reserva=reserva).aggregate(
                        total=models.Sum('monto'))['total'] or Decimal('0')
                    
                    # ✅ ACTUALIZAR RESERVA CON LÓGICA CORRECTA: SEPARAR SEÑA DE DEPÓSITO
                    # Calcular solo la seña (excluyendo depósitos)
                    pagos_reserva = Pago.objects.filter(reserva=reserva)
                    total_senia_only = 0
                    total_deposito_only = 0
                    
                    for pago in pagos_reserva:
                        concepto_lower = pago.concepto.concepto.lower() if pago.concepto else ''
                        es_deposito = any(palabra in concepto_lower for palabra in [
                            'depósito', 'deposito', 'garantía', 'garantia', 
                            'caución', 'caucion', 'seguridad', 'fianza',
                            'deposit', 'warranty', 'security'
                        ])
                        
                        if es_deposito:
                            total_deposito_only += pago.monto
                        else:
                            total_senia_only += pago.monto
                    
                    # Actualizar reserva solo con la seña
                    reserva.senia = total_senia_only  # ✅ Solo seña
                    reserva.deposito_garantia = deposito  # ✅ CORREGIDO: usar el campo correcto
                    reserva.cuota_pendiente = reserva.precio_total - total_senia_only  # ✅ Solo descontar seña
                    
                    # Si la cuota pendiente es 0 o menor, finalizar la reserva y crear movimiento de caja
                    if reserva.cuota_pendiente <= 0:
                        # Verificar si hay una caja abierta
                        caja_actual = Caja.objects.filter(
                            sucursal=request.user.sucursal,
                            estado='abierta'
                        ).first()
                        
                        if not caja_actual:
                            messages.error(request, 'No hay una caja abierta. Por favor, abra una caja antes de finalizar la reserva.')
                            return redirect('inmobiliaria:finalizar_reserva', reserva_id=reserva_id)
                        
                        # Crear el movimiento de caja
                        movimiento = MovimientoCaja(
                            caja=caja_actual,
                            tipo=TipoMovimientoCajaEnum.INGRESO,
                            tipo_comprobante=TipoComprobanteEnum.RECIBO,
                            concepto=f"Operaci\u00f3n #{reserva.id} - {reserva.propiedad.direccion}",
                            fecha_desde=reserva.fecha_inicio,
                            fecha_hasta=reserva.fecha_fin,
                            propiedad=reserva.propiedad,
                            sucursal=request.user.sucursal,
                            empleado=request.user
                        )
                        
                        # Asignar montos según los pagos de la reserva
                        for pago in reserva.pagos.all():
                            if pago.forma_pago == 'efectivo':
                                movimiento.monto_efectivo += pago.monto
                            elif pago.forma_pago == 'tarjeta':
                                movimiento.monto_tarjeta += pago.monto
                            elif pago.forma_pago == 'transferencia':
                                movimiento.monto_deposito += pago.monto
                                movimiento.destino_deposito = pago.destino_deposito
                            elif pago.forma_pago == 'cheque':
                                movimiento.monto_cheque += pago.monto
                            elif pago.forma_pago == 'qr':
                                movimiento.monto_deposito += pago.monto
                                movimiento.destino_deposito = pago.destino_deposito
                        
                        # Guardar el movimiento
                        movimiento.save()
                        reserva.estado = 'finalizada'
                        messages.success(request, 'Reserva finalizada y movimiento de caja registrado exitosamente')
                    else:
                        reserva.estado = 'en_espera'
                        messages.success(request, f'Pago registrado. Saldo pendiente: ${reserva.cuota_pendiente}')
                    
                    reserva.save()
                    
                    return JsonResponse({
                        'success': True,
                        'message': 'Pago registrado exitosamente',
                        'redirect_url': reverse('inmobiliaria:ver_recibo', args=[reserva.id]),
                        'detalles': {
                            'total_pagado': float(total_pagado),
                            'saldo_pendiente': float(reserva.cuota_pendiente),
                            'deposito_garantia': float(reserva.deposito_garantia or 0),
                            'estado': reserva.estado
                        }
                    })
                    
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': str(e)
                })
        
        # ✅ CALCULAR SALDO SEPARANDO SEÑA DE DEPÓSITO
        total_senia_pagada = 0
        total_deposito_pagado = 0
        total_pagado = 0
        
        for pago in pagos_previos:
            total_pagado += pago.monto
            
            # Identificar si es depósito por el concepto
            concepto_lower = pago.concepto.concepto.lower() if pago.concepto else ''
            es_deposito = any(palabra in concepto_lower for palabra in [
                'depósito', 'deposito', 'garantía', 'garantia', 
                'caución', 'caucion', 'seguridad', 'fianza',
                'deposit', 'warranty', 'security'
            ])
            
            if es_deposito:
                total_deposito_pagado += pago.monto
                print(f"💳 DEPÓSITO TERMINAR - Concepto: '{concepto_lower}', Monto: {pago.monto}")
            else:
                total_senia_pagada += pago.monto
                print(f"💰 SEÑA TERMINAR - Concepto: '{concepto_lower}', Monto: {pago.monto}")
        
        # ✅ SALDO PENDIENTE = Precio total - SOLO LA SEÑA (NO EL DEPÓSITO)
        saldo_pendiente = reserva.precio_total - total_senia_pagada
        
        print(f"💰 TERMINAR RESERVA - Precio Total: {reserva.precio_total}, Seña: {total_senia_pagada}, Depósito: {total_deposito_pagado}, Saldo: {saldo_pendiente}")
        
        context = {
            'reserva': reserva,
            'conceptos_pago': conceptos_pago,
            'pagos_previos': pagos_previos,
            'formas_pago': Pago.FORMA_PAGO_CHOICES,
            'total_pagado': total_pagado,
            'saldo_pendiente': saldo_pendiente,  # ✅ Usar el saldo correcto calculado
            'total_senia_pagada': total_senia_pagada,  # ✅ NUEVO: Solo seña
            'total_deposito_pagado': total_deposito_pagado,  # ✅ NUEVO: Solo depósito
            'deposito': reserva.deposito_garantia or 0
        }
        
        return render(request, 'inmobiliaria/reserva/finalizar_reserva.html', context)
        
    except Exception as e:
        messages.error(request, f'Error al procesar la reserva: {str(e)}')
        return redirect('inmobiliaria:finalizar_reserva', reserva_id=reserva_id)

@login_required
def ver_recibo(request, reserva_id):
    # DEBUG: Confirmar que estamos en la función correcta
    print("🧾 EJECUTANDO ver_recibo desde views.py (FUNCIÓN ACTUALIZADA)")
    print(f"🧾 Reserva ID: {reserva_id}")
    try:
        reserva = get_object_or_404(Reserva, id=reserva_id)
        
        # Crear movimiento de caja automáticamente
        caja_actual = Caja.objects.filter(
            sucursal=request.user.sucursal,
            estado='abierta'
        ).first()
        
        if caja_actual:
            # Crear el movimiento
            movimiento = MovimientoCaja(
                caja=caja_actual,
                tipo=TipoMovimientoCajaEnum.INGRESO,
                concepto=f"Operaci\u00f3n #{reserva.id} - {reserva.propiedad.direccion}",
                fecha_desde=reserva.fecha_inicio,
                fecha_hasta=reserva.fecha_fin,
                propiedad=reserva.propiedad,
                sucursal=request.user.sucursal,
                empleado=request.user
                # Removemos a_descontar ya que es un ingreso
            )
            
            # Asignar montos según los pagos de la reserva
            for pago in reserva.pagos.all():
                if pago.forma_pago == 'efectivo':
                    movimiento.monto_efectivo += pago.monto
                elif pago.forma_pago == 'tarjeta':
                    movimiento.monto_tarjeta += pago.monto
                elif pago.forma_pago == 'transferencia':
                    movimiento.monto_deposito += pago.monto
                    movimiento.destino_deposito = pago.destino_deposito
                elif pago.forma_pago == 'cheque':
                    movimiento.monto_cheque += pago.monto
            
            movimiento.save()
            
            messages.success(request, 'Movimiento de caja creado exitosamente')
        else:
            messages.warning(request, 'No hay una caja abierta para registrar el movimiento')
        
        # Preparar datos para el recibo
        from datetime import datetime
        from django.utils.dateformat import format
        
        fecha_actual = timezone.now()
        
        # Obtener los pagos de la reserva
        pagos = []
        total_pagado = 0
        formas_de_pago = []
        
        # Buscar si hay conceptos detallados de la operación
        from .models import Registro
        conceptos_operacion = None
        
        # Intentar encontrar registros relacionados usando número de recibo o ID de reserva
        try:
            # Buscar por número de recibo si existe un movimiento reciente
            if hasattr(reserva, 'movimiento_reciente') and reserva.movimiento_reciente:
                conceptos_operacion = Registro.objects.filter(
                    interno_caja=reserva.movimiento_reciente.numero_liquidacion
                ).order_by('fecha')
        except:
            pass
        
        if conceptos_operacion and conceptos_operacion.exists():
            # Usar los conceptos de la operación
            for registro in conceptos_operacion:
                concepto_desc = ''
                if registro.concepto:
                    concepto_desc = f'{registro.concepto.id} - {registro.concepto.nombre}'
                else:
                    concepto_desc = 'Concepto no especificado'
                
                pagos.append({
                    'fecha': registro.fecha_comprobante.strftime('%d/%m/%Y'),
                    'codigo': registro.interno_caja or f'R{registro.id:04d}',
                    'concepto': concepto_desc,
                    'monto': f'${registro.liquidacion:,.0f}'
                })
                total_pagado += registro.liquidacion
        else:
            # Fallback: usar los pagos de la reserva como antes
            for pago in reserva.pagos.all():
                # Obtener el concepto correcto del pago
                concepto_desc = ''
                if hasattr(pago, 'concepto') and pago.concepto:
                    concepto_desc = f'{pago.concepto.codigo} - {pago.concepto.nombre}'
                else:
                    concepto_desc = f'Pago reserva {reserva.id}'
                
                pagos.append({
                    'fecha': pago.fecha.strftime('%d/%m/%Y') if pago.fecha else '',
                    'codigo': pago.codigo if hasattr(pago, 'codigo') and pago.codigo else f'P{pago.id:04d}',
                    'concepto': concepto_desc,
                    'monto': f'${pago.monto:,.0f}'  # Formatear como moneda
                })
                total_pagado += pago.monto
                if pago.forma_pago not in formas_de_pago:
                    formas_de_pago.append(pago.forma_pago.title())
        
        # Si no hay formas de pago desde pagos, intentar obtener del movimiento creado
        if not formas_de_pago and 'movimiento' in locals():
            if movimiento.monto_efectivo > 0:
                formas_de_pago.append('Efectivo')
            if movimiento.monto_tarjeta > 0:
                formas_de_pago.append('Tarjeta')
            if movimiento.monto_cheque > 0:
                formas_de_pago.append('Cheque')
            if movimiento.monto_deposito > 0:
                if movimiento.destino_deposito == 'galicia':
                    formas_de_pago.append('Galicia')
                elif movimiento.destino_deposito == 'mp':
                    formas_de_pago.append('Mercado Pago')
                else:
                    formas_de_pago.append('Transferencia')
        
            # Función simplificada para convertir número a palabras
            def numero_a_palabras(numero):
                try:
                    numero = int(numero)
                    if numero == 0:
                        return "PESOS CERO CON 00/100"
                    elif numero < 1000:
                        return f"PESOS {numero} CON 00/100"
                    elif numero < 1000000:
                        return f"PESOS {numero//1000} MIL {numero%1000} CON 00/100"
                    else:
                        return f"PESOS {numero//1000000} MILLONES CON 00/100"
                except:
                    return "PESOS CIENTO TREINTA MIL CON 00/100"
        
        # Preparar datos del cliente con campos adicionales
        cliente_data = reserva.cliente
        cliente_completo = {
            'nombre_completo': f"{cliente_data.nombre} {cliente_data.apellido}",
            'domicilio': cliente_data.domicilio or '',
            'localidad': cliente_data.localidad or '',
            'provincia': cliente_data.provincia or '',
            'dni': cliente_data.dni or '',
            'telefono': cliente_data.celular or '',  # Mapear celular a telefono
            'cuit': getattr(cliente_data, 'cuit', '') or '',  # CUIT puede no existir
        }
        
        # Preparar datos de la propiedad con formato correcto
        propiedad_data = reserva.propiedad
        propiedad_completa = {
            'direccion': propiedad_data.direccion or '',
            'id': propiedad_data.id,
            'llave': propiedad_data.llave or 'N/A',
            'piso': propiedad_data.piso or '',
            'departamento': propiedad_data.departamento or '',
            'ambientes': f"{propiedad_data.ambientes} personas" if propiedad_data.ambientes else 'N/A',
            'wifi': 'SÍ' if propiedad_data.wifi else 'NO',
            'cochera': 'SÍ' if propiedad_data.cochera else 'NO',
        }
        
        # Preparar datos de la reserva con formato de moneda
        reserva_formateada = {
            'id': reserva.id,
            'precio_total': f'${reserva.precio_total:,.0f}',
            'senia': f'${reserva.senia:,.0f}',
            'cuota_pendiente': f'${reserva.cuota_pendiente:,.0f}',
            'deposito_garantia': f'${reserva.deposito_garantia:,.0f}',
            'propiedad': propiedad_completa,
        }
        
        # ✅ CALCULAR VALORES CORRECTOS PARA EL RECIBO
        # Calcular seña y saldo restante basado en lo que realmente se pagó
        senia_pagada = reserva.senia or 0
        deposito_pagado = reserva.deposito_garantia or 0
        precio_total = reserva.precio_total or 0
        saldo_restante = precio_total - senia_pagada
        
        # Verificar si el depósito fue pagado revisando los conceptos (concepto 10)
        deposito_estado = 'no_aplica'
        if deposito_pagado > 0:
            # Verificar si hay concepto 10 en los pagos
            concepto_10_presente = False
            if conceptos_operacion and conceptos_operacion.exists():
                for registro in conceptos_operacion:
                    if registro.concepto and registro.concepto.id == 10:
                        concepto_10_presente = True
                        break
            
            if concepto_10_presente:
                deposito_estado = 'pagado'
            else:
                deposito_estado = 'pendiente'
        
        # DEBUG: Confirmar template y datos
        print("🧾 TEMPLATE USADO: inmobiliaria/reserva/recibo.html")
        print(f"🧾 PRECIO TOTAL: ${precio_total:,.0f}")
        print(f"🧾 SEÑA PAGADA: ${senia_pagada:,.0f}")
        print(f"🧾 SALDO RESTANTE: ${saldo_restante:,.0f}")
        print(f"🧾 DEPÓSITO: ${deposito_pagado:,.0f} ({deposito_estado})")
        print(f"🧾 TOTAL PAGADO: {f'${total_pagado:,.0f}'}")
        print(f"🧾 FORMAS DE PAGO: {', '.join(formas_de_pago) if formas_de_pago else 'EFECTIVO'}")
        print(f"🧾 PAGOS COUNT: {len(pagos)}")
        
        # Continuar con la generación del recibo usando el template correcto
        return render(request, 'inmobiliaria/reserva/recibo.html', {
            'reserva': reserva_formateada,
            'cliente': cliente_completo,
            'propiedad': propiedad_completa,
            'numero_recibo': f'R{reserva.id:06d}',
            'fecha': fecha_actual.strftime('%d/%m/%Y'),
            'hora': fecha_actual.strftime('%H:%M'),
            'fecha_inicio': reserva.fecha_inicio.strftime('%d/%m/%Y'),
            'fecha_fin': reserva.fecha_fin.strftime('%d/%m/%Y'),
            'descripcion': 'Alquiler temporario por días',
            'pagos': pagos,
            'total_pagado': f'${total_pagado:,.0f}',
            'monto_en_palabras': numero_a_palabras(total_pagado),
            'formas_de_pago': ', '.join(formas_de_pago) if formas_de_pago else 'EFECTIVO',
            # ✅ AGREGAR VARIABLES QUE NECESITA EL TEMPLATE
            'precio_total_operacion': f'${precio_total:,.0f}',
            'monto_este_pago': f'${senia_pagada:,.0f}',  # La seña que se pagó
            'saldo_pendiente': f'${saldo_restante:,.0f}',  # Saldo restante después de la seña
            'deposito_garantia': f'${deposito_pagado:,.0f}',  # Depósito de garantía
            'deposito_estado': deposito_estado,  # Estado del depósito
        })
        
    except Exception as e:
        messages.error(request, f'Error al generar el recibo: {str(e)}')
        return redirect('inmobiliaria:finalizar_reserva', reserva_id=reserva_id)

def generar_recibo_pdf(reserva, pago_senia):
    from datetime import datetime
    
    # Preparar datos para el recibo (similar a ver_recibo)
    fecha_actual = timezone.now()
    
    # Obtener los pagos de la reserva
    pagos = []
    total_pagado = 0
    formas_de_pago = []
    
    # Buscar si hay conceptos detallados de la operación
    from .models import Registro
    conceptos_operacion = None
    
    # Intentar encontrar registros relacionados usando número de recibo o ID de reserva
    try:
        # Buscar por número de recibo si existe un movimiento reciente
        if hasattr(reserva, 'movimiento_reciente') and reserva.movimiento_reciente:
            conceptos_operacion = Registro.objects.filter(
                interno_caja=reserva.movimiento_reciente.numero_liquidacion
            ).order_by('fecha')
    except:
        pass
    
    if conceptos_operacion and conceptos_operacion.exists():
        # Usar los conceptos de la operación
        for registro in conceptos_operacion:
            concepto_desc = ''
            if registro.concepto:
                concepto_desc = f'{registro.concepto.id} - {registro.concepto.nombre}'
            else:
                concepto_desc = 'Concepto no especificado'
            
            pagos.append({
                'fecha': registro.fecha_comprobante.strftime('%d/%m/%Y'),
                'codigo': registro.interno_caja or f'R{registro.id:04d}',
                'concepto': concepto_desc,
                'monto': f'${registro.liquidacion:,.0f}'
            })
            total_pagado += registro.liquidacion
    else:
        # Fallback: usar los pagos de la reserva como antes
        for pago in reserva.pagos.all():
            # Obtener el concepto correcto del pago
            concepto_desc = ''
            if hasattr(pago, 'concepto') and pago.concepto:
                concepto_desc = f'{pago.concepto.codigo} - {pago.concepto.nombre}'
            else:
                concepto_desc = f'Pago reserva {reserva.id}'
            
            pagos.append({
                'fecha': pago.fecha.strftime('%d/%m/%Y') if pago.fecha else '',
                'codigo': pago.codigo if hasattr(pago, 'codigo') and pago.codigo else f'P{pago.id:04d}',
                'concepto': concepto_desc,
                'monto': f'${pago.monto:,.0f}'  # Formatear como moneda
            })
            total_pagado += pago.monto
            if pago.forma_pago not in formas_de_pago:
                formas_de_pago.append(pago.forma_pago.title())
    
    # Función para convertir número a palabras
    def numero_a_palabras(numero):
        # Convertir número a palabras en español (versión simplificada)
        unidades = ['', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve']
        decenas = ['', '', 'veinte', 'treinta', 'cuarenta', 'cincuenta', 'sesenta', 'setenta', 'ochenta', 'noventa']
        centenas = ['', 'ciento', 'doscientos', 'trescientos', 'cuatrocientos', 'quinientos', 'seiscientos', 'setecientos', 'ochocientos', 'novecientos']
        
        numero = int(numero)
        if numero == 0:
            return "PESOS CERO CON 00/100"
        elif numero == 100:
            return "PESOS CIEN CON 00/100"
        elif numero < 10:
            return f"PESOS {unidades[numero].upper()} CON 00/100"
        elif numero < 100:
            if numero < 20:
                especiales = ['diez', 'once', 'doce', 'trece', 'catorce', 'quince', 'dieciséis', 'diecisiete', 'dieciocho', 'diecinueve']
                return f"PESOS {especiales[numero-10].upper()} CON 00/100"
            else:
                dec = numero // 10
                uni = numero % 10
                if uni == 0:
                    return f"PESOS {decenas[dec].upper()} CON 00/100"
                else:
                    return f"PESOS {decenas[dec].upper()} Y {unidades[uni].upper()} CON 00/100"
        elif numero < 1000:
            cent = numero // 100
            resto = numero % 100
            if resto == 0:
                return f"PESOS {centenas[cent].upper()} CON 00/100"
            else:
                palabras_resto = numero_a_palabras(resto).replace("PESOS ", "").replace(" CON 00/100", "")
                return f"PESOS {centenas[cent].upper()} {palabras_resto} CON 00/100"
        else:
            # Para números mayores, usar formato simple
            return f"PESOS {numero:,} CON 00/100".replace(',', '.')
    
    # Preparar datos del cliente con campos adicionales
    cliente_data = reserva.cliente
    cliente_completo = {
        'nombre_completo': f"{cliente_data.nombre} {cliente_data.apellido}",
        'domicilio': cliente_data.domicilio or '',
        'localidad': cliente_data.localidad or '',
        'provincia': cliente_data.provincia or '',
        'dni': cliente_data.dni or '',
        'telefono': cliente_data.celular or '',  # Mapear celular a telefono
        'cuit': getattr(cliente_data, 'cuit', '') or '',  # CUIT puede no existir
    }
    
    # Preparar datos de la propiedad con formato correcto
    propiedad_data = reserva.propiedad
    propiedad_completa = {
        'direccion': propiedad_data.direccion or '',
        'id': propiedad_data.id,
        'llave': propiedad_data.llave or 'N/A',
        'piso': propiedad_data.piso or '',
        'departamento': propiedad_data.departamento or '',
        'ambientes': f"{propiedad_data.ambientes} personas" if propiedad_data.ambientes else 'N/A',
        'wifi': 'SÍ' if propiedad_data.wifi else 'NO',
        'cochera': 'SÍ' if propiedad_data.cochera else 'NO',
    }
    
    # Preparar datos de la reserva con formato de moneda
    reserva_formateada = {
        'id': reserva.id,
        'precio_total': f'${reserva.precio_total:,.0f}',
        'senia': f'${reserva.senia:,.0f}',
        'cuota_pendiente': f'${reserva.cuota_pendiente:,.0f}',
        'deposito_garantia': f'${reserva.deposito_garantia:,.0f}',
        'propiedad': propiedad_completa,
    }
    
    template_name = 'inmobiliaria/reserva/recibo.html'
    context = {
        'reserva': reserva_formateada,
        'cliente': cliente_completo,
        'propiedad': propiedad_completa,
        'numero_recibo': f'R{reserva.id:06d}',
        'fecha': fecha_actual.strftime('%d/%m/%Y'),
        'hora': fecha_actual.strftime('%H:%M'),
        'fecha_inicio': reserva.fecha_inicio.strftime('%d/%m/%Y'),
        'fecha_fin': reserva.fecha_fin.strftime('%d/%m/%Y'),
        'descripcion': 'Alquiler temporario por días',
        'pagos': pagos,
        'total_pagado': f'${total_pagado:,.0f}',
        'monto_en_palabras': numero_a_palabras(total_pagado),
        'formas_de_pago': ', '.join(formas_de_pago) if formas_de_pago else 'EFECTIVO',
    }
    
    # Renderizar HTML a string
    html = render_to_string(template_name, context)
    
    # Crear el PDF
    pdf_buffer = BytesIO()
    pisa_status = pisa.CreatePDF(BytesIO(html.encode("UTF-8")), dest=pdf_buffer)
    
    if pisa_status.err:
        return None
    else:
        return pdf_buffer.getvalue()
def realizar_pago(request, reserva_id):
    # Obtener la reserva a partir del ID
    reserva = get_object_or_404(Reserva, id=reserva_id)

    if request.method == 'POST':
        # Obtener el monto del pago ingresado en el formulario
        pago = Decimal(request.POST.get('pago', '0.00'))

        if pago <= 0:
            messages.error(request, 'El monto del pago debe ser mayor que cero.')
            return redirect('inmobiliaria:finalizar_reserva', reserva_id=reserva.id)

        # Actualizar la seña y la cuota pendiente
        reserva.senia += pago

        # Calcular la cuota pendiente
        reserva.cuota_pendiente = reserva.precio_total - reserva.senia

        if reserva.cuota_pendiente <= 0:
            # Si la cuota pendiente es 0 o menor, marcar la reserva como 'realizada'
            reserva.estado = 'realizada'
            reserva.cuota_pendiente = 0  # Asegurarse de que no quede negativo
            messages.success(request, 'La reserva ha sido completada y está totalmente pagada.')
        else:
            # Si queda saldo pendiente, mostrar el saldo restante
            messages.info(request, f'Pago recibido. Saldo pendiente: {reserva.cuota_pendiente:.2f} USD.')

        # Guardar los cambios en la reserva
        reserva.save()

        # Redirigir al listado de reservas o a alguna página de confirmación
        return redirect('inmobiliaria:reservas')

    # Si es una solicitud GET, mostrar la página de finalizar reserva
    return render(request, 'inmobiliaria/reserva/finalizar_reserva.html', {'reserva': reserva})

PrecioFormSet = inlineformset_factory(
    Propiedad,  # Modelo padre
    Precio,     # Modelo hijo (relacionado con Propiedad)
    fields=['tipo_precio', 'precio_total', 'precio_por_dia'],  # Campos que gestionamos
    extra=1,  # Formularios adicionales vacíos
    can_delete=True  # Para permitir la eliminación de precios
)
def gestionar_precios(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    precios = Precio.objects.filter(propiedad=propiedad)
    
    # Obtener el vendedor directamente
    vendedor = request.user
    
    # Definir campos según el nivel del vendedor
    fields = [
        'tipo_precio',
        'precio_por_dia',
        'precio_total',
        'ajuste_porcentaje'
    ]
    
    # Agregar campos adicionales si el nivel es mayor a 2
    if vendedor.nivel > 2:
        fields.extend(['precio_toma', 'precio_dia_toma'])
    
    PrecioFormSet = modelformset_factory(
        Precio, 
        form=PrecioForm, 
        fields=fields,
        extra=0
    )
    
    # Si la propiedad no tiene precios, crearlos TODOS
    if not precios.exists():
        print("Creando precios iniciales para la propiedad")
        for tipo_choice in TipoPrecio.choices:
            tipo_key = tipo_choice[0]
            Precio.objects.create(
                propiedad=propiedad,
                tipo_precio=tipo_key,
                precio_por_dia=0,
                precio_total=0,
                precio_toma=0 if vendedor.nivel > 2 else None,
                precio_dia_toma=0 if vendedor.nivel > 2 else None,
                ajuste_porcentaje=0
            )
        precios = Precio.objects.filter(propiedad=propiedad)
        print(f"Precios creados: {precios.count()}")

    if request.method == 'POST':
        formset = PrecioFormSet(request.POST, queryset=precios)
        if formset.is_valid():
            instances = formset.save(commit=False)
            for instance in instances:
                instance.propiedad = propiedad
                instance.save()
            messages.success(request, 'Precios actualizados correctamente.')
            return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad_id)
    else:
        formset = PrecioFormSet(queryset=precios)

    return render(request, 'inmobiliaria/propiedades/gestionar_precios.html', {
        'propiedad': propiedad,
        'formset': formset,
        'nivel_vendedor': vendedor.nivel
    })

def historial_reservas_vendedor(request, vendedor_id):
    reservas = Reserva.objects.filter(vendedor_id=vendedor_id)

    return render(request, 'inmobiliaria/vendedores/historial.html', {
        'reservas': reservas,
    })
def historial_reservas_inquilino(request, inquilino_id):
    reservas = Reserva.objects.filter(cliente_id=inquilino_id)

    return render(request, 'inmobiliaria/inquilinos/historial.html', {
        'reservas': reservas,
    })    
def buscar_propietarios(request):
    """
    Devuelve los propietarios en formato Select2:
    {
        "results": [{"id": 1, "text": "Pérez, Ana – 30123456"}, ...],
        "pagination": {"more": true}
    }
    """
    term = request.GET.get("term", "").strip()
    page = int(request.GET.get("page", 1) or 1)
    page_size = 20
    offset = (page - 1) * page_size

    qs = Propietario.objects.all()

    if term:
        qs = qs.filter(
            Q(nombre__icontains=term) |
            Q(apellido__icontains=term) |
            Q(dni__icontains=term)
        )

    total = qs.count()
    propietarios = qs.order_by("apellido", "nombre")[offset: offset + page_size]

    results = [
        {
            "id": p.id,
            "text": f"{p.apellido}, {p.nombre} – {p.dni}"
        }
        for p in propietarios
    ]

    return JsonResponse(
        {"results": results, "pagination": {"more": total > offset + page_size}}
    )

@login_required
def buscar_operacion(request):
    """Vista para buscar operación por número y autocompletar campos"""
    operacion = request.GET.get('operacion', '')
    
    if not operacion:
        return JsonResponse({'success': False, 'message': 'Número de operación requerido'})
    
    try:
        # Buscar el movimiento por número (ajusta esto según tu modelo)
        movimiento = Movimiento.objects.get(numero=operacion)
        
        # Preparar datos para autocompletar
        return JsonResponse({
            'success': True,
            'concepto_id': movimiento.concepto_id,
            'cuenta_id': movimiento.cuenta_id if movimiento.cuenta else None,
            'productor_id': movimiento.productor_id if hasattr(movimiento, 'productor') else None,
            'monto': str(movimiento.monto),
            'tipo_comprobante': movimiento.tipo_comprobante if hasattr(movimiento, 'tipo_comprobante') else None
        })
    except Movimiento.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Operación no encontrada'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

def buscar_inquilinos(request):
    query = request.GET.get('term', '')
    inquilinos = Inquilino.objects.filter(
        Q(nombre__icontains=query) | 
        Q(apellido__icontains=query) |
        Q(dni__icontains=query)
    )[:10]
    
    results = []
    for inquilino in inquilinos:
        results.append({
            'id': inquilino.id,
            'text': f"{inquilino.nombre} {inquilino.apellido} (DNI: {inquilino.dni})"
        })
    
    return JsonResponse({
        'results': results,
        'pagination': {
            'more': False
        }
    })
def propietario_nuevo_ajax(request):
    if request.method == "POST" and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        form = PropietarioForm(request.POST)
        if form.is_valid():
            propietario = form.save()
            return JsonResponse({
                'success': True,
                'id': propietario.id,
                'nombre': propietario.nombre,
                'apellido': propietario.apellido,
                'dni': propietario.dni
            })
        else:
            return JsonResponse({'success': False, 'errors': form.errors})
    return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)
    
def propiedades_por_propietario(request, propietario_id):
    propietario = get_object_or_404(Propietario, pk=propietario_id)
    propiedades = Propiedad.objects.filter(propietario=propietario)
    return render(request, 'inmobiliaria/propietarios/propiedades_propietario.html', {
        'propietario': propietario,
        'propiedades': propiedades
    })
def autenticacion_vendedor(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        reserva_id = request.POST.get('reserva_id')  # Obtener el reserva_id
        
        # Autenticar al usuario
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Autenticación exitosa
            # Aquí puedes procesar la reserva usando el reserva_id si es necesario
            return JsonResponse({'success': True, 'reserva_id': reserva_id})
        else:
            return JsonResponse({'success': False})
    return JsonResponse({'error': 'Método no permitido'}, status=405)

@login_required
def autenticar_seguridad(request):
    """
    Vista para autenticación de seguridad antes de operaciones sensibles
    """
    if request.method == 'POST':
        usuario = request.POST.get('usuario', '').strip()
        contrasena = request.POST.get('contrasena', '')
        
        print(f"🔐 AUTENTICACIÓN SEGURIDAD - Usuario: {usuario}")
        
        if not usuario or not contrasena:
            return JsonResponse({
                'success': False, 
                'error': 'Por favor completa todos los campos'
            })
        
        # Autenticar al usuario
        user = authenticate(request, username=usuario, password=contrasena)
        
        if user is not None:
            # Verificar que el usuario esté activo
            if not user.is_active:
                print(f"❌ Usuario {usuario} no está activo")
                return JsonResponse({
                    'success': False, 
                    'error': 'Tu cuenta no está activa. Contacta al administrador.'
                })
            
            # Verificar que sea un vendedor con permisos adecuados
            try:
                vendedor = user  # El user ya es un Vendedor debido al modelo personalizado
                
                # Verificar nivel mínimo (nivel 1 o superior para operaciones - permitir usuarios básicos)
                if vendedor.nivel < 1:
                    print(f"❌ Usuario {usuario} sin permisos suficientes (nivel: {vendedor.nivel})")
                    return JsonResponse({
                        'success': False, 
                        'error': 'No tienes permisos suficientes para esta operación'
                    })
                
                print(f"✅ Autenticación exitosa - Usuario: {usuario}, Nivel: {vendedor.nivel}")
                return JsonResponse({
                    'success': True,
                    'usuario': vendedor.nombre_completo_vendedor(),
                    'nivel': vendedor.nivel
                })
                
            except Exception as e:
                print(f"❌ Error verificando vendedor: {e}")
                return JsonResponse({
                    'success': False, 
                    'error': 'Error interno. Contacta al administrador.'
                })
            
        else:
            print(f"❌ Credenciales incorrectas para usuario: {usuario}")
            return JsonResponse({
                'success': False, 
                'error': 'Usuario o contraseña incorrectos'
            })
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)

def buscar_clientes(request):
    term = request.GET.get('term', '')
    clientes = Inquilino.objects.filter(
        Q(nombre__icontains=term) | 
        Q(apellido__icontains=term) | 
        Q(dni__icontains=term)
    )[:10]
    results = [{'id': c.id, 'text': f"{c.nombre} {c.apellido} (DNI: {c.dni})"} for c in clientes]
    return JsonResponse({'results': results})

@login_required
def crear_concepto_ajax(request):
    """
    Vista AJAX para crear nuevos conceptos desde el modal
    """
    if request.method == 'POST':
        try:
            id_personalizado = request.POST.get('id', '').strip()
            nombre = request.POST.get('nombre', '').strip()
            
            if not nombre:
                return JsonResponse({
                    'success': False,
                    'error': 'El nombre del concepto es requerido'
                })
            
            # Verificar si el concepto ya existe por nombre
            if Concepto.objects.filter(nombre__iexact=nombre).exists():
                return JsonResponse({
                    'success': False,
                    'error': 'Ya existe un concepto con ese nombre'
                })
            
            # Si se proporciona un ID personalizado
            if id_personalizado:
                try:
                    id_num = int(id_personalizado)
                    if Concepto.objects.filter(id=id_num).exists():
                        return JsonResponse({
                            'success': False,
                            'error': f'Ya existe un concepto con el ID {id_num}'
                        })
                    
                    # Crear concepto con ID específico
                    concepto = Concepto(id=id_num, nombre=nombre)
                    concepto.save()
                except ValueError:
                    return JsonResponse({
                        'success': False,
                        'error': 'El ID debe ser un número válido'
                    })
            else:
                # Crear concepto con ID automático
                concepto = Concepto.objects.create(nombre=nombre)
            
            return JsonResponse({
                'success': True,
                'concepto': {
                    'id': concepto.id,
                    'nombre': concepto.nombre
                }
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    
    return JsonResponse({'success': False, 'error': 'Método no permitido'})

@login_required
@transaction.atomic
def procesar_movimiento_reserva(request):
    """
    Vista para procesar el movimiento de caja completo y cambiar estado de reserva
    """
    print(f"Usuario autenticado: {request.user.is_authenticated}")
    print(f"Método de request: {request.method}")
    print(f"Headers: {dict(request.headers)}")
    
    if request.method == 'POST':
        try:
            print("=== INICIANDO PROCESAMIENTO DE MOVIMIENTO ===")
            reserva_id = request.POST.get('reserva_id')
            print(f"Reserva ID recibido: {reserva_id}")
            print(f"Todos los datos POST: {dict(request.POST)}")
            
            if not reserva_id:
                return JsonResponse({'success': False, 'error': 'ID de reserva requerido'})
            
            # Obtener la reserva
            reserva = get_object_or_404(Reserva, id=reserva_id, sucursal=request.user.sucursal)
            
            # Obtener la caja actual
            caja_actual = Caja.objects.filter(
                sucursal=request.user.sucursal,
                estado='abierta'
            ).first()
            
            if not caja_actual:
                return JsonResponse({'success': False, 'error': 'No hay una caja abierta'})
            
            # Obtener datos del formulario
            numero_recibo = request.POST.get('numero_recibo', '').strip()
            
            # ✅ Función para limpiar valores monetarios
            def limpiar_valor_monetario(valor_str):
                if not valor_str:
                    return '0'
                # Remover puntos de miles y espacios
                return str(valor_str).replace('.', '').replace(' ', '').replace(',', '.')
            
            # Formas de pago (limpiar antes de convertir a Decimal)
            monto_efectivo = Decimal(limpiar_valor_monetario(request.POST.get('monto_efectivo', '0')))
            monto_cheque = Decimal(limpiar_valor_monetario(request.POST.get('monto_cheque', '0')))
            monto_tarjeta = Decimal(limpiar_valor_monetario(request.POST.get('monto_tarjeta', '0')))
            
            # Transferencias separadas
            monto_deposito_galicia = Decimal(limpiar_valor_monetario(request.POST.get('monto_deposito_galicia', '0')))
            monto_deposito_mp = Decimal(limpiar_valor_monetario(request.POST.get('monto_deposito_mp', '0')))
            monto_deposito = monto_deposito_galicia + monto_deposito_mp
            
            print(f"=== VALORES RAW RECIBIDOS ===")
            print(f"monto_efectivo RAW: '{request.POST.get('monto_efectivo', '0')}'")
            print(f"monto_deposito_galicia RAW: '{request.POST.get('monto_deposito_galicia', '0')}'")
            print(f"monto_deposito_mp RAW: '{request.POST.get('monto_deposito_mp', '0')}'")
            
            print(f"=== VALORES CONVERTIDOS A DECIMAL ===")
            print(f"Montos recibidos - Efectivo: {monto_efectivo}, Cheque: {monto_cheque}, Tarjeta: {monto_tarjeta}")
            print(f"Transferencias - Galicia: {monto_deposito_galicia}, MP: {monto_deposito_mp}, Total: {monto_deposito}")
            print(f"TOTAL A CREAR EN MOVIMIENTOS: {monto_efectivo + monto_cheque + monto_tarjeta + monto_deposito}")
            
            # Datos adicionales
            banco = request.POST.get('banco', '').strip()
            nro_cheque = request.POST.get('nro_cheque', '').strip()
            numero_tarjeta = request.POST.get('numero_tarjeta', '').strip()
            destino_transferencia = request.POST.get('destino_transferencia', '').strip()
            observaciones_generales = request.POST.get('observaciones_generales', '').strip()
            
            # Preparar datos del movimiento
            movimiento_data = {
                'caja': caja_actual,
                'sucursal': request.user.sucursal,
                'tipo': TipoMovimientoCajaEnum.INGRESO,
                'concepto': f"Operaci\u00f3n {reserva.id} - {reserva.propiedad.direccion}",
                'propiedad': reserva.propiedad,
                'fecha_desde': reserva.fecha_inicio,
                'fecha_hasta': reserva.fecha_fin,
                'monto_efectivo': monto_efectivo,
                'monto_cheque': monto_cheque,
                'monto_tarjeta': monto_tarjeta,
                'monto_deposito': monto_deposito,
                'numero_liquidacion': numero_recibo,
                'empleado': request.user
            }
            
            # ✅ PROCESAR CONCEPTOS INDIVIDUALES DEL FRONTEND
            conceptos_count = int(request.POST.get('conceptos_count', 0))
            conceptos_detalle = []
            conceptos_completos = []  # Para guardar información completa
            
            # ✅ VARIABLES PARA VALIDAR CONCEPTO 10 (DEPÓSITO)
            concepto_10_presente = False
            concepto_10_importe = Decimal('0')
            total_conceptos = Decimal('0')
            
            for i in range(conceptos_count):
                concepto_id = request.POST.get(f'concepto_{i}_id')
                concepto_nombre = request.POST.get(f'concepto_{i}_nombre')
                concepto_observaciones = request.POST.get(f'concepto_{i}_observaciones')
                concepto_importe = request.POST.get(f'concepto_{i}_importe')
                
                if concepto_nombre:
                    conceptos_detalle.append(f"{concepto_nombre}")
                    
                    # ✅ DETECTAR CONCEPTO 10 (DEPÓSITO)
                    if concepto_id == '10':
                        concepto_10_presente = True
                        concepto_10_importe = Decimal(limpiar_valor_monetario(concepto_importe or '0'))
                        print(f"🏦 CONCEPTO 10 (DEPÓSITO) DETECTADO: ${concepto_10_importe}")
                    
                    # ✅ SUMAR AL TOTAL DE CONCEPTOS
                    importe_limpio = Decimal(limpiar_valor_monetario(concepto_importe or '0'))
                    total_conceptos += importe_limpio
                    
                    # Guardar información completa del concepto
                    conceptos_completos.append({
                        'id': concepto_id or f'C{i+1:02d}',
                        'nombre': concepto_nombre,
                        'importe': concepto_importe or '0'
                    })
                    print(f"💰 CONCEPTO {i}: ID={concepto_id}, {concepto_nombre} - ${concepto_importe}")
            
            # Construir concepto detallado con los conceptos individuales
            if conceptos_detalle:
                concepto_detallado = f"Operaci\u00f3n {reserva.id} - " + " + ".join(conceptos_detalle)
                
                # Agregar información estructurada al final para parsing posterior
                # Formato: |CONCEPTOS:id1:nombre1:importe1|id2:nombre2:importe2|
                if conceptos_completos:
                    conceptos_info = "|CONCEPTOS:"
                    for concepto in conceptos_completos:
                        conceptos_info += f"{concepto['id']}:{concepto['nombre']}:{concepto['importe']}|"
                    concepto_detallado += conceptos_info
            else:
                concepto_detallado = f"Operaci\u00f3n {reserva.id} - {reserva.propiedad.direccion}"
            
            print(f"📝 CONCEPTO FINAL: {concepto_detallado}")
            
            # Crear movimiento principal con concepto detallado
            movimiento_principal = MovimientoCaja.objects.create(
                caja=caja_actual,
                sucursal=request.user.sucursal,
                tipo=TipoMovimientoCajaEnum.INGRESO,
                concepto=concepto_detallado,  # ✅ Usar concepto con detalles
                propiedad=reserva.propiedad,
                fecha_desde=reserva.fecha_inicio,
                fecha_hasta=reserva.fecha_fin,
                monto_efectivo=monto_efectivo,
                monto_cheque=monto_cheque,
                monto_tarjeta=monto_tarjeta,
                monto_deposito=monto_deposito,
                numero_liquidacion=numero_recibo,
                empleado=request.user
            )
            
            # Crear movimientos separados para transferencias si existen
            movimientos_creados = [movimiento_principal]
            
            # ✅ ASIGNAR DESTINO DE TRANSFERENCIA AL MOVIMIENTO PRINCIPAL
            if monto_deposito_galicia > 0 and monto_deposito_mp == 0:
                # Solo Galicia
                movimiento_principal.destino_deposito = 'galicia'
                movimiento_principal.save()
            elif monto_deposito_mp > 0 and monto_deposito_galicia == 0:
                # Solo Mercado Pago
                movimiento_principal.destino_deposito = 'mp'
                movimiento_principal.save()
            elif monto_deposito_galicia > 0 and monto_deposito_mp > 0:
                # Ambos: dejar como "mixto" o crear nota en concepto
                concepto_actualizado = f"Operaci\u00f3n {reserva.id} - Galicia: ${monto_deposito_galicia}, MP: ${monto_deposito_mp}"
                movimiento_principal.concepto = concepto_actualizado
                movimiento_principal.save()
            
            print(f"✅ MOVIMIENTO ÚNICO CREADO - ID: {movimiento_principal.id}, Total: ${monto_efectivo + monto_cheque + monto_tarjeta + monto_deposito}")
            
            # Usar el movimiento principal para la respuesta
            movimiento = movimiento_principal
            
            # ✅ OBTENER VALORES DIRECTOS DEL FORMULARIO (SEÑA Y DEPÓSITO)
            senia_input = limpiar_valor_monetario(request.POST.get('senia', '0'))
            deposito_garantia_input = limpiar_valor_monetario(request.POST.get('deposito_garantia', '0'))
            importe_locacion_input = limpiar_valor_monetario(request.POST.get('importe_locacion', '0'))
            
            # ✅ CALCULAR TOTALES PAGADOS ANTES DE ESTE PAGO
            pagos_anteriores = MovimientoCaja.objects.filter(
                propiedad=reserva.propiedad,
                tipo=TipoMovimientoCajaEnum.INGRESO,
                concepto__icontains=f"Operaci\u00f3n {reserva.id}"
            )
            
            total_pagado_anteriormente = sum(
                mov.monto_efectivo + mov.monto_cheque + mov.monto_tarjeta + mov.monto_deposito
                for mov in pagos_anteriores
            )
            
            # 🔍 DEBUGGING CRÍTICO: Ver qué llega del formulario
            print(f"🔥 VALORES CRUDOS DEL FORMULARIO:")
            print(f"   - request.POST.get('senia'): '{request.POST.get('senia', 'NO_ENVIADO')}'")
            print(f"   - request.POST.get('deposito_garantia'): '{request.POST.get('deposito_garantia', 'NO_ENVIADO')}'")
            print(f"   - request.POST.get('importe_locacion'): '{request.POST.get('importe_locacion', 'NO_ENVIADO')}'")
            print(f"   - senia_input (limpiado): '{senia_input}'")
            print(f"   - deposito_garantia_input (limpiado): '{deposito_garantia_input}'")
            print(f"   - importe_locacion_input (limpiado): '{importe_locacion_input}'")
            print(f"🔥 TODOS LOS CAMPOS DEL POST:")
            for key, value in request.POST.items():
                if 'csrf' not in key.lower():
                    print(f"   - {key}: '{value}'")
            
            try:
                senia = Decimal(senia_input) if senia_input else Decimal('0')
                deposito_garantia = Decimal(deposito_garantia_input) if deposito_garantia_input else Decimal('0')
                importe_locacion = Decimal(importe_locacion_input) if importe_locacion_input else Decimal('0')
                
                # ✅ VALIDACIÓN CONCEPTO 10 vs DEPÓSITO DE GARANTÍA (después de definir variables)
                if deposito_garantia > 0 and not concepto_10_presente:
                    print(f"⚠️  ADVERTENCIA: Se indicó depósito de ${deposito_garantia} pero no se cargó el concepto 10")
                    print(f"   El depósito NO será considerado como pagado hasta que se cargue el concepto 10")
                elif concepto_10_presente and concepto_10_importe != deposito_garantia:
                    print(f"⚠️  ADVERTENCIA: Concepto 10 (${concepto_10_importe}) no coincide con depósito de garantía (${deposito_garantia})")
                    print(f"   Se usará el monto del concepto 10 como depósito realmente pagado")
                    # Actualizar el depósito para que coincida con el concepto 10
                    deposito_garantia = concepto_10_importe
                
                # 🔄 NUEVA LÓGICA: No validar conceptos vs seña+depósito
                # Los conceptos pueden ser diferentes a la seña (ej: gastos bancarios extras)
                # Solo validamos que formas de pago = total conceptos (se hace más abajo)
                print(f"✅ NUEVA VALIDACIÓN: Total conceptos: ${total_conceptos}, Seña del campo: ${senia}")
                print(f"   Los conceptos pueden incluir extras como gastos bancarios")
                print(f"   Validación principal: formas de pago = total conceptos")
                
                # ✅ CORREGIDO: MONTO DE ESTE PAGO debe ser la SEÑA DEL CASILLERO, no el total pagado
                monto_total_pagado = monto_efectivo + monto_cheque + monto_tarjeta + monto_deposito
                
                # ✅ NUEVO: monto_este_pago siempre es la seña final del casillero (no el total de este movimiento)
                monto_este_pago = senia  # Usar la seña del casillero
                monto_seña_este_pago = senia  # La seña siempre es la del casillero
                
                print(f"✅ VALORES DIRECTOS DEL FORMULARIO:")
                print(f"   - Seña nueva a agregar: ${senia}")
                print(f"   - Depósito nuevo a agregar: ${deposito_garantia}")
                print(f"   - Importe Locación TOTAL: ${importe_locacion}")
                print(f"   - Monto total pagado: ${monto_total_pagado}")
                print(f"   - Monto para seña: ${monto_seña_este_pago}")
                print(f"   - Total pagado anteriormente: ${total_pagado_anteriormente}")
                print(f"   - Seña anterior en reserva: ${reserva.senia or 0}")
                print(f"   - Depósito anterior en reserva: ${reserva.deposito_garantia or 0}")
                
                # ✅ ACTUALIZAR PRECIO TOTAL SI SE PROPORCIONA IMPORTE LOCACIÓN
                if importe_locacion > 0 and importe_locacion != reserva.precio_total:
                    print(f"🔄 ACTUALIZANDO PRECIO TOTAL: ${reserva.precio_total} -> ${importe_locacion}")
                    reserva.precio_total = importe_locacion
                
                # ✅ CORREGIDO: USAR DIRECTAMENTE EL VALOR DEL CASILLERO SEÑA (no acumulativo)
                # La seña del casillero ya es el valor total final que se quiere
                senia_anterior = reserva.senia or 0
                reserva.senia = senia  # Usar directamente el valor del casillero
                
                print(f"🔧 CORRECCIÓN SEÑA:")
                print(f"   - Seña anterior: ${senia_anterior}")
                print(f"   - Seña del casillero: ${senia}")
                print(f"   - Nueva seña total: ${reserva.senia}")
                
                # ✅ ACTUALIZAR DEPÓSITO (siempre se guarda, pero solo se marca como pagado con concepto 10)
                if deposito_garantia > 0:
                    # Siempre guardar el depósito que se indica en el casillero
                    reserva.deposito_garantia = deposito_garantia
                    
                    if concepto_10_presente:
                        print(f"💳 DEPÓSITO PAGADO: ${deposito_garantia} (confirmado por concepto 10)")
                    else:
                        print(f"💰 DEPÓSITO REGISTRADO: ${deposito_garantia} (PENDIENTE - falta concepto 10 para pagar)")
                else:
                    print(f"ℹ️  Sin depósito en este pago")
                
                # ✅ CALCULAR SALDO PENDIENTE (precio total - solo seña)
                saldo_pendiente = reserva.precio_total - reserva.senia
                
                print(f"🔥 CÁLCULOS FINALES:")
                print(f"   - Precio Total: ${reserva.precio_total}")
                print(f"   - Total Pagado (seña): ${reserva.senia}")
                print(f"   - Depósito: ${reserva.deposito_garantia}")
                print(f"   - Saldo Pendiente: ${saldo_pendiente}")
                
                reserva.save()
                
                # ✅ ACTUALIZAR HISTORIAL: Cambiar estado de "Reservado" a "Operación" si hay seña
                print(f"🔄 ACTUALIZANDO HISTORIAL después del pago...")
                reserva.actualizar_historial_disponibilidad()
                print(f"✅ HISTORIAL ACTUALIZADO - Estado debería ser 'Operación'")
                
                # ✅ CREAR RECIBO PARA ESTE PAGO
                from .models.recibo import Recibo
                # ✅ NUMERACIÓN AUTOMÁTICA DE RECIBOS POR SUCURSAL
                sucursal = request.user.sucursal
                if sucursal.usar_numeracion_automatica and sucursal.prefijo_recibo:
                    numero_recibo = sucursal.generar_numero_recibo()
                    print(f"🧾 NÚMERO AUTOMÁTICO GENERADO: {numero_recibo}")
                else:
                    # Fallback al formato anterior si no hay numeración automática
                    numero_recibo = f"R{reserva.id:06d}-{len(pagos_anteriores) + 1:02d}"
                    print(f"🧾 NÚMERO MANUAL GENERADO: {numero_recibo}")
                
                recibo = Recibo.objects.create(
                    numero_recibo=numero_recibo,
                    movimiento_caja=movimiento,
                    reserva=reserva,
                    propiedad=reserva.propiedad,
                    empleado=request.user,
                    precio_total_operacion=reserva.precio_total,
                    monto_este_pago=monto_este_pago,
                    total_pagado_antes=senia_anterior,  # ✅ CORREGIDO: usar seña anterior, no total calculado mal
                    saldo_pendiente=saldo_pendiente,
                    conceptos_detalle={
                        'conceptos': conceptos_completos,
                        'fecha_pago': timezone.now().strftime('%Y-%m-%d'),
                        'formas_pago': {
                            'efectivo': float(monto_efectivo),
                            'cheque': float(monto_cheque),
                            'tarjeta': float(monto_tarjeta),
                            'deposito': float(monto_deposito)
                        }
                    }
                )
                
                print(f"✅ RECIBO CREADO: {numero_recibo}")
                
            except (ValueError, TypeError) as e:
                print(f"❌ Error al convertir valores: {e}")
                # Si hay error en la conversión, usar valores por defecto
                reserva.senia = Decimal('0')
                deposito_garantia = Decimal('0')
                
            # Cambiar estado de la reserva
            reserva.estado = 'pagada'
            reserva.save()
            
            # Cambiar estado de la propiedad (opcional - depende de tu lógica de negocio)
            # reserva.propiedad.estado = 'reservada'
            # reserva.propiedad.save()
            
            print(f"=== MOVIMIENTO CREADO EXITOSAMENTE - ID: {movimiento.id} ===")
            
            return JsonResponse({
                'success': True,
                'movimiento_id': movimiento.id,
                'redirect_url': reverse('inmobiliaria:ver_recibo_movimiento', args=[movimiento.id])
            })
            
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            print(f"Error en procesar_movimiento_reserva: {str(e)}")
            print(f"Traceback: {error_traceback}")
            return JsonResponse({
                'success': False, 
                'error': str(e),
                'debug_info': error_traceback if settings.DEBUG else None
            })
    
    return JsonResponse({'success': False, 'error': 'Método no permitido'})

@login_required
def test_json_response(request):
    """Vista de prueba para verificar que JSON funciona"""
    return JsonResponse({'success': True, 'message': 'Test OK', 'user': str(request.user)})

@login_required
def api_propiedad_detalle(request, propiedad_id):
    """API para obtener detalles de una propiedad"""
    try:
        # Intentar obtener la propiedad de la sucursal del usuario
        try:
            propiedad = Propiedad.objects.get(id=propiedad_id, sucursal=request.user.sucursal)
        except Propiedad.DoesNotExist:
            # Si no está en la sucursal del usuario, buscar en cualquier sucursal
            propiedad = get_object_or_404(Propiedad, id=propiedad_id)
            print(f"⚠️ Propiedad {propiedad_id} encontrada en sucursal {propiedad.sucursal.nombre}, no en {request.user.sucursal.nombre}")
        
        print(f"🏠 API Propiedad {propiedad_id}:")
        print(f"   Ambientes: {propiedad.ambientes}")
        print(f"   Descripcion: {propiedad.descripcion}")
        print(f"   Caracteristicas: {propiedad.caracteristicas}")
        print(f"   Estado: {propiedad.estado}")
        
        # Obtener precios de la propiedad
        precios = PrecioPropiedad.objects.filter(propiedad=propiedad).order_by('fecha_desde')
        precios_data = []
        
        for precio in precios:
            periodo = f"{precio.fecha_desde.strftime('%d/%m/%Y')} - {precio.fecha_hasta.strftime('%d/%m/%Y')}"
            precios_data.append({
                'periodo': periodo,
                'precio_total': float(precio.precio_total),
                'precio_por_dia': float(precio.precio_por_dia)
            })
        
        # Obtener información de alquiler 24 meses si existe
        info_meses = None
        try:
            from .models import AlquilerMeses
            info_meses = AlquilerMeses.objects.get(propiedad=propiedad)
            info_meses_data = {
                'precio_mensual': float(info_meses.precio_mensual),
                'precio_expensas': float(info_meses.precio_expensas) if info_meses.precio_expensas else 0,
                'estado': info_meses.estado
            }
        except:
            info_meses_data = None
        
        data = {
            'id': propiedad.id,
            'direccion': propiedad.direccion,
            'sucursal': propiedad.sucursal.nombre,
            'ambientes': propiedad.ambientes,
            'descripcion': propiedad.descripcion or '',
            'caracteristicas': propiedad.caracteristicas or '',
            'estado': propiedad.estado,
            'precios': precios_data,
            'info_meses': info_meses_data
        }
        
        print(f"📤 Datos enviados: {data}")
        return JsonResponse(data)
        
    except Propiedad.DoesNotExist:
        print(f"❌ Propiedad {propiedad_id} no encontrada")
        return JsonResponse({
            'error': f'Propiedad {propiedad_id} no encontrada',
            'id': propiedad_id,
            'direccion': 'Propiedad no encontrada',
            'sucursal': 'N/A',
            'ambientes': 0,
            'descripcion': 'Propiedad no encontrada',
            'caracteristicas': 'Propiedad no encontrada',
            'estado': 'No encontrada',
            'precios': [],
            'info_meses': None
        }, status=404)
    except Exception as e:
        print(f"❌ Error en API propiedad: {str(e)}")
        return JsonResponse({
            'error': str(e),
            'id': propiedad_id,
            'direccion': 'Error al cargar',
            'sucursal': 'Error al cargar',
            'ambientes': 0,
            'descripcion': 'Error al cargar descripción',
            'caracteristicas': 'Error al cargar características',
            'estado': 'Error',
            'precios': [],
            'info_meses': None
        }, status=500)

def determinar_estado_deposito_completo(reserva):
    """
    Determina si el depósito fue pagado en CUALQUIER movimiento de la reserva.
    Revisa todos los movimientos de caja de la reserva para ver si alguno tiene concepto 10.
    """
    print(f"🔍 VERIFICANDO ESTADO DEPÓSITO GLOBAL - Reserva {reserva.id}")
    
    if not reserva or not reserva.deposito_garantia:
        print(f"❌ No hay depósito para verificar: reserva={reserva}, deposito={reserva.deposito_garantia if reserva else 'N/A'}")
        return 'no_aplica'  # No hay depósito
    
    # Buscar todos los movimientos de esta reserva
    todos_movimientos = MovimientoCaja.objects.filter(
        propiedad=reserva.propiedad,
        tipo=TipoMovimientoCajaEnum.INGRESO,
        concepto__icontains=f"Operaci\u00f3n {reserva.id}"
    )
    
    print(f"📋 MOVIMIENTOS ENCONTRADOS: {todos_movimientos.count()}")
    
    # Verificar si algún movimiento tiene concepto 10
    for i, movimiento in enumerate(todos_movimientos):
        print(f"🔍 Movimiento {i+1} (ID: {movimiento.id}): {movimiento.concepto[:100]}...")
        
        if movimiento.concepto and "|CONCEPTOS:" in movimiento.concepto:
            concepto_parts = movimiento.concepto.split("|CONCEPTOS:", 1)
            if len(concepto_parts) > 1:
                conceptos_data = concepto_parts[1]
                print(f"   📝 Conceptos data: {conceptos_data}")
                
                if "|10:" in conceptos_data:  # Concepto 10 presente
                    print(f"💳 DEPÓSITO GLOBAL PAGADO: Encontrado concepto 10 en movimiento {movimiento.id}")
                    return 'pagado'
                else:
                    print(f"   ❌ No encontrado concepto 10 en: {conceptos_data}")
            else:
                print(f"   ❌ No se pudo parsear conceptos estructurados")
        else:
            print(f"   ❌ Sin estructura |CONCEPTOS: o concepto vacío")
    
    print(f"⏳ DEPÓSITO GLOBAL PENDIENTE: No se encontró concepto 10 en ningún movimiento")
    return 'pendiente'

@login_required
def ver_recibo_movimiento(request, movimiento_id):
    """
    Vista para mostrar el recibo basado en un MovimientoCaja
    """
    print("🧾 EJECUTANDO ver_recibo_movimiento desde views.py (FUNCIÓN ACTUALIZADA)")
    print(f"🧾 Movimiento ID: {movimiento_id}")
    print("="*50)
    print("🔧 VERSIÓN ACTUALIZADA DE LA FUNCIÓN - DICIEMBRE 2024")
    print("="*50)
    try:
        # Obtener el movimiento de caja principal
        movimiento = get_object_or_404(MovimientoCaja, id=movimiento_id, sucursal=request.user.sucursal)
        
        # Obtener la reserva relacionada desde el concepto del movimiento
        reserva = None
        if movimiento.concepto and "Operaci\u00f3n" in movimiento.concepto:
            try:
                # Extraer el ID de la reserva del concepto (formato: "Operaci\u00f3n 123 - Dirección")
                import re
                match = re.search(r'Operaci\u00f3n (\d+)', movimiento.concepto)
                if match:
                    reserva_id = int(match.group(1))
                    reserva = Reserva.objects.filter(id=reserva_id).first()
                    print(f"🔍 RESERVA ENCONTRADA desde concepto: ID {reserva_id}, Estado: {reserva.estado if reserva else 'No encontrada'}")
                else:
                    print(f"⚠️ No se pudo extraer ID de reserva del concepto: '{movimiento.concepto}'")
            except Exception as e:
                print(f"❌ Error al buscar reserva desde concepto: {e}")
        
        # Fallback: buscar por propiedad si no se encontró por concepto
        if not reserva and movimiento.propiedad:
            reserva = movimiento.propiedad.reservas.filter(estado__in=['pagada', 'confirmada_no_pagada']).first()
            print(f"🔍 RESERVA FALLBACK desde propiedad: {reserva.id if reserva else 'No encontrada'}")
        
        # ✅ CORRECCIÓN: Buscar movimientos DE ESTA OPERACIÓN ESPECÍFICA (mismo número de recibo)
        movimientos_relacionados = MovimientoCaja.objects.filter(
            numero_liquidacion=movimiento.numero_liquidacion,
            propiedad=movimiento.propiedad,
            tipo=TipoMovimientoCajaEnum.INGRESO
        ).order_by('id')
        
        # ✅ USAR SOLO EL MOVIMIENTO PRINCIPAL (no sumar movimientos múltiples)
        total_efectivo = movimiento.monto_efectivo
        total_cheque = movimiento.monto_cheque
        total_tarjeta = movimiento.monto_tarjeta
        total_deposito = movimiento.monto_deposito
        
        # ✅ Para transferencias, extraer del concepto si hay ambas o usar destino_deposito
        total_deposito_galicia = 0
        total_deposito_mp = 0
        
        if movimiento.destino_deposito == 'galicia':
            total_deposito_galicia = movimiento.monto_deposito
        elif movimiento.destino_deposito == 'mp':
            total_deposito_mp = movimiento.monto_deposito
        elif 'Galicia:' in movimiento.concepto and 'MP:' in movimiento.concepto:
            # Extraer montos del concepto si están ambos
            import re
            galicia_match = re.search(r'Galicia: \$(\d+)', movimiento.concepto)
            mp_match = re.search(r'MP: \$(\d+)', movimiento.concepto)
            
            if galicia_match:
                total_deposito_galicia = int(galicia_match.group(1))
            if mp_match:
                total_deposito_mp = int(mp_match.group(1))
        else:
            # Si no hay destino específico, asumir que es todo en uno
            total_deposito_galicia = movimiento.monto_deposito
        
        total_movimiento = total_efectivo + total_cheque + total_tarjeta + total_deposito
        
        print(f"🧾 RECIBO ÚNICO - Movimiento ID: {movimiento.id}, Número: {movimiento.numero_liquidacion}")
        print(f"🧾 DESGLOSE - Efectivo: {total_efectivo}, Cheque: {total_cheque}, Tarjeta: {total_tarjeta}")
        print(f"🧾 TRANSFERENCIAS - Galicia: {total_deposito_galicia}, MP: {total_deposito_mp}, Total Depósitos: {total_deposito}")
        print(f"🧾 TOTAL OPERACIÓN: {total_movimiento} (debe coincidir con lo pagado)")
        
        # Calcular saldo pendiente si hay reserva
        saldo_pendiente = 0
        total_pagado_reserva = 0
        total_senia_pagada_recibo = 0  # ✅ Inicializar para evitar errores
        total_deposito_pagado_recibo = 0  # ✅ Inicializar para evitar errores
        precio_total_operacion = 0  # ✅ Inicializar para evitar errores
        concepto_10_en_recibo = False  # ✅ Inicializar estado del concepto 10
        if reserva:
            # Buscar todos los movimientos de esta reserva para calcular total pagado
            todos_movimientos = MovimientoCaja.objects.filter(
                propiedad=reserva.propiedad,
                tipo=TipoMovimientoCajaEnum.INGRESO,
                concepto__icontains=f"Operaci\u00f3n {reserva.id}"
            )
            
            print(f"🔍 BÚSQUEDA MOVIMIENTOS - Buscando concepto: 'Operaci\u00f3n {reserva.id}'")
            print(f"🔍 MOVIMIENTOS ENCONTRADOS: {todos_movimientos.count()}")
            for mov in todos_movimientos:
                print(f"🔍 Movimiento ID: {mov.id}, Concepto: '{mov.concepto}', Total: {mov.monto_efectivo + mov.monto_cheque + mov.monto_tarjeta + mov.monto_deposito}")
            
            # ✅ INTENTAR OBTENER EL RECIBO ASOCIADO A ESTE MOVIMIENTO
            recibo_obj = None
            try:
                from .models.recibo import Recibo
                recibo_obj = Recibo.objects.get(movimiento_caja=movimiento)
                print(f"🧾 RECIBO ENCONTRADO: {recibo_obj.numero_recibo}")
            except Recibo.DoesNotExist:
                print("⚠️ No se encontró recibo asociado a este movimiento")
            
            if recibo_obj:
                # ✅ USAR DATOS DEL RECIBO (MÁS PRECISOS)
                total_pagado_reserva = recibo_obj.total_pagado_antes + recibo_obj.monto_este_pago
                saldo_pendiente = recibo_obj.saldo_pendiente
                precio_total_operacion = recibo_obj.precio_total_operacion
                
                print(f"✅ USANDO DATOS DEL RECIBO:")
                print(f"   - Precio Total Operación: ${precio_total_operacion}")
                print(f"   - Monto Este Pago: ${recibo_obj.monto_este_pago}")
                print(f"   - Total Pagado Antes: ${recibo_obj.total_pagado_antes}")
                print(f"   - Total Pagado Ahora: ${total_pagado_reserva}")
                print(f"   - Saldo Pendiente: ${saldo_pendiente}")
                
            else:
                # ✅ SIMPLIFICADO: USAR DIRECTAMENTE VALORES DEL CASILLERO DE LA RESERVA
                total_senia_pagada_recibo = reserva.senia or 0
                total_deposito_pagado_recibo = reserva.deposito_garantia or 0
                precio_total_operacion = reserva.precio_total
                
                # Verificar si hay concepto 10 para el estado del depósito
                try:
                    import json
                    if movimiento.concepto and movimiento.concepto.startswith('['):
                        conceptos_data = json.loads(movimiento.concepto)
                        for concepto_data in conceptos_data:
                            concepto_id = str(concepto_data.get('id', ''))
                            if concepto_id == '10':  # Depósito
                                concepto_10_en_recibo = True
                                break
                except:
                    pass
                
                print(f"✅ USANDO VALORES DIRECTOS DE LA RESERVA:")
                print(f"   - Seña (reserva.senia): ${total_senia_pagada_recibo}")
                print(f"   - Depósito (reserva.deposito_garantia): ${total_deposito_pagado_recibo}")
                print(f"   - Concepto 10 presente: {concepto_10_en_recibo}")
            
            # ✅ CORREGIDO: Solo la seña cuenta para el total pagado (el depósito es aparte)
            total_pagado_reserva = total_senia_pagada_recibo
            
            # ✅ NUEVO CÁLCULO: El saldo pendiente es precio total - SOLO LA SEÑA (NO EL DEPÓSITO)
            saldo_pendiente = reserva.precio_total - total_senia_pagada_recibo
            
            print(f"💰 SALDO RECIBO - Precio Total: {reserva.precio_total}, Seña Pagada: {total_senia_pagada_recibo}, Depósito: {total_deposito_pagado_recibo}, Saldo Pendiente: {saldo_pendiente}")
        else:
            total_pagado_reserva = total_movimiento
        
        # Si encontramos una reserva, usar el nuevo diseño de recibo
        if reserva:
            # Usar el mismo código que la función ver_recibo
            from datetime import datetime
            fecha_actual = timezone.now()
            
            # Obtener los pagos de la reserva
            pagos = []
            total_pagado = 0
            formas_de_pago = []
            
            # Búsqueda simple de conceptos para evitar errores
            print(f"🔍 DEBUG SIMPLE - Movimiento ID: {movimiento.id}")
            print(f"🔍 Número liquidación: '{movimiento.numero_liquidacion}'")
            
            conceptos_operacion = None
            
            try:
                from .models import Registro
                # Búsqueda básica
                conceptos_operacion = Registro.objects.filter(
                    interno_caja=movimiento.numero_liquidacion
                ).order_by('fecha')
                print(f"🔍 CONCEPTOS ENCONTRADOS: {conceptos_operacion.count()}")
            except Exception as e:
                print(f"❌ Error en búsqueda básica: {e}")
                conceptos_operacion = None
            
            if conceptos_operacion and conceptos_operacion.exists():
                # Usar los conceptos de la operación
                for registro in conceptos_operacion:
                    concepto_desc = ''
                    if registro.concepto:
                        concepto_desc = f'{registro.concepto.id} - {registro.concepto.nombre}'
                    else:
                        concepto_desc = 'Concepto no especificado'
                    
                    print(f"💰 CONCEPTO: {concepto_desc} - ${registro.liquidacion}")
                    
                    pagos.append({
                        'fecha': registro.fecha_comprobante.strftime('%d/%m/%Y'),
                        'codigo': registro.interno_caja or f'R{registro.id:04d}',
                        'concepto': concepto_desc,
                        'monto': f'${registro.liquidacion:,.0f}'
                    })
                    total_pagado += registro.liquidacion
            else:
                # Fallback: extraer conceptos individuales del campo concepto del movimiento
                print("📋 FALLBACK: Extrayendo conceptos individuales desde movimiento.concepto")
                
                # ✅ INICIALIZAR VARIABLE DE CONTROL
                conceptos_procesados = False
                
                try:
                    fecha_mov = movimiento.fecha.strftime('%d/%m/%Y')
                    codigo_mov = movimiento.numero_liquidacion or f'M{movimiento.id:04d}'
                    
                    # Intentar extraer conceptos individuales del campo concepto
                    # Nuevo formato esperado: "Reserva 85 - limpieza + alquiler + deposito|CONCEPTOS:11:limpieza:35000|1:alquiler:35000|10:deposito:20000|"
                    concepto_texto = movimiento.concepto or ""
                    print(f"📝 CONCEPTO COMPLETO: {concepto_texto}")
                    
                    # Buscar información estructurada de conceptos
                    if "|CONCEPTOS:" in concepto_texto:
                        # Extraer la parte estructurada
                        concepto_parts = concepto_texto.split("|CONCEPTOS:", 1)
                        if len(concepto_parts) > 1:
                            conceptos_data = concepto_parts[1]  # "11:limpieza:35000|1:alquiler:35000|10:deposito:20000|"
                            conceptos_items = [item for item in conceptos_data.split("|") if item.strip()]
                            print(f"🔍 CONCEPTOS ESTRUCTURADOS ENCONTRADOS: {conceptos_items}")
                            
                            # ✅ VARIABLES PARA DETECTAR CONCEPTO 10
                            concepto_10_en_recibo = False
                            deposito_pagado_via_concepto10 = 0
                            
                            # Crear una entrada por cada concepto individual
                            for i, concepto_item in enumerate(conceptos_items):
                                parts = concepto_item.split(":")
                                if len(parts) >= 3:
                                    concepto_id = parts[0]
                                    concepto_nombre = parts[1]
                                    concepto_importe = parts[2]
                                    
                                    # Limpiar y convertir el importe
                                    try:
                                        importe_num = float(concepto_importe.replace(',', '').replace('.', ''))
                                        if importe_num > 1000:  # Si es mayor a 1000, probablemente no tiene decimales
                                            importe_num = importe_num
                                        else:
                                            importe_num = importe_num * 100  # Convertir si está en formato decimal
                                    except:
                                        importe_num = 0
                                    
                                    # ✅ DETECTAR CONCEPTO 10 (DEPÓSITO)
                                    if concepto_id == '10':
                                        concepto_10_en_recibo = True
                                        deposito_pagado_via_concepto10 = importe_num
                                        print(f"🏦 CONCEPTO 10 DETECTADO EN RECIBO: Depósito ${importe_num:,.0f}")
                                    
                                    pagos.append({
                                        'fecha': fecha_mov,
                                        'codigo': concepto_id,
                                        'concepto': concepto_nombre,
                                        'monto': f'${importe_num:,.0f}'
                                    })
                                    total_pagado += importe_num
                                    print(f"💰 CONCEPTO {i+1}: ID={concepto_id}, {concepto_nombre} - ${importe_num:,.0f}")
                            
                            # ✅ ACTUALIZAR DEPÓSITO BASADO EN CONCEPTO 10
                            if concepto_10_en_recibo:
                                total_deposito_pagado_recibo = deposito_pagado_via_concepto10
                                print(f"💳 DEPÓSITO CONFIRMADO: ${total_deposito_pagado_recibo} (vía concepto 10)")
                            else:
                                total_deposito_pagado_recibo = 0
                                print(f"⚠️  SIN CONCEPTO 10: Depósito NO considerado pagado")
                            
                            # Si se procesaron conceptos estructurados, marcar como completo
                            if pagos:
                                print(f"✅ CONCEPTOS ESTRUCTURADOS PROCESADOS: {len(pagos)} conceptos")
                                # MARCAR COMO PROCESADO: Ya se procesaron los conceptos estructurados
                                conceptos_procesados = True
                            else:
                                print("⚠️ No se encontraron conceptos estructurados válidos")
                                conceptos_procesados = False
                        else:
                            # Fallback al método anterior
                            print("⚠️ No se pudo parsear información estructurada, usando método anterior")
                            conceptos_procesados = False
                    
                    # ✅ SOLO EJECUTAR FALLBACK SI NO HAY CONCEPTOS PROCESADOS
                    if not conceptos_procesados and not pagos and " + " in concepto_texto:
                        # Extraer la parte después del número de reserva
                        parts = concepto_texto.split(" - ", 1)
                        if len(parts) > 1:
                            conceptos_parte = parts[1].split("|")[0]  # Tomar solo la parte antes de |CONCEPTOS si existe
                            conceptos_individuales = [c.strip() for c in conceptos_parte.split(" + ")]
                            print(f"🔍 CONCEPTOS ENCONTRADOS (método anterior): {conceptos_individuales}")
                            
                            # Crear una entrada por cada concepto individual
                            for i, concepto_nombre in enumerate(conceptos_individuales):
                                # Distribuir el monto total entre los conceptos
                                monto_por_concepto = movimiento.monto_total / len(conceptos_individuales)
                                
                                pagos.append({
                                    'fecha': fecha_mov,
                                    'codigo': f'{codigo_mov}_{i+1}' if len(conceptos_individuales) > 1 else codigo_mov,
                                    'concepto': concepto_nombre,
                                    'monto': f'${monto_por_concepto:,.0f}'
                                })
                                print(f"💰 CONCEPTO {i+1}: {concepto_nombre} - ${monto_por_concepto:,.0f}")
                            
                            total_pagado += movimiento.monto_total
                        else:
                            # No se pudo parsear, usar concepto único
                            print("⚠️ No se pudieron extraer conceptos individuales, usando concepto único")
                    pagos.append({
                        'fecha': fecha_mov,
                        'codigo': codigo_mov,
                                'concepto': concepto_texto or 'ALQ - Alquiler temporario',
                                'monto': f'${movimiento.monto_total:,.0f}'
                            })
                    total_pagado += movimiento.monto_total
                    
                    if not conceptos_procesados and not pagos:
                        # No hay conceptos separados, usar el concepto completo
                        print("⚠️ No hay conceptos separados con '+', usando concepto completo")
                        pagos.append({
                            'fecha': fecha_mov,
                            'codigo': codigo_mov,
                            'concepto': concepto_texto or 'ALQ - Alquiler temporario',
                        'monto': f'${movimiento.monto_total:,.0f}'
                    })
                    total_pagado += movimiento.monto_total
                    
                except Exception as e:
                    print(f"❌ Error en fallback: {e}")
                    # Solo usar fallback ultra simple si no se procesaron conceptos
                    if not conceptos_procesados:
                        print("🚨 USANDO FALLBACK ULTRA SIMPLE")
                        pagos.append({
                            'fecha': '15/09/2025',
                            'codigo': 'M0001',
                            'concepto': 'ALQ - Alquiler temporario',
                            'monto': '$130,000'
                        })
                        total_pagado = 130000
                    else:
                        print("✅ CONCEPTOS YA PROCESADOS - No usar fallback ultra simple")
            
            # Obtener formas de pago del movimiento
            if movimiento.monto_efectivo > 0:
                formas_de_pago.append('Efectivo')
            if movimiento.monto_tarjeta > 0:
                formas_de_pago.append('Tarjeta')
            if movimiento.monto_cheque > 0:
                formas_de_pago.append('Cheque')
            if movimiento.monto_deposito > 0:
                if movimiento.destino_deposito == 'galicia':
                    formas_de_pago.append('Galicia')
                elif movimiento.destino_deposito == 'mp':
                    formas_de_pago.append('Mercado Pago')
                else:
                    formas_de_pago.append('Transferencia')
            
            # Función para convertir número a palabras
            def numero_a_palabras(numero):
                # Convertir número a palabras en español (versión simplificada)
                unidades = ['', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve']
                decenas = ['', '', 'veinte', 'treinta', 'cuarenta', 'cincuenta', 'sesenta', 'setenta', 'ochenta', 'noventa']
                centenas = ['', 'ciento', 'doscientos', 'trescientos', 'cuatrocientos', 'quinientos', 'seiscientos', 'setecientos', 'ochocientos', 'novecientos']
                
                numero = int(numero)
                if numero == 0:
                    return "PESOS CERO CON 00/100"
                elif numero == 100:
                    return "PESOS CIEN CON 00/100"
                elif numero < 10:
                    return f"PESOS {unidades[numero].upper()} CON 00/100"
                elif numero < 100:
                    if numero < 20:
                        especiales = ['diez', 'once', 'doce', 'trece', 'catorce', 'quince', 'dieciséis', 'diecisiete', 'dieciocho', 'diecinueve']
                        return f"PESOS {especiales[numero-10].upper()} CON 00/100"
                    else:
                        dec = numero // 10
                        uni = numero % 10
                        if uni == 0:
                            return f"PESOS {decenas[dec].upper()} CON 00/100"
                        else:
                            return f"PESOS {decenas[dec].upper()} Y {unidades[uni].upper()} CON 00/100"
                elif numero < 1000:
                    cent = numero // 100
                    resto = numero % 100
                    if resto == 0:
                        return f"PESOS {centenas[cent].upper()} CON 00/100"
                    else:
                        palabras_resto = numero_a_palabras(resto).replace("PESOS ", "").replace(" CON 00/100", "")
                        return f"PESOS {centenas[cent].upper()} {palabras_resto} CON 00/100"
                else:
                    # Para números mayores, usar formato simple
                    return f"PESOS {numero:,} CON 00/100".replace(',', '.')
            
            # Preparar datos del cliente con campos adicionales
            cliente_data = reserva.cliente
            cliente_completo = {
                'nombre_completo': f"{cliente_data.nombre} {cliente_data.apellido}",
                'domicilio': cliente_data.domicilio or '',
                'localidad': cliente_data.localidad or '',
                'provincia': cliente_data.provincia or '',
                'dni': cliente_data.dni or '',
                'telefono': cliente_data.celular or '',  # Mapear celular a telefono
                'cuit': getattr(cliente_data, 'cuit', '') or '',  # CUIT puede no existir
            }
            
            # Preparar datos de la propiedad con formato correcto
            propiedad_data = reserva.propiedad
            propiedad_completa = {
                'direccion': propiedad_data.direccion or '',
                'id': propiedad_data.id,
                'llave': propiedad_data.llave or 'N/A',
                'piso': propiedad_data.piso or '',
                'departamento': propiedad_data.departamento or '',
                'ambientes': f"{propiedad_data.ambientes} personas" if propiedad_data.ambientes else 'N/A',
                'wifi': 'SÍ' if propiedad_data.wifi else 'NO',
                'cochera': 'SÍ' if propiedad_data.cochera else 'NO',
            }
            
            # Preparar datos de la reserva con formato de moneda
            reserva_formateada = {
                'id': reserva.id,
                'precio_total': f'${reserva.precio_total:,.0f}',
                'senia': f'${reserva.senia:,.0f}',
                'cuota_pendiente': f'${reserva.cuota_pendiente:,.0f}',
                'deposito_garantia': f'${reserva.deposito_garantia:,.0f}',
                'propiedad': propiedad_completa,
            }
            
            # DEBUG: Confirmar template y datos en ver_recibo_movimiento
            print("🧾 TEMPLATE USADO en ver_recibo_movimiento: inmobiliaria/reserva/recibo.html") 
            print(f"🧾 TOTAL PAGADO: {f'${total_pagado:,.0f}'}")
            print(f"🧾 FORMAS DE PAGO: {', '.join(formas_de_pago) if formas_de_pago else 'EFECTIVO'}")
            print(f"🧾 PAGOS COUNT: {len(pagos)}")
            print(f"🧾 MONTO MOVIMIENTO: ${movimiento.monto_total:,.0f}")
            
            # Si no hay pagos específicos, usar el total del movimiento
            if total_pagado == 0:
                print("⚠️ TOTAL PAGADO ES 0 - USANDO MONTO DEL MOVIMIENTO")
                total_pagado = movimiento.monto_total
            
            # Generar logo en base64 para evitar problemas de carga
            import base64
            import os
            from django.conf import settings
            
            logo_base64 = None
            try:
                logo_path = os.path.join(settings.BASE_DIR, 'inmobiliaria', 'static', 'images', 'logo.png')
                with open(logo_path, 'rb') as logo_file:
                    logo_data = base64.b64encode(logo_file.read()).decode()
                    logo_base64 = f'data:image/png;base64,{logo_data}'
            except Exception as e:
                print(f"⚠️ Error al cargar logo: {e}")
                logo_base64 = None
            
            # ✅ PREPARAR DATOS CORREGIDOS PARA EL RECIBO
            if recibo_obj:
                numero_recibo_mostrar = recibo_obj.numero_recibo
                precio_total_mostrar = recibo_obj.precio_total_operacion
                saldo_pendiente_mostrar = recibo_obj.saldo_pendiente
                monto_este_pago_mostrar = recibo_obj.monto_este_pago
            else:
                numero_recibo_mostrar = f'R{reserva.id:06d}'
                precio_total_mostrar = reserva.precio_total
                saldo_pendiente_mostrar = saldo_pendiente
                # ✅ CORREGIDO: Usar la seña del casillero, no el total del movimiento
                monto_este_pago_mostrar = total_senia_pagada_recibo
            
            # Usar el nuevo template de recibo
            return render(request, 'inmobiliaria/reserva/recibo.html', {
                'reserva': reserva_formateada,
                'cliente': cliente_completo,
                'propiedad': propiedad_completa,
                'numero_recibo': numero_recibo_mostrar,
                'fecha': fecha_actual.strftime('%d/%m/%Y'),
                'hora': fecha_actual.strftime('%H:%M'),
                'fecha_inicio': reserva.fecha_inicio.strftime('%d/%m/%Y'),
                'fecha_fin': reserva.fecha_fin.strftime('%d/%m/%Y'),
                'descripcion': 'Alquiler temporario por días',
                'pagos': pagos,
                'total_pagado': f'${total_pagado:,.0f}',
                'monto_en_palabras': numero_a_palabras(total_pagado),
                'formas_de_pago': ', '.join(formas_de_pago) if formas_de_pago else 'EFECTIVO',
                'logo_base64': logo_base64,
                # ✅ DATOS CORREGIDOS PARA MOSTRAR EN RECIBO
                'precio_total_operacion': f'${precio_total_mostrar:,.0f}',
                'saldo_pendiente': f'${saldo_pendiente_mostrar:,.0f}',
                'monto_este_pago': f'${monto_este_pago_mostrar:,.0f}',
                'deposito_garantia': f'${reserva.deposito_garantia:,.0f}',
                # ✅ ESTADO DEL DEPÓSITO: Verificar si fue pagado en CUALQUIER movimiento de la reserva
                'deposito_estado': determinar_estado_deposito_completo(reserva),
            })
        
        # Si no hay reserva, usar el template original
        context = {
            'movimiento': movimiento,
            'reserva': reserva,
            'total_movimiento': total_movimiento,
            'total_efectivo': total_efectivo,
            'total_cheque': total_cheque,
            'total_tarjeta': total_tarjeta,
            'total_deposito': total_deposito,
            'total_deposito_galicia': total_deposito_galicia,
            'total_deposito_mp': total_deposito_mp,
            'saldo_pendiente': saldo_pendiente,
            'total_pagado_acumulado': total_pagado_reserva if reserva else total_movimiento,
            'total_senia_pagada': total_senia_pagada_recibo if reserva else 0,  # ✅ NUEVO: Solo seña
            'total_deposito_pagado': total_deposito_pagado_recibo if reserva else 0,  # ✅ NUEVO: Solo depósito
            'movimientos_relacionados': movimientos_relacionados,
            'fecha_actual': datetime.now().strftime('%d/%m/%Y'),
            'caja': movimiento.caja,
            'propiedad': movimiento.propiedad,
            'empleado': movimiento.empleado,
        }
        
        return render(request, 'inmobiliaria/caja/recibo_movimiento.html', context)
        
    except Exception as e:
        messages.error(request, f'Error al generar el recibo: {str(e)}')
        return redirect('inmobiliaria:lista_cajas')

@login_required
def listar_recibos_propiedad(request, propiedad_id):
    """
    Vista para listar todos los recibos de una propiedad específica
    """
    try:
        from .models.recibo import Recibo
        from .models.propiedad import Propiedad
        
        propiedad = get_object_or_404(Propiedad, id=propiedad_id, sucursal=request.user.sucursal)
        
        # Obtener todos los recibos de esta propiedad
        recibos = Recibo.objects.filter(propiedad=propiedad).order_by('-fecha_emision')
        
        # Preparar datos para el template
        recibos_data = []
        for recibo in recibos:
            recibos_data.append({
                'numero_recibo': recibo.numero_recibo,
                'fecha_emision': recibo.fecha_emision,
                'reserva_id': recibo.reserva.id,
                'monto_este_pago': recibo.monto_este_pago,
                'precio_total_operacion': recibo.precio_total_operacion,
                'saldo_pendiente': recibo.saldo_pendiente,
                'movimiento_id': recibo.movimiento_caja.id,
                'empleado': recibo.empleado.username if recibo.empleado else 'N/A',
            })
        
        context = {
            'propiedad': propiedad,
            'recibos': recibos_data,
        }
        
        return render(request, 'inmobiliaria/recibos/lista_recibos_propiedad.html', context)
        
    except Exception as e:
        messages.error(request, f'Error al cargar recibos: {str(e)}')
        return redirect('inmobiliaria:propiedades')

@login_required
def crear_inquilino_ajax(request):
    if request.method == 'POST':
        try:
            # Obtener la sucursal del usuario logueado
            sucursal = request.user.sucursal
            
            # Campos opcionales que pueden no estar en el formulario
            fecha_nacimiento = request.POST.get('fecha_nacimiento')
            if fecha_nacimiento == '':
                fecha_nacimiento = None
            
            inquilino = Inquilino.objects.create(
                nombre=request.POST['nombre'],
                apellido=request.POST['apellido'],
                fecha_nacimiento=fecha_nacimiento,
                email=request.POST['email'],
                celular=request.POST['celular'],
                tipo_doc=request.POST['tipo_doc'],
                dni=request.POST['dni'],
                tipo_ins=request.POST.get('tipo_ins', 'otro'),  # Valor por defecto
                cuit=request.POST.get('cuit', ''),
                localidad=request.POST['localidad'],
                provincia=request.POST['provincia'],
                domicilio=request.POST['domicilio'],
                codigo_postal=request.POST['codigo_postal'],
                observaciones=request.POST.get('observaciones', ''),
                garantia=request.POST.get('garantia', ''),
                sucursal=sucursal  # Agregar la sucursal
            )
            return JsonResponse({
                'success': True,
                'inquilino': {
                    'id': inquilino.id,
                    'nombre': inquilino.nombre,
                    'apellido': inquilino.apellido,
                    'dni': inquilino.dni
                }
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    return JsonResponse({'success': False, 'error': 'Método no permitido'})

def crear_propietario_ajax(request):
    if request.method == 'POST':
        try:
            # Obtener la sucursal del usuario logueado
            sucursal = request.user.sucursal
            
            # Campos opcionales que pueden no estar en el formulario
            fecha_nacimiento = request.POST.get('fecha_nacimiento')
            if fecha_nacimiento == '':
                fecha_nacimiento = None
                
            propietario = Propietario.objects.create(
                nombre=request.POST['nombre'],
                apellido=request.POST['apellido'],
                fecha_nacimiento=fecha_nacimiento,
                email=request.POST['email'],
                celular=request.POST['celular'],
                tipo_doc=request.POST['tipo_doc'],
                dni=request.POST['dni'],
                tipo_ins=request.POST.get('tipo_ins', 'otro'),  # Valor por defecto
                cuit=request.POST.get('cuit', ''),
                localidad=request.POST['localidad'],
                provincia=request.POST['provincia'],
                domicilio=request.POST['domicilio'],
                codigo_postal=request.POST['codigo_postal'],
                observaciones=request.POST.get('observaciones', ''),
                cuenta_bancaria=request.POST.get('cuenta_bancaria', ''),
                sucursal=sucursal  # Agregar la sucursal
            )
            return JsonResponse({
                'success': True,
                'propietario': {
                    'id': propietario.id,
                    'nombre': propietario.nombre,
                    'apellido': propietario.apellido,
                    'dni': propietario.dni
                }
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    return JsonResponse({'success': False, 'error': 'Método no permitido'})

def obtener_precios_propiedad(request):
    propiedad_id = request.GET.get('propiedad_id')
    propiedad = Propiedad.objects.get(id=propiedad_id)
    precios = Precio.objects.filter(propiedad=propiedad)

    # Asegúrate de que todos los tipos de precios estén presentes
    todos_los_precios = []
    for tipo_choice in TipoPrecio.choices:
        tipo_key = tipo_choice[0]
        precio = precios.filter(tipo_precio=tipo_key).first()
        if not precio:
            precio = Precio(
                propiedad=propiedad,
                tipo_precio=tipo_key,
                precio_total=0,
                precio_por_dia=0,
                precio_toma=0,
                precio_dia_toma=0,
                ajuste_porcentaje=0
            )
        todos_los_precios.append(precio)

    # Serializar y devolver los precios
    precios_serializados = [
        {
            'tipo_precio': precio.tipo_precio,
            'precio_total': str(precio.precio_total),
            'precio_por_dia': str(precio.precio_por_dia),
            'precio_toma': str(precio.precio_toma),
            'precio_dia_toma': str(precio.precio_dia_toma),
            'ajuste_porcentaje': str(precio.ajuste_porcentaje),
        }
        for precio in todos_los_precios
    ]

    return JsonResponse({'precios': precios_serializados})

def format_price(value):
    try:
        return "{:,.0f}".format(value).replace(',', '.')
    except (ValueError, TypeError):
        return str(value)

def obtener_vendedor(request, vendedor_id):
    logger.info(f"Solicitando vendedor con ID: {vendedor_id}")
    try:
        vendedor = Vendedor.objects.get(id=vendedor_id)
        logger.info(f"Vendedor encontrado: {vendedor.nombre} {vendedor.apellido}")
        print(f"Vendedor encontrado: {vendedor.nombre} {vendedor.apellido}")
        return JsonResponse({
            'success': True,
            'vendedor': {
                'id': vendedor.id,
                'nombre_completo': f"{vendedor.nombre} {vendedor.apellido}"
            }
        })
    except Vendedor.DoesNotExist:
        logger.warning(f"Vendedor con ID {vendedor_id} no encontrado")
        return JsonResponse({'success': False, 'message': 'Vendedor no encontrado'}, status=404)
    except Exception as e:
        logger.error(f"Error al obtener vendedor: {str(e)}")
        return JsonResponse({'success': False, 'message': 'Error interno del servidor'}, status=500)











def agregar_disponibilidad_masiva(request):
    # Obtener la sucursal del usuario logueado
    sucursal = request.user.sucursal
    
    if request.method == 'POST':
        propiedad_ids = request.POST.getlist('propiedades[]')
        fecha_inicio = request.POST.get('fecha_inicio')
        fecha_fin = request.POST.get('fecha_fin')
        
        propiedades_actualizadas = 0
        propiedades_exitosas = []
        errores_detallados = []
        
        try:
            # Procesar cada propiedad individualmente y reportar resultados detallados
            for propiedad_id in propiedad_ids:
                try:
                    propiedad = Propiedad.objects.get(
                        id=propiedad_id,
                        sucursal=sucursal  # Usar la sucursal del usuario
                    )
                    
                    # 🎯 INTENTAR CREAR DISPONIBILIDAD (como antes)
                    # Si falla por cualquier razón, capturar el error pero continuar con las demás
                    nueva_disponibilidad = Disponibilidad.objects.create(
                        propiedad=propiedad,
                        fecha_inicio=fecha_inicio,
                        fecha_fin=fecha_fin,
                        es_manual=True  # Marcada explícitamente como manual
                    )
                    
                    # ✅ Las disponibilidades manuales no crean historial automáticamente
                    # El historial se gestiona por separado
                    
                    # ✅ Si llegamos aquí, fue exitoso
                    propiedades_actualizadas += 1
                    propiedades_exitosas.append({
                        'propiedad_id': propiedad_id,
                        'direccion': f"{propiedad.direccion}"
                    })
                        
                except Propiedad.DoesNotExist:
                    errores_detallados.append({
                        'propiedad_id': propiedad_id,
                        'direccion': 'Desconocida',
                        'error': 'No pertenece a su sucursal o no existe',
                        'tipo': 'no_existe'
                    })
                except Exception as e:
                    # Intentar obtener la dirección para mejor reporte
                    try:
                        propiedad = Propiedad.objects.get(id=propiedad_id)
                        direccion = f"{propiedad.direccion}"
                    except:
                        direccion = 'Desconocida'
                    
                    # 🔍 Clasificar el tipo de error para mayor claridad
                    error_msg = str(e)
                    tipo_error = 'error_general'
                    
                    if 'UNIQUE constraint failed' in error_msg or 'duplicate' in error_msg.lower():
                        error_msg = 'Ya existe disponibilidad para estas fechas'
                        tipo_error = 'solapamiento'
                    elif 'date' in error_msg.lower():
                        error_msg = 'Error en las fechas proporcionadas'
                        tipo_error = 'fecha_invalida'
                    elif 'foreign key' in error_msg.lower():
                        error_msg = 'Problema de referencia en la base de datos'
                        tipo_error = 'referencia'
                    
                    errores_detallados.append({
                        'propiedad_id': propiedad_id,
                        'direccion': direccion,
                        'error': error_msg,
                        'tipo': tipo_error,
                        'error_original': str(e)  # Para debugging si es necesario
                    })
            
            # Preparar respuesta detallada
            respuesta = {
                'propiedades_procesadas': len(propiedad_ids),
                'propiedades_exitosas': propiedades_actualizadas,
                'propiedades_con_errores': len(errores_detallados),
                'detalles_exitosas': propiedades_exitosas,
                'detalles_errores': errores_detallados
            }
            
            if propiedades_actualizadas > 0:
                mensaje = f'✅ {propiedades_actualizadas} propiedades actualizadas correctamente'
                if errores_detallados:
                    mensaje += f'\n⚠️ {len(errores_detallados)} propiedades con errores'
                
                return JsonResponse({
                    'success': True,
                    'message': mensaje,
                    'detalles': respuesta
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': f'❌ No se pudo actualizar ninguna propiedad ({len(errores_detallados)} errores)',
                    'detalles': respuesta
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error al actualizar disponibilidades: {str(e)}'
            })
    
    # Filtrar propiedades por sucursal para el listado
    propiedades = Propiedad.objects.filter(
        sucursal=sucursal
    ).order_by('direccion')
    
    return render(request, 'inmobiliaria/propiedades/disponibilidad_masiva.html', {
        'propiedades': propiedades,
        'sucursal': sucursal  # Pasar la sucursal al template
    })

# views.py
@login_required
def obtener_inquilino(request, inquilino_id):
    try:
        inquilino = Inquilino.objects.get(id=inquilino_id)
        return JsonResponse({'success': True, 'inquilino': {
            'id': inquilino.id,
            'nombre': inquilino.nombre,
            'apellido': inquilino.apellido,
            'dni': inquilino.dni,
            # Agrega más campos según sea necesario
        }})
    except Inquilino.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Inquilino no encontrado.'}, status=404)

def crear_sucursal(request):
    if request.method == 'POST':
        form = SucursalForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('inmobiliaria:reservas')  # Redirige a una lista de sucursales o a donde desees
    else:
        form = SucursalForm()
    
    return render(request, 'inmobiliaria/sucursal/crear_sucursal.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            
            try:
                vendedor = Vendedor.objects.get(username=username)
                print(f"Usuario encontrado: {username}")
                print(f"¿Usuario activo?: {vendedor.is_active}")
                
                if not vendedor.is_active:
                    messages.error(request, 'Tu cuenta no está activa. Contacta al administrador.')
                    return render(request, 'inmobiliaria/autenticacion/login.html', {'form': form})
                
                user = authenticate(request, username=username, password=password)
                if user is not None:
                    login(request, user)
                    # Verificar si tiene contraseña temporal
                    if hasattr(user, 'password_temporal') and user.password_temporal:
                        return redirect('inmobiliaria:cambiar_password')
                    return redirect('inmobiliaria:index')
                else:
                    messages.error(request, 'Contraseña incorrecta.')
                    print("Contraseña incorrecta para el usuario:", username)
                
            except Vendedor.DoesNotExist:
                messages.error(request, f'El usuario {username} no existe.')
                print(f"Usuario no encontrado: {username}")
        else:
            messages.error(request, 'Por favor, corrige los errores del formulario.')
            print("Errores del formulario:", form.errors)
    else:
        form = LoginForm()
    
    return render(request, 'inmobiliaria/autenticacion/login.html', {'form': form})

@login_required
@require_http_methods(["POST"])
def actualizar_orden_imagenes(request):
    try:
        data = json.loads(request.body)
        imagenes_orden = data.get('imagenes', [])
        logger.info(f"Actualizando orden de imágenes: {imagenes_orden}")
        
        for item in imagenes_orden:
            try:
                imagen = ImagenPropiedad.objects.get(id=item['id'])
                if imagen.orden != item['orden']:
                    imagen.orden = item['orden']
                    imagen.save()
            except ImagenPropiedad.DoesNotExist:
                logger.error(f"No se encontró la imagen con ID: {item['id']}")
            except Exception as e:
                logger.error(f"Error al actualizar imagen {item['id']}: {str(e)}")
        
        return JsonResponse({'success': True})
    except json.JSONDecodeError as e:
        logger.error(f"Error al decodificar JSON: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Datos JSON inválidos'}, status=400)
    except Exception as e:
        logger.error(f"Error general en actualizar_orden_imagenes: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
@require_http_methods(["DELETE"])
def eliminar_imagen(request):
    try:
        imagen_id = request.GET.get('imagen_id')
        logger.info(f"Intentando eliminar imagen ID: {imagen_id}")
        
        if not imagen_id:
            return JsonResponse({'success': False, 'error': 'ID de imagen no proporcionado'}, status=400)
        
        imagen = get_object_or_404(ImagenPropiedad, id=imagen_id)
        orden_eliminado = imagen.orden
        propiedad = imagen.propiedad
        
        # Eliminar el archivo físico
        try:
            if imagen.imagen:
                imagen.imagen.delete(save=False)
        except Exception as e:
            logger.error(f"Error al eliminar archivo físico: {str(e)}")
        
        # Eliminar el registro de la base de datos
        imagen.delete()
        
        # Reordenar las imágenes restantes
        ImagenPropiedad.objects.filter(
            propiedad=propiedad,
            orden__gt=orden_eliminado
        ).update(orden=models.F('orden') - 1)
        
        return JsonResponse({'success': True})
    except ImagenPropiedad.DoesNotExist:
        logger.error(f"Imagen no encontrada: {imagen_id}")
        return JsonResponse({'success': False, 'error': 'Imagen no encontrada'}, status=404)
    except Exception as e:
        logger.error(f"Error al eliminar imagen: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def enviar_recuperacion(request):
    form = EmailForm()
    
    if request.method == "POST":
        form = EmailForm(request.POST)
        
        if form.is_valid():
            email = form.cleaned_data['email']
            User = get_user_model()
            
            try:
                # Buscar usuario por email (case-insensitive)
                user = User.objects.filter(email__iexact=email).first()
                
                if user:
                    # Verificar que el usuario tiene email válido
                    if not user.email or not user.email.strip():
                        messages.error(request, 'Tu cuenta no tiene un correo electrónico configurado. Contacta al administrador.')
                        return render(request, 'inmobiliaria/autenticacion/password_reset_form.html', {'form': form})
                    
                    # Generar una nueva contraseña temporal
                    nueva_password = User.objects.make_random_password()
                    user.set_password(nueva_password)
                    user.password_temporal = True  # Marcar como contraseña temporal
                    user.save()
                    
                    # Enviar email con la nueva contraseña
                    subject = 'Tu nueva contraseña - Sistema Gonnet'
                    message = f'''
Hola {user.first_name if user.first_name else user.username},

Tu nueva contraseña temporal es: {nueva_password}

Por favor, ingresa con esta contraseña y cámbiala inmediatamente por una de tu preferencia.

Saludos,
El equipo de Sistema Gonnet
                    '''
                    
                    try:
                        send_mail(
                            subject,
                            message,
                            'gonnetinterno@gmail.com',  # Remitente
                            [user.email],  # Destinatario
                            fail_silently=False,
                        )
                        messages.success(request, f'Se ha enviado un correo con tu nueva contraseña a {user.email}.')
                        return redirect('inmobiliaria:password_reset_done')
                    except Exception as e:
                        # Revertir el cambio de contraseña si falla el envío
                        user.refresh_from_db()
                        messages.error(request, f'Error al enviar el correo: {str(e)}. Por favor, contacta al administrador.')
                else:
                    # Mensaje simple sin debug complejo
                    messages.error(request, 'No existe una cuenta con ese correo electrónico. Verifica que esté escrito correctamente.')
                        
            except Exception as e:
                messages.error(request, f'Error al procesar la solicitud: {str(e)}')
        else:
            # Si el formulario no es válido, mostrar errores
            messages.error(request, 'Por favor, ingresa un correo electrónico válido.')
    
    return render(request, 'inmobiliaria/autenticacion/password_reset_form.html', {'form': form})

@login_required
def cambiar_password(request):
    if request.method == 'POST':
        form = SetPasswordForm(request.user, request.POST)
        if form.is_valid():
            try:
                user = form.save()
                update_session_auth_hash(request, user)  # Mantiene la sesión activa
                user.password_temporal = False
                user.save()
                messages.success(request, 'Tu contraseña ha sido actualizada exitosamente.')
                return redirect('inmobiliaria:index')
            except Exception as e:
                messages.error(request, f'Error al guardar la contraseña: {str(e)}')
        else:
            # Mostrar errores específicos del formulario
            for field in form:
                for error in field.errors:
                    messages.error(request, f'{field.label}: {error}')
            if form.non_field_errors():
                for error in form.non_field_errors():
                    messages.error(request, error)
    else:
        form = SetPasswordForm(request.user)
    
    return render(request, 'inmobiliaria/autenticacion/cambiar_password.html', {
        'form': form,
        'user': request.user
    })

@login_required
def confirmar_pago(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    conceptos_pago = ConceptoPago.objects.all()
    
    context = {
        'reserva': reserva,
        'conceptos_pago': conceptos_pago,
    }
    return render(request, 'inmobiliaria/reserva/finalizar_reserva.html', context)

@login_required
def agregar_pago(request, reserva_id):
    try:
        reserva = get_object_or_404(Reserva, id=reserva_id)
        
        if request.method == 'POST':
            with transaction.atomic():
                # Obtener datos del formulario
                monto = Decimal(request.POST.get('monto', '0'))
                forma_pago = request.POST.get('forma_pago')
                concepto_id = request.POST.get('concepto')
                
                # Validaciones
                if monto <= 0:
                    raise ValueError('El monto debe ser mayor que cero')
                
                if monto > reserva.cuota_pendiente:
                    raise ValueError('El monto no puede ser mayor al saldo pendiente')
                
                # Obtener el concepto
                concepto = get_object_or_404(ConceptoPago, id=concepto_id)
                
                # Obtener datos adicionales según forma de pago
                numero_tarjeta = None
                tipo_tarjeta = None
                destino_deposito = None

                if 'tarjeta' in forma_pago:
                    numero_tarjeta = request.POST.get('numero_tarjeta')
                    tipo_tarjeta = request.POST.get('tipo_tarjeta')
                    
                    if not numero_tarjeta or not tipo_tarjeta:
                        raise ValueError('Los datos de la tarjeta son requeridos')
                
                elif forma_pago in ['transferencia', 'qr']:
                    destino_deposito = request.POST.get('destino_deposito')
                    if not destino_deposito:
                        raise ValueError('El destino de la transferencia es requerido')
                
                # Crear el pago
                pago = Pago.objects.create(
                    reserva=reserva,
                    monto=monto,
                    forma_pago=forma_pago,
                    concepto=concepto,
                    numero_tarjeta=numero_tarjeta,
                    tipo_tarjeta=tipo_tarjeta,
                    destino_deposito=destino_deposito
                )
                
                # ✅ ACTUALIZAR SALDOS SEPARANDO SEÑA DE DEPÓSITO
                pagos_reserva = Pago.objects.filter(reserva=reserva)
                total_senia_only = 0
                total_deposito_only = 0
                total_pagado = 0
                
                for pago_item in pagos_reserva:
                    total_pagado += pago_item.monto
                    
                    # Identificar si es depósito por el concepto
                    concepto_lower = pago_item.concepto.concepto.lower() if pago_item.concepto else ''
                    es_deposito = any(palabra in concepto_lower for palabra in [
                        'depósito', 'deposito', 'garantía', 'garantia', 
                        'caución', 'caucion', 'seguridad', 'fianza',
                        'deposit', 'warranty', 'security'
                    ])
                    
                    if es_deposito:
                        total_deposito_only += pago_item.monto
                        print(f"💳 DEPÓSITO AGREGAR_PAGO - Concepto: '{concepto_lower}', Monto: {pago_item.monto}")
                    else:
                        total_senia_only += pago_item.monto
                        print(f"💰 SEÑA AGREGAR_PAGO - Concepto: '{concepto_lower}', Monto: {pago_item.monto}")
                
                # Actualizar reserva solo con la seña
                reserva.senia = total_senia_only  # ✅ Solo seña
                reserva.cuota_pendiente = reserva.precio_total - total_senia_only  # ✅ Solo descontar seña
                
                print(f"💰 AGREGAR_PAGO - Precio Total: {reserva.precio_total}, Seña: {total_senia_only}, Depósito: {total_deposito_only}, Saldo: {reserva.cuota_pendiente}")
                
                # Si se completó el pago, finalizar la reserva
                if reserva.cuota_pendiente <= 0:
                    reserva.estado = 'finalizada'
                else:
                    reserva.estado = 'en_espera'
                
                reserva.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Pago registrado exitosamente',
                    'redirect_url': reverse('inmobiliaria:finalizar_reserva', args=[reserva.id]),
                    'detalles': {
                        'total_pagado': float(total_pagado),
                        'saldo_pendiente': float(reserva.cuota_pendiente),
                        'estado': reserva.estado
                    }
                })
                
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        })

@login_required
def eliminar_pago(request, pago_id):
    pago = get_object_or_404(Pago, id=pago_id)
    reserva_id = pago.reserva.id
    
    try:
        pago.delete()
        messages.success(request, 'Pago eliminado correctamente.')
    except Exception as e:
        messages.error(request, f'Error al eliminar el pago: {str(e)}')
    
    return redirect('inmobiliaria:confirmar_pago', reserva_id=reserva_id)

@login_required
def agregar_deposito(request, reserva_id):
    try:
        reserva = get_object_or_404(Reserva, id=reserva_id)
        
        if request.method == 'POST':
            monto_deposito = Decimal(request.POST.get('monto_deposito', '0'))
            
            if monto_deposito <= 0:
                raise ValueError('El monto del depósito debe ser mayor que cero')
            
            # Actualizar el depósito de garantía
            reserva.deposito_garantia = monto_deposito
            reserva.save()
            
            messages.success(request, 'Depósito de garantía registrado exitosamente')
        
        return redirect('inmobiliaria:finalizar_reserva', reserva_id=reserva_id)
        
    except Exception as e:
        messages.error(request, f'Error al registrar el depósito: {str(e)}')
        return redirect('inmobiliaria:finalizar_reserva', reserva_id=reserva_id)

from django.contrib.auth import logout
from django.shortcuts import redirect

def logout_view(request):
    logout(request)
    return redirect('inmobiliaria:login')

def ver_historial_disponibilidad(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, pk=propiedad_id)
    # ✅ MOSTRAR TODAS LAS DISPONIBILIDADES (como antes)
    # ✅ ORDENAMIENTO CRONOLÓGICO ESTRICTO: primero por fecha_inicio, luego por fecha_fin, luego por ID
    historial = HistorialDisponibilidad.objects.filter(
        propiedad=propiedad
    ).order_by('fecha_inicio', 'fecha_fin', 'id')

    return JsonResponse({
        'success': True,
        'historial': [{
            'fecha_inicio': h.fecha_inicio.strftime('%d/%m/%Y'),
            'fecha_fin': h.fecha_fin.strftime('%d/%m/%Y'),
            'estado': h.estado,
            'reserva_id': h.reserva.id if h.reserva else None,
            'cliente': h.reserva.cliente.nombre if h.reserva and h.reserva.cliente else None,
            'ultima_actualizacion': h.fecha_actualizacion.strftime('%d/%m/%Y %H:%M')
        } for h in historial]
    })

@login_required
def limpiar_historial_disponibilidad(request):
    """
    Vista para limpiar y reconstruir el historial de disponibilidad
    """
    if request.method == 'POST':
        propiedad_id = request.POST.get('propiedad_id')
        
        try:
            if propiedad_id:
                # Limpiar una propiedad específica
                propiedad = get_object_or_404(Propiedad, id=propiedad_id)
                
                # Eliminar historial de esta propiedad
                count_eliminados = HistorialDisponibilidad.objects.filter(propiedad=propiedad).count()
                HistorialDisponibilidad.objects.filter(propiedad=propiedad).delete()
                
                # Reconstruir historial
                reconstruir_historial_propiedad(propiedad)
                
                return JsonResponse({
                    'success': True,
                    'message': f'✅ Historial limpiado y reconstruido para propiedad {propiedad_id}',
                    'eliminados': count_eliminados
                })
            else:
                # Limpiar TODAS las propiedades
                count_total = HistorialDisponibilidad.objects.count()
                HistorialDisponibilidad.objects.all().delete()
                
                # Reconstruir para todas las propiedades con reservas
                propiedades_con_reservas = Propiedad.objects.filter(
                    reservas__estado__in=['confirmada', 'confirmada_no_pagada']
                ).distinct()
                
                for propiedad in propiedades_con_reservas:
                    reconstruir_historial_propiedad(propiedad)
                
                return JsonResponse({
                    'success': True,
                    'message': f'✅ Historial completamente limpiado y reconstruido',
                    'eliminados': count_total,
                    'propiedades_procesadas': propiedades_con_reservas.count()
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error al limpiar historial: {str(e)}'
            })
    
    return JsonResponse({'success': False, 'error': 'Método no permitido'})

@login_required
def limpieza_brutal(request):
    """
    🔥 LIMPIEZA BRUTAL: Elimina TODO y reconstruye desde cero
    """
    if request.method == 'POST':
        try:
            from datetime import timedelta
            from dateutil.relativedelta import relativedelta
            
            # 1. ELIMINAR absolutamente TODO
            count_historial = HistorialDisponibilidad.objects.count()
            count_disponibilidades = Disponibilidad.objects.count()
            
            HistorialDisponibilidad.objects.all().delete()
            Disponibilidad.objects.all().delete()
            
            # 2. Reconstruir SOLO propiedades con reservas
            propiedades_con_reservas = Propiedad.objects.filter(
                reservas__estado__in=['confirmada', 'confirmada_no_pagada']
            ).distinct()
            
            for propiedad in propiedades_con_reservas:
                # Obtener reservas de esta propiedad
                reservas = propiedad.reservas.filter(
                    estado__in=['confirmada', 'confirmada_no_pagada']
                ).order_by('fecha_inicio')
                
                if not reservas.exists():
                    continue
                
                # Definir rango total (6 meses antes de la primera, 6 meses después de la última)
                primera_reserva = reservas.first()
                ultima_reserva = reservas.last()
                
                fecha_inicio_total = primera_reserva.fecha_inicio - relativedelta(months=6)
                fecha_fin_total = ultima_reserva.fecha_fin + relativedelta(months=6)
                
                # Crear disponibilidades y historial fragmentados
                fecha_actual = fecha_inicio_total
                
                for reserva in reservas:
                    # Crear disponibilidad ANTES de la reserva (si hay espacio)
                    # 🏨 LÓGICA HOTELERA: El día de inicio de reserva está disponible hasta la tarde
                    if fecha_actual < reserva.fecha_inicio:
                        fecha_fin_libre = reserva.fecha_inicio  # SIN restar días
                        
                        # ❌ NO CREAR DISPONIBILIDADES AUTOMÁTICAS - Solo historial
                        # Crear historial
                        HistorialDisponibilidad.objects.create(
                            propiedad=propiedad,
                            fecha_inicio=fecha_actual,
                            fecha_fin=fecha_fin_libre,
                            estado='libre'
                        )
                    
                    # Crear historial para la RESERVA (fechas exactas)
                    HistorialDisponibilidad.objects.create(
                        propiedad=propiedad,
                        fecha_inicio=reserva.fecha_inicio,
                        fecha_fin=reserva.fecha_fin,
                        estado='reservado',
                        reserva=reserva
                    )
                    
                    # Mover fecha actual al día de fin de reserva
                    # 🏨 LÓGICA HOTELERA: El día de checkout está disponible desde la mañana
                    fecha_actual = reserva.fecha_fin  # SIN sumar días
                
                # Crear disponibilidad final
                if fecha_actual <= fecha_fin_total:
                    # ❌ NO CREAR DISPONIBILIDADES AUTOMÁTICAS - Solo historial
                    
                    # Crear historial
                    HistorialDisponibilidad.objects.create(
                        propiedad=propiedad,
                        fecha_inicio=fecha_actual,
                        fecha_fin=fecha_fin_total,
                        estado='libre'
                    )
            
            return JsonResponse({
                'success': True,
                'message': '🔥 LIMPIEZA BRUTAL completada. TODO reconstruido desde cero.',
                'historial_eliminado': count_historial,
                'disponibilidades_eliminadas': count_disponibilidades,
                'propiedades_procesadas': propiedades_con_reservas.count()
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error en limpieza brutal: {str(e)}'
            })
    
    return JsonResponse({'success': False, 'error': 'Método no permitido'})

def reconstruir_historial_propiedad(propiedad):
    """
    Función auxiliar para reconstruir el historial de una propiedad
    
    ✅ LÓGICA CORREGIDA: 
    - Las disponibilidades YA están fragmentadas correctamente
    - Solo necesitamos crear entradas del historial para disponibilidades + reservas
    - SIN duplicar períodos
    """
    print(f"🔄 Reconstruyendo historial para propiedad {propiedad.id}")
    
    # Obtener todas las disponibilidades (períodos libres ya fragmentados)
    disponibilidades = propiedad.disponibilidades.all().order_by('fecha_inicio')
    for disp in disponibilidades:
        HistorialDisponibilidad.objects.create(
            propiedad=propiedad,
            fecha_inicio=disp.fecha_inicio,
            fecha_fin=disp.fecha_fin,
            estado='libre'
        )
        print(f"   📅 Agregado período LIBRE: {disp.fecha_inicio} al {disp.fecha_fin}")
    
    # Obtener todas las reservas (períodos reservados)
    reservas = propiedad.reservas.filter(
        estado__in=['confirmada', 'confirmada_no_pagada']
    ).order_by('fecha_inicio')
    
    for reserva in reservas:
        HistorialDisponibilidad.objects.create(
            propiedad=propiedad,
            fecha_inicio=reserva.fecha_inicio,
            fecha_fin=reserva.fecha_fin,
            estado='reservado',
            reserva=reserva
        )
        print(f"   🎯 Agregado período RESERVADO: {reserva.fecha_inicio} al {reserva.fecha_fin} (Reserva #{reserva.id})")

@login_required
def editar_info_venta(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    info_venta, created = VentaPropiedad.objects.get_or_create(propiedad=propiedad)

    if request.method == 'POST':
        # Verificar si es una acción de desactivar (AJAX)
        accion = request.POST.get('accion')
        if accion == 'desactivar':
            try:
                info_venta.en_venta = False
                info_venta.save()
                return JsonResponse({
                    'success': True, 
                    'message': 'Venta desactivada correctamente'
                })
            except Exception as e:
                return JsonResponse({
                    'success': False, 
                    'error': str(e)
                })
        
        # Lógica normal del formulario (no AJAX)
        en_venta = request.POST.get('en_venta') == 'on'
        info_venta.en_venta = en_venta

        if en_venta:
            # Solo actualizar otros campos si está en venta
            info_venta.metros_cuadrados = request.POST.get('metros_cuadrados') or None
            info_venta.precio_venta = request.POST.get('precio_venta') or None
            info_venta.precio_autorizacion = request.POST.get('precio_autorizacion') or None
            info_venta.estado = request.POST.get('estado', 'disponible')
            info_venta.precio_expensas = request.POST.get('precio_expensas') or None
            info_venta.escribania = request.POST.get('escribania', '')
            info_venta.observaciones = request.POST.get('observaciones', '')

        info_venta.save()
        messages.success(request, 'Información de venta actualizada correctamente')
        return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad_id)

    return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad_id)

@login_required
def editar_info_meses(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    
    if request.method == 'POST':
        try:
            info_meses, created = AlquilerMeses.objects.get_or_create(propiedad=propiedad)
            
            info_meses.disponible = 'disponible' in request.POST
            if info_meses.disponible:
                info_meses.precio_mensual = request.POST.get('precio_mensual')
                info_meses.estado = request.POST.get('estado')
                info_meses.fecha_inicio = request.POST.get('fecha_inicio')
                info_meses.fecha_fin = request.POST.get('fecha_fin')
                info_meses.precio_expensas = request.POST.get('precio_expensas') or None
                info_meses.observaciones = request.POST.get('observaciones', '')
                
                # Si el estado es 'disponible', limpiamos las fechas
                if info_meses.estado == 'disponible':
                    info_meses.fecha_inicio = None
                    info_meses.fecha_fin = None
                # Solo establecemos fechas si el estado no es 'disponible'
                elif info_meses.estado in ['reservado', 'ocupado']:
                    info_meses.fecha_inicio = request.POST.get('fecha_inicio')
                    info_meses.fecha_fin = request.POST.get('fecha_fin')
            
            info_meses.save()
            messages.success(request, 'Información de alquiler 24 meses actualizada correctamente.')
        except Exception as e:
            messages.error(request, f'Error al actualizar la información: {str(e)}')
        
        return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad_id)
    
    return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad_id)

@login_required
def ventas(request):
    # Filtrar propiedades que tienen info de venta y están disponibles o reservadas
    propiedades_venta = Propiedad.objects.filter(
        info_venta__en_venta=True,
        info_venta__estado__in=['disponible', 'reservado']
    ).select_related('info_venta', 'sucursal').prefetch_related('imagenes')

    # Debug: Imprimir información sobre las propiedades y sus imágenes
    print("\n=== DEBUG IMÁGENES DE PROPIEDADES ===")
    print(f"MEDIA_ROOT: {settings.MEDIA_ROOT}")
    print(f"MEDIA_URL: {settings.MEDIA_URL}")
    print(f"DEBUG: {settings.DEBUG}")
    print(f"AWS_ACCESS_KEY_ID presente: {'AWS_ACCESS_KEY_ID' in os.environ}")
    print(f"AWS_STORAGE_BUCKET_NAME presente: {'AWS_STORAGE_BUCKET_NAME' in os.environ}")
    
    for propiedad in propiedades_venta:
        print(f"\nPropiedad ID: {propiedad.id}")
        print(f"Dirección: {propiedad.direccion}")
        imagenes = propiedad.imagenes.all()
        print(f"Número de imágenes: {imagenes.count()}")
        for img in imagenes:
            print(f"- Imagen ID: {img.id}")
            print(f"  URL: {img.imagen.url if img.imagen else 'No hay URL'}")
            print(f"  Nombre archivo: {img.imagen.name if img.imagen else 'No hay archivo'}")
            if img.imagen:
                ruta_completa = os.path.join(settings.MEDIA_ROOT, img.imagen.name)
                print(f"  ¿Archivo existe localmente?: {os.path.exists(ruta_completa)}")
    print("=== FIN DEBUG ===\n")

    # Calcular los contadores
    total_propiedades = propiedades_venta.count()
    propiedades_disponibles = propiedades_venta.filter(info_venta__estado='disponible').count()
    propiedades_reservadas = propiedades_venta.filter(info_venta__estado='reservado').count()

    # Aplicar filtros de búsqueda si existen
    busqueda = request.GET.get('busqueda', '')
    if busqueda:
        propiedades_venta = propiedades_venta.filter(
            Q(direccion__icontains=busqueda) |
            Q(id__icontains=busqueda)
        )

    estado = request.GET.get('estado', '')
    if estado:
        propiedades_venta = propiedades_venta.filter(info_venta__estado=estado)

    # Filtro por ambientes
    ambientes = request.GET.get('ambientes', '')
    if ambientes:
        if ambientes == '5':  # 5+ ambientes
            propiedades_venta = propiedades_venta.filter(ambientes__gte=5)
        else:
            propiedades_venta = propiedades_venta.filter(ambientes=int(ambientes))

    # Filtros avanzados
    tipo_inmueble = request.GET.get('tipo_inmueble', '')
    if tipo_inmueble:
        propiedades_venta = propiedades_venta.filter(tipo_inmueble=tipo_inmueble)

    vista = request.GET.get('vista', '')
    if vista:
        propiedades_venta = propiedades_venta.filter(vista=vista)

    valoracion = request.GET.get('valoracion', '')
    if valoracion:
        propiedades_venta = propiedades_venta.filter(valoracion=int(valoracion))

    # Filtros de precio
    precio_min = request.GET.get('precio_min', '')
    if precio_min:
        propiedades_venta = propiedades_venta.filter(info_venta__precio_venta__gte=float(precio_min))

    precio_max = request.GET.get('precio_max', '')
    if precio_max:
        propiedades_venta = propiedades_venta.filter(info_venta__precio_venta__lte=float(precio_max))

    # Filtros de características (checkboxes)
    caracteristicas_filtros = [
        'amoblado', 'cochera', 'wifi', 'piscina', 'patio', 'parrilla', 
        'terraza', 'balcon', 'vista_al_Mar', 'a_estrenar', 'seguridad', 'apto_credito'
    ]
    
    for caracteristica in caracteristicas_filtros:
        if request.GET.get(caracteristica):
            # Filtrar propiedades que tienen esta característica marcada como True
            filter_kwargs = {caracteristica: True}
            propiedades_venta = propiedades_venta.filter(**filter_kwargs)

    context = {
        'propiedades': propiedades_venta,
        'busqueda': busqueda,
        'estado_filtro': estado,
        'ambientes_filtro': ambientes,
        'estados': VentaPropiedad.ESTADO_CHOICES,
        'telefono_empresa': '5492235916229',
        'total_propiedades': total_propiedades,
        'propiedades_disponibles': propiedades_disponibles,
        'propiedades_reservadas': propiedades_reservadas,
        # Filtros avanzados para mantener en el contexto
        'tipo_inmueble_filtro': tipo_inmueble,
        'vista_filtro': vista,
        'valoracion_filtro': valoracion,
        'precio_min_filtro': precio_min,
        'precio_max_filtro': precio_max,
        # Características seleccionadas
        'caracteristicas_seleccionadas': {
            caracteristica: request.GET.get(caracteristica, False) 
            for caracteristica in caracteristicas_filtros
        }
    }
    
    return render(request, 'inmobiliaria/propiedades/ventas.html', context)

@login_required
def alquileres_24_meses(request):
    # Filtrar propiedades que tienen alquiler por 24 meses activado
    propiedades_meses = Propiedad.objects.filter(
        info_meses__disponible=True,  # Solo propiedades con alquiler 24 meses activado
        info_meses__estado='disponible'  # Por defecto mostrar solo las disponibles
    ).select_related(
        'info_meses', 
        'sucursal'
    ).prefetch_related('imagenes')

    # Aplicar filtros de búsqueda si existen
    busqueda = request.GET.get('busqueda', '')
    if busqueda:
        propiedades_meses = propiedades_meses.filter(
            Q(direccion__icontains=busqueda) |
            Q(id__icontains=busqueda)
        )

    # Si se selecciona un estado específico, sobreescribir el filtro por defecto
    estado = request.GET.get('estado', '')
    if estado:
        propiedades_meses = Propiedad.objects.filter(
            info_meses__disponible=True,
            info_meses__estado=estado
        ).select_related(
            'info_meses', 
            'sucursal'
        ).prefetch_related('imagenes')

    context = {
        'propiedades': propiedades_meses,
        'busqueda': busqueda,
        'estado_filtro': estado or 'disponible',  # Si no hay estado seleccionado, marcar 'disponible'
        'estados': AlquilerMeses.ESTADO_CHOICES,
        'inquilinos': Inquilino.objects.filter(sucursal=request.user.sucursal).order_by('apellido', 'nombre'),
    }
    
    return render(request, 'inmobiliaria/propiedades/alquileres_24_meses.html', context)

def generar_mensaje_whatsapp(propiedad):
    # Formatear el mensaje
    mensaje = f"""
*Propiedad en {propiedad.direccion}*
{propiedad.get_tipo_inmueble_display()}
{propiedad.ambientes} ambientes
{propiedad.metros_cuadrados}m²

Precio: U$D {propiedad.precios.filter(tipo_precio='VENTA').first().monto if propiedad.precios.filter(tipo_precio='VENTA').exists() else 'Consultar'}

Para más información: https://tu-sitio.com/propiedad/{propiedad.id}
"""
    # Codificar el mensaje para URL
    from urllib.parse import quote
    return quote(mensaje)

@login_required
def iniciar_compra(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    
    if request.method == 'POST':
        try:
            # Verificar que la propiedad esté disponible
            if propiedad.info_venta.estado != 'disponible':
                messages.error(request, 'La propiedad no está disponible para la compra.')
                return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad_id)
            
            # Eliminar cualquier venta pendiente anterior
            VentaPropiedad.objects.filter(
                propiedad=propiedad,
                estado='pendiente'
            ).delete()
            
            # Crear la nueva venta
            venta = VentaPropiedad.objects.create(
                propiedad=propiedad,
                precio_venta=propiedad.info_venta.precio_venta,
                estado='pendiente'
            )
            
            # Actualizar estado de la propiedad
            propiedad.info_venta.estado = 'reservado'
            propiedad.info_venta.save()
            
            messages.success(request, 'Se ha iniciado el proceso de compra correctamente.')
            return redirect('inmobiliaria:cargar_cliente_venta', venta_id=venta.id)
            
        except Exception as e:
            messages.error(request, f'Error al iniciar la compra: {str(e)}')
            return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad_id)
    
    return render(request, 'inmobiliaria/propiedades/iniciar_compra.html', {
        'propiedad': propiedad
    })

@login_required
def abrir_caja(request):
    sucursal = request.user.sucursal
    
    # Verificar si ya hay una caja abierta
    if Caja.objects.filter(sucursal=sucursal, estado='abierta').exists():
        messages.error(request, "Ya hay una caja abierta para esta sucursal")
        return redirect('inmobiliaria:gestionar_caja')
    
    try:
        # Obtener el último número de caja para esta sucursal
        ultima_caja = Caja.objects.filter(
            sucursal=sucursal
        ).order_by('-numero').first()
        
        siguiente_numero = (int(ultima_caja.numero) + 1) if ultima_caja else 1
        
        # Crear nueva caja
        caja = Caja.objects.create(
            sucursal=sucursal,
            numero=siguiente_numero,
            estado='abierta',
            fecha_apertura=timezone.now(),
            usuario_apertura=request.user,
            saldo_inicial=0  # O el valor que corresponda
        )
        
        messages.success(request, f'Caja #{caja.numero} abierta exitosamente')
        return redirect('inmobiliaria:gestionar_caja')
        
    except Exception as e:
        messages.error(request, f'Error al abrir la caja: {str(e)}')
        return redirect('inmobiliaria:gestionar_caja')

@login_required
def ver_caja(request, caja_id):
    try:
        caja = Caja.objects.get(id=caja_id, sucursal=request.user.sucursal)
        return render(request, 'inmobiliaria/caja/ver_caja.html', {'caja': caja})
    except Caja.DoesNotExist:
        messages.error(request, 'Caja no encontrada')
        return redirect('inmobiliaria:lista_cajas')
    except Exception as e:
        print("Error en ver_caja:")
        print(traceback.format_exc())
        messages.error(request, f'Error: {str(e)}')
        return redirect('inmobiliaria:lista_cajas')

@login_required
def lista_cajas(request):
    # Obtener la sucursal del usuario logueado
    sucursal = request.user.sucursal
    
    # Obtener las cajas de la sucursal
    cajas = Caja.objects.filter(sucursal=sucursal).order_by('-fecha_apertura')
    
    # Obtener la caja abierta actual (si existe)
    caja_actual = cajas.filter(estado='abierta').first()
    
    context = {
        'cajas': cajas,
        'caja_actual': caja_actual,
    }
    
    return render(request, 'inmobiliaria/caja/lista_cajas.html', context)

@login_required
def gestionar_caja(request):
    try:
        # Obtener la sucursal del usuario logueado
        sucursal = request.user.sucursal
        
        # Verificar si hay una caja abierta para esta sucursal
        caja_actual = Caja.objects.filter(
            sucursal=sucursal,
            estado='abierta'
        ).first()
        
        # Obtener últimos movimientos si hay caja abierta
        movimientos = []
        if caja_actual:
            movimientos = MovimientoCaja.objects.filter(
                caja=caja_actual
            ).order_by('-fecha')[:10]  # Últimos 10 movimientos
        
        # Obtener historial de cajas de la sucursal
        historial_cajas = Caja.objects.filter(
            sucursal=sucursal
        ).order_by('-fecha_apertura')[:5]  # Últimas 5 cajas
        
        context = {
            'sucursal': sucursal,
            'caja_actual': caja_actual,
            'movimientos': movimientos,
            'historial_cajas': historial_cajas,
        }
        
        return render(request, 'inmobiliaria/caja/gestionar_caja.html', context)
        
    except Exception as e:
        messages.error(request, f'Error al acceder a la caja: {str(e)}')
        return redirect('inmobiliaria:dashboard')



@login_required
def nuevo_movimiento(request, numero_caja=None):
    try:
        # Si no se proporciona número de caja, buscar la caja abierta
        if numero_caja is None:
            caja = Caja.objects.filter(
                sucursal=request.user.sucursal,
                estado='abierta'
            ).first()
            if not caja:
                messages.error(request, "No hay una caja abierta")
                return redirect('inmobiliaria:lista_cajas')
            numero_caja = caja.numero
        else:
            caja = get_object_or_404(Caja, numero=numero_caja, sucursal=request.user.sucursal)
            if caja.estado != 'abierta':
                messages.error(request, "La caja está cerrada")
                return redirect('inmobiliaria:lista_cajas')

        if request.method == 'POST':
            form = MovimientoCajaForm(request.POST)
            if form.is_valid():
                movimiento = form.save(commit=False)
                movimiento.caja = caja
                movimiento.empleado = request.user
                movimiento.sucursal = request.user.sucursal
                movimiento.save()
                messages.success(request, 'Movimiento registrado correctamente')
                return redirect('inmobiliaria:detalle_caja', numero=caja.numero)
        else:
            form = MovimientoCajaForm()

        context = {
            'form': form,
            'caja': caja
        }
        return render(request, 'inmobiliaria/caja/nuevo_movimiento.html', context)
    except Exception as e:
        messages.error(request, f'Error al procesar el movimiento: {str(e)}')
        return redirect('inmobiliaria:lista_cajas')

@login_required
def eliminar_movimiento(request, movimiento_id):
    movimiento = get_object_or_404(MovimientoCaja, id=movimiento_id, sucursal=request.user.sucursal)
    
    # Actualizar saldo de la caja
    caja = Caja.objects.get(sucursal=request.user.sucursal)
    if movimiento.tipo.tipo == TipoMovimientoCajaEnum.INGRESO:
        caja.saldo -= movimiento.monto
    else:
        caja.saldo += movimiento.monto
    
    caja.save()
    movimiento.delete()
    
    messages.success(request, 'Movimiento eliminado correctamente.')
    return redirect('inmobiliaria:caja')

@login_required
def caja(request):
    # Obtener la caja actual
    sucursal = request.user.sucursal
    caja = Caja.objects.filter(sucursal=sucursal, estado='abierta').first()
    
    if not caja:
        messages.error(request, "No hay una caja abierta")
        return redirect('inmobiliaria:gestionar_caja')
    
    # Obtener todos los movimientos de la caja
    movimientos = MovimientoCaja.objects.filter(
        caja=caja
    ).order_by('-fecha')
    
    # Calcular totales
    totales = {
        'efectivo': sum(m.monto_efectivo for m in movimientos),
        'cheques': sum(m.monto_cheque for m in movimientos),
        'tarjetas': sum(m.monto_tarjeta for m in movimientos),
        'depositos': sum(m.monto_deposito for m in movimientos),
    }
    
    # Calcular saldos
    ingresos = movimientos.filter(tipo='ingreso')
    egresos = movimientos.filter(tipo='egreso')
    
    saldos = {
        'anterior': caja.saldo_inicial,
        'ingresos': sum(m.monto_efectivo + m.monto_cheque + m.monto_tarjeta + m.monto_deposito + m.monto_qr for m in ingresos),
        'egresos': sum(m.monto_efectivo + m.monto_cheque + m.monto_tarjeta + m.monto_deposito + m.monto_qr for m in egresos),
        'anterior_total': caja.saldo_inicial,
        'ingresos_total': sum(m.monto_efectivo + m.monto_cheque + m.monto_tarjeta + m.monto_deposito + m.monto_qr for m in ingresos),
        'egresos_total': sum(m.monto_efectivo + m.monto_cheque + m.monto_tarjeta + m.monto_deposito + m.monto_qr for m in egresos),
    }
    
    # Calcular saldo del día y total
    saldos['dia'] = saldos['ingresos'] - saldos['egresos']
    saldos['total'] = saldos['anterior'] + saldos['dia']
    
    context = {
        'caja': caja,
        'movimientos': movimientos,
        'totales': totales,
        'saldos': saldos,
    }
    
    return render(request, 'inmobiliaria/caja/caja.html', context)

@login_required
def detalle_caja(request, numero):
    # Obtener la caja específica
    caja = get_object_or_404(Caja, numero=numero, sucursal=request.user.sucursal)
    
    # Obtener todos los movimientos de la caja
    movimientos = MovimientoCaja.objects.filter(caja=caja).order_by('-fecha')
    
    # Calcular totales por tipo de movimiento
    ingresos = movimientos.filter(tipo=TipoMovimientoCajaEnum.INGRESO)
    egresos = movimientos.filter(tipo=TipoMovimientoCajaEnum.EGRESO)
    
    # Calcular totales para ingresos (valores positivos)
    totales_ingresos = {
        'efectivo': sum(m.monto_efectivo for m in ingresos),
        'cheque': sum(m.monto_cheque for m in ingresos),
        'tarjeta': sum(m.monto_tarjeta for m in ingresos),
        'deposito': sum(m.monto_deposito for m in ingresos),
        'deposito_galicia': sum(m.monto_deposito for m in ingresos.filter(destino_deposito='galicia')),
        'deposito_mp': sum(m.monto_deposito for m in ingresos.filter(destino_deposito='mp')),
        'total': sum(m.monto_total for m in ingresos)
    }
    
    # Calcular totales para egresos (valores positivos)
    totales_egresos = {
        'efectivo': sum(m.monto_efectivo for m in egresos),
        'cheque': sum(m.monto_cheque for m in egresos),
        'tarjeta': sum(m.monto_tarjeta for m in egresos),
        'deposito': sum(m.monto_deposito for m in egresos),
        'deposito_galicia': sum(m.monto_deposito for m in egresos.filter(destino_deposito='galicia')),
        'deposito_mp': sum(m.monto_deposito for m in egresos.filter(destino_deposito='mp')),
        'total': sum(m.monto_total for m in egresos)
    }
    
    # Calcular saldo actual por método de pago (ingresos - egresos)
    saldo_actual = {
        'efectivo': totales_ingresos['efectivo'] - totales_egresos['efectivo'],
        'cheque': totales_ingresos['cheque'] - totales_egresos['cheque'],
        'tarjeta': totales_ingresos['tarjeta'] - totales_egresos['tarjeta'],
        'deposito': totales_ingresos['deposito'] - totales_egresos['deposito'],
        'deposito_galicia': totales_ingresos['deposito_galicia'] - totales_egresos['deposito_galicia'],
        'deposito_mp': totales_ingresos['deposito_mp'] - totales_egresos['deposito_mp']
    }
    
    # Calcular saldo total
    saldo_total = (
        totales_ingresos['total'] -  # Suma todos los ingresos
        totales_egresos['total']     # Resta todos los egresos
    )
    
    # Preparar el contexto con todos los totales
    totales = {
        'ingresos': totales_ingresos,
        'egresos': totales_egresos,
        'saldo_actual': saldo_actual,
        'saldo_total': saldo_total
    }
    
    context = {
        'caja': caja,
        'movimientos': movimientos,
        'totales': totales,
        'es_saldo_positivo': saldo_total >= 0  # Para el color del saldo
    }
    
    return render(request, 'inmobiliaria/caja/detalle_caja.html', context)

@login_required
def nuevo_movimiento(request, numero_caja=None):
    if numero_caja:
        caja = get_object_or_404(Caja, numero=numero_caja, sucursal=request.user.sucursal, estado='abierta')
    else:
        caja = get_object_or_404(Caja, sucursal=request.user.sucursal, estado='abierta')
    
    if request.method == 'POST':
        try:
            # Procesar fechas
            fecha_desde = None
            fecha_hasta = None
            try:
                if request.POST.get('fecha_desde'):
                    fecha_desde = datetime.strptime(request.POST.get('fecha_desde'), '%Y-%m-%d').date()
                if request.POST.get('fecha_hasta'):
                    fecha_hasta = datetime.strptime(request.POST.get('fecha_hasta'), '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, 'Formato de fecha inválido')
                return render(request, 'inmobiliaria/caja/nuevo_movimiento.html', {
                    'caja': caja,
                    'fecha_actual': timezone.now()
                })

            # Crear el movimiento con valores iniciales
            movimiento = MovimientoCaja(
                caja=caja,
                tipo=request.POST.get('tipo'),
                tipo_comprobante=request.POST.get('tipo_comprobante'),
                numero_liquidacion=request.POST.get('numero_liquidacion', ''),
                concepto=request.POST.get('concepto_id', ''),
                propiedad_id=request.POST.get('propiedad_id') if request.POST.get('propiedad_id') else None,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                monto_efectivo=0,
                monto_cheque=0,
                monto_tarjeta=0,
                monto_deposito=0,
                destino_deposito=request.POST.get('destino_deposito'),
                a_descontar=request.POST.get('a_descontar', 'oficina'),
                sucursal=request.user.sucursal,
                empleado=request.user
            )

            # Procesar los montos
            try:
                movimiento.monto_efectivo = float(request.POST.get('monto_efectivo', '0').replace(',', '.') or '0')
                movimiento.monto_cheque = float(request.POST.get('monto_cheque', '0').replace(',', '.') or '0')
                movimiento.monto_tarjeta = float(request.POST.get('monto_tarjeta', '0').replace(',', '.') or '0')
                movimiento.monto_deposito = float(request.POST.get('monto_deposito', '0').replace(',', '.') or '0')
            except (ValueError, TypeError):
                messages.error(request, 'Error en los montos ingresados')
                return render(request, 'inmobiliaria/caja/nuevo_movimiento.html', {
                    'caja': caja,
                    'fecha_actual': timezone.now()
                })

            # Guardar el movimiento
            movimiento.save()

            messages.success(request, 'Movimiento creado exitosamente')
            return redirect('inmobiliaria:caja')

        except Exception as e:
            messages.error(request, f'Error al crear el movimiento: {str(e)}')
            return render(request, 'inmobiliaria/caja/nuevo_movimiento.html', {
                'caja': caja,
                'fecha_actual': timezone.now()
            })
    
    context = {
        'caja': caja,
        'fecha_actual': timezone.now(),
    }
    return render(request, 'inmobiliaria/caja/nuevo_movimiento.html', context)

@login_required
def cerrar_caja(request, numero_caja):
    caja = get_object_or_404(Caja, numero=numero_caja, sucursal=request.user.sucursal, estado='abierta')
    
    if request.method == 'POST':
        observaciones = request.POST.get('observaciones', '')
        saldo_final = caja.get_saldo_actual()
        
        try:
            # Cerrar la caja actual
            caja.fecha_cierre = timezone.now()
            caja.estado = 'cerrada'
            caja.saldo_final = saldo_final
            caja.usuario_cierre = request.user
            caja.observaciones_cierre = observaciones
            caja.save()
            
            # 🚀 APERTURA AUTOMÁTICA DE NUEVA CAJA
            # Obtener el siguiente número de caja para esta sucursal
            siguiente_numero = caja.numero + 1
            
            # Crear nueva caja automáticamente
            nueva_caja = Caja.objects.create(
                sucursal=request.user.sucursal,
                numero=siguiente_numero,
                estado='abierta',
                fecha_apertura=timezone.now(),
                usuario_apertura=request.user,
                saldo_inicial=saldo_final,  # El saldo final de la caja anterior se convierte en inicial de la nueva
                observaciones_apertura=f'Apertura automática tras cierre de Caja #{caja.numero}'
            )
            
            messages.success(request, f'✅ Caja #{caja.numero} cerrada exitosamente')
            messages.success(request, f'🚀 Nueva Caja #{nueva_caja.numero} abierta automáticamente con saldo inicial: ${saldo_final:,.0f}')
            return redirect('inmobiliaria:lista_cajas')
            
        except Exception as e:
            messages.error(request, f'Error al cerrar/abrir caja: {str(e)}')
            return redirect('inmobiliaria:lista_cajas')
    
    return render(request, 'inmobiliaria/caja/cerrar_caja.html', {'caja': caja})

@login_required
def nuevo_registro(request):
    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            registro = form.save(commit=False)
            registro.sucursal = request.user.sucursal
            registro.empleado = request.user
            registro.interno_caja = f"IC-{timezone.now().strftime('%Y%m%d')}-{Registro.objects.count() + 1}"
            registro.save()
            
            messages.success(request, 'Registro creado correctamente.')
            return redirect('inmobiliaria:caja')
    else:
        form = RegistroForm()
    
    return render(request, 'inmobiliaria/caja/nuevo_registro.html', {
        'form': form,
        'caja_actual': request.user.sucursal.caja_set.filter(estado='abierta').first()
    })

@login_required
def nuevo_concepto(request):
    """Vista para crear un nuevo concepto desde Ajax con código único"""
    if request.method == 'POST':
        try:
            nombre = request.POST.get('nombre')
            tipo = request.POST.get('tipo', 'general')
            sucursal = request.user.sucursal
            
            if not nombre:
                return JsonResponse({'error': 'El nombre del concepto es obligatorio'}, status=400)
            
            # Generar código único para el concepto (puedes personalizar esto)
            ultimo_concepto = Concepto.objects.filter(sucursal=sucursal).order_by('-id').first()
            codigo = f"C{(ultimo_concepto.id + 1 if ultimo_concepto else 1):04d}"
            
            # Crear el concepto
            concepto = Concepto.objects.create(
                nombre=nombre,
                tipo=tipo,
                codigo=codigo,
                sucursal=sucursal
            )
            
            return JsonResponse({
                'id': concepto.id,
                'nombre': concepto.nombre,
                'codigo': concepto.codigo,
                'success': True
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)

@login_required
def buscar_cuentas(request):
    search = request.GET.get('term', '')
    cuentas = Cuenta.objects.filter(
        Q(numero__icontains=search) | 
        Q(nombre__icontains=search)
    )[:10]
    
    results = [{'id': c.id, 'text': f"{c.numero} - {c.nombre}"} for c in cuentas]
    return JsonResponse({'results': results})



@login_required
@require_POST
def crear_concepto(request):
    try:
        nombre = request.POST.get('nombre')
        if not nombre:
            return JsonResponse({'error': 'El nombre es requerido'}, status=400)
        
        concepto = Concepto.objects.create(nombre=nombre)
        return JsonResponse({
            'id': concepto.id,
            'nombre': concepto.nombre
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_POST
def crear_propiedad(request):
    try:
        direccion = request.POST.get('direccion')
        if not direccion:
            return JsonResponse({'error': 'La dirección es requerida'}, status=400)
        
        propiedad = Propiedad.objects.create(direccion=direccion)
        return JsonResponse({
            'id': propiedad.id,
            'direccion': propiedad.direccion
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# Función para búsqueda de propiedades en Select2 (nueva función)
@login_required
def buscar_propiedades_select2(request):
    """Vista para el autocompletado de Select2"""
    try:
        term = request.GET.get('term', '')
        
        # En caso de que user.sucursal cause problemas
        sucursal_vendedor = None
        if hasattr(request.user, 'sucursal'):
            sucursal_vendedor = request.user.sucursal
            
        # Consulta más segura
        propiedades = Propiedad.objects.all()
        if sucursal_vendedor:
            propiedades = propiedades.filter(sucursal=sucursal_vendedor)
            
        if term:
            propiedades = propiedades.filter(
                Q(direccion__icontains=term) | 
                Q(id__icontains=term)
            )
        
        propiedades = propiedades[:10]
        
        results = []
        for prop in propiedades:
            results.append({
                'id': prop.id,
                'text': f"{prop.direccion}"
            })
        
        return JsonResponse({'results': results})
    except Exception as e:
        import traceback
        print(f"Error en buscar_propiedades_select2: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({'results': [], 'error': str(e)})

# Asegúrate de que tu función original de alquiler por día siga intacta
# Mantén su nombre y comportamiento original

# Una versión súper simple que no debería fallar
def simple_select2(request):
    """Versión simplificada para debuggear"""
    return JsonResponse({'results': []})

@login_required
def crear_cuenta(request):
    """Vista para crear una nueva cuenta desde Ajax"""
    if request.method == 'POST':
        try:
            nombre = request.POST.get('nombre')
            tipo = request.POST.get('tipo')
            numero_cuenta = request.POST.get('numero_cuenta', '')
            cbu = request.POST.get('cbu', '')
            
            if not nombre:
                return JsonResponse({'error': 'El nombre de la cuenta es obligatorio'}, status=400)
            
            # Crear la cuenta
            cuenta = Cuenta.objects.create(
                nombre=nombre,
                tipo=tipo,
                numero_cuenta=numero_cuenta,
                cbu=cbu,
                sucursal=request.user.sucursal
            )
            
            return JsonResponse({
                'id': cuenta.id,
                'nombre': cuenta.nombre,
                'success': True
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Método no permitido'}, status=405)

@login_required
def buscar_productores(request):
    """Vista para buscar vendedores/productores"""
    term = request.GET.get('term', '')
    
    # IMPORTANTE: Depuración para verificar la consulta
    print(f"Buscando vendedores con término: '{term}'")
    
    try:
        # Buscar TODOS los vendedores sin filtros de sucursal
        if not term or len(term) < 2:
            vendedores = Vendedor.objects.all()[:15]
        else:
            vendedores = Vendedor.objects.filter(
                Q(nombre__icontains=term) | 
                Q(id__icontains=term)
            )[:15]
        
        # Imprimir resultados para depuración
        print(f"Encontrados {vendedores.count()} vendedores")
        for v in vendedores:
            print(f"Vendedor: ID={v.id}, Nombre={v.nombre}")
        
        # Formatear resultados
        resultados = []
        for v in vendedores:
            resultados.append({
                'id': v.id,
                'nombre': v.nombre,
                'telefono': getattr(v, 'telefono', '')
            })
        
        return JsonResponse({
            'success': True,
            'resultados': resultados
        })
    
    except Exception as e:
        print(f"Error en buscar_productores: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        })

def conceptos_list(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        conceptos = Concepto.objects.all().order_by('id')
        data = {
            'conceptos': [
                {'id': c.id, 'nombre': c.nombre}
                for c in conceptos
            ]
        }
        return JsonResponse(data)
    # Si acceden por navegador normal, redirigir a la gestión completa
    return redirect('inmobiliaria:gestionar_conceptos')

def propietario_cuentas(request):
    propietario_id = request.GET.get('propietario_id')
    if not propietario_id:
        return JsonResponse({'cuentas': []})
    cuentas = CuentaBancaria.objects.filter(propietario_id=propietario_id)
    data = {
        'cuentas': [
            {'id': c.id, 'numero': c.numero, 'alias': getattr(c, 'alias', '')}
            for c in cuentas
        ]
    }
    return JsonResponse(data)

def guardar_movimiento(request):
    if request.method == 'POST':
        propietario_id = request.POST.get('propietario')
        cuenta_bancaria = request.POST.get('cuenta')
        concepto_id = request.POST.get('concepto')
        monto = request.POST.get('monto')
        # ...otros campos...

        # 1. Actualizar la cuenta bancaria del propietario
        if propietario_id and cuenta_bancaria is not None:
            try:
                propietario = Propietario.objects.get(id=propietario_id)
                propietario.cuenta_bancaria = cuenta_bancaria
                propietario.save()
            except Propietario.DoesNotExist:
                messages.error(request, "No se encontró el propietario seleccionado.")
                return redirect('inmobiliaria:nuevo_movimiento')

        # 2. Guardar el movimiento (ajusta los campos según tu modelo)
        movimiento = Movimiento.objects.create(
            propietario_id=propietario_id,
            cuenta=cuenta_bancaria,
            concepto_id=concepto_id,
            monto=monto,
            # ...otros campos...
        )

        messages.success(request, "Movimiento y cuenta bancaria guardados correctamente.")
        return redirect('inmobiliaria:gestionar_caja')  # O la URL que corresponda

    # Si GET, muestra el formulario normalmente
    # ...código para mostrar el formulario...

def propiedades_propietario(request, propietario_id):
    propietario = get_object_or_404(Propietario, pk=propietario_id)

    propiedades = (
        Propiedad.objects
        .filter(propietario=propietario)
        .order_by("numero_por_propietario")      # ← clave
    )

    return render(
        request,
        "inmobiliaria/propietarios/propiedades_propietario.html",
        {"propietario": propietario, "propiedades": propiedades},
    )

@require_POST
def imagen_eliminar(request, imagen_id):
    """
    Elimina una imagen (botón rojo). Devuelve JSON {success: True}
    """
    imagen = get_object_or_404(ImagenPropiedad, pk=imagen_id)
    imagen.delete()
    return JsonResponse({"success": True})


@require_POST
def reordenar_imagenes(request, propiedad_id):
    """
    Recibe via AJAX la lista nueva de órdenes y actualiza la BD.
    """
    ordenes = json.loads(request.POST.get("ordenes", "[]"))
    with transaction.atomic():
        for item in ordenes:
            ImagenPropiedad.objects.filter(
                pk=item["id"], propiedad_id=propiedad_id
            ).update(orden=item["orden"])
    return JsonResponse({"success": True})

def obtener_caracteristicas_propiedad(request):
    propiedad_id = request.GET.get('propiedad_id')
    
    if not propiedad_id:
        return JsonResponse({'error': 'ID de propiedad requerido'}, status=400)
    
    try:
        propiedad = Propiedad.objects.get(id=propiedad_id)
        
        caracteristicas = []
        
        # Mapear los campos booleanos a nombres legibles
        caracteristicas_map = {
            'amoblado': 'Amoblado',
            'cochera': 'Cochera',
            'tv_smart': 'TV Smart',
            'wifi': 'WiFi',
            'dependencia': 'Dependencia',
            'patio': 'Patio',
            'parrilla': 'Parrilla',
            'piscina': 'Piscina',
            'reciclado': 'Reciclado',
            'a_estrenar': 'A Estrenar',
            'terraza': 'Terraza',
            'balcon': 'Balcón'
        }
        
        # Revisar cada característica y agregar las que sean True
        for campo, nombre in caracteristicas_map.items():
            if getattr(propiedad, campo, False):
                caracteristicas.append(nombre)
        
        return JsonResponse({
            'caracteristicas': caracteristicas,
            'propiedad_id': propiedad_id
        })
        
    except Propiedad.DoesNotExist:
        return JsonResponse({'error': 'Propiedad no encontrada'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def editar_sucursal(request, sucursal_id):
    sucursal = get_object_or_404(Sucursal, id=sucursal_id)
    
    if request.method == 'POST':
        form = SucursalForm(request.POST, instance=sucursal)
        if form.is_valid():
            form.save()
            messages.success(request, f'Sucursal "{sucursal.nombre}" actualizada exitosamente.')
            return redirect('inmobiliaria:detalle_sucursal', sucursal_id=sucursal.id)
    else:
        form = SucursalForm(instance=sucursal)
    
    return render(request, 'inmobiliaria/sucursales/editar.html', {
        'form': form,
        'sucursal': sucursal,
        'titulo': 'Editar Sucursal'
    })

@login_required
def sucursales(request):
    """Lista todas las sucursales"""
    # Debug: Imprimir información del usuario
    print(f"Usuario: {request.user}")
    print(f"Nivel del usuario: {request.user.nivel}")
    print(f"¿Es administrador?: {request.user.nivel == 4}")
    
    # Total de sucursales en la BD
    total_sucursales = Sucursal.objects.all().count()
    print(f"Total de sucursales en BD: {total_sucursales}")
    
    # Mostrar todas las sucursales solo si es administrador (nivel 4)
    if request.user.nivel == 4:
        sucursales = Sucursal.objects.all()
        print(f"Usuario es administrador - mostrando {sucursales.count()} sucursales")
    else:
        # Solo mostrar la sucursal del usuario actual
        sucursales = Sucursal.objects.filter(id=request.user.sucursal.id)
        print(f"Usuario NO es administrador - mostrando {sucursales.count()} sucursales")
    
    return render(request, 'inmobiliaria/sucursal/lista.html', {
        'sucursales': sucursales
    })

@login_required
def sucursal_detalle(request, sucursal_id):
    """Muestra los detalles de una sucursal"""
    sucursal = get_object_or_404(Sucursal, id=sucursal_id)
    
    # Verificar permisos
    if not request.user.is_superuser and request.user.sucursal != sucursal:
        messages.error(request, 'No tienes permisos para ver esta sucursal.')
        return redirect('inmobiliaria:sucursales')
    
    return render(request, 'inmobiliaria/sucursal/detalle.html', {
        'sucursal': sucursal
    })

@login_required
def editar_sucursal(request, sucursal_id):
    """Edita una sucursal existente"""
    sucursal = get_object_or_404(Sucursal, id=sucursal_id)
    
    # Verificar permisos - solo administrador (nivel 4)
    if request.user.nivel != 4:
        messages.error(request, 'No tienes permisos para editar sucursales.')
        return redirect('inmobiliaria:sucursal_detalle', sucursal_id=sucursal.id)
    
    if request.method == 'POST':
        form = SucursalForm(request.POST, instance=sucursal)
        if form.is_valid():
            sucursal = form.save()
            messages.success(request, f'Sucursal "{sucursal.nombre}" actualizada exitosamente.')
            return redirect('inmobiliaria:sucursal_detalle', sucursal_id=sucursal.id)
    else:
        form = SucursalForm(instance=sucursal)
    
    return render(request, 'inmobiliaria/sucursal/editar.html', {
        'form': form,
        'sucursal': sucursal,
        'titulo': f'Editar Sucursal: {sucursal.nombre}'
    })

@login_required
def crear_sucursal(request):
    """Crea una nueva sucursal"""
    # Solo administrador (nivel 4)
    if request.user.nivel != 4:
        messages.error(request, 'No tienes permisos para crear sucursales.')
        return redirect('inmobiliaria:sucursales')
    
    if request.method == 'POST':
        form = SucursalForm(request.POST)
        if form.is_valid():
            sucursal = form.save()
            messages.success(request, f'Sucursal "{sucursal.nombre}" creada exitosamente.')
            return redirect('inmobiliaria:sucursal_detalle', sucursal_id=sucursal.id)
    else:
        form = SucursalForm()
    
    return render(request, 'inmobiliaria/sucursal/crear_sucursal.html', {
        'form': form,
        'titulo': 'Nueva Sucursal'
    })

@login_required
@require_http_methods(["GET"])
def obtener_fotos_propiedad(request, propiedad_id):
    """Obtiene las fotos de una propiedad específica"""
    print(f"=== OBTENER FOTOS PROPIEDAD ===")
    print(f"Propiedad ID: {propiedad_id}")
    
    try:
        propiedad = get_object_or_404(Propiedad, id=propiedad_id)
        print(f"Propiedad encontrada: {propiedad}")
        
        # Obtener todas las fotos de la propiedad usando la relación correcta y ordenadas
        imagenes = propiedad.imagenes.all().order_by('orden')
        print(f"Imágenes encontradas: {imagenes.count()}")
        
        # Obtener el dominio base de la aplicación
        domain = request.get_host()
        protocol = 'https' if request.is_secure() else 'http'
        base_url = f"{protocol}://{domain}"
        
        imagenes_data = []
        for imagen in imagenes:
            try:
                print(f"Procesando imagen: {imagen}")
                url_imagen = imagen.imagen.url if imagen.imagen else ''
                # Asegurar que la URL sea absoluta
                if url_imagen.startswith('/'):
                    url_imagen = base_url + url_imagen
                print(f"URL de imagen: {url_imagen}")
                
                imagenes_data.append({
                    'id': imagen.id,
                    'url': url_imagen,
                    'orden': imagen.orden
                })
            except Exception as e:
                print(f"Error procesando imagen {imagen.id}: {e}")
                continue
        
        response_data = {
            'success': True,
            'fotos': imagenes_data,
            'total': len(imagenes_data)
        }
        
        print(f"Respuesta imágenes: {response_data}")
        return JsonResponse(response_data)
        
    except Exception as e:
        print(f"Error en obtener_fotos_propiedad: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
@require_http_methods(["GET"])
def obtener_precios_propiedad(request, propiedad_id):
    """Obtiene los precios de una propiedad para un período específico"""
    print(f"=== OBTENER PRECIOS PROPIEDAD ===")
    print(f"Propiedad ID: {propiedad_id}")
    
    try:
        propiedad = get_object_or_404(Propiedad, id=propiedad_id)
        
        # Obtener todos los precios de la propiedad ordenados por tipo
        precios = propiedad.precios.all()
        
        # Si no hay precios, crearlos
        if not precios.exists():
            propiedad.crear_precios_iniciales()
            precios = propiedad.precios.all()
        
        # Crear un diccionario con todos los tipos de precio posibles
        precios_data = []
        for tipo_choice in TipoPrecio.choices:
            tipo_key = tipo_choice[0]
            tipo_display = tipo_choice[1]
            
            # Buscar el precio para este tipo
            precio = precios.filter(tipo_precio=tipo_key).first()
            
            # Si no existe el precio para este tipo, crear un registro temporal
            if not precio:
                precio = Precio(
                    propiedad=propiedad,
                    tipo_precio=tipo_key,
                    precio_total=0,
                    precio_por_dia=0
                )
            
            # Agregar los datos del precio
            precios_data.append({
                'tipo_precio': tipo_key,
                'tipo_precio_display': tipo_display,
                'precio_total': str(precio.precio_total or 0),
                'precio_por_dia': str(precio.precio_por_dia or 0)
            })
        
        response_data = {
            'success': True,
            'precios': precios_data
        }
        
        print(f"Respuesta precios: {response_data}")
        return JsonResponse(response_data)
        
    except Exception as e:
        print(f"Error en obtener_precios_propiedad: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
@require_POST
def eliminar_todas_imagenes(request, propiedad_id):
    """Elimina todas las imágenes de una propiedad específica"""
    try:
        propiedad = get_object_or_404(Propiedad, id=propiedad_id)
        imagenes = ImagenPropiedad.objects.filter(propiedad=propiedad)
        
        # Primero intentamos eliminar los archivos físicos
        for imagen in imagenes:
            try:
                if imagen.imagen:
                    imagen.imagen.delete(save=False)
            except Exception as e:
                logger.warning(f'No se pudo eliminar el archivo físico de la imagen {imagen.id}: {str(e)}')
        
        # Luego eliminamos todos los registros de la base de datos
        total_eliminadas = imagenes.count()
        imagenes.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Se eliminaron {total_eliminadas} imágenes',
            'total_eliminadas': total_eliminadas
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
def dashboard_caja(request):
    return render(request, 'inmobiliaria/caja/dashboard_caja.html')

@login_required
def reportes_caja(request):
    return render(request, 'inmobiliaria/caja/reportes.html')

@login_required
def arqueo_caja(request):
    return render(request, 'inmobiliaria/caja/arqueo.html')

@login_required
def historial_caja(request):
    return render(request, 'inmobiliaria/caja/historial.html')

@login_required
def buscar_conceptos(request):
    termino = request.POST.get('termino', '')
    sucursal = request.user.sucursal
    
    # Buscar por ID o nombre dentro de la sucursal actual
    conceptos = Concepto.objects.filter(
        sucursal=sucursal
    ).filter(
        Q(id__icontains=termino) |
        Q(nombre__icontains=termino)
    ).order_by('id')[:10]  # Limitar a 10 resultados, ordenados por ID
    
    return JsonResponse({
        'conceptos': [{
            'id': c.id,
            'nombre': c.nombre,
            'fecha_creacion': c.fecha_creacion.strftime('%d/%m/%Y %H:%M')
        } for c in conceptos]
    })

@login_required
def crear_concepto(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'})
    
    id = request.POST.get('id')
    nombre = request.POST.get('nombre')
    sucursal = request.user.sucursal
    
    if not id or not nombre:
        return JsonResponse({'success': False, 'error': 'ID y nombre son requeridos'})
    
    try:
        # Verificar si ya existe un concepto con ese ID en esta sucursal
        if Concepto.objects.filter(id=id, sucursal=sucursal).exists():
            return JsonResponse({'success': False, 'error': 'Ya existe un concepto con ese ID en esta sucursal'})
        
        # Crear el concepto (fecha_creacion se asignará automáticamente)
        concepto = Concepto.objects.create(
            id=id,
            nombre=nombre,
            sucursal=sucursal
        )
        
        return JsonResponse({
            'success': True,
            'concepto': {
                'id': concepto.id,
                'nombre': concepto.nombre,
                'fecha_creacion': concepto.fecha_creacion.strftime('%d/%m/%Y %H:%M')
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def buscar_propiedad(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'})
    
    id = request.POST.get('id')
    sucursal = request.user.sucursal
    
    try:
        propiedad = Propiedad.objects.get(id=id, sucursal=sucursal)
        return JsonResponse({
            'success': True,
            'propiedad': {
                'id': propiedad.id,
                'direccion': propiedad.direccion,
                'ubicacion': propiedad.ubicacion
            }
        })
    except Propiedad.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'No se encontró la propiedad'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })



@login_required
def buscar_movimiento(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'})
    
    operacion = request.POST.get('operacion')
    sucursal = request.user.sucursal
    
    try:
        movimiento = MovimientoCaja.objects.select_related(
            'productor',
            'propiedad',
            'concepto'
        ).get(operacion=operacion, caja__sucursal=sucursal)
        
        return JsonResponse({
            'success': True,
            'movimiento': {
                'tipo': movimiento.tipo,
                'tipo_comprobante': movimiento.tipo_comprobante,
                'numero_liquidacion': movimiento.numero_liquidacion,
                'detalles': movimiento.detalles,
                'productor': {
                    'id': movimiento.productor.id,
                    'nombre': movimiento.productor.nombre,
                    'apellido': movimiento.productor.apellido
                } if movimiento.productor else None,
                'propiedad': {
                    'id': movimiento.propiedad.id,
                    'direccion': movimiento.propiedad.direccion
                } if movimiento.propiedad else None,
                'concepto': {
                    'id': movimiento.concepto.id,
                    'nombre': movimiento.concepto.nombre
                } if movimiento.concepto else None
            }
        })
    except MovimientoCaja.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'No se encontró el movimiento'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
def buscar_movimientos(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'})
    
    fecha_desde = request.POST.get('fecha_desde')
    fecha_fin = request.POST.get('fecha_hasta')
    productor_id = request.POST.get('productor_id')
    sucursal = request.user.sucursal
    
    try:
        # Construir el query base
        movimientos = MovimientoCaja.objects.filter(caja__sucursal=sucursal)
        
        # Aplicar filtros si se proporcionan
        if fecha_desde:
            movimientos = movimientos.filter(fecha__date__gte=fecha_desde)
        if fecha_fin:
            movimientos = movimientos.filter(fecha__date__lte=fecha_fin)
        if productor_id:
            movimientos = movimientos.filter(productor_id=productor_id)
        
        # Ordenar por fecha
        movimientos = movimientos.order_by('-fecha')
        
        # Convertir a lista de diccionarios para la respuesta JSON
        movimientos_data = [{
            'id': mov.id,
            'fecha': mov.fecha.strftime('%d/%m/%Y %H:%M'),
            'tipo': mov.tipo,
            'operacion': mov.operacion,
            'tipo_comprobante': mov.tipo_comprobante,
            'numero_liquidacion': mov.numero_liquidacion,
            'detalles': mov.detalles,
            'monto': float(mov.monto) if mov.monto else 0,
            'productor': {
                'id': mov.productor.id,
                'nombre': mov.productor.nombre,
                'apellido': mov.productor.apellido
            } if mov.productor else None,
            'propiedad': {
                'id': mov.propiedad.id,
                'direccion': mov.propiedad.direccion
            } if mov.propiedad else None,
            'concepto': {
                'id': mov.concepto.id,
                'nombre': movimiento.concepto.nombre
            } if mov.concepto else None
        } for mov in movimientos]
        
        return JsonResponse({
            'success': True,
            'movimientos': movimientos_data
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
def buscar_vendedor(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'})
    
    id = request.POST.get('id')
    sucursal = request.user.sucursal
    
    try:
        vendedor = Vendedor.objects.get(id=id, sucursal=sucursal)
        return JsonResponse({
            'success': True,
            'vendedor': {
                'id': vendedor.id,
                'nombre': vendedor.nombre,
                'apellido': vendedor.apellido
            }
        })
    except Vendedor.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'No se encontró el vendedor'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
def buscar_vendedores(request):
    # Aceptar tanto GET como POST para mayor flexibilidad
    if request.method == 'GET':
        termino = request.GET.get('nombre', '')
    elif request.method == 'POST':
        termino = request.POST.get('termino', '')
    else:
        return JsonResponse({'success': False, 'error': 'Método no permitido'})
    
    sucursal = request.user.sucursal
    
    try:
        vendedores = Vendedor.objects.filter(
            sucursal=sucursal
        ).filter(
            Q(nombre__icontains=termino) |
            Q(apellido__icontains=termino) |
            Q(id__icontains=termino)
        ).order_by('apellido', 'nombre')[:10]
        
        return JsonResponse({
            'success': True,
            'vendedores': [{
                'id': v.id,
                'nombre': v.nombre,
                'apellido': v.apellido
            } for v in vendedores]
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
def obtener_caja_actual(request):
    """Devuelve el número de la caja actual abierta para la sucursal del usuario"""
    try:
        caja_actual = Caja.objects.filter(
            sucursal=request.user.sucursal,
            estado='abierta'
        ).first()
        
        return JsonResponse({
            'success': True,
            'caja_numero': caja_actual.numero if caja_actual else None
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
def buscar_propiedades_caja(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'})
    
    termino = request.POST.get('termino', '')
    sucursal = request.user.sucursal
    
    try:
        propiedades = Propiedad.objects.filter(
            sucursal=sucursal
        ).filter(
            Q(id__icontains=termino) |
            Q(direccion__icontains=termino)
        ).order_by('direccion')[:10]
        
        return JsonResponse({
            'success': True,
            'propiedades': [{
                'id': p.id,
                'direccion': p.direccion,
                'ubicacion': p.ubicacion
            } for p in propiedades]
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
def buscar_propiedades(request):
    # FUNCIÓN: buscar_propiedades - función que está siendo usada en producción ✅
    print("🚀 INICIO DE BUSCAR_PROPIEDADES - FUNCIÓN EJECUTÁNDOSE")
    print("🔍 DEBUGGING: Esta es la función que se está ejecutando para ordenamiento")
    
    # Obtener la sucursal del vendedor logueado
    sucursal_vendedor = request.user.sucursal
    print(f"👤 Usuario: {request.user}, Sucursal: {sucursal_vendedor}")
    
    inquilinos = Inquilino.objects.filter(sucursal=sucursal_vendedor)
    form = BuscarPropiedadesForm(request.POST or None)
    inquilino_form = InquilinoForm(request.POST)
    propiedades_disponibles = []
    propiedades_sin_precio = []
    vendedores = Vendedor.objects.filter(sucursal=sucursal_vendedor)
    total_dias_reserva = 0
    
    # FLAG: Para identificar específicamente esta función en los edits siguientes
    FUNCION_PRINCIPAL_EN_USO = True

    fecha_inicio = None
    fecha_fin = None
    origen = None
    destino = None

    if form.is_valid():
        fecha_inicio = form.cleaned_data['fecha_inicio']
        fecha_fin = form.cleaned_data['fecha_fin']
        
        # VALIDACIÓN: Verificar que las fechas son válidas
        if not fecha_inicio or not fecha_fin:
            print("❌ Error: Fechas de inicio o fin faltantes")
            return render(request, 'inmobiliaria/reserva/buscar_propiedades.html', {
                'form': form,
                'error_fechas': 'Por favor, ingresa fechas de inicio y fin válidas.',
                'inquilinos': inquilinos,
                'vendedores': vendedores,
                'propiedades_disponibles': [],
                'total_dias_reserva': 0,
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin,
            })
        origen = form.cleaned_data['origen']
        destino = form.cleaned_data['destino']
        ver_todas = form.cleaned_data.get('ver_todas', False)

        # Filtrar propiedades según la opción seleccionada
        if ver_todas:
            propiedades = Propiedad.objects.all()
        else:
            propiedades = Propiedad.objects.filter(sucursal=sucursal_vendedor)
        
        # AGREGAR FLAG: Para editar específicamente el filtro de esta función
        ES_BUSCAR_PROPIEDADES_PRINCIPAL = True
        
        # 🎯 DEBUGGING: Verificar fechas de búsqueda
        print(f"🎯 BUSCAR_PROPIEDADES_PRINCIPAL: Buscando desde {fecha_inicio} hasta {fecha_fin}")
        
        # 🎯 DEBUGGING: Ver qué propiedades tienen reservas en estas fechas
        from inmobiliaria.models import Reserva
        reservas_en_fechas = Reserva.objects.filter(
            Q(fecha_inicio__lt=fecha_fin) & Q(fecha_fin__gt=fecha_inicio)
        )
        print(f"🔍 RESERVAS EN ESTAS FECHAS: {reservas_en_fechas.count()} encontradas")
        for r in reservas_en_fechas:
            print(f"   - Reserva {r.id}: Propiedad {r.propiedad.id} ({r.propiedad.ubicacion})")
            print(f"     Fechas: {r.fecha_inicio} al {r.fecha_fin}, Estado: '{r.estado}'")
        
        # FLAG para identificar esta función específica para debugging posterior
        DEBUGGING_FUNCION_PRINCIPAL = True

        # Prefetch los precios para cada propiedad
        propiedades = propiedades.prefetch_related(
            Prefetch('precios', queryset=Precio.objects.all(), to_attr='todos_precios')
        ).select_related('sucursal')

        # Aplicar filtros del formulario
        if origen:
            propiedades = propiedades.filter(ubicacion__icontains=origen)
        
        if destino:
            propiedades = propiedades.filter(ubicacion__icontains=destino)

        tipo_inmueble = form.cleaned_data.get('tipo_inmueble')
        if tipo_inmueble:
            propiedades = propiedades.filter(tipo_inmueble__in=tipo_inmueble)

        vista = form.cleaned_data.get('vista')
        if vista:
            propiedades = propiedades.filter(vista__in=vista)

        ambientes = form.cleaned_data.get('ambientes')
        if ambientes:
            propiedades = propiedades.filter(ambientes=ambientes)

        valoracion = form.cleaned_data.get('valoracion')
        if valoracion:
            propiedades = propiedades.filter(valoracion=valoracion)

        precio_min = form.cleaned_data.get('precio_min')
        if precio_min is not None:
            propiedades = propiedades.filter(precio__gte=precio_min)

        precio_max = form.cleaned_data.get('precio_max')
        if precio_max is not None:
            propiedades = propiedades.filter(precio__lte=precio_max)

        # Filtros booleanos
        caracteristicas_booleanas = [
            'amoblado', 'cochera', 'tv_smart', 'wifi', 'dependencia', 'patio',
            'parrilla', 'piscina', 'reciclado', 'a_estrenar', 'terraza', 'balcon',
            'baulera', 'lavadero', 'seguridad', 'vista_al_Mar', 'vista_panoramica', 'apto_credito'
        ]
        for caracteristica in caracteristicas_booleanas:
            if form.cleaned_data.get(caracteristica):
                propiedades = propiedades.filter(**{caracteristica: True})

        # Filtrar propiedades que están disponibles en las fechas indicadas
        for propiedad in propiedades:
            from datetime import timedelta
            print(f"🔍 PROCESANDO PROPIEDAD {propiedad.id}: {propiedad}")
            print(f"   🔎 Buscando disponibilidades que contengan {fecha_inicio} al {fecha_fin}")
            
            # 1️⃣ BUSCAR DISPONIBILIDADES QUE CONTENGAN EL PERÍODO
            disponibilidades = Disponibilidad.objects.filter(
                propiedad=propiedad,
                fecha_inicio__lte=fecha_inicio,
                fecha_fin__gte=fecha_fin,
            )
            
            if disponibilidades.exists():
                # 2️⃣ BUSCAR ÚLTIMA FECHA FINAL ANTES DEL PERÍODO BUSCADO
                # Combinar disponibilidades y reservas para encontrar la fecha más reciente
                
                # Fechas finales de disponibilidades que terminan antes del período
                disp_anteriores = Disponibilidad.objects.filter(
                    propiedad=propiedad,
                    fecha_fin__lt=fecha_inicio
                ).order_by('-fecha_fin').first()
                
                # Fechas finales de reservas que terminan antes del período
                reservas_anteriores = propiedad.reservas.filter(
                    fecha_fin__lt=fecha_inicio
                ).order_by('-fecha_fin').first()
                
                # Determinar la fecha final más reciente
                ultima_fecha_fin = None
                if disp_anteriores and reservas_anteriores:
                    ultima_fecha_fin = max(disp_anteriores.fecha_fin, reservas_anteriores.fecha_fin)
                elif disp_anteriores:
                    ultima_fecha_fin = disp_anteriores.fecha_fin
                elif reservas_anteriores:
                    ultima_fecha_fin = reservas_anteriores.fecha_fin
                
                # 3️⃣ BUSCAR PRIMERA FECHA INICIAL DESPUÉS DEL PERÍODO BUSCADO
                
                # Fechas iniciales de disponibilidades que empiezan después del período
                disp_posteriores = Disponibilidad.objects.filter(
                    propiedad=propiedad,
                    fecha_inicio__gt=fecha_fin
                ).order_by('fecha_inicio').first()
                
                # Fechas iniciales de reservas que empiezan después del período
                reservas_posteriores = propiedad.reservas.filter(
                    fecha_inicio__gt=fecha_fin
                ).order_by('fecha_inicio').first()
                
                # Determinar la fecha inicial más próxima
                proxima_fecha_inicio = None
                if disp_posteriores and reservas_posteriores:
                    proxima_fecha_inicio = min(disp_posteriores.fecha_inicio, reservas_posteriores.fecha_inicio)
                elif disp_posteriores:
                    proxima_fecha_inicio = disp_posteriores.fecha_inicio
                elif reservas_posteriores:
                    proxima_fecha_inicio = reservas_posteriores.fecha_inicio
                
                # 4️⃣ CALCULAR PERÍODO LIBRE
                disponibilidad_base = disponibilidades.first()
                
                fecha_disponible_desde = disponibilidad_base.fecha_inicio
                if ultima_fecha_fin:
                    # 🏨 LÓGICA HOTEL: Si reserva termina el 17, el 17 ya está disponible
                    fecha_disponible_desde = ultima_fecha_fin
                
                fecha_disponible_hasta = disponibilidad_base.fecha_fin
                if proxima_fecha_inicio:
                    # 🏨 LÓGICA HOTEL: Si próxima reserva empieza el 25, hasta el 25 está disponible
                    fecha_disponible_hasta = proxima_fecha_inicio
                
                # 5️⃣ ASIGNAR FECHAS CALCULADAS
                propiedad.disponibilidad_inicio = fecha_disponible_desde
                propiedad.disponibilidad_fin = fecha_disponible_hasta
                
                print(f"🎯 PROP {propiedad.id}: Libre desde {fecha_disponible_desde} hasta {fecha_disponible_hasta}")
                print(f"   📅 Asignado: disponibilidad_inicio={propiedad.disponibilidad_inicio}")
                print(f"   📅 Asignado: disponibilidad_fin={propiedad.disponibilidad_fin}")
                print(f"   📊 Disponibilidad base: {disponibilidad_base.fecha_inicio} al {disponibilidad_base.fecha_fin}")
                if ultima_fecha_fin:
                    print(f"   ⏪ Última fecha final anterior: {ultima_fecha_fin}")
                if proxima_fecha_inicio:
                    print(f"   ⏩ Próxima fecha inicial posterior: {proxima_fecha_inicio}")
            else:
                print(f"❌ PROP {propiedad.id}: NO tiene disponibilidades que contengan el período {fecha_inicio} al {fecha_fin}")
                
                # Para debugging: mostrar todas las disponibilidades de esta propiedad
                todas_disponibilidades = Disponibilidad.objects.filter(propiedad=propiedad)
                print(f"   📋 Disponibilidades existentes ({todas_disponibilidades.count()}):")
                for disp in todas_disponibilidades:
                    print(f"     - {disp.fecha_inicio} al {disp.fecha_fin}")
                
                # 🚫 SALTEAR: Esta propiedad no tiene disponibilidades para el período buscado
                print(f"   🚫 SALTANDO PROPIEDAD {propiedad.id} - No aparecerá en resultados")
                continue
            
            # ✅ CALCULAR DISPONIBILIDADES FRAGMENTADAS POR RESERVAS

            # Obtener las reservas asociadas a la propiedad
            reservas = propiedad.reservas.filter(
                Q(fecha_inicio__lt=fecha_fin) & Q(fecha_fin__gt=fecha_inicio)
            )
            
            if reservas.filter(estado='pagada').exists():
                continue  # Saltar esta propiedad si ya tiene una reserva pagada

            # 🎯 DEBUGGING: Ver todas las reservas encontradas
            print(f"🏠 Propiedad {propiedad.id} - Búsqueda: {fecha_inicio} al {fecha_fin}")
            print(f"   Reservas encontradas: {reservas.count()}")
            for r in reservas:
                print(f"   - Reserva {r.id}: {r.fecha_inicio} al {r.fecha_fin}, estado='{r.estado}'")
            
            # Verificar si existe una reserva confirmada no pagada, confirmada o en espera
            reserva_confirmada_no_pagada = reservas.filter(Q(estado='confirmada_no_pagada') | Q(estado='confirmada') | Q(estado='en_espera')).first()
            print(f"   ¿Reserva para mostrar en rojo? {bool(reserva_confirmada_no_pagada)}")
            if reserva_confirmada_no_pagada:
                print(f"     → Estado: {reserva_confirmada_no_pagada.estado}")
                print(f"     → Fechas: {reserva_confirmada_no_pagada.fecha_inicio} al {reserva_confirmada_no_pagada.fecha_fin}")
                print(f"     → Precio: ${reserva_confirmada_no_pagada.precio_total}")
            else:
                print(f"     → No hay reservas confirmada_no_pagada/confirmada/en_espera en estas fechas")

            # ✅ CORREGIDO: Mostrar propiedades con reservas confirmada_no_pagada en las fechas buscadas
            if reservas.exists():
                for r in reservas:
                    print(f"   Reserva {r.id}: {r.fecha_inicio} al {r.fecha_fin}, estado='{r.estado}'")
            
            # Evaluar la disponibilidad y las reservas de la propiedad
            # 🎯 CORREGIDO: Manejar propiedades CON O SIN disponibilidades
            
            # Verificar reservas conflictivas PRIMERO (solo las pagadas)
            reservas_conflictivas = reservas.filter(
                Q(estado='pagada')
            )
            
            if reservas_conflictivas.exists():
                print(f"   ❌ Saltando por reservas conflictivas: {reservas_conflictivas.count()}")
                continue  # Saltar si hay reservas pagadas o confirmadas en estas fechas
            
            # Si hay una reserva para mostrar en rojo, mostrarla SIEMPRE (es información importante)
            if reserva_confirmada_no_pagada:
                print(f"   ✅ MOSTRANDO EN ROJO: Reserva {reserva_confirmada_no_pagada.id} con estado '{reserva_confirmada_no_pagada.estado}'")
                propiedad.reserva = reserva_confirmada_no_pagada
                propiedad.estado_reserva = 'confirmada_no_pagada'  # Siempre mostrar como confirmada_no_pagada en frontend
                # ✅ USAR PRECIO DE LA RESERVA EXISTENTE, NO RECALCULAR
                propiedad.precio_total_reserva = reserva_confirmada_no_pagada.precio_total
                print(f"   💰 Precio de reserva existente: ${reserva_confirmada_no_pagada.precio_total}")
                print(f"   🔴 Estado asignado para mostrar: {propiedad.estado_reserva}")
                
                # Asignar fechas de la reserva
                propiedad.disponibilidad_inicio = reserva_confirmada_no_pagada.fecha_inicio
                propiedad.disponibilidad_fin = reserva_confirmada_no_pagada.fecha_fin
                
                # Agregar a la lista y continuar sin recalcular precios
                propiedades_disponibles.append(propiedad)
                print(f"   ✅ Propiedad {propiedad.id} agregada a la lista con reserva en rojo")
                continue
            else:
                # ✅ PROPIEDADES SIN RESERVAS - Calcular precios y agregar a lista
                propiedad.estado_reserva = 'disponible'
                print(f"   ✅ DISPONIBLE: Sin reservas para mostrar en rojo")

            # Calcular el precio total según las fechas seleccionadas
                precio_total = 0
                print('fecha de inicio',fecha_inicio)
                print('fecha de fin',fecha_fin)
            # Para cálculos de precio: usar días completos (lógica original)
                dias_reserva = (fecha_fin - fecha_inicio).days + 1

                print(f"🔥 INICIANDO CÁLCULO para propiedad {propiedad.id} del {fecha_inicio} al {fecha_fin}")
                print(f"🔥 Días a calcular: {dias_reserva}")
                
                # Calcular día por día usando tu función para determinar temporadas
                for single_date in (fecha_inicio + timedelta(n) for n in range(dias_reserva)):
                    # Determinar el tipo de precio según la fecha
                    tipo_precio = None
                    if single_date.month == 1:  # Enero
                        tipo_precio = 'QUINCENA_1_ENERO' if single_date.day <= 15 else 'QUINCENA_2_ENERO'
                    elif single_date.month == 2:  # Febrero
                        tipo_precio = 'QUINCENA_1_FEBRERO' if single_date.day < 15 else 'QUINCENA_2_FEBRERO'
                    elif single_date.month == 3:  # Marzo
                        tipo_precio = 'QUINCENA_1_MARZO' if single_date.day <= 15 else 'QUINCENA_2_MARZO'
                    elif single_date.month == 7:  # Julio (Vacaciones de Invierno)
                        tipo_precio = 'VACACIONES_INVIERNO'
                    elif single_date.month == 12:  # Diciembre
                        tipo_precio = 'QUINCENA_1_DICIEMBRE' if single_date.day <= 15 else 'QUINCENA_2_DICIEMBRE'
                    else:
                        tipo_precio = 'TEMPORADA_BAJA'  # Asumir temporada baja para otros meses

                    # Obtener el precio por día para esta temporada
                    try:
                        precio_obj = Precio.objects.get(propiedad=propiedad, tipo_precio=tipo_precio)
                        # Usar precio_por_dia directamente (ya incluye ajustes)
                        precio_dia = precio_obj.precio_por_dia or 0
                        
                        # Aplicar ajuste porcentual si existe
                        if precio_obj.ajuste_porcentaje != 0:
                            precio_dia *= (1 - precio_obj.ajuste_porcentaje / 100)
                        
                        precio_total += precio_dia
                        print(f"📅 {single_date.strftime('%d/%m')}: {tipo_precio} = ${precio_dia:,.0f} - Total acumulado: ${precio_total:,.0f}")
                    except Precio.DoesNotExist:
                        print(f"📅 {single_date.strftime('%d/%m')}: {tipo_precio} = $0 (sin precio configurado)")
                        print(f"🚨 PRECIO FALTANTE - Propiedad {propiedad.id} NO tiene precio para {tipo_precio}")
                        # Mostrar qué precios SÍ tiene esta propiedad
                        precios_existentes = Precio.objects.filter(propiedad=propiedad)
                        print(f"🔍 Precios configurados para esta propiedad: {precios_existentes.count()}")
                        for p in precios_existentes:
                            print(f"   - {p.tipo_precio}: ${p.precio_por_dia}")

                # ✅ ASIGNAR EL PRECIO CALCULADO CON TU FUNCIÓN
                print(f"🔥 PRECIO FINAL CALCULADO para propiedad {propiedad.id}: ${precio_total}")
                propiedad.precio_total_reserva = precio_total
                
                # ✅ Las fechas de disponibilidad ya fueron calculadas dinámicamente en el primer bucle
                # No sobrescribir con las fechas de búsqueda
                
                # Agregar la propiedad disponible a la lista
                propiedades_disponibles.append(propiedad)
    
    # Alerta si hay propiedades sin precio
    alerta_sin_precio = len(propiedades_sin_precio) > 0
    
    # CALCULAR NOCHES CORRECTAMENTE AQUÍ (después de validar fechas)
    if fecha_inicio and fecha_fin:
        total_dias_reserva = (fecha_fin - fecha_inicio).days
    
    print("las fechas de inicio y fin son ",fecha_inicio,fecha_fin)
    print("los dias de reserva son ",total_dias_reserva)

    # Los precios ya fueron calculados correctamente arriba para cada propiedad
    # No es necesario recalcular aquí

    # ✅ ORDENAMIENTO PERSONALIZADO: Primero rojas, luego por días libres
    def calcular_dias_libres(propiedad, fecha_inicio_busqueda, fecha_fin_busqueda):
        """
        Calcula días perdidos desde el inicio de disponibilidad hasta la búsqueda.
        Versión ultra-segura con múltiples fallbacks.
        """
        try:
            # Verificar estado de la propiedad
            if not hasattr(propiedad, 'estado_reserva'):
                return 999999  # Sin estado definido, ponerla al final
                
            if propiedad.estado_reserva == 'confirmada_no_pagada':
                return -1  # Rojas van primero (valor negativo)
            
            # ✅ LÓGICA CORREGIDA: Calcular días perdidos correctamente
            try:
                # Buscar reservas que terminen ANTES O EN la fecha de búsqueda
                reservas_anteriores = propiedad.reservas.filter(
                    fecha_fin__lte=fecha_inicio_busqueda
                ).order_by('-fecha_fin')
                
                # Buscar disponibilidades que terminen ANTES O EN la fecha de búsqueda  
                from .models.propiedad import Disponibilidad
                disponibilidades_anteriores = Disponibilidad.objects.filter(
                    propiedad=propiedad,
                    fecha_fin__lte=fecha_inicio_busqueda
                ).order_by('-fecha_fin')
                
                # Encontrar la fecha de fin más reciente (reserva o disponibilidad)
                fecha_fin_mas_reciente = None
                tipo_encontrado = None
                
                # Verificar reservas
                if reservas_anteriores.exists():
                    reserva_reciente = reservas_anteriores.first()
                    fecha_fin_mas_reciente = reserva_reciente.fecha_fin
                    tipo_encontrado = "reserva"
                
                # Verificar disponibilidades y comparar
                if disponibilidades_anteriores.exists():
                    disponibilidad_reciente = disponibilidades_anteriores.first()
                    if not fecha_fin_mas_reciente or disponibilidad_reciente.fecha_fin > fecha_fin_mas_reciente:
                        fecha_fin_mas_reciente = disponibilidad_reciente.fecha_fin
                        tipo_encontrado = "disponibilidad"
                
                if fecha_fin_mas_reciente:
                    # ✅ CALCULAR DÍAS PERDIDOS: desde el día siguiente al fin hasta el inicio de búsqueda
                    from datetime import timedelta
                    dia_siguiente = fecha_fin_mas_reciente + timedelta(days=1)
                    dias_perdidos = (fecha_inicio_busqueda - dia_siguiente).days
                    dias_resultado = max(dias_perdidos, 0)  # No negativos
                    
                    print(f"🔍 Propiedad {propiedad.id}: Última {tipo_encontrado} terminó {fecha_fin_mas_reciente}, día siguiente {dia_siguiente}, búsqueda {fecha_inicio_busqueda} → {dias_resultado} días perdidos")
                    return dias_resultado
                else:
                    # Sin fechas anteriores, usar ID como fallback
                    print(f"🔍 Propiedad {propiedad.id}: Sin fechas anteriores, usando ID como ordenamiento")
                    return int(propiedad.id) if propiedad.id else 999999
                    
            except Exception as e:
                print(f"Error en cálculo avanzado para propiedad {propiedad.id}: {e}")
                # Fallback final: usar ID de propiedad
                try:
                    return int(propiedad.id) if propiedad.id else 999999
                except:
                    return 999999
            
        except Exception as e:
            print(f"Error general calculando días libres para propiedad {propiedad.id}: {e}")
            return 999999

    # ✅ APLICAR ORDENAMIENTO MEJORADO: Rojas primero, luego por días libres
    if propiedades_disponibles:
        print("🔄 APLICANDO ORDENAMIENTO PERSONALIZADO...")
        
        # Agregar días libres a cada propiedad para debugging
        for propiedad in propiedades_disponibles:
            if fecha_inicio and fecha_fin:
                propiedad.dias_libres_calculados = calcular_dias_libres(propiedad, fecha_inicio, fecha_fin)
            else:
                # Sin fechas, usar un orden básico
                if hasattr(propiedad, 'estado_reserva') and propiedad.estado_reserva == 'confirmada_no_pagada':
                    propiedad.dias_libres_calculados = -1  # Rojas primero
                else:
                    propiedad.dias_libres_calculados = 999999  # Disponibles después
            
            estado_debug = getattr(propiedad, 'estado_reserva', 'N/A')
            print(f"🏠 Propiedad {propiedad.id}: Estado={estado_debug}, Días libres={propiedad.dias_libres_calculados}")
            
            # DEBUG ESPECIAL para propiedad 44554
            if propiedad.id == 44554:
                print(f"🔍 DEBUG ESPECIAL 44554:")
                print(f"   - Estado reserva: {estado_debug}")
                print(f"   - Fecha inicio búsqueda: {fecha_inicio}")
                print(f"   - Fecha fin búsqueda: {fecha_fin}")
                print(f"   - Días libres calculados: {propiedad.dias_libres_calculados}")
                
                # Revisar reservas y disponibilidades
                reservas = propiedad.reservas.filter(fecha_fin__lt=fecha_inicio).order_by('-fecha_fin')
                print(f"   - Reservas anteriores: {list(reservas.values('id', 'fecha_fin'))}")
                
                disponibilidades = Disponibilidad.objects.filter(propiedad=propiedad, fecha_fin__lt=fecha_inicio).order_by('-fecha_fin')
                print(f"   - Disponibilidades anteriores: {list(disponibilidades.values('id', 'fecha_fin'))}")
        
        # ✅ ORDENAR: primero las rojas (días libres = -1), luego por menos días libres, luego por ID
        propiedades_disponibles.sort(key=lambda p: (p.dias_libres_calculados, p.id))
        
        # ✅ DEBUG DETALLADO PARA VERIFICAR ORDENAMIENTO
        print("=" * 80)
        print("📋 PROPIEDADES ORDENADAS POR DÍAS PERDIDOS:")
        print(f"Total propiedades encontradas: {len(propiedades_disponibles)}")
        print("=" * 80)
        
        # Mostrar TODAS las propiedades con sus cálculos para debug
        for i, propiedad in enumerate(propiedades_disponibles, 1):
            try:
                estado = getattr(propiedad, 'estado_reserva', 'disponible')
                dias = propiedad.dias_libres_calculados
                
                # Obtener fechas de disponibilidad para mostrar
                try:
                    disponibilidad_info = "Sin info"
                    if hasattr(propiedad, 'disponibilidad_inicio') and hasattr(propiedad, 'disponibilidad_fin'):
                        disponibilidad_info = f"{propiedad.disponibilidad_inicio} al {propiedad.disponibilidad_fin}"
                except:
                    disponibilidad_info = "Error obteniendo fechas"
                
                print(f"  {i:2d}. ID:{propiedad.id:5d} | {estado:20s} | {str(dias):>6s} días | {disponibilidad_info}")
                
            except Exception as e:
                print(f"  {i:2d}. ID:{propiedad.id} | ERROR: {e}")
        
        print("=" * 80)

    # Obtener conceptos para el template
    conceptos = Concepto.objects.filter(
        Q(sucursal=sucursal_vendedor) | Q(sucursal__isnull=True)
    ).order_by('nombre')

    return render(request, 'inmobiliaria/reserva/buscar_propiedades.html', {
        'form': form,
        'propiedades_disponibles': propiedades_disponibles,
        'alerta_sin_precio': alerta_sin_precio,
        'fecha_inicio': fecha_inicio.strftime('%d/%m/%Y') if fecha_inicio else '',
        'fecha_fin': fecha_fin.strftime('%d/%m/%Y') if fecha_fin else '',
        'total_dias': total_dias_reserva,
        'inquilinos': Inquilino.objects.all().order_by('apellido', 'nombre'),
        'vendedores': vendedores,
        'tipos_precio': TipoPrecio,
        'conceptos': conceptos,
        'debugging_info': f"🔍 DEBUGGING: Se encontraron {len(propiedades_disponibles)} propiedades. Función ejecutada correctamente."
    })

# ============================
# VISTAS API PARA CONTRATOS 24 MESES
# ============================

@login_required
def api_inquilino_detalle(request, inquilino_id):
    """API para obtener detalles de un inquilino"""
    try:
        inquilino = get_object_or_404(Inquilino, id=inquilino_id)
        data = {
            'id': inquilino.id,
            'nombre': inquilino.nombre,
            'apellido': inquilino.apellido,
            'telefono': inquilino.telefono,
            'email': inquilino.email,
            'dni': inquilino.dni,
        }
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=404)

@login_required 
def api_vendedor_detalle(request, vendedor_id):
    """API para obtener detalles de un vendedor"""
    try:
        vendedor = get_object_or_404(Vendedor, id=vendedor_id)
        data = {
            'id': vendedor.id,
            'nombre': vendedor.nombre,
            'apellido': vendedor.apellido,
            'telefono': vendedor.telefono,
            'email': vendedor.email,
        }
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=404)

@login_required
@require_http_methods(['GET', 'POST'])
def crear_contrato_alquiler(request):
    if request.method == 'POST':
        try:
            # Obtener datos del formulario
            propiedad_id = request.POST.get('propiedad_id')
            inquilino_id = request.POST.get('inquilino_id')
            vendedor_id = request.POST.get('vendedor_id')
            fecha_operacion = request.POST.get('fecha_operacion')
            fecha_inicio = request.POST.get('fecha_inicio')
            fecha_fin = request.POST.get('fecha_fin')
            duracion_meses = int(request.POST.get('duracion_meses', 24))
            precio_mensual = Decimal(request.POST.get('precio_mensual').replace('.', '').replace(',', '.'))
            deposito_garantia = Decimal(request.POST.get('deposito_garantia').replace('.', '').replace(',', '.'))

            # Validar datos
            if not all([propiedad_id, inquilino_id, vendedor_id, fecha_operacion, fecha_inicio, fecha_fin]):
                return JsonResponse({'error': 'Todos los campos son requeridos'}, status=400)

            # Obtener objetos
            try:
                propiedad = Propiedad.objects.get(id=propiedad_id)
                inquilino = Inquilino.objects.get(id=inquilino_id)
                vendedor = Vendedor.objects.get(id=vendedor_id)
            except (Propiedad.DoesNotExist, Inquilino.DoesNotExist, Vendedor.DoesNotExist) as e:
                return JsonResponse({'error': f'Error al obtener datos: {str(e)}'}, status=400)

            # Crear el contrato
            contrato = ContratoAlquiler.objects.create(
                propiedad=propiedad,
                inquilino=inquilino,
                vendedor=vendedor,
                sucursal=request.user.sucursal,
                fecha_operacion=fecha_operacion,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                duracion_meses=duracion_meses,
                precio_mensual=precio_mensual,
                deposito_garantia=deposito_garantia,
                estado='reservado'  # Iniciar en estado reservado
            )

            # Marcar la propiedad como reservada
            propiedad.info_meses.estado = 'reservado'
            propiedad.info_meses.save()

            messages.success(request, 'Contrato creado exitosamente')
            return JsonResponse({
                'success': True,
                'redirect_url': reverse('inmobiliaria:detalle_contrato', args=[contrato.id])
            })

        except Exception as e:
            return JsonResponse({'error': f'Error al crear el contrato: {str(e)}'}, status=400)

    return render(request, 'inmobiliaria/contratos/crear.html')

@login_required
def lista_contratos(request):
    """Vista para listar todos los contratos de alquiler"""
    from .models import ContratoAlquiler, CuotaMensual
    from django.db.models import Q, Count, Case, When, IntegerField
    from datetime import datetime
    
    # Query base
    contratos = ContratoAlquiler.objects.filter(
        sucursal=request.user.sucursal
    ).select_related('propiedad', 'inquilino', 'vendedor')
    
    # Aplicar filtros
    estado_cuota = request.GET.get('estado_cuota')
    mes_vencimiento = request.GET.get('mes_vencimiento')
    busqueda = request.GET.get('q')
    
    # Determinar el mes de filtro (actual o seleccionado)
    mes_filtro = None
    if mes_vencimiento:
        try:
            mes_filtro = datetime.strptime(mes_vencimiento, '%Y-%m')
        except ValueError:
            mes_filtro = timezone.now()
    else:
        mes_filtro = timezone.now()
    
    # Crear fechas de inicio y fin del mes
    inicio_mes = datetime(mes_filtro.year, mes_filtro.month, 1, tzinfo=timezone.get_current_timezone())
    if mes_filtro.month == 12:
        fin_mes = datetime(mes_filtro.year + 1, 1, 1, tzinfo=timezone.get_current_timezone())
    else:
        fin_mes = datetime(mes_filtro.year, mes_filtro.month + 1, 1, tzinfo=timezone.get_current_timezone())
    
    # Filtros de cuotas
    filtro_mes = Q(
        cuotas__fecha_vencimiento__gte=inicio_mes,
        cuotas__fecha_vencimiento__lt=fin_mes
    )
    
    if estado_cuota:
        # Si es pendiente, filtrar por mes actual
        if estado_cuota == 'pendiente':
            contratos = contratos.filter(
                cuotas__estado='pendiente',
                cuotas__fecha_vencimiento__gte=inicio_mes,
                cuotas__fecha_vencimiento__lt=fin_mes
            ).distinct()
        else:
            contratos = contratos.filter(cuotas__estado=estado_cuota).distinct()
    
    if mes_vencimiento:
        contratos = contratos.filter(filtro_mes).distinct()
    
    if busqueda:
        contratos = contratos.filter(
            Q(inquilino__nombre__icontains=busqueda) |
            Q(inquilino__apellido__icontains=busqueda) |
            Q(propiedad__direccion__icontains=busqueda)
        )
    
    # Ordenar por fecha de creación
    contratos = contratos.order_by('-fecha_creacion')
    
    # Obtener estadísticas
    total_contratos = contratos.count()
    
    # Contratos al día (cuotas pagadas en el mes actual/filtrado)
    contratos_al_dia = contratos.filter(
        cuotas__estado='pagada',
        cuotas__fecha_vencimiento__gte=inicio_mes,
        cuotas__fecha_vencimiento__lt=fin_mes
    ).distinct().count()
    
    # Cuotas pendientes del mes actual/filtrado
    cuotas_pendientes = CuotaMensual.objects.filter(
        contrato__sucursal=request.user.sucursal,
        estado='pendiente',
        fecha_vencimiento__gte=inicio_mes,
        fecha_vencimiento__lt=fin_mes
    ).count()
    
    # Cuotas vencidas (del mes actual/filtrado que están vencidas)
    cuotas_vencidas = CuotaMensual.objects.filter(
        contrato__sucursal=request.user.sucursal,
        estado='vencida',
        fecha_vencimiento__gte=inicio_mes,
        fecha_vencimiento__lt=fin_mes
    ).count()
    
    # Obtener la próxima cuota para cada contrato
    for contrato in contratos:
        # Obtener la próxima cuota pendiente o vencida
        contrato.proxima_cuota = contrato.cuotas.filter(
            estado__in=['pendiente', 'vencida']
        ).order_by('fecha_vencimiento').first()
        
        # Marcar cuotas vencidas
        if contrato.proxima_cuota and contrato.proxima_cuota.fecha_vencimiento < timezone.now().date():
            contrato.proxima_cuota.estado = 'vencida'
            contrato.proxima_cuota.save()
        
        # Verificar si hay cuotas anteriores pendientes
        contrato.tiene_cuotas_anteriores_pendientes = contrato.cuotas.filter(
            Q(estado__in=['pendiente', 'vencida']) &
            Q(fecha_vencimiento__lt=contrato.proxima_cuota.fecha_vencimiento if contrato.proxima_cuota else timezone.now().date())
        ).exists()
        
        # Determinar estado de depósito, honorarios y sellados
        contrato.deposito_estado = determinar_estado_concepto_contrato(contrato, '10')  # Concepto 10 = depósito
        contrato.honorarios_estado = determinar_estado_concepto_contrato(contrato, '25')  # Concepto 25 = honorarios  
        contrato.sellados_estado = determinar_estado_concepto_contrato(contrato, '26')  # Concepto 26 = sellados
        
        # Agregar valores de honorarios y sellados desde MovimientoCaja si no están en el contrato
        if not hasattr(contrato, 'honorarios'):
            contrato.honorarios = obtener_valor_concepto_contrato(contrato, 'honorarios')
        if not hasattr(contrato, 'sellados'):
            contrato.sellados = obtener_valor_concepto_contrato(contrato, 'sellados')
    
    context = {
        'contratos': contratos,
        'total_contratos': total_contratos,
        'contratos_al_dia': contratos_al_dia,
        'cuotas_pendientes': cuotas_pendientes,
        'cuotas_vencidas': cuotas_vencidas,
        'mes_actual': mes_filtro.strftime('%B %Y'),
    }
    
    return render(request, 'inmobiliaria/contratos/lista_contratos.html', context)

@login_required
def detalle_contrato(request, contrato_id):
    """Vista para ver el detalle de un contrato específico"""
    from .models import ContratoAlquiler
    
    contrato = get_object_or_404(ContratoAlquiler, id=contrato_id, sucursal=request.user.sucursal)
    cuotas = contrato.cuotas.all().order_by('numero_cuota')
    
    # Estadísticas
    cuotas_pagadas = cuotas.filter(estado='pagada').count()
    cuotas_vencidas = cuotas.filter(estado='pendiente', fecha_vencimiento__lt=timezone.now().date()).count()
    total_pagado = sum(cuota.monto_total for cuota in cuotas.filter(estado='pagada'))
    
    context = {
        'contrato': contrato,
        'cuotas': cuotas,
        'cuotas_pagadas': cuotas_pagadas,
        'cuotas_vencidas': cuotas_vencidas,
        'total_pagado': total_pagado,
        'today': timezone.now().date(),
    }
    
    return render(request, 'inmobiliaria/contratos/detalle_contrato.html', context)

@login_required
def crear_operacion_contrato(request, contrato_id):
    contrato = get_object_or_404(ContratoAlquiler, id=contrato_id, sucursal=request.user.sucursal)
    tipo_operacion = request.GET.get('tipo', 'principal')
    
    # Verificar si hay una caja abierta
    try:
        caja = Caja.objects.get(sucursal=request.user.sucursal, estado='abierta')
    except Caja.DoesNotExist:
        # Si no hay caja abierta, crear una nueva
        caja = Caja.objects.create(
            sucursal=request.user.sucursal,
            usuario_apertura=request.user,
            saldo_inicial=0,
            estado='abierta',
            fecha_apertura=timezone.now()
        )
        messages.success(request, 'Se ha abierto una nueva caja automáticamente.')

    context = {
        'contrato': contrato,
        'tipo_operacion': tipo_operacion,
        'caja': caja,
        'conceptos': Concepto.objects.filter(
            Q(sucursal=request.user.sucursal) | 
            Q(sucursal__isnull=True)
        ).order_by('nombre'),
        'today': timezone.now(),
    }
    
    return render(request, 'inmobiliaria/contratos/crear_operacion.html', context)

def obtener_caja_abierta(request):
    """Obtiene la caja abierta para la sucursal del usuario"""
    try:
        return Caja.objects.get(sucursal=request.user.sucursal, estado='abierta')
    except Caja.DoesNotExist:
        return None

def determinar_estado_concepto_contrato(contrato, concepto_id):
    """
    Determina si un concepto específico está pagado para un contrato.
    Similar a la lógica del concepto 10 en alquiler por día.
    """
    from .models import MovimientoCaja
    
    # Buscar movimientos de caja relacionados con este contrato
    movimientos = MovimientoCaja.objects.filter(
        propiedad=contrato.propiedad,
        concepto__icontains=f'Contrato #{contrato.id}'
    )
    
    # Verificar si algún movimiento contiene el concepto específico
    for movimiento in movimientos:
        try:
            # Parsear conceptos estructurados (igual que en alquiler por día)
            conceptos_lineas = movimiento.concepto.split('\n')
            for linea in conceptos_lineas:
                if ' | ID:' in linea and ' | $' in linea:
                    partes = linea.split(' | ')
                    if len(partes) >= 3:
                        # Buscar ID en la línea
                        id_parte = [p for p in partes if p.startswith('ID:')]
                        if id_parte:
                            id_concepto = id_parte[0].replace('ID:', '').strip()
                            if id_concepto == concepto_id:
                                return 'pagado'
        except:
            continue
    
    return 'pendiente'

def obtener_valor_concepto_contrato(contrato, campo):
    """
    Obtiene el valor de honorarios o sellados desde MovimientoCaja para un contrato.
    """
    from .models import MovimientoCaja
    from decimal import Decimal
    
    # Buscar el primer movimiento de caja relacionado con este contrato
    movimiento = MovimientoCaja.objects.filter(
        propiedad=contrato.propiedad,
        concepto__icontains=f'Contrato #{contrato.id}'
    ).first()
    
    if movimiento:
        # Obtener el valor del campo específico
        return getattr(movimiento, campo, Decimal('0'))
    
    return Decimal('0')

def procesar_conceptos_y_crear_movimiento(request, caja, contrato):
    """Procesa los conceptos y crea el movimiento de caja"""
    try:
        # Función auxiliar para limpiar valores monetarios
        def limpiar_valor_monetario(valor_str):
            if not valor_str or valor_str.strip() == '':
                return Decimal('0')
            valor_limpio = valor_str.replace('.', '').replace(',', '.')
            try:
                return Decimal(valor_limpio)
            except:
                return Decimal('0')
        
        # Extraer datos del formulario
        concepto = request.POST.get('concepto', f'Contrato #{contrato.id} - {contrato.propiedad.direccion}')
        
        # Métodos de pago
        monto_efectivo = limpiar_valor_monetario(request.POST.get('monto_efectivo', '0'))
        monto_cheque = limpiar_valor_monetario(request.POST.get('monto_cheque', '0'))
        monto_tarjeta = limpiar_valor_monetario(request.POST.get('monto_tarjeta', '0'))
        monto_deposito_galicia = limpiar_valor_monetario(request.POST.get('monto_deposito_galicia', '0'))
        monto_deposito_mp = limpiar_valor_monetario(request.POST.get('monto_deposito_mp', '0'))
        
        # Honorarios y sellados (campos movidos arriba)
        honorarios = limpiar_valor_monetario(request.POST.get('honorarios_top', '0'))
        sellados = limpiar_valor_monetario(request.POST.get('sellados_top', '0'))
        
        total_movimiento = (monto_efectivo + monto_cheque + monto_tarjeta + 
                          monto_deposito_galicia + monto_deposito_mp)
        
        # Crear movimiento de caja
        movimiento = MovimientoCaja.objects.create(
            caja=caja,
            tipo='INGRESO',
            concepto=concepto,
            monto_efectivo=monto_efectivo,
            monto_cheque=monto_cheque,
            monto_tarjeta=monto_tarjeta,
            fecha=timezone.now(),
            empleado=request.user,
            sucursal=request.user.sucursal,
            propiedad=contrato.propiedad,
            honorarios=honorarios,
            sellados=sellados
        )
        
        # Si hay depósitos bancarios, guardarlos
        if monto_deposito_galicia > 0:
            movimiento.destino_deposito = 'galicia'
            movimiento.monto_deposito = monto_deposito_galicia
        elif monto_deposito_mp > 0:
            movimiento.destino_deposito = 'mp'
            movimiento.monto_deposito = monto_deposito_mp
        
        movimiento.save()
        
        return movimiento, total_movimiento
        
    except Exception as e:
        print("Error al procesar conceptos:", str(e))
        return None, 0

@login_required
@require_POST
def procesar_operacion_contrato(request, contrato_id):
    try:
        contrato = get_object_or_404(ContratoAlquiler, id=contrato_id)
        tipo_operacion = request.POST.get('tipo_operacion', '')
        nuevo_precio_mensual = request.POST.get('nuevo_precio_mensual')
        
        if nuevo_precio_mensual:
            try:
                nuevo_precio_mensual = Decimal(nuevo_precio_mensual.replace('.', '').replace(',', '.'))
                contrato.precio_mensual = nuevo_precio_mensual
                contrato.save()
                CuotaMensual.objects.filter(
                    contrato=contrato, estado='pendiente'
                ).update(monto_base=nuevo_precio_mensual, monto_total=nuevo_precio_mensual)
            except (ValueError, InvalidOperation):
                return JsonResponse({'error': 'El precio mensual proporcionado no es válido'}, status=400)
        
        if tipo_operacion == 'principal' and contrato.operacion_principal:
            return JsonResponse({'error': 'La operación principal ya fue realizada'}, status=400)
        
        caja = obtener_caja_abierta(request)
        if not caja:
            return JsonResponse({'error': 'No hay una caja abierta'}, status=400)
        
        movimiento, total_movimiento = procesar_conceptos_y_crear_movimiento(request, caja, contrato)
        if not movimiento:
            return JsonResponse({'error': 'Error al procesar el movimiento'}, status=400)
        
        if tipo_operacion == 'principal':
            # Capturar el día de vencimiento seleccionado
            dia_vencimiento = request.POST.get('dia_vencimiento')
            if dia_vencimiento:
                try:
                    dia_vencimiento = int(dia_vencimiento)
                    contrato.dia_vencimiento = dia_vencimiento
                    contrato.save()
                except (ValueError, TypeError):
                    return JsonResponse({'error': 'Día de vencimiento inválido'}, status=400)
            else:
                return JsonResponse({'error': 'Debe seleccionar un día de vencimiento'}, status=400)
            
            # Lógica inteligente: solo incluir depósito si hay concepto 10 (igual que alquiler por día)
            conceptos_texto = movimiento.concepto
            concepto_10_presente = ' | ID:10 |' in conceptos_texto
            
            if concepto_10_presente:
                total_esperado = contrato.deposito_garantia + contrato.precio_mensual
                mensaje_error = f'El monto total (${total_movimiento}) debe ser igual al depósito (${contrato.deposito_garantia}) más el primer mes (${contrato.precio_mensual})'
            else:
                # Si no hay concepto 10, el total esperado es lo que esté en los conceptos
                total_esperado = total_movimiento  # Aceptar cualquier total (conceptos + honorarios + sellados sin depósito)
                mensaje_error = f'Total validado: ${total_movimiento} (sin depósito, concepto 10 no presente)'
            
            # Usar el día de vencimiento seleccionado para crear las fechas
            fecha_actual = timezone.now().date()
            # Calcular la primera fecha de vencimiento usando el día seleccionado
            try:
                fecha_vencimiento = date(fecha_actual.year, fecha_actual.month, contrato.dia_vencimiento)
                # Si ya pasó el día este mes, programar para el próximo mes
                if fecha_actual.day >= contrato.dia_vencimiento:
                    fecha_vencimiento = fecha_vencimiento + relativedelta(months=1)
            except ValueError:
                # Si el día no existe en el mes actual (ej: 31 en febrero), usar el último día del mes
                fecha_vencimiento = date(fecha_actual.year, fecha_actual.month, 28)
                if fecha_actual.day >= 28:
                    fecha_vencimiento = fecha_vencimiento + relativedelta(months=1)
            
            for i in range(contrato.duracion_meses):
                CuotaMensual.objects.create(
                    contrato=contrato, 
                    numero_cuota=i + 1, 
                    fecha_vencimiento=fecha_vencimiento,
                    monto_base=contrato.precio_mensual, 
                    monto_total=contrato.precio_mensual,
                    estado='pendiente', 
                    movimiento=None, 
                    fecha_pago=None
                )
                # Avanzar al siguiente mes manteniendo el día de vencimiento
                try:
                    fecha_vencimiento = fecha_vencimiento.replace(month=fecha_vencimiento.month + 1)
                except ValueError:
                    # Si el día no existe en el próximo mes, ajustar el año
                    if fecha_vencimiento.month == 12:
                        fecha_vencimiento = fecha_vencimiento.replace(year=fecha_vencimiento.year + 1, month=1)
                    else:
                        fecha_vencimiento = fecha_vencimiento.replace(month=fecha_vencimiento.month + 1)
                except:
                    # Usar relativedelta como fallback
                    fecha_vencimiento = fecha_vencimiento + relativedelta(months=1)
            
            contrato.operacion_principal = True
            contrato.estado = 'activo'  # Cambiar estado a activo después de la operación principal
            contrato.save()
            
            # Actualizar estado de la propiedad
            contrato.propiedad.info_meses.estado = 'alquilada'
            contrato.propiedad.info_meses.save()
        else:
            cuota = contrato.cuotas.filter(estado='pendiente').order_by('fecha_vencimiento').first()
            if not cuota:
                return JsonResponse({'error': 'No hay cuotas pendientes para pagar'}, status=400)
            
            if nuevo_precio_mensual:
                cuota.monto_base = nuevo_precio_mensual
                cuota.monto_total = nuevo_precio_mensual
                cuota.save()
            
            total_esperado = cuota.monto_total
            mensaje_error = f'El monto total (${total_movimiento}) debe ser igual al valor de la cuota (${cuota.monto_total})'
            
            cuota.estado = 'pagada'
            cuota.fecha_pago = timezone.now().date()
            cuota.movimiento = movimiento
            cuota.save()
        
        if total_movimiento != total_esperado:
            return JsonResponse({'error': mensaje_error}, status=400)
        
        return JsonResponse({
            'success': True,
            'redirect_url': reverse('inmobiliaria:recibo_contrato_24', args=[contrato.id])
        })
    except Exception as e:
        return JsonResponse({'error': f'Error al procesar la operación: {str(e)}'}, status=400)

@login_required
def ver_cuotas_contrato(request, contrato_id):
    """Vista para ver todas las cuotas de un contrato"""
    contrato = get_object_or_404(ContratoAlquiler, id=contrato_id, sucursal=request.user.sucursal)
    cuotas = contrato.cuotas.all().order_by('numero_cuota')
    
    # Marcar cuotas vencidas
    hoy = timezone.now().date()
    for cuota in cuotas:
        if cuota.estado == 'pendiente' and cuota.fecha_vencimiento < hoy:
            cuota.estado = 'vencida'
            cuota.save()
        
        # Verificar si hay cuotas anteriores pendientes
        cuota.hay_cuotas_anteriores_pendientes = cuotas.filter(
            numero_cuota__lt=cuota.numero_cuota,
            estado__in=['pendiente', 'vencida']
        ).exists()
    
    return render(request, 'inmobiliaria/contratos/cuotas.html', {
        'contrato': contrato,
        'cuotas': cuotas
    })

@login_required
def api_cuota_detalle(request, cuota_id):
    """API para obtener detalles de una cuota"""
    cuota = get_object_or_404(CuotaMensual, id=cuota_id, contrato__sucursal=request.user.sucursal)
    
    # Calcular recargo por mora si aplica
    if cuota.estado in ['pendiente', 'vencida'] and cuota.fecha_vencimiento < timezone.now().date():
        cuota.recargo_mora = cuota.calcular_mora()
        cuota.actualizar_monto_total()
        cuota.save()
    
    return JsonResponse({
        'id': cuota.id,
        'numero_cuota': cuota.numero_cuota,
        'monto_base': float(cuota.monto_base),  # Solo el precio mensual
        'recargo_mora': float(cuota.recargo_mora),
        'monto_total': float(cuota.monto_total)  # monto_base + recargo_mora - descuento
    })

@login_required
def pagar_cuota(request, cuota_id):
    try:
        cuota = get_object_or_404(CuotaMensual, id=cuota_id)
        contrato = cuota.contrato
        
        # Verificar que no haya cuotas anteriores pendientes
        cuotas_anteriores = contrato.cuotas.filter(
            numero_cuota__lt=cuota.numero_cuota,
            estado='pendiente'
        ).exists()
        
        if cuotas_anteriores:
            return JsonResponse({
                'error': 'Hay cuotas anteriores pendientes de pago'
            }, status=400)
        
        # Obtener caja abierta
        try:
            caja = Caja.objects.get(sucursal=request.user.sucursal, estado='abierta')
        except Caja.DoesNotExist:
            return JsonResponse({
                'error': 'No hay una caja abierta'
            }, status=400)
        
        # Procesar el pago
        with transaction.atomic():
            # Crear movimiento de caja
            movimiento = MovimientoCaja.objects.create(
                caja=caja,
                tipo='INGRESO',
                concepto=f'Cuota {cuota.numero_cuota}/{contrato.duracion_meses} - {contrato.propiedad.direccion}',
                monto_efectivo=cuota.monto_total,
                fecha=timezone.now(),
                empleado=request.user,
                sucursal=request.user.sucursal,
                propiedad=contrato.propiedad
            )
            
            # Marcar la cuota actual como pagada
            cuota.estado = 'pagada'
            cuota.fecha_pago = timezone.now().date()
            cuota.movimiento = movimiento
            cuota.save()
            
            # Actualizar fecha de vencimiento de la siguiente cuota
            siguiente_cuota = contrato.cuotas.filter(
                numero_cuota=cuota.numero_cuota + 1
            ).first()
            
            if siguiente_cuota:
                # Calcular nueva fecha de vencimiento usando el día personalizado del contrato
                fecha_actual = cuota.fecha_vencimiento
                try:
                    # Intentar usar el día de vencimiento personalizado
                    if fecha_actual.month == 12:
                        nueva_fecha = date(fecha_actual.year + 1, 1, contrato.dia_vencimiento)
                    else:
                        nueva_fecha = date(fecha_actual.year, fecha_actual.month + 1, contrato.dia_vencimiento)
                    siguiente_cuota.fecha_vencimiento = nueva_fecha
                except ValueError:
                    # Si el día no existe en el próximo mes (ej: 31 en febrero), usar el último día válido
                    if fecha_actual.month == 12:
                        nueva_fecha = date(fecha_actual.year + 1, 1, min(contrato.dia_vencimiento, 28))
                    else:
                        nueva_fecha = date(fecha_actual.year, fecha_actual.month + 1, min(contrato.dia_vencimiento, 28))
                    siguiente_cuota.fecha_vencimiento = nueva_fecha
                siguiente_cuota.save()
            
            return JsonResponse({
                'success': True,
                'redirect_url': reverse('inmobiliaria:recibo_contrato_24', args=[contrato.id])
            })
            
    except Exception as e:
        print("Error al procesar pago de cuota:", str(e))
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@require_POST
def cancelar_contrato(request, contrato_id):
    try:
        contrato = get_object_or_404(ContratoAlquiler, id=contrato_id)
        motivo = request.POST.get('motivo', '')
        
        if not motivo:
            return JsonResponse({'error': 'El motivo de cancelación es requerido'}, status=400)
        
        # Cancelar el contrato directamente
        contrato.estado = 'rescindido'
        contrato.fecha_cancelacion = timezone.now().date()
        contrato.motivo_cancelacion = motivo
        contrato.save()
        
        # Desactivar la propiedad para 24 meses (disponible = False)
        if hasattr(contrato.propiedad, 'info_meses'):
            contrato.propiedad.info_meses.disponible = False
            contrato.propiedad.info_meses.estado = 'disponible'
            contrato.propiedad.info_meses.save()
        
        messages.success(request, f'El contrato #{contrato.id} ha sido cancelado exitosamente')
        return JsonResponse({'success': True})
    except Exception as e:
        print(f"Error al cancelar contrato: {str(e)}")
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@require_POST
def reactivar_propiedad_24_meses(request, propiedad_id):
    """Reactivar una propiedad para alquileres de 24 meses"""
    try:
        propiedad = get_object_or_404(Propiedad, id=propiedad_id)
        
        if hasattr(propiedad, 'info_meses'):
            propiedad.info_meses.disponible = True
            propiedad.info_meses.estado = 'disponible'
            propiedad.info_meses.save()
            
            messages.success(request, f'La propiedad {propiedad.direccion} ha sido reactivada para alquileres de 24 meses')
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'error': 'La propiedad no está configurada para 24 meses'}, status=400)
            
    except Exception as e:
        print(f"Error al reactivar propiedad: {str(e)}")
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@require_POST
def desactivar_propiedad_24_meses(request, propiedad_id):
    """Desactivar una propiedad para alquileres de 24 meses"""
    try:
        propiedad = get_object_or_404(Propiedad, id=propiedad_id)
        
        if hasattr(propiedad, 'info_meses'):
            # Verificar si hay contratos activos
            contratos_activos = propiedad.contratos.filter(estado__in=['reservado', 'activo']).exists()
            
            if contratos_activos:
                return JsonResponse({
                    'error': 'No se puede desactivar la propiedad porque tiene contratos activos o reservados'
                }, status=400)
            
            propiedad.info_meses.disponible = False
            propiedad.info_meses.save()
            
            messages.success(request, f'La propiedad {propiedad.direccion} ha sido desactivada para alquileres de 24 meses')
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'error': 'La propiedad no está configurada para 24 meses'}, status=400)
            
    except Exception as e:
        print(f"Error al desactivar propiedad: {str(e)}")
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@require_POST
def guardar_precios_propiedad(request):
    """Guarda los precios modificados de una propiedad"""
    print("=== GUARDAR PRECIOS PROPIEDAD ===")
    
    try:
        propiedad_id = request.POST.get('propiedad_id')
        precios_json = request.POST.get('precios')
        
        print(f"Propiedad ID: {propiedad_id}")
        print(f"Precios JSON: {precios_json}")
        
        if not propiedad_id or not precios_json:
            return JsonResponse({
                'success': False,
                'error': 'Faltan datos requeridos'
            })
        
        propiedad = get_object_or_404(Propiedad, id=propiedad_id)
        
        # Solo usuarios nivel 3 o superior pueden modificar precios
        if request.user.nivel < 3:
            return JsonResponse({
                'success': False,
                'error': 'No tienes permisos para modificar precios'
            })
        
        import json
        precios_data = json.loads(precios_json)
        
        # Actualizar cada precio
        for precio_info in precios_data:
            tipo_precio = precio_info.get('tipo_precio')
            
            # Buscar o crear el precio
            precio, created = Precio.objects.get_or_create(
                propiedad=propiedad,
                tipo_precio=tipo_precio,
                defaults={
                    'precio_total': 0,
                    'precio_por_dia': 0,
                    'precio_toma': 0,
                    'precio_dia_toma': 0,
                    'ajuste_porcentaje': 0
                }
            )
            
            # Actualizar valores
            precio.precio_toma = precio_info.get('precio_toma', 0)
            precio.precio_dia_toma = precio_info.get('precio_dia_toma', 0)
            precio.precio_por_dia = precio_info.get('precio_por_dia', 0)
            precio.precio_total = precio_info.get('precio_total', 0)
            precio.ajuste_porcentaje = precio_info.get('ajuste_porcentaje', 0)
            
            precio.save()
            
            print(f"✅ Actualizado precio {tipo_precio} para propiedad {propiedad_id}")
        
        return JsonResponse({
            'success': True,
            'message': 'Precios actualizados correctamente'
        })
        
    except Exception as e:
        print(f"Error en guardar_precios_propiedad: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

def enviar_recuperacion(request):
    form = EmailForm()
    
    if request.method == "POST":
        form = EmailForm(request.POST)
        
        if form.is_valid():
            email = form.cleaned_data['email']
            User = get_user_model()
            
            try:
                # Buscar usuario por email (case-insensitive)
                user = User.objects.filter(email__iexact=email).first()
                
                if user:
                    # Verificar que el usuario tiene email válido
                    if not user.email or not user.email.strip():
                        messages.error(request, 'Tu cuenta no tiene un correo electrónico configurado. Contacta al administrador.')
                        return render(request, 'inmobiliaria/autenticacion/password_reset_form.html', {'form': form})
                    
                    # Generar una nueva contraseña temporal
                    nueva_password = User.objects.make_random_password()
                    user.set_password(nueva_password)
                    user.password_temporal = True  # Marcar como contraseña temporal
                    user.save()
                    
                    # Enviar email con la nueva contraseña
                    subject = 'Tu nueva contraseña - Sistema Gonnet'
                    message = f'''
Hola {user.first_name if user.first_name else user.username},

Tu nueva contraseña temporal es: {nueva_password}

Por favor, ingresa con esta contraseña y cámbiala inmediatamente por una de tu preferencia.

Saludos,
El equipo de Sistema Gonnet
                    '''
                    
                    try:
                        send_mail(
                            subject,
                            message,
                            'gonnetinterno@gmail.com',  # Remitente
                            [user.email],  # Destinatario
                            fail_silently=False,
                        )
                        messages.success(request, f'Se ha enviado un correo con tu nueva contraseña a {user.email}.')
                        return redirect('inmobiliaria:password_reset_done')
                    except Exception as e:
                        # Revertir el cambio de contraseña si falla el envío
                        user.refresh_from_db()
                        messages.error(request, f'Error al enviar el correo: {str(e)}. Por favor, contacta al administrador.')
                else:
                    # Mensaje simple sin debug complejo
                    messages.error(request, 'No existe una cuenta con ese correo electrónico. Verifica que esté escrito correctamente.')
                        
            except Exception as e:
                messages.error(request, f'Error al procesar la solicitud: {str(e)}')
        else:
            # Si el formulario no es válido, mostrar errores
            messages.error(request, 'Por favor, ingresa un correo electrónico válido.')
    
    return render(request, 'inmobiliaria/autenticacion/password_reset_form.html', {'form': form})

# Función temporal para recalcular precios de reservas con precio 0
def recalcular_precio_reserva(reserva):
    """
    Recalcula el precio de una reserva usando la misma lógica que buscar_propiedades_reserva
    """
    print(f"🔄 RECALCULANDO PRECIO para reserva {reserva.id}")
    
    try:
        fecha_inicio = reserva.fecha_inicio
        fecha_fin = reserva.fecha_fin
        propiedad = reserva.propiedad
        
        # Calcular noches de reserva
        noches_reserva = (fecha_fin - fecha_inicio).days
        print(f"   📅 Fechas: {fecha_inicio} al {fecha_fin} ({noches_reserva} noches)")
        
        # ✅ LÓGICA ORIGINAL QUE FUNCIONABA (copiada exacta de views_temp.py)
        precio_total = 0
        precio_mas_caro = 0
        primer_dia = True
        
        for single_date in (fecha_inicio + timedelta(n) for n in range(noches_reserva)):
            # Determinar el tipo de precio según la fecha
            tipo_precio = None
            if single_date.month == 1:  # Enero
                tipo_precio = 'QUINCENA_1_ENERO' if single_date.day <= 15 else 'QUINCENA_2_ENERO'
            elif single_date.month == 2:  # Febrero
                tipo_precio = 'QUINCENA_1_FEBRERO' if single_date.day <= 15 else 'QUINCENA_2_FEBRERO'
            elif single_date.month == 3:  # Marzo
                tipo_precio = 'QUINCENA_1_MARZO' if single_date.day <= 15 else 'QUINCENA_2_MARZO'
            elif single_date.month == 7:  # Julio (Vacaciones de Invierno)
                tipo_precio = 'VACACIONES_INVIERNO'
            elif single_date.month == 12:  # Diciembre
                tipo_precio = 'QUINCENA_1_DICIEMBRE' if single_date.day <= 15 else 'QUINCENA_2_DICIEMBRE'
            else:
                tipo_precio = 'TEMPORADA_BAJA'  # Asumir temporada baja para otros meses

            # Obtener el precio para la propiedad y la quincena correspondiente
            try:
                precio = Precio.objects.get(propiedad=propiedad, tipo_precio=tipo_precio)
                precio_dia = precio.precio_por_dia or 0
            except Precio.DoesNotExist:
                precio_dia = 0

            if precio_dia > precio_mas_caro:
                precio_mas_caro = precio_dia

            if not primer_dia:
                precio_total += precio_dia
            else:
                primer_dia = False
        
        precio_total = precio_total + precio_mas_caro
        
        print(f"   💰 PRECIO TOTAL RECALCULADO: ${precio_total:,.0f}")
        
        # Actualizar la reserva si el precio es diferente
        if precio_total != reserva.precio_total:
            reserva.precio_total = precio_total
            reserva.save()
            print(f"   ✅ RESERVA ACTUALIZADA con nuevo precio: ${precio_total:,.0f}")
        else:
            print(f"   ℹ️ El precio ya era correcto: ${precio_total:,.0f}")
            
        return precio_total
        
    except Exception as e:
        print(f"   ❌ ERROR recalculando precio: {str(e)}")
        return 0

@login_required
def finalizar_reserva_nueva(request, reserva_id):
    """
    Nueva vista para finalizar reserva basada en la carga de recibo
    """
    try:
        # Obtener la reserva
        reserva = get_object_or_404(Reserva, id=reserva_id, sucursal=request.user.sucursal)
        
        # Obtener la caja actual de la sucursal
        caja_actual = Caja.objects.filter(
            sucursal=request.user.sucursal,
            fecha_cierre__isnull=True
        ).first()
        
        if not caja_actual:
            messages.error(request, 'No hay una caja abierta. Debe abrir una caja primero.')
            return redirect('inmobiliaria:reservas')
        
        # Calcular información del próximo movimiento
        cantidad_movimientos = MovimientoCaja.objects.filter(caja=caja_actual).count()
        proximo_numero_movimiento = cantidad_movimientos + 1
        
        # Obtener conceptos de caja disponibles
        conceptos_caja = Concepto.objects.all()
        
        # ✅ CALCULAR SALDO PENDIENTE CONSIDERANDO SOLO LA SEÑA (NO EL DEPÓSITO)
        # Buscar todos los movimientos de caja pagados para esta reserva
        pagos_anteriores = MovimientoCaja.objects.filter(
            propiedad=reserva.propiedad,
            tipo=TipoMovimientoCajaEnum.INGRESO,
            concepto__icontains=f"Operaci\u00f3n {reserva.id}"
        )
        
        # ✅ LÓGICA CORREGIDA: Separar conceptos
        saldo_a_ocupar = reserva.precio_total - (reserva.senia or 0)  # Lo que falta por pagar
        
        # ✅ SEÑA PENDIENTE: Solo lo que falta por pagar (puede ser 0 si quiere pagar todo)
        # El usuario decide cuánto de la seña pagar en este momento
        senia_pendiente = saldo_a_ocupar  # Por defecto el saldo pendiente, pero el usuario puede cambiarlo
        
        # ✅ DETECTAR SI EL DEPÓSITO YA FUE PAGADO (concepto 10)
        deposito_pagado = False
        if reserva.deposito_garantia > 0:
            # Buscar movimientos con concepto 10
            for movimiento in pagos_anteriores:
                if movimiento.concepto and "|CONCEPTOS:" in movimiento.concepto:
                    concepto_parts = movimiento.concepto.split("|CONCEPTOS:", 1)
                    if len(concepto_parts) > 1:
                        conceptos_data = concepto_parts[1]
                        if "|10:" in conceptos_data:  # Concepto 10 presente
                            deposito_pagado = True
                            break
        
        deposito_estado = 'pagado' if deposito_pagado else 'pendiente'
        
        print(f"✅ CÁLCULO FINALIZAR RESERVA:")
        print(f"   - Precio Total (Importe Locación): ${reserva.precio_total}")
        print(f"   - Seña ya pagada: ${reserva.senia or 0}")
        print(f"   - Saldo Pendiente: ${saldo_a_ocupar}")
        print(f"   - Seña sugerida para este pago: ${senia_pendiente}")
        print(f"   - Depósito: ${reserva.deposito_garantia or 0} ({deposito_estado})")

        
        # Datos para el formulario 
        context = {
            'reserva': reserva,
            'cliente_id': reserva.cliente.id,
            'cliente_nombre': f"{reserva.cliente.nombre} {reserva.cliente.apellido}",
            'interno_caja': caja_actual.numero,
            'propiedad_id': reserva.propiedad.id,
            'propiedad_direccion': reserva.propiedad.direccion,
            'fecha_actual': datetime.now().strftime('%d/%m/%Y'),
            'numero_movimiento': proximo_numero_movimiento,
            'numero_recibo': '0000-00000000',  # Para completar
            'productor_id': request.user.id,
            'productor_nombre': f"{request.user.nombre} {request.user.apellido}",
            'conceptos_caja': conceptos_caja,
            'saldo_a_ocupar': saldo_a_ocupar,  # Para mostrar en resumen
            'senia_pendiente': senia_pendiente,  # Para prellenar el campo seña
            'total_senia_pagada': reserva.senia or 0,  # Lo que ya se pagó
            'total_deposito_pagado': reserva.deposito_garantia or 0,  
            'deposito_garantia': reserva.deposito_garantia,
            'deposito_estado': deposito_estado,  # ✅ Estado del depósito (pagado/pendiente)
            'fecha_desde': reserva.fecha_inicio.strftime('%d/%m/%Y'),
            'fecha_hasta': reserva.fecha_fin.strftime('%d/%m/%Y'),
        }
        
        return render(request, 'inmobiliaria/reserva/finalizar_reserva_nueva.html', context)
        
    except Exception as e:
        messages.error(request, f'Error al cargar la reserva: {str(e)}')
        return redirect('inmobiliaria:reservas')



@login_required
def eliminar_disponibilidad(request, disponibilidad_id):
    """
    Vista para eliminar una disponibilidad validando que no tenga reservas existentes
    """
    if request.method == 'POST':
        try:
            disponibilidad = get_object_or_404(Disponibilidad, id=disponibilidad_id)
            
            # Verificar que la disponibilidad pertenezca a la sucursal del usuario
            if disponibilidad.propiedad.sucursal != request.user.sucursal:
                return JsonResponse({
                    'success': False,
                    'error': 'No tienes permisos para eliminar esta disponibilidad'
                })
            
            # Buscar reservas ACTIVAS en el rango de fechas de la disponibilidad
            # Solo impedir eliminar si hay reservas ACTIVAS (no canceladas)
            reservas_existentes = Reserva.objects.filter(
                propiedad=disponibilidad.propiedad,
                estado__in=['confirmada', 'pagada', 'confirmada_no_pagada']  # Solo reservas activas
            ).filter(
                # Reserva que se superpone con la disponibilidad
                fecha_inicio__lte=disponibilidad.fecha_fin,
                fecha_fin__gte=disponibilidad.fecha_inicio
            ).order_by('fecha_inicio')
            
            # Verificar también reservas futuras (para no eliminar disponibilidades que ya tienen reservas confirmadas)
            from datetime import date
            hoy = date.today()
            
            reservas_futuras = reservas_existentes.filter(fecha_fin__gte=hoy)  # Reservas que no han terminado
            
            print(f"🔍 VALIDANDO ELIMINACIÓN DE DISPONIBILIDAD {disponibilidad.id}")
            print(f"📅 Disponibilidad: {disponibilidad.fecha_inicio} - {disponibilidad.fecha_fin}")
            print(f"🏠 Propiedad: {disponibilidad.propiedad.id}")
            print(f"📋 Reservas encontradas: {reservas_existentes.count()}")
            print(f"📋 Reservas futuras/activas: {reservas_futuras.count()}")
            
            for reserva in reservas_existentes:
                es_futura = reserva.fecha_fin >= hoy
                print(f"   - Reserva {reserva.id}: {reserva.fecha_inicio} - {reserva.fecha_fin} ({reserva.estado}) {'[ACTIVA]' if es_futura else '[PASADA]'}")
            
            if reservas_futuras.exists():
                # Si hay reservas futuras/activas, preparar la información para mostrar
                reservas_info = []
                for reserva in reservas_futuras:  # Solo mostrar las reservas activas
                    reservas_info.append({
                        'id': reserva.id,
                        'fecha_inicio': reserva.fecha_inicio.strftime('%d/%m/%Y'),
                        'fecha_fin': reserva.fecha_fin.strftime('%d/%m/%Y'),
                        'cliente': f"{reserva.cliente.nombre} {reserva.cliente.apellido}" if reserva.cliente else 'Sin cliente',
                        'estado': reserva.get_estado_display(),
                        'precio': str(reserva.precio_total)
                    })
                
                return JsonResponse({
                    'success': False,
                    'error': 'No se puede eliminar la disponibilidad',
                    'motivo': 'Existen reservas activas/futuras en este período',
                    'reservas': reservas_info,
                    'total_reservas': len(reservas_info),
                    'nota': 'Solo se pueden eliminar disponibilidades sin reservas activas o futuras'
                })
            
            # Si no hay reservas, eliminar la disponibilidad
            propiedad_direccion = disponibilidad.propiedad.direccion
            fecha_inicio = disponibilidad.fecha_inicio.strftime('%d/%m/%Y')
            fecha_fin = disponibilidad.fecha_fin.strftime('%d/%m/%Y')
            propiedad = disponibilidad.propiedad
            
            print(f"🗑️ ELIMINANDO DISPONIBILIDAD: {fecha_inicio} al {fecha_fin} para {propiedad_direccion}")
            
            # ✅ NUEVO: Eliminar la disponibilidad Y reconstruir historial
            disponibilidad.delete()
            
            # ✅ Reconstruir historial cronológico para reflejar los cambios
            from .models.propiedad import Reserva
            # Buscar una reserva de esta propiedad para usar su método de reconstruir historial
            reserva_ejemplo = Reserva.objects.filter(propiedad=propiedad).first()
            if reserva_ejemplo:
                reserva_ejemplo.reconstruir_historial_cronologico()
                print(f"✅ Historial reconstruido para propiedad {propiedad.id}")
            else:
                print(f"⚠️ No se encontraron reservas para reconstruir historial de propiedad {propiedad.id}")
            
            return JsonResponse({
                'success': True,
                'message': f'Disponibilidad eliminada correctamente del {fecha_inicio} al {fecha_fin} para {propiedad_direccion}. Historial actualizado.'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error interno: {str(e)}'
            })
    
    return JsonResponse({
        'success': False,
        'error': 'Método no permitido'
    })

@login_required
def editar_disponibilidad(request, disponibilidad_id):
    """
    Vista para editar una disponibilidad con validaciones inteligentes basadas en reservas
    """
    if request.method == 'POST':
        try:
            disponibilidad = get_object_or_404(Disponibilidad, id=disponibilidad_id)
            
            # Verificar permisos
            if disponibilidad.propiedad.sucursal != request.user.sucursal:
                return JsonResponse({
                    'success': False,
                    'error': 'No tienes permisos para editar esta disponibilidad'
                })
            
            nueva_fecha_inicio = datetime.strptime(request.POST.get('fecha_inicio'), '%Y-%m-%d').date()
            nueva_fecha_fin = datetime.strptime(request.POST.get('fecha_fin'), '%Y-%m-%d').date()
            
            # Validaciones básicas
            if nueva_fecha_inicio >= nueva_fecha_fin:
                return JsonResponse({
                    'success': False,
                    'error': 'La fecha de inicio debe ser anterior a la fecha de fin'
                })
            
            # Buscar reservas existentes en la disponibilidad actual
            reservas_en_disponibilidad = Reserva.objects.filter(
                propiedad=disponibilidad.propiedad,
                fecha_inicio__lt=disponibilidad.fecha_fin,
                fecha_fin__gt=disponibilidad.fecha_inicio,
                estado__in=['confirmada', 'pagada', 'confirmada_no_pagada']
            ).order_by('fecha_inicio')
            
            print(f"🔍 EDITANDO DISPONIBILIDAD {disponibilidad.id}")
            print(f"📅 Original: {disponibilidad.fecha_inicio} - {disponibilidad.fecha_fin}")
            print(f"📅 Nueva: {nueva_fecha_inicio} - {nueva_fecha_fin}")
            print(f"📋 Reservas en disponibilidad: {reservas_en_disponibilidad.count()}")
            
            if reservas_en_disponibilidad.exists():
                # HAY RESERVAS: Calcular límites permitidos
                primera_reserva = reservas_en_disponibilidad.first()
                ultima_reserva = reservas_en_disponibilidad.last()
                
                # Límites para fecha de inicio
                limite_inicio_maximo = primera_reserva.fecha_inicio  # No puede pasar la primera reserva
                
                # Límites para fecha de fin
                limite_fin_minimo = ultima_reserva.fecha_fin  # No puede ser antes de la última reserva
                
                print(f"🚧 LÍMITES CALCULADOS:")
                print(f"   Fecha inicio: puede ir hasta {limite_inicio_maximo} (primera reserva)")
                print(f"   Fecha fin: debe ser desde {limite_fin_minimo} (última reserva) en adelante")
                
                # Validar que las nuevas fechas respeten los límites
                if nueva_fecha_inicio > limite_inicio_maximo:
                    return JsonResponse({
                        'success': False,
                        'error': f'La fecha de inicio no puede ser posterior al {limite_inicio_maximo.strftime("%d/%m/%Y")}',
                        'motivo': f'Hay una reserva que inicia el {primera_reserva.fecha_inicio.strftime("%d/%m/%Y")}',
                        'limite_inicio_maximo': limite_inicio_maximo.strftime('%Y-%m-%d')
                    })
                
                if nueva_fecha_fin < limite_fin_minimo:
                    return JsonResponse({
                        'success': False,
                        'error': f'La fecha de fin no puede ser anterior al {limite_fin_minimo.strftime("%d/%m/%Y")}',
                        'motivo': f'Hay una reserva que termina el {ultima_reserva.fecha_fin.strftime("%d/%m/%Y")}',
                        'limite_fin_minimo': limite_fin_minimo.strftime('%Y-%m-%d')
                    })
                
            # Verificar solapamiento con otras disponibilidades
            otras_disponibilidades = Disponibilidad.objects.filter(
                propiedad=disponibilidad.propiedad
            ).exclude(id=disponibilidad.id).filter(
                fecha_inicio__lt=nueva_fecha_fin,
                fecha_fin__gt=nueva_fecha_inicio
            )
            
            if otras_disponibilidades.exists():
                conflictos = []
                for otra in otras_disponibilidades:
                    conflictos.append({
                        'id': otra.id,
                        'fecha_inicio': otra.fecha_inicio.strftime('%d/%m/%Y'),
                        'fecha_fin': otra.fecha_fin.strftime('%d/%m/%Y')
                    })
                
                return JsonResponse({
                    'success': False,
                    'error': 'Las nuevas fechas se superponen con otras disponibilidades',
                    'conflictos': conflictos
                })
            
            # Si todas las validaciones pasan, actualizar la disponibilidad
            fecha_inicio_anterior = disponibilidad.fecha_inicio.strftime('%d/%m/%Y')
            fecha_fin_anterior = disponibilidad.fecha_fin.strftime('%d/%m/%Y')
            
            disponibilidad.fecha_inicio = nueva_fecha_inicio
            disponibilidad.fecha_fin = nueva_fecha_fin
            disponibilidad.save()
            
            return JsonResponse({
                'success': True,
                'message': f'Disponibilidad actualizada correctamente',
                'cambios': {
                    'anterior': f'{fecha_inicio_anterior} - {fecha_fin_anterior}',
                    'nueva': f'{nueva_fecha_inicio.strftime("%d/%m/%Y")} - {nueva_fecha_fin.strftime("%d/%m/%Y")}'
                }
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error interno: {str(e)}'
            })
    
    elif request.method == 'GET':
        # Obtener información para edición (límites, etc.)
        try:
            disponibilidad = get_object_or_404(Disponibilidad, id=disponibilidad_id)
            
            # Buscar reservas en esta disponibilidad
            reservas_en_disponibilidad = Reserva.objects.filter(
                propiedad=disponibilidad.propiedad,
                fecha_inicio__lt=disponibilidad.fecha_fin,
                fecha_fin__gt=disponibilidad.fecha_inicio,
                estado__in=['confirmada', 'pagada', 'confirmada_no_pagada']
            ).order_by('fecha_inicio')
            
            limites = {
                'fecha_inicio_actual': disponibilidad.fecha_inicio.strftime('%Y-%m-%d'),
                'fecha_fin_actual': disponibilidad.fecha_fin.strftime('%Y-%m-%d'),
                'tiene_reservas': reservas_en_disponibilidad.exists(),
                'reservas_info': []
            }
            
            if reservas_en_disponibilidad.exists():
                primera_reserva = reservas_en_disponibilidad.first()
                ultima_reserva = reservas_en_disponibilidad.last()
                
                limites.update({
                    'limite_inicio_maximo': primera_reserva.fecha_inicio.strftime('%Y-%m-%d'),
                    'limite_fin_minimo': ultima_reserva.fecha_fin.strftime('%Y-%m-%d'),
                    'primera_reserva': {
                        'fecha_inicio': primera_reserva.fecha_inicio.strftime('%d/%m/%Y'),
                        'fecha_fin': primera_reserva.fecha_fin.strftime('%d/%m/%Y')
                    },
                    'ultima_reserva': {
                        'fecha_inicio': ultima_reserva.fecha_inicio.strftime('%d/%m/%Y'),
                        'fecha_fin': ultima_reserva.fecha_fin.strftime('%d/%m/%Y')
                    }
                })
                
                # Información de todas las reservas para mostrar al usuario
                for reserva in reservas_en_disponibilidad:
                    limites['reservas_info'].append({
                        'id': reserva.id,
                        'fecha_inicio': reserva.fecha_inicio.strftime('%d/%m/%Y'),
                        'fecha_fin': reserva.fecha_fin.strftime('%d/%m/%Y'),
                        'cliente': f"{reserva.cliente.nombre} {reserva.cliente.apellido}" if reserva.cliente else 'Sin cliente',
                        'estado': reserva.get_estado_display()
                    })
            
            return JsonResponse({
                'success': True,
                'disponibilidad': limites
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error interno: {str(e)}'
            })
    
    return JsonResponse({
        'success': False,
        'error': 'Método no permitido'
    })

@login_required
def configurar_numeracion_recibos(request, sucursal_id):
    """
    Vista para configurar la numeración automática de recibos de una sucursal
    """
    if request.method == 'POST':
        try:
            sucursal = get_object_or_404(Sucursal, id=sucursal_id)
            
            # Verificar permisos (solo administradores nivel 4)
            if request.user.nivel < 4:
                messages.error(request, 'No tienes permisos para configurar la numeración de recibos')
                return redirect('inmobiliaria:sucursal_detalle', sucursal_id=sucursal.id)
            
            usar_numeracion = request.POST.get('usar_numeracion_automatica') == 'on'
            
            print(f"🔧 CONFIGURANDO NUMERACIÓN RECIBOS - Sucursal: {sucursal.nombre}")
            print(f"   Usar numeración automática: {usar_numeracion}")
            
            if usar_numeracion:
                prefijo = request.POST.get('prefijo_recibo', '').strip()
                ultimo_numero = request.POST.get('ultimo_numero_recibo', '').strip()
                
                # Si es la primera configuración y están vacíos, usar valores por defecto
                if not prefijo:
                    prefijo = '1'  # Valor por defecto
                if not ultimo_numero:
                    ultimo_numero = '1'  # Valor por defecto
                
                print(f"   📋 DATOS RECIBIDOS:")
                print(f"      - Prefijo: '{prefijo}'")
                print(f"      - Último número: '{ultimo_numero}'")
                
                # Validaciones
                try:
                    prefijo_int = int(prefijo)
                    if prefijo_int < 1 or prefijo_int > 99999:
                        raise ValueError()
                except (ValueError, TypeError):
                    messages.error(request, 'El número identificador debe ser entre 1 y 99999')
                    return redirect('inmobiliaria:sucursal_detalle', sucursal_id=sucursal.id)
                
                try:
                    ultimo_numero_int = int(ultimo_numero)
                    if ultimo_numero_int < 1 or ultimo_numero_int > 99999:
                        raise ValueError()
                except (ValueError, TypeError):
                    messages.error(request, 'El contador inicial debe ser entre 1 y 99999')
                    return redirect('inmobiliaria:sucursal_detalle', sucursal_id=sucursal.id)
                
                # Si ya tenía numeración automática y se está cambiando el prefijo/número
                if sucursal.usar_numeracion_automatica:
                    if sucursal.prefijo_recibo != prefijo_int:
                        print(f"   📝 Cambiando prefijo: {sucursal.prefijo_recibo} → {prefijo_int}")
                    if sucursal.ultimo_numero_recibo != ultimo_numero_int:
                        # Solo permitir incrementar el número, no decrementar
                        if ultimo_numero_int < sucursal.ultimo_numero_recibo:
                            messages.warning(request, 
                                f'No se puede decrementar el contador. Último número usado: {sucursal.ultimo_numero_recibo}')
                            return redirect('inmobiliaria:sucursal_detalle', sucursal_id=sucursal.id)
                        print(f"   📈 Ajustando número: {sucursal.ultimo_numero_recibo} → {ultimo_numero_int}")
                
                # Actualizar configuración
                sucursal.usar_numeracion_automatica = True
                sucursal.prefijo_recibo = prefijo_int
                sucursal.ultimo_numero_recibo = ultimo_numero_int
                sucursal.save()
                
                proximo_numero = sucursal.obtener_proximo_numero_recibo()
                messages.success(request, f'✅ Numeración automática configurada. Próximo recibo: {proximo_numero}')
                print(f"   ✅ Configuración guardada. Próximo número: {proximo_numero}")
                
            else:
                # Desactivar numeración automática
                sucursal.usar_numeracion_automatica = False
                sucursal.save()
                messages.success(request, '✅ Numeración automática desactivada. Los recibos se ingresarán manualmente.')
                print(f"   ✅ Numeración automática desactivada")
            
            return redirect('inmobiliaria:sucursal_detalle', sucursal_id=sucursal.id)
            
        except Exception as e:
            print(f"❌ Error al configurar numeración: {e}")
            messages.error(request, f'Error al guardar configuración: {str(e)}')
            return redirect('inmobiliaria:sucursal_detalle', sucursal_id=sucursal.id)
    
    return redirect('inmobiliaria:sucursal_detalle', sucursal_id=sucursal_id)


@login_required
def recibo_contrato_24(request, contrato_id):
    """Vista para mostrar el recibo de un contrato de 24 meses"""
    try:
        contrato = get_object_or_404(ContratoAlquiler, id=contrato_id, sucursal=request.user.sucursal)
        
        # Obtener los conceptos del primer pago del contrato
        conceptos_contrato = []
        
        # Buscar el primer movimiento de caja relacionado con este contrato
        # Los movimientos de contrato incluyen el ID del contrato en el concepto
        primer_movimiento = MovimientoCaja.objects.filter(
            concepto__icontains=f'Contrato #{contrato.id}',
            propiedad=contrato.propiedad,
            sucursal=request.user.sucursal
        ).first()
        
        # Si no encontramos movimiento por concepto, buscar por cuotas pagadas
        if not primer_movimiento:
            cuota_pagada = contrato.cuotas.filter(estado='pagada', movimiento__isnull=False).first()
            if cuota_pagada and cuota_pagada.movimiento:
                primer_movimiento = cuota_pagada.movimiento
        
        if primer_movimiento and primer_movimiento.concepto:
            # Parsear los conceptos del movimiento
            try:
                import json
                conceptos_data = json.loads(primer_movimiento.concepto)
                for concepto_data in conceptos_data:
                    conceptos_contrato.append({
                        'fecha': primer_movimiento.fecha,
                        'codigo': concepto_data.get('id', ''),
                        'nombre': concepto_data.get('nombre', ''),
                        'importe': f"${float(concepto_data.get('importe', 0)):,.2f}".replace(',', '.')
                    })
            except (json.JSONDecodeError, ValueError):
                # Si no se puede parsear como JSON, usar formato fallback
                conceptos_contrato.append({
                    'fecha': primer_movimiento.fecha,
                    'codigo': '90',
                    'nombre': primer_movimiento.concepto,
                    'importe': f"${primer_movimiento.monto_efectivo:,.2f}".replace(',', '.')
                })
        else:
            # Si no hay movimientos, usar datos básicos del contrato
            conceptos_contrato.append({
                'fecha': contrato.fecha_operacion,
                'codigo': '90',
                'nombre': f'CONTRATO ALQUILER - {contrato.propiedad.direccion}',
                'importe': f"${contrato.precio_mensual:,.2f}".replace(',', '.')
            })
        
        # Obtener valores de honorarios y sellados del movimiento (si existen)
        from decimal import Decimal
        
        alquiler_mensual = contrato.precio_mensual
        
        # LÓGICA SIMPLIFICADA: El total es la suma de todos los conceptos + honorarios + sellados
        total_conceptos = sum(concepto['importe'] for concepto in conceptos_contrato)
        
        # Honorarios y sellados desde el movimiento
        honorarios = Decimal('0')
        sellado = Decimal('0')
        
        if primer_movimiento:
            honorarios = getattr(primer_movimiento, 'honorarios', Decimal('0')) or Decimal('0')
            sellado = getattr(primer_movimiento, 'sellados', Decimal('0')) or Decimal('0')
            print(f"🔍 DEBUG RECIBO:")
            print(f"  - Total conceptos: {total_conceptos}")
            print(f"  - Honorarios: {honorarios}")
            print(f"  - Sellados: {sellado}")
        
        # El total del recibo es: conceptos + honorarios + sellados
        total_a_abonar = total_conceptos + honorarios + sellado
        subtotal = total_a_abonar
        total_contrato = total_a_abonar
        
        # Para el template (estos son solo informativos)
        deposito_garantia = contrato.deposito_garantia or Decimal('0')
        primer_mes = alquiler_mensual
        
        print(f"  - TOTAL FINAL: {total_a_abonar}")
        
        # Convertir números a formato de pesos argentinos
        def format_currency(amount):
            return f"${float(amount):,.2f}".replace(',', '.')
        
        # Obtener logo en base64
        logo_base64 = None
        try:
            import base64
            import os
            logo_path = os.path.join(os.path.dirname(__file__), 'static', 'images', 'logo.png')
            if os.path.exists(logo_path):
                with open(logo_path, 'rb') as logo_file:
                    logo_base64 = base64.b64encode(logo_file.read()).decode('utf-8')
        except Exception as e:
            print(f"Error al cargar logo: {e}")
        
        # Función para convertir número a texto (básica)
        def numero_a_texto(numero):
            # Implementación simple - en producción usar una librería como num2words
            if numero > 0:
                return f"PESOS {str(int(float(numero))).upper()}"
            return ""
        
        context = {
            'contrato': contrato,
            'conceptos_contrato': conceptos_contrato,
            'primer_mes': format_currency(primer_mes),
            'alquiler_mensual': format_currency(alquiler_mensual),
            'deposito_garantia': format_currency(deposito_garantia),
            'honorarios': format_currency(honorarios),
            'sellado': format_currency(sellado),
            'total_a_abonar': format_currency(total_a_abonar),
            'subtotal': format_currency(subtotal),
            'total_contrato': format_currency(total_contrato),
            'suma_en_letras': numero_a_texto(total_contrato),
            'logo_base64': logo_base64,
        }
        
        return render(request, 'inmobiliaria/contratos/recibo_contrato_24.html', context)
        
    except Exception as e:
        logger.error(f"Error al generar recibo de contrato: {str(e)}")
        messages.error(request, f'Error al generar recibo: {str(e)}')
        return redirect('inmobiliaria:lista_contratos')


@login_required
def detalles_operacion_reserva(request, reserva_id):
    """
    API endpoint para obtener detalles de la operación de una reserva
    """
    try:
        reserva = get_object_or_404(Reserva, id=reserva_id)
        
        # Obtener movimientos de caja asociados a esta reserva
        # Buscar a través de los recibos que están relacionados con la reserva
        movimientos = MovimientoCaja.objects.filter(
            Q(recibo__reserva=reserva) |
            Q(concepto__icontains=f'Reserva #{reserva.id}') |
            Q(concepto__icontains=f'Reserva {reserva.id}') |
            Q(concepto__icontains=f'#{reserva.id}')
        ).order_by('fecha')
        
        # Calcular totales sumando todos los tipos de montos
        total_pagado = 0
        for movimiento in movimientos:
            total_movimiento = (
                movimiento.monto_efectivo + 
                movimiento.monto_cheque + 
                movimiento.monto_tarjeta + 
                movimiento.monto_deposito
            )
            total_pagado += total_movimiento
        
        saldo_pendiente = max(0, reserva.precio_total - total_pagado)
        
        # Obtener recibos generados a través de la relación
        recibos = []
        recibos_reserva = reserva.recibos.all().order_by('fecha_emision')
        for recibo in recibos_reserva:
            recibos.append({
                'id': recibo.id,
                'numero': recibo.numero_recibo,
                'fecha': recibo.fecha_emision.strftime('%d/%m/%Y'),
                'monto': float(recibo.monto_este_pago),
                'concepto': recibo.movimiento_caja.concepto if recibo.movimiento_caja else 'N/A',
                'movimiento_id': recibo.movimiento_caja.id if recibo.movimiento_caja else None
            })
        
        # Calcular precio por día desde la relación con Precio
        precio_por_dia = 0
        try:
            # Buscar precio por día en los precios de la propiedad
            precio_obj = reserva.propiedad.precios.filter(precio_por_dia__isnull=False).first()
            if precio_obj and precio_obj.precio_por_dia:
                precio_por_dia = float(precio_obj.precio_por_dia)
        except:
            precio_por_dia = 0
        
        # Preparar datos de respuesta
        operacion_data = {
            'importe_total': float(reserva.precio_total),
            'precio_por_dia': precio_por_dia,
            'senia_pagada': float(total_pagado),
            'deposito': float(reserva.deposito_garantia) if reserva.deposito_garantia else 0,
            'saldo_pendiente': float(saldo_pendiente),
            'recibos': recibos
        }
        
        reserva_data = {
            'id': reserva.id,
            'cliente': reserva.cliente.nombre if reserva.cliente else 'No especificado',
            'fecha_inicio': reserva.fecha_inicio.strftime('%d/%m/%Y'),
            'fecha_fin': reserva.fecha_fin.strftime('%d/%m/%Y'),
            'total_dias': (reserva.fecha_fin - reserva.fecha_inicio).days,
            'estado': reserva.estado
        }
        
        return JsonResponse({
            'success': True,
            'operacion': operacion_data,
            'reserva': reserva_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error al cargar detalles: {str(e)}'
        })


@login_required
def gestionar_conceptos(request):
    """
    Vista para gestionar conceptos: listar, crear, editar y eliminar
    """
    sucursal_vendedor = request.user.sucursal
    # Mostrar conceptos de TODAS las sucursales
    conceptos = Concepto.objects.all().order_by('id')
    
    # Formulario para crear nuevo concepto
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'crear':
            nuevo_id = request.POST.get('nuevo_id')
            nuevo_nombre = request.POST.get('nuevo_nombre')
            
            if nuevo_id and nuevo_nombre:
                try:
                    Concepto.objects.create(
                        id=nuevo_id,
                        nombre=nuevo_nombre,
                        sucursal=sucursal_vendedor
                    )
                    messages.success(request, f'Concepto "{nuevo_nombre}" creado exitosamente.')
                except Exception as e:
                    messages.error(request, f'Error al crear concepto: {e}')
            else:
                messages.error(request, 'ID y nombre son requeridos.')
        
        elif action == 'editar':
            concepto_id = request.POST.get('concepto_id')
            nuevo_nombre = request.POST.get('nuevo_nombre')
            
            try:
                # Buscar concepto en todas las sucursales
                concepto = Concepto.objects.get(id=concepto_id)
                concepto.nombre = nuevo_nombre
                concepto.save()
                messages.success(request, f'Concepto actualizado exitosamente.')
            except Concepto.DoesNotExist:
                messages.error(request, 'Concepto no encontrado.')
            except Exception as e:
                messages.error(request, f'Error al actualizar concepto: {e}')
        
        elif action == 'eliminar':
            concepto_id = request.POST.get('concepto_id')
            
            try:
                # Buscar concepto en todas las sucursales
                concepto = Concepto.objects.get(id=concepto_id)
                nombre_concepto = concepto.nombre
                concepto.delete()
                messages.success(request, f'Concepto "{nombre_concepto}" eliminado exitosamente.')
            except Concepto.DoesNotExist:
                messages.error(request, 'Concepto no encontrado.')
            except Exception as e:
                messages.error(request, f'Error al eliminar concepto: {e}')
        
        return redirect('inmobiliaria:gestionar_conceptos')
    
    context = {
        'conceptos': conceptos,
        'total_conceptos': conceptos.count(),
        'sucursal': 'Todas las sucursales'
    }
    
    return render(request, 'inmobiliaria/conceptos/gestionar_conceptos.html', context)
