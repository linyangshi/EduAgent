# gunicorn_config.py
bind = "0.0.0.0:5029"
workers = 4  # 进程数，建议设置为 CPU核心数 * 2 + 1
threads = 2  # 每个worker的线程数
worker_class = "gthread"  # 使用线程模式
timeout = 120
keepalive = 5
max_requests = 1000
max_requests_jitter = 100