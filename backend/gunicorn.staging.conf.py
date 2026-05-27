bind = "0.0.0.0:8000"

# Virtech staging: VM petita, configuració estable i sense autoreload
workers = 2
worker_class = "sync"

reload = False

timeout = 120
graceful_timeout = 30
keepalive = 5

accesslog = "-"
errorlog = "-"
loglevel = "info"
