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
import hashlib
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
    """Заглушка-обложка рилса: рисуем сами, никаких внешних загрузок.

    Детерминированно по url: один и тот же рилс всегда получает одну и ту же
    картинку (цвет градиента зависит от сида).
    """
    return f'/img/reel/{thumbnail_fallback_stable(url)}'


def thumbnail_fallback_stable(seed_text):
    """Детерминированный короткий сид из произвольного текста."""
    return hashlib.md5(str(seed_text).encode('utf-8')).hexdigest()[:12]


# Палитры для генерируемых заглушек (обложки/аватары рисуем сами,
# ничего не подгружаем из интернета).
_PLACEHOLDER_PALETTES = [
    ('#3479ff', '#a78bfa'),
    ('#f472b6', '#fb923c'),
    ('#10b981', '#34d399'),
    ('#f59e0b', '#f97316'),
    ('#8b5cf6', '#6366f1'),
    ('#06b6d4', '#3b82f6'),
]


def _svg_reel_cover(seed_text):
    """Рисует SVG-обложку рилса: градиент по сиду + кнопка play."""
    digest = hashlib.md5(str(seed_text).encode('utf-8')).digest()
    c1, c2 = _PLACEHOLDER_PALETTES[digest[0] % len(_PLACEHOLDER_PALETTES)]
    angle = digest[1] % 360
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="500" '
        'viewBox="0 0 400 500" preserveAspectRatio="xMidYMid slice">'
        '<defs><linearGradient id="g" gradientTransform="rotate(%d 0.5 0.5)">'
        '<stop offset="0%%" stop-color="%s"/><stop offset="100%%" stop-color="%s"/>'
        '</linearGradient></defs>'
        '<rect width="400" height="500" fill="url(#g)"/>'
        '<circle cx="330" cy="70" r="110" fill="rgba(255,255,255,0.14)"/>'
        '<circle cx="60" cy="440" r="90" fill="rgba(255,255,255,0.10)"/>'
        '<circle cx="200" cy="250" r="52" fill="rgba(15,23,42,0.35)"/>'
        '<polygon points="185,225 235,250 185,275" fill="#ffffff"/>'
        '</svg>'
    ) % (angle, c1, c2)


def _svg_avatar(seed_text):
    """Рисует SVG-аватар: градиентный круг с первой буквой сида."""
    digest = hashlib.md5(str(seed_text).encode('utf-8')).digest()
    c1, c2 = _PLACEHOLDER_PALETTES[digest[2] % len(_PLACEHOLDER_PALETTES)]
    letter = (str(seed_text).strip()[:1] or 'P').upper()
    if not letter.isalnum():
        letter = 'P'
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="150" height="150" viewBox="0 0 150 150">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0%%" stop-color="%s"/><stop offset="100%%" stop-color="%s"/>'
        '</linearGradient></defs>'
        '<rect width="150" height="150" fill="url(#g)"/>'
        '<text x="75" y="97" font-family="Manrope,Arial,sans-serif" font-size="64" '
        'font-weight="800" fill="#ffffff" text-anchor="middle">%s</text>'
        '</svg>'
    ) % (c1, c2, letter)


# ---------- Настоящие фото на лендинге ----------
# На главной оставляем реальные фотографии: сервер сам качает кадр
# с loremflickr (этот сервис доступен из этой сети, в отличие от picsum/
# unsplash) и отдаёт байты браузеру. Если скачать не удалось — тихо
# подменяем на локальную SVG-заглушку, картинка никогда не «ломается».
_LANDING_TOPICS = ['nature', 'travel', 'city', 'beach', 'mountains', 'sunset']
_IMG_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
           '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
_PHOTO_CACHE = {}


@app.route('/img/photo/<seed>')
def img_photo_real(seed):
    """Фотография для главной страницы: качаем сами, фолбэк — SVG."""
    cached = _PHOTO_CACHE.get(seed)
    if not cached:
        digest = hashlib.md5(str(seed).encode('utf-8')).digest()
        topic = _LANDING_TOPICS[digest[0] % len(_LANDING_TOPICS)]
        lock = int.from_bytes(digest[1:4], 'big') % 9999
        url = f'https://loremflickr.com/600/760/{topic}?lock={lock}'
        data = b''
        ctype = 'image/jpeg'
        ok_img = False
        try:
            req = urllib.request.Request(url, headers={'User-Agent': _IMG_UA})
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = resp.read(10 * 1024 * 1024)
                ctype = resp.headers.get('Content-Type', 'image/jpeg').split(';')[0]
                ok_img = bool(data) and (data[:2] == b'\xff\xd8' or 'image' in ctype)
        except Exception:
            ok_img = False
        if not ok_img:
            # Не скачалось — SVG-заглушка, чтобы главная всегда была красивой.
            resp = app.response_class(_svg_reel_cover(seed),
                                      mimetype='image/svg+xml')
            resp.headers['Cache-Control'] = 'public, max-age=300'
            return resp
        if len(_PHOTO_CACHE) > 40:
            _PHOTO_CACHE.clear()
        _PHOTO_CACHE[seed] = (data, ctype)
    else:
        data, ctype = cached
    resp = app.response_class(data, mimetype=ctype)
    resp.headers['Cache-Control'] = 'public, max-age=86400'
    return resp


# ---------- Конфигурация Apify ----------
# Ключ API берётся из переменной окружения APIFY_TOKEN.
# Если его нет — данные имитируются, чтобы демо работало офлайн.
APIFY_TOKEN = os.environ.get('APIFY_TOKEN', '').strip()
# Какой актор использовать: apify/instagram-scraper (вход через directUrls,
# без логина) или любой другой совместимый публичный скрапер Instagram/Reels.
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

    views = num('views', 'playCount', 'play_count', 'videoViewCount', 'viewCount')
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
        'thumbnail': thumbnail_fallback(url),
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
    """Тянет посты/рилсы аккаунта через Apify.

    handle: юзернейм без @  (например 'anna.smirnova')

    ВАЖНО: у актуального apify/instagram-scraper НЕТ поля 'usernames' во входной
    схеме — адрес задаётся только через directUrls. С 'usernames' актор не находит
    ни одной ссылки и отвечает {'error': 'no_items'}, из-за чего приложение
    молча уходило в демо-режим.
    """
    return _apify_run({
        'directUrls': [f'https://www.instagram.com/{handle}/'],
        'resultsType': 'posts',
        'resultsLimit': 15,
    })


def _apify_fetch_details(handle):
    """Тянет метаданные профиля (аватар, био, имя, подписчики) через Apify."""
    return _apify_run({
        'directUrls': [f'https://www.instagram.com/{handle}/'],
        'resultsType': 'details',
        'resultsLimit': 1,
    })


# ---------- Картинки-обложки (реальные фото) ----------


def parse_profile(items):
    """Разбирает ответ Apify на импорт аккаунта.

    Ожидаем список item'ов с постами (resultsType='posts') либо первый item
    с деталями профиля (resultsType='details'). Поля актуального
    instagram-scraper: type/productType, videoViewCount, likesCount,
    commentsCount, displayUrl, timestamp, shortCode, ownerUsername.
    Возвращает dict:
      { handle, name, avatar, bio, url, reels: [...] }
    Если данных нет — None.
    """
    if not isinstance(items, list) or not items:
        return None

    first = items[0]
    if not isinstance(first, dict):
        return None

    meta = first.get('item') if isinstance(first.get('item'), dict) else first

    # Профиль-поля: у instagram-scraper имя/юзернейм приходят из details-item
    # (username/fullName) либо из полей ownerUsername/ownerFullName постов.
    profile = first.get('profile') if isinstance(first.get('profile'), dict) else {}

    def _first(*vals):
        for v in vals:
            if v:
                return v
        return ''

    handle = _first(
        profile.get('username'),
        first.get('username'), meta.get('username'),
        first.get('ownerUsername'), meta.get('ownerUsername'),
    )
    name = _first(
        profile.get('fullName'),
        first.get('fullName'), meta.get('fullName'),
        first.get('ownerFullName'), meta.get('ownerFullName'),
        handle, 'Аккаунт',
    )
    bio = _first(
        profile.get('bio'), profile.get('biography'),
        meta.get('bio'), meta.get('biography'),
    )
    insta_url = f'https://www.instagram.com/{handle}' if handle else ''
    # Аватар — всегда локальная SVG-заглушка: внешние картинки не подгружаем.
    avatar = f'/img/avatar/{handle or "user"}'

    posts = []
    for it in items:
        it_meta = it.get('item') if isinstance(it.get('item'), dict) else it
        if it_meta.get('error'):
            continue  # элемент-заглушка с ошибкой актора
        if (it_meta.get('type') == 'Video' or it_meta.get('is_video')
                or it_meta.get('mediaType') == 2 or it_meta.get('productType') == 'clips'):
            posts.append(it_meta)
        else:
            # у некоторых акторов посты живут в it.posts / it.itemsPosts
            for sub in (it.get('posts') or it.get('items') or []):
                if isinstance(sub, dict):
                    posts.append(sub)

    reels = []
    for p in posts:
        inner = p.get('item') if isinstance(p.get('item'), dict) else p
        r_url = p.get('url') or p.get('shortCode') or inner.get('url') or ''
        # В генератор заглушки передаём уникальный url рилса, а не общий
        # профильный — иначе все обложки-плейсхолдеры будут одинаковыми.
        seed_url = r_url or insta_url
        r = parse_apify_item(p, seed_url)
        if r is None:
            # Пытаемся из вложенного item
            r = parse_apify_item(inner, seed_url)
        if r:
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


def apply_profile_details(account, det_item):
    """Дополняет аккаунт метаданными из details-ответа Apify (best-effort).

    Картинки не трогаем: аватар остаётся локальной заглушкой /img/avatar/.
    """
    if not isinstance(account, dict) or not isinstance(det_item, dict):
        return
    if det_item.get('username'):
        account['handle'] = det_item['username']
    if det_item.get('fullName'):
        account['name'] = det_item['fullName']
    account['avatar'] = f"/img/avatar/{account.get('handle') or 'user'}"
    bio_txt = det_item.get('biography') or det_item.get('bio')
    if bio_txt:
        account['bio'] = bio_txt
    if det_item.get('url'):
        account['url'] = det_item['url']
    followers = det_item.get('followersCount')
    if isinstance(followers, (int, float)):
        account['followers'] = int(followers)


@app.route('/img/reel/<seed>')
def img_reel_cover(seed):
    """SVG-обложка рилса по сиду — рисуем сами, без внешних запросов."""
    resp = app.response_class(_svg_reel_cover(seed), mimetype='image/svg+xml')
    resp.headers['Cache-Control'] = 'public, max-age=604800'
    return resp


@app.route('/img/avatar/<seed>')
def img_avatar(seed):
    """SVG-аватар по сиду."""
    resp = app.response_class(_svg_avatar(seed), mimetype='image/svg+xml')
    resp.headers['Cache-Control'] = 'public, max-age=604800'
    return resp


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
            'thumbnail': thumbnail_fallback(f'{handle}-{i}'),
            'posted_at': (datetime.now(timezone.utc) - timedelta(days=i * 4)).strftime('%Y-%m-%dT%H:%M:%S') + 'Z',
            'url': f'https://www.instagram.com/reel/demo{i}/',
        })
    return {
        'handle': handle or 'demo_creator',
        'name': name,
        'avatar': f'/img/avatar/{handle or "demo_creator"}',
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
        raw_items = _apify_fetch_profile(handle)
        items = [i for i in (raw_items or []) if isinstance(i, dict) and not i.get('error')]
        account = parse_profile(items) if items else None
        if account:
            live = True
            # Аватар/био/имя живут в details — тянем вторым коротким запросом
            # (best-effort: без него аккаунт всё равно собирается из постов).
            det = _apify_fetch_details(handle) or []
            det_item = next((d for d in det if isinstance(d, dict) and not d.get('error')), None)
            apply_profile_details(account, det_item)
        else:
            errors = [i.get('errorDescription') or i.get('error')
                      for i in (raw_items or [])
                      if isinstance(i, dict) and i.get('error')]
            why = '; '.join(dict.fromkeys(errors)) if errors else 'актор вернул пустой датасет'
            print(f'[Apify] Профиль не получен ({why}). Использую демо-режим.')

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