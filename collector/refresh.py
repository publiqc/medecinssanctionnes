"""Weekly incremental refresh, built on the CMQ avis feeds.

Cheap by design: instead of re-scanning the ~44k-physician registry, we read the
disciplinary avis feeds (getNoticeListing — a rolling ~3-month "what's new"
stream) to learn who to look at. The avis is published the moment a sanction takes
effect, so this catches new sanctions the same week. Nothing is published when a
sanction ends, though, so we also re-check every doctor we currently show as
sanctioned — otherwise an accusation could never be withdrawn.

Pipeline:
  1. Merge the disciplinary avis feeds into data/notices_ledger.jsonl.
  2. (Re)fetch and upsert into data/disciplined.jsonl, by physicianId:
       - every doctor named in the avis ledger (catches NEW sanctions), and
       - every doctor we currently show as sanctioned (catches LIFTED ones — no
         avis is ever published when a sanction ends, so this is the only signal).
  3. Fetch any newly-referenced decision PDFs (fetch_decisions.py, idempotent).
  4. Normalize -> site/src/data/doctors.json.
  5. Write a change summary (added / status-changed doctors) to
     data/refresh_summary.md for CI to post as a GitHub issue.

The site build + deploy runs in the GitHub Action after this script.

Usage:
  python refresh.py                # full incremental refresh
  python refresh.py --rate 2       # cap physician fetches to 2/s (default)
  python refresh.py --skip-fetch   # rebuild + diff only, no API calls
  python refresh.py --no-verify    # avis ledger only (skip the re-verification pass)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import cmq_client as api
import fetch_notices
from collect import summarize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
DISCIPLINED = DATA / "disciplined.jsonl"
DOCTORS = ROOT / "site" / "src" / "data" / "doctors.json"
SUMMARY = DATA / "refresh_summary.md"


def ledger_physician_ids() -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for rec in fetch_notices.load_ledger().values():
        pid = rec.get("physicianId")
        if isinstance(pid, int) and pid not in seen:
            seen.add(pid)
            ids.append(pid)
    return ids


def accused_physician_ids() -> list[int]:
    """physicianIds we currently present as being under an active sanction.

    The avis feed announces sanctions being imposed, but nothing is ever published
    when one is lifted or served. So the feed alone can only ever add accusations —
    re-checking everyone we currently accuse against the registry is what lets us
    withdraw one.
    """
    if not DOCTORS.exists() or not DISCIPLINED.exists():
        return []
    accused = {str(d.get("number") or "").strip()
               for d in json.loads(DOCTORS.read_text(encoding="utf-8"))
               if d.get("statusKind") in ("radiated", "restricted")}
    ids: list[int] = []
    seen: set[int] = set()
    for line in DISCIPLINED.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        pid = rec.get("physicianId")
        if (str(rec.get("number") or "").strip() in accused
                and isinstance(pid, int) and pid not in seen):
            seen.add(pid)
            ids.append(pid)
    return ids


def fetch_disciplined_record(pid: int) -> dict | None:
    """Fetch one physician's full disciplined record (details + files + history)."""
    status, body = api.get_physician_details(pid)
    if status != 200 or not body:
        return None
    number = (body.get("number") or "").strip()
    files: list = []
    if number:
        f_status, f_body = api.search_disciplinary_files(number=number)
        if f_status == 200 and isinstance(f_body, list):
            files = f_body
    history = None
    h_status, h_body = api.get_physician_history(pid)
    if h_status == 200:
        history = h_body
    return summarize(body, files, history)


def upsert_disciplined(by_pid: dict[int, dict]) -> None:
    """Merge freshly-fetched records into disciplined.jsonl by physicianId."""
    existing: dict[int, dict] = {}
    order: list[int] = []
    if DISCIPLINED.exists():
        for line in DISCIPLINED.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            pid = rec.get("physicianId")
            if pid not in existing:
                order.append(pid)
            existing[pid] = rec
    for pid, rec in by_pid.items():
        if pid not in existing:
            order.append(pid)
        existing[pid] = rec
    with DISCIPLINED.open("w", encoding="utf-8") as fh:
        for pid in order:
            fh.write(json.dumps(existing[pid], ensure_ascii=False) + "\n")


def status_snapshot() -> dict[str, dict]:
    """Map permit number -> {kind, name} from the current doctors.json."""
    if not DOCTORS.exists():
        return {}
    out: dict[str, dict] = {}
    for d in json.loads(DOCTORS.read_text(encoding="utf-8")):
        num = str(d.get("number") or "").strip()
        if num:
            out[num] = {"kind": d.get("statusKind") or "record",
                        "name": f"{d.get('lastName', '')}, {d.get('firstName', '')}"}
    return out


def run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=HERE, check=True)


# Readable labels for the change summary, per language.
STATUS_LABELS = {
    "fr": {"radiated": "radié ou suspendu", "restricted": "exercice limité",
           "record": "antécédent disciplinaire", "past": "sanction purgée",
           "clean": "aucune sanction"},
    "en": {"radiated": "struck off or suspended", "restricted": "restricted practice",
           "record": "disciplinary record", "past": "sanction served",
           "clean": "no sanction"},
}
CATEGORY_LABELS = {
    "fr": {"radiation": "radiation", "limitation": "limitation",
           "suspension": "suspension", "revocation": "révocation de permis"},
    "en": {"radiation": "striking off", "limitation": "practice restriction",
           "suspension": "suspension", "revocation": "licence revocation"},
}


def _summary_section(lang: str, new_notices: list[dict], added: list[dict],
                     changed: list[dict], removed: list[dict]) -> list[str]:
    tr = {
        "fr": {"none": "Aucun changement cette semaine.",
               "notices": "Nouveaux avis", "added": "Médecins ajoutés",
               "changed": "Changements de statut", "permit": "permis",
               "removed": "Médecins retirés (plus aucune sanction au tableau)"},
        "en": {"none": "No changes this week.",
               "notices": "New notices", "added": "Doctors added",
               "changed": "Status changes", "permit": "permit",
               "removed": "Doctors removed (no sanction left on the register)"},
    }[lang]
    status = STATUS_LABELS[lang]
    cats = CATEGORY_LABELS[lang]
    out: list[str] = []
    if not (new_notices or added or changed or removed):
        out.append(tr["none"])
        return out
    if new_notices:
        out.append(f"### {tr['notices']} ({len(new_notices)})")
        for n in new_notices:
            cat = cats.get(n["categoryLabel"], n["categoryLabel"])
            out.append(f"- **{cat}** : {n['name']} "
                       f"({tr['permit']} {n['number']}), {n.get('city', '')}, {n['noticeDate']}")
        out.append("")
    if added:
        out.append(f"### {tr['added']} ({len(added)})")
        for d in added:
            out.append(f"- {d['name']} ({tr['permit']} {d['number']}) : "
                       f"{status.get(d['statusKind'], d['statusKind'])}")
        out.append("")
    if changed:
        out.append(f"### {tr['changed']} ({len(changed)})")
        for d in changed:
            old = status.get(d["old"], d["old"])
            new = status.get(d["new"], d["new"])
            out.append(f"- {d['name']} ({tr['permit']} {d['number']}) : {old} → {new}")
        out.append("")
    if removed:
        out.append(f"### {tr['removed']} ({len(removed)})")
        for d in removed:
            out.append(f"- {d['name']} ({tr['permit']} {d['number']}) : "
                       f"{status.get(d['old'], d['old'])} → —")
        out.append("")
    return out


def write_summary(new_notices: list[dict], added: list[dict],
                  changed: list[dict], removed: list[dict]) -> None:
    lines = ["# Mise à jour hebdomadaire des sanctions / Weekly sanctions update", ""]
    lines.append("## Français")
    lines += _summary_section("fr", new_notices, added, changed, removed)
    lines.append("")
    lines.append("## English")
    lines += _summary_section("en", new_notices, added, changed, removed)
    SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {SUMMARY}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=float, default=2.0,
                    help="max physician fetches per second (default 2)")
    ap.add_argument("--skip-fetch", action="store_true",
                    help="rebuild + diff only, no CMQ API calls")
    ap.add_argument("--no-verify", action="store_true",
                    help="only refresh doctors named in the avis ledger; skip re-checking "
                         "everyone currently shown as sanctioned")
    args = ap.parse_args()

    before = status_snapshot()
    new_notices: list[dict] = []

    if not args.skip_fetch:
        total, new_notices = fetch_notices.merge()
        print(f"ledger: {total} notices (+{len(new_notices)} new)")

        pids = ledger_physician_ids()
        from_ledger = len(pids)
        if not args.no_verify:
            seen = set(pids)
            pids += [p for p in accused_physician_ids() if p not in seen]
        print(f"refreshing {len(pids)} physicianIds "
              f"({from_ledger} from the avis ledger, "
              f"{len(pids) - from_ledger} re-verified as currently sanctioned)")
        by_pid: dict[int, dict] = {}
        delay = 1.0 / args.rate if args.rate > 0 else 0.0
        for i, pid in enumerate(pids, 1):
            try:
                rec = fetch_disciplined_record(pid)
            except (api.ApiError, api.PermanentError) as exc:
                print(f"  ! {pid}: {exc}", file=sys.stderr)
                continue
            if rec:
                by_pid[pid] = rec
            if i % 10 == 0:
                print(f"  {i}/{len(pids)}")
            if delay:
                time.sleep(delay)
        if by_pid:
            upsert_disciplined(by_pid)
            print(f"upserted {len(by_pid)} records into disciplined.jsonl")

        # Grab any newly-referenced decision PDFs (idempotent).
        run([sys.executable, "fetch_decisions.py"])

    # Rebuild the site dataset.
    run([sys.executable, "normalize.py"])

    # Diff against the pre-refresh snapshot.
    after_full = json.loads(DOCTORS.read_text(encoding="utf-8"))
    after = {str(d.get("number") or "").strip(): d for d in after_full}
    name_of = {n: f"{d.get('lastName', '')}, {d.get('firstName', '')}"
               for n, d in after.items()}

    added = [{"number": n, "name": name_of[n], "statusKind": d.get("statusKind")}
             for n, d in after.items() if n not in before]
    changed = [{"number": n, "name": name_of[n],
                "old": before[n]["kind"], "new": d.get("statusKind")}
               for n, d in after.items()
               if n in before and before[n]["kind"] != (d.get("statusKind") or "record")]
    # Dropping out means the last sanction came off the register — the change we most
    # need to publish, since it is us withdrawing an accusation.
    removed = [{"number": n, "name": b["name"], "old": b["kind"]}
               for n, b in before.items() if n not in after]

    print(f"\nadded: {len(added)}   status-changed: {len(changed)}   removed: {len(removed)}")
    for d in added:
        print(f"  + {d['name']} ({d['number']}) {d['statusKind']}")
    for d in changed:
        print(f"  ~ {d['name']} ({d['number']}) {d['old']} -> {d['new']}")
    for d in removed:
        print(f"  - {d['name']} ({d['number']}) {d['old']} -> no longer listed")

    write_summary(new_notices, added, changed, removed)


if __name__ == "__main__":
    main()
