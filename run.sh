#!/usr/bin/env bash
# Launch Pass Manager, creating the virtualenv on first run.
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "First run: creating virtualenv and installing dependencies..."
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
fi

exec .venv/bin/python main.py
