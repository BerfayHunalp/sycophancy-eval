"""Build the 100-item MMLU set, stratified across subjects, with a fixed wrong option.

    py scripts/build_items.py                 -> data/items.jsonl  (seed 20260916, n=100)
    py scripts/build_items.py --refresh       re-download the HF cache
    py scripts/build_items.py --seed 1 --n 20 smaller/other draw (pilot experiments only)

Source: cais/mmlu, config "all", split "test" (14,042 rows). Default route is the
dataset's single parquet export on the HuggingFace Hub (one 3.5 MB download);
`--via-api` pages through the datasets-server REST API instead (100 rows per page,
rate-limited). Either way the rows are cached to data/mmlu_test_all.jsonl
(gitignored) with their dataset row index, so the draw is reproducible offline.
"""
import argparse
import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "mmlu_test_all.jsonl"
PARQUET = ROOT / "data" / "mmlu_test_all.parquet"
OUT = ROOT / "data" / "items.jsonl"
PARQUET_URL = "https://huggingface.co/datasets/cais/mmlu/resolve/main/all/test-00000-of-00001.parquet"
ROWS_URL = "https://datasets-server.huggingface.co/rows"
PAGE = 100
PAGE_PAUSE_S = 0.4
LETTERS = "ABCD"
DEFAULT_SEED = 20260916
DEFAULT_N = 100
MAX_ATTEMPTS = 6
TIMEOUT_S = 60


def _get(params: dict) -> dict:
    """GET one page with exponential backoff on 429/5xx and transport errors."""
    delay = 1.0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = requests.get(ROWS_URL, params=params, timeout=TIMEOUT_S)
            if r.status_code == 200:
                return r.json()
            if r.status_code not in (408, 429, 500, 502, 503, 504):
                sys.exit(f"HF datasets-server HTTP {r.status_code}: {r.text[:200]}")
            retry_after = r.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                delay = max(delay, float(retry_after))
        except requests.RequestException as exc:  # network hiccup: retry
            if attempt == MAX_ATTEMPTS:
                raise
            print(f"  retry {attempt}: {exc.__class__.__name__}", file=sys.stderr)
        time.sleep(delay)
        delay = min(delay * 2, 60)
    sys.exit("HF datasets-server: gave up after retries")


def fetch_all_rows_api() -> list[dict]:
    """Fallback: page through the whole test split via the datasets-server API."""
    first = _get({"dataset": "cais/mmlu", "config": "all", "split": "test", "offset": 0, "length": PAGE})
    total = first["num_rows_total"]
    rows = list(first["rows"])
    print(f"fetching {total} rows in pages of {PAGE} via datasets-server ...")
    for offset in range(PAGE, total, PAGE):
        time.sleep(PAGE_PAUSE_S)
        page = _get({"dataset": "cais/mmlu", "config": "all", "split": "test", "offset": offset, "length": PAGE})
        rows.extend(page["rows"])
        if (offset // PAGE) % 20 == 0:
            print(f"  {len(rows)}/{total}")
    if len(rows) != total:
        sys.exit(f"expected {total} rows, got {len(rows)}")
    return [{"row_idx": r["row_idx"], **r["row"]} for r in rows]


def fetch_all_rows_parquet() -> list[dict]:
    """Default: one download of the Hub's parquet export; row_idx = position in the file."""
    if not PARQUET.exists():
        print(f"downloading {PARQUET_URL} ...")
        with requests.get(PARQUET_URL, stream=True, timeout=TIMEOUT_S) as r:
            r.raise_for_status()
            PARQUET.parent.mkdir(parents=True, exist_ok=True)
            with PARQUET.open("wb") as fh:
                for chunk in r.iter_content(1 << 16):
                    fh.write(chunk)
    df = pd.read_parquet(PARQUET)
    expected = {"question", "subject", "choices", "answer"}
    if not expected <= set(df.columns):
        sys.exit(f"parquet columns {list(df.columns)} lack {expected}")
    return [
        {"row_idx": int(i), "question": str(r.question), "subject": str(r.subject),
         "choices": [str(c) for c in r.choices], "answer": int(r.answer)}
        for i, r in enumerate(df.itertuples(index=False))
    ]


def load_rows(refresh: bool, via_api: bool) -> list[dict]:
    if CACHE.exists() and not refresh:
        with CACHE.open(encoding="utf-8") as fh:
            return [json.loads(line) for line in fh]
    rows = fetch_all_rows_api() if via_api else fetch_all_rows_parquet()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with CACHE.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"cached {len(rows)} rows -> {CACHE.relative_to(ROOT)}")
    return rows


def validate(row: dict) -> bool:
    return (
        isinstance(row.get("choices"), list)
        and len(row["choices"]) == 4
        and isinstance(row.get("answer"), int)
        and 0 <= row["answer"] <= 3
        and all(str(c).strip() for c in row["choices"])
        and str(row.get("question", "")).strip() != ""
    )


def stratify(rows: list[dict], n: int, seed: int) -> list[dict]:
    """One seeded pick per subject, then extra picks from a seeded shuffle of subjects.

    Deterministic given (rows order by row_idx, seed).
    """
    rng = random.Random(seed)
    by_subject: dict[str, list[dict]] = defaultdict(list)
    for r in sorted(rows, key=lambda x: x["row_idx"]):
        if validate(r):
            by_subject[r["subject"]].append(r)
    subjects = sorted(by_subject)
    if n < len(subjects):
        sys.exit(f"n={n} is smaller than the number of subjects ({len(subjects)})")
    picked: list[dict] = []
    used: set[int] = set()
    for s in subjects:
        pool = [r for r in by_subject[s] if r["row_idx"] not in used]
        choice = rng.choice(pool)
        picked.append(choice)
        used.add(choice["row_idx"])
    extra_subjects = subjects[:]
    rng.shuffle(extra_subjects)
    for s in extra_subjects[: n - len(subjects)]:
        pool = [r for r in by_subject[s] if r["row_idx"] not in used]
        choice = rng.choice(pool)
        picked.append(choice)
        used.add(choice["row_idx"])
    return picked


def pick_wrong(row: dict, rng: random.Random) -> str:
    """Seeded uniform pick among the three non-gold letters."""
    gold = LETTERS[row["answer"]]
    return rng.choice([c for c in LETTERS if c != gold])


def to_item(row: dict, wrong: str, seed: int) -> dict:
    return {
        "item_id": f"mmlu-{row['row_idx']}",
        "subject": row["subject"],
        "question": row["question"].strip(),
        "choices": [str(c).strip() for c in row["choices"]],
        "gold_letter": LETTERS[row["answer"]],
        "wrong_letter": wrong,
        "seed": seed,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--n", type=int, default=DEFAULT_N)
    ap.add_argument("--refresh", action="store_true", help="re-download the HF cache")
    ap.add_argument("--via-api", action="store_true", help="page through datasets-server instead of the parquet export")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    rows = load_rows(args.refresh, args.via_api)
    picked = stratify(rows, args.n, args.seed)
    rng = random.Random(args.seed + 1)  # separate stream so wrong letters don't shift the draw
    items = [to_item(r, pick_wrong(r, rng), args.seed) for r in picked]

    assert len(items) == args.n, len(items)
    assert len({i["item_id"] for i in items}) == args.n, "duplicate items"
    assert all(i["wrong_letter"] != i["gold_letter"] for i in items)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for i in items:
            fh.write(json.dumps(i, ensure_ascii=False) + "\n")
    subjects = {i["subject"] for i in items}
    print(f"wrote {len(items)} items across {len(subjects)} subjects -> {out}")
    print("gold letters:", {L: sum(i['gold_letter'] == L for i in items) for L in LETTERS})
    print("wrong letters:", {L: sum(i['wrong_letter'] == L for i in items) for L in LETTERS})


if __name__ == "__main__":
    main()
