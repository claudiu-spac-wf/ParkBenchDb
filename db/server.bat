@echo off
rem Start, stop or query the ParkBenchDB database server with bulk-load-friendly settings.
rem
rem   usage: db\server.bat start  <db-path> [--port N] [--workers N] [--buffers N] [--apws N] [--lock-table N]
rem          db\server.bat stop   <db-path>
rem          db\server.bat status <db-path>
rem
rem start: proserve + 1 before-image writer + N page writers; waits for "connections enabled".
rem Exit codes: 0 ok / running; 2 bad arguments or already running; 3 not running; 4 start timed out.
rem Keep in step with db/server.sh. See docs\data-generation.md for the settings.

setlocal EnableExtensions EnableDelayedExpansion
if "%~2"=="" goto :usage
set "CMD=%~1"
set "DB=%~2"
if /i "%DB:~-3%"==".db" set "DB=%DB:~0,-3%"
set "PORT=20931" & set "WORKERS=8" & set "BUFFERS=200000" & set "APWS=2" & set "LOCKTABLE="
shift & shift
:parse
if "%~1"=="" goto :parsed
if /i "%~1"=="--port" (set "PORT=%~2" & shift & shift & goto :parse)
if /i "%~1"=="--workers" (set "WORKERS=%~2" & shift & shift & goto :parse)
if /i "%~1"=="--buffers" (set "BUFFERS=%~2" & shift & shift & goto :parse)
if /i "%~1"=="--apws" (set "APWS=%~2" & shift & shift & goto :parse)
if /i "%~1"=="--lock-table" (set "LOCKTABLE=%~2" & shift & shift & goto :parse)
echo unknown option: %~1
goto :usage
:parsed
for %%V in ("%PORT%" "%WORKERS%" "%BUFFERS%" "%APWS%") do (
    echo(%%~V| findstr /r /x "[0-9][0-9]*" >nul || (echo option values must be whole numbers ^(got '%%~V'^) & exit /b 2)
)
if not defined DLC (echo DLC is not set; point it at the OpenEdge 12.8 installation & exit /b 2)
if not exist "!DB!.db" (echo database !DB!.db not found & exit /b 2)
if not defined LOCKTABLE (
    set /a LOCKTABLE=WORKERS*40000
    if !LOCKTABLE! LSS 100000 set "LOCKTABLE=100000"
)

if /i "%CMD%"=="start" goto :start
if /i "%CMD%"=="stop" goto :stop
if /i "%CMD%"=="status" goto :status
goto :usage

:is_running
call "!DLC!\bin\proutil.bat" "!DB!" -C holder >nul 2>&1
if !ERRORLEVEL! EQU 16 exit /b 0
exit /b 1

:start
call :is_running && (echo database !DB! is already running & exit /b 2)
set /a MN=4+(WORKERS+3)/4
set /a NUSERS=WORKERS+10
set "MARK=0"
if exist "!DB!.lg" for /f %%C in ('find /c /v "" ^< "!DB!.lg"') do set "MARK=%%C"
echo starting !DB!: -S !PORT! -n !NUSERS! -Mn !MN! -L !LOCKTABLE! -B !BUFFERS!, 1 BIW, !APWS! APW(s)
call :spawn "!DLC!\bin\proserve.bat" """!DB!"" -S !PORT! -n !NUSERS! -Mn !MN! -L !LOCKTABLE! -B !BUFFERS! -bibufs 64 -spin 20000"
set "UP="
for /l %%I in (1,1,120) do (
    if not defined UP (
        more +!MARK! "!DB!.lg" 2>nul | findstr /c:"(10471)" >nul && set "UP=1"
        if not defined UP ping -n 1 -w 500 127.255.255.255 >nul 2>&1
    )
)
if not defined UP (echo server did not report 'Database connections have been enabled' within 60s; see !DB!.lg & exit /b 4)
call :spawn "!DLC!\bin\probiw.bat" """!DB!"""
for /l %%I in (1,1,!APWS!) do call :spawn "!DLC!\bin\proapw.bat" """!DB!"""
echo running on port !PORT!, -L !LOCKTABLE!
exit /b 0

:spawn
rem Start a process detached with its own hidden console, so callers (and WSL) do not wait for it.
set "PB_EXE=%~1"
set "PB_ARGS=%~2"
set "PB_ARGS=!PB_ARGS:""="!"
powershell -NoProfile -NonInteractive -Command "Start-Process -WindowStyle Hidden -FilePath $env:PB_EXE -ArgumentList $env:PB_ARGS" >nul 2>&1
exit /b 0

:stop
call :is_running || (echo stopped & exit /b 3)
call "!DLC!\bin\proshut.bat" "!DB!" -by
exit /b !ERRORLEVEL!

:status
call :is_running && (echo running & exit /b 0)
echo stopped
exit /b 3

:usage
echo usage: server.bat start ^<db-path^> [--port N] [--workers N] [--buffers N] [--apws N] [--lock-table N]
echo        server.bat stop ^<db-path^>
echo        server.bat status ^<db-path^>
exit /b 2
