import os

# Render free-tier deploy notes:
# - The master process must bind to $PORT *before* any worker imports app.py,
#   otherwise Render's port-scan times out (the "Port scan timeout reached"
#   error). Keeping preload_app=False ensures the master only sets up the
#   socket and forks; the heavy imports (playwright via spareroom_scraper,
#   pdfkit, jinja2, etc.) run inside the worker after the port is already
#   listening.
# - graceful_timeout < timeout so a stuck worker is killed and replaced
#   rather than dragging the whole service down.
bind = f"0.0.0.0:{os.environ.get('PORT', 8000)}"
workers = 1
threads = 2
timeout = 180
graceful_timeout = 30
preload_app = False
# Log to stdout so the lines show up in the Render dashboard.
accesslog = "-"
errorlog = "-"
loglevel = "info"
