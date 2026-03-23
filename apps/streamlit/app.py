from __future__ import annotations

import json
import os
from typing import Any

import httpx
import pandas as pd
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
    try:
        resp = client.get(f'{base}{path}', params=params)
    except Exception as exc:
        return 0, {'error': str(exc), 'kind': 'network_error'}
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, resp.text


def api_post(base: str, path: str, payload: dict[str, Any]) -> tuple[int, Any]:
    client = get_http_client()
    try:
        resp = client.post(f'{base}{path}', json=payload)
    except Exception as exc:
        return 0, {'error': str(exc), 'kind': 'network_error'}
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


def render_status(code: int, payload: Any, success_text: str) -> None:
    if code == 0:
        st.error(f"Request failed before a response was received: {payload.get('error', payload)}")
    elif 200 <= code < 300:
        st.success(success_text)
    elif code == 501:
        st.warning(f"Endpoint says this is not implemented yet: {payload}")
    elif code == 503:
        st.warning(f"Backend is up, but live data/snapshot input is missing: {payload}")
    else:
        st.error(f'HTTP {code}: {payload}')


def download_json_button(label: str, filename: str, payload: Any) -> None:
    st.download_button(
        label,
        data=json.dumps(payload, indent=2),
        file_name=filename,
        mime='application/json',
        use_container_width=True,
    )


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
        st.session_state['last_strategy'] = None
        st.success('Cleared cached GET responses and last displayed results.')

health = st.session_state.get('last_health')
if health:
    code, payload = health
    with st.expander('Health', expanded=code != 200):
        render_status(code, payload, 'Backend health check passed.')
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
        render_status(code, payload, 'Chain loaded.')
        if 200 <= code < 300 and isinstance(payload, dict):
            col1, col2, col3 = st.columns(3)
            col1.metric('Symbol', payload.get('symbol', '—'))
            col2.metric('Spot', payload.get('spot', '—'))
            col3.metric('Source', payload.get('source', '—'))

            strikes = payload.get('strikes') or []
            ivs = payload.get('ivs') or []
            expiry_days = payload.get('expiry_days') or [None] * len(strikes)
            df = pd.DataFrame({'strike': strikes, 'iv': ivs, 'expiry_days': expiry_days})
            st.dataframe(df, use_container_width=True)
            if not df.empty:
                chart_df = df[['strike', 'iv']].set_index('strike')
                st.line_chart(chart_df)
            download_json_button('Download chain JSON', f"{symbol.lower()}_chain.json", payload)
        else:
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
        render_status(code, payload, 'Trade brief loaded.')
        if 200 <= code < 300 and isinstance(payload, dict):
            try:
                brief = payload.get('TRADE BRIEF', {})
                col1, col2, col3 = st.columns(3)
                col1.metric('Ticker', brief.get('Ticker', symbol))
                col2.metric('Spot', brief.get('Spot', '—'))
                col3.metric('Decision', brief.get('Final Decision', '—'))

                if brief.get('NoCandidatesReason'):
                    st.warning(f"No-candidate reason: {brief['NoCandidatesReason']}")
                missing = brief.get('missingRequiredData') or []
                if missing:
                    st.caption('Missing required data: ' + ', '.join(str(x) for x in missing))

                candidates = brief.get('Candidates') or []
                if candidates:
                    candidate_rows = []
                    for idx, candidate in enumerate(candidates, start=1):
                        if isinstance(candidate, dict):
                            candidate_rows.append({
                                'candidate': idx,
                                'type': candidate.get('type'),
                                'decision': candidate.get('decision'),
                                'score_total': (candidate.get('score') or {}).get('Total') if isinstance(candidate.get('score'), dict) else None,
                                'gate_failures': ', '.join(candidate.get('gateFailures') or []),
                            })
                        else:
                            candidate_rows.append({'candidate': idx, 'raw': str(candidate)})
                    st.dataframe(pd.DataFrame(candidate_rows), use_container_width=True)
                else:
                    st.info('No candidates were returned in the brief payload.')

                with st.expander('Raw brief payload'):
                    st.json(payload)
                download_json_button('Download brief JSON', f"{symbol.lower()}_brief.json", payload)
            except Exception as exc:
                st.error(f'Brief rendering failed: {exc}')
                st.json(payload)
        else:
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
        render_status(code, payload, 'Vol surface loaded.')
        if 200 <= code < 300 and isinstance(payload, dict):
            col1, col2, col3 = st.columns(3)
            col1.metric('IV ATM', round(float(payload.get('iv_atm', 0.0)), 4))
            col2.metric('Skew', round(float(payload.get('skew', 0.0)), 4))
            col3.metric('Curvature', round(float(payload.get('curv', 0.0)), 4))

            strikes = payload.get('strikes') or []
            ivs = payload.get('ivs') or []
            fitted = payload.get('fitted_ivs') or []
            df = pd.DataFrame({'strike': strikes, 'observed_iv': ivs, 'fitted_iv': fitted})
            st.dataframe(df, use_container_width=True)
            if not df.empty:
                st.line_chart(df.set_index('strike')[['observed_iv', 'fitted_iv']])
            download_json_button('Download surface JSON', f"{symbol.lower()}_surface.json", payload)
        else:
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
        render_status(code, payload, 'Strategy analysis loaded.')
        if 200 <= code < 300 and isinstance(payload, dict):
            col1, col2, col3 = st.columns(3)
            col1.metric('Entry value', round(float(payload.get('entry_value', 0.0)), 4))
            col2.metric('Max profit', round(float(payload.get('max_profit', 0.0)), 4))
            col3.metric('Max loss', round(float(payload.get('max_loss', 0.0)), 4))

            greeks = payload.get('greeks_aggregate') or {}
            g1, g2, g3, g4 = st.columns(4)
            g1.metric('Delta', round(float(greeks.get('delta', 0.0)), 4))
            g2.metric('Gamma', round(float(greeks.get('gamma', 0.0)), 4))
            g3.metric('Vega', round(float(greeks.get('vega', 0.0)), 4))
            g4.metric('Theta/day', round(float(greeks.get('theta_daily', 0.0)), 4))

            left, right = st.columns(2)
            with left:
                st.markdown('**Breakevens**')
                st.write(payload.get('breakevens'))
            with right:
                st.markdown('**Exit rules**')
                st.json(payload.get('exit_rules', {}))

            download_json_button('Download strategy JSON', f"{symbol.lower()}_strategy.json", payload)
        else:
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
