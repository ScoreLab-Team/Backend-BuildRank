# Gunicorn configuration - development
bind = "0.0.0.0:8000"

# 2 workers para desarrollo; en producción usar (2 * CPU) + 1
workers = 2
worker_class = "sync"

# Recarga automática cuando cambia el código (solo para desarrollo)
reload = True
reload_extra_files = []

timeout = 120
graceful_timeout = 30
keepalive = 5

# Logs a stdout/stderr (Docker los captura)
accesslog = "-"
errorlog = "-"
loglevel = "info"
