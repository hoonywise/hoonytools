@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo HoonyTools Build Script
echo -----------------------
echo Python version in use:
python --version

set "SOURCE_DIR=%~dp0"

echo Terminating any running HoonyTools.exe...
taskkill /f /im HoonyTools.exe >nul 2>&1

echo Cleaning previous build folders...
del /q HoonyTools.spec >nul 2>&1
rmdir /s /q build >nul 2>&1
rmdir /s /q dist >nul 2>&1

:: Use HoonyTools.pyw as the launcher (legacy launcher removed)
if exist "%SOURCE_DIR%HoonyTools.pyw" (
    set "LAUNCHER=HoonyTools.pyw"
) else (
    echo Launcher script not found: HoonyTools.pyw
    pause
    exit /b 1
)

:: Build add-data options dynamically (only include folders that exist)
set "ADDS="
if exist "%SOURCE_DIR%assets"   set "ADDS=%ADDS% --add-data assets;assets"
if exist "%SOURCE_DIR%libs"     set "ADDS=%ADDS% --add-data libs;libs"
if exist "%SOURCE_DIR%loaders"  set "ADDS=%ADDS% --add-data loaders;loaders"
if exist "%SOURCE_DIR%tools"    set "ADDS=%ADDS% --add-data tools;tools"

:: Locate PyInstaller (prefer installed CLI then python -m)
where pyinstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not on PATH, will use "python -m PyInstaller"
    set "PYINST_CMD=python -m PyInstaller"
) else (
    set "PYINST_CMD=pyinstaller"
)

:: Resolve icon path explicitly so PyInstaller can embed it correctly
set "ICON_PATH=%SOURCE_DIR%assets\hoonywise_gui.ico"
if not exist "%ICON_PATH%" (
    echo Warning: icon not found at %ICON_PATH% - continuing without explicit icon
    set "ICON_ARG="
) else (
    set "ICON_ARG=--icon=%ICON_PATH%"
)

echo Building EXE using %PYINST_CMD% ...
echo Command: %PYINST_CMD% --noconfirm --windowed --onefile --name HoonyTools %ICON_ARG% %ADDS% "%LAUNCHER%"
%PYINST_CMD% --noconfirm --windowed --onefile --name HoonyTools %ICON_ARG% %ADDS% "%LAUNCHER%"

echo.
echo Build finished. Check dist\ for HoonyTools.exe (if created).

pause
