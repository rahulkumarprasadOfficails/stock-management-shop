#!/usr/bin/env bash
set -o errexit
python -m pip install -r requirements.txt
python manage.py ensure_control_schema
python manage.py migrate --noinput
python manage.py collectstatic --noinput
