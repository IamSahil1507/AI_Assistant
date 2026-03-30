@echo off
set here=%~dp0
powershell -NoExit -ExecutionPolicy Bypass -File "%here%serve_addin.ps1"
