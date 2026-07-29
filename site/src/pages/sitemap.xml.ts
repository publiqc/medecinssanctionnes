import type { APIRoute } from "astro";
import { doctors } from "../data/sample";

// Absolute base for canonical URLs. Matches astro.config `site`.
const SITE = "https://medecinssanctionnes.ca";

// Top-level pages (both languages). Doctor detail pages are added below.
const STATIC_PATHS = [
  "/",
  "/en/",
  "/contact/",
  "/en/contact/",
  "/a-propos/",
  "/en/about/",
];

export const GET: APIRoute = () => {
  const paths = [...STATIC_PATHS];
  for (const d of doctors) {
    paths.push(`/medecin/${d.slug}/`);
    paths.push(`/en/doctor/${d.slug}/`);
  }
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${paths.map((p) => `  <url><loc>${SITE}${p}</loc></url>`).join("\n")}
</urlset>
`;
  return new Response(xml, {
    headers: { "Content-Type": "application/xml; charset=utf-8" },
  });
};
