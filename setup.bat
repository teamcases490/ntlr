@echo off
echo ============================================
echo INTEGRATED NTLR PIPELINE - SETUP
echo ============================================
echo.

echo [1/4] Checking Python installation...
python --version
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.8+
    pause
    exit /b 1
)
echo.

echo [2/4] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo.

echo [3/4] Checking configuration...
if not exist .env (
    echo WARNING: .env file not found
    echo Creating .env from template...
    copy .env.template .env
    echo.
    echo IMPORTANT: Edit .env and add your API keys!
    echo.
)

if not exist credentials.json (
    echo WARNING: credentials.json not found
    echo Please add your Google Earth Engine service account JSON file
    echo.
)
echo.

echo [4/4] Creating directories...
if not exist cache mkdir cache
if not exist logs mkdir logs
if not exist downloads mkdir downloads
if not exist downloads\current mkdir downloads\current
if not exist downloads\historical mkdir downloads\historical
echo.

echo ============================================
echo SETUP COMPLETE!
echo ============================================
echo.
echo Next steps:
echo 1. Edit .env and add your GOOGLE_API_KEY
echo 2. Add credentials.json (GEE service account)
echo 3. Run: earthengine authenticate
echo 4. Run: python main.py
echo.
pause
