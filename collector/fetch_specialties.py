"""Fetch the CMQ specialty list in French and English and build a fr->en map.

Specialty IDs are stable across languages, so we join on specialtyId. The output
(specialties_fr_en.json) is a small public reference map (not personal data) that
normalize.py uses to attach English specialty names. Re-runnable in the weekly
pipeline; specialties change rarely.

Usage: python fetch_specialties.py
"""
from __future__ import annotations

import json
from pathlib import Path

import cmq_client as api

OUT = Path(__file__).resolve().parent / "specialties_fr_en.json"


def main() -> None:
    fr = api.get_specialties("fr")
    en = api.get_specialties("en")
    en_by_id = {s["specialtyId"]: (s.get("specialtyName") or "").strip() for s in en}

    mapping: dict[str, str] = {}
    for s in fr:
        fr_name = (s.get("specialtyName") or "").strip()
        en_name = en_by_id.get(s["specialtyId"], "")
        if fr_name and en_name:
            mapping[fr_name] = en_name

    OUT.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(f"wrote {OUT} ({len(mapping)} specialties)")


if __name__ == "__main__":
    main()
