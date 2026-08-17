"""
URL configuration for sistema_gonnet project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# File: sistema_gonnet/urls.py

from django.contrib import admin
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


def healthz(_request):
    """Liveness para Railway: sin DB ni sesión, para que el deploy no se cuelgue."""
    return HttpResponse('ok', content_type='text/plain')


def root_redirect(request):
    if getattr(request, 'user', None) is not None and request.user.is_authenticated:
        return HttpResponseRedirect('/dashboard/')
    return HttpResponseRedirect('/login/')


urlpatterns = [
    path('healthz/', healthz, name='healthz'),
    path('healthz', healthz),
    path('', root_redirect, name='index'),
    path('admin/', admin.site.urls),
    path('', include(('inmobiliaria.urls', 'inmobiliaria'), namespace='inmobiliaria')),
]

# Servir archivos de medios en desarrollo y producción
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)