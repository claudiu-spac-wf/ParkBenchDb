@echo off
rem Wrapper for the ParkBenchDB data generator: runs "python -m pbgen" from this repository.
rem   usage: db\pbgen.bat <command> [options]      (see docs\data-generation.md)
rem Python: %PBGEN_PYTHON% if set, else the repo's .venv-win, else python.
setlocal
set "REPO=%~dp0.."
for %%I in ("%REPO%") do set "REPO=%%~fI"
set "PY=%PBGEN_PYTHON%"
if not defined PY if exist "%REPO%\.venv-win\Scripts\python.exe" set "PY=%REPO%\.venv-win\Scripts\python.exe"
if not defined PY set "PY=python"
set "PYTHONPATH=%REPO%;%PYTHONPATH%"
"%PY%" -m pbgen %*
exit /b %ERRORLEVEL%
