// @ts-check
import { defineConfig } from 'astro/config';

import tailwindcss from '@tailwindcss/vite';
import pagefind from 'astro-pagefind';

// https://astro.build/config
export default defineConfig({
  // Primary (FR) production domain. The site serves FR at / and EN at /en/.
  // The EN domain (sanctioneddoctors.ca) redirects to /en/ at the DNS/registrar
  // level. For GitHub Pages *project* testing (no custom domain), also set
  // `base: '/<repo-name>'` and update `site` to the github.io URL.
  site: 'https://medecinssanctionnes.ca',
  integrations: [pagefind()],
  vite: {
    plugins: [tailwindcss()]
  }
});