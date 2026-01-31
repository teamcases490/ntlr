@echo off
echo ============================================
echo NTLR PIPELINE - SETUP
echo ============================================
echo.

echo [1/5] Checking Python installation...
python --version
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.8+
    pause
    exit /b 1
)
echo.

echo [2/5] Creating virtual environment...
if exist venv (
    echo Virtual environment already exists, skipping creation...
) else (
    echo Creating new virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
    echo Virtual environment created successfully!
)
echo.

echo [3/5] Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment
    pause
    exit /b 1
)
echo Virtual environment activated!
echo.

echo [4/5] Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo.

echo [5/5] Checking configuration...
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

echo Creating directories...
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
echo Virtual environment is ready at: venv\
echo.
echo Next steps:
echo 1. Edit .env and add your GOOGLE_API_KEY and GCS_BUCKET
echo 2. Add credentials.json (GEE service account)
echo 3. Activate venv: venv\Scripts\activate
echo 4. Authenticate GEE: earthengine authenticate
echo 5. Run pipeline: python main.py
echo.
echo To activate the virtual environment in future sessions:
echo   venv\Scripts\activate
echo.
pause
