bind = "0.0.0.0:8000"

# Para esta VM de staging con 1 CPU, 2 workers es razonable
workers = 2
worker_class = "sync"

# En staging NO queremos autoreload
reload = False

timeout = 120
graceful_timeout = 30
keepalive = 5

# Logs a stdout/stderr para verlos con Docker
accesslog = "-"
errorlog = "-"
loglevel = "info"