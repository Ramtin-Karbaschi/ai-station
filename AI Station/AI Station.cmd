@echo off
setlocal
rem Quick start: bring platform up and open Open WebUI in the default browser.
rem Always run the copy in WSL /opt/ai-station so Desktop shortcuts cannot go stale.
set "DISTRO=Ubuntu"
if defined AI_STATION_WSL_DISTRO set "DISTRO=%AI_STATION_WSL_DISTRO%"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "\\wsl.localhost\%DISTRO%\opt\ai-station\AI Station\AI Station.ps1"
exit /b %ERRORLEVEL%
