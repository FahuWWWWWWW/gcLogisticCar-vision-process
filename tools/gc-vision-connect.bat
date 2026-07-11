@echo off
REM ============================================================================
REM gc-vision-connect.bat — Windows 批处理入口
REM 自动检测 Git Bash 并调用 gc-vision-connect.sh
REM ============================================================================
setlocal enabledelayedexpansion

REM 查找 Git Bash
set "GIT_BASH="
for %%p in (
    "C:\Program Files\Git\bin\bash.exe"
    "C:\Program Files (x86)\Git\bin\bash.exe"
    "%LOCALAPPDATA%\Programs\Git\bin\bash.exe"
) do (
    if exist %%p set "GIT_BASH=%%~p"
)

if "%GIT_BASH%"=="" (
    echo [错误] 未找到 Git Bash，请安装 Git for Windows: https://git-scm.com/
    echo        或者直接在 Git Bash 中运行: bash tools/gc-vision-connect.sh %*
    pause
    exit /b 1
)

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_PATH=%SCRIPT_DIR%gc-vision-connect.sh"

if not exist "%SCRIPT_PATH%" (
    echo [错误] 找不到脚本: %SCRIPT_PATH%
    exit /b 1
)

REM 调用 Git Bash 执行
"%GIT_BASH%" -c "cd \"$(cygpath -u '%CD%')\" && bash \"$(cygpath -u '%SCRIPT_PATH%')\" %*"
exit /b %ERRORLEVEL%
