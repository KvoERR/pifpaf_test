"""Диагностика Apify API: проверка актора/токена с ретраями (сеть нестабильна)."""
import json
import os
import sys
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Токен читаем из .env / окружения — в git он попадать не должен.
load_dotenv(os.path.join(BASE_DIR, '.env'))
TOKEN = os.environ.get('APIFY_TOKEN', '').strip()


def get_json(path, attempts=5, timeout=8):
    url = f'https://api.apify.com/v2/{path}{"&" if "?" in path else "?"}token={TOKEN}'
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return json.load(resp)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            print(f'  попытка {attempt}/{attempts} не удалась: {exc!r}')
            time.sleep(2)
    raise RuntimeError(f'Все {attempts} попыток исчерпаны') from last_exc


if __name__ == '__main__':
    if not TOKEN:
        sys.exit('APIFY_TOKEN не задан: укажите его в .env рядом со скриптом '
                 'или в переменных окружения.')
    actor_path = sys.argv[1] if len(sys.argv) > 1 else 'acts/apify~instagram-scraper'
    print(f'GET /v2/{actor_path}')
    data = get_json(actor_path)['data']
    print('ID:', data['id'])
    print('NAME:', data['username'] + '/' + data['name'])
    print('TITLE:', data.get('title'))
    print('TOTAL RUNS:', (data.get('stats') or {}).get('totalRuns'))
    dri = data.get('defaultRunInput')
    print('DEFAULT INPUT:', (dri[:800] if dri else None))
