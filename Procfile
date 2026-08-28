release: python manage.py migrate --noinput
web: gunicorn sistema_gonnet.wsgi --bind 0.0.0.0:$PORT --workers ${WEB_CONCURRENCY:-1} --threads ${GUNICORN_THREADS:-4} --timeout 120 --max-requests ${GUNICORN_MAX_REQUESTS:-200} --max-requests-jitter 25 --log-file -
