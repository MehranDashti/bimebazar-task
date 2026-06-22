# Register commands and their cron expressions.
# Trigger all due commands with: python manage.py schedule:run
# Recommended OS cron entry (runs every minute, Laravel-style):
#   * * * * * cd /path/to/project && \
#       venv/bin/python manage.py schedule:run >> /var/log/scheduler.log 2>&1

SCHEDULE: list[dict] = []

# All commands available for manual execution via `python manage.py run <name>`.
COMMANDS: list[type] = []
