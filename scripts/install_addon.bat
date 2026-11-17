@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ===========================================================================
REM  freecad-mcp :: addon installer / updater for Windows
REM
REM  What it does:
REM    1. verifies it is running on Windows
REM    2. locates FreeCADCmd.exe (PATH, registry, common install roots)
REM    3. asks FreeCAD itself for its version and its authoritative Mod dir
REM    4. makes sure FreeCAD is not running
REM    5. fetches addon\FreeCADMCP from GitHub (git, or a zip fallback)
REM    6. backs up any existing install and copies the new addon into place
REM
REM  Usage:
REM    install_addon.bat
REM    install_addon.bat "C:\Program Files\FreeCAD 1.1\bin\FreeCADCmd.exe"
REM    install_addon.bat -b main
REM    install_addon.bat -b v0.1.24
REM
REM  Options:
REM    <path>   explicit path to FreeCADCmd.exe (skips auto-detection)
REM    -b REF   install from this git branch or tag instead of "main"
REM    -h       show this help
REM ===========================================================================

set "REPO_URL=https://github.com/neka-nat/freecad-mcp.git"
set "REPO_BRANCH=main"
set "FREECADCMD="
set "FC_VER="
set "FC_MOD="
set "ADDON_SRC="
set "BAK="

REM ---------------------------------------------------------------------------
REM  argument parsing
REM ---------------------------------------------------------------------------
:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="-b" goto arg_branch
if /i "%~1"=="-h" goto usage
if /i "%~1"=="--help" goto usage
set "_arg=%~1"
if "!_arg:~0,1!"=="-" (
    echo [x] Unknown option: %~1
    echo.
    goto usage
)
set "FREECADCMD=%~1"
shift
goto parse_args

:arg_branch
if "%~2"=="" (
    echo [x] -b requires a branch or tag name.
    exit /b 2
)
set "REPO_BRANCH=%~2"
shift
shift
goto parse_args

:args_done
REM The un-prefixed archive form resolves both branches and tags; the
REM refs/heads/ form 404s when %REPO_BRANCH% is a tag.
set "REPO_ZIP=https://github.com/neka-nat/freecad-mcp/archive/%REPO_BRANCH%.zip"

REM ---------------------------------------------------------------------------
REM  1. operating system
REM ---------------------------------------------------------------------------
echo.
echo [1/6] Checking operating system
if /i not "%OS%"=="Windows_NT" (
    echo       [x] This script targets Windows; detected OS is "%OS%".
    echo           On Linux or macOS copy addon/FreeCADMCP into the Mod
    echo           directory yourself, see docs/installation.md.
    exit /b 1
)
set "OSVER="
for /f "delims=" %%V in ('ver') do set "OSVER=%%V"
echo       OS      : %OS%  (%PROCESSOR_ARCHITECTURE%)
echo       Version : %OSVER%

REM ---------------------------------------------------------------------------
REM  2. locate FreeCADCmd.exe
REM ---------------------------------------------------------------------------
echo.
echo [2/6] Locating FreeCADCmd.exe
if defined FREECADCMD (
    if not exist "%FREECADCMD%" (
        echo       [x] The given path does not exist: !FREECADCMD!
        exit /b 1
    )
    echo       Using the path you provided.
    goto detect_freecad
)

call :find_freecadcmd
if not defined FREECADCMD (
    echo       [warn] Could not find FreeCADCmd.exe automatically.
    echo              Falling back to inspecting %%APPDATA%%\FreeCAD.
    call :infer_moddir_without_freecad
    goto after_detect
)
echo       Found : %FREECADCMD%

REM ---------------------------------------------------------------------------
REM  3. ask FreeCAD for its version and Mod directory
REM ---------------------------------------------------------------------------
:detect_freecad
echo.
echo [3/6] Reading FreeCAD version and addon directory
set "TMPPY=%TEMP%\fcmcp_detect_%RANDOM%%RANDOM%.py"
set "TMPOUT=%TEMP%\fcmcp_detect_%RANDOM%%RANDOM%.out"

> "%TMPPY%" echo import FreeCAD, os
>>"%TMPPY%" echo _v = FreeCAD.Version()
>>"%TMPPY%" echo print("FCMCP_VERSION=" + ".".join(str(x) for x in list(_v)[:3]))
>>"%TMPPY%" echo print("FCMCP_MODDIR=" + os.path.join(FreeCAD.getUserAppDataDir(), "Mod"))

REM Same invocation the MCP server's headless runner uses: "-c <code>".
"%FREECADCMD%" -c "exec(open(r'%TMPPY%', encoding='utf-8').read())" > "%TMPOUT%" 2>&1
for /f "usebackq tokens=1,* delims==" %%A in ("%TMPOUT%") do (
    if /i "%%A"=="FCMCP_VERSION" set "FC_VER=%%B"
    if /i "%%A"=="FCMCP_MODDIR" set "FC_MOD=%%B"
)
if not defined FC_MOD (
    echo       [warn] FreeCADCmd did not report a Mod directory.
    if exist "%TMPOUT%" (
        echo       --- FreeCADCmd output ---
        type "%TMPOUT%"
        echo       -------------------------
    )
    del /q "%TMPPY%" "%TMPOUT%" >nul 2>nul
    call :infer_moddir_without_freecad
    goto after_detect
)
del /q "%TMPPY%" "%TMPOUT%" >nul 2>nul
if not defined FC_VER set "FC_VER=unknown"
echo       FreeCAD version : %FC_VER%
echo       Mod directory   : %FC_MOD%

REM ---------------------------------------------------------------------------
REM  4. make sure FreeCAD is closed
REM ---------------------------------------------------------------------------
:after_detect
if not defined FC_MOD (
    echo.
    echo [x] Could not determine the FreeCAD addon directory.
    echo     Pass FreeCADCmd.exe explicitly, for example:
    echo         install_addon.bat "C:\Program Files\FreeCAD 1.1\bin\FreeCADCmd.exe"
    exit /b 1
)
if not defined FC_VER set "FC_VER=unknown"

echo.
echo [4/6] Checking that FreeCAD is not running
set "RUNNING="
tasklist /fi "imagename eq FreeCAD.exe" 2>nul | find /i "FreeCAD.exe" >nul && set "RUNNING=FreeCAD.exe"
tasklist /fi "imagename eq FreeCADCmd.exe" 2>nul | find /i "FreeCADCmd.exe" >nul && set "RUNNING=!RUNNING! FreeCADCmd.exe"
if defined RUNNING (
    echo       [x] FreeCAD is running:!RUNNING!
    echo           Close it and run this script again. Files in the Mod
    echo           directory cannot be replaced reliably while it is loaded.
    exit /b 1
)
echo       FreeCAD is not running.

REM ---------------------------------------------------------------------------
REM  5. fetch the addon from GitHub
REM ---------------------------------------------------------------------------
echo.
echo [5/6] Fetching the addon from %REPO_URL%
echo       Ref: %REPO_BRANCH%
set "WORKDIR=%TEMP%\fcmcp_fetch_%RANDOM%%RANDOM%"
mkdir "%WORKDIR%" >nul 2>nul

where git >nul 2>nul
if errorlevel 1 (
    echo       git not found on PATH, using a zip download instead.
    goto fetch_zip
)

echo       Cloning with git...
git clone --depth 1 --branch "%REPO_BRANCH%" --filter=blob:none --sparse "%REPO_URL%" "%WORKDIR%\repo" >nul 2>nul
if errorlevel 1 (
    echo       Sparse clone failed, retrying a plain shallow clone...
    rmdir /s /q "%WORKDIR%\repo" >nul 2>nul
    git clone --depth 1 --branch "%REPO_BRANCH%" "%REPO_URL%" "%WORKDIR%\repo" >nul 2>nul
)
if errorlevel 1 (
    echo       [warn] git clone failed, using a zip download instead.
    goto fetch_zip
)
if exist "%WORKDIR%\repo\.git" (
    pushd "%WORKDIR%\repo"
    git sparse-checkout set addon >nul 2>nul
    popd
)
if exist "%WORKDIR%\repo\addon\FreeCADMCP\InitGui.py" (
    set "ADDON_SRC=%WORKDIR%\repo\addon\FreeCADMCP"
    goto fetch_done
)
echo       [warn] addon\FreeCADMCP missing from the clone, using a zip download instead.

:fetch_zip
echo       Downloading %REPO_ZIP%
set "ZIPFILE=%WORKDIR%\repo.zip"
set "PSLOG=%WORKDIR%\powershell.log"
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri '%REPO_ZIP%' -OutFile '%ZIPFILE%'; Expand-Archive -LiteralPath '%ZIPFILE%' -DestinationPath '%WORKDIR%\zip' -Force } catch { Write-Output $_; exit 1 }" > "%PSLOG%" 2>&1
if errorlevel 1 (
    echo       [x] Download or extraction failed.
    if exist "%PSLOG%" type "%PSLOG%"
    goto fetch_failed
)
for /d %%D in ("%WORKDIR%\zip\*") do (
    if exist "%%~fD\addon\FreeCADMCP\InitGui.py" set "ADDON_SRC=%%~fD\addon\FreeCADMCP"
)
if not defined ADDON_SRC (
    echo       [x] The archive did not contain addon\FreeCADMCP.
    goto fetch_failed
)
echo       Used the zip archive.

:fetch_done
echo       Source : %ADDON_SRC%

REM ---------------------------------------------------------------------------
REM  6. install
REM ---------------------------------------------------------------------------
echo.
echo [6/6] Installing the addon
set "DEST=%FC_MOD%\FreeCADMCP"

if not exist "%FC_MOD%\" (
    mkdir "%FC_MOD%" >nul 2>nul
    if not exist "%FC_MOD%\" (
        echo       [x] Could not create !FC_MOD!
        goto install_failed
    )
)

if exist "%DEST%\" (
    set "TSFILE=%TEMP%\fcmcp_ts_%RANDOM%.txt"
    REM Delayed expansion is required here: cmd expands the whole block when it
    REM is parsed, before the set above runs, so a plain expansion is empty.
    powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss" > "!TSFILE!" 2>nul
    set "TS="
    if exist "!TSFILE!" set /p TS=<"!TSFILE!"
    del /q "!TSFILE!" >nul 2>nul
    if not defined TS set "TS=%RANDOM%%RANDOM%"
    set "BAK=%FC_MOD%\FreeCADMCP.bak-!TS!"
    echo       Backing up the existing install to:
    echo         !BAK!
    move "%DEST%" "!BAK!" >nul
    if errorlevel 1 (
        echo       [x] Could not move the existing addon directory aside.
        echo           Make sure no process is holding files in it.
        set "BAK="
        goto install_failed
    )
)

echo       Copying to %DEST%
xcopy /E /I /Y /Q "%ADDON_SRC%" "%DEST%\" >nul
if errorlevel 1 (
    echo       [x] xcopy failed.
    goto install_failed
)
if not exist "%DEST%\InitGui.py" (
    echo       [x] Verification failed: !DEST!\InitGui.py is missing.
    goto install_failed
)

echo.
echo [OK] The addon was installed and verified.
echo        FreeCAD version : %FC_VER%
echo        Addon directory : %DEST%
if defined BAK echo        Previous install: %BAK%
echo.
echo Next steps
echo   1. Start FreeCAD and select the "MCP Addon" workbench.
echo   2. Click "Start RPC Server" in the FreeCAD MCP toolbar.
echo   3. Point your MCP client at the matching server package:
echo        "command": "uvx", "args": ["freecad-mcp"]
echo.
echo Note: the addon and the "freecad-mcp" package ship separately and are
echo versioned separately. This script updates only the addon; keep the
echo package current with ^"uvx freecad-mcp@latest^" or ^"pip install -U freecad-mcp^".
rmdir /s /q "%WORKDIR%" >nul 2>nul
exit /b 0

:install_failed
REM Roll back to the backup moved aside above, if one was made. Clear any
REM partial copy first: a failed xcopy can leave a half-written FreeCADMCP
REM behind, and a Mod\FreeCADMCP without InitGui.py is not a usable addon.
if defined BAK (
    if exist "!DEST!\" rmdir /s /q "!DEST!" >nul 2>nul
    move "!BAK!" "!DEST!" >nul 2>nul
    if exist "!DEST!\InitGui.py" (
        echo       [i] Restored the previous addon to: !DEST!
    ) else (
        echo       [i] The previous addon was left at: !BAK!
    )
)
rmdir /s /q "%WORKDIR%" >nul 2>nul
exit /b 1

:fetch_failed
rmdir /s /q "%WORKDIR%" >nul 2>nul
exit /b 1

REM ===========================================================================
REM  subroutines
REM ===========================================================================

:find_freecadcmd
REM 1) on PATH
for /f "delims=" %%P in ('where FreeCADCmd.exe 2^>nul') do (
    if not defined FREECADCMD set "FREECADCMD=%%P"
)
if defined FREECADCMD exit /b 0

REM 2) registry uninstall entries
call :find_freecadcmd_registry
if defined FREECADCMD exit /b 0

REM 3) common install roots (last match wins, which is usually the newest)
call :scan_freecad_root "%ProgramFiles%"
if defined FREECADCMD exit /b 0
call :scan_freecad_root "%ProgramFiles(x86)%"
if defined FREECADCMD exit /b 0
call :scan_freecad_root "%LOCALAPPDATA%\Programs"
exit /b 0

:scan_freecad_root
set "_root=%~1"
if "%_root%"=="" exit /b 0
if not exist "%_root%\" exit /b 0
for /d %%D in ("%_root%\FreeCAD*") do (
    if exist "%%~fD\bin\FreeCADCmd.exe" set "FREECADCMD=%%~fD\bin\FreeCADCmd.exe"
    if exist "%%~fD\FreeCADCmd.exe" set "FREECADCMD=%%~fD\FreeCADCmd.exe"
)
exit /b 0

:find_freecadcmd_registry
for %%R in (HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall) do (
    for /f "tokens=2,*" %%A in ('reg query "%%R" /s /f "FreeCAD" /d 2^>nul ^| findstr /i "InstallLocation"') do (
        call :try_reg_install_location "%%B"
    )
)
exit /b 0

:try_reg_install_location
if defined FREECADCMD exit /b 0
set "_loc=%~1"
REM strip any quotes the registry value carried, then a trailing separator
set "_loc=%_loc:"=%"
if "%_loc%"=="" exit /b 0
set "_last=%_loc:~-1%"
if "%_last%"=="\" set "_loc=%_loc:~0,-1%"
if exist "%_loc%\bin\FreeCADCmd.exe" set "FREECADCMD=%_loc%\bin\FreeCADCmd.exe"
if exist "%_loc%\FreeCADCmd.exe" set "FREECADCMD=%_loc%\FreeCADCmd.exe"
exit /b 0

:infer_moddir_without_freecad
set "FC_VER=unknown"
set "FC_MOD="
set "_fcdata=%APPDATA%\FreeCAD"
if not exist "%_fcdata%\" (
    echo       [warn] %_fcdata% does not exist yet, assuming an unversioned install.
    set "FC_MOD=%_fcdata%\Mod"
    echo       Guessed Mod directory: !FC_MOD!
    exit /b 0
)
set "_verdir="
for /d %%D in ("%_fcdata%\v*") do set "_verdir=%%~nxD"
if defined _verdir (
    set "_vv=!_verdir:v=!"
    set "FC_VER=!_vv:-=.!"
    set "FC_MOD=%_fcdata%\!_verdir!\Mod"
    echo       [warn] Guessed from %%APPDATA%%: version !FC_VER!, Mod dir !FC_MOD!
    exit /b 0
)
set "FC_MOD=%_fcdata%\Mod"
echo       [warn] No versioned directory found, assuming an unversioned install.
echo       Guessed Mod directory: !FC_MOD!
exit /b 0

:usage
echo.
echo freecad-mcp addon installer for Windows
echo.
echo Usage:
echo   install_addon.bat [FreeCADCmd path] [-b REF]
echo.
echo   FreeCADCmd path  explicit path to FreeCADCmd.exe; skips auto-detection
echo   -b REF           install from this git branch or tag (default: main)
echo   -h, --help       show this help
echo.
echo Examples:
echo   install_addon.bat
echo   install_addon.bat "C:\Program Files\FreeCAD 1.1\bin\FreeCADCmd.exe"
echo   install_addon.bat -b v0.1.24
echo.
echo The addon is copied to the Mod directory FreeCAD reports for the running
echo installation, so versioned layouts such as %%APPDATA%%\FreeCAD\v1-1\Mod
echo are handled automatically.
exit /b 0
