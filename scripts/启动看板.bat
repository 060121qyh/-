@echo off
rem ============================================================
rem 学习导师看板 - 开机自启动脚本（REQ-20260813-004 任务1）
rem 1. 切换到项目工作目录（Flask 依赖相对路径读取 config/data）
rem 2. 健康检查：已在运行则直接退出，防止重复启动
rem 3. 未运行则用绝对路径 Python 启动 server/app.py，日志追加
rem ============================================================
cd /d D:\乔一禾\项目工作区\多Agent学习导师

curl -s -m 3 http://localhost:8899/api/health | findstr "ok" >nul 2>&1
if %errorlevel%==0 (
    echo [%date% %time%] 看板已在运行，跳过启动 >> "scripts\看板启动日志.log"
    exit /b 0
)

echo [%date% %time%] 看板未运行，开始启动 >> "scripts\看板启动日志.log"
start "学习导师看板" /min "C:\Users\乔一禾\AppData\Local\Programs\Python\Python313\python.exe" server\app.py >> "scripts\看板启动日志.log" 2>&1
exit /b 0
