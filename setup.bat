@echo off
title NTLR v3 PIPELINE SETUP

echo ============================================
echo NTLR v3 PIPELINE - SETUP
echo ============================================
echo.

REM =========================================================
REM [1/6] CHECK PYTHON
REM =========================================================
echo [1/6] Checking Python installation...
python --version
if errorlevel 1 (
    echo ERROR: Python 3.8+ is required but not installed.
    pause
    exit /b 1
)
echo.

REM =========================================================
REM [2/6] CREATE VIRTUAL ENVIRONMENT
REM =========================================================
echo [2/6] Creating virtual environment...
if exist venv (
    echo Virtual environment already exists. Skipping...
) else (
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Virtual environment created successfully!
)
echo.

REM =========================================================
REM [3/6] ACTIVATE VENV
REM =========================================================
echo [3/6] Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment.
    pause
    exit /b 1
)
echo Virtual environment activated!
echo.

REM =========================================================
REM [4/6] INSTALL DEPENDENCIES
REM =========================================================
echo [4/6] Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Dependency installation failed.
    pause
    exit /b 1
)
echo Dependencies installed successfully!
echo.

REM =========================================================
REM [5/6] CHECK GOOGLE AUTH FILES
REM =========================================================
echo [5/6] Checking Google authentication setup...

if not exist client_secrets.json (
    echo WARNING: client_secrets.json NOT found.
    echo.
    echo Required for first-time Google Drive OAuth authentication.
    echo Download OAuth Desktop credentials from Google Cloud Console
    echo and place them in project root as:
    echo client_secrets.json
    echo.
) else (
    echo client_secrets.json found.
)

if exist credentials.json (
    echo credentials.json found. Silent login enabled.
) else (
    echo credentials.json not found yet.
    echo First pipeline run will open browser for Google login.
)

echo.

REM =========================================================
REM [6/6] CREATE PROJECT FOLDERS
REM =========================================================
echo [6/6] Creating required directories...

if not exist data mkdir data
if not exist result mkdir result
if not exist versions mkdir versions
if not exist utils mkdir utils
if not exist logs mkdir logs

echo Directories ready!
echo.

REM =========================================================
REM FINAL STATUS
REM =========================================================
echo ============================================
echo NTLR V3 SETUP COMPLETE!
echo ============================================
echo.
echo Project folders:
echo   data\      - Extracted + enriched datasets
echo   result\    - Version outputs (result_v3.csv, result_v2.csv)
echo   versions\  - Logic versions
echo   utils\     - Shared loaders/helpers
echo.
echo Next Steps:
echo.
echo 1. Add client_secrets.json to project root
echo 2. Run extractor:
echo      python ntlr_pipeline.py
echo.
echo    First run:
echo      Browser OAuth
echo    Later runs:
echo      Silent login via credentials.json
echo.
echo 3. Run Version 3 logic:
echo      python versions\ntlr_v3.py
echo.
echo To activate virtual environment later:
echo   venv\Scripts\activate
echo.
pause