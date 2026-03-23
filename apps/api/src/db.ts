import { Client } from 'pg'

export async function upsertUserFromClerk(input: { clerkId: string; email?: string | null; tier?: string | null }) {
  const databaseUrl = process.env.DATABASE_URL
  if (!databaseUrl) {
    return { persisted: false, reason: 'missing_database_url' as const }
  }

  const client = new Client({ connectionString: databaseUrl })
  await client.connect()
  try {
    await client.query(
      `INSERT INTO users (clerk_id, email, tier)
       VALUES ($1, $2, COALESCE($3, 'free'))
       ON CONFLICT (clerk_id)
       DO UPDATE SET email = EXCLUDED.email, tier = COALESCE(EXCLUDED.tier, users.tier)`,
      [input.clerkId, input.email ?? null, input.tier ?? 'free'],
    )
    return { persisted: true as const }
  } finally {
    await client.end()
  }
}
