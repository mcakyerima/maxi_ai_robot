@echo off
REM Maxi AI Robot Startup Script for Windows
REM This script activates the virtual environment and starts the app

echo.
echo ========================================
echo  Starting Maxi AI Robot
echo ========================================
echo.

REM Check if we're in the right directory
if not exist "main.py" (
    echo ERROR: Please run this script from the project root directory!
    echo Current directory: %CD%
    pause
    exit /b 1
)

REM Activate virtual environment if it exists
if exist "venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo WARNING: Virtual environment not found at venv\
    echo Make sure you have created a virtual environment with: python -m venv venv
    echo.
)

REM Start the application
echo.
echo Starting Maxi AI Robot...
echo.
python start.py

REM If the script exits with error, keep window open
if %ERRORLEVEL% neq 0 (
    echo.
    echo ========================================
    echo  ERROR: Application failed to start
    echo ========================================
    echo.
    pause
)
