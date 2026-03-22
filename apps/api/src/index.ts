import { verifyToken } from '@clerk/backend'
import { Hono } from 'hono'
import { cors } from 'hono/cors'

const FASTAPI_BASE = process.env.FASTAPI_BASE_URL ?? 'http://localhost:8080'
const CORS_ORIGINS = (process.env.CORS_ORIGINS ?? 'http://localhost:3000').split(',').map((v) => v.trim())
const FREE_LIMIT = Number(process.env.RATE_LIMIT_FREE_PER_MIN ?? 100)
const PRO_LIMIT = Number(process.env.RATE_LIMIT_PRO_PER_MIN ?? 1000)
const AUTH_OPTIONAL = (process.env.AUTH_OPTIONAL ?? 'true').toLowerCase() === 'true'
const CLERK_SECRET_KEY = process.env.CLERK_SECRET_KEY

const app = new Hono()
const buckets = new Map<string, { count: number; resetAt: number }>()

app.use(
  '*',
  cors({
    origin: CORS_ORIGINS,
    allowMethods: ['GET', 'POST', 'OPTIONS'],
    allowHeaders: ['Content-Type', 'Authorization'],
  }),
)

type Identity = { ok: boolean; tier: 'free' | 'pro'; subject: string; authMode: 'clerk' | 'dev' | 'none' }

async function getIdentity(c: any): Promise<Identity> {
  const auth = c.req.header('authorization')

  if (!auth) {
    return { ok: AUTH_OPTIONAL, tier: 'free', subject: 'anonymous', authMode: AUTH_OPTIONAL ? 'none' : 'dev' }
  }

  if (!auth.startsWith('Bearer ')) {
    return { ok: false, tier: 'free', subject: 'invalid', authMode: 'dev' }
  }

  const token = auth.slice('Bearer '.length)

  if (CLERK_SECRET_KEY) {
    try {
      const verified = await verifyToken(token, { secretKey: CLERK_SECRET_KEY })
      const tierClaim = (verified?.metadata as any)?.tier ?? (verified as any)?.tier ?? 'free'
      return {
        ok: true,
        tier: tierClaim === 'pro' ? 'pro' : 'free',
        subject: verified.sub ?? 'clerk-user',
        authMode: 'clerk',
      }
    } catch {
      return { ok: false, tier: 'free', subject: 'invalid-clerk-token', authMode: 'clerk' }
    }
  }

  if (AUTH_OPTIONAL) {
    return { ok: true, tier: 'free', subject: 'dev-fallback', authMode: 'dev' }
  }

  return { ok: false, tier: 'free', subject: 'missing-clerk-config', authMode: 'dev' }
}

function enforceRateLimit(subject: string, tier: string) {
  const now = Date.now()
  const windowMs = 60_000
  const limit = tier === 'pro' ? PRO_LIMIT : FREE_LIMIT
  const current = buckets.get(subject)
  if (!current || current.resetAt <= now) {
    buckets.set(subject, { count: 1, resetAt: now + windowMs })
    return { ok: true, remaining: limit - 1 }
  }
  if (current.count >= limit) {
    return { ok: false, remaining: 0, retryAfterMs: current.resetAt - now }
  }
  current.count += 1
  buckets.set(subject, current)
  return { ok: true, remaining: limit - current.count }
}

app.get('/health', async (c) => {
  let upstream: unknown = null
  let upstreamOk = false
  try {
    const response = await fetch(`${FASTAPI_BASE}/v1/health`)
    upstreamOk = response.ok
    upstream = await response.json()
  } catch {
    upstream = { status: 'unreachable' }
  }

  return c.json({
    status: upstreamOk ? 'ok' : 'degraded',
    service: 'api-gateway',
    fastapi: upstream,
    auth_optional: AUTH_OPTIONAL,
    clerk_configured: Boolean(CLERK_SECRET_KEY),
  })
})

app.post('/api/webhooks/clerk', async (c) => {
  const payload = await c.req.json().catch(() => ({}))
  const type = payload?.type ?? null
  const data = payload?.data ?? null
  return c.json({
    status: 'accepted',
    received: type,
    user_hint: data?.id ?? null,
  }, 202)
})

app.use('/api/v1/*', async (c, next) => {
  const identity = await getIdentity(c)
  if (!identity.ok) {
    return c.json({ error: 'unauthorized', auth_mode: identity.authMode }, 401)
  }
  const rl = enforceRateLimit(identity.subject, identity.tier)
  if (!rl.ok) {
    c.header('Retry-After', String(Math.ceil((rl.retryAfterMs ?? 0) / 1000)))
    return c.json({ error: 'rate_limited' }, 429)
  }
  c.set('identity', identity)
  c.header('X-RateLimit-Remaining', String(rl.remaining))
  c.header('X-Auth-Mode', identity.authMode)
  await next()
})

app.all('/api/v1/*', async (c) => {
  const path = c.req.path.replace(/^\/api/, '')
  const query = new URLSearchParams(c.req.query()).toString()
  const url = `${FASTAPI_BASE}${path}${query ? `?${query}` : ''}`
  const method = c.req.method
  const headers = new Headers(c.req.header())
  headers.delete('host')

  const identity = c.get('identity') as Identity | undefined
  if (identity) {
    headers.set('x-openclaw-user-sub', identity.subject)
    headers.set('x-openclaw-user-tier', identity.tier)
  }

  const init: RequestInit = { method, headers }
  if (!['GET', 'HEAD'].includes(method)) {
    init.body = await c.req.text()
  }

  const response = await fetch(url, init)
  const body = await response.text()
  return new Response(body, { status: response.status, headers: response.headers })
})

export default {
  port: Number(process.env.PORT ?? 8787),
  fetch: app.fetch,
}
