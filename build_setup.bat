@echo off
setlocal

cd /d "%~dp0"

echo ============================================================
echo EVE Local Intel Scanner - Setup.exe Builder
echo ============================================================
echo.

if not exist ".venv\Scripts\activate.bat" goto no_venv

call ".venv\Scripts\activate.bat"

echo [1/4] Installing/updating PyInstaller...
python -m pip install --upgrade pyinstaller
if errorlevel 1 goto error

echo.
echo [1A/4] Running preflight checks...
python preflight_check.py pre
if errorlevel 1 goto error

echo.
echo [2/4] Cleaning old build files...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist installer_output rmdir /s /q installer_output

echo.
echo [3/4] Building app folder with PyInstaller...
pyinstaller --clean --noconfirm "EVE Local Intel Scanner.spec"
if errorlevel 1 goto error

python preflight_check.py post-pyinstaller
if errorlevel 1 goto error

echo.
echo [4/4] Building Setup.exe with Inno Setup...

set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" goto run_inno

set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" goto run_inno

goto no_inno

:run_inno
echo Found Inno Setup compiler:
echo "%ISCC%"
"%ISCC%" "installer.iss"
if errorlevel 1 goto error

python preflight_check.py post-inno
if errorlevel 1 goto error

echo.
echo ============================================================
echo DONE
echo Setup file:
echo installer_output\EVE_Local_Intel_Scanner_Setup.exe
echo ============================================================
pause
exit /b 0

:no_venv
echo [ERROR] .venv not found.
echo Run this from project root: c:\eve-local-scanner
pause
exit /b 1

:no_inno
echo [ERROR] Inno Setup 6 was not found.
echo Install Inno Setup 6 and run this script again.
echo Expected:
echo C:\Program Files (x86)\Inno Setup 6\ISCC.exe
echo or:
echo C:\Program Files\Inno Setup 6\ISCC.exe
pause
exit /b 1

:error
echo.
echo [ERROR] Build failed.
pause
exit /b 1
