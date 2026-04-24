@echo off
setlocal enabledelayedexpansion

echo -------------------------------------------------------
echo  NTLR Pipeline - Environment Setup
echo -------------------------------------------------------

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.9+ and add to PATH.
    pause
    exit /b 1
)

:: Create virtual environment
if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: Activate
call venv\Scripts\activate.bat

:: UTF-8 support
set PYTHONIOENCODING=utf-8

:: Install dependencies
if exist "requirements.txt" (
    echo Upgrading pip...
    pip install --upgrade pip -q

    echo Installing dependencies...
    pip install -r requirements.txt

    if %errorlevel% neq 0 (
        echo [ERROR] Dependency installation failed.
        pause
        exit /b 1
    )
) else (
    echo [ERROR] requirements.txt not found.
    pause
    exit /b 1
)

echo.
echo -------------------------------------------------------
echo  Setup complete!
echo -------------------------------------------------------
echo.
echo  Steps to run:
echo.
echo  1. Activate environment:
echo       venv\Scripts\activate
echo.
echo  2. Authenticate Earth Engine (first time only):
echo       python -c "import ee; ee.Authenticate()"
echo.
echo  3. Run pipeline:
echo       python ntlr_pipeline.py
echo.
echo -------------------------------------------------------
pause