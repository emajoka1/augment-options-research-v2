#!/usr/bin/env node
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');

const { DXLinkWebSocketClient, DXLinkFeed, FeedDataFormat } = require('/Users/forge/lab/tastytrade/node_modules/@dxfeed/dxlink-api');

const CHAIN_PATH = process.env.SPY_CHAIN_PATH || path.join(os.homedir(), 'lab/data/tastytrade/SPY_nested_chain.json');
const TOKEN_PATH = process.env.SPY_TOKEN_PATH || path.join(os.homedir(), 'lab/data/tastytrade/api_quote_token.json');
const OUT_PATH = process.env.SPY_LIVE_OUT || path.join(os.homedir(), 'lab/data/tastytrade/spy_live_snapshot.json');
const WAIT_MS = Number(process.env.SPY_WAIT_MS || 10000);
const AUTO_REFRESH = String(process.env.SPY_AUTO_REFRESH_TOKEN || '1') !== '0';
const FETCH_SCRIPT = process.env.SPY_FETCH_QUOTE_TOKEN_SCRIPT || path.join(__dirname, 'fetch_tasty_live_quote_token.py');
const PYTHON = process.env.SPY_FETCH_QUOTE_TOKEN_PYTHON || path.join(__dirname, '..', '.venv', 'bin', 'python');
const CONNECT_RETRIES = Number(process.env.SPY_CONNECT_RETRIES || 3);
const CONNECT_BACKOFF_MS = Number(process.env.SPY_CONNECT_BACKOFF_MS || 1500);
const MIN_SYMBOLS_WITH_DATA = Number(process.env.SPY_MIN_SYMBOLS_WITH_DATA || 5);
const REQUIRE_UNDERLYING_QUOTE = String(process.env.SPY_REQUIRE_UNDERLYING_QUOTE || '1') !== '0';
const MAX_EXPIRIES = Number(process.env.SPY_MAX_EXPIRIES || 4);
const STRIKE_OFFSETS = String(process.env.SPY_STRIKE_OFFSETS || '-40,-30,-25,-20,-15,-10,-5,0,5,10,15,20,25,30,40')
  .split(',')
  .map((v) => Number(v.trim()))
  .filter(Number.isFinite);
const MAX_CONTRACTS = Number(process.env.SPY_MAX_CONTRACTS || 120);

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
 const { spawnSync } = require('child_process');
 const result = spawnSync(PYTHON, [FETCH_SCRIPT], { env: { ...process.env, TT_QUOTE_TOKEN_OUT: TOKEN_PATH }, encoding: 'utf8' });
 if (result.status !== 0) {
 fail('Auto-refresh of quote token failed', { stdout: result.stdout, stderr: result.stderr });
 }
}

function round5(x) { return Math.round(x / 5) * 5; }

function fail(msg, details = {}) {
  console.error(JSON.stringify({ ok: false, error: msg, ...details }, null, 2));
  process.exit(2);
}

function validateQuoteToken(qt) {
  const dxUrl = String(qt['dxlink-url'] || '');
  const level = String(qt.level || '');
  const expiresAt = qt['expires-at'] || qt.expiresAt || null;

  if (!qt.token) fail('Missing quote token', { reason: 'missing_token' });
  if (!dxUrl) fail('Missing dxLink URL', { reason: 'missing_dxlink_url' });

  if (/demo/i.test(level)) {
    fail('Refusing demo quote token for live snapshot', {
      reason: 'demo_level',
      level,
      dxlinkUrl: dxUrl,
    });
  }
  if (/tasty-demo-ws/i.test(dxUrl) || /\/delayed$/i.test(dxUrl) || /delayed/i.test(dxUrl)) {
    fail('Refusing delayed/demo dxLink endpoint for live snapshot', {
      reason: 'delayed_or_demo_dxlink',
      level,
      dxlinkUrl: dxUrl,
    });
  }
  if (expiresAt) {
    const exp = new Date(expiresAt).getTime();
    if (Number.isFinite(exp) && Date.now() >= exp) {
      fail('Refusing expired quote token', {
        reason: 'expired_token',
        expiresAt,
        dxlinkUrl: dxUrl,
        level,
      });
    }
  }
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function withRetries(label, fn) {
  let lastErr = null;
  for (let attempt = 1; attempt <= CONNECT_RETRIES; attempt++) {
    try {
      return await fn(attempt);
    } catch (err) {
      lastErr = err;
      if (attempt === CONNECT_RETRIES) break;
      await sleep(CONNECT_BACKOFF_MS * attempt);
    }
  }
  fail(`DXLink ${label} failed after retries`, {
    reason: 'dxlink_retry_exhausted',
    attempts: CONNECT_RETRIES,
    message: String(lastErr && lastErr.message ? lastErr.message : lastErr),
  });
}

function pickContracts(chain, spotGuess) {
  const exp = [...(chain.expirations || [])]
    .sort((a,b)=> (a['days-to-expiration']??9999) - (b['days-to-expiration']??9999))
    .slice(0, MAX_EXPIRIES);
  const center = round5(spotGuess || 600);
  const picks = STRIKE_OFFSETS.map((off) => center + off);
  const out = [];
  for (const e of exp) {
    const byStrike = new Map((e.strikes||[]).map(s => [Number(s['strike-price']), s]));
    for (const st of picks) {
      const row = byStrike.get(st);
      if (!row) continue;
      if (row['call-streamer-symbol']) out.push({expiry:e['expiration-date'], dte:e['days-to-expiration'], strike:st, side:'C', symbol:row['call-streamer-symbol']});
      if (row['put-streamer-symbol']) out.push({expiry:e['expiration-date'], dte:e['days-to-expiration'], strike:st, side:'P', symbol:row['put-streamer-symbol']});
    }
  }
  return out.slice(0, MAX_CONTRACTS);
}

(async () => {
  maybeRefreshQuoteToken();
  const qt = JSON.parse(fs.readFileSync(TOKEN_PATH, 'utf8')).data;
  validateQuoteToken(qt);
  const chain = JSON.parse(fs.readFileSync(CHAIN_PATH, 'utf8')).data.items[0];

  const spotGuess = Number(process.env.SPY_SPOT_GUESS || 0);
  const chainSpotHint = (() => {
    try {
      const exps = chain.expirations || [];
      if (exps.length === 0) return 0;
      const strikes = (exps[0].strikes || []).map(s => Number(s['strike-price'])).filter(Number.isFinite);
      if (strikes.length === 0) return 0;
      return strikes[Math.floor(strikes.length / 2)];
    } catch { return 0; }
  })();
  const contracts = pickContracts(chain, spotGuess || chainSpotHint || 600);
  const symbols = contracts.map(c => c.symbol);

  const underlyingStreamerSymbol = chain?.underlying?.['streamer-symbol'] || 'SPY';
  const snapshotId = `snapshot_${Date.now()}_${crypto.randomUUID().slice(0,8)}`;
  const out = {
    snapshotId,
    startedAt: new Date().toISOString(),
    source: 'dxlink-live',
    level: qt.level,
    underlying: { symbol: 'SPY', streamerSymbol: underlyingStreamerSymbol },
    contracts,
    data: {},
  };

  const client = new DXLinkWebSocketClient();
  client.setAuthToken(qt.token);
  await withRetries('connect', () => client.connect(qt['dxlink-url']));

  const feed = new DXLinkFeed(client, 'AUTO');
  feed.configure({ acceptDataFormat: FeedDataFormat.COMPACT });

  await withRetries('subscription', async () => {
    feed.addSubscriptions({ type: 'Quote', symbol: underlyingStreamerSymbol });
    for (const s of symbols) {
      for (const t of ['Quote', 'Greeks', 'Trade', 'Summary']) feed.addSubscriptions({ type: t, symbol: s });
    }
  });

  feed.addEventListener((events) => {
    for (const e of events) {
      if (e.eventSymbol === underlyingStreamerSymbol && e.eventType === 'Quote') {
        out.underlying.bid = e.bidPrice;
        out.underlying.ask = e.askPrice;
        if (Number.isFinite(e.bidPrice) && Number.isFinite(e.askPrice)) out.underlying.mark = (e.bidPrice + e.askPrice)/2;
      }
      if (!symbols.includes(e.eventSymbol)) continue;
      if (!out.data[e.eventSymbol]) out.data[e.eventSymbol] = {};
      const d = out.data[e.eventSymbol];
      d.eventSymbol = e.eventSymbol;
      if (e.eventType === 'Quote') {
        d.bid = e.bidPrice; d.ask = e.askPrice;
        if (Number.isFinite(e.bidPrice) && Number.isFinite(e.askPrice)) d.mark = (e.bidPrice + e.askPrice)/2;
      } else if (e.eventType === 'Greeks') {
        d.delta = e.delta; d.gamma = e.gamma; d.theta = e.theta; d.vega = e.vega; d.iv = e.volatility;
      } else if (e.eventType === 'Trade') {
        d.last = e.price; d.dayVolume = e.dayVolume;
      } else if (e.eventType === 'Summary') {
        d.openInterest = e.openInterest;
      }
      d.ts = new Date().toISOString();
    }
  });

  await new Promise(r => setTimeout(r, WAIT_MS));
  out.finishedAt = new Date().toISOString();

  // --- LIVENESS GATE ---
  const symbolsWithData = Object.keys(out.data).length;
  if (symbolsWithData < MIN_SYMBOLS_WITH_DATA) {
    fail('Too few symbols with data after wait window', {
      reason: 'insufficient_data',
      symbolsWithData,
      minRequired: MIN_SYMBOLS_WITH_DATA,
      waitMs: WAIT_MS,
    });
  }
  if (REQUIRE_UNDERLYING_QUOTE && !Number.isFinite(out.underlying.mark)) {
    fail('Underlying SPY quote missing after wait window', {
      reason: 'missing_underlying_quote',
      underlying: out.underlying,
      waitMs: WAIT_MS,
    });
  }
  // --- END LIVENESS GATE ---

  fs.mkdirSync(path.dirname(OUT_PATH), { recursive: true });
  fs.writeFileSync(OUT_PATH, JSON.stringify(out, null, 2));
  console.log(JSON.stringify({ ok: true, snapshot_id: snapshotId, outPath: OUT_PATH, contracts: contracts.length, symbolsWithData }, null, 2));
  process.exit(0);
})();
