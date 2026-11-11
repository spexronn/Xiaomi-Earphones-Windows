@echo off
chcp 65001 >nul
setlocal EnableExtensions
title SPEXRON Buds Monitor - Derleme
rem  1) Calisan uygulamayi kapat  2) Eski derlemeyi sil
rem  3) Eski derleme artiklarini temizle  4) Yeniden derle   - SPEXRON SOFT

cd /d "%~dp0"
set "APP=SPEXRON Buds Monitor"
set "PY=.venv\Scripts\python.exe"
set "PYTHONIOENCODING=utf-8"
set "WAS_RUNNING=0"

echo.
echo  === SPEXRON Buds Monitor - Derleme ===
echo.

echo [1/4] Çalışan uygulama kapatılıyor...
tasklist /FI "IMAGENAME eq %APP%.exe" 2>nul | find /I "%APP%.exe" >nul
if not errorlevel 1 (
    set "WAS_RUNNING=1"
    taskkill /F /IM "%APP%.exe" >nul 2>&1
    ping -n 3 127.0.0.1 >nul
)

echo [2/4] Eski derleme siliniyor...
if exist "%APP%.exe" del /f /q "%APP%.exe" 2>nul
if exist "%APP%.lnk" del /f /q "%APP%.lnk" 2>nul
if exist "dist" rmdir /s /q "dist"
if exist "dist" (
    echo       HATA: dist silinemedi, bir dosya hala acik olabilir.
    goto :fail
)

echo [3/4] Eski derleme artıkları temizleniyor...
if exist "build\work" rmdir /s /q "build\work"
if exist "build\build_log.txt" del /q "build\build_log.txt"
if exist "*.spec" del /q "*.spec"

if not exist "%PY%" (
    echo       HATA: .venv bulunamadi. README'deki kurulum adimlarini uygulayin.
    goto :fail
)

echo [4/4] Derleniyor...
"%PY%" build\build.py > "build\build_log.txt" 2>&1
if errorlevel 1 goto :buildfail
if not exist "dist\%APP%\%APP%.exe" goto :buildfail

rem Ana dizine EXE eklendiğini doğrula (gerekirse kopyala)
if not exist "%APP%.exe" (
    copy /y "dist\%APP%\%APP%.exe" "%APP%.exe" >nul 2>&1
)

echo.
echo  TAMAM:
echo    - Ana Dizin: %CD%\%APP%.exe
echo    - Dağıtım  : %CD%\dist\%APP%\%APP%.exe
if exist "%APP%.lnk" echo    - Kısayol  : %CD%\%APP%.lnk
rem Izleyiciyi bu pencereden bagimsiz baslat (cikti kanallarini miras almasin)
if "%WAS_RUNNING%"=="1" powershell -NoProfile -Command "Start-Process -FilePath '%CD%\%APP%.exe' -ArgumentList '--watch'"
echo.
if /I not "%~1"=="/nopause" pause
exit /b 0

:buildfail
echo       HATA: Derleme basarisiz. Ayrintilar: build\build_log.txt
:fail
echo.
echo  DERLEME BASARISIZ
if /I not "%~1"=="/nopause" pause
exit /b 1
