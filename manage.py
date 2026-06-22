import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()

from app.commands.kernel import COMMANDS, SCHEDULE
from app.seeders.kernel import SEEDERS


def _find(name: str):
    for cls in COMMANDS:
        if cls.name == name:
            return cls
    return None


def cmd_list():
    print(f"{'Name':<30} Description")
    print("-" * 60)
    for cls in COMMANDS:
        print(f"{cls.name:<30} {cls.description}")


def cmd_run(name: str):
    cls = _find(name)
    if cls is None:
        print(f"Command '{name}' not found. Run `python manage.py list` to see available commands.")
        sys.exit(1)
    asyncio.run(cls().run())


def cmd_schedule_run():
    if not SCHEDULE:
        print("No commands registered in SCHEDULE (app/commands/kernel.py).")
        return
    try:
        from datetime import datetime

        from croniter import croniter

        now = datetime.now()
        ran = 0
        for entry in SCHEDULE:
            if croniter.match(entry["cron"], now):
                print(f"→ Running {entry['command'].name}")
                asyncio.run(entry["command"]().run())
                ran += 1
        if ran == 0:
            print("No commands due right now.")
    except ImportError:
        print("croniter not installed — running all scheduled commands unconditionally.")
        print("To enable cron expressions: pip install croniter")
        for entry in SCHEDULE:
            asyncio.run(entry["command"]().run())


def _find_seeder(name: str):
    for cls in SEEDERS:
        if cls.name == name:
            return cls
    return None


def seed_list():
    print(f"{'Name':<30} Description")
    print("-" * 60)
    for cls in SEEDERS:
        print(f"{cls.name:<30} {cls.description}")


def seed_run(name: str | None = None):
    if name:
        cls = _find_seeder(name)
        if cls is None:
            print(
                f"Seeder '{name}' not found. "
                "Run `python manage.py seed:list` to see available seeders."
            )
            sys.exit(1)
        asyncio.run(cls().execute())
    else:
        from seed import run_all

        asyncio.run(run_all())


def main():
    args = sys.argv[1:]
    if not args or args[0] == "list":
        cmd_list()
    elif args[0] == "schedule:run":
        cmd_schedule_run()
    elif args[0] == "run" and len(args) == 2:
        cmd_run(args[1])
    elif args[0] == "seed:list":
        seed_list()
    elif args[0] == "seed:run" and len(args) == 1:
        seed_run()
    elif args[0] == "seed:run" and len(args) == 2:
        seed_run(args[1])
    else:
        print("Usage:")
        print("  python manage.py list")
        print("  python manage.py run <command-name>")
        print("  python manage.py schedule:run")
        print("  python manage.py seed:list")
        print("  python manage.py seed:run")
        print("  python manage.py seed:run <seeder-name>")
        sys.exit(1)


if __name__ == "__main__":
    main()
