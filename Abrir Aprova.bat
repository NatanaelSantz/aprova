@echo off
rem Abre o Aprova. Na primeira vez prepara tudo numa janela de instalacao,
rem sem precisar mexer em nada aqui.
setlocal
cd /d "%~dp0"
set "AQUI=%~dp0"
set "PY_URL=https://www.python.org/ftp/python/3.13.16/python-3.13.16-amd64.exe"

rem Ja instalado: abre o app sem janela preta
if exist ".venv\Scripts\pythonw.exe" (
  ".venv\Scripts\python.exe" -c "import sys" >nul 2>&1
  if not errorlevel 1 (
    start "" ".venv\Scripts\pythonw.exe" "%AQUI%iniciar.pyw"
    exit /b 0
  )
  rem a pasta .venv veio de outro computador: refaz
  rmdir /s /q ".venv"
)

rem Primeira vez: esta janela fica minimizada e a instalacao aparece numa janela propria
if /i not "%~1"=="--min" (
  start "Aprova" /min cmd /c ""%~f0" --min"
  exit /b 0
)

call :procurar_python
if not defined PYBASE (
  powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%AQUI%ferramentas\instalar_python.ps1" -Url "%PY_URL%"
  call :procurar_python
)
if not defined PYBASE goto sem_python
start "" "%PYW%" "%AQUI%iniciar.pyw"
exit /b 0


rem ---------------------------------------------------------------------------
:procurar_python
rem Procura um Python 3.10+ (ignora o atalho falso da Microsoft Store)
set "PYBASE="
set "PYW="
for /f "usebackq delims=" %%P in (`py -3 "%AQUI%ferramentas\onde_python.py" 2^>nul`) do set "PYBASE=%%P"
if not defined PYBASE for /f "usebackq delims=" %%P in (`python "%AQUI%ferramentas\onde_python.py" 2^>nul`) do set "PYBASE=%%P"
if not defined PYBASE for %%D in ("%LOCALAPPDATA%\Programs\Python\Python313" "%LOCALAPPDATA%\Programs\Python\Python312" "%LOCALAPPDATA%\Programs\Python\Python311" "%LOCALAPPDATA%\Programs\Python\Python314" "%ProgramFiles%\Python313" "%ProgramFiles%\Python312" "%ProgramFiles%\Python311" "%ProgramFiles%\Python314") do (
  if not defined PYBASE if exist "%%~D\python.exe" set "PYBASE=%%~D\python.exe"
)
if not defined PYBASE goto :eof
for %%F in ("%PYBASE%") do set "PYW=%%~dpFpythonw.exe"
if not exist "%PYW%" set "PYW=%PYBASE%"
goto :eof


:sem_python
powershell -NoProfile -WindowStyle Hidden -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('Nao consegui instalar o Python sozinho. Vou abrir o site python.org: instale a versao 3.13, marque Add python.exe to PATH e abra o Abrir Aprova.bat de novo.', 'Aprova') | Out-Null"
echo.
echo Nao consegui instalar o Python sozinho.
echo Instale pelo site python.org (versao 3.11 ou mais nova), marque a opcao
echo "Add python.exe to PATH" durante a instalacao e abra este arquivo de novo.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1
