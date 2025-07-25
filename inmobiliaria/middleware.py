from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth import logout
from django.utils import timezone
from datetime import timedelta
from django.conf import settings

class SucursalMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not hasattr(request.user, 'sucursal'):
            messages.error(request, 'No tienes una sucursal asignada')
            return redirect('logout')
        return self.get_response(request)

class PasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Verifica si el usuario necesita cambiar su contraseña
            # Puedes agregar un campo en tu modelo de Usuario para marcar contraseñas temporales
            if getattr(request.user, 'password_temporal', False):
                # Excluye la página de cambio de contraseña para evitar redirecciones infinitas
                if not request.path == reverse('inmobiliaria:cambiar_password'):
                    messages.warning(request, 'Por favor, cambia tu contraseña temporal.')
                    return redirect('inmobiliaria:cambiar_password')

        response = self.get_response(request)
        return response

class SessionTimeoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            last_activity = request.session.get('last_activity')
            if last_activity:
                last_activity = timezone.datetime.fromisoformat(last_activity)
                if timezone.now() - last_activity > timedelta(seconds=settings.SESSION_COOKIE_AGE):
                    logout(request)
                    messages.warning(request, 'Tu sesión ha expirado. Por favor, inicia sesión nuevamente.')
                    return redirect('inmobiliaria:login')
            
            request.session['last_activity'] = timezone.now().isoformat()

        response = self.get_response(request)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Lista de URLs que no requieren autenticación
        public_urls = [
            '/login/',
            '/recuperar-password/',  # URL correcta para recuperación de contraseña
            '/admin/login/',
            '/admin/password_reset/',
            '/password_reset/',
            '/reset/',
        ]
        
        # Si la URL actual está en la lista de URLs públicas, permitir el acceso
        if any(request.path.startswith(url) for url in public_urls):
            return None

        if not request.user.is_authenticated:
            messages.warning(request, 'Por favor, inicia sesión para continuar.')
            return redirect('inmobiliaria:login')
        return None