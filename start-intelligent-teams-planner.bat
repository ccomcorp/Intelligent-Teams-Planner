@echo off
REM Intelligent Teams Planner - Windows startup script
setlocal enabledelayedexpansion

REM Colors for Windows (limited support)
set "RED=[91m"
set "GREEN=[92m"
set "YELLOW=[93m"
set "BLUE=[94m"
set "PURPLE=[95m"
set "NC=[0m"

REM Script directory
set "SCRIPT_DIR=%~dp0"
set "PYTHON_SCRIPT=%SCRIPT_DIR%scripts\intelligent-startup.py"

REM Function to print colored output (Windows 10+ only)
goto :check_windows_version

:print_color
set "color=%~1"
set "message=%~2"
echo %color%%message%%NC%
goto :eof

:check_windows_version
for /f "tokens=4-5 delims=. " %%i in ('ver') do set VERSION=%%i.%%j
if "%VERSION%" geq "10.0" (
    REM Enable ANSI color support on Windows 10+
    reg add HKCU\Console /v VirtualTerminalLevel /t REG_DWORD /d 1 /f >nul 2>&1
)

:header
echo.
echo %PURPLE%
echo ^╔══════════════════════════════════════════════════════════════^╗
echo ^║               Intelligent Teams Planner                     ^║
echo ^║                  Smart Startup System                       ^║
echo ^╚══════════════════════════════════════════════════════════════^╝
echo %NC%

REM Parse command line arguments
set "action=start"
set "target_service="

:parse_args
if "%~1"=="" goto :end_parse
if "%~1"=="-h" goto :show_help
if "%~1"=="--help" goto :show_help
if "%~1"=="-c" set "action=check" & shift & goto :parse_args
if "%~1"=="--check" set "action=check" & shift & goto :parse_args
if "%~1"=="-s" set "action=stop" & shift & goto :parse_args
if "%~1"=="--stop" set "action=stop" & shift & goto :parse_args
if "%~1"=="-r" set "action=restart" & shift & goto :parse_args
if "%~1"=="--restart" set "action=restart" & shift & goto :parse_args
if "%~1"=="--cleanup" set "action=cleanup" & shift & goto :parse_args
if "%~1"=="--status" set "action=status" & shift & goto :parse_args
if "%~1"=="--logs" (
    set "action=logs"
    shift
    if not "%~1"=="" (
        set "target_service=%~1"
        shift
    ) else (
        call :print_color "%RED%" "❌ --logs requires a service name"
        exit /b 1
    )
    goto :parse_args
)
call :print_color "%RED%" "❌ Unknown option: %~1"
goto :show_help

:end_parse

REM Execute action
if "%action%"=="check" goto :check_requirements
if "%action%"=="stop" goto :stop_services
if "%action%"=="restart" goto :restart_services
if "%action%"=="cleanup" goto :cleanup_services
if "%action%"=="status" goto :show_status
if "%action%"=="logs" goto :show_logs
if "%action%"=="start" goto :start_services

:show_help
echo.
call :print_color "%GREEN%" "Intelligent Teams Planner - Startup Script"
echo.
call :print_color "%BLUE%" "Usage:"
echo     %~nx0 [OPTIONS]
echo.
call :print_color "%BLUE%" "Options:"
echo     -h, --help              Show this help message
echo     -c, --check             Only check requirements (don't start services)
echo     -s, --stop              Stop all services
echo     -r, --restart           Restart all services
echo     --cleanup               Clean up Docker resources and stop services
echo     --status                Show current service status
echo     --logs ^<service^>        Show logs for specific service
echo.
call :print_color "%BLUE%" "Examples:"
echo     %~nx0                   Start all services with intelligent monitoring
echo     %~nx0 --check           Check if system requirements are met
echo     %~nx0 --restart         Stop and restart all services
echo     %~nx0 --logs postgres   Show PostgreSQL logs
echo.
call :print_color "%BLUE%" "Services:"
echo     Infrastructure: postgres, redis, neo4j
echo     Applications:   planner-mcp-server, mcpo-proxy, teams-bot, rag-service
echo.
exit /b 0

:check_requirements
call :print_color "%BLUE%" "🔍 Checking system requirements for Windows..."

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    py --version >nul 2>&1
    if errorlevel 1 (
        call :print_color "%RED%" "❌ Python not found!"
        call :print_color "%YELLOW%" "Please install Python 3.6+ from https://python.org"
        call :print_color "%YELLOW%" "Make sure to check 'Add Python to PATH' during installation"
        exit /b 1
    ) else (
        for /f "tokens=2" %%i in ('py --version 2^>^&1') do set PYTHON_VERSION=%%i
        call :print_color "%GREEN%" "✅ Found Python: !PYTHON_VERSION! (py)"
        set "PYTHON_CMD=py"
    )
) else (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
    call :print_color "%GREEN%" "✅ Found Python: !PYTHON_VERSION! (python)"
    set "PYTHON_CMD=python"
)

REM Check Docker
docker --version >nul 2>&1
if errorlevel 1 (
    call :print_color "%RED%" "❌ Docker not found!"
    call :print_color "%YELLOW%" "Please install Docker Desktop from https://docker.com"
    exit /b 1
) else (
    for /f "tokens=3" %%i in ('docker --version 2^>^&1') do set DOCKER_VERSION=%%i
    call :print_color "%GREEN%" "✅ Found Docker: !DOCKER_VERSION!"
)

REM Check Docker daemon
docker ps >nul 2>&1
if errorlevel 1 (
    call :print_color "%RED%" "❌ Docker daemon not running!"
    call :print_color "%YELLOW%" "Please start Docker Desktop"
    exit /b 1
)

REM Check Docker Compose
docker compose version >nul 2>&1
if errorlevel 1 (
    docker-compose --version >nul 2>&1
    if errorlevel 1 (
        call :print_color "%RED%" "❌ Docker Compose not found!"
        call :print_color "%YELLOW%" "Please install Docker Compose (usually included with Docker Desktop)"
        exit /b 1
    ) else (
        for /f "tokens=3" %%i in ('docker-compose --version 2^>^&1') do set COMPOSE_VERSION=%%i
        call :print_color "%GREEN%" "✅ Found Docker Compose: !COMPOSE_VERSION!"
    )
) else (
    for /f "tokens=4" %%i in ('docker compose version 2^>^&1') do set COMPOSE_VERSION=%%i
    call :print_color "%GREEN%" "✅ Found Docker Compose: !COMPOSE_VERSION!"
)

if "%action%"=="check" exit /b 0
goto :check_project_directory

:check_project_directory
if not exist "docker-compose.simple.yml" (
    call :print_color "%RED%" "❌ docker-compose.simple.yml not found!"
    call :print_color "%YELLOW%" "Please run this script from the project root directory"
    exit /b 1
)

if not exist "%PYTHON_SCRIPT%" (
    call :print_color "%RED%" "❌ Python startup script not found at: %PYTHON_SCRIPT%"
    exit /b 1
)

goto :setup_directories

:setup_directories
if not exist "scripts" (
    mkdir "scripts"
    call :print_color "%GREEN%" "✅ Created directory: scripts"
)

if not exist "logs" (
    mkdir "logs"
    call :print_color "%GREEN%" "✅ Created directory: logs"
)

goto :continue_startup

:stop_services
call :check_project_directory
if errorlevel 1 exit /b 1

call :print_color "%YELLOW%" "🛑 Stopping services..."
docker compose -f docker-compose.simple.yml down --remove-orphans
call :print_color "%GREEN%" "✅ Services stopped"

if "%action%"=="stop" exit /b 0
goto :eof

:restart_services
call :stop_services
set "action=start"
goto :continue_startup

:cleanup_services
call :stop_services
call :print_color "%YELLOW%" "🧹 Cleaning up Docker resources..."

REM Remove stopped containers
for /f %%i in ('docker ps -aq --filter "status=exited" 2^>nul') do (
    docker rm %%i >nul 2>&1
)

REM Clean up unused networks and volumes
docker network prune -f >nul 2>&1
docker volume prune -f >nul 2>&1

call :print_color "%GREEN%" "✅ Docker cleanup completed"
exit /b 0

:show_status
call :check_project_directory
if errorlevel 1 exit /b 1

call :print_color "%BLUE%" "📊 Current Service Status:"
docker compose -f docker-compose.simple.yml ps
exit /b 0

:show_logs
call :check_project_directory
if errorlevel 1 exit /b 1

if "%target_service%"=="" (
    call :print_color "%RED%" "❌ Service name required for --logs"
    exit /b 1
)

call :print_color "%BLUE%" "📋 Logs for service: %target_service%"
docker compose -f docker-compose.simple.yml logs --tail=50 -f "%target_service%"
exit /b 0

:continue_startup
if "%action%"=="restart" call :stop_services

:start_services
call :print_color "%GREEN%" "🚀 Starting Intelligent Teams Planner with Python orchestrator..."
call :print_color "%BLUE%" "📝 Logs will be written to: intelligent-startup.log"
call :print_color "%YELLOW%" "⏳ This may take several minutes for first-time setup..."

REM Start the Python orchestrator
%PYTHON_CMD% "%PYTHON_SCRIPT%"

exit /b %errorlevel%