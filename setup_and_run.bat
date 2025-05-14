@echo off

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not added to PATH.
    echo Please install Python from https://www.python.org/downloads/ and ensure it is added to your system PATH.
    pause
    exit /b 1
)

REM Check if pip is available
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo pip is not available. Please ensure pip is installed with your Python distribution.
    echo Often, it can be installed by re-running the Python installer and selecting pip, or using: python -m ensurepip --upgrade
    pause
    exit /b 1
)

REM Define the virtual environment directory
set VENV_DIR=venv

REM Create virtual environment if it doesn't exist
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo Creating virtual environment in %VENV_DIR%...
    python -m venv %VENV_DIR%
    if errorlevel 1 (
        echo Failed to create virtual environment. Please check your Python venv module.
        pause
        exit /b 1
    )
)

echo Activating virtual environment...
call "%VENV_DIR%\Scripts\activate.bat"

echo Installing dependencies from requirements.txt...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install dependencies. Please check requirements.txt and your internet connection.
    pause
    exit /b 1
)

echo Starting the Dash application...
python dash_app.py

REM Deactivate virtual environment (optional, as closing cmd window will handle this)
REM call "%VENV_DIR%\Scripts\deactivate.bat"

echo Application closed.
pause 