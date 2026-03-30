@echo off
taskkill /f /im python.exe
taskkill /f /im cmd.exe /fi "WINDOWTITLE eq Gateway"
echo Services stopped.
pause