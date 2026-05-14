@echo off
setlocal
cd /d "%~dp0"

REM --- Create venv on first run ---
if not exist ".venv\Scripts\python.exe" (
    echo [setup] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [error] Failed to create venv. Make sure Python 3.10+ is installed and on PATH.
        pause
        exit /b 1
    )
)

REM --- Install / update dependencies ---
if not exist ".venv\.deps_installed" (
    echo [setup] Installing dependencies...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [error] pip install failed.
        pause
        exit /b 1
    )
    echo done > ".venv\.deps_installed"
)

REM --- Create empty .env if missing (dashboard will collect the key on first load) ---
if not exist ".env" (
    > .env echo GEMINI_API_KEY=
)

REM --- Launch ---
echo.
echo [run] Starting server at http://127.0.0.1:8000
echo [run] First time? The dashboard will prompt for your Gemini API key.
echo [run] Press Ctrl+C to stop.
echo.
start "" http://127.0.0.1:8000
".venv\Scripts\python.exe" main.py

endlocal
