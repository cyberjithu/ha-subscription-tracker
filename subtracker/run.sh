#!/usr/bin/env sh
set -e
cd /opt/subtracker
export SUBTRACKER_DATA=/data
alembic upgrade head
if python3 -c "import json,sys; sys.exit(0 if json.load(open('/data/options.json')).get('install_lovelace_card') else 1)" 2>/dev/null; then
  mkdir -p /homeassistant/www
  cp card/subtracker-card.js /homeassistant/www/subtracker-card.js
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8099
