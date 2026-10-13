@echo off
setlocal
set "REPO=%~dp0.."
for %%I in ("%REPO%") do set "REPO=%%~fI"
set "PY=%PBWORK_PYTHON%"
if not defined PY if exist "%REPO%\.venv-win\Scripts\python.exe" set "PY=%REPO%\.venv-win\Scripts\python.exe"
if not defined PY set "PY=python"
set "PYTHONPATH=%REPO%;%PYTHONPATH%"
set "PYTHONUTF8=1"
"%PY%" -m pbwork %*
exit /b %ERRORLEVEL%
