@echo off
setlocal DisableDelayedExpansion

:: ── MetaEduBase one-click dev startup (Windows) ─────────────────────────────

set "PROJECT_ROOT=%~dp0"
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "SERVER_DIR=%PROJECT_ROOT%\packages\server-python"
set "WEB_DIR=%PROJECT_ROOT%\packages\web"
set "DEPLOY_DIR=%PROJECT_ROOT%\deploy"
set "LOG_DIR=%PROJECT_ROOT%\.dev-logs"
set "VENV_PY=%SERVER_DIR%\.venv\Scripts\python.exe"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

if "%~1"=="" goto do_all
if "%~1"=="all" goto do_all
if "%~1"=="infra" goto do_infra
if "%~1"=="backend" goto do_backend
if "%~1"=="frontend" goto do_frontend
if "%~1"=="celery" goto do_celery
if "%~1"=="init-db" goto do_init_db
if "%~1"=="init-test-db" goto do_init_test_db
if "%~1"=="stop" goto do_stop
if "%~1"=="status" goto do_status
if "%~1"=="logs" goto do_logs
goto usage

:do_infra
    powershell -Command "Write-Host '[MetaEdu] Starting Docker infra (PostgreSQL + Redis + MinIO)...' -ForegroundColor Cyan"
    if not exist "%DEPLOY_DIR%\.env" copy "%DEPLOY_DIR%\.env.example" "%DEPLOY_DIR%\.env" >nul 2>&1
    docker compose -f "%DEPLOY_DIR%\docker-compose.dev.yml" up -d >nul 2>&1
    powershell -Command "Write-Host '[OK] Docker infra started' -ForegroundColor Green"
    exit /b 0

:do_backend
    curl -sf http://localhost:8000/api/v1/health >nul 2>&1
    if %errorlevel%==0 (
        powershell -Command "Write-Host '[MetaEdu] Backend already running, skip' -ForegroundColor DarkGray"
        goto backend_done
    )
    powershell -Command "Write-Host '[MetaEdu] Restarting backend...' -ForegroundColor Cyan"
    taskkill /f /im python.exe >nul 2>&1
    timeout /t 1 /nobreak >nul
    if not exist "%VENV_PY%" (
        powershell -Command "Write-Host '[MetaEdu] Creating Python venv...' -ForegroundColor Cyan"
        python -m venv "%SERVER_DIR%\.venv"
    )
    powershell -Command "Write-Host '[MetaEdu] Starting backend on port 8000...' -ForegroundColor Cyan"
    start /b "" "%VENV_PY%" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 > "%LOG_DIR%\backend.log" 2>&1
    for /l %%i in (1,1,20) do (
        curl -sf http://localhost:8000/api/v1/health >nul 2>&1
        if %errorlevel%==0 goto backend_ready
        timeout /t 1 /nobreak >nul
    )
    :backend_ready
    powershell -Command "Write-Host '[OK] Backend ready - http://localhost:8000' -ForegroundColor Green"
    :backend_done
    exit /b 0

:do_frontend
    curl -sf http://localhost:3000 >nul 2>&1
    if %errorlevel%==0 (
        powershell -Command "Write-Host '[MetaEdu] Frontend already running, skip' -ForegroundColor DarkGray"
        goto frontend_done
    )
    powershell -Command "Write-Host '[MetaEdu] Restarting frontend...' -ForegroundColor Cyan"
    taskkill /f /im node.exe >nul 2>&1
    timeout /t 1 /nobreak >nul
    if not exist "%WEB_DIR%\node_modules" (
        powershell -Command "Write-Host '[MetaEdu] Installing frontend deps...' -ForegroundColor Cyan"
        cd /d "%WEB_DIR%" && pnpm install >nul 2>&1
    )
    powershell -Command "Write-Host '[MetaEdu] Starting frontend on port 3000...' -ForegroundColor Cyan"
    start "" cmd /c "cd /d "%WEB_DIR%" && pnpm dev"
    for /l %%i in (1,1,20) do (
        curl -sf http://localhost:3000 >nul 2>&1
        if %errorlevel%==0 goto frontend_ready
        timeout /t 1 /nobreak >nul
    )
    :frontend_ready
    powershell -Command "Write-Host '[OK] Frontend ready - http://localhost:3000' -ForegroundColor Green"
    :frontend_done
    exit /b 0

:do_celery
    docker ps 2>nul | findstr "redis" >nul 2>&1
    if %errorlevel% neq 0 (
        powershell -Command "Write-Host '[WARN] Redis not running, skip Celery' -ForegroundColor Yellow"
        exit /b 0
    )
    if not exist "%VENV_PY%" (
        python -m venv "%SERVER_DIR%\.venv"
    )
    powershell -Command "Write-Host '[MetaEdu] Starting Celery Worker...' -ForegroundColor Cyan"
    start /b "" "%VENV_PY%" -m celery -A app.celery_app worker --loglevel=info --pool=solo > "%LOG_DIR%\celery.log" 2>&1
    powershell -Command "Write-Host '[OK] Celery Worker started' -ForegroundColor Green"
    exit /b 0

:do_init_db
    powershell -Command "Write-Host '[MetaEdu] Initializing dev database...' -ForegroundColor Cyan"
    call :do_infra
    cd /d "%SERVER_DIR%"
    if not exist "%VENV_PY%" (
        python -m venv .venv
    )
    "%VENV_PY%" -m pip install -e ".[dev,ai]" -q >nul 2>&1
    set ALLOW_DEFAULT_SEED=true
    "%VENV_PY%" -m app.shared.infrastructure.dev_setup
    powershell -Command "Write-Host '[OK] Dev database initialized' -ForegroundColor Green"
    exit /b 0

:do_init_test_db
    powershell -Command "Write-Host '[MetaEdu] Initializing test database...' -ForegroundColor Cyan"
    call :do_infra
    cd /d "%SERVER_DIR%"
    if not exist "%VENV_PY%" (
        python -m venv .venv
    )
    "%VENV_PY%" -m pip install -e ".[dev,ai]" -q >nul 2>&1
    "%VENV_PY%" -m app.shared.infrastructure.test_db_setup
    powershell -Command "Write-Host '[OK] Test database initialized' -ForegroundColor Green"
    exit /b 0

:do_stop
    powershell -Command "Write-Host '[MetaEdu] Stopping all services...' -ForegroundColor Cyan"
    taskkill /f /im python.exe >nul 2>&1
    taskkill /f /im node.exe >nul 2>&1
    docker compose -f "%DEPLOY_DIR%\docker-compose.dev.yml" down >nul 2>&1
    powershell -Command "Write-Host '[OK] All services stopped' -ForegroundColor Green"
    exit /b 0

:do_status
    powershell -Command ""
    powershell -Command "Write-Host '  MetaEduBase Status' -ForegroundColor White"
    powershell -Command "Write-Host '  ----------------------' -ForegroundColor White"

    docker ps 2>nul | findstr "postgres" >nul 2>&1
    if %errorlevel%==0 (
        powershell -Command "Write-Host '  PostgreSQL   running (localhost:5432)' -ForegroundColor Green"
    ) else (
        powershell -Command "Write-Host '  PostgreSQL   NOT running' -ForegroundColor Red"
    )

    docker ps 2>nul | findstr "redis" >nul 2>&1
    if %errorlevel%==0 (
        powershell -Command "Write-Host '  Redis        running (localhost:6379)' -ForegroundColor Green"
    ) else (
        powershell -Command "Write-Host '  Redis        NOT running' -ForegroundColor Red"
    )

    docker ps 2>nul | findstr "minio" >nul 2>&1
    if %errorlevel%==0 (
        powershell -Command "Write-Host '  MinIO        running (localhost:9000)' -ForegroundColor Green"
    ) else (
        powershell -Command "Write-Host '  MinIO        NOT running' -ForegroundColor Red"
    )

    curl -sf http://localhost:8000/api/v1/health >nul 2>&1
    if %errorlevel%==0 (
        powershell -Command "Write-Host '  Backend      running (localhost:8000)' -ForegroundColor Green"
    ) else (
        powershell -Command "Write-Host '  Backend      NOT running' -ForegroundColor Red"
    )

    curl -sf http://localhost:3000 >nul 2>&1
    if %errorlevel%==0 (
        powershell -Command "Write-Host '  Frontend     running (localhost:3000)' -ForegroundColor Green"
    ) else (
        curl -sf http://localhost:5173 >nul 2>&1
        if %errorlevel%==0 (
            powershell -Command "Write-Host '  Frontend     running (localhost:5173)' -ForegroundColor Green"
        ) else (
            powershell -Command "Write-Host '  Frontend     NOT running' -ForegroundColor Red"
        )
    )
    powershell -Command ""
    powershell -Command "Write-Host '  API Docs: http://localhost:8000/docs' -ForegroundColor White"
    powershell -Command "Write-Host '  Frontend:  http://localhost:3000' -ForegroundColor White"
    powershell -Command ""
    exit /b 0

:do_logs
    set "TARGET=%~2"
    if "%TARGET%"=="" set "TARGET=backend"
    if "%TARGET%"=="backend" (
        type "%LOG_DIR%\backend.log" 2>nul
    ) else if "%TARGET%"=="frontend" (
        type "%LOG_DIR%\frontend.log" 2>nul
    ) else if "%TARGET%"=="celery" (
        type "%LOG_DIR%\celery.log" 2>nul
    ) else (
        echo Usage: dev.bat logs [backend^|frontend^|celery]
    )
    exit /b 0

:do_all
    call :do_infra
    call :do_backend
    call :do_celery
    call :do_frontend
    call :do_status
    exit /b 0

:usage
    echo Usage: dev.bat [all^|infra^|backend^|frontend^|celery^|init-db^|init-test-db^|stop^|status^|logs]
    echo.
    echo   all         start all services
    echo   infra       start Docker infra only
    echo   backend     restart backend
    echo   frontend    restart frontend
    echo   celery      start Celery Worker
    echo   init-db     init dev database
    echo   init-test-db init test database
    echo   stop        stop all services
    echo   status      show service status
    echo   logs        show logs [backend^|frontend^|celery]
    exit /b 1
