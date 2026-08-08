"""Assert the published status matches the CMQ registry — nothing else.

Guards the one claim the site cannot get wrong: calling a doctor currently struck
off. Re-derives the active sanctions straight from the raw API records in
data/disciplined.jsonl and checks both directions against site/src/data/doctors.json:

    statusKind == "radiated"  <=>  an active radiation/revocation/suspension

This deliberately does NOT consult the avis ledger. A published avis is evidence a
sanction was imposed, never proof it is still in force — treating it as a status
override is exactly the bug this check exists to catch. Offline; exits non-zero on
any violation so a weekly refresh cannot publish a false accusation.
"""
import json
import sys
from pathlib import Path

from normalize import FIELD_TO_TYPE, sanction_items, is_deceased, sanction_active

ROOT = Path(__file__).resolve().parent.parent
DISCIPLINED = ROOT / "data" / "disciplined.jsonl"
DOCTORS = ROOT / "site" / "src" / "data" / "doctors.json"

HARD = ("radiation", "revocation", "suspension")


def registry_hard_sanction(record: dict) -> bool:
    status = record.get("status") or ""
    deceased = is_deceased(status)
    for field, _item in sanction_items(record.get("detail") or {}):
        if FIELD_TO_TYPE[field] in HARD and sanction_active(field, status, deceased):
            return True
    return False


def main() -> int:
    raw = {}
    for line in DISCIPLINED.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rec = json.loads(line)
            raw[(rec.get("number") or "").strip()] = rec

    published = json.loads(DOCTORS.read_text(encoding="utf-8"))
    false_accusations, missed = [], []

    for doc in published:
        num = str(doc.get("number") or "").strip()
        rec = raw.get(num)
        if rec is None:
            continue
        labelled = doc.get("statusKind") == "radiated"
        actual = registry_hard_sanction(rec)
        name = f"{doc.get('lastName', '')}, {doc.get('firstName', '')}"
        if labelled and not actual:
            false_accusations.append((num, name, rec.get("status")))
        elif actual and not labelled:
            missed.append((num, name, doc.get("statusKind")))

    print(f"published: {len(published)}   "
          f"labelled radiated: {sum(1 for d in published if d.get('statusKind') == 'radiated')}")

    if false_accusations:
        print(f"\nFALSE ACCUSATION — labelled radiated, no active registry sanction "
              f"({len(false_accusations)}):")
        for num, name, status in false_accusations:
            print(f"  {num}  {name}  registry says: {status}")
    if missed:
        print(f"\nMISSED — active registry sanction, not labelled radiated ({len(missed)}):")
        for num, name, kind in missed:
            print(f"  {num}  {name}  labelled: {kind}")

    if false_accusations or missed:
        return 1
    print("\nOK: published status matches the registry in both directions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
