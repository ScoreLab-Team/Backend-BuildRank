# config/celery.py
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('buildrank')

# Llegeix configuració des de Django settings amb prefix CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# Descobreix tasques automàticament de totes les apps
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')