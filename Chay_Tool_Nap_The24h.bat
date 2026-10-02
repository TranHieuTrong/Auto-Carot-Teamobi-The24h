@echo off
chcp 65001 >nul
title THE24H AUTO TOPUP - TOOL NẠP THẺ CAROT HÀNG LOẠT
echo ========================================================
echo        THE24H AUTO TOPUP - TEAMOBI / CAROT
echo ========================================================
echo Đang khởi động tool, vui lòng chờ giây lát...

if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe" (
    "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe" app.py
) else (
    python app.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [LỖI] Có lỗi khi chạy tool. Nhấn phím bất kỳ để thoát...
    pause >nul
)
