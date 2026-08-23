"""Append-only history of every sanction the CMQ registry has shown us.

The CMQ deletes a sanction from a physician's record once it stops applying: a
served radiation, or a fulfilled undertaking to cease practice. That makes the
registry authoritative about what is in force *today*, but it is not a history —
and without one a sanction, sometimes the doctor's whole entry, would silently
vanish from the site the week it ended (Lalonde 90127, Garceau 81429).

So we keep what we saw. Each sanction is recorded the first time the registry
shows it and never removed, with firstSeen/lastSeen so a later run can tell which
ones are still in force. `normalize.py` merges the two: live items stay active,
items the registry has dropped are shown as served.

Only sanctions actually observed on the registry are recorded, so this can never
resurrect a doctor whose complaints were dismissed or withdrawn.
"""
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "data" / "sanctions_ledger.jsonl"

SANCTION_FIELDS = ("strikingOffTheRoll", "revocations", "suspensions",
                   "restrictions", "commitments")


def iso_day(raw: str | None) -> str:
    """'2026-08-10T00:00:00.000Z' -> '2026-08-10'."""
    s = (raw or "").strip()
    return s[:10] if len(s) >= 10 else s


def ledger_key(number: str, field: str, day: str) -> str:
    return f"{number}|{field}|{day}"


def load() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if LEDGER.exists():
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rec = json.loads(line)
                out[ledger_key(rec["number"], rec["field"], rec["date"])] = rec
    return out


def write(records: dict[str, dict]) -> None:
    ordered = sorted(records.values(),
                     key=lambda r: (r.get("number") or "", r.get("date") or "",
                                    r.get("field") or ""))
    LEDGER.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in ordered),
        encoding="utf-8")


def registry_sanctions(record: dict):
    """Yield (number, field, day, item) for each sanction on a disciplined.jsonl record."""
    number = (record.get("number") or "").strip()
    if not number:
        return
    detail = record.get("detail") or {}
    for field in SANCTION_FIELDS:
        for item in ((detail.get(field) or {}).get("items") or []):
            yield number, field, iso_day(item.get("date")), item


def observe(records, today: str | None = None) -> list[dict]:
    """Fold every sanction in `records` into the ledger. Returns the newly seen ones."""
    today = today or date.today().isoformat()
    ledger = load()
    new: list[dict] = []
    for record in records:
        for number, field, day, item in registry_sanctions(record):
            key = ledger_key(number, field, day)
            existing = ledger.get(key)
            if existing:
                # Keep the earliest sighting; refresh the wording in case it was edited.
                existing["lastSeen"] = max(existing.get("lastSeen") or "", today)
                existing["item"] = item
                continue
            rec = {"number": number, "field": field, "date": day, "item": item,
                   "firstSeen": today, "lastSeen": today}
            ledger[key] = rec
            new.append(rec)
    write(ledger)
    return new


def by_number() -> dict[str, list[tuple[str, dict]]]:
    """Historical sanctions as {permit: [(field, item), ...]} for the normalizer."""
    out: dict[str, list[tuple[str, dict]]] = {}
    for rec in load().values():
        out.setdefault(rec["number"], []).append((rec["field"], rec["item"]))
    return out


def main() -> None:
    from normalize import DATA
    records = [json.loads(l) for l in DATA.read_text(encoding="utf-8").splitlines() if l.strip()]
    new = observe(records)
    print(f"sanctions ledger: {len(load())} total, {len(new)} newly recorded")
    for r in new[:20]:
        label = (r["item"].get("noticeLabel") or "").strip()
        print(f"  NEW {r['number']}  {r['field']}  {r['date']}  {label}")


if __name__ == "__main__":
    main()
