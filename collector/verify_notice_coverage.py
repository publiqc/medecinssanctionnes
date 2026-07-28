"""Cross-check the CMQ notice feeds against our tracked dataset.

Confirms every doctor named in the disciplinary avis feeds (radiation,
limitation, suspension, revocation) is present in site/src/data/doctors.json.
"""
import json
from pathlib import Path

from cmq_client import (
    DISCIPLINARY_NOTICE_CATEGORIES,
    NOTICE_CATEGORIES,
    get_notice_listing,
)

DOCTORS = Path(__file__).resolve().parent.parent / "site" / "src" / "data" / "doctors.json"


def main():
    tracked = {str(d["number"]).strip(): d for d in json.load(DOCTORS.open(encoding="utf-8"))}
    print(f"Tracked doctors: {len(tracked)}\n")

    missing = []
    for cat in DISCIPLINARY_NOTICE_CATEGORIES:
        items = get_notice_listing(cat)
        label = NOTICE_CATEGORIES[cat]
        present = sum(1 for it in items if str(it.get("number", "")).strip() in tracked)
        print(f"category {cat} ({label}): {len(items)} notices, {present} tracked")
        for it in items:
            num = str(it.get("number", "")).strip()
            if num not in tracked:
                missing.append((cat, label, num, it.get("formattedLabel"),
                                it.get("city"), it.get("date")))

    print()
    if not missing:
        print("ALL notice-feed doctors are tracked.")
        return
    print(f"MISSING ({len(missing)}):")
    for cat, label, num, name, city, date in missing:
        print(f"  [{label}] {num}  {name}  {city}  {date}")


if __name__ == "__main__":
    main()
