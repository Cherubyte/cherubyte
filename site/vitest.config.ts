import {
  defineWorkersConfig,
  readD1Migrations,
} from "@cloudflare/vitest-pool-workers/config";

// Tests run inside workerd against real D1, per the house testing convention:
// query and crypto code is exercised on the runtime it ships to rather than a
// Node approximation of it. The schema comes from the same migration files
// wrangler applies in production — a test schema kept by hand would drift, and
// would drift silently.
const migrations = await readD1Migrations("./migrations");

export default defineWorkersConfig({
  test: {
    setupFiles: ["./test/apply-migrations.ts"],
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.jsonc" },
        miniflare: {
          bindings: { TEST_MIGRATIONS: migrations },
        },
      },
    },
  },
});
