# File: inmobiliaria/urls.py

from django.urls import path
from . import views

app_name = 'inmobiliaria'

urlpatterns = [
    # main entities
    path('', views.index, name='index'),
    path('vendedores/', views.vendedores, name='vendedores'),
    path('inquilinos/', views.inquilinos, name='inquilinos'),
    path('propietarios/', views.propietarios, name='propietarios'),
    
    # detail views
    path('vendedores/<int:vendedor_id>/', views.vendedor_detalle, name='vendedor_detalle'),
    path('inquilinos/<int:inquilino_id>/', views.inquilino_detalle, name='inquilino_detalle'),
    path('propietarios/<int:propietario_id>/', views.propietario_detalle, name='propietario_detalle'),
    
    # crear
    path('vendedores/nuevo/', views.vendedor_nuevo, name='vendedor_nuevo'),
    path('inquilinos/nuevo/', views.inquilino_nuevo, name='inquilino_nuevo'),
    path('propietarios/nuevo/', views.propietario_nuevo, name='propietario_nuevo'),
    
    # editar
    path('vendedores/<int:vendedor_id>/editar/', views.vendedor_editar, name='vendedor_editar'),
    path('inquilinos/<int:inquilino_id>/editar/', views.inquilino_editar, name='inquilino_editar'),
    path('propietarios/<int:propietario_id>/editar/', views.propietario_editar, name='propietario_editar'),
    
    # eliminar
    path('vendedores/<int:vendedor_id>/eliminar/', views.vendedor_eliminar, name='vendedor_eliminar'),
    path('inquilinos/<int:inquilino_id>/eliminar/', views.inquilino_eliminar, name='inquilino_eliminar'),
    path('propietarios/<int:propietario_id>/eliminar/', views.propietario_eliminar, name='propietario_eliminar'),
]