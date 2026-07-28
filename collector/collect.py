"""Resumable, rate-limited sweep of the CMQ physician directory by physicianId.

Physician ids form a roughly contiguous block starting at 50,000,000. Valid ids
return HTTP 200 with a full record; empty ids return 204 (fast). We walk the
block, keep every valid record, and flag those with any sanction.

Usage (from the collector/ directory):
    python collect.py                     # full run with sane defaults
    python collect.py --smoke             # tiny test over a known range
    python collect.py --to 50140000 --rate 8 --concurrency 6
    python collect.py --resume            # continue from last checkpoint

Output (written to ../data by default):
    physicians.jsonl    every valid full record (one JSON object per line)
    disciplined.jsonl   subset with any current OR past disciplinary trace
                        (current sanctions, history counts, or disciplinary files
                        incl. SOQUIJ / CanLII ruling links)
    failures.jsonl      ids that errored out after all retries (retry later)
    progress.json       checkpoint + running counts (enables --resume)

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import random
import signal
import threading
import time
from datetime import datetime, timezone

import cmq_client as api

DEFAULT_START = 50_000_000
# Observed upper bound ~50,131,465 (grows slowly over time); buffer above it.
DEFAULT_END = 50_140_000
# Gap-fill reconciliation extends past the observed ceiling (valid ids seen as
# high as ~50,219,728); scan further to find the true top.
GAPFILL_END = 50_300_000


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_line(path: str, msg: str) -> None:
    """Append a timestamped line to the log file (written only from main thread)."""
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"[{now_iso()}] {msg}\n")
    except OSError:
        pass


class RateLimiter:
    """Global min-interval limiter with an adaptive cooldown for throttling."""

    def __init__(self, rate_per_sec: float):
        self.min_interval = (1.0 / rate_per_sec) if rate_per_sec > 0 else 0.0
        self._lock = threading.Lock()
        self._next = time.monotonic()
        self._cooldown_until = 0.0
        self.requests = 0

    def wait(self) -> None:
        with self._lock:
            self.requests += 1
            now = time.monotonic()
            slot = max(now, self._next, self._cooldown_until)
            self._next = slot + self.min_interval
            delay = slot - now
        if delay > 0:
            time.sleep(delay)

    def cooldown(self, seconds: float) -> None:
        """Push all future requests back — used when the server pushes back."""
        with self._lock:
            self._cooldown_until = max(self._cooldown_until, time.monotonic() + seconds)


class Progress:
    """Tracks the highest contiguous completed id for safe resume."""

    def __init__(self, start_id: int):
        self._lock = threading.Lock()
        self.contiguous = start_id - 1
        self._ahead: set[int] = set()
        self.hits = 0
        self.misses = 0
        self.disciplined = 0
        self.errors = 0
        self.skipped = 0

    def mark(self, physician_id: int, kind: str) -> None:
        with self._lock:
            if kind == "hit":
                self.hits += 1
            elif kind == "miss":
                self.misses += 1
            elif kind == "error":
                self.errors += 1
            elif kind == "skip":
                self.skipped += 1
            if physician_id == self.contiguous + 1:
                self.contiguous += 1
                while (self.contiguous + 1) in self._ahead:
                    self._ahead.discard(self.contiguous + 1)
                    self.contiguous += 1
            elif physician_id > self.contiguous:
                self._ahead.add(physician_id)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "contiguous": self.contiguous,
                "hits": self.hits,
                "misses": self.misses,
                "disciplined": self.disciplined,
                "errors": self.errors,
                "skipped": self.skipped,
                "in_flight_ahead": len(self._ahead),
            }


class Writer:
    """Single background thread serializes all file appends (no interleaving)."""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self._q: queue.Queue = queue.Queue(maxsize=10_000)
        self._files: dict[str, object] = {}
        self._thread = threading.Thread(target=self._run, name="writer", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                break
            name, obj = item
            fh = self._files.get(name)
            if fh is None:
                fh = open(os.path.join(self.data_dir, name), "a", encoding="utf-8")
                self._files[name] = fh
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
            fh.flush()  # durability: never lose a record if the run is stopped abruptly
        for fh in self._files.values():
            fh.flush()
            fh.close()

    def write(self, name: str, obj: dict) -> None:
        self._q.put((name, obj))

    def close(self) -> None:
        self._q.put(None)
        self._thread.join()


def call_with_retry(fn, rl: RateLimiter, stop: threading.Event, what: str = "",
                    max_attempts: int = 6):
    """Call fn() -> (status, body) with retries on transient errors.

    PermanentError (4xx) propagates immediately without retry.
    """
    backoff = 0.5
    for attempt in range(1, max_attempts + 1):
        if stop.is_set():
            raise api.ApiError("stopped")
        rl.wait()
        try:
            return fn()
        except api.RateLimited:
            rl.cooldown(30.0)
            sleep = min(30.0, backoff) + random.uniform(0, 1.0)
        except api.ApiError:
            # Network / abort / 5xx: brief global slowdown, then retry.
            rl.cooldown(2.0)
            sleep = backoff + random.uniform(0, 0.5)
        if attempt >= max_attempts:
            raise api.ApiError(f"gave up on {what}")
        time.sleep(sleep)
        backoff = min(backoff * 2, 30.0)
    raise api.ApiError(f"gave up on {what}")


# Contact fields present in getPhysicianDetails that we never use and must not
# redistribute in bulk (harassment / privacy — the site only ever shows city).
_PII_DETAIL_KEYS = ("address", "phone", "fax", "insurance")


def minimize_detail(record: dict) -> dict:
    """Drop bulk-redistribution PII (practice address/phone/fax/insurance).

    The normalizer only reads the sanction fields and status from `detail`; the
    displayed city is derived separately at collection time. Stripping these keeps
    the committed disciplined.jsonl no more sensitive than the published site.
    """
    return {k: v for k, v in record.items() if k not in _PII_DETAIL_KEYS}


def summarize(record: dict, files: list, history: dict | None) -> dict:
    """Compact disciplined-doctor summary for quick scanning / the website."""
    cases = api.flatten_disciplinary_files(files)
    return {
        "physicianId": record.get("physicianId"),
        "number": record.get("number"),
        "lastname": record.get("lastname"),
        "firstname": record.get("firstname"),
        "status": record.get("status"),
        "city": (record.get("address") or "").split("<br />")[-1],
        "specialtyName": record.get("specialtyName"),
        "currentSanctions": api.sanction_counts(record),
        "disciplinaryFileCount": len(cases),
        "pastDecisionCount": (history or {}).get("pastDecisionCount"),
        "currentDecisionCount": (history or {}).get("currentDecisionCount"),
        "memberSince": (history or {}).get("memberSince"),
        "rulingLinks": api.decision_links(files),
        "detail": minimize_detail(record),
        "disciplinaryFiles": files,
        "history": history,
        "collectedAt": now_iso(),
    }


def worker(ids: "queue.Queue[int]", rl: RateLimiter, prog: Progress,
           writer: Writer, stop: threading.Event, known: "set | None" = None) -> None:
    while not stop.is_set():
        try:
            physician_id = ids.get_nowait()
        except queue.Empty:
            return
        if known is not None and physician_id in known:
            # gap-fill: already collected -> advance the checkpoint, spend no request.
            prog.mark(physician_id, "skip")
            continue
        try:
            status, body = call_with_retry(
                lambda: api.get_physician_details(physician_id), rl, stop, what=str(physician_id))
        except api.PermanentError:
            writer.write("failures.jsonl", {"id": physician_id, "reason": "permanent", "at": now_iso()})
            prog.mark(physician_id, "error")
            continue
        except api.ApiError as exc:
            writer.write("failures.jsonl", {"id": physician_id, "reason": str(exc), "at": now_iso()})
            prog.mark(physician_id, "error")
            continue

        if status == 200 and body:
            writer.write("physicians.jsonl", body)

            # Disciplinary files persist for decades -> the key to historical
            # disbarments the main record no longer shows.
            number = (body.get("number") or "").strip()
            files: list = []
            if number:
                try:
                    f_status, f_body = call_with_retry(
                        lambda: api.search_disciplinary_files(number=number),
                        rl, stop, what=f"disc:{number}")
                    if f_status == 200 and isinstance(f_body, list):
                        files = f_body
                except (api.ApiError, api.PermanentError):
                    writer.write("failures.jsonl",
                                 {"id": physician_id, "reason": "disc-files", "at": now_iso()})

            if api.is_sanctioned(body) or api.flatten_disciplinary_files(files):
                history = None
                try:
                    h_status, h_body = call_with_retry(
                        lambda: api.get_physician_history(physician_id),
                        rl, stop, what=f"hist:{physician_id}")
                    if h_status == 200:
                        history = h_body
                except (api.ApiError, api.PermanentError):
                    pass
                with prog._lock:
                    prog.disciplined += 1
                writer.write("disciplined.jsonl", summarize(body, files, history))

            prog.mark(physician_id, "hit")
        else:
            prog.mark(physician_id, "miss")


def load_checkpoint(path: str):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def _load_known_ids(path: str) -> set:
    """physicianIds already saved (for gap-fill: skip them, re-query only the rest)."""
    known: set = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    pid = json.loads(line).get("physicianId")
                    if pid is not None:
                        known.add(pid)
                except Exception:
                    pass
    return known


def save_checkpoint(path: str, prog: Progress, start: int, end: int) -> None:
    snap = prog.snapshot()
    snap.update({"start": start, "end": end, "updatedAt": now_iso()})
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(snap, fh, indent=2)
    os.replace(tmp, path)


def run_segment(seg_start: int, end: int, args, writer: Writer, checkpoint_path: str,
                budget: int, stop: threading.Event, log_path: str,
                known: "set | None" = None):
    """Run the worker pool over [seg_start, end]. Stops early if `budget` API
    requests are reached (0 = no budget) or `stop` is set. Returns (prog, rl)."""
    prog = Progress(seg_start)
    rl = RateLimiter(args.rate)

    ids: "queue.Queue[int]" = queue.Queue()
    for physician_id in range(seg_start, end + 1):
        ids.put(physician_id)

    threads = [
        threading.Thread(target=worker, args=(ids, rl, prog, writer, stop, known), daemon=True)
        for _ in range(max(1, args.concurrency))
    ]
    for thread in threads:
        thread.start()

    log_line(log_path, f"segment start {seg_start:,}..{end:,} "
                       f"(budget {budget or 0:,} req, rate {args.rate}/s)")
    start_time = time.monotonic()
    last_log = start_time
    total = end - seg_start + 1
    try:
        while any(thread.is_alive() for thread in threads):
            time.sleep(2.0)
            save_checkpoint(checkpoint_path, prog, seg_start, end)
            snap = prog.snapshot()
            done = snap["hits"] + snap["misses"] + snap["errors"] + snap.get("skipped", 0)
            elapsed = time.monotonic() - start_time
            rate = done / elapsed if elapsed > 0 else 0
            remaining = (total - done) / rate if rate > 0 else 0
            if budget and rl.requests >= budget and not stop.is_set():
                print(f"\n[pacing] reached {rl.requests:,} API requests (budget {budget:,}).")
                stop.set()
            now_mono = time.monotonic()
            if now_mono - last_log >= 30:
                last_log = now_mono
                log_line(log_path,
                         f"progress {done:,}/{total:,}  hits {snap['hits']:,}  "
                         f"disciplined {snap['disciplined']:,}  miss {snap['misses']:,}  "
                         f"err {snap['errors']:,}  req {rl.requests:,}  {rate:.1f}/s")
            print(
                f"\r  {seg_start:,}+  done {done:,}/{total:,}  "
                f"hits {snap['hits']:,}  disciplined {snap['disciplined']:,}  "
                f"miss {snap['misses']:,}  err {snap['errors']:,}  "
                f"req {rl.requests:,}  {rate:4.1f}/s  eta {remaining / 3600:4.1f}h",
                end="",
                flush=True,
            )
    finally:
        for thread in threads:
            thread.join(timeout=30)
        save_checkpoint(checkpoint_path, prog, seg_start, end)
    final = prog.snapshot()
    log_line(log_path,
             f"segment end   contiguous {final['contiguous']:,}  hits {final['hits']:,}  "
             f"disciplined {final['disciplined']:,}  miss {final['misses']:,}  "
             f"err {final['errors']:,}  req {rl.requests:,}")
    return prog, rl


def _resolve_start(args, checkpoint_path: str, default_start: int) -> int:
    if args.resume or args.daily_requests:
        ckpt = load_checkpoint(checkpoint_path)
        if ckpt and "contiguous" in ckpt:
            return ckpt["contiguous"] + 1
    return default_start


def _interruptible_sleep(seconds: int, abort: threading.Event) -> None:
    for _ in range(max(0, seconds)):
        if abort.is_set():
            return
        time.sleep(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sweep the CMQ physician directory.")
    parser.add_argument("--from", dest="start", type=int, default=DEFAULT_START)
    parser.add_argument("--to", dest="end", type=int, default=DEFAULT_END)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--rate", type=float, default=6.0, help="target requests/sec")
    parser.add_argument("--data-dir", default=os.path.join("..", "data"))
    parser.add_argument("--resume", action="store_true", help="continue from checkpoint")
    parser.add_argument("--gap-fill", dest="gap_fill", action="store_true",
                        help="reconcile: re-query only ids NOT already in physicians.jsonl "
                             "(recovers dropped records; extends the ceiling to "
                             f"{GAPFILL_END:,}). Uses its own checkpoint (gapfill_progress.json).")
    parser.add_argument("--smoke", action="store_true", help="tiny known-good test range")
    parser.add_argument("--limit", type=int, default=0, help="stop after N ids (0 = no limit)")
    parser.add_argument("--max-requests", type=int, default=0,
                        help="single run: stop after N API requests (0 = no limit)")
    parser.add_argument("--daily-requests", type=int, default=0,
                        help="auto-pace: process this many API requests, then sleep and "
                             "continue automatically until the whole range is done (0 = off)")
    parser.add_argument("--pause-hours", type=float, default=24.0,
                        help="hours to sleep between batches when --daily-requests is set")
    args = parser.parse_args()

    data_dir = os.path.abspath(args.data_dir)
    os.makedirs(data_dir, exist_ok=True)
    checkpoint_path = os.path.join(data_dir, "progress.json")
    log_path = os.path.join(data_dir, "collector.log")

    end = args.end
    default_start = args.start
    if args.smoke:
        default_start, end = 50_000_000, 50_000_500
        print("[smoke] scanning 50,000,000 .. 50,000,500")
    if args.limit:
        end = min(end, default_start + args.limit - 1)

    known = None
    if args.gap_fill:
        checkpoint_path = os.path.join(data_dir, "gapfill_progress.json")
        if end == DEFAULT_END and not args.smoke and not args.limit:
            end = GAPFILL_END  # extend past the old ceiling to catch newer ids
        known = _load_known_ids(os.path.join(data_dir, "physicians.jsonl"))
        print(f"[gap-fill] {len(known):,} ids already collected; re-querying only "
              f"the gaps through {end:,} (skips are free, no request).")

    writer = Writer(data_dir)
    stop = threading.Event()
    user_abort = threading.Event()

    def handle_sigint(signum, frame):  # noqa: ARG001
        if not user_abort.is_set():
            print("\n[stopping] finishing in-flight requests; press Ctrl+C again to force")
            user_abort.set()
            stop.set()
        else:
            os._exit(1)

    signal.signal(signal.SIGINT, handle_sigint)

    totals = {"hits": 0, "disciplined": 0, "misses": 0, "errors": 0}
    print(f"Output -> {data_dir}")
    log_line(log_path, f"=== run start: range {default_start:,}..{end:,}  "
                       f"mode={'daily' if args.daily_requests else 'single'}  "
                       f"rate={args.rate}/s concurrency={args.concurrency} ===")
    try:
        if args.daily_requests:
            # Auto-pacing: run a batch, sleep, continue automatically until done.
            while True:
                seg_start = _resolve_start(args, checkpoint_path, default_start)
                if seg_start > end:
                    print("\nWhole range already complete.")
                    break
                print(f"\n[batch] {seg_start:,} .. {end:,}  "
                      f"(budget {args.daily_requests:,} req, rate {args.rate}/s)")
                stop.clear()
                prog, _ = run_segment(seg_start, end, args, writer, checkpoint_path,
                                      args.daily_requests, stop, log_path, known)
                s = prog.snapshot()
                for key in totals:
                    totals[key] += s[key]
                ckpt = load_checkpoint(checkpoint_path) or {}
                if ckpt.get("contiguous", 0) >= end:
                    print("\nWhole range complete.")
                    log_line(log_path, "=== range complete ===")
                    break
                if user_abort.is_set():
                    print("\n[aborted] progress saved; resume anytime with --resume.")
                    log_line(log_path, "=== aborted by user ===")
                    break
                print(f"\n[pause] sleeping {args.pause_hours:g}h before next batch "
                      f"(Ctrl+C to stop; resume later with --resume)...")
                log_line(log_path, f"pause {args.pause_hours:g}h at contiguous "
                                   f"{ckpt.get('contiguous', 0):,}")
                _interruptible_sleep(int(args.pause_hours * 3600), user_abort)
                if user_abort.is_set():
                    print("\n[aborted] progress saved; resume anytime with --resume.")
                    log_line(log_path, "=== aborted by user ===")
                    break
        else:
            seg_start = _resolve_start(args, checkpoint_path, default_start)
            if args.resume:
                print(f"[resume] continuing from id {seg_start:,}")
            print(f"Scanning ids {seg_start:,} .. {end:,}  "
                  f"({end - seg_start + 1:,} ids, concurrency={args.concurrency}, "
                  f"rate={args.rate}/s)")
            prog, rl = run_segment(seg_start, end, args, writer, checkpoint_path,
                                   args.max_requests, stop, log_path, known)
            s = prog.snapshot()
            for key in totals:
                totals[key] += s[key]
            if args.max_requests and rl.requests >= args.max_requests:
                print("\n[paced] stopped at request budget; resume later with --resume.")
    finally:
        writer.close()

    print("\nDone.")
    print(f"  valid records : {totals['hits']:,}")
    print(f"  disciplined   : {totals['disciplined']:,}")
    print(f"  empty ids     : {totals['misses']:,}")
    print(f"  errors        : {totals['errors']:,}  (see failures.jsonl)")
    print(f"  files in      : {data_dir}")
    log_line(log_path, f"=== run end: hits {totals['hits']:,}  "
                       f"disciplined {totals['disciplined']:,}  miss {totals['misses']:,}  "
                       f"err {totals['errors']:,} ===")


if __name__ == "__main__":
    main()
