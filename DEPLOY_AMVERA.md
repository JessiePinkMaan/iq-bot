# Деплой NOEMA на Amvera Cloud

Бот работает через long polling: ему **не нужны домен, HTTPS и входящий порт**. Страница «Сеть» на скриншоте для бота не нужна.

В проекте уже есть всё для Amvera:

- `Dockerfile` - сборка образа;
- `amvera.yml` - постоянное хранилище `/data`;
- `DB_PATH=/data/noema.sqlite3` - база не теряется при пересборке;
- `.gitignore` - `.env`, `.venv`, логи и база не попадут в Git.

---

## 1. Создай приложение

1. Открой [cloud.amvera.ru](https://cloud.amvera.ru).
2. Нажми **«Создать проект»**.
3. Выбери тип **«Приложение»**.
4. Название: `noema-bot` (или любое).
5. Тариф:
   - **Пробный** - можно попробовать, но 100 МБ ОЗУ может быть мало;
   - **Начальный** - 500 МБ ОЗУ, стабильнее для бота (около 290 ₽ / 30 дней).
6. Нажми **«Далее»**.

Домен и «Сеть» не настраивай. Бот сам подключается к Telegram.

---

## 2. Загрузи код через Git

В проекте уже создан Git-коммит. Осталось добавить remote Amvera и запушить.

На странице проекта Amvera открой **«Репозиторий»** и скопируй команду клонирования вида:

```text
https://git.amvera.ru/ТВОЙ_ЛОГИН/ИМЯ_ПРОЕКТА
```

В PowerShell:

```powershell
cd C:\Users\user\Desktop\tg-iq-bot

git remote add amvera https://git.amvera.ru/ТВОЙ_ЛОГИН/ИМЯ_ПРОЕКТА
git push -u amvera master
```

Если remote уже добавлен:

```powershell
git remote set-url amvera https://git.amvera.ru/ТВОЙ_ЛОГИН/ИМЯ_ПРОЕКТА
git push -u amvera master
```

При запросе введи логин и пароль Amvera. Пароль от Telegram и данные карты не нужны.

После push Amvera автоматически начнёт сборку.

---

## 3. Добавь переменные окружения

В проекте Amvera открой раздел **«Переменные»** и добавь:

| Имя | Значение | Секрет |
|---|---|---|
| `BOT_TOKEN` | токен из @BotFather | да |
| `ADMIN_IDS` | твой Telegram ID | нет |
| `PAYMENT_SECRET` | длинная случайная строка | да |
| `PRICE_STARS` | `50` | нет |
| `TIMEZONE` | `Europe/Moscow` | нет |
| `LOG_LEVEL` | `INFO` | нет |
| `BRAND` | `NOEMA` | нет |
| `SUPPORT_CONTACT` | `@твой_ник` или пусто | нет |
| `PYTHONUNBUFFERED` | `1` | нет |

`BOT_TOKEN` и `PAYMENT_SECRET` лучше добавить именно как **секреты**, а не обычные переменные.

После добавления переменных нажми **«Перезапустить»** или запусти пересборку.

---

## 4. Проверь запуск

На странице проекта смотри:

1. **Лог сборки** - установка зависимостей.
2. **Лог приложения** - запуск бота.

Успешный лог выглядит примерно так:

```text
INFO | bot.main | Подключение установлено: @VEL_YOU_IQ_BOT
INFO | bot.main | NOEMA запущен. База: /data/noema.sqlite3
INFO | aiogram.dispatcher | Start polling
```

После этого открой бота в Telegram и нажми `/start`.

---

## 5. Останови локальный бот

**Очень важно:** два экземпляра одного бота одновременно не работают. Telegram выдаст ошибку `TerminatedByOtherGetUpdates` или `409 Conflict`.

Перед запуском облачной версии останови локальную:

```powershell
Stop-Process -Id (Get-Content data\bot.pid) -Force
```

Если процесс уже остановлен, команда просто выдаст ошибку - это нормально.

---

## 6. Перенеси текущую базу на Amvera (по желанию)

Если хочешь сохранить пользователей, тесты и оплаты, которые уже есть локально:

1. Локальный бот должен быть остановлен.
2. В папке проекта уже лежит консистентный бэкап:

```text
data/noema-upload.sqlite3
```

Если его нет, создай заново:

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; s=sqlite3.connect('data/noema.sqlite3'); d=sqlite3.connect('data/noema-upload.sqlite3'); s.backup(d); d.close(); s.close()"
```

3. В Amvera открой **«Репозиторий» → Data → «Загрузить данные»**.
4. Загрузи `data/noema-upload.sqlite3` в корень `/data`.
5. В переменных добавь:

```text
DB_PATH=/data/noema-upload.sqlite3
```

6. Перезапусти приложение.

Если переносить базу не нужно, оставь `DB_PATH` из Dockerfile: `/data/noema.sqlite3`. База создастся пустой автоматически.

---

## Частые ошибки

### Бот молчит, в логах `409 Conflict` / `TerminatedByOtherGetUpdates`

Локальный бот всё ещё работает. Останови его:

```powershell
Stop-Process -Id (Get-Content data\bot.pid) -Force
```

### В логах `BOT_TOKEN не задан`

Переменная `BOT_TOKEN` не добавлена в Amvera или контейнер не перезапущен после её добавления.

### В логах `ADMIN_IDS не задан`

Добавь свой Telegram ID в переменную `ADMIN_IDS`.

### Проект перезапускается по памяти

Пробного тарифа может не хватить. Перейди на **«Начальный»** (500 МБ ОЗУ).

### Не сохраняются пользователи после пересборки

Проверь, что:

- `amvera.yml` содержит `run.persistenceMount: /data`;
- база лежит именно в `/data`, а не в `/app/data`;
- в переменных не переопределён `DB_PATH` на относительный путь.

### Платёж Stars не проходит

Проверь `PRICE_STARS=50`, `PAYMENT_SECRET` и логи `pre_checkout`. Оплата в Stars не требует домена и внешнего платёжного провайдера.

---

## Обновление бота

После изменений локально:

```powershell
git add .
git commit -m "update"
git push amvera master
```

Amvera сама пересоберёт проект. База в `/data` сохранится.
