import { type Signup, emailKey } from "../shared/schemas";

export interface SignupRow {
  id: number;
  email: string;
  networks: string | null;
  note: string | null;
  source: string | null;
  created_at: string;
}

/**
 * Record a signup, or return the existing one.
 *
 * `ON CONFLICT DO UPDATE` rather than a read-then-write: two taps on a slow
 * phone are two concurrent requests, and a check-then-insert lets both through.
 * The update is a no-op on the key columns so a second signup cannot overwrite
 * the first one's note with an empty one.
 */
export async function recordSignup(
  db: D1Database,
  input: Signup,
): Promise<{ row: SignupRow; created: boolean }> {
  const key = emailKey(input.email);
  const before = await db
    .prepare("SELECT id FROM signups WHERE email_key = ?")
    .bind(key)
    .first<{ id: number }>();

  const row = await db
    .prepare(
      `INSERT INTO signups (email, email_key, networks, note, source)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(email_key) DO UPDATE SET
         networks = COALESCE(NULLIF(excluded.networks, ''), signups.networks),
         note     = COALESCE(NULLIF(excluded.note, ''), signups.note)
       RETURNING id, email, networks, note, source, created_at`,
    )
    .bind(
      input.email.trim(),
      key,
      input.networks ?? null,
      input.note ?? null,
      input.source ?? null,
    )
    .first<SignupRow>();

  if (!row) throw new Error("signup insert returned no row");
  return { row, created: before === null };
}

export async function listSignups(db: D1Database, limit = 200): Promise<SignupRow[]> {
  const { results } = await db
    .prepare(
      `SELECT id, email, networks, note, source, created_at
       FROM signups ORDER BY created_at DESC LIMIT ?`,
    )
    .bind(Math.min(Math.max(limit, 1), 1000))
    .all<SignupRow>();
  return results ?? [];
}

export async function countSignups(db: D1Database): Promise<number> {
  const row = await db.prepare("SELECT COUNT(*) AS n FROM signups").first<{ n: number }>();
  return row?.n ?? 0;
}
