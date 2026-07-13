#!/usr/bin/env bash
# Launch Pass Manager, installing dependencies for this user on first run.
set -e
cd "$(dirname "$0")"

if ! python3 -c "import PySide6, cryptography, argon2, secretstorage, pyotp" >/dev/null 2>&1; then
    echo "First run: installing dependencies..."
    python3 -m pip install --user --no-warn-script-location -r requirements.txt \
        || python3 -m pip install --user --break-system-packages --no-warn-script-location -r requirements.txt
fi

exec python3 main.py
