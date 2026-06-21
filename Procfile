# Post Reach Backend Procfile
# Used by Heroku / Dokku / other platforms to run production services

web: gunicorn post_reach_backend.wsgi:application --bind 0.0.0.0:$PORT --workers 4 --timeout 120 --access-logfile -

# Celery worker for async task processing
worker: celery -A post_reach_backend worker -l info -P solo

# Celery beat scheduler for periodic tasks
beat: celery -A post_reach_backend beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler