import { defineConfig } from 'astro/config';
export default defineConfig({
  site: 'https://vibe.andeye.com',
  // single page, one stylesheet: inline it so the page arrives styled in one
  // round-trip (and so the self-contained preview render sees the CSS at all)
  build: { inlineStylesheets: 'always' },
});
