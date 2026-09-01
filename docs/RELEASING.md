# Releasing

A release exists to do one thing: publish `:latest` and the semver image tags to
GHCR, so the `docker run` / `docker compose` lines in the README work without a
local build.

For a build to test *before* a release, run the `Images` workflow by hand
(`gh workflow run Images` or the Actions tab) — it publishes the same two images
tagged `:edge` and `:sha-<commit>`.

## Cutting one

1. **Pick the version.** `frontend/package.json`'s `version` is the single source
   of truth for the app (`__APP_VERSION__` reads it). Bump it in its own commit
   or as part of the last feature PR — patch / minor / major by judgement.

2. **Tag it `vX.Y.Z`**, matching that version exactly. `docker/metadata-action`
   turns `v0.5.0` into the image tags `0.5.0`, `0.5`, and `latest`.

   ```bash
   git checkout main && git pull
   gh release create v0.5.0 --generate-notes --title v0.5.0
   ```

   `--generate-notes` drafts the changelog from merged PRs; edit before
   publishing if you want.

3. **Watch the build.** Publishing the release triggers `Image`, which builds
   `cherubyte-panel` for `linux/amd64` + `linux/arm64` (QEMU, ~20 min) and pushes
   it. (The agent releases from its own repo,
   [Cherubyte/cherubyte-agent](https://github.com/Cherubyte/cherubyte-agent).)

   ```bash
   gh run watch
   ```

4. **Check the tags landed.**

   ```bash
   docker manifest inspect ghcr.io/cherubyte/cherubyte-panel:0.5.0 | grep architecture
   ```

## First release

The GHCR package is created by the first successful push. It is private by
default — make `cherubyte-panel` public once (GitHub → your profile → Packages →
`cherubyte-panel` → Package settings → Change visibility), or `docker compose
up` fails with `denied` for anyone not logged in.

## What can go wrong

- **`arm64` build fails but `amd64` passed.** `fail-fast: false` means one arch
  or one image failing does not stop the rest, so a release can publish half its
  tags. Re-run the job after fixing; `docker/build-push-action` is idempotent.
- **Tag doesn't match `package.json`.** Nothing enforces it. The image tag comes
  from the git tag, the in-app version string from `package.json` — a mismatch
  ships an image whose UI reports a different version.
