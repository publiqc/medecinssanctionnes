// Data model for the site. Mirrors (a normalized view of) the collector's
// `disciplined.jsonl` records. The build step will map raw records to these.

export type SanctionType =
  | "radiation"
  | "revocation"
  | "suspension"
  | "limitation"
  | "commitment";

export interface Sanction {
  type: SanctionType;
  /** Short official label, e.g. "RADIATION (2026-05-15)". */
  label: string;
  /** ISO date the sanction took effect / was pronounced. */
  date: string;
  /** Whether this sanction is currently in force. */
  active: boolean;
  /** Human duration if known, e.g. "2 mois". */
  durationText?: string;
  /** Derived/known end date (ISO), if applicable. */
  endDate?: string;
  /** Whether endDate was derived (start + duration) rather than published. */
  endDerived?: boolean;
  /** Verbatim official notice text (reason), as published by the CMQ. */
  reason?: string;
}

export interface RulingLink {
  case: string;
  date?: string;
  url: string;
  source: "SOQUIJ" | "CanLII" | "CMQ";
}

/** A disciplinary decision document (from the fetched PDF, when available). */
export interface DecisionRef {
  case?: string;
  date?: string;
  result?: string;
  /** Official summary of the complaint grounds (the "cause"). */
  grounds?: string;
  /** Decision type, e.g. "Décision sur culpabilité et sanction". */
  precision?: string;
  /** Decision status caveat, e.g. "sanction non exécutoire". */
  precisionStatus?: string;
  documentId?: number;
  /** Whether the decision PDF text was retrieved. */
  hasText?: boolean;
  /** True when the decision carries a non-publication order (protects a patient). */
  publicationBan?: boolean;
  /** The tribunal's own (anonymized) statement of the charges. */
  charges?: string;
  /** Verbatim excerpt of the sanction(s) imposed (the dispositif). */
  disposition?: string;
  /** Coarse sanction kinds found in the disposition, e.g. ["radiation","fine"]. */
  dispositionKinds?: string[];
  /** External SOQUIJ / CanLII links, when present. */
  links?: string[];
}

export interface NoticeRef {
  /** Sanction type the published avis announces. */
  type: SanctionType;
  /** ISO date the CMQ published the avis. */
  date: string;
}

export type Lang = "fr" | "en";

export interface Doctor {
  slug: string;
  number: string;
  lastName: string;
  firstName: string;
  city?: string;
  specialty?: string;
  /** English specialty name (from the CMQ API in EN), when available. */
  specialtyEn?: string;
  memberSince?: number;
  /** Year the physician obtained their specialty certification, if any. */
  specialtyYear?: number;
  /** Raw CMQ status string, e.g. "Radié depuis le 2026-05-15". */
  statusText: string;
  sanctions: Sanction[];
  caseCount: number;
  rulingLinks: RulingLink[];
  /** True when the CMQ status marks the physician as deceased. */
  deceased?: boolean;
  /** Precomputed facet: the most serious sanction type on record. */
  primaryType?: SanctionType;
  /** Precomputed facet: headline status kind (mirrors statusOf). */
  statusKind?: StatusKind;
  /** True when a decision imposed a radiation the doctor has since served. */
  formerlyStruckOff?: boolean;
  /** Precomputed facet: distinct sanction years, newest first. */
  sanctionYears?: number[];
  /** Precomputed facet: specialty split into individual names. */
  specialties?: string[];
  /** Disciplinary decision documents (metadata + anonymized charges), when fetched. */
  decisions?: DecisionRef[];
  /** Public CMQ disciplinary avis (getNoticeListing) — authoritative status signal. */
  notices?: NoticeRef[];
  /** ISO timestamp of when this record was collected. */
  collectedAt?: string;
}

export type StatusKind = "radiated" | "restricted" | "past" | "record" | "clean";

export interface StatusInfo {
  kind: StatusKind;
  label: string;
  /** daisyUI semantic color (alert-… / badge-…). */
  tone: "error" | "warning" | "neutral" | "success";
}

const SANCTION_META: Record<
  SanctionType,
  { label: Record<Lang, string>; tone: StatusInfo["tone"] }
> = {
  radiation: { label: { fr: "Radiation", en: "Striking off" }, tone: "error" },
  revocation: { label: { fr: "Révocation de permis", en: "Licence revocation" }, tone: "error" },
  suspension: { label: { fr: "Suspension", en: "Suspension" }, tone: "warning" },
  limitation: { label: { fr: "Limitation d’exercice", en: "Practice restriction" }, tone: "warning" },
  commitment: { label: { fr: "Engagement", en: "Undertaking" }, tone: "neutral" },
};

export function sanctionLabel(type: SanctionType, lang: Lang = "fr"): string {
  return SANCTION_META[type].label[lang];
}

export function sanctionTone(type: SanctionType): StatusInfo["tone"] {
  return SANCTION_META[type].tone;
}

/** Localized specialty name for a doctor. */
export function specialtyOf(doctor: Doctor, lang: Lang = "fr"): string | undefined {
  if (lang === "en") return doctor.specialtyEn ?? doctor.specialty;
  return doctor.specialty;
}

const STATUS_LABELS = {
  radiatedRadiation: { fr: "Actuellement radié", en: "Currently struck off" },
  radiatedSuspension: { fr: "Actuellement suspendu", en: "Currently suspended" },
  restricted: { fr: "Droit d’exercice limité", en: "Restricted practice" },
  past: { fr: "Sanction déjà purgée", en: "Sanction already served" },
  record: { fr: "Antécédent disciplinaire", en: "Disciplinary record" },
  clean: { fr: "Aucune sanction active", en: "No active sanction" },
};

/** Derive the headline status for a doctor from their sanctions. */
export function statusOf(doctor: Doctor, lang: Lang = "fr"): StatusInfo {
  const active = doctor.sanctions.filter((s) => s.active);
  if (active.some((s) => s.type === "radiation" || s.type === "revocation")) {
    return { kind: "radiated", label: STATUS_LABELS.radiatedRadiation[lang], tone: "error" };
  }
  if (active.some((s) => s.type === "suspension")) {
    return { kind: "radiated", label: STATUS_LABELS.radiatedSuspension[lang], tone: "error" };
  }
  if (active.some((s) => s.type === "limitation" || s.type === "commitment")) {
    return { kind: "restricted", label: STATUS_LABELS.restricted[lang], tone: "warning" };
  }
  // A published CMQ avis is authoritative even when the registry hasn't caught up.
  const notices = doctor.notices ?? [];
  if (notices.some((n) => n.type === "radiation" || n.type === "revocation")) {
    return { kind: "radiated", label: STATUS_LABELS.radiatedRadiation[lang], tone: "error" };
  }
  if (notices.some((n) => n.type === "suspension")) {
    return { kind: "radiated", label: STATUS_LABELS.radiatedSuspension[lang], tone: "error" };
  }
  if (notices.some((n) => n.type === "limitation")) {
    return { kind: "restricted", label: STATUS_LABELS.restricted[lang], tone: "warning" };
  }
  if (doctor.sanctions.length > 0) {
    return { kind: "past", label: STATUS_LABELS.past[lang], tone: "neutral" };
  }
  if ((doctor.decisions?.length ?? 0) > 0 || doctor.caseCount > 0) {
    return { kind: "record", label: STATUS_LABELS.record[lang], tone: "neutral" };
  }
  return { kind: "clean", label: STATUS_LABELS.clean[lang], tone: "success" };
}

export function fullName(doctor: Doctor): string {
  return `${doctor.lastName}, ${doctor.firstName}`;
}

// CMQ disciplinary-file results, translated for the English site (verbatim in FR).
const RESULT_LABELS: Record<string, Record<Lang, string>> = {
  "plainte accueillie": { fr: "Plainte accueillie", en: "Complaint upheld" },
  "plainte rejetée": { fr: "Plainte rejetée", en: "Complaint dismissed" },
  "plainte retirée": { fr: "Plainte retirée", en: "Complaint withdrawn" },
  "requête accueillie": { fr: "Requête accueillie", en: "Motion granted" },
  "requête rejetée": { fr: "Requête rejetée", en: "Motion dismissed" },
};

/** Localized label for a disciplinary-file result; falls back to the verbatim text. */
export function resultLabel(result: string | undefined, lang: Lang = "fr"): string | undefined {
  if (!result) return undefined;
  const key = result.trim().toLowerCase();
  return RESULT_LABELS[key]?.[lang] ?? result.trim();
}

// Decision "precision" / "precisionStatus" phrases — a small enumerable set from
// the CMQ, translated for the English site (shown verbatim in FR).
const PHRASE_EN: Record<string, string> = {
  "décision sur culpabilité et sanction": "Decision on guilt and sanction",
  "décision rectifiée sur culpabilité et sanction": "Corrected decision on guilt and sanction",
  "décision sur culpabilité": "Decision on guilt",
  "décision rectifiée sur culpabilité": "Corrected decision on guilt",
  "décision sur sanction": "Decision on sanction",
  "décision sur requête": "Decision on motion",
  "décision sur requête en réinscription": "Decision on application for reinstatement",
  "décision sur requête en arrêt des procédures": "Decision on motion to stay proceedings",
  "décision sur requête en rejet de la plainte": "Decision on motion to dismiss the complaint",
  "décision sur reprise du plein droit de l'exercice": "Decision on resumption of full practice rights",
  "jugement du tribunal des professions": "Judgment of the Professions Tribunal",
  "jugement de la cour supérieure": "Superior Court judgment",
  "jugement de la cour d'appel": "Court of Appeal judgment",
  "désistement - cour supérieure": "Discontinuance – Superior Court",
  "sanction non exécutoire": "sanction not enforceable",
  "requête rejetée": "Motion dismissed",
  "requête accueillie": "Motion granted",
};

/** Localize a decision precision/precisionStatus phrase; verbatim FR fallback. */
export function localizePhrase(value: string | undefined, lang: Lang = "fr"): string | undefined {
  if (!value) return value;
  if (lang === "fr") return value;
  return PHRASE_EN[value.trim().toLowerCase()] ?? value.trim();
}

const MONTHS: Record<Lang, string[]> = {
  fr: [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
  ],
  en: [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ],
};

/** Format an ISO date as a readable date, e.g. "8 juillet 2026" / "8 July 2026". */
export function formatDate(iso: string, lang: Lang = "fr"): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  const [, y, mo, d] = m;
  const day = parseInt(d, 10);
  const dayLabel = lang === "fr" && day === 1 ? "1er" : String(day);
  return `${dayLabel} ${MONTHS[lang][parseInt(mo, 10) - 1]} ${y}`;
}

/** Most recent sanction (used for card summaries). */
export function primarySanction(doctor: Doctor): Sanction | undefined {
  return [...doctor.sanctions].sort((a, b) => b.date.localeCompare(a.date))[0];
}

/** Status-based filter buckets that partition the whole list (each doctor once). */
export type StatusFilter = "radie" | "limite" | "antecedent";

export function statusFilterOf(doctor: Doctor): StatusFilter {
  const kind = statusOf(doctor).kind;
  if (kind === "radiated") return "radie";
  if (kind === "restricted") return "limite";
  return "antecedent"; // record / past (served)
}

/** Representative date for sorting: latest sanction, else latest decision. */
export function sortDate(doctor: Doctor): string {
  const s = doctor.sanctions.map((x) => x.date).filter(Boolean).sort().at(-1);
  if (s) return s;
  const d = (doctor.decisions ?? []).map((x) => x.date).filter(Boolean).sort().at(-1);
  return d ?? "";
}

const DURATION_UNITS: Array<[RegExp, string, string]> = [
  [/jour/, "day", "days"],
  [/semaine/, "week", "weeks"],
  [/mois/, "month", "months"],
  [/(?:ans?|ann[ée]es?)/, "year", "years"],
];

/**
 * Localize a French duration string (as stored from the CMQ notice), e.g.
 * "2 mois" -> "2 months", "3 mois et demi" -> "3 and a half months".
 * Falls back to the original text if it can't be parsed.
 */
export function formatDuration(text: string | undefined, lang: Lang = "fr"): string | undefined {
  if (!text || lang === "fr") return text;
  const t = text.toLowerCase();
  const half = /\bet demie?\b/.test(t);
  const numMatch = t.match(/(\d+(?:[.,]\d+)?)/);
  const n = numMatch ? parseFloat(numMatch[1].replace(",", ".")) : NaN;
  const unit = DURATION_UNITS.find(([re]) => re.test(t));
  if (!unit || Number.isNaN(n)) return text;
  const [, singular, plural] = unit;
  if (half) return `${n} and a half ${plural}`;
  return `${n} ${n === 1 ? singular : plural}`;
}

const PERIOD: Record<Lang, { from: string; to: string; estimated: string; since: string }> = {
  fr: { from: "du", to: "au", estimated: "(fin estimée)", since: "depuis le" },
  en: { from: "from", to: "to", estimated: "(estimated end)", since: "since" },
};

/** Readable date range, e.g. "du 8 juillet 2026 au 8 septembre 2026 (fin estimée)". */
export function sanctionPeriodText(s: Sanction, lang: Lang = "fr"): string {
  const p = PERIOD[lang];
  if (s.endDate) {
    const base = `${p.from} ${formatDate(s.date, lang)} ${p.to} ${formatDate(s.endDate, lang)}`;
    return s.endDerived ? `${base} ${p.estimated}` : base;
  }
  return `${p.since} ${formatDate(s.date, lang)}`;
}

export interface CardDisplay {
  label: string;
  tone: StatusInfo["tone"];
  /** Count chip text when there is more than one sanction, e.g. "2 limitations". */
  countLabel: string;
  /** Representative date: oldest for limitations ("depuis le..."), most recent otherwise. */
  detail: string;
}

const CARD_PILL = {
  revoked: { fr: "Permis révoqué", en: "Licence revoked" },
  struck: { fr: "Radié", en: "Struck off" },
  suspended: { fr: "Suspendu", en: "Suspended" },
  restricted: { fr: "Exercice limité", en: "Restricted" },
};

const PAST_PILL: Record<string, { one: Record<Lang, string>; many: Record<Lang, string> }> = {
  radiation: {
    one: { fr: "Radiation purgée", en: "Striking off served" },
    many: { fr: "Radiations purgées", en: "Strikings off served" },
  },
  suspension: {
    one: { fr: "Suspension purgée", en: "Suspension served" },
    many: { fr: "Suspensions purgées", en: "Suspensions served" },
  },
  other: {
    one: { fr: "Sanction purgée", en: "Sanction served" },
    many: { fr: "Sanctions purgées", en: "Sanctions served" },
  },
};

const TYPE_NOUN_PLURAL: Record<Lang, Record<SanctionType, string>> = {
  fr: {
    radiation: "radiations", revocation: "révocations", suspension: "suspensions",
    limitation: "limitations", commitment: "engagements",
  },
  en: {
    radiation: "strikings off", revocation: "licence revocations", suspension: "suspensions",
    limitation: "restrictions", commitment: "undertakings",
  },
};

const SANCTIONS_WORD: Record<Lang, string> = { fr: "sanctions", en: "sanctions" };
const SINCE_WORD: Record<Lang, string> = { fr: "depuis le", en: "since" };

/**
 * Card status pill + a count chip (when several sanctions) + one representative
 * date. Limitations use the OLDEST date ("limité depuis..."); radiations and
 * served sanctions use the MOST RECENT. Full dated history lives on the detail
 * page. "Exercice limité" stays singular (one droit d'exercice).
 */
export function cardDisplay(doctor: Doctor, lang: Lang = "fr"): CardDisplay {
  const s = statusOf(doctor, lang);
  const active = doctor.sanctions.filter((x) => x.active);

  let label = s.label;
  let tone = s.tone;
  if (s.kind === "radiated") {
    tone = "error";
    if (active.some((x) => x.type === "revocation")) label = CARD_PILL.revoked[lang];
    else if (active.some((x) => x.type === "radiation")) label = CARD_PILL.struck[lang];
    else label = CARD_PILL.suspended[lang];
  } else if (s.kind === "restricted") {
    tone = "warning";
    label = CARD_PILL.restricted[lang];
  } else if (s.kind === "past") {
    tone = "neutral";
    const t = primarySanction(doctor)?.type;
    const sameType = doctor.sanctions.filter((x) => x.type === t).length;
    const group = t === "radiation" ? PAST_PILL.radiation : t === "suspension" ? PAST_PILL.suspension : PAST_PILL.other;
    label = (sameType > 1 ? group.many : group.one)[lang];
  } else if (s.kind === "record") {
    tone = "neutral";
    label = s.label;
  }

  // Representative date.
  let detail = "";
  if (s.kind === "restricted") {
    const limitations = active.filter((x) => x.type === "limitation" || x.type === "commitment");
    const earliest = [...limitations].sort((a, b) => a.date.localeCompare(b.date))[0];
    detail = earliest ? `${SINCE_WORD[lang]} ${formatDate(earliest.date, lang)}` : "";
  } else if (s.kind === "record") {
    const dates = (doctor.decisions ?? []).map((x) => x.date).filter(Boolean) as string[];
    const recent = [...dates].sort().at(-1);
    detail = recent ? formatDate(recent, lang) : "";
  } else {
    const recent = primarySanction(doctor);
    detail = recent ? sanctionPeriodText(recent, lang) : "";
  }

  // Count chip.
  const n = doctor.sanctions.length;
  let countLabel = "";
  if (n > 1) {
    const types = new Set(doctor.sanctions.map((x) => x.type));
    countLabel =
      types.size === 1
        ? `${n} ${TYPE_NOUN_PLURAL[lang][doctor.sanctions[0].type]}`
        : `${n} ${SANCTIONS_WORD[lang]}`;
  }

  return { label, tone, countLabel, detail };
}

export function toSlug(lastName: string, firstName: string, number: string): string {
  const base = `${lastName}-${firstName}`
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${base}-${number}`;
}
