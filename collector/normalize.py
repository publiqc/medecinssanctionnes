"""Normalize collector output (disciplined.jsonl) into site-ready doctor records.

Produces JSON matching the site's `Omit<Doctor, "slug">` shape (src/lib/types.ts).
The site's sample.ts adds the slug via toSlug().

Scope (per product decision): include every doctor with a GENUINE disciplinary
finding. This first pass emits the "rich" records — those with an active/registry
sanction in detail.* (strikingOffTheRoll / suspensions / revocations /
restrictions / commitments), which carry the verbatim official notice. Thin,
narrative-less past cases (upheld complaint, no registry sanction) are handled in
a later pass once decision PDFs are fetched.

Accuracy rules:
- Start date = the sanction item's own effective date (authoritative).
- Reason = verbatim noticeDescription (only <br /> unwrapped; no rewriting).
- `active` derived from the CMQ status string, not inferred from prose.
- Duration/end date only when the notice states it unambiguously; marked derived.

Usage:
  python normalize.py            # write curated sample -> site/src/data/sample.json
  python normalize.py --full     # also write ALL rich records -> site/src/data/doctors.json (gitignored)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "disciplined.jsonl"
SITE_DATA = ROOT / "site" / "src" / "data"
DECISIONS_DIR = ROOT / "data" / "decisions"

# French -> English specialty names (built by fetch_specialties.py from the CMQ API).
_SPEC_PATH = Path(__file__).resolve().parent / "specialties_fr_en.json"
SPECIALTY_MAP: dict[str, str] = (
    json.loads(_SPEC_PATH.read_text(encoding="utf-8")) if _SPEC_PATH.exists() else {}
)

# Public disciplinary avis (getNoticeListing), keyed by permit number. The CMQ
# publishes these the moment a sanction takes effect — often before the
# physician-details API reflects it — so they're an authoritative inclusion and
# status signal. Built by fetch_notices.py.
_NOTICES_PATH = ROOT / "data" / "notices_ledger.jsonl"
# avis category label -> sanction type / headline status kind.
NOTICE_TYPE = {"radiation": "radiation", "suspension": "suspension",
               "revocation": "revocation", "limitation": "limitation"}
NOTICE_KIND = {"radiation": "radiated", "suspension": "radiated",
               "revocation": "radiated", "limitation": "restricted"}


def _load_notices() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    if _NOTICES_PATH.exists():
        for line in _NOTICES_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            num = str(rec.get("number") or "").strip()
            if num:
                out.setdefault(num, []).append(rec)
    return out


NOTICES_BY_NUMBER = _load_notices()

TODAY = date.today()

FIELD_TO_TYPE = {
    "strikingOffTheRoll": "radiation",
    "revocations": "revocation",
    "suspensions": "suspension",
    "restrictions": "limitation",
    "commitments": "commitment",
}

# Priority for choosing a doctor's "headline" sanction and sample coverage.
TYPE_RANK = {"revocation": 0, "radiation": 1, "suspension": 2, "limitation": 3, "commitment": 4}

NUM_WORDS = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6,
    "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12,
    "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16, "dix-sept": 17,
    "dix-huit": 18, "dix-neuf": 19, "vingt": 20, "vingt-quatre": 24,
    "trente": 30, "trente-six": 36, "quarante-huit": 48,
}

BR = re.compile(r"<br\s*/?>", re.IGNORECASE)

# Standard administrative footer appended to many notices; not substantive.
BOILERPLATE_RE = re.compile(r"Pour obtenir des renseignements additionnels", re.IGNORECASE)
PHONE_RE = re.compile(r"^\d{3}-\d{3}-\d{4}\.?$")


def clean_notice(text: str) -> str:
    """Unwrap the CMQ notice HTML into plain text with real line breaks.

    Drops the standard 'Pour obtenir des renseignements additionnels...' footer
    (and its bare phone-number line), which is administrative boilerplate rather
    than part of the substantive notice.
    """
    if not text:
        return ""
    text = BR.sub("\n", text)
    text = text.replace("\r", "")
    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if not BOILERPLATE_RE.search(ln) and not PHONE_RE.match(ln)]
    # Collapse runs of blank lines / trailing spaces, keep paragraph breaks.
    out: list[str] = []
    blank = False
    for ln in lines:
        if ln:
            out.append(ln)
            blank = False
        elif not blank:
            out.append("")
            blank = True
    return "\n".join(out).strip()


def clean_city(raw: str | None) -> str | None:
    """Reduce an address tail like 'Saint-Laurent QC H4T 1Z9' to 'Saint-Laurent'."""
    if not raw:
        return None
    city = raw.strip()
    # Strip trailing Canadian postal code, then a trailing province code.
    city = re.sub(r"\s+[A-Za-z]\d[A-Za-z]\s*\d[A-Za-z]\d$", "", city)
    city = re.sub(r"\s+(QC|Qc|ON|NB|NS|AB|BC|MB|SK|PE|NL|NT|YT|NU)$", "", city)
    return city.strip() or None


def iso(d: str | None) -> str | None:
    if not d:
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", d)
    return m.group(1) if m else None


def strip_status(status: str | None) -> str:
    if not status:
        return ""
    return re.sub(r"\s+", " ", BR.sub(" ", status)).strip()


def is_deceased(status: str | None) -> bool:
    return "décédé" in (status or "").lower()


def parse_specialty_year(hist: dict | None) -> int | None:
    if not hist:
        return None
    raw = hist.get("specialtyYear")
    if not raw:
        return None
    years = [int(y) for y in re.findall(r"\((\d{4})\)", str(raw))]
    return max(years) if years else None


def add_months(start: date, months: int) -> date:
    m = start.month - 1 + months
    y = start.year + m // 12
    mo = m % 12 + 1
    # Clamp day to end of target month.
    import calendar
    d = min(start.day, calendar.monthrange(y, mo)[1])
    return date(y, mo, d)


DURATION_RE = re.compile(
    r"(?:d['’]une\s+p[ée]riode\s+de|pour\s+une\s+p[ée]riode\s+de|totalisant|"
    r"pour\s+une\s+dur[ée]e\s+de|d['’]une\s+dur[ée]e\s+de|radiation\s+de)\s+"
    r"([\w-]+)\s*(et\s+demie?)?\s*(mois|ans?|ann[ée]es?|semaines?|jours?)",
    re.IGNORECASE,
)
PERMANENT_RE = re.compile(
    r"permanente?|d[ée]finitive?|de\s+fa[çc]on\s+permanente|permanent", re.IGNORECASE)


def parse_duration(desc: str, sanction_type: str) -> tuple[str | None, int | None, str | None]:
    """Return (durationText, months_equiv, unit) if unambiguously stated, else Nones.

    Only fires on clear patterns to avoid fabricating end dates. `months_equiv`
    is a day/month count usable for a derived end date; unit disambiguates.
    """
    m = DURATION_RE.search(desc)
    if not m:
        return None, None, None
    word = m.group(1).lower().strip()
    half = bool(m.group(2))
    unit = m.group(3).lower()

    if word.isdigit():
        n = int(word)
    else:
        n = NUM_WORDS.get(word)
    if n is None:
        return None, None, None

    # French unit noun for durationText (site's formatDuration understands these).
    if unit.startswith("mois"):
        unit_fr = "mois"
    elif unit.startswith("an") or unit.startswith("ann"):
        unit_fr = "an" if n == 1 else "ans"
    elif unit.startswith("semaine"):
        unit_fr = "semaine" if n == 1 else "semaines"
    else:
        unit_fr = "jour" if n == 1 else "jours"

    text = f"{n} {unit_fr}"
    if half:
        text += " et demi"
    return text, n, unit_fr


def derived_end(start: date, n: int, unit_fr: str, half: bool) -> date | None:
    if unit_fr == "mois":
        end = add_months(start, n)
        if half:
            end = end + timedelta(days=15)
        return end
    if unit_fr in ("an", "ans"):
        end = add_months(start, n * 12)
        if half:
            end = add_months(end, 6)
        return end
    if unit_fr in ("semaine", "semaines"):
        return start + timedelta(days=n * 7 + (4 if half else 0))
    if unit_fr in ("jour", "jours"):
        return start + timedelta(days=n)
    return None


def sanction_active(field: str, status: str, deceased: bool) -> bool:
    """Whether a sanction is currently in force, per the CMQ status string."""
    if deceased:
        return False
    s = status.lower()
    if "non-paiement" in s or "démission" in s or "demission" in s:
        # Current standing is an administrative removal, not this discipline.
        return field == "revocations"  # a revoked permit is permanent
    if field == "strikingOffTheRoll":
        return "radié" in s
    if field == "revocations":
        return "radié" in s or "révoqu" in s or "revoqu" in s
    if field == "restrictions":
        return "limité" in s
    if field == "suspensions":
        return "suspend" in s
    if field == "commitments":
        # A live undertaking (limited practice / future cessation).
        return "limité" in s or "actif" in s
    return False


# --- Decision PDF text (Stage 2) --------------------------------------------

# A non-publication order (usually protecting a patient's identity) means we must
# not republish the full decision. We still surface the tribunal's own anonymized
# charges, but we flag the ban so the site can add a notice and never dump text.
BAN_RE = re.compile(
    r"non-?publication|non-?divulgation|non-?diffusion|ordonnance\s+de\s+non", re.IGNORECASE)

# The tribunal states the charges verbatim (already anonymized) after introducing
# "la plainte". Anchor to "plainte" so we don't latch onto quoted articles of law
# (which are also introduced by "se lit comme suit :"). Tolerate a footnote digit
# before the colon ("ainsi libellée3 :").
CHARGE_INTRO_RE = re.compile(
    r"plainte[^.\n]{0,180}?(?:ainsi\s+libell[ée]e?|libell[ée]e?\s+ainsi|"
    r"se\s+lit\s+comme\s+suit|reproch[eé]e?\s+ce\s+qui\s+suit)\s*\d{0,2}\s*:",
    re.IGNORECASE)

# Narrative form used by many decisions: "le plaignant reproche à/au Dr X … d'avoir …".
NARRATIVE_INTRO_RE = re.compile(
    r"reproch[eé]\s+(?:à|au|aux)\b[^.\n]{0,140}?d['’]avoir\b", re.IGNORECASE)
CHARGE_STOP_RE = re.compile(
    r"\[Transcription textuelle\]|\n\s*\[\d+\]|\b(PLAIDOYER|CONTEXTE|LES FAITS|"
    r"ANALYSE|REPR[ÉE]SENTATIONS|DISPOSITIF|MOTIFS)\b")

# PDF page furniture that pypdf interleaves into the text.
FURNITURE_RE = re.compile(r"^(?:\d{1,4}|PAGE\s+\d+|\d{2}-\d{4}-\d{5}(?:\s+PAGE\s+\d+)?)$",
                          re.IGNORECASE)


def load_decision_text(doc_id: int) -> str | None:
    path = DECISIONS_DIR / f"{doc_id}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    return None


def clean_decision_text(text: str) -> str:
    """Drop page numbers / running headers that pypdf splices into the body."""
    out = []
    for ln in text.split("\n"):
        s = ln.strip()
        if not s:
            out.append("")
            continue
        if FURNITURE_RE.match(s) or re.match(r"^\d{2}-\d{4}-\d{5}\b", s):
            continue
        out.append(s)
    return "\n".join(out)


def has_publication_ban(text: str) -> bool:
    # These orders are stated up front; only look near the top.
    return bool(BAN_RE.search(text[:2500]))


def _tidy(s: str) -> str:
    # Rejoin words split across a line break ("réalisa-\ntion" -> "réalisation"),
    # keeping same-line compounds like "Saint-Jean" intact.
    s = re.sub(r"(\w)-\s*\n\s*([a-zà-ÿ])", r"\1\2", s)
    s = re.sub(r"\s*\n\s*", " ", s)
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"^\[\d+\]\s*", "", s)  # drop a leading paragraph marker
    return s.strip(" :;\u2013-")


def extract_charges(text: str) -> str | None:
    """The tribunal's verbatim (already anonymized) statement of the charges.

    Handles two common forms: a numbered list after "la plainte … libellée ainsi :",
    and the narrative "le plaignant reproche à … d'avoir …". Returns None rather
    than risk a wrong excerpt.
    """
    cleaned = clean_decision_text(text)

    m = CHARGE_INTRO_RE.search(cleaned)
    if m:
        rest = cleaned[m.end(): m.end() + 3000]
        stop = CHARGE_STOP_RE.search(rest)
        excerpt = _tidy(rest[: stop.start()] if stop else rest)
        if len(excerpt) >= 20:
            return excerpt

    m2 = NARRATIVE_INTRO_RE.search(cleaned)
    if m2:
        # Start at the sentence opening for context ("Le plaignant reproche …").
        prev = max(cleaned.rfind(". ", 0, m2.start()), cleaned.rfind("\n", 0, m2.start()))
        start = prev + 1 if prev > 0 else m2.start()
        window = cleaned[start: start + 1400]
        stop = CHARGE_STOP_RE.search(window[20:])
        excerpt = _tidy(window[: stop.start() + 20] if stop else window)
        if len(excerpt) >= 40:
            return excerpt

    return None


def clean_plain(s: str | None) -> str | None:
    """Normalize a plain-text CMQ field (grounds, precision) or return None."""
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


# --- Disposition (the sanction imposed) ------------------------------------
# The formal ruling uses UPPERCASE verbs (IMPOSE / RADIE / PRONONCE ...), which
# distinguishes the actual order from lowercase mentions in the analysis or in
# cited precedents. We reproduce the tribunal's own words (verbatim), never our
# interpretation.
DISPO_RE = re.compile(
    r"\b(IMPOSE|RADIE|PRONONCE|CONDAMNE|SUSPEND|LIMITE|R[ÉE]PRIMANDE|R[ÉE]VOQUE)\b[^.]{0,400}\.")
SANCTION_DISPO_RE = re.compile(
    r"radiation|suspension|limitation|r[ée]primande|amende|r[ée]vocation", re.IGNORECASE)
# A procedural stay of redundant charges — not a disciplinary suspension.
PROCEDURAL_RE = re.compile(r"suspension\s+conditionnelle\s+des\s+proc[ée]dures|"
                           r"suspension\s+des\s+proc[ée]dures", re.IGNORECASE)
DISPO_KINDS = [
    ("radiation", "radiation"), ("suspension", "suspension"), ("limitation", "limitation"),
    ("revocation", r"r[ée]vocation"), ("reprimand", r"r[ée]primande"), ("fine", "amende"),
]


def extract_disposition(text: str) -> tuple[str | None, list[str]]:
    """Verbatim excerpt of the sanction(s) imposed + a coarse kind list.

    Returns (None, []) when no formal sanction order is confidently found.
    """
    cleaned = clean_decision_text(text)
    m = re.search(r"P(?:OUR|AR)\s+CES\s+MOTIFS", cleaned)
    region = cleaned[m.start():] if m else cleaned
    found: list[str] = []
    for lm in DISPO_RE.finditer(region):
        sent = lm.group(0)
        if SANCTION_DISPO_RE.search(PROCEDURAL_RE.sub("", sent)):
            t = _tidy(sent)
            if t and t not in found:
                found.append(t)
    if not found:
        return None, []
    joined = PROCEDURAL_RE.sub("", " ".join(found)).lower()
    kinds = [k for k, pat in DISPO_KINDS if re.search(pat, joined)]
    return " ".join(found), kinds


def case_reached_sanction(case: dict) -> bool:
    """True when a case has a decision imposing a sanction (guilt established)."""
    for d in case.get("decisions") or []:
        if re.search(r"sanction", d.get("precision") or "", re.I):
            return True
    return False


def build_decisions(record: dict, notice_backed: bool = False) -> list[dict]:
    """One entry per UPHELD disciplinary case: its grounds/result + decision
    metadata and (anonymized) charges from a fetched PDF when available.

    Only upheld cases (plainte/requête accueillie) are surfaced — a dismissed or
    withdrawn complaint is not a finding and must not be shown. When the doctor is
    backed by a published avis, a case whose summary result is still blank
    ("en cours") but which reached a sanction decision is also surfaced: the avis
    proves the sanction took effect even though the API hasn't caught up.
    """
    out: list[dict] = []
    seen_cases: set[str] = set()
    for entry in record.get("disciplinaryFiles") or []:
        for case in entry.get("items") or []:
            result = (case.get("result") or "").strip()
            real = result.lower() in REAL_RESULTS
            if not real and not (notice_backed and case_reached_sanction(case)):
                continue
            cnum = case.get("number")
            if cnum and cnum in seen_cases:
                continue
            if cnum:
                seen_cases.add(cnum)

            decisions = case.get("decisions") or []
            doc_decisions = [d for d in decisions
                             if isinstance(d.get("documentId"), int) and d["documentId"] > 0]
            primary = doc_decisions[0] if doc_decisions else (decisions[0] if decisions else {})

            info = {
                "case": cnum,
                "date": iso(primary.get("date")),
                "result": result or None,
                # The official summary of the complaint grounds (the "cause").
                "grounds": clean_plain(case.get("complaintReason")),
                "precision": clean_plain(primary.get("precision")),
                "precisionStatus": clean_plain(primary.get("precisionStatus")),
            }

            # A case may span several decisions (culpabilité, sanction, appeal);
            # the charges and the disposition live in whichever one states them.
            if doc_decisions:
                charges = None
                disposition = None
                dispo_kinds: list[str] = []
                ban = False
                used_doc = None
                has_text = False
                for d in doc_decisions:
                    text = load_decision_text(d["documentId"])
                    if not text:
                        continue
                    has_text = True
                    if used_doc is None:
                        used_doc = d["documentId"]
                    ban = ban or has_publication_ban(text)
                    if charges is None:
                        c = extract_charges(text)
                        if c:
                            charges = c
                            used_doc = d["documentId"]
                    if disposition is None:
                        disp, kinds = extract_disposition(text)
                        if disp:
                            disposition = disp
                            dispo_kinds = kinds
                info["documentId"] = used_doc or doc_decisions[0]["documentId"]
                info["hasText"] = has_text
                if ban:
                    info["publicationBan"] = True
                if charges:
                    info["charges"] = charges
                if disposition:
                    info["disposition"] = disposition
                    info["dispositionKinds"] = dispo_kinds

            links = []
            for d in decisions:
                for k in ("linkQuebec", "linkCanada"):
                    u = (d.get(k) or "").strip()
                    if u and u not in links:
                        links.append(u)
            if links:
                info["links"] = links

            out.append({k: v for k, v in info.items() if v is not None})
    return out
    return out


def link_source(url: str) -> str:
    u = url.lower()
    if "soquij" in u:
        return "SOQUIJ"
    if "canlii" in u:
        return "CanLII"
    return "CMQ"


def build_ruling_links(record: dict) -> list[dict]:
    seen = set()
    out = []
    for lk in record.get("rulingLinks") or []:
        url = (lk.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append({
            "case": lk.get("case"),
            "date": iso(lk.get("date")),
            "url": url,
            "source": link_source(url),
        })
    return out


def sanction_items(detail: dict) -> list[tuple[str, dict]]:
    out = []
    for field in FIELD_TO_TYPE:
        v = detail.get(field) or {}
        for item in v.get("items") or []:
            out.append((field, item))
    return out


# A complaint/motion is a genuine finding only when upheld.
REAL_RESULTS = {"plainte accueillie", "requête accueillie", "requete accueillie"}


def has_real_result(record: dict) -> bool:
    for entry in record.get("disciplinaryFiles") or []:
        for case in entry.get("items") or []:
            if (case.get("result") or "").strip().lower() in REAL_RESULTS:
                return True
    return False


def doctor_notices(number: str) -> list[dict]:
    """Deduped public avis for a permit as [{type, date}], newest first."""
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for rec in sorted(NOTICES_BY_NUMBER.get(number, []),
                      key=lambda r: r.get("noticeDate") or "", reverse=True):
        stype = NOTICE_TYPE.get(rec.get("categoryLabel"))
        if not stype:
            continue
        d = rec.get("noticeDate") or ""
        key = (stype, d)
        if key in seen:
            continue
        seen.add(key)
        out.append({"type": stype, "date": d})
    return out


def notice_status_kind(notices: list[dict]) -> str | None:
    """Headline status implied by a doctor's published avis (radiated > restricted)."""
    kinds = {NOTICE_KIND.get(n["type"]) for n in notices}
    if "radiated" in kinds:
        return "radiated"
    if "restricted" in kinds:
        return "restricted"
    return None


def normalize_record(record: dict) -> dict | None:
    detail = record.get("detail") or {}
    number = (record.get("number") or "").strip()
    notices = doctor_notices(number)
    items = sanction_items(detail)
    decisions = build_decisions(record, notice_backed=bool(notices))
    # Include any GENUINE disciplinary record: a registry sanction, an upheld
    # complaint/motion, a fetched decision, or a published CMQ avis. Exclude the
    # false positives whose only cases were rejected/withdrawn complaints.
    if not items and not has_real_result(record) and not decisions and not notices:
        return None

    status = record.get("status") or ""
    deceased = is_deceased(status)
    hist = record.get("history")

    sanctions = []
    for field, item in items:
        stype = FIELD_TO_TYPE[field]
        start_iso = iso(item.get("date"))
        reason = clean_notice(item.get("noticeDescription") or "")
        label = (item.get("noticeLabel") or "").strip()

        san = {
            "type": stype,
            "label": label or f"{stype.upper()} ({start_iso})",
            "date": start_iso or "",
            "active": sanction_active(field, status, deceased),
        }

        if start_iso and stype in ("radiation", "suspension", "limitation"):
            dtext, n, unit_fr = parse_duration(reason, stype)
            if dtext and n is not None:
                san["durationText"] = dtext
                half = "et demi" in dtext
                try:
                    y, mo, d = (int(x) for x in start_iso.split("-"))
                    end = derived_end(date(y, mo, d), n, unit_fr, half)
                    if end:
                        san["endDate"] = end.isoformat()
                        san["endDerived"] = True
                except ValueError:
                    pass

        if reason:
            san["reason"] = reason
        sanctions.append(san)

    sanctions.sort(key=lambda s: s.get("date") or "", reverse=True)

    specialty = (record.get("specialtyName") or "").strip() or None
    notice_kind = notice_status_kind(notices)
    status_k = status_kind(sanctions, has_finding=True, notice_kind=notice_kind)
    # A radiation found in a decision's disposition, when the doctor isn't
    # currently struck off, means a served (past) radiation the registry dropped.
    dispo_kinds = {k for dec in decisions for k in dec.get("dispositionKinds", [])}
    formerly_struck = (
        ("radiation" in dispo_kinds or "revocation" in dispo_kinds)
        and status_k != "radiated"
    )
    doc = {
        "number": number,
        "lastName": record.get("lastname") or "",
        "firstName": record.get("firstname") or "",
        "city": clean_city(record.get("city")),
        "specialty": specialty,
        "specialtyEn": specialty_en(specialty),
        "memberSince": record.get("memberSince"),
        "specialtyYear": parse_specialty_year(hist),
        "statusText": strip_status(status),
        "sanctions": sanctions,
        "caseCount": record.get("disciplinaryFileCount") or len(sanctions),
        "rulingLinks": build_ruling_links(record),
        "deceased": deceased,
        # Precomputed facet fields so the site can filter/sort without re-deriving.
        "primaryType": primary_type(sanctions),
        "statusKind": status_k,
        "formerlyStruckOff": formerly_struck or None,
        "sanctionYears": sanction_years(sanctions),
        "specialties": split_specialties(specialty),
        "decisions": decisions or None,
        "notices": notices or None,
        "collectedAt": record.get("collectedAt"),
    }
    # Drop null-valued optional keys for a clean file.
    return {k: v for k, v in doc.items() if v is not None}


def primary_type(sanctions: list[dict]) -> str | None:
    types = [s["type"] for s in sanctions]
    return min(types, key=lambda t: TYPE_RANK.get(t, 9)) if types else None


def status_kind(sanctions: list[dict], has_finding: bool = False,
                notice_kind: str | None = None) -> str:
    """Mirror the site's statusOf(): headline status from the active sanctions."""
    active = [s for s in sanctions if s.get("active")]
    if any(s["type"] in ("radiation", "revocation", "suspension") for s in active):
        return "radiated"
    if any(s["type"] in ("limitation", "commitment") for s in active):
        return "restricted"
    # A published CMQ avis is authoritative even when the registry hasn't caught up.
    if notice_kind:
        return notice_kind
    if sanctions:
        return "past"
    if has_finding:
        return "record"
    return "clean"


def sanction_years(sanctions: list[dict]) -> list[int]:
    years = {int(s["date"][:4]) for s in sanctions if (s.get("date") or "")[:4].isdigit()}
    return sorted(years, reverse=True)


def split_specialties(specialty: str | None) -> list[str] | None:
    if not specialty:
        return None
    parts = [p.strip() for p in specialty.split(",") if p.strip()]
    return parts or None


def specialty_en(specialty: str | None) -> str | None:
    """Map a (possibly multi-part) FR specialty to EN via the CMQ specialty list.

    Returns None if any part is unmapped, so the site falls back to the FR name
    rather than showing a half-translated string.
    """
    if not specialty:
        return None
    parts = [p.strip() for p in specialty.split(",") if p.strip()]
    en_parts = []
    for p in parts:
        en = SPECIALTY_MAP.get(p)
        if not en:
            return None
        en_parts.append(en)
    return ", ".join(en_parts) if en_parts else None


def headline_type(doc: dict) -> str:
    types = [s["type"] for s in doc["sanctions"]]
    if not types:
        return "record"
    return min(types, key=lambda t: TYPE_RANK.get(t, 9))


def recent_date(doc: dict) -> str:
    return max((s.get("date") or "" for s in doc["sanctions"]), default="")


def curate_sample(docs: list[dict], size: int = 30) -> list[dict]:
    """Pick a diverse, mostly-recent sample covering every sanction type."""
    by_recent = sorted(docs, key=recent_date, reverse=True)
    picked: list[dict] = []
    seen_numbers: set[str] = set()

    # 1) Ensure each sanction type has its most-recent representative.
    for t in ["revocation", "radiation", "suspension", "limitation", "commitment"]:
        for d in by_recent:
            if d["number"] in seen_numbers:
                continue
            if headline_type(d) == t:
                picked.append(d)
                seen_numbers.add(d["number"])
                break

    # 2) Fill the rest with the most recent overall.
    for d in by_recent:
        if len(picked) >= size:
            break
        if d["number"] in seen_numbers:
            continue
        picked.append(d)
        seen_numbers.add(d["number"])

    picked.sort(key=recent_date, reverse=True)
    return picked


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true",
                    help="also write a curated 30-record sample.json (for quick dev)")
    ap.add_argument("--sample-size", type=int, default=30)
    args = ap.parse_args()

    records = []
    with open(DATA, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    docs = []
    for r in records:
        doc = normalize_record(r)
        if doc:
            docs.append(doc)

    print(f"records normalized: {len(docs)} (of {len(records)} disciplined)")
    type_counts: dict[str, int] = {}
    for d in docs:
        type_counts[headline_type(d)] = type_counts.get(headline_type(d), 0) + 1
    print("headline type distribution:", type_counts)
    with_charges = sum(1 for d in docs for x in (d.get("decisions") or []) if x.get("charges"))
    with_en = sum(1 for d in docs if d.get("specialtyEn"))
    print(f"decisions with charges: {with_charges}   records with EN specialty: {with_en}")

    full_path = SITE_DATA / "doctors.json"
    full_path.write_text(
        json.dumps(docs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {full_path} ({len(docs)} records)")

    if args.sample:
        sample = curate_sample(docs, args.sample_size)
        sample_path = SITE_DATA / "sample.json"
        sample_path.write_text(
            json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {sample_path} ({len(sample)} records)")


if __name__ == "__main__":
    main()
