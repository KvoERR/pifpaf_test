# PifPaf Creators

Дашборд для блоггеров: импорт Instagram-аккаунта по ссылке, статистика рилсов
(просмотры, лайки, комментарии, даты) через Apify API. Бэкенд — Flask,
фронтенд — статика в `/static`.

## Локальный запуск

```bash
py -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env         # и вписать APIFY_TOKEN
py app.py                      # http://localhost:3000
```

Без `APIFY_TOKEN` приложение работает с демо-данными.

## Переменные окружения

| Переменная       | Обязательна | По умолчанию              | Описание                          |
|------------------|-------------|---------------------------|-----------------------------------|
| `APIFY_TOKEN`    | да (для live)| —                        | Токен console.apify.com           |
| `APIFY_ACTOR_ID` | нет         | `apify/instagram-scraper` | Актор-скрапер                     |
| `APIFY_BUDGET`   | нет         | `10`                      | Бюджет запроса, центы             |
| `PORT`           | нет         | `3000`                    | Порт (на Railway задаётся сам)    |

Локально значения можно класть в `.env` (см. `.env.example`). На Railway —
в **Variables** сервиса.

## Деплой на Railway

1. Запушьте репозиторий на GitHub.
2. [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo** → выберите репозиторий.
3. Railway соберёт проект автоматически (Nixpacks увидит `requirements.txt` и запустит команду из `Procfile`).
4. В сервисе откройте **Variables** и добавьте:
   - `APIFY_TOKEN` — токен из [console.apify.com](https://console.apify.com/settings/integrations)
   - опционально `APIFY_BUDGET`
5. После деплоя: **Settings → Networking → Generate Domain** — получите публичный URL.

Healthcheck-эндпоинт: `/health`.

### Почему Procfile такой

Импорт аккаунта ждёт завершения актора Apify до ~3 минут, поэтому
`--timeout 300` (иначе gunicorn убивает воркер по умолчанию через 30 c).
`0.0.0.0:$PORT` — обязательная привязка в облаке. Воркеры/треды дают
параллельность при долгих запросах.

### Особенности картинок

В некоторых сетях CDN Инстаграма и часть photo-сервисов недоступны
(DNS-блокировки), поэтому обложки рилсов и аватары отдаются как локальные
SVG-заглушки, а фото на главной сервер качает сам (`loremflickr`) со
SVG-фолбэком. Реальные данные (просмотры/лайки/даты) при этом настоящие.

## Диагностика

- `python apify_check.py` — проверка токена и актора Apify.
- `python test_images.py` — тесты картинок (локальные заглушки + лендинг).
- `python test_import_live.py` — сквозной импорт реального аккаунта
  (тратит квоту Apify!).
