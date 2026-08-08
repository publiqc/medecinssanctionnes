# Collector

The data pipeline behind [Médecins sanctionnés / Sanctioned Doctors](../README.md).
It gathers public disciplinary information from the Collège des médecins du Québec
(CMQ) and produces the dataset the website is built from
(`site/src/data/doctors.json`).

Python 3.12, mostly the standard library, plus `pypdf` and `pypdfium2` for reading
decision PDFs. Install with `pip install -r requirements.txt`.

## The source

All data comes from the CMQ's public directory, through the same unauthenticated
JSON endpoint their own website uses:

```
POST https://www.cmq.org/api/directory
```

We only read public information. Requests are paced, retried gently, and identify
themselves with a contact address (`cmq_client.USER_AGENT`) so the CMQ can reach
us rather than block us. The CMQ `robots.txt` sets no restrictions on these pages.

## How the site was populated (step by step)

1. **Find every physician.** `collect.py` walks the CMQ directory and saves each
   physician it finds, flagging anyone with a disciplinary trace (a current
   sanction, a disciplinary file, or an old decision). This is done once, and it
   is the slow part.
2. **Keep only the disciplined, without contact details.** From that sweep we keep
   the subset of physicians who have a disciplinary history, and we strip out the
   practice address, phone and fax we never use. The result is
   `disciplined.jsonl`.
3. **Read the actual decisions.** `fetch_decisions.py` downloads the public
   decision documents referenced by those files and extracts their text, so we can
   show the real charges and sanctions instead of a one-line summary.
4. **Add English specialty names.** `fetch_specialties.py` builds a French to
   English map of medical specialties so the English site reads naturally.
5. **Build the dataset.** `normalize.py` turns everything into `doctors.json`. It
   keeps only genuine findings, reproduces the official text word for word, records
   the city but not the address, and respects non-publication orders that protect
   patients.
6. **Build the site.** The website reads `doctors.json` and generates the pages.

## Saying who is *currently* sanctioned

This is the one thing the site must not get wrong, so it follows a single rule:

> **The CMQ registry is the only source of truth for a doctor's current status.**
> A published notice is proof a sanction was *imposed*. It is never proof the
> sanction is *still in force*.

The distinction matters because the two sources behave very differently:

| | Registry (`getPhysicianDetails`) | Notices (`getNoticeListing`) |
|--|--|--|
| Says what | The sanctions in force **today** | That a sanction was imposed, once |
| Retracted when a sanction ends? | Yes, the entry disappears | **No, never** |
| Covers | Every doctor | A rolling ~3 month window |

So a doctor whose radiation has been served still has a notice on file forever,
but the registry shows them active again. We label them *sanction purgée /
sanction already served*, not *currently struck off*. Treating the notice as the
status was a real bug: two doctors who had served their radiation were shown as
currently struck off.

A related trap: **a radiation does not expire on its own.** A two-year radiation
from 1996 can still be in force today, because reinstatement requires the doctor
to apply for it. So the end date we parse out of a decision is indicative only —
never infer that a sanction is over because its duration has elapsed. Only the
registry can tell us.

The rule is implemented in two places that must stay in agreement:
`normalize.py` (`status_kind`) and `site/src/lib/types.ts` (`statusOf`).

## Keeping it up to date (weekly)

`refresh.py` runs every Monday (via GitHub Actions). The design follows from one
asymmetry:

> The CMQ publishes a notice when a sanction **starts**, and nothing at all when
> it **ends**.

So the notices alone can only ever *add* an accusation. They can never withdraw
one. That is why the weekly run re-checks two groups of doctors:

1. **Anyone named in a new notice** — this is how we *discover* new sanctions.
   The notices are the fast path: the CMQ publishes one the moment a sanction
   takes effect.
2. **Everyone we currently show as sanctioned** — struck off or restricted. This
   is the only way we ever find out that a sanction has *ended*, because nothing
   is published when it does. About 360 doctors, a few minutes of paced
   requests.

Doctors we show as `past`, `record` or `clean` are not re-checked: if they pick
up a new sanction, a notice will tell us. Pass `--no-verify` to skip group 2.

The run then downloads any new decision documents, rebuilds `doctors.json`, and
writes a summary of what changed, which becomes a GitHub issue. The summary
reports three kinds of change: doctors **added**, doctors whose **status
changed**, and doctors **removed** — removed meaning the last sanction came off
the register, so we stop listing them. Removals matter most, because that is us
withdrawing an accusation.

### The safety check

Before anything is committed, `verify_status.py` asserts the published data
against the registry, in both directions:

```
statusKind == "radiated"   <=>   an active radiation, revocation or suspension
```

It re-derives the answer from the raw API records and deliberately ignores the
notices, so it cannot inherit the assumption it exists to catch. It runs *before*
the commit step, so a false accusation fails the workflow instead of reaching the
site.

## Scripts

| Script | Purpose |
|--------|---------|
| `cmq_client.py` | Small client for the CMQ endpoints. |
| `collect.py` | One-time full sweep of the directory. |
| `fetch_notices.py` | Update the running history of published notices. |
| `fetch_decisions.py` | Download decision documents and extract their text. |
| `fetch_specialties.py` | Build the French to English specialty map. |
| `normalize.py` | Produce `site/src/data/doctors.json`. |
| `refresh.py` | The weekly update that ties the steps together. |
| `verify_status.py` | Assert the published status matches the registry. Fails the weekly run if not. |
| `verify_notice_coverage.py` | Check that every doctor in the notices is on the site. |
| `inspect_one.py`, `fetch_decision.py` | Small helpers for looking at a single record or document. |

## What stays on the collecting machine

The website only needs the two small, privacy-safe files that the weekly update
depends on: the disciplined subset (with contact details removed) and the history
of published notices. Everything else stays local and is not published: the full
raw directory, because it holds personal contact information we do not use, and the
downloaded decision PDFs, because they are large and can be fetched again from the
CMQ at any time.
