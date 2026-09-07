#!/usr/bin/env sh
# gitteam web UI launcher (macOS / Linux). Run: ./start_ui.sh
set -e
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo "[gitteam] First run: creating a Python virtual environment and installing dependencies..."
    python3 -m venv .venv
    .venv/bin/python -m pip install --quiet --upgrade pip
    .venv/bin/python -m pip install --quiet -e ".[ui]"
fi

echo "[gitteam] Starting the web UI. If the browser does not open, visit http://localhost:8501"
exec .venv/bin/python -m streamlit run ui/streamlit_app.py --server.address localhost
