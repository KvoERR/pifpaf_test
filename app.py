"""
PifPaf Creators — Flask-бэкенд (порт с Node.js server.js).

Заменяет server.js. Полностью совместим с фронтендом в /static.
Запуск:  py app.py   (или  python app.py)

Данные рилсов подтягиваются из Instagram через Apify API (бесплатная квота).
Для реальной интеграции задайте переменные окружения:
  APIFY_TOKEN     — ваш ключ Apify  (обязательно)
  APIFY_ACTOR_ID  — ID актора (по умолчанию apify/instagram-scraper)
  APIFY_BUDGET    — бюджет в центах на запрос (по умолчанию 10)

Эти же переменные можно прописать в .env (если запускаете с python-dotenv)
или задать в системе/докер-контейнере. Пример — в .env.example.

Если APIFY_TOKEN не задан, приложение работает в демо-режиме:
данные (просмотры, лайки, обложка, дата) имитируются, чтобы сайт
можно было посмотреть офлайн без токена.
"""

import os
import random
import json
import sqlite3
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta

from flask import Flask, jsonify, request, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
DB_PATH = os.path.join(BASE_DIR, 'data.db')

app = Flask(__name__, static_folder=None)
# Отключаем стандартную раздачу статики Flask — раздаём сами из /static.
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# ---------- Лёгкий загрузчик .env (без python-dotenv) ----------
def load_dotenv(path=None):
    """Читает файл .env формата KEY=VALUE и кладёт в os.environ (не перезаписывая)."""
    env_path = path or os.path.join(BASE_DIR, '.env')
    if not os.path.isfile(env_path):
        return
    try:
        with open(env_path, 'r', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, val = line.partition('=')
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except OSError:
        pass


load_dotenv()

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
        return datetime.utcfromtimestamp(ts).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
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

    api = (
        'https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?'
        'token={token}&format=json&status=SUCCEEDED&timeout=60&budget={budget}'
    ).format(
        actor=urllib.parse.quote(APIFY_ACTOR_ID),
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
        with urllib.request.urlopen(req, timeout=90) as resp:
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
    api = (
        'https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?'
        'token={token}&format=json&status=SUCCEEDED&timeout=90&budget={budget}'
    ).format(
        actor=urllib.parse.quote(APIFY_ACTOR_ID),
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
        with urllib.request.urlopen(req, timeout=120) as resp:
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


# ---------- База данных ----------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode = WAL')
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        name TEXT NOT NULL,
        avatar TEXT,
        bio TEXT,
        instagram TEXT,
        created_at TEXT DEFAULT (datetime('now'))
      );

      CREATE TABLE IF NOT EXISTS reels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        url TEXT NOT NULL,
        caption TEXT,
        thumbnail TEXT,
        views INTEGER DEFAULT 0,
        likes INTEGER DEFAULT 0,
        comments INTEGER DEFAULT 0,
        posted_at TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
      );

      CREATE TABLE IF NOT EXISTS stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reel_id INTEGER NOT NULL,
        views INTEGER DEFAULT 0,
        likes INTEGER DEFAULT 0,
        comments INTEGER DEFAULT 0,
        recorded_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (reel_id) REFERENCES reels(id)
      );
    ''')
    conn.commit()
    conn.close()
# ---------- Демо-данные ----------
def seed():
    conn = get_db()
    count = conn.execute('SELECT COUNT(*) as c FROM users').fetchone()['c']
    if count > 0:
        conn.close()
        return

    users = [
        ['anna', 'demo123', 'Анна Смирнова', 'https://i.pravatar.cc/150?img=47', 'Фотограф · мама · люблю тренды', '@anna.smirnova'],
        ['misha', 'demo123', 'Миша Ковалёв', 'https://i.pravatar.cc/150?img=12', 'Креатор · путешествия', '@misha.kovalev'],
        ['liza', 'demo123', 'Лиза Петрова', 'https://i.pravatar.cc/150?img=32', 'Бьюти-блогер', '@liza.petrova'],
    ]

    reels = [
        # Анна
        [1, 'https://www.instagram.com/reel/Cx1aB2cD3eF/', 'Тренд из Reels: фотосессия в один клик 🔥', 'https://picsum.photos/seed/anna1/400/500', 128400, 8420, 356, '2026-08-20T10:00:00Z'],
        [1, 'https://www.instagram.com/reel/Cx2bC3dE4fG/', 'Аватарка для профиля ✨', 'https://picsum.photos/seed/anna2/400/500', 45200, 3100, 128, '2026-08-18T15:30:00Z'],
        [1, 'https://www.instagram.com/reel/Cx3cD4eF5gH/', 'Парные фото с подругой 💕', 'https://picsum.photos/seed/anna3/400/500', 89300, 5600, 210, '2026-08-15T09:00:00Z'],
        # Миша
        [2, 'https://www.instagram.com/reel/Cy1dE5fG6hI/', 'Тренд недели: как это снять?', 'https://picsum.photos/seed/misha1/400/500', 210500, 15400, 890, '2026-08-21T18:00:00Z'],
        [2, 'https://www.instagram.com/reel/Cy2eF6gH7iJ/', 'Путешествие мечты 🏝️', 'https://picsum.photos/seed/misha2/400/500', 67400, 4300, 156, '2026-08-17T12:00:00Z'],
        # Лиза
        [3, 'https://www.instagram.com/reel/Cz1fG7hI8jK/', 'Бьюти-рутина за 60 секунд 💄', 'https://picsum.photos/seed/liza1/400/500', 156800, 9800, 420, '2026-08-22T08:00:00Z'],
        [3, 'https://www.instagram.com/reel/Cz2gH8iJ9kL/', 'Макияж для фотосессии', 'https://picsum.photos/seed/liza2/400/500', 38900, 2700, 98, '2026-08-16T14:00:00Z'],
    ]

    user_ids = {}
    for u in users:
        cur = conn.execute(
            'INSERT INTO users (username, password, name, avatar, bio, instagram) VALUES (?, ?, ?, ?, ?, ?)',
            u
        )
        user_ids[u[0]] = cur.lastrowid

    for r in reels:
        r = list(r)
        r[0] = user_ids[['anna', 'misha', 'liza'][r[0] - 1]]
        cur = conn.execute(
            'INSERT INTO reels (user_id, url, caption, thumbnail, views, likes, comments, posted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            r
        )
        reel_id = cur.lastrowid
        base = r[4]
        # История просмотров для графика (7 точек)
        for i in range(6, -1, -1):
            factor = 0.3 + (6 - i) * 0.1
            recorded = (datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d %H:%M:%S')
            conn.execute(
                'INSERT INTO stats (reel_id, views, likes, comments, recorded_at) VALUES (?, ?, ?, ?, ?)',
                (reel_id, int(base * factor), int(r[5] * factor), int(r[6] * factor), recorded)
            )

    conn.commit()
    conn.close()


init_db()
seed()
# ---------- Хелперы / middleware ----------
def get_json():
    """Возвращает JSON из тела запроса (или пустой dict)."""
    if not request.is_json:
        return {}
    return request.get_json(silent=True) or {}


def parse_cookie(header_value):
    """Простой парсер Cookie header: 'a=b; c=d' -> {'a': 'b'}."""
    cookies = {}
    if not header_value:
        return cookies
    for part in header_value.split(';'):
        if '=' in part:
            k, _, v = part.strip().partition('=')
            if k:
                cookies[k.strip()] = v.strip()
    return cookies


def get_session_user():
    """Возвращает dict пользователя по cookie 'session' либо None."""
    cookies = parse_cookie(request.headers.get('Cookie'))
    raw_id = cookies.get('session')
    if not raw_id:
        return None
    try:
        user_id = int(raw_id)
    except (TypeError, ValueError):
        return None

    conn = get_db()
    row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_session_cookie(resp, user_id):
    """Устанавливает httpOnly cookie 'session' на 7 дней (как в server.js)."""
    resp.set_cookie(
        'session',
        str(user_id),
        httponly=True,
        max_age=7 * 24 * 60 * 60,  # 1000*60*60*24*7 мс -> 7 суток в секундах
        samesite='Lax',
    )
    return resp
# ---------- API ----------

# Авторизация
@app.route('/api/login', methods=['POST'])
def login():
    body = get_json()
    username = body.get('username', '')
    password = body.get('password', '')

    conn = get_db()
    row = conn.execute(
        'SELECT * FROM users WHERE username = ? AND password = ?',
        (username, password)
    ).fetchone()
    conn.close()

    if row is None:
        return jsonify(error='Неверный логин или пароль'), 401

    user = dict(row)
    resp = jsonify(id=user['id'], username=user['username'], name=user['name'])
    return set_session_cookie(resp, user['id'])


@app.route('/api/logout', methods=['POST'])
def logout():
    resp = jsonify(ok=True)
    resp.delete_cookie('session')
    return resp


# Текущий пользователь
@app.route('/api/me', methods=['GET'])
def me():
    user = get_session_user()
    if user is None:
        return jsonify(error='Не авторизован'), 401
    return jsonify(
        id=user['id'], username=user['username'], name=user['name'],
        avatar=user['avatar'], bio=user['bio'], instagram=user['instagram']
    )


# Список блоггеров (для общей ленты)
@app.route('/api/users', methods=['GET'])
def list_users():
    conn = get_db()
    rows = conn.execute('''
        SELECT u.id, u.name, u.avatar, u.bio, u.instagram,
          (SELECT COUNT(*) FROM reels r WHERE r.user_id = u.id) as reel_count,
          (SELECT COALESCE(SUM(views), 0) FROM reels r WHERE r.user_id = u.id) as total_views
        FROM users u
    ''').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# Рилсы конкретного пользователя
@app.route('/api/users/<int:uid>/reels', methods=['GET'])
def user_reels(uid):
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM reels WHERE user_id = ? ORDER BY posted_at DESC', (uid,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# Рилсы текущего пользователя (для дашборда)
@app.route('/api/my/reels', methods=['GET'])
def my_reels():
    user = get_session_user()
    if user is None:
        return jsonify(error='Не авторизован'), 401
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM reels WHERE user_id = ? ORDER BY posted_at DESC', (user['id'],)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# Аналитика текущего пользователя
@app.route('/api/my/analytics', methods=['GET'])
def my_analytics():
    user = get_session_user()
    if user is None:
        return jsonify(error='Не авторизован'), 401

    conn = get_db()
    totals = conn.execute('''
        SELECT COUNT(*) as reel_count,
          COALESCE(SUM(views), 0) as total_views,
          COALESCE(SUM(likes), 0) as total_likes,
          COALESCE(SUM(comments), 0) as total_comments,
          COALESCE(AVG(views), 0) as avg_views
        FROM reels WHERE user_id = ?
    ''', (user['id'],)).fetchone()

    best = conn.execute(
        'SELECT * FROM reels WHERE user_id = ? ORDER BY views DESC LIMIT 1',
        (user['id'],)
    ).fetchone()

    timeline = conn.execute('''
        SELECT date(s.recorded_at) as day, SUM(s.views) as views
        FROM stats s JOIN reels r ON s.reel_id = r.id
        WHERE r.user_id = ?
        GROUP BY day ORDER BY day
    ''', (user['id'],)).fetchall()

    conn.close()

    return jsonify(
        totals=dict(totals),
        best=(dict(best) if best else None),
        timeline=[dict(t) for t in timeline]
    )
# Добавить рилс по ссылке (с имитацией подтягивания данных)
@app.route('/api/my/reels', methods=['POST'])
def add_my_reel():
    user = get_session_user()
    if user is None:
        return jsonify(error='Не авторизован'), 401

    body = get_json()
    url = (body.get('url') or '').strip()
    if not url:
        return jsonify(error='Укажите ссылку на рилс'), 400
    if not url.lower().startswith(('http://', 'https://')):
        return jsonify(error='Ссылка должна начинаться с http(s)://'), 400
    caption = (body.get('caption') or '').strip() or 'Новый рилс'

    # --- Подтягиваем данные из Instagram через Apify ---
    # Ход работы:
    #   1) Есть APIFY_TOKEN -> реальный скрапер, парсим ответ.
    #   2) Нет токена или скрапер вернул пусто -> имитируем (демо-режим).
    # Функция возвращает 201 с полем live: true/false, чтобы фронт показал источник.
    from_apify = False
    if APIFY_TOKEN:
        items = _apify_fetch(url)
        candidates = items if isinstance(items, list) else [items] if isinstance(items, dict) else []
        scraped = None
        for it in candidates:
            scraped = parse_apify_item(it, url)
            if scraped:
                break
        if scraped:
            caption = scraped['caption'] or caption
            views = scraped['views']
            likes = scraped['likes']
            comments = scraped['comments']
            thumbnail = scraped['thumbnail']
            posted_at = scraped['posted_at'] or datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
            from_apify = True
        else:
            # Скрапер сработал, но данных нет — падаем в имитацию.
            print('[Apify] Актор отработал, но данные не найдены. Использую демо-режим.')

    if not from_apify:
        # Демо-режим: имитируем данные из Instagram API (для офлайн/демо)
        views = random.randint(5000, 155000)
        likes = int(views * 0.06)
        comments = int(views * 0.003)
        if not caption or caption == 'Новый рилс':
            caption = 'Новый рилс'
        posted_at = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
        thumbnail = f'https://picsum.photos/seed/demo{int(datetime.utcnow().timestamp() * 1000)}/400/500'

    conn = get_db()
    cur = conn.execute(
        'INSERT INTO reels (user_id, url, caption, thumbnail, views, likes, comments, posted_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (user['id'], url, caption, thumbnail, views, likes, comments, posted_at)
    )
    reel_id = cur.lastrowid
    conn.execute(
        'INSERT INTO stats (reel_id, views, likes, comments) VALUES (?, ?, ?, ?)',
        (reel_id, views, likes, comments)
    )
    conn.commit()
    conn.close()

    return jsonify(
        id=reel_id, url=url, caption=caption, thumbnail=thumbnail,
        views=views, likes=likes, comments=comments, posted_at=posted_at,
        live=from_apify
    ), 201


# ============ Импорт аккаунта по ссылке (без авторизации) ============
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
            'posted_at': (datetime.utcnow() - timedelta(days=i * 4)).strftime('%Y-%m-%dT%H:%M:%S') + 'Z',
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