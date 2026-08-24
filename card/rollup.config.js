import resolve from "@rollup/plugin-node-resolve";
import typescript from "@rollup/plugin-typescript";
import commonjs from "@rollup/plugin-commonjs";
import terser from "@rollup/plugin-terser";
import { defineConfig } from "rollup";
import { readFileSync } from "node:fs";

// manifest.json is the single source of truth for the version; the preamble of
// a minified bundle is the only place left where it can still be read.
const version = JSON.parse(
  readFileSync(
    new URL("../custom_components/lognotifier/manifest.json", import.meta.url),
    "utf-8",
  ),
).version;

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
  },
  plugins: [
    resolve({ browser: true, preferBuiltins: false }),
    commonjs(),
    typescript({ tsconfig: "./tsconfig.json", declaration: false }),
    minify &&
      terser({
        format: {
          comments: false,
          preamble: `/*! log-notifier-card ${version} | MIT */`,
        },
      }),
  ].filter(Boolean),
  context: "window",
});
