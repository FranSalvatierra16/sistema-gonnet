from django.urls import path
from django.contrib.auth import views as auth_views
from django.views.generic.base import RedirectView
from django.conf import settings
from django.conf.urls.static import static
from . import views

app_name = 'inmobiliaria'

urlpatterns = [
    # Auth URLs
    path('login/', auth_views.LoginView.as_view(template_name='inmobiliaria/autenticacion/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='inmobiliaria:login'), name='logout'),
    path('register/', views.register, name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # Redirect root URL to register
    path('', RedirectView.as_view(url='/register/', permanent=False), name='index'),

    # Vendedor URLs
    path('vendedores/', views.vendedores, name='vendedores'),
    path('vendedores/<int:vendedor_id>/', views.vendedor_detalle, name='vendedor_detalle'),
    path('vendedores/nuevo/', views.vendedor_nuevo, name='vendedor_nuevo'),
    path('vendedores/<int:vendedor_id>/editar/', views.vendedor_editar, name='vendedor_editar'),
    path('vendedores/<int:vendedor_id>/eliminar/', views.vendedor_eliminar, name='vendedor_eliminar'),
    path('historial-reservas-vendedor/<int:vendedor_id>/', views.historial_reservas_vendedor, name='historial_reservas_vendedor'),
    # Inquilino URLs
    path('inquilinos/', views.inquilinos, name='inquilinos'),
    path('inquilinos/<int:inquilino_id>/', views.inquilino_detalle, name='inquilino_detalle'),
    path('inquilinos/nuevo/', views.inquilino_nuevo, name='inquilino_nuevo'),
    path('inquilinos/<int:inquilino_id>/editar/', views.inquilino_editar, name='inquilino_editar'),
    path('inquilinos/<int:inquilino_id>/eliminar/', views.inquilino_eliminar, name='inquilino_eliminar'),
    path('historial-reservas-inquilino/<int:inquilino_id>/', views.historial_reservas_inquilino, name='historial_reservas_inquilino'),
    # Propietario URLs
    path('propietarios/', views.propietarios, name='propietarios'),
    path('propietarios/<int:propietario_id>/', views.propietario_detalle, name='propietario_detalle'),
    path('propietarios/nuevo/', views.propietario_nuevo, name='propietario_nuevo'),
    path('propietarios/<int:propietario_id>/editar/', views.propietario_editar, name='propietario_editar'),
    path('propietarios/<int:propietario_id>/eliminar/', views.propietario_eliminar, name='propietario_eliminar'),
    path('crear-propietario/', views.propietario_nuevo_ajax, name='crear_propietario_ajax'),
    path('propiedad/<int:propiedad_id>/precios/', views.gestionar_precios, name='gestionar_precios'),
    path('propietario/<int:propietario_id>/propiedades/', views.propiedades_por_propietario, name='propiedades_propietario'),
    # Propiedad URLs
    path('propiedades/', views.propiedades, name='propiedades'),
    path('propiedades/<int:propiedad_id>/', views.propiedad_detalle, name='propiedad_detalle'),
    path('propiedades/nuevo/', views.propiedad_nuevo, name='propiedad_nuevo'),
    path('propiedades/<int:propiedad_id>/editar/', views.propiedad_editar, name='propiedad_editar'),
    path('propiedades/<int:propiedad_id>/eliminar/', views.propiedad_eliminar, name='propiedad_eliminar'),
    path('propiedad/<int:propiedad_id>/crear-disponibilidad/', views.crear_disponibilidad, name='crear_disponibilidad'),
    path('buscar-propiedades-23/', views.buscar_propiedades_23, name='buscar_propiedades_23'),
    path('propietario/nuevo/ajax/', views.propietario_nuevo_ajax, name='propietario_nuevo_ajax'),
     path('buscar-clientes/', views.buscar_clientes, name='buscar_clientes'),
    path('crear-inquilino-ajax/', views.crear_inquilino_ajax, name='crear_inquilino_ajax'),

    # Reserva URLs
    path('reservas/', views.reservas, name='reservas'),
    path('operaciones/', views.operaciones, name='operaciones'),
    path('reservas/nuevo/', views.buscar_propiedades, name='buscar_propiedades'),
    path('reservas/crear/', views.crear_reserva, name='crear_reserva'),
    path('reservas/<int:reserva_id>/', views.reserva_detalle, name='reserva_detalle'),
    path('confirmar_reserva/', views.confirmar_reserva, name='confirmar_reserva'),
    path('reserva_exitosa/<int:reserva_id>/', views.reserva_exitosa, name='reserva_exitosa'),
    path('reservas/finalizar/<int:reserva_id>/', views.terminar_reserva, name='finalizar_reserva'),
    path('reservas/<int:reserva_id>/editar/', views.reserva_editar, name='reserva_editar'),
  path('buscar-propietarios/', views.buscar_propietarios, name='buscar_propietarios'),
  path('buscar-inquilinos/', views.buscar_inquilinos, name='buscar_inquilinos'),
    path('reserva/eliminar/<int:reserva_id>/', views.reserva_eliminar, name='reserva_eliminar'),
    path('autenticacion-vendedor/', views.autenticacion_vendedor, name='autenticacion_vendedor'),
    path('obtener-precios-propiedad/', views.obtener_precios_propiedad, name='obtener_precios_propiedad'),
    path('obtener-vendedor/<int:vendedor_id>/', views.obtener_vendedor, name='obtener_vendedor'),
    
  

]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


