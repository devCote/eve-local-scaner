@echo off
setlocal

cd /d "%~dp0"

echo ============================================================
echo EVE Local Intel Scanner - Code Signing Helper
echo ============================================================
echo.
echo This script requires a real code-signing certificate.
echo You need:
echo   - Windows SDK signtool.exe
echo   - .pfx certificate file
echo   - certificate password
echo.
echo Without a paid/trusted certificate this cannot remove SmartScreen warnings.
echo.

set "APP_EXE=dist\EVE Local Intel Scanner\EVE Local Intel Scanner.exe"
set "SETUP_EXE=installer_output\EVE_Local_Intel_Scanner_Setup.exe"

if "%SIGN_CERT_PFX%"=="" goto no_cert
if "%SIGN_CERT_PASSWORD%"=="" goto no_pass

set "SIGNTOOL=signtool.exe"

where signtool.exe >nul 2>nul
if errorlevel 1 goto no_signtool

if exist "%APP_EXE%" (
    echo Signing app exe...
    "%SIGNTOOL%" sign /fd SHA256 /f "%SIGN_CERT_PFX%" /p "%SIGN_CERT_PASSWORD%" /tr http://timestamp.digicert.com /td SHA256 "%APP_EXE%"
    if errorlevel 1 goto error
)

if exist "%SETUP_EXE%" (
    echo Signing setup exe...
    "%SIGNTOOL%" sign /fd SHA256 /f "%SIGN_CERT_PFX%" /p "%SIGN_CERT_PASSWORD%" /tr http://timestamp.digicert.com /td SHA256 "%SETUP_EXE%"
    if errorlevel 1 goto error
)

echo.
echo DONE: signing finished.
pause
exit /b 0

:no_cert
echo [ERROR] SIGN_CERT_PFX env variable is not set.
echo Example:
echo set SIGN_CERT_PFX=C:\certs\my-code-signing-cert.pfx
pause
exit /b 1

:no_pass
echo [ERROR] SIGN_CERT_PASSWORD env variable is not set.
echo Example:
echo set SIGN_CERT_PASSWORD=your_password
pause
exit /b 1

:no_signtool
echo [ERROR] signtool.exe not found.
echo Install Windows SDK and make sure signtool.exe is in PATH.
pause
exit /b 1

:error
echo [ERROR] Signing failed.
pause
exit /b 1
