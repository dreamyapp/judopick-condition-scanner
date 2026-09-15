@echo off
setlocal
cd /d "%~dp0"

py -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

py -m PyInstaller --noconfirm condition_scanner_windows.spec
if errorlevel 1 exit /b 1

set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo Inno Setup 6이 필요합니다: https://jrsoftware.org/isdl.php
  exit /b 1
)

"%ISCC%" installer_windows.iss
if errorlevel 1 exit /b 1

echo 완료: dist\Judopick-ConditionScanner-Windows-x64-Setup.exe
