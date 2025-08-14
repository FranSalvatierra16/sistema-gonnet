from django.urls import path
from django.contrib.auth import views as auth_views
from django.views.generic.base import RedirectView
from django.conf import settings
from django.conf.urls.static import static
from . import views

app_name = 'inmobiliaria'

urlpatterns = [
    # Auth URLs
    path('login/', views.login_view, name='login'),
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
    path('crear-propietario/', views.crear_propietario_ajax, name='crear_propietario_ajax'),
    path('propiedad/<int:propiedad_id>/precios/', views.gestionar_precios, name='gestionar_precios'),
    path('propietario/<int:propietario_id>/propiedades/', views.propiedades_por_propietario, name='propiedades_propietario'),
    
    # Propiedad URLs
    path('propiedades/', views.propiedades, name='propiedades'),
    path('propiedades/<int:propiedad_id>/', views.propiedad_detalle, name='propiedad_detalle'),
    path('propiedades/nuevo/', views.propiedad_nuevo, name='propiedad_nuevo'),
    path('propiedades/<int:propiedad_id>/editar/', views.propiedad_editar, name='propiedad_editar'),
    path('propiedades/<int:propiedad_id>/eliminar/', views.propiedad_eliminar, name='propiedad_eliminar'),
    path('propiedad/<int:propiedad_id>/crear-disponibilidad/', views.crear_disponibilidad, name='crear_disponibilidad'),

    # Reserva URLs
    path('reservas/', views.reservas, name='reservas'),
    path('reservas/<int:reserva_id>/', views.reserva_detalle, name='reserva_detalle'),
    path('reservas/nueva/', views.reserva_nueva, name='reserva_nueva'),
    path('reservas/<int:reserva_id>/editar/', views.reserva_editar, name='reserva_editar'),
    path('reservas/<int:reserva_id>/eliminar/', views.reserva_eliminar, name='reserva_eliminar'),
    path('reservas/<int:reserva_id>/confirmar-pago/', views.confirmar_pago, name='confirmar_pago'),
    path('reservas/<int:reserva_id>/agregar-pago/', views.agregar_pago, name='agregar_pago'),
    path('reservas/<int:reserva_id>/agregar-deposito/', views.agregar_deposito, name='agregar_deposito'),
    path('pago/<int:pago_id>/eliminar/', views.eliminar_pago, name='eliminar_pago'),
    
    # ============================
    # URLs SIMPLIFICADAS PARA CAJA
    # ============================
    
    # Dashboard y gestión general
    path('caja/dashboard/', views.dashboard_caja, name='dashboard_caja'),
    path('caja/', views.gestionar_caja, name='gestionar_caja'),
    path('caja/abrir/', views.abrir_caja, name='abrir_caja'),
    
    # Lista de cajas
    path('cajas/', views.lista_cajas, name='lista_cajas'),
    path('cajas/<int:numero>/', views.detalle_caja, name='detalle_caja'),
    path('cajas/<int:numero>/cerrar/', views.cerrar_caja, name='cerrar_caja'),
    
    # Movimientos
    path('caja/movimiento/nuevo/', views.nuevo_movimiento, name='nuevo_movimiento'),
    path('caja/movimiento/<int:movimiento_id>/eliminar/', views.eliminar_movimiento, name='eliminar_movimiento'),
    
    # APIs y utilidades de caja
    path('caja/obtener-actual/', views.obtener_caja_actual, name='obtener_caja_actual'),
    path('caja/conceptos/buscar/', views.buscar_conceptos, name='buscar_conceptos'),
    path('caja/conceptos/crear/', views.crear_concepto, name='crear_concepto'),
    path('caja/propiedades/buscar/', views.buscar_propiedades_caja, name='buscar_propiedades_caja'),

    # Otros URLs
    path('propietario/nuevo/ajax/', views.propietario_nuevo_ajax, name='propietario_nuevo_ajax'),
    path('buscar-clientes/', views.buscar_clientes, name='buscar_clientes'),
    path('crear-inquilino-ajax/', views.crear_inquilino_ajax, name='crear_inquilino_ajax'),
    path('crear-concepto-ajax/', views.crear_concepto_ajax, name='crear_concepto_ajax'),
    path('procesar-movimiento-reserva/', views.procesar_movimiento_reserva, name='procesar_movimiento_reserva'),
    path('test-json/', views.test_json_response, name='test_json_response'),
    path('api/propiedad/<int:propiedad_id>/', views.api_propiedad_detalle, name='api_propiedad_detalle'),
    path('api/precio/<int:precio_id>/', views.api_precio_detalle, name='api_precio_detalle'),
    path('api/conceptos/', views.api_conceptos, name='api_conceptos'),
    path('api/vendedores/', views.api_vendedores, name='api_vendedores'),
    path('api/inquilinos/', views.api_inquilinos, name='api_inquilinos'),
    path('api/propietarios/', views.api_propietarios, name='api_propietarios'),
    path('api/propietario/<int:propietario_id>/', views.api_propietario_detalle, name='api_propietario_detalle'),
    path('api/propiedades/', views.api_propiedades, name='api_propiedades'),
    path('api/check-disponibilidad/', views.api_check_disponibilidad, name='api_check_disponibilidad'),
    path('buscar-propiedades/', views.buscar_propiedades, name='buscar_propiedades'),
    path('cambiar-password/', views.cambiar_password, name='cambiar_password'),
    path('propiedades/<str:propiedad_id>/editar-venta/', views.editar_info_venta, name='editar_info_venta'),
    path('propiedades/<int:propiedad_id>/editar-meses/', views.editar_info_meses, name='editar_info_meses'),
    path('ventas/', views.ventas, name='ventas'),
    path('alquileres-24-meses/', views.alquileres_24_meses, name='alquileres_24_meses'),
    path('dashboard/ventas/', views.ventas, name='dashboard_ventas'),
    path('propiedad/<int:propiedad_id>/iniciar-compra/', views.iniciar_compra, name='iniciar_compra'),

    # Utilidades
    path('crear-propiedad/', views.crear_propiedad, name='crear_propiedad'),
    path('api/simple-select2/', views.simple_select2, name='simple_select2'),
    path('buscar/propietarios/', views.buscar_propietarios, name='buscar_propietarios'),
    path('buscar/operacion/', views.buscar_operacion, name='buscar_operacion'),
    path('buscar/productores/', views.buscar_productores, name='buscar_productores'),
    path('conceptos/', views.conceptos_list, name='conceptos_list'),
    path('propietario_cuentas/', views.propietario_cuentas, name='propietario_cuentas'),
    path('guardar_movimiento/', views.guardar_movimiento, name='guardar_movimiento'),

    # Rutas de imágenes
    path('imagen/<int:imagen_id>/eliminar/', views.imagen_eliminar, name='imagen_eliminar'),
    path('propiedad/<int:propiedad_id>/eliminar-todas-imagenes/', views.eliminar_todas_imagenes, name='eliminar_todas_imagenes'),
    path('propiedades/<int:propiedad_id>/reordenar-imagenes/', views.reordenar_imagenes, name='reordenar_imagenes'),
    path('obtener-caracteristicas-propiedad/', views.obtener_caracteristicas_propiedad, name='obtener_caracteristicas_propiedad'),
    path('obtener-fotos-propiedad/<int:propiedad_id>/', views.obtener_fotos_propiedad, name='obtener_fotos_propiedad'),
    path('obtener-precios-propiedad/<int:propiedad_id>/', views.obtener_precios_propiedad, name='obtener_precios_propiedad'),
    path('guardar-precios-propiedad/', views.guardar_precios_propiedad, name='guardar_precios_propiedad'),
    
    # Sucursal URLs
    path('sucursal/', views.sucursales, name='sucursales'),
    path('sucursal/<int:sucursal_id>/', views.sucursal_detalle, name='sucursal_detalle'),
    path('sucursal/<int:sucursal_id>/editar/', views.editar_sucursal, name='editar_sucursal'),

    # ============================
    # URLs PARA CONTRATOS 24 MESES
    # ============================
    
    # APIs
    path('api/inquilino/<int:inquilino_id>/', views.api_inquilino_detalle, name='api_inquilino_detalle'),
    path('api/vendedor/<int:vendedor_id>/', views.api_vendedor_detalle, name='api_vendedor_detalle'),
    
    # Contratos
    path('contratos/crear/', views.crear_contrato_alquiler, name='crear_contrato_alquiler'),
    path('contratos/', views.lista_contratos, name='lista_contratos'),
    path('contratos/<int:contrato_id>/', views.detalle_contrato, name='detalle_contrato'),
    path('contratos/<int:contrato_id>/operacion/', views.crear_operacion_contrato, name='crear_operacion_contrato'),
    path('contratos/<int:contrato_id>/procesar-operacion/', views.procesar_operacion_contrato, name='procesar_operacion_contrato'),
    path('contratos/<int:contrato_id>/cuotas/', views.ver_cuotas_contrato, name='ver_cuotas_contrato'),
    path('api/cuota/<int:cuota_id>/', views.api_cuota_detalle, name='api_cuota_detalle'),
    path('contratos/cuota/<int:cuota_id>/pagar/', views.pagar_cuota, name='pagar_cuota'),
    path('contratos/<int:contrato_id>/cancelar/', views.cancelar_contrato, name='cancelar_contrato'),
    path('propiedades/<int:propiedad_id>/reactivar-24-meses/', views.reactivar_propiedad_24_meses, name='reactivar_propiedad_24_meses'),
    path('propiedades/<int:propiedad_id>/desactivar-24-meses/', views.desactivar_propiedad_24_meses, name='desactivar_propiedad_24_meses'),
    
]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
