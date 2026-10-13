@echo off
rem Binary-dump a ParkBenchDB database so it can be loaded on another OS with db/load_db.*.
rem
rem   usage: db\dump_db.bat <db-path> <dump-dir> [--allow-active]
rem
rem The source is only read. It may be served (the dump connects to the server) or offline.
rem <dump-dir> must be new or empty. It receives <table>.bd for every table (LOBs included),
rem schema.df, manifest.txt (tables, row counts, sequence values) and dump.log.
rem The binary dump format is platform-independent: copy the directory to the other host as-is.
rem
rem Steps: 1 Check prerequisites   2 Dump schema and sequences   3 Dump tables   4 Summary
rem Exit codes: 0 dumped; 2 prerequisite missing or refused (nothing written); 3 a step failed.
rem Keep in step with db/dump_db.sh: same steps, names, options, output and exit codes.

setlocal EnableExtensions EnableDelayedExpansion

set "STEPS=4"
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "DUMPLOAD_P=%SCRIPT_DIR%\abl\dumpload.p"

set "ALLOW_ACTIVE=0"
set "DB="
set "OUT="
set "NPOS=0"
:parse
if "%~1"=="" goto :parsed
if /i "%~1"=="--allow-active" (set "ALLOW_ACTIVE=1" & shift & goto :parse)
set "ARG=%~1"
if "!ARG:~0,1!"=="-" goto :usage
set /a NPOS+=1
if !NPOS!==1 set "DB=%~1"
if !NPOS!==2 set "OUT=%~1"
if !NPOS! GTR 2 goto :usage
shift
goto :parse
:parsed
if not !NPOS!==2 goto :usage
if /i "!DB:~-3!"==".db" set "DB=!DB:~0,-3!"
set "LOG="

rem ---------------------------------------------------------------- 1. prerequisites (nothing written)
<nul set /p "=[1/%STEPS%] Check prerequisites ... "
if not defined DLC (set "REASON=DLC is not set; point it at an OpenEdge 12.8 installation" & goto :prereq_fail)
if not exist "!DLC!\version" (set "REASON=!DLC!\version not found; DLC does not look like an OpenEdge installation" & goto :prereq_fail)
findstr /c:"12.8" "!DLC!\version" >nul || (set "REASON=OpenEdge 12.8 is required; check !DLC!\version" & goto :prereq_fail)
if not exist "!DLC!\bin\proutil.bat" (set "REASON=!DLC!\bin\proutil.bat not found" & goto :prereq_fail)
if not exist "!DLC!\bin\_progres.exe" if not exist "!DLC!\bin\_progres.bat" (set "REASON=!DLC!\bin\_progres.exe not found" & goto :prereq_fail)
if not exist "%DUMPLOAD_P%" (set "REASON=%DUMPLOAD_P% not found; restore the repository files" & goto :prereq_fail)
if not exist "!DB!.db" (set "REASON=database !DB!.db not found" & goto :prereq_fail)
if exist "!OUT!\" (
    dir /b /a "!OUT!" 2>nul | findstr "^" >nul && (set "REASON=dump directory !OUT! is not empty; choose a new or empty directory" & goto :prereq_fail)
)
for %%I in ("!DB!") do set "DB=%%~fI"
call "!DLC!\bin\proutil.bat" "!DB!" -C holder >nul 2>&1
set "HOLDER=!errorlevel!"
if "!HOLDER!"=="16" (set "SU=" & set "MODE=served") else if "!HOLDER!"=="0" (set "SU=-1" & set "MODE=offline") else (
    set "REASON=database !DB! is open single-user (or its state is unknown); close that session first" & goto :prereq_fail
)
echo ok (!MODE!)

rem ---------------------------------------------------------------- 2-4. dump
set "N=2" & set "NAME=Dump schema and sequences" & set "CODE=3"
if not exist "!OUT!\" mkdir "!OUT!" 2>nul
if not exist "!OUT!\" (<nul set /p "=[2/%STEPS%] !NAME! ... " & goto :step_fail)
for %%I in ("!OUT!") do set "OUT=%%~fI"
set "LOG=!OUT!\dump.log"
set "PB_LOG=!LOG!"
set "PB_OUT=!OUT!"
type nul > "!LOG!"
set "MANIFEST=!OUT!\manifest.txt"
set "TMPF=!OUT!\proutil.out"

call :begin
call "!DLC!\bin\_progres" -b !SU! -db "!DB!" -cpinternal UTF-8 -cpstream UTF-8 -p "%DUMPLOAD_P%" -param "dump|!OUT!" >>"!LOG!" 2>&1
findstr /b /c:"format=parkbench-dump-1" "!MANIFEST!" >nul 2>&1 || goto :step_fail
for %%F in ("!OUT!\schema.df") do if %%~zF==0 goto :step_fail
set "ACTIVE=0"
for /f "tokens=2 delims==" %%a in ('findstr /b /c:"activeClaims=" "!MANIFEST!"') do set "ACTIVE=%%a"
if not "!ACTIVE!"=="0" if "!ALLOW_ACTIVE!"=="0" (
    echo FAILED
    del "!MANIFEST!" "!OUT!\schema.df" 2>nul
    echo FAILED at step 2 ^(Dump schema and sequences^): !ACTIVE! pbgen unit^(s^) are claimed, so workers are still
    echo writing. Stop them ^(Ctrl+C on pbgen run^) and dump again, or pass --allow-active.
    exit /b 2
)
echo ok

set "N=3" & set "NAME=Dump tables"
call :begin
set "TOTAL=0" & set "NT=0"
for /f "tokens=2 delims==" %%t in ('findstr /b /c:"table=" "!MANIFEST!"') do (
    call :dump_one %%t || goto :step_fail
)
del "!TMPF!" 2>nul
echo ok

echo [4/%STEPS%] Summary ... ok
set "MB=0"
for /f %%s in ('powershell -NoProfile -Command "[int]((Get-ChildItem -LiteralPath $env:PB_OUT | Measure-Object Length -Sum).Sum/1MB)"') do set "MB=%%s"
echo Dumped !NT! tables, !TOTAL! rows (!MB! MB) from !DB! into !OUT!.
echo Copy the directory to the target host, then run db/load_db.sh ^<dump-dir^> ^<target-dir^> there.
exit /b 0

rem ---------------------------------------------------------------- subroutines
:dump_one
set "ROWS="
call "!DLC!\bin\proutil.bat" "!DB!" -C dump %1 "!OUT!" > "!TMPF!" 2>&1
set "RC=!errorlevel!"
type "!TMPF!" >>"!LOG!"
for /f "tokens=2" %%n in ('findstr /c:"Dumped " "!TMPF!"') do if not defined ROWS set "ROWS=%%n"
if not "!RC!"=="0" goto :dump_one_fail
if not defined ROWS goto :dump_one_fail
if not exist "!OUT!\%1.bd" goto :dump_one_fail
>>"!MANIFEST!" echo rows=%1=!ROWS!
set /a TOTAL+=ROWS, NT+=1
exit /b 0
:dump_one_fail
>>"!LOG!" echo table %1: proutil dump did not complete
exit /b 1

:begin
<nul set /p "=[!N!/%STEPS%] !NAME! ... "
>>"!LOG!" echo ==== [!N!/%STEPS%] !NAME!
exit /b 0

:step_fail
echo FAILED
echo FAILED at step !N! (!NAME!)
call :show_log
exit /b !CODE!

:show_log
if not defined LOG exit /b 0
if not exist "!LOG!" exit /b 0
echo ---- last 40 lines of !LOG! ----
powershell -NoProfile -Command "Get-Content -Tail 40 -LiteralPath $env:PB_LOG" 2>nul || type "!LOG!"
exit /b 0

:prereq_fail
echo FAILED
echo FAILED at step 1 (Check prerequisites): !REASON!
exit /b 2

:usage
echo usage: dump_db.bat ^<db-path^> ^<dump-dir^> [--allow-active]
echo   Binary-dumps every table of ^<db-path^> (served or offline) into ^<dump-dir^> (new or empty).
echo   --allow-active  dump even while pbgen workers hold claimed units (the dump may be inconsistent)
echo   DLC must point at the OpenEdge 12.8 installation.
exit /b 2
