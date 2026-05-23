@echo off
setlocal

set "ROOT=%~dp0"
set "FRONTEND_DIR=%ROOT%visualization_site"
set "BACKEND_PORT=8765"
set "FRONTEND_PORT=5173"
set "SITE_URL=http://127.0.0.1:%FRONTEND_PORT%/"

echo.
echo ================================================
echo  Marketing Sandbox Website Launcher
echo ================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found in PATH.
  echo Please install Python or add it to PATH, then run this file again.
  pause
  exit /b 1
)

where npm.cmd >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm.cmd was not found in PATH.
  echo Please install Node.js, then run this file again.
  pause
  exit /b 1
)

if not exist "%FRONTEND_DIR%\package.json" (
  echo [ERROR] Cannot find visualization_site\package.json.
  echo Please run this launcher from the project root folder.
  pause
  exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules\" (
  echo [INFO] Frontend dependencies are missing. Installing now...
  pushd "%FRONTEND_DIR%"
  call npm.cmd install
  if errorlevel 1 (
    popd
    echo [ERROR] npm install failed.
    pause
    exit /b 1
  )
  popd
)

echo [INFO] Starting Python backend on http://127.0.0.1:%BACKEND_PORT%
start "Marketing Sandbox Backend" cmd /k "cd /d ""%ROOT%"" && python -m marketing_sandbox.web_server --host 127.0.0.1 --port %BACKEND_PORT%"

timeout /t 2 /nobreak >nul

echo [INFO] Starting Vite frontend on %SITE_URL%
start "Marketing Sandbox Frontend" cmd /k "cd /d ""%FRONTEND_DIR%"" && npm.cmd run dev -- --port %FRONTEND_PORT%"

echo [INFO] Waiting for the website to become available...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(35); do { try { $r=Invoke-WebRequest -UseBasicParsing '%SITE_URL%' -TimeoutSec 1; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); exit 1"

if errorlevel 1 (
  echo [WARN] The website did not answer within 35 seconds. Opening it anyway.
) else (
  echo [INFO] Website is ready.
)

start "" "%SITE_URL%"

echo.
echo [DONE] Browser opened: %SITE_URL%
echo Keep the Backend and Frontend windows open while using the site.
echo Close those two windows when you want to stop the sandbox.
echo.
pause
