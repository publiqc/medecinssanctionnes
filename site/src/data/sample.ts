import type { Doctor } from "../lib/types";
import { toSlug } from "../lib/types";
import raw from "./doctors.json";

// Generated from the collector's disciplined.jsonl by collector/normalize.py.
// The full set of real disciplinary records. Slugs are derived here so the JSON
// stays free of computed fields.

export const doctors: Doctor[] = (raw as unknown as Omit<Doctor, "slug">[]).map(
  (d) => ({
    ...d,
    slug: toSlug(d.lastName, d.firstName, d.number),
  }),
);
