#!/usr/bin/env node
// vendor-player.mjs — copies the asciinema-player standalone bundle into
// site/public/vendor/ so it ships as a same-origin static asset the page can
// dynamically import at runtime (CastPlayer.astro), instead of a bundler
// dependency. Runs on every `npm run build` (see package.json's "build"
// script) — site/public/vendor/ is gitignored, not committed.
//
// The vendored .min.js gets one addition beyond a plain copy: an
// `export default AsciinemaPlayer;` line appended at the end. The upstream
// bundle is a classic-script UMD (`var AsciinemaPlayer = (function(){...})()`)
// with no ES module exports; a dynamic `import()` of it as-is would run the
// code but leave `AsciinemaPlayer` trapped in that module's own scope (ES
// module top-level `var` never becomes a global, unlike a classic <script>).
// Appending the export statement — in the SAME file, so it can still see
// that module-scoped binding — turns the bundle into a real ESM default
// export without touching a byte of the (minified, license-headed) upstream
// code.
import { copyFileSync, mkdirSync, appendFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SITE_ROOT = path.resolve(HERE, '..');
const PKG_DIR = path.join(SITE_ROOT, 'node_modules/asciinema-player/dist/bundle');
const OUT_DIR = path.join(SITE_ROOT, 'public/vendor');

const JS_SRC = path.join(PKG_DIR, 'asciinema-player.min.js');
const CSS_SRC = path.join(PKG_DIR, 'asciinema-player.css');
const JS_OUT = path.join(OUT_DIR, 'asciinema-player.min.js');
const CSS_OUT = path.join(OUT_DIR, 'asciinema-player.css');

function main() {
  if (!existsSync(JS_SRC) || !existsSync(CSS_SRC)) {
    console.error(
      `vendor-player: asciinema-player bundle not found under ${PKG_DIR} — ` +
      'run `npm install` first (devDependency "asciinema-player").',
    );
    process.exit(1);
  }
  mkdirSync(OUT_DIR, { recursive: true });
  copyFileSync(JS_SRC, JS_OUT);
  copyFileSync(CSS_SRC, CSS_OUT);
  appendFileSync(JS_OUT, '\nexport default AsciinemaPlayer;\n');
  console.log(`vendor-player: wrote ${path.relative(SITE_ROOT, JS_OUT)} and ${path.relative(SITE_ROOT, CSS_OUT)}`);
}

main();
