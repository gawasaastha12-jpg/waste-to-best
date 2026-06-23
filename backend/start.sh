#!/bin/bash

# Run database migrations
echo "Running database migrations..."
python manage.py migrate --noinput

# Start Celery worker in the background
echo "Starting Celery worker..."
celery -A core worker --loglevel=info -P solo -Q classification,safety,notifications,celery &

# Start Gunicorn server in the foreground
echo "Starting Gunicorn server..."
gunicorn core.wsgi:application --bind 0.0.0.0:8000 --workers 2
