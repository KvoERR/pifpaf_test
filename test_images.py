# -*- coding: utf-8 -*-
"""Проверка: картинки — только локальные SVG-заглушки, внешних загрузок нет."""
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import app as appmod  # noqa: E402

client = appmod.app.test_client()
ok = True


def check(name, cond):
    global ok
    print(('PASS' if cond else 'FAIL'), '-', name)
    ok = ok and cond


# 1) Обложка по сиду: SVG с нашего сервера
r = client.get('/img/reel/hero-1')
svg = r.get_data(as_text=True)
check(f'GET /img/reel/hero-1 -> {r.status_code} svg', r.status_code == 200
      and r.content_type.startswith('image/svg+xml'))
check('валидный <svg> с градиентом и play',
      svg.lstrip().startswith('<svg') and 'linearGradient' in svg and 'polygon' in svg)
check('детерминирован (повтор тот же)',
      client.get('/img/reel/hero-1').data == r.data)
colors = {tuple(re.findall(r'stop-color="(#\w+)"', client.get(f'/img/reel/s{i}').get_data(as_text=True)))
          for i in range(8)}
print('   уникальных расцветок из 8 сидов:', len(colors))
check('разные сиды дают разные заглушки (>=4)', len(colors) >= 4)

# 2) Аватар по сиду: буква юзернейма
ra = client.get('/img/avatar/misha')
av = ra.get_data(as_text=True).replace('\n', '')
check(f'GET /img/avatar/misha -> {ra.status_code} svg', ra.status_code == 200
      and ra.content_type.startswith('image/svg+xml'))
check('аватар содержит букву M', '>M</text>' in av)

# 3) Демо-аккаунт: все пути локальные
data = client.get('/api/account/demo').get_json()
acc = data['account']
thumbs = [rl['thumbnail'] for rl in acc['reels']]
check(f'demo reels={len(thumbs)}', len(thumbs) == 5)
check('обложки демо — локальные /img/reel/', all(t.startswith('/img/reel/') for t in thumbs))
check('сиды обложек уникальны', len(set(thumbs)) == len(thumbs))
check('все обложки демо реально отдаются как SVG',
      all(client.get(t).content_type.startswith('image/svg') for t in thumbs))
check('аватар демо — локальный /img/avatar/', acc['avatar'].startswith('/img/avatar/'))

# 4) parse_apify_item: thumbnail всегда локальный, IG displayUrl игнорируется
item = {'type': 'Video', 'videoViewCount': 1000, 'likesCount': 50,
        'commentsCount': 5, 'displayUrl': 'https://scontent-x.cdninstagram.com/a.jpg',
        'timestamp': '2026-01-01T00:00:00.000Z', 'caption': 't'}
res = appmod.parse_apify_item(item, 'https://www.instagram.com/p/AbCdEf/')
check('parse_apify_item: thumbnail локальная заглушка',
      bool(res) and res['thumbnail'].startswith('/img/reel/'))

# 5) В коде не осталось внешних прокси/заглушек-сервисов
#    (loremflickr разрешён осознанно — только для фото на лендинге,
#    причём качает их наш сервер, а не браузер; ищем именно URL-ссылки,
#    а не упоминания слов в комментариях)
url_re = re.compile(r'https?://[^\s"\'<>]*', re.I)
for fname in ('app.py', os.path.join('static', 'index.html'), os.path.join('static', 'app.js')):
    with open(os.path.join(BASE_DIR, fname), encoding='utf-8') as f:
        src = f.read()
    urls = ' '.join(url_re.findall(src))
    bad = [w for w in ('pravatar', 'picsum', 'unsplash', 'wsrv.nl', 'weserv')
           if w in urls.lower()]
    bad += [w for w in ('_proxied_image', '/media?', 'IMG_PROXY') if w in src]
    check(f'{fname}: без внешних картинок/прокси {bad or ""}', not bad)

# 6) Маршрут /media удалён (теперь его перехватывает SPA-fallback -> HTML)
rm = client.get('/media?u=https://x.com/a.jpg')
check('маршрут /media больше не отдаёт картинки',
      rm.content_type.startswith('text/html'))

# 7) Лендинг: настоящие фото через наш сервер (+ SVG-фолбэк при сбое сети)
rp = client.get('/img/photo/hero-1')
print(f'   GET /img/photo/hero-1 -> {rp.status_code} {rp.content_type}')
check('фото лендинга отдаётся как image/*', rp.status_code == 200
      and rp.content_type.startswith('image/'))
rp2 = client.get('/img/photo/hero-1')
check('повторный запрос фото из кэша',
      rp2.status_code == 200 and rp2.data == rp.data)
html = client.get('/').get_data(as_text=True)
check('index ссылается на /img/photo/hero-1..3',
      all(f'/img/photo/hero-{i}' in html for i in (1, 2, 3)))
check('index больше не использует /img/reel для hero',
      '/img/reel/hero-' not in html)

print('\nALL_' + ('PASSED' if ok else 'FAILED'))
