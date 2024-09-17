from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Vendedor, Inquilino, Propietario, Propiedad, Reserva, Disponibilidad, ImagenPropiedad,Precio
from .forms import  VendedorUserCreationForm, VendedorChangeForm, InquilinoForm, PropietarioForm, PropiedadForm, ReservaForm,BuscarPropiedadesForm, DisponibilidadForm,PrecioForm, PrecioFormSet
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from datetime import datetime, date
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.forms import modelformset_factory
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from dateutil.parser import parse
from django.contrib.auth.models import User
from decimal import Decimal
from django.forms import inlineformset_factory


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
    precios = propiedad.precios.all() 
    print(propiedad.precios.all())  # Para depurar

    return render(request, 'inmobiliaria/propiedades/detalle.html', {
        'propiedad': propiedad,
        'disponibilidades': disponibilidades,
        'precios': precios
    })
@login_required
def propiedad_nuevo(request):
    if request.method == 'POST':
        form = PropiedadForm(request.POST, request.FILES)
        if form.is_valid():
            propiedad = form.save()
            
            # Manejo de múltiples imágenes
            imagenes = request.FILES.getlist('imagenes')
            for imagen in imagenes:
                ImagenPropiedad.objects.create(propiedad=propiedad, imagen=imagen)
            
            messages.success(request, 'Propiedad creada exitosamente.')
            return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad.id)
    else:
        form = PropiedadForm()
    return render(request, 'inmobiliaria/propiedades/formulario.html', {'form': form})
@login_required
def propiedad_editar(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, pk=propiedad_id)

    if request.method == 'POST':
        form = PropiedadForm(request.POST, request.FILES, instance=propiedad)
        
        if form.is_valid():
            propiedad = form.save()
            
            # Manejar las imágenes subidas
            if 'imagenes' in request.FILES:
                imagenes = request.FILES.getlist('imagenes')
                for imagen in imagenes:
                    ImagenPropiedad.objects.create(propiedad=propiedad, imagen=imagen)
                    
            return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad.id)
    else:
        form = PropiedadForm(instance=propiedad)

    return render(request, 'inmobiliaria/propiedades/formulario.html', {
        'form': form,
        'propiedad': propiedad
    })
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
def operaciones(request):
    reservas = Reserva.objects.all()
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
        return redirect('inmobiliaria:reservas')  # Redirige a la lista de reservas después de eliminar
    
    return render(request, 'inmobiliaria/reserva/confirmar_eliminar.html', {'reserva': reserva})
def parse_fecha(fecha_str):
    formatos_fecha = ['%Y-%m-%d', '%d %b. %Y', '%d %B %Y', '%m/%d/%Y', '%m-%d-%Y']
    for formato in formatos_fecha:
        try:
            return datetime.strptime(fecha_str, formato).date()
        except ValueError:
            continue
    raise ValidationError('El formato de la fecha es inválido.')
def parse_time(hora_str):
    try:
        return datetime.strptime(hora_str, '%H:%M').time()
    except ValueError:
        raise ValidationError('El formato de la hora es inválido.')
def confirmar_reserva(request):
    if request.method == 'POST':
        try:
            # Obtener datos del formulario
            propiedad_id = request.POST.get('propiedad_id')
            fecha_inicio_str = request.POST.get('fecha_inicio')
            fecha_fin_str = request.POST.get('fecha_fin')
            hora_ingreso_str = request.POST.get('hora_ingreso', '')
            hora_egreso_str = request.POST.get('hora_egreso', '')
            vendedor_id = request.POST.get('vendedor', '')
            cliente_id = request.POST.get('cliente', '')
            print(vendedor_id)
            # Validar que las fechas no estén vacías
            if not fecha_inicio_str or not fecha_fin_str:
                raise ValidationError('Las fechas proporcionadas no son válidas.')

            # Convertir las fechas a objetos `date`
            fecha_inicio = parse_fecha(fecha_inicio_str)
            fecha_fin = parse_fecha(fecha_fin_str)

            # Validar que la fecha de inicio no sea posterior a la de fin
            if fecha_inicio > fecha_fin:
                raise ValidationError('La fecha de inicio no puede ser posterior a la fecha de fin.')

            # Convertir las horas a objetos `time` (opcional, dependiendo de cómo almacenes las horas)
            hora_ingreso = parse_time(hora_ingreso_str) if hora_ingreso_str else None
            hora_egreso = parse_time(hora_egreso_str) if hora_egreso_str else None

            # Validar que los IDs no estén vacíos
            if not vendedor_id or not cliente_id:
                raise ValidationError('Vendedor o cliente no pueden estar vacíos.')

            # Obtener la propiedad, vendedor y cliente de la base de datos
            propiedad = get_object_or_404(Propiedad, id=propiedad_id)
            vendedor = get_object_or_404(Vendedor, id=vendedor_id)
            cliente = get_object_or_404(Inquilino, id=cliente_id)

            # Calcular el precio total
            total_dias = (fecha_fin - fecha_inicio).days
            total_precio = propiedad.precio_diario * total_dias

            # Crear la reserva con el precio total y otros detalles
            reserva = Reserva.objects.create(
                propiedad=propiedad,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                hora_ingreso=hora_ingreso,
                hora_egreso=hora_egreso,
                vendedor=vendedor,
                cliente=cliente,
                precio_total=total_precio
            )

            # Redirigir a la página de éxito con los detalles de la reserva
            return redirect('inmobiliaria:reserva_exitosa', reserva_id=reserva.id)

        except (ValueError, ValidationError, Propiedad.DoesNotExist, Vendedor.DoesNotExist, Inquilino.DoesNotExist) as e:
            # Si ocurre algún error, mostrar el mensaje de error
            # Asegúrate de tener una plantilla para manejar errores
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
    inquilinos = Inquilino.objects.all()
    form = BuscarPropiedadesForm(request.POST or None)
    propiedades_disponibles = []
    vendedores = Vendedor.objects.all()

    fecha_inicio = None
    fecha_fin = None

    if form.is_valid():
        fecha_inicio = form.cleaned_data['fecha_inicio']
        fecha_fin = form.cleaned_data['fecha_fin']

        # Filtrar propiedades que están disponibles en las fechas indicadas
        propiedades = Propiedad.objects.all()

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
        'inquilinos': inquilinos,  # Asegúrate de que esto esté aquí
        'vendedores': vendedores,  # Pasar el vendedor actual al template
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
    
    context = {
        'reserva': reserva
    }
    return render(request, 'inmobiliaria/reserva/reserva_exitosa.html', context)
def terminar_reserva(request, reserva_id):
    reserva = get_object_or_404(Reserva, pk=reserva_id)
    if request.method == "POST":
        pago_senia = Decimal(request.POST.get('pago_senia'))
        reserva.confirmar_reserva(pago_senia)
        messages.success(request, 'Reserva confirmada exitosamente.')
        return redirect('inmobiliaria:reservas')
    return render(request, 'inmobiliaria/reserva/finalizar_reserva.html', {'reserva': reserva})
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
    PrecioFormSet = modelformset_factory(Precio, form=PrecioForm, extra=0)
    precios = Precio.objects.filter(propiedad=propiedad)
    formset = PrecioFormSet(queryset=precios)
    # Si la propiedad no tiene precios, creamos uno por cada tipo de precio
    if not precios.exists():
        tipos_de_precios = ['quincena', 'fin_de_semana_largo', 'dia']
        for tipo in tipos_de_precios:
            Precio.objects.create(propiedad=propiedad, tipo_precio=tipo, precio_por_dia=0, precio_total=0, ajuste_porcentaje=0)

    if request.method == 'POST':
        formset = PrecioFormSet(request.POST)
        if formset.is_valid():
            formset.save()
            return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad_id)
 

    return render(request, 'inmobiliaria/propiedades/gestionar_precios.html', {
        'propiedad': propiedad,
        'formset': formset,
    })


