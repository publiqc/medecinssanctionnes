# AGENTS.md

Instructions for AI agents working in this repository. Read this before changing
collector or site code.

## What this is

A bilingual public-interest site listing Quebec physicians sanctioned by the
Collège des médecins du Québec (CMQ). Public data only, from the CMQ's own
registry. Real people are named, so **accuracy outranks completeness, features and
tidiness**. When in doubt, publish less, never more.

- `collector/` — Python 3.12 pipeline that builds the dataset. Standard library
  plus `pypdf`/`pypdfium2`.
- `site/` — Astro + Tailwind/daisyUI + Pagefind. Node 22.12+.
- `data/` — working state. Mostly gitignored; see "Tracked data files" below.

## The rules that must not be broken

### 1. The registry is the only source of truth for current status

`getPhysicianDetails` says what is in force **today**. A published avis
(`getNoticeListing`) proves a sanction was **imposed**, never that it still
applies — the CMQ never retracts one.

Measured 2026-08-08: 91 of 101 actively radiated doctors were absent from the
rolling avis feed (some radiated since 1969), and the registry does not lag it.
Treating an avis as a status override once labelled two doctors who had served
their radiation as "Actuellement radié". Do not reintroduce it.

Avis are for **discovery** (who to re-fetch) and **history**. Nothing else.

### 2. A sanction never expires on its own

Reinstatement requires the doctor to apply. All 26 radiated doctors whose parsed
end date had passed were still radiated. `endDate` is derived and indicative
only — **never** infer that a sanction is over because its duration elapsed. Only
the registry can say.

### 3. A doctor is never removed once published

The CMQ **deletes** a sanction from a record once it stops applying. Without a
history that silently erases the doctor (this happened to Lalonde 90127 and
Garceau 81429). `data/sanctions_ledger.jsonl` remembers every sanction we have
seen; `normalize.py` merges live items (active) with ledger items the registry
has dropped (served). An ended sanction is a **status change**, not a removal.

`refresh.py` still reports a "removed" section — it is a tripwire. If it ever
fires, something is wrong.

### 4. Only genuine findings are listed

A registry sanction (current or since ended), an upheld complaint/motion
(`plainte accueillie` / `requête accueillie`), a fetched decision, or a published
avis. Dismissed or withdrawn complaints are never shown. Administrative striking
off for unpaid dues is not a sanction. Non-publication orders protecting patients
are respected. Official text is reproduced verbatim.

### 5. The invariant, enforced in CI

```
statusKind == "radiated"   <=>   an active radiation, revocation or suspension
```

`collector/verify_status.py` checks both directions offline, re-deriving from raw
records and deliberately ignoring the avis ledger so it cannot inherit the
assumption it exists to catch. It runs in `refresh.yml` **before** the commit
step, so a false accusation fails the job instead of reaching the site. Keep it
that way.

### 6. Two files must stay in sync

`status_kind()` in `collector/normalize.py` and `statusOf()` in
`site/src/lib/types.ts` implement the same rule. Change one, change the other, or
the page will contradict the dataset.

### 7. Output must be deterministic

Running `normalize.py` twice with unchanged inputs must produce a
**byte-identical** `doctors.json`. Volatile values (timestamps, unstable ordering)
must not leak into it — `collectedAt` was removed for exactly this reason. Weekly
commits should be readable at a glance; noise hides real changes.

## Data flow

```
CMQ API ──> collect.py ──────────> data/disciplined.jsonl   (registry snapshot)
        └─> fetch_notices.py ────> data/notices_ledger.jsonl (avis history)
                                   data/sanctions_ledger.jsonl (sanction history)
                                        │
        fetch_decisions.py ──> data/decisions/*.txt
                                        ▼
                              normalize.py ──> site/src/data/doctors.json ──> Astro
```

Weekly, `refresh.py` re-checks two cohorts, because **an avis is published when a
sanction starts and nothing at all when it ends**:

1. anyone named in a new avis — how new sanctions are discovered;
2. everyone currently shown as `radiated` or `restricted` (~360) — the only way a
   sanction can be found to have ended.

Doctors at `past`/`record`/`clean` are not re-checked; a new sanction on them
produces an avis.

### Tracked data files

Committed (small, no contact PII): `disciplined.jsonl`, `notices_ledger.jsonl`,
`sanctions_ledger.jsonl`, `site/src/data/doctors.json`. Everything else in
`data/` is gitignored, including `physicians.jsonl` (contains PII), the decision
PDF cache (re-fetchable) and `refresh_summary.md` (a CI artifact — a stale local
copy is **not** evidence of what CI did).

Both ledgers are **append-only**. Never rewrite or prune them.

## CMQ API notes

`POST https://www.cmq.org/api/directory`, unauthenticated JSON, wrapped by
`collector/cmq_client.py`.

| Method | Use |
|---|---|
| `getPhysicianDetails` | current status + active sanction items |
| `getPhysicianHistory` | past/current decision counts |
| `searchDisciplinaryFiles` | permanent case history |
| `getNoticeListing` | rolling ~3-month avis feed |
| `getDisciplinaryDecisionDocument` | decision PDFs |
| `getSpecialties` | FR→EN specialty names |

- Notice categories: `1` radiation, `2` limitation, `3` suspension, `6` revocation.
- Sanction fields: `strikingOffTheRoll`, `revocations`, `suspensions`,
  `restrictions`, `commitments`.
- **`restrictions.count` can undercount** (Duranleau 86049 reported `count=1` with
  2 items). Always iterate `items[]`; never trust `count`.
- `search_physicians(number=...)` has returned **HTTP 422**. Resolve a permit via
  the `physicianId` stored in `disciplined.jsonl` instead.
- Be polite: rate-limit (~2 req/s, `--rate 2`), and the CMQ caps requests per IP
  per day. A full weekly run is ~1,100 requests / ~10 minutes.

## Commands

```powershell
pip install -r collector/requirements.txt

cd collector
python refresh.py --rate 2        # full weekly run
python refresh.py --skip-fetch    # rebuild + diff, no API calls
python refresh.py --no-verify     # skip the re-verification cohort
python normalize.py               # rebuild doctors.json only
python verify_status.py           # the invariant gate (exit 1 on violation)
python sanctions_history.py       # fold current sanctions into the ledger

cd site
npm run build                     # static build + Pagefind index
npm run dev
```

## Environment gotchas (Windows / PowerShell 5.1)

- Chain with `;`. **Never** `&&`.
- No heredocs. For a multi-line commit message, write a file and use
  `git commit -F file`.
- `git show X > file` writes UTF-16 and later breaks decoding. Use
  `subprocess.run(["git","show",...]).stdout.decode("utf-8")`.
- `Get-Content` defaults to ANSI; pass `-Encoding UTF8` or accented text looks
  like mojibake. Console garbling is usually display-only — verify with Python
  before assuming a file is corrupt.
- `Select-String | Measure-Object` counts **lines**, not matches. Astro emits
  near-minified HTML, so use `[regex]::Matches()` to count occurrences.
- Avoid multi-line `python -c "..."`; quoting breaks. Write a temp `.py` file.

## Working style here

- Verify against the live API rather than assuming. This codebase's worst bugs
  were plausible-sounding assumptions (the avis override, the 30-day grace
  window) that measurement disproved.
- When comparing datasets, diff **semantically**. Raw line counts mislead: a
  single removed record shifts every later index.
- Prefer extending an existing pattern over inventing one. The sanctions ledger
  deliberately mirrors the notices ledger.
- After changing status logic, run `verify_status.py` and rebuild the site.
