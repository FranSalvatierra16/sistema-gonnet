release: python manage.py migrate --noinput
web: gunicorn sistema_gonnet.wsgi --preload --bind 0.0.0.0:$PORT --workers ${WEB_CONCURRENCY:-1} --threads=4 --timeout=120 --max-requests=500 --max-requests-jitter=50 --log-file -
