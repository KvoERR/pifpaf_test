# -*- coding: utf-8 -*-
"""Временный диагностический скрипт: варианты входа для Apify-актора."""
import json
import sys

sys.path.insert(0, r'C:\Users\user\Downloads\tmp\pifpaf_test')
import app  # noqa: E402  (подтягивает .env с токеном и ID актора)

OUT_DIR = r'C:\Users\user\Downloads\tmp\pifpaf_test'


def probe(name, payload):
    try:
        items = app._apify_run(payload)
    except Exception as exc:  # noqa: BLE001
        items = 'EXC: ' + repr(exc)

    res = {'payload': payload, 'is_list': isinstance(items, list),
           'count': len(items) if isinstance(items, list) else None}
    if isinstance(items, list) and items:
        first = items[0] if isinstance(items[0], dict) else {}
        res['first_keys'] = sorted(first.keys())
        res['sample'] = str(items[0])[:2200]
        if len(items) > 1 and isinstance(items[1], dict):
            res['second_keys'] = sorted(items[1].keys())
            res['second_sample'] = str(items[1])[:700]
    else:
        res['raw_head'] = str(items)[:600]

    with open(OUT_DIR + r'\probe_' + name + '.json', 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(name, 'written')


URL = 'https://www.instagram.com/instagram/'

probe('posts', {
    'directUrls': [URL],
    'resultsType': 'posts',
    'resultsLimit': 15,
})

probe('details', {
    'directUrls': [URL],
    'resultsType': 'details',
    'resultsLimit': 1,
})

print('PROBE_DONE')

