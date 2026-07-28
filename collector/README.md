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
   the city but not the address, respects non-publication orders that protect
   patients, and recovers temporary radiations that were already served (these drop
   off the live registry but remain in the decision text).
6. **Build the site.** The website reads `doctors.json` and generates the pages.

## Keeping it up to date (weekly)

`refresh.py` runs every week (via GitHub Actions) and does the small, incremental
version of the above:

1. Reads the CMQ's published notices, a rolling list of the last three months of
   radiations, practice restrictions, suspensions and licence revocations.
2. Re-checks only the physicians named in a new notice.
3. Downloads any new decision documents.
4. Rebuilds `doctors.json`.
5. Writes a short summary of what changed, which becomes a GitHub issue.

The notices are the fast path: the CMQ publishes one the moment a sanction takes
effect, often before the main directory record catches up. So the weekly run
touches only a handful of physicians instead of the whole registry.

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
| `verify_notice_coverage.py` | Check that every doctor in the notices is on the site. |
| `inspect_one.py`, `fetch_decision.py` | Small helpers for looking at a single record or document. |

## What stays on the collecting machine

The website only needs the two small, privacy-safe files that the weekly update
depends on: the disciplined subset (with contact details removed) and the history
of published notices. Everything else stays local and is not published: the full
raw directory, because it holds personal contact information we do not use, and the
downloaded decision PDFs, because they are large and can be fetched again from the
CMQ at any time.
