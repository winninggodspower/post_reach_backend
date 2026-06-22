# Post Reach Backend Procfile
# Used by Heroku / Dokku / other platforms to run production services
release: python manage.py migrate

web: gunicorn post_reach_backend.wsgi:application --bind 0.0.0.0:$PORT --workers 4 --timeout 120 --access-logfile -

# update celery and schedular to run in same process for now
worker: celery -A post_reach_backend worker -B -l info -P solo --scheduler django_celery_beat.schedulers:DatabaseScheduler

# Celery beat scheduler for periodic tasks
# beat: celery -A post_reach_backend beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
