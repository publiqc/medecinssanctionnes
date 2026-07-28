"""Harvest the CMQ public disciplinary avis feeds into a persistent ledger.

The /bottin/avis feeds (getNoticeListing) roll on a ~3-month window, so we can't
rely on re-querying them to keep history. This script merges each run's notices
into an append-only ledger (data/notices_ledger.jsonl), tracking firstSeen /
lastSeen so a sanction stays known long after it drops off the live feed.

The ledger is an authoritative inclusion + status signal for the normalizer: the
CMQ publishes an avis the moment a sanction takes effect, often before the
physician-details/disciplinary-files API reflects it.

Usage:
  python fetch_notices.py            # merge current disciplinary feeds into the ledger
  python fetch_notices.py --show     # print the ledger, no fetch
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from cmq_client import (
    DISCIPLINARY_NOTICE_CATEGORIES,
    NOTICE_CATEGORIES,
    get_notice_listing,
)

LEDGER = Path(__file__).resolve().parent.parent / "data" / "notices_ledger.jsonl"


def notice_date(raw: str | None) -> str:
    return (raw or "")[:10]


def ledger_key(rec: dict) -> str:
    nid = rec.get("noticeId")
    if nid is not None:
        return f"id:{nid}"
    return f"{rec.get('number')}|{rec.get('category')}|{rec.get('noticeDate')}"


def load_ledger() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rec = json.loads(line)
                out[ledger_key(rec)] = rec
    return out


def write_ledger(records: dict[str, dict]) -> None:
    ordered = sorted(records.values(),
                     key=lambda r: (r.get("noticeDate") or "", r.get("number") or ""))
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("w", encoding="utf-8") as fh:
        for rec in ordered:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def merge() -> tuple[int, list[dict]]:
    today = date.today().isoformat()
    ledger = load_ledger()
    new_records: list[dict] = []
    for cat in DISCIPLINARY_NOTICE_CATEGORIES:
        label = NOTICE_CATEGORIES[cat]
        for it in get_notice_listing(cat):
            rec = {
                "noticeId": it.get("noticeId"),
                "number": str(it.get("number") or "").strip(),
                "physicianId": it.get("physicianId"),
                "name": it.get("formattedLabel"),
                "city": it.get("city"),
                "category": cat,
                "categoryLabel": label,
                "noticeDate": notice_date(it.get("date")),
            }
            key = ledger_key(rec)
            existing = ledger.get(key)
            if existing:
                existing["lastSeen"] = today
                # Backfill any fields that were previously missing.
                for k, v in rec.items():
                    if v is not None and not existing.get(k):
                        existing[k] = v
            else:
                rec["firstSeen"] = today
                rec["lastSeen"] = today
                ledger[key] = rec
                new_records.append(rec)
    write_ledger(ledger)
    return len(ledger), new_records


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true", help="print the ledger without fetching")
    args = ap.parse_args()

    if args.show:
        for rec in load_ledger().values():
            print(json.dumps(rec, ensure_ascii=False))
        return

    total, new = merge()
    print(f"ledger: {total} notices  (+{len(new)} new this run)")
    for rec in new:
        print(f"  NEW [{rec['categoryLabel']}] {rec['number']}  {rec['name']}  {rec['noticeDate']}")


if __name__ == "__main__":
    main()
