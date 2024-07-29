# File: inmobiliaria/views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from .models import Vendedor, Inquilino, Propietario
from django.contrib import messages
from .forms import VendedorForm, InquilinoForm, PropietarioForm

# index view
def index(request):
    return render(request, 'inmobiliaria/index.html')

# Vendedor views
def vendedores(request):
    vendedores = Vendedor.objects.all()
    return render(request, 'inmobiliaria/vendedores/lista.html', {'vendedores': vendedores})

def vendedor_detalle(request, vendedor_id):
    vendedor = get_object_or_404(Vendedor, pk=vendedor_id)
    return render(request, 'inmobiliaria/vendedores/detalle.html', {'vendedor': vendedor})

def vendedor_nuevo(request):
    if request.method == "POST":
        form = VendedorForm(request.POST)
        if form.is_valid():
            vendedor = form.save()
            messages.success(request, 'Vendedor creado exitosamente.')
            return redirect('inmobiliaria:vendedor_detalle', vendedor_id=vendedor.id)
    else:
        form = VendedorForm()
    return render(request, 'inmobiliaria/vendedores/formulario.html', {'form': form})

def vendedor_editar(request, vendedor_id):
    vendedor = get_object_or_404(Vendedor, pk=vendedor_id)
    if request.method == "POST":
        form = VendedorForm(request.POST, instance=vendedor)
        if form.is_valid():
            vendedor = form.save()
            messages.success(request, 'Vendedor actualizado exitosamente.')
            return redirect('inmobiliaria:vendedor_detalle', vendedor_id=vendedor.id)
    else:
        form = VendedorForm(instance=vendedor)
    return render(request, 'inmobiliaria/vendedores/formulario.html', {'form': form, 'vendedor': vendedor})

def vendedor_eliminar(request, vendedor_id):
    vendedor = get_object_or_404(Vendedor, pk=vendedor_id)
    if request.method == "POST":
        vendedor.delete()
        messages.success(request, 'Vendedor eliminado exitosamente.')
        return redirect('inmobiliaria:vendedores')
    return render(request, 'inmobiliaria/vendedores/confirmar_eliminar.html', {'vendedor': vendedor})

# Inquilino views
def inquilinos(request):
    inquilinos = Inquilino.objects.all()
    return render(request, 'inmobiliaria/inquilinos/lista.html', {'inquilinos': inquilinos})

def inquilino_detalle(request, inquilino_id):
    inquilino = get_object_or_404(Inquilino, pk=inquilino_id)
    return render(request, 'inmobiliaria/inquilinos/detalle.html', {'inquilino': inquilino})

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

def inquilino_eliminar(request, inquilino_id):
    inquilino = get_object_or_404(Inquilino, pk=inquilino_id)
    if request.method == "POST":
        inquilino.delete()
        messages.success(request, 'Inquilino eliminado exitosamente.')
        return redirect('inmobiliaria:inquilinos')
    return render(request, 'inmobiliaria/inquilinos/confirmar_eliminar.html', {'inquilino': inquilino})

# Propietario views
def propietarios(request):
    propietarios = Propietario.objects.all()
    return render(request, 'inmobiliaria/propietarios/lista.html', {'propietarios': propietarios})

def propietario_detalle(request, propietario_id):
    propietario = get_object_or_404(Propietario, pk=propietario_id)
    return render(request, 'inmobiliaria/propietarios/detalle.html', {'propietario': propietario})

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

def propietario_eliminar(request, propietario_id):
    propietario = get_object_or_404(Propietario, pk=propietario_id)
    if request.method == "POST":
        propietario.delete()
        messages.success(request, 'Propietario eliminado exitosamente.')
        return redirect('inmobiliaria:propietarios')
    return render(request, 'inmobiliaria/propietarios/confirmar_eliminar.html', {'propietario': propietario})