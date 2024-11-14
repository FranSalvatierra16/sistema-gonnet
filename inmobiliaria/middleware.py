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