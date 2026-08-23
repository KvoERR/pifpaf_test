"""
PifPaf Creators — Flask-бэкенд (порт с Node.js server.js).

Заменяет server.js. Полностью совместим с фронтендом в /static.
Запуск:  py app.py   (или  python app.py)
"""

import os
import random
import sqlite3
from datetime import datetime, timedelta

from flask import Flask, jsonify, request, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
DB_PATH = os.path.join(BASE_DIR, 'data.db')

app = Flask(__name__, static_folder=None)
# Отключаем стандартную раздачу статики Flask — раздаём сами из /static.
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

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
    caption = (body.get('caption') or '').strip() or 'Новый рилс'

    # Имитация данных из Instagram API (реальная интеграция при наличии ключа)
    views = random.randint(5000, 155000)
    likes = int(views * 0.06)
    comments = int(views * 0.003)
    posted_at = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
    thumbnail = f'https://picsum.photos/seed/new{int(datetime.utcnow().timestamp() * 1000)}/400/500'

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
        views=views, likes=likes, comments=comments, posted_at=posted_at
    )


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