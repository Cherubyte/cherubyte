/**
 * Runs inside workerd against real D1, per the house testing convention.
 *
 * Most of these pin a refusal or a property whose failure would be silent: a
 * public page that quietly became gated, an admin page that quietly did not.
 */
import { createExecutionContext, env } from "cloudflare:test";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import worker from "../src/index";
import { countSignups, listSignups, recordSignup } from "../src/db/queries";
import { resetJwksCache, verifyAccess } from "../src/middleware/access";
import { emailKey, signupSchema } from "../src/shared/schemas";

const ctx = createExecutionContext();

async function get(path: string, init?: RequestInit) {
  return worker.fetch(new Request(`https://cherubyte.test${path}`, init), env, ctx);
}

async function postForm(path: string, fields: Record<string, string>) {
  const body = new URLSearchParams(fields);
  return get(path, {
    method: "POST",
    body,
    headers: { "content-type": "application/x-www-form-urlencoded" },
  });
}

beforeEach(async () => {
  await env.DB.prepare("DELETE FROM signups").run();
});

describe("the public surface", () => {
  it("serves the landing page to anyone", async () => {
    const response = await get("/");
    expect(response.status).toBe(200);
    const html = await response.text();
    expect(html).toContain("See every device on your network");
  });

  it("says self-hosting is free, which is the whole positioning", async () => {
    expect(await (await get("/")).text()).toContain("Self-hosting is free");
  });

  it("answers a health check", async () => {
    expect(await (await get("/health")).json()).toEqual({ status: "ok" });
  });

  it("sends the download link somewhere real", async () => {
    const response = await get("/download/agent");
    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toContain("github.com");
  });
});

describe("signing up for a hosted panel", () => {
  it("records a signup from the form", async () => {
    const response = await postForm("/signup", {
      email: "Sam@Example.com",
      networks: "duas",
    });
    expect(response.status).toBe(200);
    expect(await response.text()).toContain("you are on the list");

    const rows = await listSignups(env.DB);
    expect(rows).toHaveLength(1);
    expect(rows[0]!.email).toBe("Sam@Example.com");
  });

  it("treats the same address in different case as one person", async () => {
    await postForm("/signup", { email: "a@b.com" });
    await postForm("/signup", { email: "A@B.COM" });
    expect(await countSignups(env.DB)).toBe(1);
  });

  it("answers a repeat signup exactly like a first one", async () => {
    // Otherwise the form becomes a way to check whether an address is on the list.
    const first = await postForm("/signup", { email: "a@b.com" });
    const second = await postForm("/signup", { email: "a@b.com" });
    expect(second.status).toBe(first.status);
    expect(await second.text()).toEqual(await first.text());
  });

  it("does not let a repeat signup erase the first note", async () => {
    await postForm("/signup", { email: "a@b.com", note: "tenho tres redes" });
    await postForm("/signup", { email: "a@b.com", note: "" });
    expect((await listSignups(env.DB))[0]!.note).toBe("tenho tres redes");
  });

  it("refuses something that is not an email", async () => {
    const response = await postForm("/signup", { email: "nao-e-email" });
    expect(response.status).toBe(400);
    expect(await countSignups(env.DB)).toBe(0);
  });

  it("accepts JSON as well as a form", async () => {
    const response = await get("/signup", {
      method: "POST",
      body: JSON.stringify({ email: "json@example.com" }),
      headers: { "content-type": "application/json" },
    });
    expect(response.status).toBe(200);
    expect(await countSignups(env.DB)).toBe(1);
  });

  it("stores what was written, letting the page escape it", async () => {
    await postForm("/signup", { email: "x@y.com", note: "<script>alert(1)</script>" });
    expect((await listSignups(env.DB))[0]!.note).toContain("<script>");
  });
});

describe("the admin area", () => {
  it("refuses with no assertion at all", async () => {
    expect((await get("/admin")).status).toBe(403);
    expect((await get("/admin/signups.json")).status).toBe(403);
  });

  it("refuses a forged assertion", async () => {
    const response = await get("/admin", {
      headers: { "cf-access-jwt-assertion": "nao.e.um.token" },
    });
    expect(response.status).toBe(403);
  });

  it("never leaks a signup to an unauthenticated caller", async () => {
    await postForm("/signup", { email: "privado@example.com" });
    expect(await (await get("/admin")).text()).not.toContain("privado@example.com");
  });
});

describe("Access verification fails closed", () => {
  const full = {
    ACCESS_TEAM_DOMAIN: "team.cloudflareaccess.com",
    ACCESS_AUD: "aud",
    ALLOWED_EMAILS: "eu@example.com",
  };

  it("denies when the allowlist is empty", async () => {
    // Forgetting to upload the secret must lock the owner out, not let
    // everyone in.
    expect(await verifyAccess("a.b.c", { ...full, ALLOWED_EMAILS: "" })).toBeNull();
  });

  it("denies when the audience is unset", async () => {
    expect(await verifyAccess("a.b.c", { ...full, ACCESS_AUD: "" })).toBeNull();
  });

  it("denies when the team domain is unset", async () => {
    expect(await verifyAccess("a.b.c", { ...full, ACCESS_TEAM_DOMAIN: "" })).toBeNull();
  });

  it("denies a token with no signature", async () => {
    expect(await verifyAccess("", full)).toBeNull();
    expect(await verifyAccess("only.two", full)).toBeNull();
  });
});

/**
 * The verifier against a real key.
 *
 * The absent-configuration tests above pass whether or not the signature is
 * ever checked — a JWKS fetch that fails returns null too, so they cannot tell
 * a working verifier from a broken one. These sign real tokens with a real RSA
 * key and serve a real JWKS, so each refusal is attributable.
 */
describe("Access verification against a real key", () => {
  const TEAM = "team.cloudflareaccess.com";
  const base = { ACCESS_TEAM_DOMAIN: TEAM, ACCESS_AUD: "aud", ALLOWED_EMAILS: "eu@example.com" };
  const b64 = (bytes: ArrayBuffer | Uint8Array) => {
    const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    let s = "";
    for (const byte of view) s += String.fromCharCode(byte);
    return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  };
  const b64json = (o: unknown) => b64(new TextEncoder().encode(JSON.stringify(o)));

  let keys: CryptoKeyPair;
  const KID = "test-key";
  let realFetch: typeof globalThis.fetch;

  beforeEach(async () => {
    resetJwksCache();
    keys = (await crypto.subtle.generateKey(
      { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
      true,
      ["sign", "verify"],
    )) as CryptoKeyPair;
    const jwk = await crypto.subtle.exportKey("jwk", keys.publicKey);
    realFetch = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      if (String(input).includes("/cdn-cgi/access/certs")) {
        return Response.json({ keys: [{ ...jwk, kid: KID, kty: "RSA", alg: "RS256" }] });
      }
      return realFetch(input as RequestInfo);
    }) as typeof globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = realFetch;
    resetJwksCache();
  });

  async function sign(payload: Record<string, unknown>, header: Record<string, unknown> = {}) {
    const head = b64json({ alg: "RS256", kid: KID, ...header });
    const body = b64json(payload);
    const signature = await crypto.subtle.sign(
      "RSASSA-PKCS1-v1_5",
      keys.privateKey,
      new TextEncoder().encode(`${head}.${body}`),
    );
    return `${head}.${body}.${b64(signature)}`;
  }

  const goodPayload = () => ({
    aud: "aud",
    iss: `https://${TEAM}`,
    exp: Math.floor(Date.now() / 1000) + 600,
    email: "eu@example.com",
  });

  it("admits a properly signed assertion", async () => {
    expect(await verifyAccess(await sign(goodPayload()), base)).toEqual({
      email: "eu@example.com",
    });
  });

  it("refuses a token signed by a different key", async () => {
    const other = (await crypto.subtle.generateKey(
      { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
      true,
      ["sign", "verify"],
    )) as CryptoKeyPair;
    const head = b64json({ alg: "RS256", kid: KID });
    const body = b64json(goodPayload());
    const sig = await crypto.subtle.sign(
      "RSASSA-PKCS1-v1_5",
      other.privateKey,
      new TextEncoder().encode(`${head}.${body}`),
    );
    expect(await verifyAccess(`${head}.${body}.${b64(sig)}`, base)).toBeNull();
  });

  it("refuses an unsigned token that names an allowed email", async () => {
    // "alg: none" is the classic forgery. Note what actually stops it here:
    // the signature check, which always runs RSASSA-PKCS1-v1_5 against the
    // JWKS key whatever the header claims. Removing the algorithm pin does not
    // make this test fail — verified by removing it. The pin is there so that
    // a later refactor which starts honouring `header.alg` cannot reintroduce
    // algorithm confusion; this test pins the outcome, not the mechanism.
    const token = `${b64json({ alg: "none", kid: KID })}.${b64json(goodPayload())}.`;
    expect(await verifyAccess(token, base)).toBeNull();
  });

  it("refuses an assertion for another application", async () => {
    expect(await verifyAccess(await sign({ ...goodPayload(), aud: "outra" }), base)).toBeNull();
  });

  it("refuses an assertion from another team", async () => {
    const token = await sign({ ...goodPayload(), iss: "https://mau.cloudflareaccess.com" });
    expect(await verifyAccess(token, base)).toBeNull();
  });

  it("refuses an expired assertion", async () => {
    const token = await sign({ ...goodPayload(), exp: Math.floor(Date.now() / 1000) - 10 });
    expect(await verifyAccess(token, base)).toBeNull();
  });

  it("refuses a valid assertion for someone not on the allowlist", async () => {
    const token = await sign({ ...goodPayload(), email: "estranho@example.com" });
    expect(await verifyAccess(token, base)).toBeNull();
  });

  it("lets a signed-in allowed reader see the admin page", async () => {
    const token = await sign(goodPayload());
    const response = await worker.fetch(
      new Request("https://cherubyte.test/admin", {
        headers: { "cf-access-jwt-assertion": token },
      }),
      { ...env, ...base } as never,
      createExecutionContext(),
    );
    expect(response.status).toBe(200);
    expect(await response.text()).toContain("signups");
  });
});

describe("the shared schema", () => {
  it("is the one definition both surfaces validate with", () => {
    expect(signupSchema.safeParse({ email: "a@b.com" }).success).toBe(true);
    expect(signupSchema.safeParse({ email: "nope" }).success).toBe(false);
    expect(signupSchema.safeParse({ email: `${"a".repeat(250)}@b.com` }).success).toBe(false);
  });

  it("keys an address the same way the database does", () => {
    expect(emailKey("  A@B.com ")).toBe("a@b.com");
  });
});

describe("the query layer", () => {
  it("reports whether a signup was new", async () => {
    const first = await recordSignup(env.DB, { email: "a@b.com" });
    const second = await recordSignup(env.DB, { email: "a@b.com" });
    expect(first.created).toBe(true);
    expect(second.created).toBe(false);
  });
});
