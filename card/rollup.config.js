import resolve from "@rollup/plugin-node-resolve";
import typescript from "@rollup/plugin-typescript";
import commonjs from "@rollup/plugin-commonjs";
import terser from "@rollup/plugin-terser";
import { defineConfig } from "rollup";
import { readFileSync } from "node:fs";

import { nextBuild } from "./scripts/build-number.mjs";

// manifest.json is the single source of truth for the version. The card reads
// it from here through output.intro rather than from a constant in the source
// — that constant is how CARD_VERSION sat at "1.0.0" four releases on.
// Declared for TypeScript in src/build-globals.d.ts.
const version = JSON.parse(
  readFileSync(
    new URL("../custom_components/lognotifier/manifest.json", import.meta.url),
    "utf-8",
  ),
).version;

// Only `builddeploy.sh` asks for a build counter (LOGNOTIFIER_BUILD_COUNTER);
// every other build, the GitHub release included, reports the bare semver.
// Bumped once per rollup run — a `watch` session keeps the number it started
// with, exactly like the build it stands in for.
const { build, builtAt, full } = nextBuild(version);
console.log(`log-notifier-card ${full} (${builtAt})`);

// Only the release workflow sets LOGNOTIFIER_MINIFY; local builds and `watch`
// keep the readable bundle, so what is debugged in the browser is what is in
// src/. The same flag decides the source map: it is what makes a minified
// bundle debuggable, so it belongs to every local build and to none of the
// released ones, where it would only travel along unread in the zip of every
// HACS install.
const minify = process.env.LOGNOTIFIER_MINIFY === "1";

// The target is the integration's www directory directly: the integration
// serves the card itself, so no Lovelace resource has to be maintained by
// hand.
export default defineConfig({
  input: "src/log-notifier-card.ts",
  output: {
    file: "../custom_components/lognotifier/www/log-notifier-card.js",
    format: "es",
    sourcemap: !minify,
    intro: [
      `const CARD_VERSION = ${JSON.stringify(full)};`,
      `const CARD_SEMVER = ${JSON.stringify(version)};`,
      `const CARD_BUILD = ${JSON.stringify(build)};`,
      `const CARD_BUILD_TIME = ${JSON.stringify(builtAt)};`,
    ].join("\n"),
  },
  plugins: [
    resolve({ browser: true, preferBuiltins: false }),
    commonjs(),
    typescript({ tsconfig: "./tsconfig.json", declaration: false }),
    minify &&
      terser({
        format: {
          comments: false,
          preamble: `/*! log-notifier-card ${full} | MIT */`,
        },
      }),
  ].filter(Boolean),
  context: "window",
});
