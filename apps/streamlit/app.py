from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
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
        'live_auto_refresh': True,
        'live_refresh_seconds': 5,
        'last_refresh_at': None,
        'previous_live_generated_at': None,
        'last_health': None,
        'last_live_status': None,
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
    return httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0))


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
    last_exc = None
    for attempt in range(2):
        try:
            resp = client.post(f'{base}{path}', json=payload)
            break
        except Exception as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(0.5)
                continue
            return 0, {'error': str(exc), 'kind': 'network_error'}
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, resp.text


@st.cache_data(ttl=15, show_spinner=False)
def cached_health(base: str) -> tuple[int, Any]:
    return api_get(base, '/v1/health')


@st.cache_data(ttl=10, show_spinner=False)
def cached_live_status(base: str) -> tuple[int, Any]:
    return api_get(base, '/v1/live-status')


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
    try:
        data = json.dumps(payload, indent=2, default=str)
    except Exception:
        data = str(payload)
    st.download_button(label, data=data, file_name=filename, mime='application/json')


def candidate_heading(candidate: dict[str, Any], idx: int) -> str:
    candidate_type = str(candidate.get('type', 'unknown')).replace('_', ' ').title()
    decision = candidate.get('decision', '—')
    ticket = candidate.get('ticket') or {}
    ticket_legs = ticket.get('legs') or []
    structure = candidate.get('structure') or {}
    structure_legs = structure.get('legs') or []

    def format_expiry(value: Any) -> str:
        if not value or not isinstance(value, str):
            return ''
        try:
            dt = datetime.fromisoformat(value)
            return dt.strftime('%d %b')
        except Exception:
            return value

    if structure_legs:
        rendered_legs: list[str] = []
        candidate_kind = str(candidate.get('type', '')).lower()
        for leg_index, leg in enumerate(structure_legs):
            if not isinstance(leg, dict):
                continue
            opt_side = str(leg.get('side', '')).upper()
            strike = leg.get('strike')
            expiry = format_expiry(leg.get('expiry'))
            if strike is None or opt_side not in {'P', 'C'}:
                continue
            if candidate_kind == 'debit':
                action = 'Buy' if leg_index == 0 else 'Sell'
            elif candidate_kind == 'credit':
                action = 'Sell' if leg_index == 0 else 'Buy'
            elif candidate_kind == 'condor':
                action = 'Sell' if leg_index in {0, 2} else 'Buy'
            else:
                action = 'Leg'
            leg_text = f"{action} {strike:g}{opt_side}"
            if expiry:
                leg_text += f" ({expiry})"
            rendered_legs.append(leg_text)
        if rendered_legs:
            return f"Candidate {idx}: {candidate_type} · {decision} · {' / '.join(rendered_legs)}"

    if ticket_legs and all(isinstance(leg, str) for leg in ticket_legs):
        legs_text = ' / '.join(str(leg) for leg in ticket_legs)
        return f"Candidate {idx}: {candidate_type} · {decision} · {legs_text}"
    return f"Candidate {idx}: {candidate_type} · {decision}"


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def format_elapsed_from_iso(value: Any) -> str:
    if not value or not isinstance(value, str):
        return '—'
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        delta = datetime.now(timezone.utc) - dt
        seconds = max(int(delta.total_seconds()), 0)
    except Exception:
        return '—'
    if seconds < 60:
        return f'{seconds}s ago'
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f'{minutes}m {sec}s ago'
    hours, minutes = divmod(minutes, 60)
    return f'{hours}h {minutes}m ago'


def refresh_live_panels(base: str, symbol: str, snapshot_path: str, *, force: bool = False) -> None:
    if force:
        cached_live_status.clear()
        cached_chain.clear()
        cached_surface.clear()
    st.session_state['last_live_status'] = api_get(base, '/v1/live-status')
    if st.session_state.get('last_chain') is not None:
        params = {'snapshot_path': snapshot_path} if snapshot_path else None
        st.session_state['last_chain'] = api_get(base, f'/v1/chain/{symbol}', params=params)
    if st.session_state.get('last_surface') is not None:
        params = {'snapshot_path': snapshot_path} if snapshot_path else None
        st.session_state['last_surface'] = api_get(base, f'/v1/vol-surface/{symbol}', params=params)
    st.session_state['last_refresh_at'] = now_utc_iso()


def render_live_status_panel() -> None:
    live_status_result = st.session_state.get('last_live_status')
    if not live_status_result:
        st.info('No live status fetched yet.')
        return

    live_code, live_payload = live_status_result
    if live_code == 200 and isinstance(live_payload, dict):
        health = live_payload.get('health') or {}
        generated_at = live_payload.get('generatedAt')
        previous_generated_at = st.session_state.get('previous_live_generated_at')
        changed = bool(generated_at and generated_at != previous_generated_at)
        if generated_at:
            st.session_state['previous_live_generated_at'] = generated_at

        freshness_cols = st.columns(5)
        freshness_cols[0].metric('Daemon health', 'OK' if health.get('ok') and not health.get('stale') else 'DEGRADED')
        freshness_cols[1].metric('Connection', live_payload.get('connectionState', '—'))
        freshness_cols[2].metric('Auth', live_payload.get('authState', '—'))
        freshness_cols[3].metric('Daemon update', generated_at or '—', delta='new tick' if changed else None)
        freshness_cols[4].metric('UI refresh', st.session_state.get('last_refresh_at') or '—', delta=format_elapsed_from_iso(st.session_state.get('last_refresh_at')))

        meta_cols = st.columns(4)
        meta_cols[0].metric('Snapshot ID', live_payload.get('snapshotId', '—'))
        meta_cols[1].metric('Active candle', live_payload.get('activeCandleSymbol', '—'))
        meta_cols[2].metric('Options with data', live_payload.get('symbolsWithData', '—'))
        meta_cols[3].metric('Daemon freshness', format_elapsed_from_iso(generated_at))

        if health.get('ok') and not health.get('stale'):
            status_text = f"DXLink daemon healthy — active candle symbol: {live_payload.get('activeCandleSymbol', '—')}"
            if changed:
                st.success(status_text + ' · live payload just updated.')
            else:
                st.info(status_text + ' · waiting for next tick.')
        else:
            st.warning(f'DXLink daemon degraded: {health}')

        with st.expander('Live daemon status'):
            st.json(live_payload)
    else:
        st.warning(f'DXLink daemon status unavailable: {live_payload}')


def render_live_refresh_fragment(base: str, symbol: str, snapshot_path: str) -> None:
    auto_refresh_enabled = st.session_state.get('live_auto_refresh', True)
    refresh_seconds = int(st.session_state.get('live_refresh_seconds', 5) or 5)

    if hasattr(st, 'fragment'):
        @st.fragment(run_every=f'{refresh_seconds}s' if auto_refresh_enabled else None)
        def _fragment() -> None:
            if auto_refresh_enabled:
                refresh_live_panels(base, symbol, snapshot_path, force=True)
            render_live_status_panel()

        _fragment()
    else:
        if auto_refresh_enabled and st.button('Refresh live status now', key='manual_live_refresh_fallback'):
            refresh_live_panels(base, symbol, snapshot_path, force=True)
        render_live_status_panel()


def render_live_dataframe(result: tuple[int, Any] | None, kind: str, symbol: str) -> None:
    if not result:
        return

    code, payload = result
    if not (200 <= code < 300 and isinstance(payload, dict)):
        st.json(payload)
        return

    if kind == 'chain':
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
        return

    if kind == 'surface':
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


with st.sidebar:
    st.subheader('Connection')
    api_base = st.text_input('API base URL', key='api_base').rstrip('/')
    symbol = st.text_input('Ticker', key='symbol').strip().upper() or DEFAULT_SYMBOL
    snapshot_path = st.text_input('Optional snapshot path', key='snapshot_path').strip()
    st.markdown('---')
    st.subheader('Live refresh')
    st.checkbox('Auto-refresh live views', key='live_auto_refresh', help='Continuously re-poll live status, plus any loaded chain and vol-surface views.')
    st.number_input('Refresh every (seconds)', min_value=2, max_value=60, step=1, key='live_refresh_seconds')
    if st.button('Refresh live data now', use_container_width=True):
        refresh_live_panels(api_base, symbol, snapshot_path, force=True)
        st.success('Live views refreshed.')
    st.markdown('---')
    if st.button('Check health', use_container_width=True):
        st.session_state['last_health'] = cached_health(api_base)
        st.session_state['last_live_status'] = cached_live_status(api_base)
    if st.button('Clear cached responses', use_container_width=True):
        cached_health.clear()
        cached_live_status.clear()
        cached_chain.clear()
        cached_surface.clear()
        st.session_state['last_health'] = None
        st.session_state['last_live_status'] = None
        st.session_state['last_chain'] = None
        st.session_state['last_brief'] = None
        st.session_state['last_surface'] = None
        st.session_state['last_strategy'] = None
        st.success('Cleared cached GET responses and last displayed results.')

if st.session_state.get('last_live_status') is None:
    st.session_state['last_live_status'] = cached_live_status(api_base)
    st.session_state['last_refresh_at'] = now_utc_iso()

render_live_refresh_fragment(api_base, symbol, snapshot_path)

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
            if st.session_state.get('live_auto_refresh'):
                st.caption('Live mode: this chain view will refresh automatically while auto-refresh is enabled.')
            render_live_dataframe(result, 'chain', symbol)
        else:
            st.json(payload)
    else:
        st.info('Load a chain to inspect strikes, IVs, and source metadata.')

with brief_tab:
    st.subheader('Trade brief')
    if st.button('Load brief', key='load_brief'):
        st.session_state['last_brief'] = api_post(api_base, f'/v1/brief/{symbol}', payload={})
    if st.session_state.get('live_auto_refresh') and st.session_state.get('last_brief') is not None:
        refreshed = api_post(api_base, f'/v1/brief/{symbol}', payload={})
        if isinstance(refreshed, tuple) and len(refreshed) == 2 and 200 <= refreshed[0] < 300:
            st.session_state['last_brief'] = refreshed
        elif st.button('Retry brief now', key='retry_brief_now'):
            st.session_state['last_brief'] = api_post(api_base, f'/v1/brief/{symbol}', payload={})
    result = st.session_state.get('last_brief')
    if result and isinstance(result, tuple) and len(result) == 2:
        code, payload = result
        if 200 <= code < 300 and isinstance(payload, dict):
            brief_probe = payload.get('TRADE BRIEF', {})
            missing_probe = set(brief_probe.get('missingRequiredData') or [])
            stale_missing = {'spot', 'option_rows', 'ivCurrent'}
            if missing_probe & stale_missing:
                refreshed = api_post(api_base, f'/v1/brief/{symbol}', payload={})
                if isinstance(refreshed, tuple) and len(refreshed) == 2:
                    r_code, r_payload = refreshed
                    if 200 <= r_code < 300 and isinstance(r_payload, dict):
                        st.session_state['last_brief'] = refreshed
                        result = refreshed
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

                vol_state = brief.get('Volatility State') or {}
                regime = brief.get('Regime') or {}
                rv10 = None
                rv20 = None
                for metric in regime.get('metrics') or []:
                    if not isinstance(metric, dict):
                        continue
                v1, v2, v3, v4 = st.columns(4)
                v1.metric('IV current', vol_state.get('ivCurrent', '—'))
                v2.metric('RV10', vol_state.get('ivCurrent', None) - vol_state.get('ivVsRv10', None) if vol_state.get('ivCurrent') is not None and vol_state.get('ivVsRv10') is not None else '—')
                v3.metric('RV20', vol_state.get('ivCurrent', None) - vol_state.get('ivVsRv20', None) if vol_state.get('ivCurrent') is not None and vol_state.get('ivVsRv20') is not None else '—')
                v4.metric('Vol regime', (vol_state.get('classifier') or {}).get('regime', '—'))
                st.caption(f"IV-RV10: {vol_state.get('ivVsRv10', '—')} · IV-RV20: {vol_state.get('ivVsRv20', '—')}")

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
                            mc = candidate.get('mc') or {}
                            metrics = mc.get('metrics') or {}
                            used_mc = candidate.get('decisionSource') == 'mc_engine' and bool(mc)
                            candidate_rows.append({
                                'candidate': idx,
                                'type': candidate.get('type'),
                                'decision': candidate.get('decision'),
                                'decision_source': candidate.get('decisionSource') or 'pre_mc_rejection',
                                'score_total': (candidate.get('score') or {}).get('Total') if isinstance(candidate.get('score'), dict) else None,
                                'max_loss_per_contract': candidate.get('maxLossPerContract'),
                                'mc_allow_trade': mc.get('allowTrade') if used_mc else 'not_run',
                                'mc_status': mc.get('status') if used_mc else 'not_run',
                                'ev': metrics.get('ev') if used_mc else None,
                                'pop': metrics.get('pop') if used_mc else None,
                                'cvar95': metrics.get('cvar95') if used_mc else None,
                                'gate_failures': ', '.join(candidate.get('gateFailures') or []),
                            })
                        else:
                            candidate_rows.append({'candidate': idx, 'raw': str(candidate)})
                    st.dataframe(pd.DataFrame(candidate_rows), use_container_width=True)

                    for idx, candidate in enumerate(candidates, start=1):
                        if not isinstance(candidate, dict):
                            continue
                        with st.expander(candidate_heading(candidate, idx)):
                            mc = candidate.get('mc') or {}
                            metrics = mc.get('metrics') or {}
                            multi = mc.get('multiSeedConfidence') or {}
                            gates = mc.get('gates') or {}
                            attr = mc.get('edgeAttribution') or {}
                            strategy = mc.get('strategy') or {}
                            used_mc = candidate.get('decisionSource') == 'mc_engine' and bool(mc)

                            if not used_mc:
                                st.info('Rejected before MC. This candidate did not make it far enough to run Monte Carlo.')
                                x1, x2 = st.columns(2)
                                x1.metric('Max loss / contract', candidate.get('maxLossPerContract', '—'))
                                x2.metric('Decision source', candidate.get('decisionSource') or 'pre_mc_rejection')
                                if candidate.get('gateFailures'):
                                    st.caption('Pre-MC gate failures: ' + ', '.join(str(x) for x in (candidate.get('gateFailures') or [])))
                                structure = candidate.get('structure') or {}
                                pricing = structure.get('pricing') or {}
                                st.markdown('**Attempted structure**')
                                st.write({
                                    'name': structure.get('name'),
                                    'expiry': structure.get('expiry'),
                                    'dte': structure.get('dte'),
                                    'pricing': pricing,
                                })
                                legs = structure.get('legs') or []
                                if legs:
                                    st.dataframe(pd.DataFrame(legs), use_container_width=True)
                                st.markdown('**Accompanying strategy / ticket context**')
                                st.write({'score': candidate.get('score'), 'ticket': candidate.get('ticket'), 'whys': candidate.get('whys')})
                                continue

                            c1, c2, c3, c4 = st.columns(4)
                            c1.metric('Decision source', candidate.get('decisionSource', '—'))
                            c2.metric('MC allow trade', mc.get('allowTrade', '—'))
                            c3.metric('EV', metrics.get('ev', '—'))
                            c4.metric('POP', metrics.get('pop', '—'))

                            d1, d2, d3 = st.columns(3)
                            d1.metric('CVaR95', metrics.get('cvar95', '—'))
                            d2.metric('Data quality', mc.get('dataQualityStatus', '—'))
                            d3.metric('MC status', mc.get('status', '—'))

                            if candidate.get('gateFailures'):
                                st.caption('Gate failures: ' + ', '.join(str(x) for x in (candidate.get('gateFailures') or [])))
                            if mc.get('breakevens') is not None:
                                st.write({'breakevens': mc.get('breakevens')})

                            left, right = st.columns(2)
                            with left:
                                st.markdown('**MC gates**')
                                st.json(gates)
                                st.markdown('**Strategy**')
                                if isinstance(strategy, (dict, list)):
                                    st.json(strategy)
                                else:
                                    st.write(strategy)
                            with right:
                                st.markdown('**Multi-seed confidence**')
                                st.json(multi)
                                st.markdown('**Edge attribution**')
                                st.json(attr)
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
            if st.session_state.get('live_auto_refresh'):
                st.caption('Live mode: this vol-surface view will refresh automatically while auto-refresh is enabled.')
            render_live_dataframe(result, 'surface', symbol)
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
