"""Stage 2: bulk-fetch CMQ disciplinary decision PDFs and extract their text.

Reads every decision with a real documentId (> 0) from disciplined.jsonl, then
downloads each PDF once (skipping any already cached), extracts its text with
pypdf, and records a manifest line so the normalizer can later join the text
onto the right doctor/case.

Politeness: paced with --rate (requests/sec) and an optional --max-requests cap
for a single daily run. Fetching is idempotent — re-running resumes, because a
PDF already on disk (or listed in the manifest) is skipped.

Storage model: PDFs are a LOCAL CACHE (data/decisions/{id}.pdf), not committed to
the main tree; the extracted {id}.txt is what the site pipeline consumes. The
manifest (decisions_index.jsonl) is the tracking record: documentId -> permit,
case, dates, sizes, fetch time.

Usage:
    python fetch_decisions.py                      # fetch all missing, paced
    python fetch_decisions.py --max-requests 200   # cap a daily run
    python fetch_decisions.py --ids 438 406        # fetch specific documentIds
    python fetch_decisions.py --list               # just report what's pending
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import cmq_client as api

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DISCIPLINED = DATA / "disciplined.jsonl"
OUT_DIR = DATA / "decisions"
MANIFEST = DATA / "decisions_index.jsonl"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_text(pdf_bytes: bytes) -> str | None:
    # Prefer pypdfium2 (Google's PDFium; Apache-2.0/BSD) - far cleaner word
    # spacing than pypdf, which mangles ligatures ("en viron" vs "environ").
    try:
        import pypdfium2 as pdfium  # type: ignore
        pdf = pdfium.PdfDocument(pdf_bytes)
        try:
            parts = []
            for i in range(len(pdf)):
                parts.append(pdf[i].get_textpage().get_text_range())
            return "\n".join(parts)
        finally:
            pdf.close()
    except ImportError:
        pass
    except Exception:  # noqa: BLE001 - fall back to pypdf on any pdfium error
        pass
    # Fallback: pypdf / PyPDF2.
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            return None
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def collect_targets() -> list[dict]:
    """Unique decisions with documentId > 0, with joinable context for the manifest."""
    seen: dict[int, dict] = {}
    with open(DISCIPLINED, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            permit = rec.get("number")
            for entry in rec.get("disciplinaryFiles") or []:
                for case in entry.get("items") or []:
                    for dec in case.get("decisions") or []:
                        doc_id = dec.get("documentId")
                        if isinstance(doc_id, int) and doc_id > 0 and doc_id not in seen:
                            seen[doc_id] = {
                                "documentId": doc_id,
                                "permit": permit,
                                "case": case.get("number"),
                                "decisionDate": (dec.get("date") or "")[:10] or None,
                            }
    return list(seen.values())


def load_done() -> set[int]:
    done: set[int] = set()
    if MANIFEST.exists():
        with open(MANIFEST, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        done.add(json.loads(line)["documentId"])
                    except (KeyError, json.JSONDecodeError):
                        pass
    # A PDF already on disk counts as done even if the manifest was lost.
    for pdf in OUT_DIR.glob("*.pdf"):
        try:
            done.add(int(pdf.stem))
        except ValueError:
            pass
    return done


def fetch_one(doc_id: int, retries: int = 4) -> bytes:
    backoff = 1.0
    for attempt in range(1, retries + 1):
        try:
            b64 = api.get_decision_document_b64(doc_id)
            if not b64 or not b64.strip():
                raise api.ApiError("empty response")
            pdf = base64.b64decode(b64)
            if len(pdf) < 100 or pdf[:4] != b"%PDF":
                raise api.ApiError("not a PDF payload")
            return pdf
        except Exception as exc:  # noqa: BLE001 - transient network/decode
            if attempt >= retries:
                raise
            time.sleep(backoff)
            backoff = min(backoff * 2, 20.0)
    raise api.ApiError(f"gave up on {doc_id}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rate", type=float, default=2.0, help="requests per second")
    ap.add_argument("--max-requests", type=int, default=0, help="stop after N fetches (0 = no cap)")
    ap.add_argument("--ids", type=int, nargs="*", help="fetch only these documentIds")
    ap.add_argument("--list", action="store_true", help="report pending count and exit")
    ap.add_argument("--reextract", action="store_true",
                    help="re-run text extraction on cached PDFs (no download)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.reextract:
        pdfs = sorted(OUT_DIR.glob("*.pdf"))
        done = 0
        for p in pdfs:
            text = extract_text(p.read_bytes())
            if text is not None:
                (OUT_DIR / f"{p.stem}.txt").write_text(text, encoding="utf-8")
                done += 1
        print(f"re-extracted text for {done}/{len(pdfs)} cached PDFs")
        return
    targets = collect_targets()
    by_id = {t["documentId"]: t for t in targets}

    if args.ids:
        pending = [by_id.get(i, {"documentId": i, "permit": None, "case": None, "decisionDate": None})
                   for i in args.ids]
    else:
        done = load_done()
        pending = [t for t in targets if t["documentId"] not in done]

    print(f"decisions total: {len(targets)}  pending: {len(pending)}")
    if args.list:
        return
    if not pending:
        print("nothing to fetch.")
        return

    delay = 1.0 / args.rate if args.rate > 0 else 0.0
    fetched = failed = 0
    with open(MANIFEST, "a", encoding="utf-8") as man:
        for i, target in enumerate(pending, 1):
            if args.max_requests and fetched >= args.max_requests:
                print(f"reached --max-requests {args.max_requests}; stopping.")
                break
            doc_id = target["documentId"]
            try:
                pdf = fetch_one(doc_id)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"  [{i}/{len(pending)}] doc {doc_id} FAILED: {exc}")
                man.write(json.dumps({**target, "error": str(exc), "at": now_iso()},
                                     ensure_ascii=False) + "\n")
                man.flush()
                time.sleep(delay)
                continue

            (OUT_DIR / f"{doc_id}.pdf").write_bytes(pdf)
            text = extract_text(pdf)
            chars = 0
            if text is not None:
                (OUT_DIR / f"{doc_id}.txt").write_text(text, encoding="utf-8")
                chars = len(text)

            fetched += 1
            man.write(json.dumps({**target, "pdfBytes": len(pdf), "textChars": chars,
                                  "at": now_iso()}, ensure_ascii=False) + "\n")
            man.flush()
            print(f"  [{i}/{len(pending)}] doc {doc_id} -> {len(pdf):,} bytes, {chars:,} chars")
            time.sleep(delay)

    print(f"done. fetched {fetched}, failed {failed}.")


if __name__ == "__main__":
    main()
