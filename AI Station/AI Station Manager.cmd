@echo off
setlocal EnableExtensions

rem AI Station Windows launcher
rem Talks to the Ubuntu WSL distro and /opt/ai-station scripts.

set "WSL_DISTRO=Ubuntu"
set "AI_STATION_ROOT=/opt/ai-station"
set "ACTION_SCRIPT=%AI_STATION_ROOT%/scripts/ai-station-manager-action.sh"

:MENU
cls
echo ==========================================
echo           AI Station Manager
echo ==========================================
echo.
echo  1. Start AI Station
echo  2. Open Open WebUI
echo  3. Open SearXNG Search
echo  4. Open Gateway Health
echo.
echo  5. Stop Heavy LLM Models
echo  6. Stop AI Station
echo.
echo  7. Status
echo  8. Logs - Gateway
echo  9. Logs - Open WebUI
echo 10. Logs - Tika OCR
echo 11. Logs - General LLM
echo.
echo 12. Open Project in VS Code
echo 13. Open Project Folder
echo 14. Git Status
echo 15. Disk / Docker Usage
echo 16. Verify Stack
echo.
echo  0. Exit
echo.

set /p CHOICE=Select:

if "%CHOICE%"=="1" goto START
if "%CHOICE%"=="2" goto OPEN_WEBUI
if "%CHOICE%"=="3" goto OPEN_SEARCH
if "%CHOICE%"=="4" goto OPEN_GATEWAY
if "%CHOICE%"=="5" goto STOP_MODELS
if "%CHOICE%"=="6" goto STOP
if "%CHOICE%"=="7" goto STATUS
if "%CHOICE%"=="8" goto LOG_GATEWAY
if "%CHOICE%"=="9" goto LOG_WEBUI
if "%CHOICE%"=="10" goto LOG_TIKA
if "%CHOICE%"=="11" goto LOG_GENERAL
if "%CHOICE%"=="12" goto VSCODE
if "%CHOICE%"=="13" goto FOLDER
if "%CHOICE%"=="14" goto GIT
if "%CHOICE%"=="15" goto DISK
if "%CHOICE%"=="16" goto VERIFY
if "%CHOICE%"=="0" exit /b 0

goto MENU

:START
echo.
echo Starting AI Station via WSL...
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION_SCRIPT% start"
if errorlevel 1 (
  echo.
  echo START FAILED. Check Docker Desktop and WSL systemd.
)
echo.
pause
goto MENU

:OPEN_WEBUI
start "" "http://127.0.0.1:3000"
goto MENU

:OPEN_SEARCH
start "" "http://127.0.0.1:8889"
goto MENU

:OPEN_GATEWAY
start "" "http://127.0.0.1:8888/health"
goto MENU

:STOP_MODELS
echo.
echo Stopping heavy LLM models...
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION_SCRIPT% stop-heavy-models"
echo.
pause
goto MENU

:STOP
echo.
echo Stopping AI Station...
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION_SCRIPT% stop"
if errorlevel 1 (
  echo.
  echo STOP FAILED.
)
echo.
pause
goto MENU

:STATUS
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION_SCRIPT% status"
echo.
pause
goto MENU

:LOG_GATEWAY
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION_SCRIPT% logs-gateway"
echo.
pause
goto MENU

:LOG_WEBUI
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION_SCRIPT% logs-webui"
echo.
pause
goto MENU

:LOG_TIKA
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION_SCRIPT% logs-tika"
echo.
pause
goto MENU

:LOG_GENERAL
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION_SCRIPT% logs-general"
echo.
pause
goto MENU

:VSCODE
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION_SCRIPT% vscode"
echo.
pause
goto MENU

:FOLDER
explorer.exe "\\wsl.localhost\Ubuntu\opt\ai-station"
goto MENU

:GIT
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION_SCRIPT% git"
echo.
pause
goto MENU

:DISK
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION_SCRIPT% disk"
echo.
pause
goto MENU

:VERIFY
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION_SCRIPT% verify"
echo.
pause
goto MENU
