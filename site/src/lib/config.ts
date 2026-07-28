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
  githubUrl: null as string | null,
  /** GitHub issues URL for general feedback / bug reports. */
  githubIssuesUrl: null as string | null,
  /** Max number of doctors shown in the homepage "recent" list. */
  recentLimit: 24,
  /** Doctors per page on the browsable listing. */
  listPageSize: 24,
};

export type SiteConfig = typeof siteConfig;
export type { Lang };
