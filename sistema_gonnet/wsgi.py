"""
WSGI config for sistema_gonnet project.

El healthcheck de Railway tiene que responder 200 *antes* de cargar Django
(views.py es enorme y el primer import puede tardar minutos).
"""

import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sistema_gonnet.settings')

_django_app = None
_HEALTH_BODY = b'ok'
_HEALTH_HEADERS = [
    ('Content-Type', 'text/plain; charset=utf-8'),
    ('Content-Length', str(len(_HEALTH_BODY))),
    ('Cache-Control', 'no-store'),
]


def _es_healthcheck(environ):
    path = (environ.get('PATH_INFO') or '').split('?', 1)[0]
    if path.rstrip('/') == '/healthz':
        return True
    host = (environ.get('HTTP_HOST') or '').split(':')[0].lower()
    return host == 'healthcheck.railway.app'


def application(environ, start_response):
    global _django_app
    if _es_healthcheck(environ):
        start_response('200 OK', list(_HEALTH_HEADERS))
        return [_HEALTH_BODY]
    if _django_app is None:
        from django.core.wsgi import get_wsgi_application
        _django_app = get_wsgi_application()
    return _django_app(environ, start_response)
