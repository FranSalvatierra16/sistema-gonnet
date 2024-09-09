from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Vendedor, Inquilino, Propietario, Propiedad, Reserva, Disponibilidad
from .forms import  VendedorUserCreationForm, VendedorChangeForm, InquilinoForm, PropietarioForm, PropiedadForm, ReservaForm,BuscarPropiedadesForm, DisponibilidadForm
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from datetime import datetime, date
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.forms import modelformset_factory
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from dateutil.parser import parse

# index view
def index(request):
    nivel = None
    if request.user.is_authenticated and hasattr(request.user, 'vendedor'):
        nivel = request.user.vendedor.nivel

    context = {
        'nivel_usuario': nivel,
    }
    return render(request, 'inmobiliaria/index.html', context)

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
    vendedores = Vendedor.objects.all()
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
    inquilinos = Inquilino.objects.all()
    return render(request, 'inmobiliaria/inquilinos/lista.html', {'inquilinos': inquilinos})

@login_required
def inquilino_detalle(request, inquilino_id):
    inquilino = get_object_or_404(Inquilino, pk=inquilino_id)
    return render(request, 'inmobiliaria/inquilinos/detalle.html', {'inquilino': inquilino})

@login_required
def inquilino_nuevo(request):
    if request.method == "POST":
        form = InquilinoForm(request.POST)
        if form.is_valid():
            inquilino = form.save()
            messages.success(request, 'Inquilino creado exitosamente.')
            return redirect('inmobiliaria:inquilino_detalle', inquilino_id=inquilino.id)
    else:
        form = InquilinoForm()
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
    propietarios = Propietario.objects.all()
    return render(request, 'inmobiliaria/propietarios/lista.html', {'propietarios': propietarios})

@login_required
def propietario_detalle(request, propietario_id):
    propietario = get_object_or_404(Propietario, pk=propietario_id)
    return render(request, 'inmobiliaria/propietarios/detalle.html', {'propietario': propietario})

@login_required
def propietario_nuevo(request):
    if request.method == "POST":
        form = PropietarioForm(request.POST)
        if form.is_valid():
            propietario = form.save()
            messages.success(request, 'Propietario creado exitosamente.')
            return redirect('inmobiliaria:propietario_detalle', propietario_id=propietario.id)
    else:
        form = PropietarioForm()
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
    propiedades = Propiedad.objects.all()
    return render(request, 'inmobiliaria/propiedades/lista.html', {'propiedades': propiedades})

@login_required
def propiedad_detalle(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, pk=propiedad_id)
    disponibilidades = propiedad.disponibilidades.all()  # Si tienes una relación entre propiedad y disponibilidad
    
    return render(request, 'inmobiliaria/propiedades/detalle.html', {
        'propiedad': propiedad,
        'disponibilidades': disponibilidades,
    })
@login_required
def propiedad_nuevo(request):
    if request.method == 'POST':
        form = PropiedadForm(request.POST, request.FILES)
        if form.is_valid():
            propiedad = form.save(commit=False)
            propiedad.save()

            # Comentamos la parte de la carga de imágenes
            # images = request.FILES.getlist('imagenes')
            # for image in images:
            #     PropiedadImagen.objects.create(propiedad=propiedad, imagen=image)

            messages.success(request, 'Propiedad creada exitosamente.')
            return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad.id)
    else:
        form = PropiedadForm()

    return render(request, 'inmobiliaria/propiedades/formulario.html', {'form': form})

@login_required
def propiedad_editar(request, propiedad_id):
    propiedad = Propiedad.objects.get(pk=propiedad_id)

    # Comentamos o eliminamos la lógica relacionada con las imágenes
    # ImageFormSet = modelformset_factory(PropiedadImagen, form=ImagenForm, extra=3)

    if request.method == 'POST':
        form = PropiedadForm(request.POST, request.FILES, instance=propiedad)
        # formset = ImageFormSet(request.POST, request.FILES, queryset=PropiedadImagen.objects.filter(propiedad=propiedad))
        
        if form.is_valid():  # Quitamos la validación de formset
            propiedad = form.save()
            # for form in formset:
            #     image = form.save(commit=False)
            #     image.propiedad = propiedad
            #     image.save()
            return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad.id)
    else:
        form = PropiedadForm(instance=propiedad)
        # formset = ImageFormSet(queryset=PropiedadImagen.objects.filter(propiedad=propiedad))

    return render(request, 'inmobiliaria/propiedades/formulario.html', {'form': form})
@login_required
def propiedad_eliminar(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, pk=propiedad_id)
    if request.method == "POST":
        propiedad.delete()
        messages.success(request, 'Propiedad eliminada exitosamente.')
        return redirect('inmobiliaria:propiedades')
    return render(request, 'inmobiliaria/propiedades/confirmar_eliminar.html', {'propiedad': propiedad})

    
def register(request):
    if request.method == 'POST':
        form = VendedorUserCreationForm(request.POST)
        if form.is_valid():
            vendedor = form.save()
            messages.success(request, 'Registro exitoso. Ahora puedes iniciar sesión.')
            return redirect('inmobiliaria:login')  # Redirige a la página de inicio de sesión
    else:
        form = VendedorUserCreationForm()
    return render(request, 'inmobiliaria/autenticacion/register.html', {'form': form})
@login_required
def crear_propietario_ajax(request):
    if request.method == 'POST' and request.is_ajax():
        form = PropietarioForm(request.POST)
        if form.is_valid():
            propietario = form.save()
            return JsonResponse({
                'success': True,
                'propietario_id': propietario.id,
                'propietario_nombre': f'{propietario.nombre} {propietario.apellido}',
            })
        else:
            return JsonResponse({
                'success': False,
                'errors': form.errors.as_json(),
            })
    return JsonResponse({'success': False, 'error': 'Invalid request'})

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
def reservas(request):
    reservas = Reserva.objects.all()
    return render(request, 'inmobiliaria/reserva/lista.html', {'reservas': reservas})

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

            # Validación de temporadas
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
        return redirect('inmobiliaria:reservas')
    return render(request, 'inmobiliaria/reserva/confirmar_eliminar.html', {'reserva': reserva})
def parse_fecha(fecha_str):
    formatos_fecha = ['%Y-%m-%d', '%d %b. %Y', '%d %B %Y', '%m/%d/%Y', '%m-%d-%Y']
    for formato in formatos_fecha:
        try:
            return datetime.strptime(fecha_str, formato).date()
        except ValueError:
            continue
    raise ValidationError('El formato de la fecha es inválido.')

def confirmar_reserva(request):
    if request.method == 'POST':
        try:
            # Obtener datos del formulario
            propiedad_id = request.POST['propiedad_id']
            fecha_inicio_str = request.POST['fecha_inicio']
            fecha_fin_str = request.POST['fecha_fin']

            # Validar que las fechas no estén vacías
            if not fecha_inicio_str or not fecha_fin_str:
                raise ValidationError('Las fechas proporcionadas no son válidas.')

            # Convertir las fechas a objetos `date`
            fecha_inicio = parse_fecha(fecha_inicio_str)
            fecha_fin = parse_fecha(fecha_fin_str)

            # Validar que la fecha de inicio no sea posterior a la de fin
            if fecha_inicio > fecha_fin:
                raise ValidationError('La fecha de inicio no puede ser posterior a la fecha de fin.')

            # Obtener la propiedad de la base de datos
            propiedad = get_object_or_404(Propiedad, id=propiedad_id)

            # Calcular el precio total
            total_dias = (fecha_fin - fecha_inicio).days
            total_precio = propiedad.precio_diario * total_dias

            # Crear la reserva con el precio total
            reserva = Reserva.objects.create(
                propiedad=propiedad,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                precio_total=total_precio
            )

            # Redirigir a la página de éxito con los detalles de la reserva
            return redirect('inmobiliaria:reserva_exitosa', reserva_id=reserva.id)

        except (ValueError, ValidationError, Propiedad.DoesNotExist) as e:
            # Si ocurre algún error, mostrar el mensaje de error
            return render(request, 'inmobiliaria/reserva/error.html', {'error': str(e)})

    # Si la solicitud no es POST, redirigir a la búsqueda de propiedades
    return redirect('inmobiliaria:buscar_propiedades')
def reserva_detalle(request, reserva_id):
    reserva = get_object_or_404(Reserva, pk=reserva_id)
    return render(request, 'inmobiliaria/reserva/detalle.html', {'reserva': reserva})
# inmobiliaria/views.py
def formato_fecha(fecha):
    return fecha.strftime('%m/%d/%Y') if fecha else ''
def buscar_propiedades(request):
    form = BuscarPropiedadesForm(request.POST or None)
    propiedades_disponibles = []
    fecha_inicio = None
    fecha_fin = None
    
    if form.is_valid():
        fecha_inicio = form.cleaned_data['fecha_inicio']
        fecha_fin = form.cleaned_data['fecha_fin']
        
        # Filtrar propiedades que están disponibles en las fechas indicadas
        propiedades = Propiedad.objects.all()

        # Filtrar propiedades que tienen disponibilidad activa en ese rango
        for propiedad in propiedades:
            disponibilidades = Disponibilidad.objects.filter(
                propiedad=propiedad,
                fecha_inicio__lte=fecha_fin,
                fecha_fin__gte=fecha_inicio
            )

            reservas = propiedad.reservas.filter(
                Q(fecha_inicio__lte=fecha_fin) & Q(fecha_fin__gte=fecha_inicio)
            )

            if disponibilidades.exists() and not reservas.exists():
                propiedades_disponibles.append(propiedad)
        
    return render(request, 'inmobiliaria/reserva/buscar_propiedades.html', {
        'form': form,
        'propiedades_disponibles': propiedades_disponibles,
        'fecha_inicio': formato_fecha(fecha_inicio),
        'fecha_fin': formato_fecha(fecha_fin),
    })

def crear_disponibilidad(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, id=propiedad_id)
    
    if request.method == 'POST':
        form = DisponibilidadForm(request.POST, propiedad=propiedad)
        if form.is_valid():
            try:
                disponibilidad = form.save(commit=False)
                disponibilidad.propiedad = propiedad
                disponibilidad.full_clean()
                disponibilidad.save()
                messages.success(request, 'Disponibilidad creada exitosamente.')
                return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad.id)
            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        form.add_error(field, error)
    else:
        form = DisponibilidadForm(propiedad=propiedad)

    return render(request, 'inmobiliaria/propiedades/crear_disponibilidad.html', {
        'form': form,
        'propiedad': propiedad
    })
def reserva_exitosa(request, reserva_id):
    
    reserva = Reserva.objects.get(id=reserva_id)
    
    context = {
        'reserva': reserva
    }
    return render(request, 'inmobiliaria/reserva/reserva_exitosa.html', context)
