import type { Lang } from "./types";

/**
 * Site-wide configuration and external links.
 *
 * The GitHub links are intentionally `null` for now: the transparency /
 * feedback sections only render once a public repository exists. Set these
 * when the repo goes public (ideally under a dedicated org / role account).
 */
export const siteConfig = {
  /** Private channel for corrections about a specific listing (per language). */
  contactEmail: {
    fr: "contact@medecinssanctionnes.ca",
    en: "contact@sanctioneddoctors.ca",
  } as Record<Lang, string>,
  /** Public repository URL (code + data). Null = transparency links hidden. */
  githubUrl: "https://github.com/publiqc/medecinssanctionnes" as string | null,
  /** GitHub issues URL for general feedback / bug reports. */
  githubIssuesUrl: "https://github.com/publiqc/medecinssanctionnes/issues" as string | null,
  /** Max number of doctors shown in the homepage "recent" list. */
  recentLimit: 24,
  /** Doctors per page on the browsable listing. */
  listPageSize: 24,
  /**
   * Keep the site out of search engines during the preview / feedback phase.
   * Adds a `noindex` robots meta tag on every page. Set to `false` at the real
   * public launch (then submit the sitemap in Google Search Console).
   */
  previewNoindex: true,
};

export type SiteConfig = typeof siteConfig;
export type { Lang };
