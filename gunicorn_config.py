"""
Gunicorn配置文件 - 生产环境WSGI服务器配置
"""
import os
import multiprocessing

# 绑定地址和端口
bind = f"0.0.0.0:{os.getenv('PORT', '3001')}"

# Worker进程数 (推荐: CPU核心数 * 2 + 1)
workers = multiprocessing.cpu_count() * 2 + 1

# Worker类型 (使用gevent支持异步)
worker_class = "sync"

# 每个worker的线程数
threads = 2

# Worker超时时间 (秒)
timeout = 120

# 保持连接时间 (秒)
keepalive = 5

# 最大请求数 (达到后重启worker,防止内存泄漏)
max_requests = 1000
max_requests_jitter = 50

# 日志配置
accesslog = "-"  # 输出到stdout
errorlog = "-"   # 输出到stderr
loglevel = "info"

# 进程名称
proc_name = "uniagent"

# 预加载应用
preload_app = True

# 重载配置文件时的行为
reload = os.getenv("DEBUG", "False").lower() == "true"
