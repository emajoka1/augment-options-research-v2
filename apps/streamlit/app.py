from __future__ import annotations

import json
import os
from typing import Any

import httpx
import streamlit as st

DEFAULT_API_BASE = os.environ.get('RESEARCH_API_BASE', 'http://localhost:8000').rstrip('/')
DEFAULT_SYMBOL = 'SPY'
DEFAULT_SPOT = 600.0
DEFAULT_R = 0.04
DEFAULT_Q = 0.0
DEFAULT_LEGS = [
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

st.set_page_config(page_title='Augment Options Research', layout='wide')
st.title('Augment Options Research')
st.caption('Thin Streamlit client for the research-engine API')


def ensure_state() -> None:
    defaults = {
        'api_base': DEFAULT_API_BASE,
        'symbol': DEFAULT_SYMBOL,
        'snapshot_path': '',
        'spot': DEFAULT_SPOT,
        'r': DEFAULT_R,
        'q': DEFAULT_Q,
        'legs_text': json.dumps(DEFAULT_LEGS, indent=2),
        'last_health': None,
        'last_chain': None,
        'last_brief': None,
        'last_surface': None,
        'last_strategy': None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


ensure_state()


@st.cache_resource
def get_http_client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0))


def api_get(base: str, path: str, params: dict[str, Any] | None = None) -> tuple[int, Any]:
    client = get_http_client()
    resp = client.get(f'{base}{path}', params=params)
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, resp.text


def api_post(base: str, path: str, payload: dict[str, Any]) -> tuple[int, Any]:
    client = get_http_client()
    resp = client.post(f'{base}{path}', json=payload)
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, resp.text


@st.cache_data(ttl=15, show_spinner=False)
def cached_health(base: str) -> tuple[int, Any]:
    return api_get(base, '/v1/health')


@st.cache_data(ttl=15, show_spinner=False)
def cached_chain(base: str, symbol: str, snapshot_path: str) -> tuple[int, Any]:
    params = {'snapshot_path': snapshot_path} if snapshot_path else None
    return api_get(base, f'/v1/chain/{symbol}', params=params)


@st.cache_data(ttl=30, show_spinner=False)
def cached_surface(base: str, symbol: str, snapshot_path: str) -> tuple[int, Any]:
    params = {'snapshot_path': snapshot_path} if snapshot_path else None
    return api_get(base, f'/v1/vol-surface/{symbol}', params=params)


with st.sidebar:
    st.subheader('Connection')
    api_base = st.text_input('API base URL', key='api_base').rstrip('/')
    symbol = st.text_input('Ticker', key='symbol').strip().upper() or DEFAULT_SYMBOL
    snapshot_path = st.text_input('Optional snapshot path', key='snapshot_path').strip()
    st.markdown('---')
    if st.button('Check health', use_container_width=True):
        st.session_state['last_health'] = cached_health(api_base)
    if st.button('Clear cached responses', use_container_width=True):
        cached_health.clear()
        cached_chain.clear()
        cached_surface.clear()
        st.session_state['last_health'] = None
        st.session_state['last_chain'] = None
        st.session_state['last_brief'] = None
        st.session_state['last_surface'] = None
        st.success('Cleared cached GET responses.')

health = st.session_state.get('last_health')
if health:
    code, payload = health
    with st.expander('Health', expanded=code != 200):
        st.write({'status_code': code})
        st.json(payload)

chain_tab, brief_tab, surface_tab, strategy_tab, deploy_tab = st.tabs(
    ['Chain', 'Brief', 'Vol Surface', 'Strategy', 'Deploy notes']
)

with chain_tab:
    st.subheader('Chain')
    if st.button('Load chain', key='load_chain'):
        st.session_state['last_chain'] = cached_chain(api_base, symbol, snapshot_path)
    result = st.session_state.get('last_chain')
    if result:
        code, payload = result
        st.write({'status_code': code})
        st.json(payload)
    else:
        st.info('Load a chain to inspect strikes, IVs, and source metadata.')

with brief_tab:
    st.subheader('Trade brief')
    if st.button('Load brief', key='load_brief'):
        st.session_state['last_brief'] = api_post(api_base, f'/v1/brief/{symbol}', payload={})
    result = st.session_state.get('last_brief')
    if result:
        code, payload = result
        st.write({'status_code': code})
        st.json(payload)
    else:
        st.info('Load a brief to inspect current trade-decision output for the selected ticker.')

with surface_tab:
    st.subheader('Vol surface')
    if st.button('Load surface', key='load_surface'):
        st.session_state['last_surface'] = cached_surface(api_base, symbol, snapshot_path)
    result = st.session_state.get('last_surface')
    if result:
        code, payload = result
        st.write({'status_code': code})
        st.json(payload)
    else:
        st.info('Load the fitted vol surface for the selected ticker.')

with strategy_tab:
    st.subheader('Strategy analyze')
    st.number_input('Spot', min_value=0.01, step=1.0, key='spot')
    st.number_input('Rate', step=0.005, format='%.4f', key='r')
    st.number_input('Dividend yield', step=0.005, format='%.4f', key='q')
    legs_text = st.text_area('Legs JSON', key='legs_text', height=240)

    if st.button('Analyze strategy', key='analyze_strategy'):
        try:
            legs = json.loads(legs_text)
        except json.JSONDecodeError as exc:
            st.error(f'Invalid legs JSON: {exc}')
        else:
            st.session_state['last_strategy'] = api_post(
                api_base,
                '/v1/strategy/analyze',
                {
                    'spot': st.session_state['spot'],
                    'r': st.session_state['r'],
                    'q': st.session_state['q'],
                    'legs': legs,
                },
            )
    result = st.session_state.get('last_strategy')
    if result:
        code, payload = result
        st.write({'status_code': code})
        st.json(payload)
    else:
        st.info('Analyze a strategy to inspect entry value, breakevens, greeks, and exit rules.')

with deploy_tab:
    st.subheader('Deploy notes')
    st.markdown(
        '''
- Streamlit is the frontend. It should call the research-engine API; it should **not** talk directly to dxLink.
- For Streamlit Community Cloud, set the **main file path** to `streamlit_app.py`.
- Set `RESEARCH_API_BASE` to a public backend URL, not `localhost`.
- Recommended architecture:
  - Streamlit UI → research-engine API → provider/snapshot/dxLink-backed data
- Local demo path:
  - backend on `http://127.0.0.1:8000`
  - Streamlit on `http://127.0.0.1:8501`
        '''
    )
