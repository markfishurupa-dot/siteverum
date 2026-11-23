import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://markfishurupa-dot.github.io',
  base: '/siteverum',
  integrations: [starlight({
    title: 'SiteVerum 2.0',
    customCss: ['./src/styles/custom.css'],
    sidebar: [
      { label: 'Getting started', items: [{ autogenerate: { directory: 'start' } }] },
      { label: 'Using SiteVerum', items: [{ autogenerate: { directory: 'guide' } }] },
      { label: 'Reference', items: [{ autogenerate: { directory: 'reference' } }] },
    ],
  })],
});
