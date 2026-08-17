from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth import logout
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from django.db import connection

# Actualizar last_activity en sesión como máximo cada N segundos (menos escrituras a DB).
SESSION_ACTIVITY_WRITE_INTERVAL_SECONDS = 300


class CloseDBConnectionMiddleware:
    """
    Cierra la conexión DB al final del request solo cuando no hay pool (MySQL CONN_MAX_AGE=0).
    En Railway/PostgreSQL con conn_max_age>0, reutilizar la conexión es mucho más rápido.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = None
        try:
            response = self.get_response(request)
        finally:
            db = settings.DATABASES.get('default', {})
            conn_max_age = int(db.get('CONN_MAX_AGE') or 0)
            engine = (db.get('ENGINE') or '').lower()
            reuse = conn_max_age > 0 and 'postgresql' in engine
            if not reuse and connection.connection is not None:
                connection.close()
        return response


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
            if getattr(request.user, 'password_temporal', False):
                if not request.path == reverse('inmobiliaria:cambiar_password'):
                    messages.warning(request, 'Por favor, cambia tu contraseña temporal.')
                    return redirect('inmobiliaria:cambiar_password')

        response = self.get_response(request)
        return response


_PUBLIC_PATH_PREFIXES = (
    '/healthz',
    '/login/',
    '/sucursal/',
    '/recuperar-password/',
    '/admin/login/',
    '/admin/password_reset/',
    '/password_reset/',
    '/reset/',
    '/api/resetear-password-temp/',
    '/api/debug-usuarios/',
    '/api/ejecutar-migracion/',
    '/utilidades/diagrama-db/',
    '/web/',
    '/recibo-publico/',
    '/recibo-movimiento-publico/',
    '/static/',
    '/media/',
    '/favicon',
    '/robots.txt',
)


def _es_ruta_publica(path: str) -> bool:
    if path in ('/', '/healthz', '/healthz/'):
        return True
    return any(path.startswith(p) for p in _PUBLIC_PATH_PREFIXES)


class SessionTimeoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Healthcheck: no tocar usuario/sesión/DB.
        if _es_ruta_publica(request.path) and request.path.startswith('/healthz'):
            return self.get_response(request)

        if request.user.is_authenticated:
            now = timezone.now()
            last_activity = request.session.get('last_activity')
            if last_activity:
                last_activity_dt = timezone.datetime.fromisoformat(last_activity)
                if now - last_activity_dt > timedelta(seconds=settings.SESSION_COOKIE_AGE):
                    logout(request)
                    messages.warning(request, 'Tu sesión ha expirado. Por favor, inicia sesión nuevamente.')
                    return redirect('inmobiliaria:login')
                if now - last_activity_dt > timedelta(seconds=SESSION_ACTIVITY_WRITE_INTERVAL_SECONDS):
                    request.session['last_activity'] = now.isoformat()
            else:
                request.session['last_activity'] = now.isoformat()

        response = self.get_response(request)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        if _es_ruta_publica(request.path):
            return None

        if not request.user.is_authenticated:
            # Sin messages: cada aviso anónimo escribía una sesión en DB y saturaba workers.
            return redirect('inmobiliaria:login')
        return None
