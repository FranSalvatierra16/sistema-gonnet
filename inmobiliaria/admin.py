from django.contrib import admin
from django.contrib import messages
from .models import (
    Vendedor,
    Inquilino,
    Propietario,
    Propiedad,
    HistorialDisponibilidad,
    Sucursal,
    Caja,
)

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
    list_display = ('dni', 'nombre', 'apellido', 'email', 'celular', 'cuenta_cbu_alias', 'cuenta_banco')
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


def reset_caja_desde_cero_sucursal(modeladmin, request, queryset):
    """
    Cierra cajas abiertas de la sucursal y abre una nueva con saldo 0 (no borra movimientos).
    Solo superusuarios: acción destructiva en producción.
    """
    if not request.user.is_superuser:
        modeladmin.message_user(
            request,
            'Solo un superusuario puede ejecutar el reset de caja.',
            level=messages.ERROR,
        )
        return
    from inmobiliaria.caja_reset import reset_caja_sucursal_desde_cero

    for sucursal in queryset:
        try:
            nueva, cerradas = reset_caja_sucursal_desde_cero(
                sucursal,
                request.user,
                observacion_cierre_extra='[Admin: reset caja desde cero]',
            )
            modeladmin.message_user(
                request,
                f'{sucursal.nombre}: se cerraron {len(cerradas)} caja(s) abierta(s); '
                f'nueva caja #{nueva.numero} con saldo inicial $0.',
                level=messages.SUCCESS,
            )
        except Exception as e:
            modeladmin.message_user(
                request,
                f'Error en {sucursal.nombre}: {e}',
                level=messages.ERROR,
            )


reset_caja_desde_cero_sucursal.short_description = (
    'Caja: cerrar abiertas y abrir nueva (saldo $0) — solo superuser'
)


@admin.register(Sucursal)
class SucursalAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'direccion', 'telefono')
    search_fields = ('nombre', 'direccion')
    actions = [reset_caja_desde_cero_sucursal]


@admin.register(Caja)
class CajaAdmin(admin.ModelAdmin):
    list_display = (
        'numero',
        'sucursal',
        'estado',
        'saldo_inicial',
        'saldo_final',
        'fecha_apertura',
        'fecha_cierre',
    )
    list_filter = ('estado', 'sucursal')
    search_fields = ('observaciones_apertura', 'observaciones_cierre')
    readonly_fields = ('numero',)
    ordering = ('-fecha_apertura',)


@admin.register(Propiedad)
class PropiedadAdmin(admin.ModelAdmin):
    list_display = ('id', 'direccion', 'propietario', 'sucursal')
    search_fields = ('direccion', 'propietario__nombre', 'propietario__apellido')
    list_filter = ('sucursal', 'tipo_inmueble')
    actions = [reconstruir_historial_propiedad]
