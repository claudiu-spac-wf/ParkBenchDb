@echo off
rem Build a new ParkBenchDB database from a binary dump made by db/dump_db.* (on any OS).
rem
rem   usage: db\load_db.bat <dump-dir> <target-dir> [db-name] [--bi-block-size <KB>] [--bi-cluster-size <MB>]
rem          (db-name defaults to parkbench; before-image defaults: 16 KB blocks, 16 MB clusters)
rem
rem The new database uses this repository's parkbench.st (so extent paths are local), the UTF-8
rem empty database and the schema.df from the dump. An existing database is never touched: if
rem <target-dir>\<db-name>.db exists, nothing is done.
rem
rem Steps: 1 Check prerequisites   2 Create structure       3 Copy UTF-8 metaschema   4 Configure before-image
rem        5 Load schema           6 Load data              7 Rebuild indexes         8 Restore sequences and verify
rem Exit codes: 0 loaded and verified; 2 prerequisite missing or target exists (nothing changed);
rem             3 a step failed (partial database left in place); 4 verification failed.
rem Keep in step with db/load_db.sh: same steps, names, options, output and exit codes.

setlocal EnableExtensions EnableDelayedExpansion

set "STEPS=8"
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "ST_FILE=%SCRIPT_DIR%\parkbench.st"
set "LOAD_P=%SCRIPT_DIR%\abl\load_df.p"
set "DUMPLOAD_P=%SCRIPT_DIR%\abl\dumpload.p"

set "BI_BLOCK_KB=16"
set "BI_CLUSTER_MB=16"
set "DUMP=" & set "TARGET=" & set "DB="
set "NPOS=0"
:parse
if "%~1"=="" goto :parsed
if /i "%~1"=="--bi-block-size" (
    if "%~2"=="" goto :usage
    set "BI_BLOCK_KB=%~2" & shift & shift & goto :parse
)
if /i "%~1"=="--bi-cluster-size" (
    if "%~2"=="" goto :usage
    set "BI_CLUSTER_MB=%~2" & shift & shift & goto :parse
)
set "ARG=%~1"
if "!ARG:~0,1!"=="-" goto :usage
set /a NPOS+=1
if !NPOS!==1 set "DUMP=%~1"
if !NPOS!==2 set "TARGET=%~1"
if !NPOS!==3 set "DB=%~1"
if !NPOS! GTR 3 goto :usage
shift
goto :parse
:parsed
if !NPOS! LSS 2 goto :usage
if not defined DB set "DB=parkbench"
set "LOG="

rem ---------------------------------------------------------------- 1. prerequisites (no changes made)
<nul set /p "=[1/%STEPS%] Check prerequisites ... "
set "REASON=invalid db-name '%DB%': letters, digits, _ and -; at most 11 characters; must start with a letter"
echo(%DB%|findstr /r /x "[A-Za-z][A-Za-z0-9_-]*" >nul || goto :prereq_fail
if not "%DB:~11,1%"=="" goto :prereq_fail
set "REASON=invalid --bi-block-size '!BI_BLOCK_KB!' (KB); allowed: 1, 2, 4, 8, 16"
echo(%BI_BLOCK_KB%|findstr /x "1 2 4 8 16" >nul || goto :prereq_fail
set "REASON=invalid --bi-cluster-size '!BI_CLUSTER_MB!' (MB); allowed: 1-255"
echo(%BI_CLUSTER_MB%|findstr /r /x "[1-9] [1-9][0-9] [1-2][0-9][0-9]" >nul || goto :prereq_fail
if !BI_CLUSTER_MB! GTR 255 goto :prereq_fail
set /a BI_CLUSTER_KB=BI_CLUSTER_MB*1024
if not defined DLC (set "REASON=DLC is not set; point it at an OpenEdge 12.8 installation" & goto :prereq_fail)
if not exist "!DLC!\version" (set "REASON=!DLC!\version not found; DLC does not look like an OpenEdge installation" & goto :prereq_fail)
findstr /c:"12.8" "!DLC!\version" >nul || (set "REASON=OpenEdge 12.8 is required; check !DLC!\version" & goto :prereq_fail)
for %%T in (prostrct procopy proutil) do (
    if not exist "!DLC!\bin\%%T.bat" (set "REASON=!DLC!\bin\%%T.bat not found" & goto :prereq_fail)
)
if not exist "!DLC!\bin\_progres.exe" if not exist "!DLC!\bin\_progres.bat" (set "REASON=!DLC!\bin\_progres.exe not found" & goto :prereq_fail)
if not exist "!DLC!\prolang\utf\empty8.db" (set "REASON=UTF-8 empty database !DLC!\prolang\utf\empty8.db not found" & goto :prereq_fail)
for %%F in ("%ST_FILE%" "%LOAD_P%" "%DUMPLOAD_P%") do (
    if not exist "%%~F" (set "REASON=%%~F not found; restore the repository files" & goto :prereq_fail)
)
if not exist "!DUMP!\" (set "REASON=dump directory !DUMP! not found" & goto :prereq_fail)
for %%I in ("!DUMP!") do set "DUMP=%%~fI"
set "MANIFEST=!DUMP!\manifest.txt"
findstr /b /c:"format=parkbench-dump-1" "!MANIFEST!" >nul 2>&1 || (set "REASON=!MANIFEST! is missing or not a dump_db manifest" & goto :prereq_fail)
if not exist "!DUMP!\schema.df" (set "REASON=!DUMP!\schema.df is missing" & goto :prereq_fail)
set "NT=0"
for /f "tokens=2 delims==" %%t in ('findstr /b /c:"table=" "!MANIFEST!"') do (
    set /a NT+=1
    if not exist "!DUMP!\%%t.bd" (set "REASON=!DUMP!\%%t.bd is missing; the dump is incomplete" & goto :prereq_fail)
    findstr /b /c:"rows=%%t=" "!MANIFEST!" >nul || (set "REASON=!MANIFEST! has no row count for %%t; the dump did not finish" & goto :prereq_fail)
)
if !NT!==0 (set "REASON=!MANIFEST! lists no tables" & goto :prereq_fail)
if exist "!TARGET!\!DB!.db" (set "REASON=database !TARGET!\!DB!.db already exists; it is never overwritten - choose another target or name" & goto :prereq_fail)
echo ok

rem ---------------------------------------------------------------- 2-8. build and load
set "N=2" & set "NAME=Create structure" & set "CODE=3"
if not exist "!TARGET!\" mkdir "!TARGET!" 2>nul
if not exist "!TARGET!\" (<nul set /p "=[2/%STEPS%] Create structure ... " & goto :step_fail)
for %%I in ("!TARGET!") do set "TARGET=%%~fI"
set "LOG=!TARGET!\!DB!_load.log"
set "PB_LOG=!LOG!"
type nul > "!LOG!"
cd /d "!TARGET!"
set "SCHEMA_STATUS=!TARGET!\!DB!_step5.status"
set "FINISH_STATUS=!TARGET!\!DB!_step8.status"
set "TMPF=!TARGET!\!DB!_proutil.out"
del "!SCHEMA_STATUS!" "!FINISH_STATUS!" 2>nul

call :begin
copy /y "%ST_FILE%" "!TARGET!\!DB!.st" >>"!LOG!" 2>&1 || goto :step_fail
call "!DLC!\bin\prostrct.bat" create !DB! !DB!.st -blocksize 8192 >>"!LOG!" 2>&1 || goto :step_fail
echo ok

set "N=3" & set "NAME=Copy UTF-8 metaschema"
call :begin
call "!DLC!\bin\procopy.bat" "!DLC!\prolang\utf\empty8" !DB! >>"!LOG!" 2>&1 || goto :step_fail
echo ok

set "N=4" & set "NAME=Configure before-image"
call :begin
call "!DLC!\bin\proutil.bat" !DB! -C truncate bi -bi !BI_CLUSTER_KB! -biblocksize !BI_BLOCK_KB! >>"!LOG!" 2>&1 || goto :step_fail
echo ok

set "N=5" & set "NAME=Load schema"
call :begin
call "!DLC!\bin\_progres" -b -1 -db !DB! -cpinternal UTF-8 -cpstream UTF-8 -p "%LOAD_P%" -param "!DUMP!\schema.df|!SCHEMA_STATUS!" >>"!LOG!" 2>&1 || goto :step_fail
call :status_ok "!SCHEMA_STATUS!" || goto :step_fail
echo ok

set "N=6" & set "NAME=Load data"
call :begin
set "BAD=0"
for /f "tokens=2 delims==" %%t in ('findstr /b /c:"table=" "!MANIFEST!"') do (
    call :load_one %%t || (set "CODE=3" & goto :step_fail)
)
del "!TMPF!" 2>nul
if not !BAD!==0 (
    echo FAILED
    findstr /b /c:"COUNT " "!LOG!" | findstr /c:"FAIL"
    echo FAILED at step 6 ^(Load data^)
    call :show_log
    exit /b 4
)
echo ok

set "N=7" & set "NAME=Rebuild indexes"
call :begin
rem piped commands run in a child cmd without delayed expansion, hence %...%
echo y| "%DLC%\bin\proutil.bat" %DB% -C idxbuild all -TB 64 -TM 32 -SG 64 -cpinternal UTF-8 > "!TMPF!" 2>&1
set "RC=!errorlevel!"
type "!TMPF!" >>"!LOG!"
if not "!RC!"=="0" goto :step_fail
findstr /c:" 0 error(s) encountered" "!TMPF!" >nul || goto :step_fail
del "!TMPF!" 2>nul
echo ok

set "N=8" & set "NAME=Restore sequences and verify" & set "CODE=4"
call :begin
call "!DLC!\bin\_progres" -b -1 -db !DB! -cpinternal UTF-8 -cpstream UTF-8 -p "%DUMPLOAD_P%" -param "finish|!DUMP!|!FINISH_STATUS!" >>"!LOG!" 2>&1 || goto :step_fail
call :status_ok "!FINISH_STATUS!" || goto :step_fail
echo ok

findstr /b /c:"CHECK" /c:"FINISH" "!LOG!"
set "OKT=0"
for /f %%c in ('findstr /b /c:"COUNT " "!LOG!" ^| find /c ": ok"') do set "OKT=%%c"
echo Database !TARGET!\!DB!.db loaded from !DUMP! (!OKT! tables) and verified.
exit /b 0

rem ---------------------------------------------------------------- subroutines
:load_one
set "ROWS=" & set "WANT="
call "!DLC!\bin\proutil.bat" !DB! -C load "!DUMP!\%1.bd" -cpinternal UTF-8 > "!TMPF!" 2>&1
set "RC=!errorlevel!"
type "!TMPF!" >>"!LOG!"
if not "!RC!"=="0" exit /b 1
for /f "tokens=2" %%n in ('findstr /c:"Loaded " "!TMPF!"') do if not defined ROWS set "ROWS=%%n"
for /f "tokens=3 delims==" %%w in ('findstr /b /c:"rows=%1=" "!MANIFEST!"') do set "WANT=%%w"
if "!ROWS!"=="!WANT!" (>>"!LOG!" echo COUNT %1: ok ^(!ROWS!^)) else (
    if not defined ROWS set "ROWS=none"
    >>"!LOG!" echo COUNT %1: FAIL ^(loaded !ROWS!, dumped !WANT!^)
    set /a BAD+=1
)
exit /b 0

:begin
<nul set /p "=[!N!/%STEPS%] !NAME! ... "
>>"!LOG!" echo ==== [!N!/%STEPS%] !NAME!
exit /b 0

:status_ok
set "STATUS_LINE="
if exist "%~1" set /p STATUS_LINE=<"%~1"
if "!STATUS_LINE!"=="OK" exit /b 0
if not defined STATUS_LINE set "STATUS_LINE=missing - the ABL procedure did not finish"
>>"!LOG!" echo status (%~1): !STATUS_LINE!
exit /b 1

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
echo usage: load_db.bat ^<dump-dir^> ^<target-dir^> [db-name] [--bi-block-size ^<KB^>] [--bi-cluster-size ^<MB^>]
echo   Builds a new database ^<target-dir^>\^<db-name^>.db (default name: parkbench) from a dump made by dump_db.
echo   --bi-block-size    before-image block size in KB, one of 1, 2, 4, 8, 16 (default 16)
echo   --bi-cluster-size  before-image cluster size in MB, 1-255 (default 16)
echo   DLC must point at the OpenEdge 12.8 installation.
exit /b 2
