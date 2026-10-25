@echo off
setlocal
cd /d "%~dp0"
title Aprova no celular
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" goto instalar
"%PY%" -c "import flet, flet_web" 2>nul
if errorlevel 1 goto instalar

echo Deixe esta janela aberta enquanto usa o Aprova no celular.
"%PY%" main.py --web
pause
exit /b 0

:instalar
echo Abra primeiro o arquivo "Abrir Aprova.bat" para instalar o app.
pause
exit /b 1
