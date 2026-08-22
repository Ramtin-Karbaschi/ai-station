@echo off
setlocal
set "DISTRO=Ubuntu"
if defined AI_STATION_WSL_DISTRO set "DISTRO=%AI_STATION_WSL_DISTRO%"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "\\wsl.localhost\%DISTRO%\opt\ai-station\AI Station\AI Station Manager.ps1"
exit /b %ERRORLEVEL%
