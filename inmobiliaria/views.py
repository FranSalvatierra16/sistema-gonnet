from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Vendedor, Inquilino, Propietario, Propiedad, Reserva, Disponibilidad, ImagenPropiedad,Precio, TipoPrecio, Pago, ConceptoPago
from .forms import  VendedorUserCreationForm, VendedorChangeForm, InquilinoForm, PropietarioForm, PropiedadForm, ReservaForm,BuscarPropiedadesForm, DisponibilidadForm,PrecioForm, PrecioFormSet, PropietarioBuscarForm, InquilinoBuscarForm, SucursalForm, LoginForm, PropiedadSearchForm
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm, SetPasswordForm
from django.contrib.auth import login
from datetime import datetime, date, timedelta
from django.db.models import Q, Prefetch, Case, When, IntegerField
from django.core.exceptions import ValidationError
from django.forms import modelformset_factory
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from dateutil.parser import parse
from django.contrib.auth.models import User
from decimal import Decimal
from django.forms import inlineformset_factory
from xhtml2pdf import pisa
from io import BytesIO
from django.template.loader import render_to_string
from django.contrib.auth import authenticate
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

# index view
def index(request):
    if request.user.is_authenticated:
        return redirect('inmobiliaria:buscar_propiedades')
    else:
        return redirect('inmobiliaria:login')

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
    propiedades = Propiedad.objects.filter(sucursal=request.user.sucursal)

    if form.is_valid():
        query = form.cleaned_data.get('query')
        if query:
            propiedades = propiedades.filter(
                Q(direccion__icontains=query) |
                Q(id__icontains=query) |
                Q(propietario__nombre__icontains=query) |
                Q(propietario__apellido__icontains=query)
            )

    return render(request, 'inmobiliaria/propiedades/lista.html', {
        'form': form,
        'propiedades': propiedades
    })

@login_required
def propiedad_detalle(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, pk=propiedad_id)
    disponibilidades = propiedad.disponibilidades.all()
    imagenes = propiedad.imagenes.all()

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
        When(tipo_precio=TipoPrecio.ESTUDIANTES, then=11),
        # Añade más condiciones si es necesario
        output_field=IntegerField(),
    )

    # Obtener los precios ordenados
    precios = propiedad.precios.annotate(
        orden_tipo_precio=orden_tipo_precio
    ).order_by('orden_tipo_precio')

    print("Imágenes de la propiedad:", [imagen.imagen.url for imagen in imagenes])

    return render(request, 'inmobiliaria/propiedades/detalle.html', {
        'propiedad': propiedad,
        'disponibilidades': disponibilidades,
        'precios': precios,
        'imagenes': imagenes
    })
@login_required
def propiedad_nuevo(request):
    if request.method == 'POST':
        form = PropiedadForm(request.POST, request.FILES, user=request.user)
        propietario_form = PropietarioForm(user=request.user)
        if form.is_valid():
            propiedad = form.save()
            
            # Procesar imágenes
            imagenes = request.FILES.getlist('imagenes')
            for index, imagen in enumerate(imagenes):
                ImagenPropiedad.objects.create(
                    propiedad=propiedad,
                    imagen=imagen,
                    orden=index + 1
                )
            
            messages.success(request, 'Propiedad creada exitosamente.')
            return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad.id)
    else:
        form = PropiedadForm()
        propietario_form = PropietarioForm(user=request.user)
    
    return render(request, 'inmobiliaria/propiedades/formulario.html', {
        'form': form,
        'propietario_form': propietario_form,
        'titulo': 'Nueva Propiedad'
    })

@login_required
def propiedad_editar(request, propiedad_id):
    try:
        propiedad = get_object_or_404(Propiedad, pk=propiedad_id)
        imagenes = ImagenPropiedad.objects.filter(propiedad=propiedad).order_by('orden')
        
        if request.method == 'POST':
            form = PropiedadForm(request.POST, request.FILES, instance=propiedad)
            if form.is_valid():
                propiedad = form.save()
                
                nuevas_imagenes = request.FILES.getlist('imagenes')
                if nuevas_imagenes:
                    ultimo_orden = ImagenPropiedad.objects.filter(propiedad=propiedad).aggregate(
                        max_orden=models.Max('orden')
                    )['max_orden'] or 0
                    
                    for i, imagen in enumerate(nuevas_imagenes, 1):
                        # Verificar duplicados por nombre de archivo
                        if not ImagenPropiedad.objects.filter(
                            propiedad=propiedad,
                            imagen__icontains=imagen.name
                        ).exists():
                            ImagenPropiedad.objects.create(
                                propiedad=propiedad,
                                imagen=imagen,
                                orden=ultimo_orden + i
                            )
                
                messages.success(request, 'Propiedad actualizada exitosamente.')
                return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad.id)
        else:
            form = PropiedadForm(instance=propiedad)
        
        return render(request, 'inmobiliaria/propiedades/formulario.html', {
            'form': form,
            'propiedad': propiedad,
            'imagenes': imagenes,
        })
    except Exception as e:
        logger.error(f"Error en propiedad_editar: {str(e)}")
        messages.error(request, f'Error al procesar la solicitud: {str(e)}')
        return redirect('inmobiliaria:propiedades')

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
            print('Propietario creado exitosamente.')
            print('Propietario', propietario)
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
    reservas = Reserva.objects.filter(sucursal=request.user.sucursal)
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
            # Obtener datos del formulario
            propiedad_id = request.POST.get('propiedad_id')
            fecha_inicio_str = request.POST.get('fecha_inicio')
            fecha_fin_str = request.POST.get('fecha_fin')
            vendedor_id = request.POST.get('vendedor_id')
            inquilino_id = request.POST.get('inquilino_id')
            precio = request.POST.get('precio_total', '0')

            # Validación de datos obligatorios
            campos_requeridos = {
                'propiedad_id': propiedad_id,
                'fecha_inicio': fecha_inicio_str,
                'fecha_fin': fecha_fin_str,
                'vendedor_id': vendedor_id,
                'inquilino_id': inquilino_id,
                'precio': precio
            }
            print("los campos requeridos son ",campos_requeridos)

            campos_faltantes = [k for k, v in campos_requeridos.items() if not v]
            if campos_faltantes:
                messages.error(request, f'Faltan los siguientes campos: {", ".join(campos_faltantes)}')
                return redirect('inmobiliaria:buscar_propiedades')

            # Convertir 
            print("la fecha de inicio es ",fecha_inicio_str)
            fecha_inicio = parse_fecha(fecha_inicio_str)
            fecha_fin = parse_fecha(fecha_fin_str)
            print("la fecha de fin es ",fecha_fin)

            # Validar fechas    
            if fecha_inicio > fecha_fin:
                messages.error(request, 'La fecha de inicio no puede ser posterior a la fecha de fin.')
                return redirect('inmobiliaria:buscar_propiedades')

            # Obtener objetos de la base de datos
            try:
                propiedad = Propiedad.objects.get(id=propiedad_id)
                vendedor = Vendedor.objects.get(id=vendedor_id)
                inquilino = Inquilino.objects.get(id=inquilino_id)
            except ObjectDoesNotExist as e:
                messages.error(request, f'Error al obtener datos: {str(e)}')
                return redirect('inmobiliaria:buscar_propiedades')

            # Procesar el precio
            try:
                precio_total = Decimal(precio.replace(',', '.'))
            except (ValueError, TypeError):
                messages.error(request, 'El precio proporcionado no es válido')
                return redirect('inmobiliaria:buscar_propiedades') 

            print("el precio total es ",precio_total)

            # Crear la reserva
            with transaction.atomic():
                reserva = Reserva.objects.create(
                    propiedad=propiedad,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    vendedor=vendedor,
                    cliente=inquilino,
                    precio_total=precio_total
                )
                print("la reserva es ",reserva)


            messages.success(request, 'Reserva creada exitosamente')
            return redirect('inmobiliaria:reserva_exitosa', reserva_id=reserva.id)

        except Exception as e:
            messages.error(request, f'Error inesperado: {str(e)}')
            return redirect('inmobiliaria:buscar_propiedades')
    else:
        messages.error(request, 'Método no permitido')
        return redirect('inmobiliaria:buscar_propiedades')


def reserva_detalle(request, reserva_id):
    reserva = get_object_or_404(Reserva, pk=reserva_id)
    return render(request, 'inmobiliaria/reserva/detalle.html', {'reserva': reserva})
# inmobiliaria/views.py
def formato_fecha(fecha):
    return fecha.strftime('%d/%m/%Y') if fecha else ''


@login_required
def buscar_propiedades(request):
    # Obtener la sucursal del vendedor logueado
    sucursal_vendedor = request.user.sucursal
    print("la sucursal del vendedor es ",sucursal_vendedor)
    
    inquilinos = Inquilino.objects.filter(sucursal=sucursal_vendedor)
    form = BuscarPropiedadesForm(request.POST or None)
    inquilino_form = InquilinoForm(request.POST)
    propiedades_disponibles = []
    propiedades_sin_precio = []
    vendedores = Vendedor.objects.filter(sucursal=sucursal_vendedor)
    total_dias_reserva = 0

    fecha_inicio = None
    fecha_fin = None

    if form.is_valid():
        fecha_inicio = form.cleaned_data['fecha_inicio']
        fecha_fin = form.cleaned_data['fecha_fin']

        # Filtrar propiedades por sucursal
        propiedades = Propiedad.objects.filter(sucursal=sucursal_vendedor)

        # Prefetch los precios para cada propiedad
        propiedades = propiedades.prefetch_related(
            Prefetch('precios', queryset=Precio.objects.all(), to_attr='todos_precios')
        )

        # Aplicar filtros del formulario
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
            # Verificar si existen reservas pagada
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
                        precio_dia = precio.precio_por_dia
                    except Precio.DoesNotExist:
                        precio_dia = 0

                    if precio_dia == 0:
                        propiedades_sin_precio.append(propiedad)
                        # No romper el bucle, solo marcar la propiedad como sin precio
                        continue

                    if precio_dia > precio_mas_caro:
                        precio_mas_caro = precio_dia

                    if not primer_dia:
                        precio_total += precio_dia
                    else:
                        primer_dia = False

                if precio_dia > 0 or precio_dia == 0 :

                    if reserva_confirmada_no_pagada:
                        propiedad.precio_total_reserva = reserva_confirmada_no_pagada.precio_total
                    else:
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
                    propiedad.todos_precios = sorted(propiedad.todos_precios, key=lambda x: TipoPrecio[x.tipo_precio].value)

    # Alerta si hay propiedades sin precio
    alerta_sin_precio = len(propiedades_sin_precio) > 0
    print("las fechas de inicio y fin son ",fecha_inicio,fecha_fin)
    print("los dias de reserva son ",total_dias_reserva)

    return render(request, 'inmobiliaria/reserva/buscar_propiedades.html', {
        'form': form,
        'propiedades_disponibles': propiedades_disponibles,
        'alerta_sin_precio': alerta_sin_precio,
        'fecha_inicio': formato_fecha(fecha_inicio) if fecha_inicio else None,
        'fecha_fin': formato_fecha(fecha_fin) if fecha_fin else None,
        'inquilinos': Inquilino.objects.all().order_by('apellido', 'nombre'),
        'vendedores': vendedores,
        'tipos_precio': TipoPrecio,
        'inquilino_form': inquilino_form,
        'total_dias': total_dias_reserva,
    })

def crear_disponibilidad(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    
    if request.method == 'POST':
        form = DisponibilidadForm(request.POST, propiedad=propiedad)
        if form.is_valid():
            try:
                disponibilidad = form.save(commit=False)
                disponibilidad.propiedad = propiedad
                disponibilidad.save()
                messages.success(request, 'Disponibilidad creada exitosamente.')
                return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad.id)
            except ValidationError as e:
                form.add_error(None, e)  # Agrega errores globales
    else:
        form = DisponibilidadForm(propiedad=propiedad)

    return render(request, 'inmobiliaria/propiedades/crear_disponibilidad.html', {
        'form': form,
        'propiedad': propiedad
    })


def reserva_exitosa(request, reserva_id):
    
    reserva = Reserva.objects.get(id=reserva_id)
    print("la reserva es ",reserva.precio_total)
    
    context = {
        'reserva': reserva
    }
    return render(request, 'inmobiliaria/reserva/reserva_exitosa.html', context)

def terminar_reserva(request, reserva_id):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    conceptos_pago = ConceptoPago.objects.all()
    pagos_previos = Pago.objects.filter(reserva=reserva).order_by('-fecha')
    
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
                
                # Crear el pago
                pago = Pago.objects.create(
                    reserva=reserva,
                    monto=monto,
                    forma_pago=forma_pago,
                    concepto=concepto
                )
                
                # Calcular total pagado y actualizar saldo pendiente
                total_pagado = Pago.objects.filter(reserva=reserva).aggregate(
                    total=models.Sum('monto'))['total'] or Decimal('0')
                
                # Actualizar la reserva
                reserva.senia = total_pagado
                reserva.deposito = deposito  # Aseguramos que se guarde el depósito
                reserva.cuota_pendiente = reserva.precio_total - total_pagado
                
                print(f"Debug - Precio Total: {reserva.precio_total}")
                print(f"Debug - Total Pagado: {total_pagado}")
                print(f"Debug - Cuota Pendiente: {reserva.cuota_pendiente}")
                print(f"Debug - Depósito de Garantía: {reserva.deposito_garantia}")  # Agregado
                
                # Actualizar estado según el saldo pendiente
                if reserva.cuota_pendiente <= 0:
                    reserva.estado = 'pagada'
                    messages.success(request, 'Reserva pagada completamente')
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
                        'deposit_garantia': float(reserva.deposito_garantia),  # Incluimos el depósito en la respuesta
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
        'total_pagado': sum(pago.monto for pago in pagos_previos),
        'saldo_pendiente': reserva.cuota_pendiente,
        'deposito': reserva.deposito_garantia or 0  # Aseguramos que siempre haya un valor
    }
    
    return render(request, 'inmobiliaria/reserva/finalizar_reserva.html', context)
@login_required
def ver_recibo(request, reserva_id):
    try:
        reserva = get_object_or_404(Reserva, id=reserva_id)
        fecha_actual = datetime.now()
        
        propiedad = reserva.propiedad
        
        # Obtener todos los pagos de la reserva ordenados por fecha
        pagos = reserva.pagos.all().order_by('fecha')
        formas_de_pago = ', '.join(set(pago.get_forma_pago_display() for pago in pagos))
        
        # Convertir el precio total a palabras
        monto_en_palabras = numero_a_palabras(int(sum(pago.monto for pago in pagos)))
        
        # Crear lista de características con SI/NO
        caracteristicas = []
        caracteristicas_base = [
            ('WiFi', propiedad.wifi),
            ('Cochera', propiedad.cochera),
            ('TV Smart', propiedad.tv_smart),
            ('Piscina', propiedad.piscina),
            ('Parrilla', propiedad.parrilla),

        ]
        
        # Convertir cada característica a su formato "Nombre: SI/NO"
        caracteristicas = [f"{nombre}: {'SI' if valor else 'NO'}" for nombre, valor in caracteristicas_base]
        
        # Crear descripción
        vista = getattr(propiedad, 'vista', 'No especificada')
        ambientes = getattr(propiedad, 'ambientes', 'No especificados')
        
        descripcion = f"Vista {vista}, {ambientes} ambientes"
        if caracteristicas:
            descripcion += f" con {', '.join(caracteristicas)}"
        
        # Print de debug
        print("Características encontradas:", caracteristicas)
        print("Descripción generada:", descripcion)
        
        context = {
            # Datos básicos del recibo
            'numero_recibo': f'0007-{reserva.id:06d}',
            'fecha': fecha_actual.strftime('%d/%m/%Y'),
            'hora': fecha_actual.strftime('%H:%M'),
            
            # Datos de la reserva
            'reserva': reserva,
            'operacion': f'{reserva.id:04d}',
            'precio_total': reserva.precio_total,
            'senia': reserva.senia,
            'saldo': reserva.cuota_pendiente,
            'deposito': getattr(reserva, 'deposito', 0),
            'fecha_inicio': reserva.fecha_inicio.strftime('%d/%m/%Y'),
            'fecha_fin': reserva.fecha_fin.strftime('%d/%m/%Y'),
            'monto_en_palabras': monto_en_palabras,
            
            # Datos del cliente
            'cliente': {
                'nombre_completo': f"{reserva.cliente.nombre} {reserva.cliente.apellido}",
                'dni': reserva.cliente.dni,
                'telefono': reserva.cliente.celular,
                'domicilio': reserva.cliente.domicilio,
                'localidad': reserva.cliente.localidad,
                'provincia': reserva.cliente.provincia,
                'cuit': reserva.cliente.cuit if reserva.cliente.cuit not in [None, ''] else '',
                'iva': reserva.cliente.tipo_ins
            },
            
            # Datos de la propiedad
            'propiedad': {
                'id': propiedad.id,
                'direccion': propiedad.direccion,
                'numero': getattr(propiedad, 'numero', ''),
                'piso': getattr(propiedad, 'piso', ''),
                'departamento': getattr(propiedad, 'departamento', ''),
                'localidad': getattr(propiedad, 'localidad', ''),
                'provincia': getattr(propiedad, 'provincia', ''),
                'codigo_postal': getattr(propiedad, 'codigo_postal', ''),
                'tipo_propiedad': getattr(propiedad, 'tipo_propiedad', ''),
                'superficie': getattr(propiedad, 'superficie', ''),
                'ambientes': ambientes,
                'dormitorios': getattr(propiedad, 'dormitorios', ''),
                'baños': getattr(propiedad, 'baños', ''),
                'garage': getattr(propiedad, 'garage', ''),
                'descripcion': descripcion,
                'precio': getattr(propiedad, 'precio', ''),
                'moneda': getattr(propiedad, 'moneda', ''),
                'estado': getattr(propiedad, 'estado', ''),
                'disponibilidad': getattr(propiedad, 'disponibilidad', ''),
                'fecha_publicacion': getattr(propiedad, 'fecha_publicacion', ''),
                'propietario': propiedad.propietario.nombre if getattr(propiedad, 'propietario', None) else '',
                'ficha': getattr(propiedad, 'ficha', ''),
                'llave': getattr(propiedad, 'llave', ''),
                'comodidades': ', '.join(caracteristicas),
                'vista': vista,
                'wifi': 'SI' if propiedad.wifi else 'NO',
                'cochera': 'SI' if propiedad.cochera else 'NO',
                'tv_smart': 'SI' if propiedad.tv_smart else 'NO',
                'piscina': 'SI' if propiedad.piscina else 'NO',
                'parrilla': 'SI' if propiedad.parrilla else 'NO',
          
            },
            
            # Datos del vendedor
            'vendedor': {
                'nombre_completo': f"{reserva.vendedor.nombre} {reserva.vendedor.apellido}" if reserva.vendedor else '',
                'dni': getattr(reserva.vendedor, 'dni', '') if reserva.vendedor else '',
                'telefono': getattr(reserva.vendedor, 'celular', '') if reserva.vendedor else ''
            },
            
            # Agregar los pagos al contexto
            'pagos': [{
                'fecha': pago.fecha.strftime('%d/%m/%Y'),
                'codigo': pago.codigo,
                'concepto': pago.concepto.nombre,
                'forma_pago': pago.get_forma_pago_display(),
                'monto': pago.monto
            } for pago in pagos],
            
            # Total de pagos
            'total_pagado': sum(pago.monto for pago in pagos),
            'formas_de_pago': formas_de_pago,
        }
        
        return render(request, 'inmobiliaria/reserva/recibo.html', context)
        
    except Exception as e:
        print(f"Error en ver_recibo: {str(e)}")
        messages.error(request, f'Error al generar el recibo: {str(e)}')
        return redirect('inmobiliaria:buscar_propiedades')

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
    
    # Si la propiedad no tiene precios, creamos uno por cada tipo de precio
    if not precios.exists():
        tipos_de_precios = ['quincena', 'fin_de_semana_largo', 'dia']
        for tipo in tipos_de_precios:
            Precio.objects.create(
                propiedad=propiedad,
                tipo_precio=tipo,
                precio_por_dia=0,
                precio_total=0,
                precio_toma=0 if vendedor.nivel > 2 else None,
                precio_dia_toma=0 if vendedor.nivel > 2 else None,
                ajuste_porcentaje=0
            )
        precios = Precio.objects.filter(propiedad=propiedad)

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
        'nivel_vendedor': vendedor.nivel  # Pasamos el nivel a la plantilla
    })
def buscar_propiedades_23(request):
    # Aquí filtramos directamente las propiedades habilitadas para alquiler
    propiedades_disponibles = Propiedad.objects.filter(habilitar_precio_alquiler=True)

    # Contexto para la plantilla
    context = {
        'propiedades_disponibles': propiedades_disponibles,
    }
    
    return render(request, 'inmobiliaria/reservas/buscar_propiedades.html', context)
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
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        query = request.GET.get('term', '')
        propietarios = Propietario.objects.filter(
            Q(nombre__icontains=query) | 
            Q(apellido__icontains=query) |
            Q(dni__icontains=query)
        )[:10]
        results = [{'id': p.id, 'text': f"{p.nombre} {p.apellido} (DNI: {p.dni})"} for p in propietarios]
        return JsonResponse({'results': results})
    return JsonResponse({'results': []})
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
    propietario = get_object_or_404(Propietario, id=propietario_id)
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

def crear_inquilino_ajax(request):
    if request.method == 'POST':
        try:
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
                garantia=request.POST.get('garantia', '')
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
    
    try:
        propiedad_id = request.GET.get('propiedad_id')
        print(f"Obteniendo precios para propiedad con ID: {propiedad_id}")
        if not propiedad_id:
            return JsonResponse({'error': 'No se proporcionó ID de propiedad'}, status=400)
            
        propiedad = get_object_or_404(Propiedad, id=propiedad_id)
        precios = Precio.objects.filter(propiedad=propiedad)
        
        precios_data = [{
            'tipo_precio': precio.get_tipo_precio_display(),
            'precio_por_dia': format_price(precio.precio_por_dia),
            'precio_total': format_price(precio.precio_total)
        } for precio in precios]
        
        return JsonResponse({'precios': precios_data})
        
    except Exception as e:
        print(f"Error en obtener_precios_propiedad: {str(e)}")  # Para debugging
        return JsonResponse({'error': str(e)}, status=500)

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
    if request.method == 'POST':
        propiedad_ids = request.POST.getlist('propiedades[]')
        fecha_inicio = request.POST.get('fecha_inicio')
        fecha_fin = request.POST.get('fecha_fin')
        
        propiedades_actualizadas = 0
        errores = []
        
        try:
            for propiedad_id in propiedad_ids:
                try:
                    propiedad = Propiedad.objects.get(id=propiedad_id)
                    Disponibilidad.objects.create(
                        propiedad=propiedad,
                        fecha_inicio=fecha_inicio,
                        fecha_fin=fecha_fin
                    )
                    propiedades_actualizadas += 1
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
            
    propiedades = Propiedad.objects.all().order_by('direccion')
    return render(request, 'inmobiliaria/propiedades/disponibilidad_masiva.html', {
        'propiedades': propiedades
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
        
        if User.objects.filter(email=email).exists():
            user = User.objects.get(email=email)
            
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
    if request.method == 'POST':
        reserva = get_object_or_404(Reserva, id=reserva_id)
        try:
            # Convertir el monto a Decimal
            monto = Decimal(request.POST['monto'])
            
            # Crear el pago
            pago = Pago.objects.create(
                reserva=reserva,
                concepto_id=request.POST['concepto'],
                forma_pago=request.POST['forma_pago'],
                monto=monto
            )
            
            # Forzar la actualización de saldos
            reserva.actualizar_saldos()
            
            messages.success(request, 'Pago registrado exitosamente.')
        except ValueError as e:
            messages.error(request, f'Error al procesar el pago: {str(e)}')
        except Exception as e:
            messages.error(request, f'Error inesperado: {str(e)}')
        
    return redirect('inmobiliaria:confirmar_pago', reserva_id=reserva_id)

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
            
            # Actualizar el depósito de garantía en la reserva
            reserva.deposito_garantia = monto_deposito
            reserva.save()
            
            messages.success(request, 'Depósito de garantía agregado correctamente')
            
            # Print de debug
            print(f"Depósito guardado: {reserva.deposito_garantia}")
            
        return redirect('inmobiliaria:finalizar_reserva', reserva_id=reserva.id)
        
    except Exception as e:
        messages.error(request, f'Error al agregar el depósito: {str(e)}')
        return redirect('inmobiliaria:finalizar_reserva', reserva_id=reserva_id)

from django.contrib.auth import logout
from django.shortcuts import redirect

def logout_view(request):
    logout(request)
    return redirect('inmobiliaria:login')

def ver_historial_disponibilidad(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    historial = propiedad.historial_disponibilidad.all()
    
    context = {
        'propiedad': propiedad,
        'historial': historial
    }
    return render(request, 'inmobiliaria/propiedades/historial_disponibilidad.html', context)

