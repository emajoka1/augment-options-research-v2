#!/usr/bin/env node
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const { DXLinkWebSocketClient, DXLinkFeed, FeedDataFormat, FeedContract } = require(process.env.DXLINK_API_MODULE || '/Users/forge/lab/tastytrade/node_modules/@dxfeed/dxlink-api');

const DEFAULT_DATA_DIR = process.env.DXLINK_DATA_DIR || path.join(os.homedir(), 'lab/data/tastytrade');
const TOKEN_PATH = process.env.SPY_TOKEN_PATH || path.join(DEFAULT_DATA_DIR, 'api_quote_token.json');
const CHAIN_PATH = process.env.DXLINK_CHAIN_PATH || process.env.SPY_CHAIN_PATH || path.join(DEFAULT_DATA_DIR, 'SPY_nested_chain.json');
const OUT_DIR = process.env.DXLINK_STREAM_OUT_DIR || DEFAULT_DATA_DIR;
const SNAPSHOT_PATH = process.env.DXLINK_STREAM_SNAPSHOT_OUT || path.join(OUT_DIR, 'dxlink_live_snapshot.json');
const CANDLES_PATH = process.env.DXLINK_STREAM_CANDLES_OUT || path.join(OUT_DIR, 'dxlink_live_candles.json');
const DAILY_CLOSES_PATH = process.env.DXLINK_STREAM_DAILY_CLOSES_OUT || path.join(OUT_DIR, 'dxlink_daily_closes.json');
const STATUS_PATH = process.env.DXLINK_STREAM_STATUS_OUT || path.join(OUT_DIR, 'dxlink_live_status.json');
const AUTO_REFRESH = String(process.env.SPY_AUTO_REFRESH_TOKEN || '1') !== '0';
const FETCH_SCRIPT = process.env.SPY_FETCH_QUOTE_TOKEN_SCRIPT || path.join(__dirname, 'fetch_tasty_live_quote_token.py');
const PYTHON = process.env.SPY_FETCH_QUOTE_TOKEN_PYTHON || path.join(__dirname, '..', '.venv', 'bin', 'python');
const CONTROL_POLL_MS = Number(process.env.DXLINK_CONTROL_POLL_MS || 5000);
const FLUSH_MS = Number(process.env.DXLINK_STREAM_FLUSH_MS || 5000);
const RING_REFRESH_MS = Number(process.env.DXLINK_RING_REFRESH_MS || 30000);
const HEALTH_TIMEOUT_MS = Number(process.env.DXLINK_HEALTH_TIMEOUT_MS || 45000);
const STARTUP_GRACE_MS = Number(process.env.DXLINK_STARTUP_GRACE_MS || 60000);
const CONNECT_BACKOFF_MS = Number(process.env.DXLINK_CONNECT_BACKOFF_MS || 2500);
const AGGREGATION_PERIOD = Number(process.env.DXLINK_ACCEPT_AGGREGATION_PERIOD || 0.1);
const UNDERLYING_SYMBOL = String(process.env.DXLINK_UNDERLYING_SYMBOL || 'SPY');
const MAX_EXPIRIES = Number(process.env.DXLINK_MAX_EXPIRIES || 4);
const STRIKE_OFFSETS = String(process.env.DXLINK_STRIKE_OFFSETS || '-40,-30,-25,-20,-15,-10,-5,0,5,10,15,20,25,30,40')
  .split(',')
  .map((v) => Number(v.trim()))
  .filter(Number.isFinite);
const MAX_CONTRACTS = Number(process.env.DXLINK_MAX_CONTRACTS || 120);
const CANDLE_WIDTH = String(process.env.DXLINK_CANDLE_WIDTH || '5m');
const CANDLE_LOOKBACK_MS = Number(process.env.DXLINK_CANDLE_LOOKBACK_MS || 3 * 24 * 60 * 60 * 1000);
const STATUS_STDOUT = String(process.env.DXLINK_STATUS_STDOUT || '1') !== '0';
const MARKET_TZ = 'America/New_York';
const MARKET_CLOSE_HOUR_ET = 16;
const VIX_SYMBOL = String(process.env.DXLINK_VIX_SYMBOL || 'VIX');
const US10Y_SYMBOL = String(process.env.DXLINK_US10Y_SYMBOL || '/ZNU6:XCBT');

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function fail(message, details = {}) {
  const error = new Error(message);
  error.details = details;
  throw error;
}

function writeJsonAtomic(filePath, data) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const tempPath = `${filePath}.tmp`;
  fs.writeFileSync(tempPath, JSON.stringify(data, null, 2));
  fs.renameSync(tempPath, filePath);
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
    fail('Quote token missing/expired and auto-refresh env is incomplete', { missingEnv });
  }
  const result = spawnSync(PYTHON, [FETCH_SCRIPT], {
    env: { ...process.env, TT_QUOTE_TOKEN_OUT: TOKEN_PATH },
    encoding: 'utf8',
  });
  if (result.status !== 0) {
    fail('Auto-refresh of quote token failed', { stdout: result.stdout, stderr: result.stderr });
  }
}

function loadQuoteToken() {
  maybeRefreshQuoteToken();
  const qt = JSON.parse(fs.readFileSync(TOKEN_PATH, 'utf8')).data || {};
  const dxUrl = String(qt['dxlink-url'] || '');
  const level = String(qt.level || '');
  if (!qt.token) fail('Missing quote token');
  if (!dxUrl) fail('Missing dxLink URL');
  if (/demo/i.test(level) || /delayed/i.test(dxUrl) || /tasty-demo-ws/i.test(dxUrl)) {
    fail('Refusing delayed/demo dxLink endpoint', { level, dxlinkUrl: dxUrl });
  }
  return qt;
}

function loadChainSnapshot() {
  const raw = JSON.parse(fs.readFileSync(CHAIN_PATH, 'utf8'));
  if (raw?.data?.items?.[0]) return raw.data.items[0];
  if (raw?.items?.[0]) return raw.items[0];
  fail('Unsupported chain snapshot shape', { chainPath: CHAIN_PATH });
}

function roundStrike(x, spacing = 5) {
  return Math.round(x / spacing) * spacing;
}

function dedupe(list) {
  return [...new Set(list)];
}

function computeDte(expiryValue, now = new Date()) {
  if (!expiryValue) return null;
  const expiryAtClose = new Date(`${expiryValue}T${String(MARKET_CLOSE_HOUR_ET).padStart(2, '0')}:00:00-04:00`);
  if (Number.isNaN(expiryAtClose.getTime())) return null;
  const deltaSeconds = (expiryAtClose.getTime() - now.getTime()) / 1000;
  if (deltaSeconds <= 0) return 0;
  return Math.max(0, Math.floor(deltaSeconds / 86400));
}

function contractMetaMap(contracts) {
  return Object.fromEntries(contracts.map((c) => [c.symbol, c]));
}

function pickContracts(chain, spot) {
  const expirations = [...(chain.expirations || [])]
    .sort((a, b) => (a['days-to-expiration'] ?? 9999) - (b['days-to-expiration'] ?? 9999))
    .slice(0, MAX_EXPIRIES);
  const center = roundStrike(Number.isFinite(spot) && spot > 0 ? spot : Number(process.env.DXLINK_SPOT_GUESS || 0)) || 0;
  const desiredStrikes = STRIKE_OFFSETS.map((offset) => center + offset);
  const contracts = [];
  const now = new Date();
  for (const expiry of expirations) {
    const byStrike = new Map((expiry.strikes || []).map((row) => [Number(row['strike-price']), row]));
    for (const strike of desiredStrikes) {
      const row = byStrike.get(strike);
      if (!row) continue;
      if (row['call-streamer-symbol']) {
        contracts.push({
          symbol: row['call-streamer-symbol'],
          strike,
          side: 'C',
          expiry: expiry['expiration-date'],
          dte: computeDte(expiry['expiration-date'], now),
          streamerSymbol: row['call-streamer-symbol'],
        });
      }
      if (row['put-streamer-symbol']) {
        contracts.push({
          symbol: row['put-streamer-symbol'],
          strike,
          side: 'P',
          expiry: expiry['expiration-date'],
          dte: computeDte(expiry['expiration-date'], now),
          streamerSymbol: row['put-streamer-symbol'],
        });
      }
    }
  }
  return contracts.slice(0, MAX_CONTRACTS);
}

function buildCandleSymbol(streamerSymbol) {
  return `${streamerSymbol}{=${CANDLE_WIDTH}}`;
}

function midpoint(bid, ask) {
  return Number.isFinite(bid) && Number.isFinite(ask) ? (bid + ask) / 2 : undefined;
}

async function main() {
  const state = {
    startedAt: new Date().toISOString(),
    lastFlushAt: null,
    lastRingRefreshAt: null,
    lastEventAt: null,
    reconnects: 0,
    subscriptionsVersion: 0,
    connectionState: 'NOT_CONNECTED',
    authState: 'UNAUTHORIZED',
    marketFeedChannel: 1,
    candleFeedChannel: 3,
    underlying: {
      symbol: UNDERLYING_SYMBOL,
      streamerSymbol: UNDERLYING_SYMBOL,
    },
    vix: {
      symbol: 'VIX',
      streamerSymbol: VIX_SYMBOL,
    },
    us10y: {
      symbol: 'ZN',
      streamerSymbol: US10Y_SYMBOL,
      proxy: 'ZN_futures_proxy',
    },
    quoteToken: {
      level: null,
      expiresAt: null,
      dxlinkUrl: null,
    },
    feeds: {
      market: {
        contract: FeedContract.STREAM,
        channel: 1,
        compactFields: {
          Trade: ['eventType', 'eventSymbol', 'price', 'dayVolume', 'size'],
          Quote: ['eventType', 'eventSymbol', 'bidPrice', 'askPrice', 'bidSize', 'askSize'],
          Greeks: ['eventType', 'eventSymbol', 'volatility', 'delta', 'gamma', 'theta', 'rho', 'vega'],
          Summary: ['eventType', 'eventSymbol', 'openInterest', 'dayOpenPrice', 'dayHighPrice', 'dayLowPrice', 'prevDayClosePrice'],
        },
      },
      candles: {
        contract: FeedContract.HISTORY,
        channel: 3,
        compactFields: {
          Candle: ['eventType', 'eventSymbol', 'time', 'open', 'high', 'low', 'close', 'volume'],
        },
      },
    },
    health: {
      ok: false,
      stale: false,
      reason: 'starting',
    },
  };

  const marketData = {};
  const candlesByTime = new Map();
  const activeSubscriptions = new Set();
  let client = null;
  let marketFeed = null;
  let candleFeed = null;
  let chain = null;
  let contractMeta = {};
  let activeOptionSymbols = [];
  let activeUnderlyingSymbol = UNDERLYING_SYMBOL;
  let activeCandleSymbol = buildCandleSymbol(UNDERLYING_SYMBOL);
  let shouldStop = false;

function flushOutputs() {
    const now = Date.now();
    const candleRows = [...candlesByTime.values()].sort((a, b) => a.time - b.time);
    const dailyCloseRows = buildDailyCloseRows(candleRows);
    const snapshot = {
      source: 'dxlink-stream-daemon',
      generatedAt: new Date().toISOString(),
      underlying: state.underlying,
      vix: state.vix,
      us10y: state.us10y,
      optionRing: activeOptionSymbols.map((symbol) => contractMeta[symbol]).filter(Boolean),
      data: marketData,
    };
    const candles = {
      source: 'dxlink-stream-daemon',
      generatedAt: new Date().toISOString(),
      symbol: activeCandleSymbol,
      lookbackMs: CANDLE_LOOKBACK_MS,
      candles: candleRows,
      realizedVol: computeRealizedVol(candleRows),
    };
    const dailyCloses = {
      source: 'dxlink-stream-daemon',
      generatedAt: new Date().toISOString(),
      symbol: activeCandleSymbol,
      timezone: MARKET_TZ,
      closes: dailyCloseRows,
    };
    const status = {
      source: 'dxlink-stream-daemon',
      generatedAt: new Date().toISOString(),
      startedAt: state.startedAt,
      controlChannel: {
        channel: 0,
        note: 'connection/auth/keepalive handled by DXLinkWebSocketClient SDK',
      },
      connectionState: state.connectionState,
      authState: state.authState,
      health: state.health,
      reconnects: state.reconnects,
      subscriptionsVersion: state.subscriptionsVersion,
      activeOptionSymbols,
      activeCandleSymbol,
      outputFiles: {
        snapshot: SNAPSHOT_PATH,
        candles: CANDLES_PATH,
        dailyCloses: DAILY_CLOSES_PATH,
        status: STATUS_PATH,
      },
      quoteToken: state.quoteToken,
      feeds: state.feeds,
      underlying: state.underlying,
      vix: state.vix,
      us10y: state.us10y,
      counts: {
        optionSymbols: activeOptionSymbols.length,
        symbolsWithData: Object.keys(marketData).length,
        candles: candleRows.length,
      },
      timings: {
        lastEventAt: state.lastEventAt,
        lastFlushAt: state.lastFlushAt,
        lastRingRefreshAt: state.lastRingRefreshAt,
        secondsSinceEvent: state.lastEventAt ? Math.round((now - new Date(state.lastEventAt).getTime()) / 1000) : null,
      },
    };
    writeJsonAtomic(SNAPSHOT_PATH, snapshot);
    writeJsonAtomic(CANDLES_PATH, candles);
    writeJsonAtomic(DAILY_CLOSES_PATH, dailyCloses);
    writeJsonAtomic(STATUS_PATH, status);
    state.lastFlushAt = status.generatedAt;
    if (STATUS_STDOUT) {
      console.log(JSON.stringify({
        ts: status.generatedAt,
        health: status.health,
        connectionState: status.connectionState,
        authState: status.authState,
        optionSymbols: status.counts.optionSymbols,
        symbolsWithData: status.counts.symbolsWithData,
        candles: status.counts.candles,
      }));
    }
  }

  function updateHealth(reason = 'running') {
    const now = Date.now();
    const startedAtMs = new Date(state.startedAt).getTime();
    const inStartupGrace = Number.isFinite(startedAtMs) && (now - startedAtMs) < STARTUP_GRACE_MS;
    const lastEventMs = state.lastEventAt ? new Date(state.lastEventAt).getTime() : 0;
    const stale = !inStartupGrace && (!lastEventMs || (now - lastEventMs) > HEALTH_TIMEOUT_MS);
    state.health = {
      ok: state.connectionState === 'CONNECTED' && state.authState === 'AUTHORIZED' && !stale,
      stale,
      reason: stale ? 'stale_feed' : (inStartupGrace && !lastEventMs ? 'startup_grace' : reason),
      checkedAt: new Date().toISOString(),
    };
  }

  function computeRealizedVol(candles) {
    if (candles.length < 2) return null;
    const closes = candles.map((row) => Number(row.close)).filter(Number.isFinite);
    if (closes.length < 2) return null;
    const returns = [];
    for (let i = 1; i < closes.length; i += 1) {
      returns.push(Math.log(closes[i] / closes[i - 1]));
    }
    if (!returns.length) return null;
    const mean = returns.reduce((acc, value) => acc + value, 0) / returns.length;
    const variance = returns.reduce((acc, value) => acc + ((value - mean) ** 2), 0) / returns.length;
    const periodsPerYear = CANDLE_WIDTH === '1m' ? 252 * 390 : CANDLE_WIDTH === '5m' ? 252 * 78 : 252;
    return {
      window: returns.length,
      annualized: Math.sqrt(variance) * Math.sqrt(periodsPerYear),
      period: CANDLE_WIDTH,
    };
  }

  function buildDailyCloseRows(candles) {
    const byDay = new Map();
    const formatter = new Intl.DateTimeFormat('en-CA', { timeZone: MARKET_TZ, year: 'numeric', month: '2-digit', day: '2-digit' });
    for (const row of candles) {
      const close = Number(row.close);
      const ts = Number(row.time);
      if (!Number.isFinite(close) || !Number.isFinite(ts)) continue;
      const day = formatter.format(new Date(ts));
      const existing = byDay.get(day);
      if (!existing || ts > existing.time) {
        byDay.set(day, { date: day, time: ts, close });
      }
    }
    return [...byDay.values()].sort((a, b) => a.time - b.time);
  }

  function noteEvent() {
    state.lastEventAt = new Date().toISOString();
    updateHealth();
  }

  function applyUnderlyingQuote(event) {
    state.underlying.bid = event.bidPrice;
    state.underlying.ask = event.askPrice;
    const mark = midpoint(event.bidPrice, event.askPrice);
    if (Number.isFinite(mark)) state.underlying.mark = mark;
    noteEvent();
  }

  function applyUnderlyingTrade(event) {
    if (Number.isFinite(event.price)) state.underlying.last = event.price;
    noteEvent();
  }

  function applyVixQuote(event) {
    state.vix.bid = event.bidPrice;
    state.vix.ask = event.askPrice;
    const mark = midpoint(event.bidPrice, event.askPrice);
    if (Number.isFinite(mark)) state.vix.mark = mark;
    noteEvent();
  }

  function applyVixTrade(event) {
    if (Number.isFinite(event.price)) state.vix.last = event.price;
    noteEvent();
  }

  function applyVixSummary(event) {
    if (Number.isFinite(event.prevDayClosePrice)) state.vix.prevDayClosePrice = event.prevDayClosePrice;
    if (Number.isFinite(event.dayOpenPrice)) state.vix.dayOpenPrice = event.dayOpenPrice;
    if (Number.isFinite(event.dayHighPrice)) state.vix.dayHighPrice = event.dayHighPrice;
    if (Number.isFinite(event.dayLowPrice)) state.vix.dayLowPrice = event.dayLowPrice;
    noteEvent();
  }

  function applyUs10YQuote(event) {
    state.us10y.bid = event.bidPrice;
    state.us10y.ask = event.askPrice;
    const mark = midpoint(event.bidPrice, event.askPrice);
    if (Number.isFinite(mark)) state.us10y.mark = mark;
    noteEvent();
  }

  function applyUs10YTrade(event) {
    if (Number.isFinite(event.price)) state.us10y.last = event.price;
    noteEvent();
  }

  function applyUs10YSummary(event) {
    if (Number.isFinite(event.prevDayClosePrice)) state.us10y.prevDayClosePrice = event.prevDayClosePrice;
    if (Number.isFinite(event.dayOpenPrice)) state.us10y.dayOpenPrice = event.dayOpenPrice;
    if (Number.isFinite(event.dayHighPrice)) state.us10y.dayHighPrice = event.dayHighPrice;
    if (Number.isFinite(event.dayLowPrice)) state.us10y.dayLowPrice = event.dayLowPrice;
    noteEvent();
  }

  function applyOptionEvent(event) {
    if (!marketData[event.eventSymbol]) {
      marketData[event.eventSymbol] = {
        eventSymbol: event.eventSymbol,
        ...contractMeta[event.eventSymbol],
      };
    }
    const row = marketData[event.eventSymbol];
    if (event.eventType === 'Quote') {
      row.bid = event.bidPrice;
      row.ask = event.askPrice;
      const mark = midpoint(event.bidPrice, event.askPrice);
      if (Number.isFinite(mark)) row.mark = mark;
      row.bidSize = event.bidSize;
      row.askSize = event.askSize;
    } else if (event.eventType === 'Trade') {
      row.last = event.price;
      row.dayVolume = event.dayVolume;
      row.lastSize = event.size;
    } else if (event.eventType === 'Greeks') {
      row.iv = event.volatility;
      row.delta = event.delta;
      row.gamma = event.gamma;
      row.theta = event.theta;
      row.rho = event.rho;
      row.vega = event.vega;
    } else if (event.eventType === 'Summary') {
      row.openInterest = event.openInterest;
      row.dayOpenPrice = event.dayOpenPrice;
      row.dayHighPrice = event.dayHighPrice;
      row.dayLowPrice = event.dayLowPrice;
      row.prevDayClosePrice = event.prevDayClosePrice;
    }
    row.updatedAt = new Date().toISOString();
    noteEvent();
  }

  function applyCandleEvent(event) {
    if (event.eventType !== 'Candle' || !Number.isFinite(event.time)) return;
    candlesByTime.set(event.time, {
      eventSymbol: event.eventSymbol,
      time: event.time,
      open: event.open,
      high: event.high,
      low: event.low,
      close: event.close,
      volume: event.volume,
      updatedAt: new Date().toISOString(),
    });
    const cutoff = Date.now() - CANDLE_LOOKBACK_MS;
    for (const [time] of candlesByTime) {
      if (time < cutoff) candlesByTime.delete(time);
    }
    noteEvent();
  }

  async function refreshRingSubscriptions(force = false) {
    chain = loadChainSnapshot();
    const streamerSymbol = chain?.underlying?.['streamer-symbol'] || chain?.underlying?.streamerSymbol || chain?.['underlying-symbol'] || UNDERLYING_SYMBOL;
    const previousUnderlyingSymbol = activeUnderlyingSymbol;
    state.underlying.streamerSymbol = streamerSymbol;
    activeUnderlyingSymbol = streamerSymbol;
    if (marketFeed && previousUnderlyingSymbol !== activeUnderlyingSymbol) {
      marketFeed.removeSubscriptions({ type: 'Quote', symbol: previousUnderlyingSymbol });
      marketFeed.removeSubscriptions({ type: 'Trade', symbol: previousUnderlyingSymbol });
      marketFeed.addSubscriptions({ type: 'Quote', symbol: activeUnderlyingSymbol });
      marketFeed.addSubscriptions({ type: 'Trade', symbol: activeUnderlyingSymbol });
    }
    const spot = state.underlying.mark || state.underlying.last || Number(process.env.DXLINK_SPOT_GUESS || 0);
    const nextContracts = pickContracts(chain, spot);
    const nextSymbols = dedupe(nextContracts.map((row) => row.streamerSymbol));
    const nextMeta = contractMetaMap(nextContracts);
    const same = nextSymbols.length === activeOptionSymbols.length && nextSymbols.every((symbol, idx) => symbol === activeOptionSymbols[idx]);
    activeCandleSymbol = buildCandleSymbol(streamerSymbol);
    if (!force && same) {
      state.lastRingRefreshAt = new Date().toISOString();
      return;
    }
    contractMeta = nextMeta;
    const nextSet = new Set(nextSymbols);
    const prevSet = new Set(activeOptionSymbols);
    const removeSymbols = activeOptionSymbols.filter((symbol) => !nextSet.has(symbol));
    const addSymbols = nextSymbols.filter((symbol) => !prevSet.has(symbol));

    for (const symbol of removeSymbols) {
      for (const type of ['Quote', 'Greeks', 'Trade', 'Summary']) {
        marketFeed.removeSubscriptions({ type, symbol });
      }
      activeSubscriptions.delete(symbol);
      delete marketData[symbol];
    }
    for (const symbol of addSymbols) {
      for (const type of ['Quote', 'Greeks', 'Trade', 'Summary']) {
        marketFeed.addSubscriptions({ type, symbol });
      }
      activeSubscriptions.add(symbol);
    }

    candleFeed.clearSubscriptions();
    candlesByTime.clear();
    candleFeed.addSubscriptions({
      type: 'Candle',
      symbol: activeCandleSymbol,
      fromTime: Date.now() - CANDLE_LOOKBACK_MS,
    });

    activeOptionSymbols = nextSymbols;
    state.subscriptionsVersion += 1;
    state.lastRingRefreshAt = new Date().toISOString();
  }

  async function connectAndRun() {
    const quoteToken = loadQuoteToken();
    state.quoteToken = {
      level: quoteToken.level,
      expiresAt: quoteToken['expires-at'] || quoteToken.expiresAt || null,
      dxlinkUrl: quoteToken['dxlink-url'],
    };

    client = new DXLinkWebSocketClient({ maxReconnectAttempts: -1 });
    client.setAuthToken(quoteToken.token);
    client.addConnectionStateChangeListener((connectionState) => {
      state.connectionState = connectionState;
      updateHealth('connection_state_changed');
    });
    client.addAuthStateChangeListener((authState) => {
      state.authState = authState;
      updateHealth('auth_state_changed');
    });
    client.addErrorListener((error) => {
      state.health = {
        ok: false,
        stale: false,
        reason: 'client_error',
        error: String(error?.message || error),
        checkedAt: new Date().toISOString(),
      };
    });

    await client.connect(quoteToken['dxlink-url']);

    activeOptionSymbols = [];
    activeUnderlyingSymbol = UNDERLYING_SYMBOL;
    contractMeta = {};
    for (const key of Object.keys(marketData)) delete marketData[key];
    candlesByTime.clear();
    marketFeed = new DXLinkFeed(client, FeedContract.STREAM);
    candleFeed = new DXLinkFeed(client, FeedContract.HISTORY);

    marketFeed.configure({
      acceptAggregationPeriod: AGGREGATION_PERIOD,
      acceptDataFormat: FeedDataFormat.COMPACT,
      acceptEventFields: state.feeds.market.compactFields,
    });
    candleFeed.configure({
      acceptAggregationPeriod: AGGREGATION_PERIOD,
      acceptDataFormat: FeedDataFormat.COMPACT,
      acceptEventFields: state.feeds.candles.compactFields,
    });

    marketFeed.addEventListener((events) => {
      for (const event of events) {
        if (event.eventSymbol === state.underlying.streamerSymbol && event.eventType === 'Quote') {
          applyUnderlyingQuote(event);
          continue;
        }
        if (event.eventSymbol === state.underlying.streamerSymbol && event.eventType === 'Trade') {
          applyUnderlyingTrade(event);
          continue;
        }
        if (event.eventSymbol === state.vix.streamerSymbol && event.eventType === 'Quote') {
          applyVixQuote(event);
          continue;
        }
        if (event.eventSymbol === state.vix.streamerSymbol && event.eventType === 'Trade') {
          applyVixTrade(event);
          continue;
        }
        if (event.eventSymbol === state.vix.streamerSymbol && event.eventType === 'Summary') {
          applyVixSummary(event);
          continue;
        }
        if (event.eventSymbol === state.us10y.streamerSymbol && event.eventType === 'Quote') {
          applyUs10YQuote(event);
          continue;
        }
        if (event.eventSymbol === state.us10y.streamerSymbol && event.eventType === 'Trade') {
          applyUs10YTrade(event);
          continue;
        }
        if (event.eventSymbol === state.us10y.streamerSymbol && event.eventType === 'Summary') {
          applyUs10YSummary(event);
          continue;
        }
        if (contractMeta[event.eventSymbol]) {
          applyOptionEvent(event);
        }
      }
    });

    candleFeed.addEventListener((events) => {
      for (const event of events) applyCandleEvent(event);
    });

    await refreshRingSubscriptions(true);
    marketFeed.addSubscriptions({ type: 'Quote', symbol: activeUnderlyingSymbol });
    marketFeed.addSubscriptions({ type: 'Trade', symbol: activeUnderlyingSymbol });
    marketFeed.addSubscriptions({ type: 'Quote', symbol: state.vix.streamerSymbol });
    marketFeed.addSubscriptions({ type: 'Trade', symbol: state.vix.streamerSymbol });
    marketFeed.addSubscriptions({ type: 'Summary', symbol: state.vix.streamerSymbol });
    marketFeed.addSubscriptions({ type: 'Quote', symbol: state.us10y.streamerSymbol });
    marketFeed.addSubscriptions({ type: 'Trade', symbol: state.us10y.streamerSymbol });
    marketFeed.addSubscriptions({ type: 'Summary', symbol: state.us10y.streamerSymbol });

    while (!shouldStop) {
      updateHealth();
      if (state.health.stale) {
        throw new Error(`Feed stale for more than ${HEALTH_TIMEOUT_MS}ms`);
      }
      const now = Date.now();
      if (!state.lastFlushAt || (now - new Date(state.lastFlushAt).getTime()) >= FLUSH_MS) {
        flushOutputs();
      }
      if (!state.lastRingRefreshAt || (now - new Date(state.lastRingRefreshAt).getTime()) >= RING_REFRESH_MS) {
        await refreshRingSubscriptions(false);
      }
      await sleep(CONTROL_POLL_MS);
    }
  }

  async function shutdown(signal) {
    shouldStop = true;
    state.health = {
      ok: false,
      stale: false,
      reason: `stopping:${signal}`,
      checkedAt: new Date().toISOString(),
    };
    try {
      flushOutputs();
    } catch {}
    try {
      if (client) client.close();
    } catch {}
    process.exit(0);
  }

  process.on('SIGINT', () => shutdown('SIGINT'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));

  while (!shouldStop) {
    try {
      state.reconnects += 1;
      await connectAndRun();
    } catch (error) {
      const details = error?.details || {};
      const stderr = String(details.stderr || '').trim();
      const stdout = String(details.stdout || '').trim();
      const diagnostic = [
        String(error?.message || error),
        stderr ? `stderr: ${stderr}` : null,
        stdout ? `stdout: ${stdout}` : null,
        details.missingEnv?.length ? `missing env: ${details.missingEnv.join(', ')}` : null,
      ].filter(Boolean).join(' | ');
      state.health = {
        ok: false,
        stale: false,
        reason: 'reconnecting',
        error: diagnostic,
        details: Object.keys(details).length ? details : undefined,
        checkedAt: new Date().toISOString(),
      };
      console.error(JSON.stringify({ event: 'reconnect_error', error: diagnostic, details }, null, 2));
      flushOutputs();
      try {
        if (client) client.close();
      } catch {}
      client = null;
      marketFeed = null;
      candleFeed = null;
      await sleep(CONNECT_BACKOFF_MS);
    }
  }
}

if (require.main === module) {
  main().catch((error) => {
    console.error(JSON.stringify({ ok: false, error: error.message, details: error.details || null }, null, 2));
    process.exit(2);
  });
}

module.exports = {
  pickContracts,
  buildCandleSymbol,
  roundStrike,
};
