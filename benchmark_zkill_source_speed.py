"""Benchmark local SQLite vs zKill API loading speed for the Zkill tab.

Usage examples:
    python benchmark_zkill_source_speed.py 2113334374
    python benchmark_zkill_source_speed.py "Tsundere Ragnarok"
    python benchmark_zkill_source_speed.py "Tsundere Ragnarok" --runs 3

What it measures:
    - DB kills/losses: direct reads from data/local_intel.sqlite through local_intel_db.py
    - API kills/losses: direct HTTP requests to zkillboard.com API, bypassing app cache

ESI name -> character_id resolving is measured separately and is not included in DB/API totals.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from dataclasses import dataclass
from typing import Any

import requests

from esi_client import get_character_id
from local_intel_db import db_exists, get_db_path, get_recent_kills as db_recent_kills, get_recent_losses as db_recent_losses

USER_AGENT = "EVE-Local-Scanner-Speed-Test"
ZKILL_API = "https://zkillboard.com/api"
TIMEOUT = 12


@dataclass
class BenchResult:
    name: str
    seconds: float
    rows: int
    ok: bool
    error: str = ""


def now() -> float:
    return time.perf_counter()


def timed(name: str, fn) -> BenchResult:
    start = now()
    try:
        data = fn()
        elapsed = now() - start
        rows = len(data) if isinstance(data, list) else 0
        return BenchResult(name=name, seconds=elapsed, rows=rows, ok=True)
    except Exception as exc:
        elapsed = now() - start
        return BenchResult(name=name, seconds=elapsed, rows=0, ok=False, error=str(exc))


def api_get(session: requests.Session, url: str) -> list[dict[str, Any]]:
    response = session.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, list) else []


def resolve_character(value: str) -> tuple[int | None, float]:
    value = str(value).strip()
    if value.isdigit():
        return int(value), 0.0

    start = now()
    character_id = get_character_id(value)
    return character_id, now() - start


def median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def print_result(result: BenchResult) -> None:
    status = "OK" if result.ok else "ERR"
    print(f"{result.name:<24} {result.seconds:>8.3f}s   rows={result.rows:<4}   {status}")
    if result.error:
        print(f"  error: {result.error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare zKill table loading speed from SQLite DB vs zKill API.")
    parser.add_argument("character", help="Character ID or exact character name")
    parser.add_argument("--kills", type=int, default=20, help="How many DB kill rows to read. Default: 20")
    parser.add_argument("--losses", type=int, default=50, help="How many DB loss rows to read. Default: 50")
    parser.add_argument("--runs", type=int, default=3, help="Number of runs. Default: 3")
    args = parser.parse_args()

    character_id, resolve_seconds = resolve_character(args.character)
    if not character_id:
        print(f"Could not resolve character: {args.character}")
        return 2

    print("Base test target")
    print(f"  character: {args.character}")
    print(f"  character_id: {character_id}")
    if resolve_seconds:
        print(f"  ESI resolve time: {resolve_seconds:.3f}s")
    print(f"  DB path: {get_db_path()}")
    print(f"  DB exists: {db_exists()}")
    print()

    session = requests.Session()
    all_results: dict[str, list[BenchResult]] = {
        "DB kills": [],
        "DB losses": [],
        "DB total": [],
        "API kills": [],
        "API losses": [],
        "API total": [],
    }

    for run_no in range(1, max(1, args.runs) + 1):
        print(f"Run {run_no}/{args.runs}")

        db_start = now()
        db_kills = timed("DB kills", lambda: db_recent_kills(character_id, limit=args.kills))
        db_losses = timed("DB losses", lambda: db_recent_losses(character_id, limit=args.losses))
        db_total_seconds = now() - db_start
        db_total = BenchResult("DB total", db_total_seconds, db_kills.rows + db_losses.rows, db_kills.ok and db_losses.ok)

        api_start = now()
        api_kills = timed(
            "API kills",
            lambda: api_get(session, f"{ZKILL_API}/kills/characterID/{character_id}/"),
        )
        api_losses = timed(
            "API losses",
            lambda: api_get(session, f"{ZKILL_API}/losses/characterID/{character_id}/"),
        )
        api_total_seconds = now() - api_start
        api_total = BenchResult("API total", api_total_seconds, api_kills.rows + api_losses.rows, api_kills.ok and api_losses.ok)

        for result in [db_kills, db_losses, db_total, api_kills, api_losses, api_total]:
            all_results[result.name].append(result)
            print_result(result)
        print()

    print("Median summary")
    print(f"{'Source':<24} {'median':>8}   {'rows last':<10} status")
    for name in ["DB kills", "DB losses", "DB total", "API kills", "API losses", "API total"]:
        results = all_results[name]
        seconds = median([r.seconds for r in results])
        last = results[-1] if results else BenchResult(name, 0, 0, False)
        status = "OK" if all(r.ok for r in results) else "HAS ERRORS"
        print(f"{name:<24} {seconds:>8.3f}s   rows={last.rows:<4}   {status}")

    db_total_median = median([r.seconds for r in all_results["DB total"] if r.ok])
    api_total_median = median([r.seconds for r in all_results["API total"] if r.ok])
    print()

    if db_total_median and api_total_median:
        faster = "DB" if db_total_median < api_total_median else "API"
        ratio = max(db_total_median, api_total_median) / max(min(db_total_median, api_total_median), 0.000001)
        print(f"Winner: {faster} is about {ratio:.1f}x faster on this run.")
    else:
        print("Could not calculate winner because one source returned errors.")

    print()
    print("Note: API calls are direct network calls and can be affected by zKill rate limits, internet latency, Cloudflare, and remote cache.")
    print("Note: DB calls measure only local SQLite read speed; if your local DB is outdated, it can be faster but less fresh.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
