@echo off
rem gitteam web UI launcher (Windows). Double-click to start; the browser opens automatically.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [gitteam] First run: creating a Python virtual environment and installing dependencies...
    python -m venv .venv || goto :error
    ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
    ".venv\Scripts\python.exe" -m pip install --quiet -e ".[ui]" || goto :error
)

echo [gitteam] Starting the web UI. If the browser does not open, visit http://localhost:8501
".venv\Scripts\python.exe" -m streamlit run ui\streamlit_app.py --server.address localhost
goto :eof

:error
echo [gitteam] Setup failed. Please install Python 3.11 or newer from https://www.python.org/ and try again.
pause
exit /b 1
