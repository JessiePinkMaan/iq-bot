@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [1/2] Создаю виртуальное окружение...
    python -m venv .venv
    if errorlevel 1 goto error
    echo [2/2] Устанавливаю зависимости...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto error
)

echo.
echo ============================================================
echo   NOEMA · IQ TEST BOT
echo ============================================================
echo.

".venv\Scripts\python.exe" run.py
echo.
echo Бот остановлен.
pause
exit /b 0

:error
echo.
echo Не удалось подготовить окружение. Проверь, что установлен Python 3.11+.
pause
exit /b 1
