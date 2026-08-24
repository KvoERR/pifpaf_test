# -*- coding: utf-8 -*-
"""Сквозной тест /api/account/import через Flask test client (реальный Apify)."""
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import app as appmod  # noqa: E402

client = appmod.app.test_client()

resp = client.post('/api/account/import',
                   json={'url': 'https://www.instagram.com/instagram/'})
print('status:', resp.status_code)
data = resp.get_json()
acc = data.get('account') or {}
reels = acc.get('reels') or []
print('live   :', data.get('live'))
print('handle :', acc.get('handle'))
print('name   :', acc.get('name'))
print('avatar :', (acc.get('avatar') or '')[:80])
print('bio    :', (acc.get('bio') or '')[:80])
print('followers:', acc.get('followers'))
print('reels  :', len(reels))
if reels:
    r = reels[0]
    print('first reel:')
    print('  views   :', r.get('views'))
    print('  likes   :', r.get('likes'))
    print('  comments:', r.get('comments'))
    print('  posted_at:', r.get('posted_at'))
    print('  url     :', r.get('url'))
    print('  thumb   :', (r.get('thumbnail') or '')[:60])
ok = (
    resp.status_code == 200
    and data.get('live') is True
    and len(reels) > 0
    and all(r.get('views') for r in reels)
)

# --- Картинки: только локальные заглушки, внешних ссылок быть не должно ---
av = acc.get('avatar') or ''
print('avatar:', av)
check_av = av.startswith('/img/avatar/')
ok = ok and check_av
print(('PASS' if check_av else 'FAIL'), '- avatar локальная заглушка')
thumbs = [r.get('thumbnail') or '' for r in reels]
local_n = sum(1 for t in thumbs if t.startswith('/img/reel/'))
print(f'локальных обложек: {local_n}/{len(thumbs)}')
ok = ok and local_n == len(thumbs)
for i, t in enumerate(thumbs[:3]):
    print(f'thumb[{i}]:', t[:60])

print('\nTEST_' + ('PASSED' if ok else 'FAILED'))
