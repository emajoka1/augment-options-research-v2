#!/usr/bin/env node
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const { DXLinkWebSocketClient, DXLinkFeed, FeedDataFormat } = require(process.env.DXLINK_API_MODULE || '/Users/forge/lab/tastytrade/node_modules/@dxfeed/dxlink-api');

const TOKEN_PATH = process.env.SPY_TOKEN_PATH || path.join(os.homedir(), 'lab/data/tastytrade/api_quote_token.json');
const OUT_PATH = process.env.DXLINK_CANDLE_OUT || path.join(os.homedir(), 'lab/data/tastytrade/dxlink_candles.json');
const AUTO_REFRESH = String(process.env.SPY_AUTO_REFRESH_TOKEN || '1') !== '0';
const FETCH_SCRIPT = process.env.SPY_FETCH_QUOTE_TOKEN_SCRIPT || path.join(__dirname, 'fetch_tasty_live_quote_token.py');
const WAIT_MS = Number(process.env.DXLINK_CANDLE_WAIT_MS || 8000);
const SYMBOL = String(process.env.DXLINK_CANDLE_SYMBOL || 'SPY{=5m}');
const FROM_TIME = Number(process.env.DXLINK_CANDLE_FROM_TIME || (Date.now() - 24 * 60 * 60 * 1000));
const PYTHON = process.env.SPY_FETCH_QUOTE_TOKEN_PYTHON || path.join(__dirname, '..', '.venv', 'bin', 'python');
const AGGREGATION_PERIOD = Number(process.env.DXLINK_ACCEPT_AGGREGATION_PERIOD || 0.1);

function fail(msg, details = {}) {
  console.error(JSON.stringify({ ok: false, error: msg, ...details }, null, 2));
  process.exit(2);
}

function maybeRefreshQuoteToken() {
  if (!AUTO_REFRESH) return;
  const missing = !fs.existsSync(TOKEN_PATH);
  let expired = false;
  if (!missing) {
    try {
      const qt = JSON.parse(fs.readFileSync(TOKEN_PATH, 'utf8')).data || {};
      const expiresAt = qt['expires-at'] || qt.expiresAt || null;
      if (expiresAt) {
        const exp = new Date(expiresAt).getTime();
        expired = Number.isFinite(exp) && Date.now() >= exp;
      }
    } catch {
      expired = true;
    }
  }
  if (!missing && !expired) return;
  const envNeeded = ['TT_CLIENT_ID', 'TT_CLIENT_SECRET', 'TT_REFRESH_TOKEN'];
  const missingEnv = envNeeded.filter((k) => !process.env[k]);
  if (missingEnv.length) {
    fail('Quote token missing/expired and auto-refresh env is incomplete', { reason: 'missing_refresh_env', missingEnv });
  }
  const result = spawnSync(PYTHON, [FETCH_SCRIPT], { env: { ...process.env, TT_QUOTE_TOKEN_OUT: TOKEN_PATH }, encoding: 'utf8' });
  if (result.status !== 0) {
    fail('Auto-refresh of quote token failed', { stdout: result.stdout, stderr: result.stderr });
  }
}

function validateQuoteToken(qt) {
  const dxUrl = String(qt['dxlink-url'] || '');
  const level = String(qt.level || '');
  if (!qt.token) fail('Missing quote token');
  if (!dxUrl) fail('Missing dxLink URL');
  if (/demo/i.test(level) || /tasty-demo-ws/i.test(dxUrl) || /\/delayed$/i.test(dxUrl) || /delayed/i.test(dxUrl)) {
    fail('Refusing delayed/demo dxLink endpoint for candle stream', { level, dxlinkUrl: dxUrl });
  }
}

(async () => {
  maybeRefreshQuoteToken();
  const qt = JSON.parse(fs.readFileSync(TOKEN_PATH, 'utf8')).data;
  validateQuoteToken(qt);

  const out = {
    source: 'dxlink-live-candles',
    level: qt.level,
    symbol: SYMBOL,
    fromTime: FROM_TIME,
    startedAt: new Date().toISOString(),
    candles: [],
  };

  const client = new DXLinkWebSocketClient();
  client.setAuthToken(qt.token);
  await client.connect(qt['dxlink-url']);

  const feed = new DXLinkFeed(client, 'AUTO');
  feed.configure({
    acceptAggregationPeriod: AGGREGATION_PERIOD,
    acceptDataFormat: FeedDataFormat.COMPACT,
    acceptEventFields: {
      Candle: ['eventType', 'eventSymbol', 'time', 'open', 'high', 'low', 'close', 'volume'],
    },
  });

  feed.addSubscriptions({ type: 'Candle', symbol: SYMBOL, fromTime: FROM_TIME });

  feed.addEventListener((events) => {
    for (const e of events) {
      if (e.eventType !== 'Candle') continue;
      out.candles.push({
        eventSymbol: e.eventSymbol,
        time: e.time,
        open: e.open,
        high: e.high,
        low: e.low,
        close: e.close,
        volume: e.volume,
      });
    }
  });

  await new Promise((r) => setTimeout(r, WAIT_MS));
  out.finishedAt = new Date().toISOString();
  fs.mkdirSync(path.dirname(OUT_PATH), { recursive: true });
  fs.writeFileSync(OUT_PATH, JSON.stringify(out, null, 2));
  console.log(JSON.stringify({ ok: true, outPath: OUT_PATH, symbol: SYMBOL, candles: out.candles.length }, null, 2));
  process.exit(0);
})();
