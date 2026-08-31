/**
 * The Cherubyte service site.
 *
 * Public by design: self-hosting is free and needs no account, so the landing
 * page, the install instructions and the download links must be reachable by
 * anyone. Only the signup list is gated, and it is gated by Cloudflare Access
 * plus in-Worker verification — not by the mere presence of a header.
 *
 * Access destinations for this Worker: `admin*` only. Adding a Workers-scoped
 * destination would cover every route it serves, including the landing page,
 * and it does not appear in the Destinations preview panel — so it would gate
 * the public site silently.
 */
import { Hono } from "hono";

import { countSignups, listSignups, recordSignup } from "./db/queries";
import { requireAccess } from "./middleware/access";
import { adminPage, landingPage } from "./render";
import { signupSchema } from "./shared/schemas";

export interface Env {
  DB: D1Database;
  ACCESS_TEAM_DOMAIN?: string;
  ACCESS_AUD?: string;
  ALLOWED_EMAILS?: string;
  AGENT_RELEASES_URL?: string;
}

const app = new Hono<{ Bindings: Env }>();

const releases = (env: Env) =>
  env.AGENT_RELEASES_URL ?? "https://github.com/Cherubyte/cherubyte/releases/latest";

app.get("/", (c) => c.html(landingPage({ releasesUrl: releases(c.env) })));

app.get("/health", (c) => c.json({ status: "ok" }));

/** Where a Windows install sends someone. One hop, so the link in the panel and
 *  in the docs never has to change when the release layout does. */
app.get("/download/agent", (c) => c.redirect(releases(c.env), 302));

app.post("/signup", async (c) => {
  const contentType = c.req.header("content-type") ?? "";
  const raw = contentType.includes("application/json")
    ? await c.req.json().catch(() => ({}))
    : Object.fromEntries(await c.req.formData());

  const parsed = signupSchema.safeParse(raw);
  if (!parsed.success) {
    const message = "That email did not look right — try again?";
    return contentType.includes("application/json")
      ? c.json({ ok: false, error: message }, 400)
      : c.html(landingPage({ releasesUrl: releases(c.env), error: message }), 400);
  }

  const { created } = await recordSignup(c.env.DB, parsed.data);
  // The same answer either way: telling a stranger whether an address is
  // already on the list turns the form into an address checker.
  const message = "Thanks — you are on the list.";
  return contentType.includes("application/json")
    ? c.json({ ok: true, created })
    : c.html(landingPage({ releasesUrl: releases(c.env), message }));
});

app.get("/admin", requireAccess(), async (c) =>
  c.html(adminPage(await listSignups(c.env.DB))),
);

app.get("/admin/signups.json", requireAccess(), async (c) =>
  c.json({ total: await countSignups(c.env.DB), signups: await listSignups(c.env.DB) }),
);

app.notFound((c) => c.redirect("/", 302));

export default app;
