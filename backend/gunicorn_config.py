import logging
import sys

# Gunicorn config
bind = "0.0.0.0:5000"
workers = 1
worker_class = "sync"
timeout = 120
keepalive = 5

# Logging configuration
accesslog = "-"  # stdout
errorlog = "-"   # stdout
loglevel = "debug"  # CRITICAL
capture_output = True
enable_stdio_inheritance = True

# Logger class to ensure proper formatting
logclass = "gunicorn.glogging.Logger"

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info(f"Worker spawned (pid: {worker.pid})")

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("="*80)
    server.log.info("🚀 MEDIFINDER GUNICORN SERVER READY")
    server.log.info("="*80)

def on_exit(server):
    """Called just before exiting Gunicorn."""
    server.log.info("Shutting down Medifinder server")
