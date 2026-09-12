@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto :tryPython
py -3 -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>nul
if errorlevel 1 goto :tryPython
set "VERTICE_PY=py -3"
goto :run
:tryPython
where python >nul 2>nul
if errorlevel 1 goto :missing
python -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>nul
if errorlevel 1 goto :missing
set "VERTICE_PY=python"
:run
%VERTICE_PY% server.py --open %*
set "VERTICE_EXIT=%errorlevel%"
goto :end
:missing
echo Se necesita Python 3.10 o posterior: https://www.python.org/downloads/
echo Tambien puedes usar la version web publicada sin instalar Python.
set "VERTICE_EXIT=1"
:end
if "%~1"=="" pause
exit /b %VERTICE_EXIT%
