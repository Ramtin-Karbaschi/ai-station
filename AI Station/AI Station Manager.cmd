@echo off
setlocal EnableExtensions

rem AI Station — unified Windows control panel
rem One entrypoint for platform, models, and application API keys.

set "WSL_DISTRO=Ubuntu"
set "ACTION=/opt/ai-station/scripts/ai-station-manager-action.sh"

:MENU
cls
echo ================================================
echo              AI Station Control Panel
echo ================================================
echo.
echo  --- Platform ---
echo   1. Start
echo   2. Stop
echo   3. Restart
echo   4. Status
echo   5. Verify
echo.
echo  --- Open UI ---
echo   6. Open WebUI          http://127.0.0.1:3000
echo   7. Open LiteLLM Admin  http://127.0.0.1:4000/ui
echo   8. Open API health     http://127.0.0.1:4000/health/liveliness
echo   9. Open SearXNG        http://127.0.0.1:8889
echo.
echo  --- Models ---
echo  10. List models / active profile
echo  11. Use model: general
echo  12. Use model: coder
echo  13. Use model: reasoning
echo  14. Use model: vision
echo  15. Stop heavy models
echo.
echo  --- Application API ---
echo  16. API info + project list
echo  17. Create project API key
echo  18. Show project
echo  19. Revoke project API key
echo  20. Open projects folder
echo.
echo  --- Account ---
echo  26. Reset Open WebUI password
echo.
echo  --- Ops ---
echo  21. Logs
echo  22. Backup
echo  23. Disk / Docker usage
echo  24. Open project in VS Code
echo  25. Git status
echo.
echo   0. Exit
echo.

set /p CHOICE=Select:

if "%CHOICE%"=="1" goto START
if "%CHOICE%"=="2" goto STOP
if "%CHOICE%"=="3" goto RESTART
if "%CHOICE%"=="4" goto STATUS
if "%CHOICE%"=="5" goto VERIFY
if "%CHOICE%"=="6" goto OPEN_WEBUI
if "%CHOICE%"=="7" goto OPEN_LITELLM
if "%CHOICE%"=="8" goto OPEN_API_HEALTH
if "%CHOICE%"=="9" goto OPEN_SEARCH
if "%CHOICE%"=="10" goto MODELS_LIST
if "%CHOICE%"=="11" goto MODEL_GENERAL
if "%CHOICE%"=="12" goto MODEL_CODER
if "%CHOICE%"=="13" goto MODEL_REASONING
if "%CHOICE%"=="14" goto MODEL_VISION
if "%CHOICE%"=="15" goto STOP_MODELS
if "%CHOICE%"=="16" goto API_INFO
if "%CHOICE%"=="17" goto PROJECT_CREATE
if "%CHOICE%"=="18" goto PROJECT_SHOW
if "%CHOICE%"=="19" goto PROJECT_REVOKE
if "%CHOICE%"=="20" goto PROJECTS_FOLDER
if "%CHOICE%"=="21" goto LOGS
if "%CHOICE%"=="22" goto BACKUP
if "%CHOICE%"=="23" goto DISK
if "%CHOICE%"=="24" goto VSCODE
if "%CHOICE%"=="25" goto GIT
if "%CHOICE%"=="26" goto RESET_WEBUI_PASSWORD
if "%CHOICE%"=="0" exit /b 0
goto MENU

:START
echo.
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION% start"
if errorlevel 1 echo START FAILED. Check Docker Desktop and WSL systemd.
echo.
pause
goto MENU

:STOP
echo.
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION% stop"
echo.
pause
goto MENU

:RESTART
echo.
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION% restart"
echo.
pause
goto MENU

:STATUS
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION% status"
echo.
pause
goto MENU

:VERIFY
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION% verify"
echo.
pause
goto MENU

:OPEN_WEBUI
start "" "http://127.0.0.1:3000"
goto MENU

:OPEN_LITELLM
start "" "http://127.0.0.1:4000/ui"
goto MENU

:OPEN_API_HEALTH
start "" "http://127.0.0.1:4000/health/liveliness"
goto MENU

:OPEN_SEARCH
start "" "http://127.0.0.1:8889"
goto MENU

:MODELS_LIST
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION% models-list"
echo.
pause
goto MENU

:MODEL_GENERAL
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION% model-use general"
echo.
pause
goto MENU

:MODEL_CODER
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION% model-use coder"
echo.
pause
goto MENU

:MODEL_REASONING
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION% model-use reasoning"
echo.
pause
goto MENU

:MODEL_VISION
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION% model-use vision"
echo.
pause
goto MENU

:STOP_MODELS
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION% stop-heavy-models"
echo.
pause
goto MENU

:API_INFO
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION% api-info"
echo.
pause
goto MENU

:PROJECT_CREATE
echo.
set /p PROJECT_ID=Project id (e.g. inventory-api): 
if "%PROJECT_ID%"=="" goto MENU
set /p PROJECT_MODELS=Models CSV [local-general,local-embedding]: 
if "%PROJECT_MODELS%"=="" set "PROJECT_MODELS=local-general,local-embedding"
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION% projects-create %PROJECT_ID% %PROJECT_MODELS%"
echo.
pause
goto MENU

:PROJECT_SHOW
echo.
set /p PROJECT_ID=Project id: 
if "%PROJECT_ID%"=="" goto MENU
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION% projects-show %PROJECT_ID%"
echo.
pause
goto MENU

:PROJECT_REVOKE
echo.
set /p PROJECT_ID=Project id to revoke: 
if "%PROJECT_ID%"=="" goto MENU
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION% projects-revoke %PROJECT_ID%"
echo.
pause
goto MENU

:PROJECTS_FOLDER
explorer.exe "\\wsl.localhost\Ubuntu\opt\ai-station\projects"
goto MENU

:LOGS
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION% logs"
echo.
pause
goto MENU

:BACKUP
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION% backup"
echo.
pause
goto MENU

:DISK
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION% disk"
echo.
pause
goto MENU

:VSCODE
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION% vscode"
echo.
pause
goto MENU

:GIT
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION% git"
echo.
pause
goto MENU

:RESET_WEBUI_PASSWORD
echo.
echo This will set a new Open WebUI password for the admin account.
echo The new password will be shown once in this window.
echo.
wsl.exe -d %WSL_DISTRO% --user root -- bash -lc "%ACTION% reset-webui-password"
echo.
pause
goto MENU
