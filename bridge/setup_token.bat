@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 quanta_uploader.py --setup
) else (
  python quanta_uploader.py --setup
)
echo.
pause
