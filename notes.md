# Important Notes

## Instagram login url
https://www.instagram.com/oauth/authorize
?client_id=2492724647730358
&redirect_uri=https%3A%2F%2Fapp.streamlivr.com%2Foauth%2Finstagram
&response_type=code
&scope=instagram_business_basic%2Cinstagram_business_content_publish%2Cinstagram_business_manage_insights
&enable_fb_login=0
&force_authentication=1

## Start celery worker
celery -A post_reach_backend worker -l info  -P solo

## Celery beat
celery -A post_reach_backend beat -l  info --scheduler django_celery_beat.schedulers:DatabaseScheduler
