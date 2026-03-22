import { Hono } from 'hono'
import { cors } from 'hono/cors'

const FASTAPI_BASE = process.env.FASTAPI_BASE_URL ?? 'http://localhost:8080'

const app = new Hono()

app.use(
  '*',
  cors({
    origin: ['http://localhost:3000'],
    allowMethods: ['GET', 'POST', 'OPTIONS'],
    allowHeaders: ['Content-Type', 'Authorization'],
  }),
)

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
  })
})

app.all('/api/v1/*', async (c) => {
  const path = c.req.path.replace(/^\/api/, '')
  const url = new URL(path + (c.req.query() ? `?${new URLSearchParams(c.req.query()).toString()}` : ''), FASTAPI_BASE)
  const method = c.req.method
  const headers = new Headers(c.req.header())
  headers.delete('host')

  const init: RequestInit = {
    method,
    headers,
  }

  if (!['GET', 'HEAD'].includes(method)) {
    init.body = await c.req.text()
  }

  const response = await fetch(url, init)
  const body = await response.text()
  return new Response(body, { status: response.status, headers: response.headers })
})

export default app
