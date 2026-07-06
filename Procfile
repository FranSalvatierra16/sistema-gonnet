web: python manage.py migrate --noinput && gunicorn sistema_gonnet.wsgi --bind 0.0.0.0:$PORT --workers=3 --threads=2 --timeout=120 --max-requests=1000 --max-requests-jitter=50 --log-file -

