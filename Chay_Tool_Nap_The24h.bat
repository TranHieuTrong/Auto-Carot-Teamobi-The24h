@echo off
setlocal
title The24h Auto Topup
echo ========================================================
echo        THE24H AUTO TOPUP - TEAMOBI / CAROT
echo ========================================================
echo Dang khoi dong tool, vui long cho giay lat...

set "PY_EXE=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe"
if exist "%PY_EXE%" (
    "%PY_EXE%" app.py
    goto FINISH
)

set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist "%PY_EXE%" (
    "%PY_EXE%" app.py
    goto FINISH
)

py -3.12 app.py 2>nul
if %ERRORLEVEL% EQU 0 goto FINISH

python app.py

:FINISH
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [LOI] Khong the khoi dong tool.
    pause
)
