/**
 * Cloudflare Access assertion verification.
 *
 * Access gates at the edge so unauthenticated traffic never reaches the admin
 * routes. The Worker then verifies the assertion itself — signature, issuer,
 * audience, expiry, email allowlist — rather than trusting the header's mere
 * presence, which is forgeable by anything that can reach the origin.
 *
 * Fail closed everywhere. An unset or empty allowlist reads as *nobody*, never
 * *everybody*: forget to upload the secret and the admin area refuses every
 * request instead of falling open.
 */
import type { MiddlewareHandler } from "hono";

interface Jwk {
  kid: string;
  kty: string;
  alg?: string;
  n: string;
  e: string;
}

const JWKS_TTL_MS = 60 * 60 * 1000;
let cached: { at: number; keys: Map<string, CryptoKey> } | null = null;

function b64urlToBytes(value: string): Uint8Array {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

async function jwks(teamDomain: string): Promise<Map<string, CryptoKey>> {
  if (cached && Date.now() - cached.at < JWKS_TTL_MS) return cached.keys;
  const response = await fetch(`https://${teamDomain}/cdn-cgi/access/certs`);
  if (!response.ok) throw new Error(`JWKS fetch failed: ${response.status}`);
  const body = (await response.json()) as { keys: Jwk[] };
  const keys = new Map<string, CryptoKey>();
  for (const jwk of body.keys ?? []) {
    if (jwk.kty !== "RSA") continue;
    keys.set(
      jwk.kid,
      await crypto.subtle.importKey(
        "jwk",
        { kty: "RSA", n: jwk.n, e: jwk.e, alg: "RS256", ext: true },
        { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
        false,
        ["verify"],
      ),
    );
  }
  cached = { at: Date.now(), keys };
  return keys;
}

export interface AccessIdentity {
  email: string;
}

/** The verified identity behind an Access assertion, or null. Never throws. */
export async function verifyAccess(
  token: string | undefined,
  env: { ACCESS_TEAM_DOMAIN?: string; ACCESS_AUD?: string; ALLOWED_EMAILS?: string },
): Promise<AccessIdentity | null> {
  const allowed = (env.ALLOWED_EMAILS ?? "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);

  // Absent configuration denies. This is the whole fail-closed contract: a
  // missing secret must lock the owner out, never let a stranger in.
  if (!token || !env.ACCESS_TEAM_DOMAIN || !env.ACCESS_AUD || allowed.length === 0) {
    return null;
  }

  const parts = token.split(".");
  if (parts.length !== 3) return null;
  const [rawHeader, rawPayload, rawSignature] = parts as [string, string, string];

  let header: { alg?: string; kid?: string };
  let payload: { aud?: string | string[]; iss?: string; exp?: number; email?: string };
  try {
    header = JSON.parse(new TextDecoder().decode(b64urlToBytes(rawHeader)));
    payload = JSON.parse(new TextDecoder().decode(b64urlToBytes(rawPayload)));
  } catch {
    return null;
  }

  // Pin the algorithm. Not load-bearing today — the signature below is always
  // verified as RSASSA-PKCS1-v1_5 against the JWKS key, whatever the header
  // says, so "alg: none" already fails there (checked by removing this line
  // and watching the test still pass). It is here so that a later refactor
  // which starts honouring `header.alg` cannot reintroduce algorithm
  // confusion. Do not delete it as dead code: it guards a future, not a bug.
  if (header.alg !== "RS256" || !header.kid) return null;

  let key: CryptoKey | undefined;
  try {
    key = (await jwks(env.ACCESS_TEAM_DOMAIN)).get(header.kid);
  } catch {
    return null;
  }
  if (!key) return null;

  const signed = new TextEncoder().encode(`${rawHeader}.${rawPayload}`);
  const ok = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    key,
    b64urlToBytes(rawSignature),
    signed,
  );
  if (!ok) return null;

  const audiences = Array.isArray(payload.aud) ? payload.aud : [payload.aud];
  if (!audiences.includes(env.ACCESS_AUD)) return null;
  if (payload.iss !== `https://${env.ACCESS_TEAM_DOMAIN}`) return null;
  if (!payload.exp || payload.exp * 1000 < Date.now()) return null;

  const email = (payload.email ?? "").toLowerCase();
  if (!email || !allowed.includes(email)) return null;

  return { email };
}

export function requireAccess(): MiddlewareHandler {
  return async (c, next) => {
    const identity = await verifyAccess(
      c.req.header("cf-access-jwt-assertion") ??
        getCookie(c.req.header("cookie"), "CF_Authorization"),
      c.env as never,
    );
    if (!identity) return c.text("Not authorised", 403);
    c.set("identity" as never, identity as never);
    await next();
  };
}

function getCookie(header: string | undefined, name: string): string | undefined {
  if (!header) return undefined;
  for (const part of header.split(";")) {
    const [k, ...rest] = part.trim().split("=");
    if (k === name) return rest.join("=");
  }
  return undefined;
}

/** Exported for tests: the JWKS cache is module state and has to be clearable. */
export function resetJwksCache(): void {
  cached = null;
}
