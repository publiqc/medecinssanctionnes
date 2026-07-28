"""Inspect a single doctor's raw record: decisions, documentIds, links, notices."""
import json
import re
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "disciplined.jsonl"
OUT = Path(__file__).resolve().parent / "inspect_one.txt"

target = sys.argv[1] if len(sys.argv) > 1 else "87296"


def main():
    rec = None
    with open(DATA, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if str(r.get("number")) == target:
                rec = r
                break
    out = open(OUT, "w", encoding="utf-8")

    def p(*a):
        print(*a, file=out)

    if rec is None:
        p(f"no record with number {target}")
        out.close()
        print("done")
        return

    p(f"number={rec.get('number')} name={rec.get('firstname')} {rec.get('lastname')}")
    p(f"status={rec.get('status')!r}")
    p(f"disciplinaryFileCount={rec.get('disciplinaryFileCount')}")
    p(f"pastDecisionCount={rec.get('pastDecisionCount')} currentDecisionCount={rec.get('currentDecisionCount')}")

    detail = rec.get("detail") or {}
    for field in ("strikingOffTheRoll", "suspensions", "revocations", "restrictions", "commitments"):
        v = detail.get(field) or {}
        items = v.get("items") or []
        if items:
            p(f"\n[detail.{field}] {len(items)} item(s)")
            for it in items:
                desc = (it.get("noticeDescription") or "").replace("<br />", " ")
                p(f"  label={it.get('noticeLabel')!r} date={it.get('date')}")
                p(f"  noticeDescription: {desc[:400]}")

    p("\n[disciplinaryFiles]")
    for entry in rec.get("disciplinaryFiles") or []:
        for c in entry.get("items") or []:
            p(f"  case={c.get('number')} result={c.get('result')!r} complaintReason={c.get('complaintReason')!r}")
            for d in c.get("decisions") or []:
                p(f"    decision documentId={d.get('documentId')} date={d.get('date')} "
                  f"resultDescription={d.get('resultDescription')!r}")
                p(f"      linkQuebec={d.get('linkQuebec')!r}")
                p(f"      linkCanada={d.get('linkCanada')!r}")

    out.close()
    print("wrote", OUT)


if __name__ == "__main__":
    main()
