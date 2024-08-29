from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Vendedor, Inquilino, Propietario, Propiedad,PropiedadImagen
from .forms import  VendedorUserCreationForm, VendedorChangeForm, InquilinoForm, PropietarioForm, PropiedadForm, PropiedadImagenForm
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login

from django.forms import modelformset_factory

# index view
def index(request):
    return render(request, 'inmobiliaria/index.html')

# Vendedor views
@login_required
def dashboard(request):
    return render(request, 'inmobiliaria/dashboard.html')
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
        form = VendedorCreationForm(request.POST)
        if form.is_valid():
            vendedor = form.save()
            messages.success(request, 'Vendedor creado exitosamente.')
            return redirect('inmobiliaria:vendedor_detalle', vendedor_id=vendedor.id)
    else:
        form = VendedorCreationForm()
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
    return render(request, 'inmobiliaria/propiedades/detalle.html', {'propiedad': propiedad})
@login_required 
def propiedad_nuevo(request):
    ImageFormSet = modelformset_factory(PropiedadImagen, form=PropiedadImagenForm, extra=1, can_delete=True)

    if request.method == 'POST':
        form = PropiedadForm(request.POST, request.FILES)
        formset = ImageFormSet(request.POST, request.FILES, queryset=PropiedadImagen.objects.none())

        if form.is_valid() and formset.is_valid():
            propiedad = form.save(commit=False)
            
            if form.cleaned_data['nuevo_propietario']:
                # Create new Propietario
                propietario = Propietario.objects.create(
                    nombre=form.cleaned_data['nombre_propietario'],
                    apellido=form.cleaned_data['apellido_propietario'],
                    # Add other fields as necessary
                )
            else:
                propietario = form.cleaned_data['propietario']
            
            propiedad.propietario = propietario
            propiedad.save()

            # Save images
            for form in formset.cleaned_data:
                if form:
                    imagen = form['imagen']
                    PropiedadImagen.objects.create(propiedad=propiedad, imagen=imagen)

            messages.success(request, 'Propiedad creada exitosamente.')
            return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad.id)
    else:
        form = PropiedadForm()
        formset = ImageFormSet(queryset=PropiedadImagen.objects.none())

    return render(request, 'inmobiliaria/propiedades/formulario.html', {
        'form': form,
        'image_formset': formset,
    })

@login_required
def propiedad_editar(request, propiedad_id):
    propiedad = get_object_or_404(Propiedad, pk=propiedad_id)
    ImageFormSet = modelformset_factory(PropiedadImagen, form=PropiedadImagenForm, extra=1, can_delete=True)

    if request.method == "POST":
        form = PropiedadForm(request.POST, request.FILES, instance=propiedad)
        formset = ImageFormSet(request.POST, request.FILES, queryset=propiedad.imagenes.all())

        if form.is_valid() and formset.is_valid():
            propiedad = form.save(commit=False)
            
            if form.cleaned_data['nuevo_propietario']:
                # Create new Propietario
                propietario = Propietario.objects.create(
                    nombre=form.cleaned_data['nombre_propietario'],
                    apellido=form.cleaned_data['apellido_propietario'],
                    # Add other fields as necessary
                )
                propiedad.propietario = propietario
            elif form.cleaned_data['propietario']:
                propiedad.propietario = form.cleaned_data['propietario']
            
            propiedad.save()

            # Handle images (same as before)
            for form in formset.cleaned_data:
                if form:
                    imagen = form['imagen']
                    if form.get('id'):
                        instance = form['id']
                        instance.imagen = imagen
                        instance.save()
                    else:
                        PropiedadImagen.objects.create(propiedad=propiedad, imagen=imagen)

            for obj in formset.deleted_objects:
                obj.delete()

            messages.success(request, 'Propiedad actualizada exitosamente.')
            return redirect('inmobiliaria:propiedad_detalle', propiedad_id=propiedad.id)
    else:
        form = PropiedadForm(instance=propiedad)
        formset = ImageFormSet(queryset=propiedad.imagenes.all())

    return render(request, 'inmobiliaria/propiedades/formulario.html', {
        'form': form,
        'image_formset': formset,
        'propiedad': propiedad,
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
