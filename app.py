"""
PifPaf Creators — Flask-бэкенд (порт с Node.js server.js).

Заменяет server.js. Полностью совместим с фронтендом в /static.
Запуск:  py app.py   (или  python app.py)

Данные рилсов подтягиваются из Instagram через Apify API (бесплатная квота).
Для реальной интеграции задайте переменные окружения:
  APIFY_TOKEN     — ваш ключ Apify  (обязательно)
  APIFY_ACTOR_ID  — ID актора (по умолчанию apify/instagram-scraper)
  APIFY_BUDGET    — бюджет в центах на запрос (по умолчанию 10)

Эти же переменные можно прописать в .env — файл подхватывается автоматически
через python-dotenv, или задать в системе/докер-контейнере.

Если APIFY_TOKEN не задан, приложение работает в демо-режиме:
данные (просмотры, лайки, обложка, дата) имитируются, чтобы сайт
можно было посмотреть офлайн без токена.
"""

import os
import random
import json
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')

app = Flask(__name__, static_folder=None)
# Отключаем стандартную раздачу статики Flask — раздаём сами из /static.
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# ---------- Загрузка переменных окружения из .env ----------
# Файл .env рядом с app.py. Существующие переменные окружения
# имеют приоритет над значениями из файла (override=False по умолчанию).
load_dotenv(os.path.join(BASE_DIR, '.env'))

# ---------- Хелперы ----------
def my_iso(value):
    """Приводит дату к единому ISO-формату (или пустая строка)."""
    if not value:
        return ''
    # Если пришёл ISO с 'Z' в конце — оставляем как есть (JS-парсер поймёт).
    if isinstance(value, str):
        return value.replace(' ', 'T')
    # Если timestamp (число секунд/мс) — конвертируем.
    try:
        ts = float(value)
        if ts > 1e12:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
    except (TypeError, ValueError, OSError):
        return str(value)


def thumbnail_fallback(url):
    """Заглушка-обложка, когда скрапер не отдал imageUrl (для демо)."""
    seed = 0
    for ch in url:
        seed = (seed * 31 + ord(ch)) % 1000000
    return f'https://picsum.photos/seed/{seed}/400/500'


# ---------- Конфигурация Apify ----------
# Ключ API берётся из переменной окружения APIFY_TOKEN.
# Если его нет — данные имитируются, чтобы демо работало офлайн.
APIFY_TOKEN = os.environ.get('APIFY_TOKEN', '').strip()
# Какой актор использовать: apify/instagram-scraper (нужен логин/пароль в input)
# или любой другой совместимый публичный скрапер Instagram/Reels.
APIFY_ACTOR_ID = os.environ.get('APIFY_ACTOR_ID', 'apify/instagram-scraper').strip()
# Запас активных исполнителей, который мы готовы тратить на один запрос (cents).
# Для бесплатного плана ставьте 10–15 кр.
APIFY_BUDGET = os.environ.get('APIFY_BUDGET', '10')


def _apify_fetch(url):
    """Вызывает актор Apify синхронно и возвращает список items (dict).

    Использует run-sync-get-dataset-items — один HTTP-запрос, который сам
    запускает актор, ждёт завершения и отдаёт данные. Идеален для бесплатной
    квоты: нет фоновых задач, деpжим функцию в рамках одного хэндлера.

    Возвращает list или None (если Apify не настроен / ошибся).
    """
    if not APIFY_TOKEN:
        return None

    input_payload = {
        'directUrls': [url],
        'resultsType': 'details',
        'resultsLimit': 1,
    }

    # ID актора нормализуем: 'apify/name' -> 'apify~name' и квотируем целиком.
    # Иначе слэш остаётся в пути (/v2/acts/apify/name/run-...) и API даёт 404.
    actor = urllib.parse.quote(APIFY_ACTOR_ID.strip().replace('/', '~'), safe='')
    api = (
        'https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?'
        'token={token}&format=json&timeout=180&budget={budget}'
    ).format(
        actor=actor,
        token=urllib.parse.quote(APIFY_TOKEN),
        budget=APIFY_BUDGET,
    )

    req = urllib.request.Request(
        api,
        data=json.dumps(input_payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=200) as resp:
            body = resp.read().decode('utf-8')
        return json.loads(body)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError) as exc:
        print(f'[Apify] Ошибка подтягивания данных: {exc}')
        return None


def parse_apify_item(item, url=''):
    """Вытаскивает нужные поля из item'а Instagram-скрапера Apify."""
    if not isinstance(item, dict):
        return None

    def num(*keys, default=0):
        for k in keys:
            v = item.get(k)
            if isinstance(v, (int, float)):
                return int(v)
        return default

    # Метаданные часто лежат либо в корне, либо в item['item'].
    meta = item.get('item') if isinstance(item.get('item'), dict) else item

    caption = (item.get('caption') or meta.get('caption') or '').strip()
    if not caption and item.get('caption2'):
        caption = item['caption2']
    caption = caption or 'Новый рилс'

    views = num('views', 'playCount', 'play_count')
    likes = num('likes', 'likesCount', 'likeCount')
    comments = num('comments', 'commentsCount', 'commentCount')

    thumbnail = (
        item.get('imageUrl')
        or item.get('displayUrl')
        or meta.get('displayUrl')
        or item.get('thumbnail')
        or meta.get('imageUrl')
    ) or ''

    posted_at = (
        item.get('timestamp')
        or item.get('postedAt')
        or meta.get('timestamp')
    ) or ''

    # Если провайдер ничего не вернул — фолбек на имитацию не делаем тут,
    # вернём None, чтобы обработчик понял, что данных нет.
    if not views and not likes:
        return None

    return {
        'caption': caption,
        'views': views,
        'likes': likes,
        'comments': comments,
        'thumbnail': thumbnail or thumbnail_fallback(url),
        'posted_at': my_iso(posted_at),
    }

def _apify_run(payload):
    """Вызывает актор Apify синхронно с произвольным payload и возвращает items.

    Возвращает list либо None (нет токена / актор ошибся).
    """
    if not APIFY_TOKEN:
        return None
    actor = urllib.parse.quote(APIFY_ACTOR_ID.strip().replace('/', '~'), safe='')
    api = (
        'https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?'
        'token={token}&format=json&timeout=180&budget={budget}'
    ).format(
        actor=actor,
        token=urllib.parse.quote(APIFY_TOKEN),
        budget=APIFY_BUDGET,
    )
    req = urllib.request.Request(
        api,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=200) as resp:
            body = resp.read().decode('utf-8')
        return json.loads(body)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError) as exc:
        print(f'[Apify] Ошибка: {exc}')
        return None


def _apify_fetch(url):
    """(совместимость) Одиночный рилс по прямой ссылке."""
    return _apify_run({
        'directUrls': [url],
        'resultsType': 'details',
        'resultsLimit': 1,
    })


def _apify_fetch_profile(handle):
    """Тянет профиль аккаунта + его посты/рилсы через Apify.

    handle: юзернейм без @  (например 'anna.smirnova')
    """
    return _apify_run({
        'usernames': [handle],
        'resultsType': 'posts',
        'resultsLimit': 15,
        'postsLimit': 15,
    })


def thumbnail_fallback_stable(seed_text):
    seed = 0
    for ch in str(seed_text):
        seed = (seed * 31 + ord(ch)) % 1000000
    return f'https://picsum.photos/seed/{seed}/400/500'


def parse_profile(items):
    """Разбирает ответ Apify на импорт аккаунта.

    Ожидаем список item'ов: первый — профиль, в остальных лежат посты (поля
    'posts' или 'items'). Возвращает dict:
      { username, name, avatar, bio, followers, url, reels: [...] }
    Если данных нет — None.
    """
    if not isinstance(items, list) or not items:
        return None

    first = items[0]
    if not isinstance(first, dict):
        return None

    meta = first.get('item') if isinstance(first.get('item'), dict) else first

    # Профиль-поля
    profile = first.get('profile') if isinstance(first.get('profile'), dict) else first
    handle = (profile or {}).get('username') or meta.get('username') or ''
    name = (profile or {}).get('fullName') or meta.get('fullName') or handle or 'Аккаунт'
    avatar = (profile or {}).get('picurl') or meta.get('profilePicUrl') or meta.get('avatar') or ''
    bio = (profile or {}).get('bio') or meta.get('bio') or ''
    insta_url = f'https://www.instagram.com/{handle}' if handle else ''

    posts = []
    for it in items:
        it_meta = it.get('item') if isinstance(it.get('item'), dict) else it
        if it_meta.get('type') == 'Video' or it_meta.get('is_video') or it_meta.get('mediaType') == 2:
            posts.append(it_meta)
        else:
            # у некоторых акторов посты живут в it.posts / it.itemsPosts
            for sub in (it.get('posts') or it.get('items') or []):
                if isinstance(sub, dict):
                    posts.append(sub)

    reels = []
    for p in posts:
        inner = p.get('item') if isinstance(p.get('item'), dict) else p
        r = parse_apify_item(p, insta_url)
        if r is None:
            # Пытаемся из вложенного item
            r = parse_apify_item(inner, insta_url)
        if r:
            r_url = p.get('url') or p.get('shortCode') or inner.get('url') or ''
            r['url'] = r_url
            reels.append(r)

    if not reels:
        return None

    return {
        'handle': handle,
        'name': name,
        'avatar': avatar,
        'bio': bio,
        'url': insta_url,
        'reels': reels,
    }


# ---------- Хелперы / middleware ----------
def get_json():
    """Возвращает JSON из тела запроса (или пустой dict)."""
    if not request.is_json:
        return {}
    return request.get_json(silent=True) or {}


# ============ Импорт аккаунта по ссылке ============
def parse_handle(raw):
    """Извлекает юзернейм из 'https://instagram.com/handle/', '@handle' или 'handle'."""
    s = (raw or '').strip().rstrip('/')
    if '@' in s:
        s = s.split('@')[-1]
    # режем до последнего важного сегмента после instagram.com
    if 'instagram.com' in s.lower():
        # берём часть после 'instagram.com/'
        idx = s.lower().find('instagram.com')
        s = s[idx + len('instagram.com'):].lstrip('/')
    # обрезаем по первым / ? #
    for ch in ('/', '?', '#'):
        if ch in s:
            s = s.split(ch)[0]
    return s.strip().strip('@')


def demo_account(handle='demo_creator'):
    """Демо-аккаунт с сгенерированными рилсами (офлайн-режим без Apify)."""
    names_map = {
        'anna': 'Анна Смирнова',
        'misha': 'Миша Ковалёв',
        'liza': 'Лиза Петрова',
    }
    name = names_map.get(handle, (handle or 'Демо Креатор').replace('_', ' ').title())
    reels = []
    captions = [
        'Тренд недели: как это снять? 🔥',
        'Фотосессия в один клик 📸',
        'Мой лучший рилс этого месяца ✨',
        'Backstage моего блога 🎬',
        'Короткий лайфхак для тебя 💡',
    ]
    base_views = random.randint(20000, 90000)
    for i in range(5):
        views = int(base_views * (1 - i * 0.12))
        reels.append({
            'caption': captions[i],
            'views': views,
            'likes': int(views * 0.07),
            'comments': int(views * 0.003),
            'thumbnail': thumbnail_fallback_stable(f'{handle}-{i}'),
            'posted_at': (datetime.now(timezone.utc) - timedelta(days=i * 4)).strftime('%Y-%m-%dT%H:%M:%S') + 'Z',
            'url': f'https://www.instagram.com/reel/demo{i}/',
        })
    return {
        'handle': handle or 'demo_creator',
        'name': name,
        'avatar': f'https://i.pravatar.cc/150?img={random.randint(10, 60)}',
        'bio': 'Креатор · снимаю тренды',
        'url': f'https://www.instagram.com/{handle or "demo_creator"}',
        'reels': reels,
    }


@app.route('/api/account/import', methods=['POST'])
def import_account():
    body = get_json()
    raw = (body.get('url') or body.get('username') or body.get('handle') or '').strip()
    if not raw:
        return jsonify(error='Вставьте ссылку на аккаунт Instagram'), 400
    handle = parse_handle(raw)
    if not handle:
        return jsonify(error='Не смог распознать юзернейм. Пример: https://instagram.com/anna.smirnova'), 400

    account = None
    live = False
    if APIFY_TOKEN:
        items = _apify_fetch_profile(handle)
        account = parse_profile(items) if items else None
        if account:
            live = True
        else:
            print('[Apify] Профиль не найден или пустой. Использую демо-режим.')

    if account is None:
        # Демо-режим (нет токена / скрапер вернул пусто)
        account = demo_account(handle)

    return jsonify(account=account, live=live, handle=handle)


@app.route('/api/account/demo', methods=['GET'])
def get_demo_account():
    return jsonify(account=demo_account('demo_creator'), live=False)


# ---------- Статика + SPA fallback ----------
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def spa(path):
    # Если запрашивают реальный файл из /static — отдаём его
    if path and os.path.isfile(os.path.join(STATIC_DIR, path)):
        return send_from_directory(STATIC_DIR, path)
    # Иначе — SPA fallback на index.html
    return send_from_directory(STATIC_DIR, 'index.html')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    print(f'PifPaf Creators запущен на http://localhost:{port}')
    app.run(host='127.0.0.1', port=port, debug=False)