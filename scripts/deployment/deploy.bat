@echo off
REM Intelligent Teams Planner v2.0 - Windows Deployment Script

setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "PYTHON_SCRIPT=%SCRIPT_DIR%scripts\smart-deploy.py"

REM Check if Python is available
python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo ❌ Python is not installed or not in PATH
    exit /b 1
)

REM Check if requests module is available for health checks
python -c "import requests" >nul 2>&1
if !errorlevel! neq 0 (
    echo 📦 Installing requests module for health checks...
    python -m pip install requests
)

REM Run the smart deployment script
echo 🚀 Starting Intelligent Teams Planner Smart Deployment...
python "%PYTHON_SCRIPT%" %*