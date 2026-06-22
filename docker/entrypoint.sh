#!/bin/sh
set -e

echo "→ Running migrations..."
alembic upgrade head

echo "→ Seeding database..."
python seed.py

echo "→ Starting application..."
exec python run.py
