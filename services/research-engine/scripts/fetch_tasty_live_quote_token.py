#!/usr/bin/env python3
import base64
import json
import os
from pathlib import Path

import requests


BASE = os.environ.get('TT_BASE_URL', 'https://api.tastytrade.com').rstrip('/')
CLIENT_ID = os.environ['TT_CLIENT_ID'].strip()
CLIENT_SECRET = os.environ['TT_CLIENT_SECRET'].strip()
REFRESH_TOKEN = os.environ['TT_REFRESH_TOKEN'].strip()
OUT = Path(os.environ.get('TT_QUOTE_TOKEN_OUT', str(Path.home() / 'lab/data/tastytrade/api_quote_token.json')))


def main() -> None:
    basic = base64.b64encode(f'{CLIENT_ID}:{CLIENT_SECRET}'.encode()).decode()
    ua = {'User-Agent': 'augment-options-research/0.1'}

    tok = requests.post(
        f'{BASE}/oauth/token',
        headers={**ua, 'Authorization': f'Basic {basic}'},
        data={'grant_type': 'refresh_token', 'refresh_token': REFRESH_TOKEN},
        timeout=30,
    )
    tok.raise_for_status()
    access = tok.json()['access_token']

    quote = requests.get(
        f'{BASE}/api-quote-tokens',
        headers={**ua, 'Authorization': f'Bearer {access}'},
        timeout=30,
    )
    quote.raise_for_status()
    payload = quote.json()

    data = payload.get('data') or {}
    dx_url = str(data.get('dxlink-url') or '')
    level = str(data.get('level') or '')
    if 'demo' in dx_url.lower() or 'delayed' in dx_url.lower() or level.lower() != 'api':
        raise SystemExit(f'Refusing non-live quote token: level={level!r}, dxlink-url={dx_url!r}')

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))
    print(json.dumps({'ok': True, 'out': str(OUT), 'level': level, 'dxlink-url': dx_url}, indent=2))


if __name__ == '__main__':
    main()
