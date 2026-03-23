from __future__ import annotations

import json
import os
from typing import Any

import httpx
import streamlit as st

DEFAULT_API_BASE = os.environ.get('RESEARCH_API_BASE', 'http://localhost:8000').rstrip('/')

st.set_page_config(page_title='Augment Options Research', layout='wide')
st.title('Augment Options Research')
st.caption('Minimal Streamlit frontend for the research-engine API')


def api_get(base: str, path: str, params: dict[str, Any] | None = None) -> tuple[int, Any]:
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(f'{base}{path}', params=params)
        try:
            return resp.status_code, resp.json()
        except Exception:
            return resp.status_code, resp.text


def api_post(base: str, path: str, payload: dict[str, Any]) -> tuple[int, Any]:
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(f'{base}{path}', json=payload)
        try:
            return resp.status_code, resp.json()
        except Exception:
            return resp.status_code, resp.text


with st.sidebar:
    api_base = st.text_input('API base URL', value=DEFAULT_API_BASE)
    symbol = st.text_input('Ticker', value='SPY').strip().upper() or 'SPY'
    snapshot_path = st.text_input('Optional snapshot path', value='')
    st.markdown('---')
    health_clicked = st.button('Check health', use_container_width=True)

if health_clicked:
    code, payload = api_get(api_base, '/v1/health')
    st.subheader('Health')
    st.write({'status_code': code, 'payload': payload})

chain_tab, brief_tab, surface_tab, strategy_tab = st.tabs(['Chain', 'Brief', 'Vol Surface', 'Strategy'])

with chain_tab:
    st.subheader('Chain')
    if st.button('Load chain', key='load_chain'):
        params = {'snapshot_path': snapshot_path} if snapshot_path else None
        code, payload = api_get(api_base, f'/v1/chain/{symbol}', params=params)
        st.write({'status_code': code})
        st.json(payload)

with brief_tab:
    st.subheader('Trade brief')
    if st.button('Load brief', key='load_brief'):
        code, payload = api_post(api_base, f'/v1/brief/{symbol}', payload={})
        st.write({'status_code': code})
        st.json(payload)

with surface_tab:
    st.subheader('Vol surface')
    if st.button('Load surface', key='load_surface'):
        params = {'snapshot_path': snapshot_path} if snapshot_path else None
        code, payload = api_get(api_base, f'/v1/vol-surface/{symbol}', params=params)
        st.write({'status_code': code})
        st.json(payload)

with strategy_tab:
    st.subheader('Strategy analyze')
    spot = st.number_input('Spot', min_value=0.01, value=600.0, step=1.0)
    r = st.number_input('Rate', value=0.04, step=0.005, format='%.4f')
    q = st.number_input('Dividend yield', value=0.0, step=0.005, format='%.4f')
    default_legs = [
        {
            'option_type': 'call',
            'side': 'long',
            'strike': 600,
            'qty': 1,
            'expiry_years': 7 / 365,
        },
        {
            'option_type': 'put',
            'side': 'long',
            'strike': 600,
            'qty': 1,
            'expiry_years': 7 / 365,
        },
    ]
    legs_text = st.text_area('Legs JSON', value=json.dumps(default_legs, indent=2), height=240)

    if st.button('Analyze strategy', key='analyze_strategy'):
        try:
            legs = json.loads(legs_text)
        except json.JSONDecodeError as exc:
            st.error(f'Invalid legs JSON: {exc}')
        else:
            code, payload = api_post(api_base, '/v1/strategy/analyze', {
                'spot': spot,
                'r': r,
                'q': q,
                'legs': legs,
            })
            st.write({'status_code': code})
            st.json(payload)
