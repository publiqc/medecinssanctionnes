"""Fetch a CMQ disciplinary decision document (PDF) by its documentId.

The API method `getDisciplinaryDecisionDocument` returns the PDF as base64 text.
This downloads it server-side (no browser), decodes it, saves the PDF, and tries
to extract text so we can read details like a radiation period.

Usage:
    python fetch_decision.py 406 378 492
"""

from __future__ import annotations

import base64
import os
import sys

import cmq_client as api

OUT_DIR = os.path.abspath(os.path.join("..", "data", "decisions"))


def fetch(document_id: int) -> bytes:
    text = api.get_decision_document_b64(document_id)
    if not text:
        raise RuntimeError(f"no document for id {document_id}")
    return base64.b64decode(text)


def extract_text(pdf_bytes: bytes) -> str | None:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            return None
    import io

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def main(argv: list[str]) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    for arg in argv:
        doc_id = int(arg)
        pdf = fetch(doc_id)
        path = os.path.join(OUT_DIR, f"{doc_id}.pdf")
        with open(path, "wb") as fh:
            fh.write(pdf)
        print(f"saved {path} ({len(pdf):,} bytes)")
        text = extract_text(pdf)
        if text is None:
            print("  (no PDF text extractor installed; run: python -m pip install pypdf)")
            continue
        txt_path = os.path.join(OUT_DIR, f"{doc_id}.txt")
        with open(txt_path, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"  text -> {txt_path} ({len(text):,} chars)")


if __name__ == "__main__":
    main(sys.argv[1:] or ["406"])
