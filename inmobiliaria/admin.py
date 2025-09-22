from django.contrib import admin
from django.contrib import messages
from .models import Vendedor, Inquilino, Propietario, Propiedad, HistorialDisponibilidad

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

def reconstruir_historial_propiedad(modeladmin, request, queryset):
    """
    Acción de admin para reconstruir historial de propiedades seleccionadas
    """
    propiedades_procesadas = 0
    
    for propiedad in queryset:
        try:
            # Limpiar historial existente
            HistorialDisponibilidad.objects.filter(propiedad=propiedad).delete()
            
            # Reconstruir si hay reservas
            if propiedad.reservas.exists():
                primera_reserva = propiedad.reservas.first()
                primera_reserva.reconstruir_historial_cronologico()
            else:
                # Si no hay reservas, crear historial básico con disponibilidades
                for disp in propiedad.disponibilidades.all():
                    HistorialDisponibilidad.objects.create(
                        propiedad=propiedad,
                        fecha_inicio=disp.fecha_inicio,
                        fecha_fin=disp.fecha_fin,
                        estado='libre'
                    )
            
            propiedades_procesadas += 1
            
        except Exception as e:
            messages.error(request, f'Error en propiedad {propiedad.id}: {str(e)}')
            continue
    
    if propiedades_procesadas > 0:
        messages.success(request, f'✅ Historial reconstruido para {propiedades_procesadas} propiedades')
    else:
        messages.warning(request, '⚠️ No se procesaron propiedades')

reconstruir_historial_propiedad.short_description = "🔄 Reconstruir historial cronológico"

@admin.register(Propiedad)
class PropiedadAdmin(admin.ModelAdmin):
    list_display = ('id', 'direccion', 'propietario', 'sucursal')
    search_fields = ('direccion', 'propietario__nombre', 'propietario__apellido')
    list_filter = ('sucursal', 'tipo_inmueble')
    actions = [reconstruir_historial_propiedad]
