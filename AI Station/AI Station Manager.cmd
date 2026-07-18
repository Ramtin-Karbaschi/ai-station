@echo off
setlocal EnableExtensions

:MENU
cls
echo ==========================================
echo              AI Station Manager
echo ==========================================
echo.
echo  1. Start AI Station
echo  2. Open Open WebUI
echo  3. Open SearXNG Search
echo  4. Open Docling OCR UI
echo.
echo  5. Stop Heavy LLM Models
echo  6. Stop AI Station
echo.
echo  7. Status
echo  8. Logs - Gateway
echo  9. Logs - Open WebUI
echo 10. Logs - OCR Docling
echo.
echo 11. Open Project in VS Code
echo 12. Open Project Folder
echo 13. Git Status
echo 14. Disk / Docker Usage
echo 15. Verify Stack
echo.
echo  0. Exit
echo.

set /p CHOICE=Select:

if "%CHOICE%"=="1" goto START
if "%CHOICE%"=="2" goto OPEN_WEBUI
if "%CHOICE%"=="3" goto OPEN_SEARCH
if "%CHOICE%"=="4" goto OPEN_OCR
if "%CHOICE%"=="5" goto STOP_MODELS
if "%CHOICE%"=="6" goto STOP
if "%CHOICE%"=="7" goto STATUS
if "%CHOICE%"=="8" goto LOG_GATEWAY
if "%CHOICE%"=="9" goto LOG_WEBUI
if "%CHOICE%"=="10" goto LOG_OCR
if "%CHOICE%"=="11" goto VSCODE
if "%CHOICE%"=="12" goto FOLDER
if "%CHOICE%"=="13" goto GIT
if "%CHOICE%"=="14" goto DISK
if "%CHOICE%"=="15" goto VERIFY
if "%CHOICE%"=="0" exit /b 0

goto MENU

:START
wsl.exe -d Ubuntu -- bash -lc "/opt/ai-station/scripts/ai-station-manager-action.sh start"
pause
goto MENU

:OPEN_WEBUI
start "" "http://localhost:3000"
goto MENU

:OPEN_SEARCH
start "" "http://localhost:8889"
goto MENU

:OPEN_OCR
start "" "http://localhost:5001/ui"
goto MENU

:STOP_MODELS
wsl.exe -d Ubuntu -- bash -lc "/opt/ai-station/scripts/ai-station-manager-action.sh stop-heavy-models"
pause
goto MENU

:STOP
wsl.exe -d Ubuntu -- bash -lc "/opt/ai-station/scripts/ai-station-manager-action.sh stop"
pause
goto MENU

:STATUS
wsl.exe -d Ubuntu -- bash -lc "/opt/ai-station/scripts/ai-station-manager-action.sh status"
pause
goto MENU

:LOG_GATEWAY
wsl.exe -d Ubuntu -- bash -lc "/opt/ai-station/scripts/ai-station-manager-action.sh logs-gateway"
pause
goto MENU

:LOG_WEBUI
wsl.exe -d Ubuntu -- bash -lc "/opt/ai-station/scripts/ai-station-manager-action.sh logs-webui"
pause
goto MENU

:LOG_OCR
wsl.exe -d Ubuntu -- bash -lc "/opt/ai-station/scripts/ai-station-manager-action.sh logs-ocr"
pause
goto MENU

:VSCODE
wsl.exe -d Ubuntu -- bash -lc "/opt/ai-station/scripts/ai-station-manager-action.sh vscode"
pause
goto MENU

:FOLDER
explorer.exe "\\wsl.localhost\Ubuntu\opt\ai-station"
goto MENU

:GIT
wsl.exe -d Ubuntu -- bash -lc "/opt/ai-station/scripts/ai-station-manager-action.sh git"
pause
goto MENU

:DISK
wsl.exe -d Ubuntu -- bash -lc "/opt/ai-station/scripts/ai-station-manager-action.sh disk"
pause
goto MENU

:VERIFY
wsl.exe -d Ubuntu -- bash -lc "/opt/ai-station/scripts/ai-station-manager-action.sh verify"
pause
goto MENU
