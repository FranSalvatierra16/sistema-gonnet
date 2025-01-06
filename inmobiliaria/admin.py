from django.contrib import admin
from .models import Vendedor, Inquilino, Propietario, Movimiento

@admin.register(Vendedor)
class VendedorAdmin(admin.ModelAdmin):
    list_display = ('username', 'dni', 'nombre', 'apellido', 'email', 'comision')

@admin.register(Inquilino)
class InquilinoAdmin(admin.ModelAdmin):
    list_display = ('dni', 'nombre', 'apellido', 'email', 'celular')
    search_fields = ('dni', 'nombre', 'apellido', 'email')
    list_filter = ('fecha_nacimiento',)

@admin.register(Propietario)
class PropietarioAdmin(admin.ModelAdmin):
    list_display = ('dni', 'nombre', 'apellido', 'email', 'celular', 'cuenta_bancaria')
    search_fields = ('dni', 'nombre', 'apellido', 'email')
    list_filter = ('fecha_nacimiento',)

@admin.register(Movimiento)
class MovimientoAdmin(admin.ModelAdmin):
    list_display = ['fecha', 'tipo', 'categoria', 'monto', 'usuario', 'sucursal']
    list_filter = ['tipo', 'categoria', 'fecha', 'sucursal']
    search_fields = ['descripcion']
    date_hierarchy = 'fecha'
