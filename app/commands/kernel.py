from app.commands.example_command import ExampleCommand

# Register commands and their cron expressions.
# Trigger all due commands with: python manage.py schedule:run
# Recommended OS cron entry (runs every minute, Laravel-style):
#   * * * * * cd /path/to/project && \
#       venv/bin/python manage.py schedule:run >> /var/log/scheduler.log 2>&1

SCHEDULE: list[dict] = [
    # {"command": ExampleCommand, "cron": "0 * * * *"},   # every hour
    # {"command": ExampleCommand, "cron": "0 0 * * *"},   # daily at midnight
    # {"command": ExampleCommand, "cron": "*/5 * * * *"}, # every 5 minutes
]

# All commands available for manual execution via `python manage.py run <name>`.
COMMANDS: list[type] = [
    ExampleCommand,
]
