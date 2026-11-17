import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://markfishurupa-dot.github.io',
  base: '/streetview-v2',
  integrations: [starlight({
    title: 'StreetView 2.0',
    customCss: ['./src/styles/custom.css'],
    sidebar: [
      { label: 'Getting started', items: [{ autogenerate: { directory: 'start' } }] },
      { label: 'Using StreetView', items: [{ autogenerate: { directory: 'guide' } }] },
      { label: 'Reference', items: [{ autogenerate: { directory: 'reference' } }] },
    ],
  })],
});
