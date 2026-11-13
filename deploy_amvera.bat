@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ============================================================
echo   NOEMA - деплой на Amvera
echo ============================================================
echo.
echo Сначала создай приложение в Amvera и скопируй Git URL.
echo Он выглядит так:
echo   https://git.amvera.ru/ЛОГИН/ИМЯ_ПРОЕКТА
echo.
set /p REPO=Вставь Git URL проекта Amvera: 

if "%REPO%"=="" (
    echo URL не указан.
    pause
    exit /b 1
)

echo.
echo [1/3] Настраиваю remote...
git remote remove amvera >nul 2>&1
git remote add amvera "%REPO%"
if errorlevel 1 goto error

echo [2/3] Коммичу изменения...
git add .
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "deploy update"
)

echo [3/3] Отправляю код в Amvera...
echo Если Git попросит логин и пароль - введи данные аккаунта Amvera.
git push -u amvera master
if errorlevel 1 (
    echo.
    echo Обычный push не прошёл. Пробую перезаписать ветку master...
    echo Это безопасно для нового проекта Amvera.
    git push -u amvera master --force
)
if errorlevel 1 goto error

echo.
echo ============================================================
echo   ГОТОВО. Amvera начала сборку.
echo ============================================================
echo.
echo Теперь добавь переменные в Amvera:
echo   BOT_TOKEN, ADMIN_IDS, PAYMENT_SECRET, PRICE_STARS,
echo   TIMEZONE, LOG_LEVEL, BRAND, SUPPORT_CONTACT,
echo   PYTHONUNBUFFERED
echo.
echo И останови локальный бот:
echo   Stop-Process -Id (Get-Content data\bot.pid) -Force
echo.
pause
exit /b 0

:error
echo.
echo Ошибка. Проверь Git URL и данные аккаунта Amvera.
pause
exit /b 1
