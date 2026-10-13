@echo off
rem Build an empty ParkBenchDB OpenEdge 12.8 database from the generated files in this directory.
rem
rem   usage: db\build_db.bat <target-dir> [db-name] [--bi-block-size <KB>] [--bi-cluster-size <MB>]
rem          (db-name defaults to parkbench; before-image defaults: 16 KB blocks, 16 MB clusters)
rem
rem Steps (see specs\002-df-st-generation\research.md R8):
rem   1 Check prerequisites   2 Create structure   3 Copy UTF-8 metaschema   4 Configure before-image
rem   5 Confirm large files   6 Load schema        7 Verify database
rem
rem Exit codes: 0 built and verified; 2 prerequisite missing or database exists (nothing changed);
rem             3 a build step failed (partial database left in place); 4 verification failed.
rem Keep in step with db/build_db.sh: same steps, names, options, output and exit codes.

setlocal EnableExtensions EnableDelayedExpansion

set "STEPS=7"
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "ST_FILE=%SCRIPT_DIR%\parkbench.st"
set "DF_FILE=%SCRIPT_DIR%\parkbench.df"
set "EXPECT_FILE=%SCRIPT_DIR%\parkbench.expect"
set "LOAD_P=%SCRIPT_DIR%\abl\load_df.p"
set "VERIFY_P=%SCRIPT_DIR%\abl\verify_db.p"

set "BI_BLOCK_KB=16"
set "BI_CLUSTER_MB=16"
set "TARGET="
set "DB="
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
if !NPOS!==1 set "TARGET=%~1"
if !NPOS!==2 set "DB=%~1"
if !NPOS! GTR 2 goto :usage
shift
goto :parse
:parsed
if not defined TARGET goto :usage
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
set /a BI_CLUSTER_KB=BI_CLUSTER_MB*1024, BI_BLOCK_BYTES=BI_BLOCK_KB*1024, BI_CLUSTER_BYTES=BI_CLUSTER_MB*1048576
set "BI_EXPECT=biblocksize=!BI_BLOCK_BYTES!;biclustersize=!BI_CLUSTER_BYTES!"
if not defined DLC (set "REASON=DLC is not set; point it at an OpenEdge 12.8 installation" & goto :prereq_fail)
if not exist "!DLC!\version" (set "REASON=!DLC!\version not found; DLC does not look like an OpenEdge installation" & goto :prereq_fail)
findstr /c:"12.8" "!DLC!\version" >nul || (set "REASON=OpenEdge 12.8 is required; check !DLC!\version" & goto :prereq_fail)
for %%T in (prostrct procopy proutil) do (
    if not exist "!DLC!\bin\%%T.bat" (set "REASON=!DLC!\bin\%%T.bat not found" & goto :prereq_fail)
)
if not exist "!DLC!\bin\_progres.exe" if not exist "!DLC!\bin\_progres.bat" (set "REASON=!DLC!\bin\_progres.exe not found" & goto :prereq_fail)
if not exist "!DLC!\prolang\utf\empty8.db" (set "REASON=UTF-8 empty database !DLC!\prolang\utf\empty8.db not found" & goto :prereq_fail)
for %%F in ("%ST_FILE%" "%DF_FILE%" "%EXPECT_FILE%" "%LOAD_P%" "%VERIFY_P%") do (
    if not exist "%%~F" (set "REASON=%%~F not found; run tools/gen_db_files.py or restore the repository files" & goto :prereq_fail)
)
if exist "!TARGET!\!DB!.db" (set "REASON=database !TARGET!\!DB!.db already exists; remove it or choose another target" & goto :prereq_fail)
echo ok

rem ---------------------------------------------------------------- 2-7. build
set "N=2" & set "NAME=Create structure" & set "CODE=3"
if not exist "!TARGET!\" mkdir "!TARGET!" 2>nul
if not exist "!TARGET!\" (<nul set /p "=[2/%STEPS%] Create structure ... " & goto :step_fail)
for %%I in ("!TARGET!") do set "TARGET=%%~fI"
set "LOG=!TARGET!\!DB!_build.log"
set "PB_LOG=!LOG!"
type nul > "!LOG!"
cd /d "!TARGET!"
set "LOAD_STATUS=!TARGET!\!DB!_step6.status"
set "VERIFY_STATUS=!TARGET!\!DB!_step7.status"
del "!LOAD_STATUS!" "!VERIFY_STATUS!" 2>nul

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

rem Large files are always on in OpenEdge 12.x (proutil -C enablelargefiles is retired, message 19352),
rem so step 5 confirms the feature is active instead of trying to enable it.
set "N=5" & set "NAME=Confirm large files"
call :begin
call "!DLC!\bin\proutil.bat" !DB! -C describe > "!TARGET!\!DB!_describe.txt" 2>&1
type "!TARGET!\!DB!_describe.txt" >>"!LOG!"
findstr /r /c:"Large Files  *Yes" "!TARGET!\!DB!_describe.txt" >nul || goto :step_fail
echo ok

set "N=6" & set "NAME=Load schema"
call :begin
call "!DLC!\bin\_progres" -b -1 -db !DB! -cpinternal UTF-8 -cpstream UTF-8 -p "%LOAD_P%" -param "%DF_FILE%|!LOAD_STATUS!" >>"!LOG!" 2>&1 || goto :step_fail
call :status_ok "!LOAD_STATUS!" || goto :step_fail
echo ok

set "N=7" & set "NAME=Verify database" & set "CODE=4"
call :begin
call "!DLC!\bin\_progres" -b -1 -db !DB! -cpinternal UTF-8 -cpstream UTF-8 -p "%VERIFY_P%" -param "%EXPECT_FILE%|!VERIFY_STATUS!|!BI_EXPECT!" >>"!LOG!" 2>&1 || goto :step_fail
call :status_ok "!VERIFY_STATUS!" || goto :step_fail
echo ok

findstr /b /c:"CHECK" /c:"VERIFY" "!LOG!"
echo Database !TARGET!\!DB!.db built and verified.
exit /b 0

rem ---------------------------------------------------------------- subroutines
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
echo usage: build_db.bat ^<target-dir^> [db-name] [--bi-block-size ^<KB^>] [--bi-cluster-size ^<MB^>]
echo   Builds an empty OpenEdge 12.8 database ^<target-dir^>\^<db-name^>.db (default name: parkbench).
echo   --bi-block-size    before-image block size in KB, one of 1, 2, 4, 8, 16 (default 16)
echo   --bi-cluster-size  before-image cluster size in MB, 1-255 (default 16)
echo   DLC must point at the OpenEdge 12.8 installation.
exit /b 2
