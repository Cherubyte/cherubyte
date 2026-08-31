# Cherubyte service site

The public face of Cherubyte: what it is, how to install it, where to download the
agent, and a signup list for people who would rather we ran their panel.

One Cloudflare Worker, per the house convention. D1 holds the signups. Static
content is rendered from the Worker rather than built into an assets bundle —
it is a single document with no client bundle, so a build step would be a moving
part that buys nothing.

## What is public and what is not

**Public**, deliberately: the landing page, the install instructions, the
download redirect and the signup form. Self-hosting is free and needs no
account, so gating any of that would be gating the product.

**Behind Cloudflare Access**: `/admin` and `/admin/signups.json`, the only place
signups can be read.

When creating the Access application, add **`admin*`** as the destination and
nothing else.

> Do not add a Workers-scoped destination. One scoped to the Worker covers every
> route it serves — including the landing page — and it does not appear in the
> Destinations preview panel, so it would gate the public site silently.

## First deploy

```sh
npx wrangler d1 create cherubyte-site        # put the id in wrangler.jsonc
npx wrangler secret put ACCESS_AUD         # the Access application's AUD tag
npx wrangler secret put ALLOWED_EMAILS     # comma separated
# ACCESS_TEAM_DOMAIN is a plain var in wrangler.jsonc
npm run deploy                             # typecheck, test, migrate, deploy
```

`workers_dev` is `false`. A `*.workers.dev` hostname would be a second front
door onto the same Worker and the same signup table, with no Access application
bound to it.

## Tests

```sh
npm test        # vitest inside workerd, against real D1
```

The schema comes from the same migration files wrangler applies in production, so
a test schema cannot drift from the real one.

The Access tests sign real tokens with a real RSA key and serve a real JWKS,
rather than only checking the absent-configuration paths — those pass whether or
not a signature is ever verified, so on their own they cannot tell a working
verifier from a broken one. Each refusal was confirmed by removing the check it
depends on and watching the right test fail.
