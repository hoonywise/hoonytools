@echo off
REM HoonyTools packaging script (ASCII-only)
chcp 65001 >nul

REM Prompt for version number (no 'v' prefix)
set /p VERSION_RAW=Enter version number (e.g., 1.0.5):
if "%VERSION_RAW%"=="" (
  echo No version entered. Exiting.
  pause
  exit /b 1
)
set "VERSION=v%VERSION_RAW%"

REM Paths
set "SOURCE_DIR=%~dp0"
set "RELEASE_BASE=%SOURCE_DIR%build\%VERSION%"
set "RELEASE_DIR=%RELEASE_BASE%\HoonyTools"
set "DIST_DIR=%SOURCE_DIR%dist"
set "ZIP_NAME=HoonyTools_v%VERSION_RAW%.zip"
set "ZIP_PATH=%DIST_DIR%\%ZIP_NAME%"

REM Prepare directories
if exist "%RELEASE_DIR%" rmdir /s /q "%RELEASE_DIR%"
if not exist "%RELEASE_DIR%" mkdir "%RELEASE_DIR%"
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

REM Copy optional folders
if exist "%SOURCE_DIR%assets" xcopy /s /e /y /i "%SOURCE_DIR%assets" "%RELEASE_DIR%\assets" >nul
if exist "%SOURCE_DIR%libs" xcopy /s /e /y /i "%SOURCE_DIR%libs" "%RELEASE_DIR%\libs" >nul
if exist "%SOURCE_DIR%loaders" xcopy /s /e /y /i "%SOURCE_DIR%loaders" "%RELEASE_DIR%\loaders" >nul
if exist "%SOURCE_DIR%tools" xcopy /s /e /y /i "%SOURCE_DIR%tools" "%RELEASE_DIR%\tools" >nul

REM Copy files if present
if exist "%SOURCE_DIR%HoonyTools.pyw" copy "%SOURCE_DIR%HoonyTools.pyw" "%RELEASE_DIR%\" >nul
:: Do not copy root-level config.py or setup_config.py; libs/ is already copied above
if exist "%SOURCE_DIR%README.txt" copy "%SOURCE_DIR%README.txt" "%RELEASE_DIR%\" >nul
if exist "%SOURCE_DIR%LICENSE.md" copy "%SOURCE_DIR%LICENSE.md" "%RELEASE_DIR%\" >nul
if exist "%SOURCE_DIR%CHANGELOG.md" copy "%SOURCE_DIR%CHANGELOG.md" "%RELEASE_DIR%\" >nul
if exist "%SOURCE_DIR%requirements.txt" copy "%SOURCE_DIR%requirements.txt" "%RELEASE_DIR%\" >nul

REM Cleanup pycache and .gitkeep
for /d /r "%RELEASE_DIR%" %%d in (__pycache__) do (
    if exist "%%d" rmdir /s /q "%%d"
)
for /r "%RELEASE_DIR%" %%f in (*.gitkeep) do (
    if exist "%%f" del /f /q "%%f"
)

REM Remove local-only files
if exist "%RELEASE_DIR%\libs\config.ini" del /f /q "%RELEASE_DIR%\libs\config.ini"

REM Locate 7-Zip
set "SEVENZIP="
if exist "%ProgramFiles(x86)%\7-Zip\7z.exe" set "SEVENZIP=%ProgramFiles(x86)%\7-Zip\7z.exe"
if not defined SEVENZIP if exist "%ProgramFiles%\7-Zip\7z.exe" set "SEVENZIP=%ProgramFiles%\7-Zip\7z.exe"
if not defined SEVENZIP for /f "usebackq delims=" %%P in (`where 7z.exe 2^>nul`) do if not defined SEVENZIP set "SEVENZIP=%%P"

if not defined SEVENZIP (
    echo 7-Zip not found. Please install 7-Zip or set SEVENZIP environment variable.
    pause
    exit /b 1
)

echo Using 7-Zip: %SEVENZIP%
echo Output ZIP: %ZIP_PATH%

if exist "%ZIP_PATH%" del /f /q "%ZIP_PATH%"

REM Create ZIP and show 7z output
"%SEVENZIP%" a -tzip "%ZIP_PATH%" "%RELEASE_DIR%\*"
if errorlevel 1 (
    echo 7-Zip failed with error %ERRORLEVEL%
    pause
    exit /b 1
)

echo Packaging complete: %ZIP_PATH%
pause
