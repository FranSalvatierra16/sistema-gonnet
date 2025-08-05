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
from django.db.models import Q, Prefetch, Case, When, IntegerField, Sum, Max, F
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
            return redirect('inmobiliaria:inquilino_detalle', inquilino_id=inquilino.id)
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
    # Obtener propiedades de la sucursal y ordenar por id desde el inicio
    propiedades = Propiedad.objects.filter(sucursal=request.user.sucursal).order_by('id')

    if form.is_valid():
        query = form.cleaned_data.get('query')
        if query:
            propiedades = propiedades.filter(
                Q(direccion__icontains=query) |
                Q(id__icontains=query) |
                Q(propietario__nombre__icontains=query) |
                Q(propietario__apellido__icontains=query)
            ).order_by('id')  # Mantener el orden incluso después de la búsqueda

    return render(request, 'inmobiliaria/propiedades/lista.html', {
        'form': form,
        'propiedades': propiedades
    })

@login_required
def propiedad_detalle(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, pk=propiedad_id)
    disponibilidades = propiedad.disponibilidades.all()
    
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

    context = {
        'propiedad': propiedad,
        'disponibilidades': disponibilidades,
        'precios': precios,
        'imagenes': imagenes,
        'historiales': historiales,  # Agregamos el historial al contexto
        'active_tab': request.GET.get('tab', 'alquiler'),  # default a 'alquiler'
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
    reservas = Reserva.objects.filter(sucursal=request.user.sucursal)
    return render(request, 'inmobiliaria/reserva/lista.html', {'reservas': reservas})
def operaciones(request):
    # Obtener solo reservas pagadas (completas o con saldo pendiente)
    reservas = Reserva.objects.filter(
        sucursal=request.user.sucursal,
        estado__in=['pagada', 'confirmada_no_pagada']
    ).prefetch_related('pagos')
    
    # Calcular totales pagados para cada reserva
    for reserva in reservas:
        # Buscar movimientos de caja relacionados con esta reserva
        movimientos = MovimientoCaja.objects.filter(
            propiedad=reserva.propiedad,
            tipo=TipoMovimientoCajaEnum.INGRESO,
            concepto__icontains=f"Reserva {reserva.id}"
        )
        
        # Calcular total pagado desde movimientos de caja
        total_pagado = sum(
            mov.monto_efectivo + mov.monto_cheque + mov.monto_tarjeta + mov.monto_deposito
            for mov in movimientos
        )
        
        # ✅ CORRECCIÓN: Calcular saldo pendiente correctamente:
        # El saldo pendiente es: precio_total - TODOS LOS PAGOS realizados
        reserva.total_pagado = total_pagado
        reserva.saldo_pendiente = reserva.precio_total - total_pagado
        
        # Obtener el movimiento más reciente para el enlace del recibo
        reserva.movimiento_reciente = movimientos.first() if movimientos.exists() else None
    
    return render(request, 'inmobiliaria/reserva/operaciones.html', {'reservas': reservas})
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
        reserva.delete()
        messages.success(request, 'Reserva eliminada exitosamente.')
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

                # Limpiar el precio y convertirlo a float
                precio_limpio = precio.replace('$', '').replace(',', '').replace('.', '').strip()
                try:
                    precio_float = float(precio_limpio)  # Ya no dividir por 100
                except ValueError:
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

                # Buscar la disponibilidad que cubre el período de la reserva
                disponibilidad = Disponibilidad.objects.filter(
                    propiedad=propiedad,
                    fecha_inicio__lte=fecha_inicio,
                    fecha_fin__gte=fecha_fin
                ).first()

                if disponibilidad:
                    # Eliminar la disponibilidad actual
                    disponibilidad_inicio = disponibilidad.fecha_inicio
                    disponibilidad_fin = disponibilidad.fecha_fin
                    disponibilidad.delete()

                    # Crear disponibilidad antes de la reserva si es necesario
                    if disponibilidad_inicio < fecha_inicio:
                        Disponibilidad.objects.create(
                            propiedad=propiedad,
                            fecha_inicio=disponibilidad_inicio,
                            fecha_fin=fecha_inicio
                        )

                    # Crear disponibilidad después de la reserva si es necesario
                    if disponibilidad_fin > fecha_fin:
                        Disponibilidad.objects.create(
                            propiedad=propiedad,
                            fecha_inicio=fecha_fin,
                            fecha_fin=disponibilidad_fin
                        )

                # Crear historial de disponibilidad
                HistorialDisponibilidad.objects.create(
                    propiedad=propiedad,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    estado='ocupado' if es_operacion_directa else 'reservado',
                    reserva=reserva
                )

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

                return JsonResponse({
                    'success': True,
                    'reserva_id': reserva.id,
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


@login_required
def buscar_propiedades_reserva(request):
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

        # Filtrar propiedades que están disponibles en las fechas indicadas
        for propiedad in propiedades:
            disponibilidades = Disponibilidad.objects.filter(
                propiedad=propiedad,
                fecha_inicio__lte=fecha_fin,
                fecha_fin__gte=fecha_inicio,
            )

            # Obtener las reservas asociadas a la propiedad
            reservas = propiedad.reservas.filter(
                Q(fecha_inicio__lt=fecha_fin) & Q(fecha_fin__gt=fecha_inicio)
            )
            
            if reservas.filter(estado='pagada').exists():
                continue  # Saltar esta propiedad si ya tiene una reserva pagada

            # Verificar si existe una reserva en estado 'en espera' (confirmada no pagada)
            reserva_confirmada_no_pagada = reservas.filter(estado='en_espera').first()

            # Evaluar la disponibilidad y las reservas de la propiedad
            if disponibilidades.exists() and not reservas.filter(estado='confirmada').exists():
                if reserva_confirmada_no_pagada:
                    propiedad.reserva = reserva_confirmada_no_pagada
                    propiedad.estado_reserva = 'confirmada_no_pagada'
                    propiedad.precio_total_reserva = reserva_confirmada_no_pagada.precio_total
                else:
                    propiedad.estado_reserva = 'disponible'

                # Calcular el precio total de la reserva según las fechas seleccionadas
                precio_total = 0
                precio_mas_caro = 0
                primer_dia = True
                print('fecha de inicio',fecha_inicio)
                print('fecha de fin',fecha_fin)
                dias_reserva = (fecha_fin - fecha_inicio).days + 1
                total_dias_reserva = dias_reserva - 1

                for single_date in (fecha_inicio + timedelta(n) for n in range(dias_reserva)):
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

                propiedad.precio_total_reserva = precio_total + precio_mas_caro

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

    for propiedad in propiedades_disponibles:
        try:
            # Obtener los precios para la propiedad
            precios = propiedad.precios.all()
            precio_total = 0
            
            if fecha_inicio and fecha_fin:
                dias_totales = (fecha_fin - fecha_inicio).days + 1
                # Buscar el precio correspondiente según el período
                for precio in precios:
                    if precio.precio_por_dia:
                        precio_total = float(precio.precio_por_dia) * dias_totales
                        break
            
            propiedad.precio_total_reserva = precio_total
            
        except Exception as e:
            print(f"Error calculando precio para propiedad {propiedad.id}: {str(e)}")
            propiedad.precio_total_reserva = 0

    return render(request, 'inmobiliaria/reserva/buscar_propiedades.html', {
        'form': form,
        'propiedades_disponibles': propiedades_disponibles,
        'alerta_sin_precio': alerta_sin_precio,
        'fecha_inicio': fecha_inicio.strftime('%d/%m/%Y') if fecha_inicio else '',
        'fecha_fin': fecha_fin.strftime('%d/%m/%Y') if fecha_fin else '',
        'inquilinos': Inquilino.objects.all().order_by('apellido', 'nombre'),
        'vendedores': vendedores,
        'tipos_precio': TipoPrecio,
        'inquilino_form': inquilino_form,
        'total_dias': total_dias_reserva,
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
                    fecha_fin=form.cleaned_data['fecha_fin']
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
        
        # ✅ CALCULAR SALDO PENDIENTE CONSIDERANDO PAGOS ANTERIORES
        # Buscar todos los movimientos de caja pagados para esta reserva
        pagos_anteriores = MovimientoCaja.objects.filter(
            propiedad=reserva.propiedad,
            tipo=TipoMovimientoCajaEnum.INGRESO,
            concepto__icontains=f"Reserva {reserva.id}"
        )
        
        # Calcular total pagado hasta ahora
        total_pagado_anterior = sum(
            pago.monto_efectivo + pago.monto_cheque + pago.monto_tarjeta + pago.monto_deposito
            for pago in pagos_anteriores
        )
        
        # Saldo pendiente = Precio total - Total pagado hasta ahora
        saldo_a_ocupar = reserva.precio_total - total_pagado_anterior
        
        print(f"💰 CÁLCULO SALDO - Precio Total: {reserva.precio_total}, Total Pagado: {total_pagado_anterior}, Saldo Pendiente: {saldo_a_ocupar}")
        
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
            'total_pagado_anterior': total_pagado_anterior,
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
                    
                    # Actualizar la reserva
                    reserva.senia = total_pagado
                    reserva.deposito = deposito
                    reserva.cuota_pendiente = reserva.precio_total - total_pagado
                    
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
                            concepto=f"Reserva #{reserva.id} - {reserva.propiedad.direccion}",
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
        
        # Calcular saldo pendiente actual para el contexto
        total_pagado = sum(pago.monto for pago in pagos_previos)
        saldo_pendiente = reserva.precio_total - total_pagado
        
        context = {
            'reserva': reserva,
            'conceptos_pago': conceptos_pago,
            'pagos_previos': pagos_previos,
            'formas_pago': Pago.FORMA_PAGO_CHOICES,
            'total_pagado': total_pagado,
            'saldo_pendiente': reserva.cuota_pendiente,
            'deposito': reserva.deposito_garantia or 0
        }
        
        return render(request, 'inmobiliaria/reserva/finalizar_reserva.html', context)
        
    except Exception as e:
        messages.error(request, f'Error al procesar la reserva: {str(e)}')
        return redirect('inmobiliaria:finalizar_reserva', reserva_id=reserva_id)

@login_required
def ver_recibo(request, reserva_id):
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
                concepto=f"Reserva #{reserva.id} - {reserva.propiedad.direccion}",
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
        
        # Continuar con la generación del recibo
        template = get_template('inmobiliaria/html.recibo/recibo.html')
        context = {
            'reserva': reserva,
            'fecha_actual': timezone.now(),
        }
        html = template.render(context)
        
        # Crear el PDF
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'filename=recibo_{reserva.id}.pdf'
        
        pisa_status = pisa.CreatePDF(html, dest=response)
        if pisa_status.err:
            return HttpResponse('Error al generar el PDF', status=500)
        
        return response
        
    except Exception as e:
        messages.error(request, f'Error al generar el recibo: {str(e)}')
        return redirect('inmobiliaria:finalizar_reserva', reserva_id=reserva_id)

def generar_recibo_pdf(reserva, pago_senia):
    template_name = 'inmobiliaria/reserva/recibo.html'
    context = {'reserva': reserva, 'pago_senia': pago_senia}
    
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
                'concepto': f"Reserva {reserva.id} - {reserva.propiedad.direccion}",
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
            
            # Crear movimiento principal (sin transferencias)
            movimiento_principal = MovimientoCaja.objects.create(
                caja=caja_actual,
                sucursal=request.user.sucursal,
                tipo=TipoMovimientoCajaEnum.INGRESO,
                concepto=f"Reserva {reserva.id} - {reserva.propiedad.direccion}",
                propiedad=reserva.propiedad,
                fecha_desde=reserva.fecha_inicio,
                fecha_hasta=reserva.fecha_fin,
                monto_efectivo=monto_efectivo,
                monto_cheque=monto_cheque,
                monto_tarjeta=monto_tarjeta,
                monto_deposito=monto_deposito,  # ✅ Incluir total de transferencias
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
                concepto_actualizado = f"Reserva {reserva.id} - Galicia: ${monto_deposito_galicia}, MP: ${monto_deposito_mp}"
                movimiento_principal.concepto = concepto_actualizado
                movimiento_principal.save()
            
            print(f"✅ MOVIMIENTO ÚNICO CREADO - ID: {movimiento_principal.id}, Total: ${monto_efectivo + monto_cheque + monto_tarjeta + monto_deposito}")
            
            # Usar el movimiento principal para la respuesta
            movimiento = movimiento_principal
            
            # Obtener datos de pago de la reserva original (limpiados)
            senia_input = limpiar_valor_monetario(request.POST.get('senia', '0'))
            importe_locacion_input = limpiar_valor_monetario(request.POST.get('importe_locacion', '0'))
            
            try:
                senia = Decimal(senia_input) if senia_input else Decimal('0')
                importe_locacion = Decimal(importe_locacion_input) if importe_locacion_input else Decimal('0')
                
                # Actualizar reserva con información de pagos
                reserva.senia = senia
                # Si tienes un campo precio_locacion en el modelo, úsalo
                # reserva.precio_locacion = importe_locacion
                
            except (ValueError, TypeError):
                # Si hay error en la conversión, usar valores por defecto
                reserva.senia = Decimal('0')
                
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

@login_required
def ver_recibo_movimiento(request, movimiento_id):
    """
    Vista para mostrar el recibo basado en un MovimientoCaja
    """
    try:
        # Obtener el movimiento de caja principal
        movimiento = get_object_or_404(MovimientoCaja, id=movimiento_id, sucursal=request.user.sucursal)
        
        # Obtener la reserva relacionada desde el concepto del movimiento
        reserva = None
        if movimiento.concepto and "Reserva" in movimiento.concepto:
            try:
                # Extraer el ID de la reserva del concepto (formato: "Reserva 123 - Dirección")
                import re
                match = re.search(r'Reserva (\d+)', movimiento.concepto)
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
        if reserva:
            # Buscar todos los movimientos de esta reserva para calcular total pagado
            todos_movimientos = MovimientoCaja.objects.filter(
                propiedad=reserva.propiedad,
                tipo=TipoMovimientoCajaEnum.INGRESO,
                concepto__icontains=f"Reserva {reserva.id}"
            )
            
            print(f"🔍 BÚSQUEDA MOVIMIENTOS - Buscando concepto: 'Reserva {reserva.id}'")
            print(f"🔍 MOVIMIENTOS ENCONTRADOS: {todos_movimientos.count()}")
            for mov in todos_movimientos:
                print(f"🔍 Movimiento ID: {mov.id}, Concepto: '{mov.concepto}', Total: {mov.monto_efectivo + mov.monto_cheque + mov.monto_tarjeta + mov.monto_deposito}")
            
            total_pagado_reserva = sum(
                m.monto_efectivo + m.monto_cheque + m.monto_tarjeta + m.monto_deposito
                for m in todos_movimientos
            )
            
            # ✅ CORRECCIÓN: El saldo pendiente es precio total - TODOS LOS PAGOS
            saldo_pendiente = reserva.precio_total - total_pagado_reserva
            
            print(f"💰 SALDO CÁLCULO - Precio Total: {reserva.precio_total}, Total Pagado: {total_pagado_reserva}, Saldo Pendiente: {saldo_pendiente}")
        else:
            total_pagado_reserva = total_movimiento
        
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
def crear_inquilino_ajax(request):
    if request.method == 'POST':
        try:
            # Obtener la sucursal del usuario logueado
            sucursal = request.user.sucursal
            
            inquilino = Inquilino.objects.create(
                nombre=request.POST['nombre'],
                apellido=request.POST['apellido'],
                fecha_nacimiento=request.POST['fecha_nacimiento'],
                email=request.POST['email'],
                celular=request.POST['celular'],
                tipo_doc=request.POST['tipo_doc'],
                dni=request.POST['dni'],
                tipo_ins=request.POST['tipo_ins'],
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
        errores = []
        
        try:
            # Verificar que las propiedades pertenezcan a la sucursal del usuario
            for propiedad_id in propiedad_ids:
                try:
                    propiedad = Propiedad.objects.get(
                        id=propiedad_id,
                        sucursal=sucursal  # Usar la sucursal del usuario
                    )
                    Disponibilidad.objects.create(
                        propiedad=propiedad,
                        fecha_inicio=fecha_inicio,
                        fecha_fin=fecha_fin
                    )
                    propiedades_actualizadas += 1
                except Propiedad.DoesNotExist:
                    errores.append(f"Propiedad {propiedad_id} no pertenece a su sucursal")
                except Exception as e:
                    errores.append(f"Error en propiedad {propiedad_id}: {str(e)}")
            
            if propiedades_actualizadas > 0:
                mensaje = f'Se actualizó la disponibilidad de {propiedades_actualizadas} propiedades'
                if errores:
                    mensaje += f'\nPero hubo {len(errores)} errores'
                return JsonResponse({
                    'success': True,
                    'message': mensaje
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': f'No se pudo actualizar ninguna propiedad.\nErrores: {", ".join(errores)}'
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
    if request.method == "POST":
        email = request.POST.get("email")
        User = get_user_model()
        
        try:
            # Obtener el primer usuario con ese email
            user = User.objects.filter(email=email).first()
            
            if user:
                # Generar una nueva contraseña temporal
                nueva_password = User.objects.make_random_password()
                user.set_password(nueva_password)
                user.password_temporal = True  # Marcar como contraseña temporal
                user.save()
                
                # Enviar email con la nueva contraseña
                subject = 'Tu nueva contraseña - Gonnet'
                message = f'''
                Hola {user.username},
                
                Tu nueva contraseña temporal es: {nueva_password}
                
                Por favor, ingresa con esta contraseña y cámbiala inmediatamente por una de tu preferencia.
                
                Saludos,
                El equipo de Gonnet
                '''
                
                try:
                    send_mail(
                        subject,
                        message,
                        'gonnetinterno@gmail.com',  # Remitente
                        [email],  # Destinatario
                        fail_silently=False,
                    )
                    messages.success(request, 'Se ha enviado un correo con tu nueva contraseña.')
                    return redirect('login')
                except Exception as e:
                    messages.error(request, f'Error al enviar el correo: {str(e)}')
            else:
                messages.error(request, 'No existe una cuenta con ese correo electrónico.')
        except Exception as e:
            messages.error(request, f'Error al procesar la solicitud: {str(e)}')
    
    return render(request, 'inmobiliaria/autenticacion/password_reset_form.html')

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
                
                # Actualizar saldos de la reserva
                total_pagado = Pago.objects.filter(reserva=reserva).aggregate(
                    total=models.Sum('monto'))['total'] or Decimal('0')
                
                reserva.senia = total_pagado
                reserva.cuota_pendiente = reserva.precio_total - total_pagado
                
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
    historial = HistorialDisponibilidad.objects.filter(
        propiedad=propiedad
    ).order_by('fecha_inicio')

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
def editar_info_venta(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    info_venta, created = VentaPropiedad.objects.get_or_create(propiedad=propiedad)

    if request.method == 'POST':
        # Actualizar en_venta
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

    context = {
        'propiedades': propiedades_venta,
        'busqueda': busqueda,
        'estado_filtro': estado,
        'estados': VentaPropiedad.ESTADO_CHOICES,
        'telefono_empresa': '5492235916229',
        'total_propiedades': total_propiedades,
        'propiedades_disponibles': propiedades_disponibles,
        'propiedades_reservadas': propiedades_reservadas,
    }
    
    return render(request, 'inmobiliaria/propiedades/ventas.html', context)

@login_required
def alquileres_24_meses(request):
    # Filtrar propiedades que tienen info de alquiler por meses y están disponibles o reservadas
    propiedades_meses = Propiedad.objects.filter(
        info_meses__disponible=True,
        info_meses__estado__in=['disponible', 'reservado']
    ).select_related('info_meses', 'sucursal')

    # Aplicar filtros de búsqueda si existen
    busqueda = request.GET.get('busqueda', '')
    if busqueda:
        propiedades_meses = propiedades_meses.filter(
            Q(direccion__icontains=busqueda) |
            Q(id__icontains=busqueda)
        )

    estado = request.GET.get('estado', '')
    if estado:
        propiedades_meses = propiedades_meses.filter(info_meses__estado=estado)

    context = {
        'propiedades': propiedades_meses,
        'busqueda': busqueda,
        'estado_filtro': estado,
        'estados': AlquilerMeses.ESTADO_CHOICES,
        'inquilinos': Inquilino.objects.all().order_by('apellido', 'nombre'),
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
    # Si acceden por navegador normal, puedes devolver una plantilla o un error

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
                'nombre': mov.concepto.nombre
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
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'})
    
    termino = request.POST.get('termino', '')
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

        # Filtrar propiedades que están disponibles en las fechas indicadas
        for propiedad in propiedades:
            disponibilidades = Disponibilidad.objects.filter(
                propiedad=propiedad,
                fecha_inicio__lte=fecha_fin,
                fecha_fin__gte=fecha_inicio,
            )

            # Obtener las reservas asociadas a la propiedad
            reservas = propiedad.reservas.filter(
                Q(fecha_inicio__lt=fecha_fin) & Q(fecha_fin__gt=fecha_inicio)
            )
            
            if reservas.filter(estado='pagada').exists():
                continue  # Saltar esta propiedad si ya tiene una reserva pagada

            # Verificar si existe una reserva en estado 'confirmada_no_pagada'
            reserva_confirmada_no_pagada = reservas.filter(estado='confirmada_no_pagada').first()

            # Evaluar la disponibilidad y las reservas de la propiedad
            if disponibilidades.exists() and not reservas.filter(estado='confirmada').exists():
                if reserva_confirmada_no_pagada:
                    propiedad.reserva = reserva_confirmada_no_pagada
                    propiedad.estado_reserva = 'confirmada_no_pagada'
                    propiedad.precio_total_reserva = reserva_confirmada_no_pagada.precio_total
                else:
                    propiedad.estado_reserva = 'disponible'

                # Calcular el precio total de la reserva según las fechas seleccionadas
                precio_total = 0
                precio_mas_caro = 0
                primer_dia = True
                print('fecha de inicio',fecha_inicio)
                print('fecha de fin',fecha_fin)
                dias_reserva = (fecha_fin - fecha_inicio).days + 1
                total_dias_reserva = dias_reserva - 1

                for single_date in (fecha_inicio + timedelta(n) for n in range(dias_reserva)):
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

                propiedad.precio_total_reserva = precio_total + precio_mas_caro

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

    for propiedad in propiedades_disponibles:
        try:
            # Obtener los precios para la propiedad
            precios = propiedad.precios.all()
            precio_total = 0
            
            if fecha_inicio and fecha_fin:
                dias_totales = (fecha_fin - fecha_inicio).days + 1
                # Buscar el precio correspondiente según el período
                for precio in precios:
                    if precio.precio_por_dia:
                        precio_total = float(precio.precio_por_dia) * dias_totales
                        break
            
            propiedad.precio_total_reserva = precio_total
            
        except Exception as e:
            print(f"Error calculando precio para propiedad {propiedad.id}: {str(e)}")
            propiedad.precio_total_reserva = 0

    return render(request, 'inmobiliaria/reserva/buscar_propiedades.html', {
        'form': form,
        'propiedades_disponibles': propiedades_disponibles,
        'alerta_sin_precio': alerta_sin_precio,
        'fecha_inicio': fecha_inicio.strftime('%d/%m/%Y') if fecha_inicio else '',
        'fecha_fin': fecha_fin.strftime('%d/%m/%Y') if fecha_fin else '',
        'inquilinos': Inquilino.objects.all().order_by('apellido', 'nombre'),
        'vendedores': vendedores,
        'tipos_precio': TipoPrecio,
        'conceptos': conceptos
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
def crear_contrato_alquiler(request):
    """Vista para crear un nuevo contrato de alquiler"""
    if request.method == 'POST':
        try:
            from datetime import datetime, timedelta
            from dateutil.relativedelta import relativedelta
            from decimal import Decimal
            from .models import ContratoAlquiler
            
            # Obtener datos del formulario
            propiedad_id = request.POST.get('propiedad_id')
            inquilino_id = request.POST.get('inquilino_id')
            vendedor_id = request.POST.get('vendedor_id')
            fecha_operacion = request.POST.get('fecha_operacion')
            fecha_inicio = request.POST.get('fecha_inicio')
            fecha_fin = request.POST.get('fecha_fin')
            duracion_meses = int(request.POST.get('duracion_meses', 24))
            precio_mensual_str = request.POST.get('precio_mensual', '0').replace('.', '')
            deposito_garantia_str = request.POST.get('deposito_garantia', '0').replace('.', '')
            
            # Validaciones
            if not all([propiedad_id, inquilino_id, vendedor_id, fecha_operacion, fecha_inicio, fecha_fin]):
                messages.error(request, 'Todos los campos son obligatorios')
                return redirect('inmobiliaria:alquileres_24_meses')
            
            # Obtener objetos relacionados
            try:
                propiedad = Propiedad.objects.get(id=propiedad_id)  # Ya no filtramos por sucursal
            except Propiedad.DoesNotExist:
                messages.error(request, 'La propiedad no existe')
                return redirect('inmobiliaria:alquileres_24_meses')
            
            try:
                inquilino = Inquilino.objects.get(id=inquilino_id)
            except Inquilino.DoesNotExist:
                messages.error(request, 'El inquilino no existe')
                return redirect('inmobiliaria:alquileres_24_meses')
            
            try:
                vendedor = Vendedor.objects.get(id=vendedor_id)
            except Vendedor.DoesNotExist:
                messages.error(request, 'El vendedor no existe')
                return redirect('inmobiliaria:alquileres_24_meses')
            
            # Convertir valores monetarios
            precio_mensual = Decimal(precio_mensual_str)
            deposito_garantia = Decimal(deposito_garantia_str)
            
            # Parsear fechas
            fecha_operacion_obj = datetime.strptime(fecha_operacion, '%Y-%m-%d').date()
            fecha_inicio_obj = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
            fecha_fin_obj = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
            
            print(f"🏠 CREANDO CONTRATO:")
            print(f"   Propiedad: {propiedad.direccion}")
            print(f"   Inquilino: {inquilino.nombre} {inquilino.apellido}")
            print(f"   Vendedor: {vendedor.nombre} {vendedor.apellido}")
            print(f"   Duración: {duracion_meses} meses")
            print(f"   Precio mensual: ${precio_mensual}")
            print(f"   Depósito: ${deposito_garantia}")
            
            # Crear el contrato
            with transaction.atomic():
                contrato = ContratoAlquiler.objects.create(
                    propiedad=propiedad,
                    inquilino=inquilino,
                    vendedor=vendedor,
                    fecha_operacion=fecha_operacion_obj,
                    fecha_inicio=fecha_inicio_obj,
                    fecha_fin=fecha_fin_obj,
                    duracion_meses=duracion_meses,
                    precio_mensual=precio_mensual,
                    deposito_garantia=deposito_garantia,
                    estado='activo',
                    sucursal=request.user.sucursal  # La sucursal del contrato será la del usuario que lo crea
                )
                
                print(f"✅ CONTRATO CREADO: ID {contrato.id}")
                
                # Actualizar estado de la propiedad (opcional)
                if hasattr(propiedad, 'info_meses'):
                    propiedad.info_meses.estado = 'alquilada'
                    propiedad.info_meses.save()
                
                messages.success(request, f'✅ Contrato de {duracion_meses} meses creado exitosamente! Ahora puedes crear operaciones de caja para los pagos.')
                return redirect('inmobiliaria:lista_contratos')
                
        except Exception as e:
            print(f"❌ ERROR AL CREAR CONTRATO: {str(e)}")
            messages.error(request, f'Error al crear el contrato: {str(e)}')
            return redirect('inmobiliaria:alquileres_24_meses')
    
    return redirect('inmobiliaria:alquileres_24_meses')

@login_required
def lista_contratos(request):
    """Vista para listar todos los contratos de alquiler"""
    from .models import ContratoAlquiler
    
    contratos = ContratoAlquiler.objects.filter(
        sucursal=request.user.sucursal
    ).select_related('propiedad', 'inquilino', 'vendedor').order_by('-fecha_creacion')
    
    # Obtener la próxima cuota para cada contrato
    for contrato in contratos:
        contrato.proxima_cuota = contrato.cuotas.filter(
            estado__in=['pendiente', 'vencida']
        ).order_by('fecha_vencimiento').first()
        
        # Marcar cuotas vencidas
        if contrato.proxima_cuota and contrato.proxima_cuota.fecha_vencimiento < timezone.now().date():
            contrato.proxima_cuota.estado = 'vencida'
            contrato.proxima_cuota.save()
    
    context = {
        'contratos': contratos
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


@login_required
def procesar_operacion_contrato(request, contrato_id):
    """Procesar la operación de contrato (similar a procesar_movimiento_reserva)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    try:
        with transaction.atomic():
            contrato = get_object_or_404(ContratoAlquiler, id=contrato_id, sucursal=request.user.sucursal)
            
            # Obtener caja abierta
            caja_abierta = Caja.objects.filter(
                sucursal=request.user.sucursal, 
                estado='abierta'
            ).first()
            
            if not caja_abierta:
                return JsonResponse({'error': 'No hay caja abierta'}, status=400)
            
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
            
            total_movimiento = (monto_efectivo + monto_cheque + monto_tarjeta + 
                              monto_deposito_galicia + monto_deposito_mp)
            
            # El total debe ser igual al depósito de garantía más el primer mes solo en operación principal
            tipo_operacion = request.POST.get('tipo_operacion', '')
            if tipo_operacion == 'principal':
                total_esperado = contrato.deposito_garantia + contrato.precio_mensual
                mensaje_error = f'El monto total (${total_movimiento}) debe ser igual al depósito (${contrato.deposito_garantia}) más el primer mes (${contrato.precio_mensual})'
            else:
                total_esperado = contrato.precio_mensual
                mensaje_error = f'El monto total (${total_movimiento}) debe ser igual al valor de la cuota (${contrato.precio_mensual})'
            
            if total_movimiento != total_esperado:
                return JsonResponse({
                    'error': mensaje_error
                }, status=400)
            
            # Crear movimiento de caja
            movimiento = MovimientoCaja.objects.create(
                caja=caja_abierta,
                tipo='INGRESO',
                concepto=concepto,
                monto_efectivo=monto_efectivo,
                monto_cheque=monto_cheque,
                monto_tarjeta=monto_tarjeta,
                fecha=timezone.now(),
                empleado=request.user,
                sucursal=request.user.sucursal,
                propiedad=contrato.propiedad
            )
            
            # Si hay depósitos bancarios, guardarlos
            if monto_deposito_galicia > 0:
                movimiento.destino_deposito = 'galicia'
                movimiento.monto_deposito = monto_deposito_galicia
            elif monto_deposito_mp > 0:
                movimiento.destino_deposito = 'mp'
                movimiento.monto_deposito = monto_deposito_mp
            
            movimiento.save()
            
            # Si es operación principal, marcar el contrato
            if tipo_operacion == 'principal':
                contrato.operacion_principal = True
                contrato.save()
                
                # Crear las cuotas mensuales
                fecha_vencimiento = contrato.fecha_inicio
                for i in range(contrato.duracion_meses):
                    CuotaMensual.objects.create(
                        contrato=contrato,
                        numero_cuota=i + 1,
                        fecha_vencimiento=fecha_vencimiento,
                        monto_base=contrato.precio_mensual,
                        monto_total=contrato.precio_mensual,  # Solo el precio mensual, sin depósito
                        # La primera cuota ya está pagada con este movimiento
                        estado='pagada' if i == 0 else 'pendiente',
                        # Asociar el movimiento solo a la primera cuota
                        movimiento=movimiento if i == 0 else None,
                        fecha_pago=timezone.now().date() if i == 0 else None
                    )
                    # Calcular próximo vencimiento
                    fecha_vencimiento = fecha_vencimiento + relativedelta(months=1)
            
            return JsonResponse({
                'success': True,
                'redirect_url': reverse('inmobiliaria:ver_recibo_movimiento', args=[movimiento.id])
            })
            
    except Exception as e:
        print("Error al procesar operación:", str(e))
        return JsonResponse({'error': str(e)}, status=400)

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
    """Vista para procesar el pago de una cuota"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    try:
        with transaction.atomic():
            cuota = get_object_or_404(CuotaMensual, 
                                    id=cuota_id, 
                                    contrato__sucursal=request.user.sucursal,
                                    estado__in=['pendiente', 'vencida'])
            
            # Verificar que no haya cuotas anteriores pendientes
            if cuota.contrato.cuotas.filter(
                numero_cuota__lt=cuota.numero_cuota,
                estado__in=['pendiente', 'vencida']
            ).exists():
                return JsonResponse({'error': 'Hay cuotas anteriores pendientes'}, status=400)
            
            # Obtener caja abierta
            caja_abierta = Caja.objects.filter(
                sucursal=request.user.sucursal, 
                estado='abierta'
            ).first()
            
            if not caja_abierta:
                return JsonResponse({'error': 'No hay caja abierta'}, status=400)
            
            # Función auxiliar para limpiar valores monetarios
            def limpiar_valor_monetario(valor_str):
                if not valor_str or valor_str.strip() == '':
                    return Decimal('0')
                valor_limpio = valor_str.replace('.', '').replace(',', '.')
                try:
                    return Decimal(valor_limpio)
                except:
                    return Decimal('0')
            
            # Extraer montos del formulario
            monto_efectivo = limpiar_valor_monetario(request.POST.get('monto_efectivo', '0'))
            monto_cheque = limpiar_valor_monetario(request.POST.get('monto_cheque', '0'))
            monto_tarjeta = limpiar_valor_monetario(request.POST.get('monto_tarjeta', '0'))
            monto_deposito_galicia = limpiar_valor_monetario(request.POST.get('monto_deposito_galicia', '0'))
            monto_deposito_mp = limpiar_valor_monetario(request.POST.get('monto_deposito_mp', '0'))
            
            total_pagado = (monto_efectivo + monto_cheque + monto_tarjeta + 
                          monto_deposito_galicia + monto_deposito_mp)
            
            # Para cuotas mensuales, el total debe ser igual al monto de la cuota
            if total_pagado != cuota.monto_total:
                return JsonResponse({
                    'error': f'El monto pagado (${total_pagado}) no coincide con el total de la cuota (${cuota.monto_total})'
                }, status=400)
            
            # Crear movimiento de caja
            movimiento = MovimientoCaja.objects.create(
                caja=caja_abierta,
                tipo='INGRESO',
                concepto=f'Cuota {cuota.numero_cuota}/{cuota.contrato.duracion_meses} - {cuota.contrato.propiedad.direccion}',
                monto_efectivo=monto_efectivo,
                monto_cheque=monto_cheque,
                monto_tarjeta=monto_tarjeta,
                fecha=timezone.now(),
                empleado=request.user,
                sucursal=request.user.sucursal,
                propiedad=cuota.contrato.propiedad
            )
            
            # Si hay depósitos bancarios, guardarlos
            if monto_deposito_galicia > 0:
                movimiento.destino_deposito = 'galicia'
                movimiento.monto_deposito = monto_deposito_galicia
            elif monto_deposito_mp > 0:
                movimiento.destino_deposito = 'mp'
                movimiento.monto_deposito = monto_deposito_mp
            
            movimiento.save()
            
            # Actualizar cuota
            cuota.fecha_pago = timezone.now().date()
            cuota.estado = 'pagada_con_mora' if cuota.recargo_mora > 0 else 'pagada'
            cuota.movimiento = movimiento
            cuota.save()
            
            return JsonResponse({
                'success': True,
                'redirect_url': reverse('inmobiliaria:ver_recibo_movimiento', args=[movimiento.id])
            })
            
    except Exception as e:
        print("Error al procesar pago de cuota:", str(e))
        return JsonResponse({'error': str(e)}, status=400)