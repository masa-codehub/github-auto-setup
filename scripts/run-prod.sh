#!/bin/bash
set -e

# 本番用: GunicornでDjangoアプリをWSGI経由で起動
exec gunicorn webapp_project.wsgi:application --bind 0.0.0.0:8000 --workers 3 --chdir /app/webapp
