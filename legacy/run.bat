@echo off
chcp 65001 >nul
title MagFieldSim Server

echo ========================================
echo   地球磁场与粒子仿真 - EarthMagFieldSim
echo ========================================
echo.

REM Use embedded Python runtime (no system Python required)
set PATH=.\python_embed;C:\utils\mingw64\mingw64\bin;%PATH%
set PYTHONHOME=.\python_embed

echo [启动] 正在初始化仿真引擎...
echo [提示] 首次启动需计算磁场网格，请耐心等待约30秒
echo [提示] 启动完成后访问 http://localhost:8001
echo.

MagFieldSim_Server.exe

pause
