@echo off
chcp 65001 >nul 2>&1
title 光电测试系统软件平台

echo ========================================
echo   光电测试系统软件平台 - PLAT_Optics
echo ========================================
echo.

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [错误] 未找到虚拟环境 .venv
    echo 请先创建虚拟环境: python -m venv .venv
    echo 然后安装依赖: .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo [1/2] 激活虚拟环境...
call .venv\Scripts\activate.bat

echo [2/2] 启动服务...
echo.
python app.py

if errorlevel 1 (
    echo.
    echo [错误] 程序异常退出
    pause
)
