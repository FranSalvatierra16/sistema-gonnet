import os

# Configuración de sesión
SESSION_COOKIE_AGE = 600  # 10 minutos en segundos
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

# Configuración para servir archivos estáticos en producción
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Configuración de seguridad
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Configuración de hosts permitidos
ALLOWED_HOSTS = [
    'gonnet-interno-052a6cec3da9.herokuapp.com',
    'localhost',
    '127.0.0.1',
]

# Configuración de middleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Configuración de Debug
DEBUG = False  # Asegúrate de que esté en False en producción

INSTALLED_APPS = [
    # ... otras apps ...
    'django.contrib.humanize',
    'storages',
    # ... resto de las apps ...
]

FILE_UPLOAD_MAX_MEMORY_SIZE = 26214400  # 25 MB

MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
MEDIA_URL = '/media/'

DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

DATABASES = {
    'default': {
        'CONN_MAX_AGE': 60,  # o 0 para cerrar cada vez, pero 60 es razonable
    }
}