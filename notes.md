# Important Notes

## Start celery worker
celery -A post_reach_backend worker -l info  -P solo

## Celery beat
celery -A post_reach_backend beat -l  info --scheduler django_celery_beat.schedulers:DatabaseScheduler

## Beat and worker
celery -A post_reach_backend worker -l info  -P solo --scheduler django_celery_beat.schedulers:DatabaseScheduler
