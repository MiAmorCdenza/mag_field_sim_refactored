@echo off
rem mf_server 一键启动(双击):venv/依赖/编译/端口检查/浏览器全自动
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 (
    echo.
    echo 启动失败,详见上方输出或 logs\server.jsonl
    pause
)
