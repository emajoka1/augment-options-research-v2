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

function round5(x) { return Math.round(x / 5) * 5; }

function pickContracts(chain, spotGuess) {
  const exp = [...(chain.expirations || [])].sort((a,b)=> (a['days-to-expiration']??9999) - (b['days-to-expiration']??9999)).slice(0,2);
  const center = round5(spotGuess || 600);
  const picks = [center - 25, center - 20, center - 15, center - 10, center - 5, center, center + 5, center + 10, center + 15, center + 20, center + 25];
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
  return out.slice(0, 44);
}

(async () => {
  const qt = JSON.parse(fs.readFileSync(TOKEN_PATH, 'utf8')).data;
  const chain = JSON.parse(fs.readFileSync(CHAIN_PATH, 'utf8')).data.items[0];

  const contracts = pickContracts(chain, 680);
  const symbols = contracts.map(c => c.symbol);

  const snapshotId = `snapshot_${Date.now()}_${crypto.randomUUID().slice(0,8)}`;
  const out = {
    snapshotId,
    startedAt: new Date().toISOString(),
    source: 'dxlink-delayed',
    level: qt.level,
    underlying: { symbol: 'SPY' },
    contracts,
    data: {},
  };

  const client = new DXLinkWebSocketClient();
  client.setAuthToken(qt.token);
  await client.connect(qt['dxlink-url']);

  const feed = new DXLinkFeed(client, 'AUTO');
  feed.configure({ acceptDataFormat: FeedDataFormat.FULL });

  feed.addSubscriptions({ type: 'Quote', symbol: 'SPY' });
  for (const s of symbols) {
    for (const t of ['Quote','Greeks','Trade','Summary']) feed.addSubscriptions({ type: t, symbol: s });
  }

  feed.addEventListener((events) => {
    for (const e of events) {
      if (e.eventSymbol === 'SPY' && e.eventType === 'Quote') {
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

  fs.mkdirSync(path.dirname(OUT_PATH), { recursive: true });
  fs.writeFileSync(OUT_PATH, JSON.stringify(out, null, 2));
  console.log(JSON.stringify({ ok: true, snapshot_id: snapshotId, outPath: OUT_PATH, contracts: contracts.length, symbolsWithData: Object.keys(out.data).length }, null, 2));
  process.exit(0);
})();
