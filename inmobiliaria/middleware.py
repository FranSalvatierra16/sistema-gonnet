from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages

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