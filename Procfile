release: python manage.py migrate --noinput
web: gunicorn sistema_gonnet.wsgi --bind 0.0.0.0:$PORT --workers ${WEB_CONCURRENCY:-1} --threads ${WEB_THREADS:-8} --timeout 45 --graceful-timeout 25 --keep-alive 5 --max-requests 200 --max-requests-jitter 40 --log-file -
