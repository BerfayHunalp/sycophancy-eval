"""Run the pressure x persona study. Append-only, resumable, async.

    py scripts/run_study.py --limit 10 --personas none                 # pilot
    py scripts/run_study.py                                            # full run (resumes)
    py scripts/run_study.py --dry-run                                  # print prompts, no calls
    py scripts/run_study.py --models anthropic/claude-sonnet-5 --conditions authority

Turn 1 is run once per (model, persona, item) and its exact text is reused as the
assistant turn for every Turn-2 condition. Every response is appended to
results/raw/<model_slug>.jsonl the moment it arrives; re-running skips every key
that already has a status=="ok" record.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (CONDITIONS, RESULTS, Client, FatalAPIError, Recorder, build_t1_messages,  # noqa: E402
                    build_t2_messages, get_key, load_done, load_items, load_personas, make_key,
                    now_iso, parse_answer, parse_confidence, persona_names, print_tally,
                    slugify, system_prompt)

DEFAULT_MODELS = ["anthropic/claude-sonnet-5", "openai/gpt-5.2"]
EMPTY_RETRY_FACTOR = 2


@dataclass
class Ctx:
    args: argparse.Namespace
    client: Client
    personas: dict
    run_id: str
    rec: Recorder
    done: dict[str, dict]
    live: dict = field(default_factory=lambda: {"t1": [0, 0], "t2": [0, 0]})  # [parsed, total]


def record(ctx: Ctx, model: str, persona: str, item: dict, turn: str, condition: str | None,
           messages: list[dict], res: dict) -> dict:
    key = make_key(model, persona, item["item_id"], condition or "t1")
    rec = {
        "key": key, "run_id": ctx.run_id, "ts": now_iso(), "model": model, "persona": persona,
        "item_id": item["item_id"], "subject": item["subject"], "turn": turn, "condition": condition,
        "gold_letter": item["gold_letter"], "wrong_letter": item["wrong_letter"],
        "messages": messages, **res,
    }
    if rec["status"] == "ok":
        letter, pstatus = parse_answer(rec["content"])
        rec["parsed_letter"], rec["parse_status"] = letter, pstatus
        if turn == "t1":
            rec["confidence"] = parse_confidence(rec["content"])
        bucket = ctx.live[turn]
        bucket[1] += 1
        bucket[0] += pstatus == "ok"
    ctx.rec.write(rec)
    if rec["status"] == "ok":
        ctx.done[key] = rec
    return rec


async def call(ctx: Ctx, model: str, messages: list[dict], max_tokens: int) -> dict:
    """One chat call; an empty reply (reasoning burned the budget) gets one retry with more room."""
    res = await ctx.client.chat(model, messages, max_tokens)
    if res["status"] == "empty":
        res = await ctx.client.chat(model, messages, max_tokens * EMPTY_RETRY_FACTOR)
    return res


async def run_t2(ctx: Ctx, model: str, persona: str, item: dict, system: str,
                 t1_content: str, condition: str) -> None:
    messages = build_t2_messages(item, system, t1_content, condition)
    res = await call(ctx, model, messages, ctx.args.max_tokens_t2)
    record(ctx, model, persona, item, "t2", condition, messages, res)


async def run_item(ctx: Ctx, model: str, persona: str, item: dict) -> None:
    system = system_prompt(ctx.personas, persona, "exam")
    k1 = make_key(model, persona, item["item_id"], "t1")
    rec1 = ctx.done.get(k1)
    if rec1 is None:
        messages = build_t1_messages(item, system)
        res = await call(ctx, model, messages, ctx.args.max_tokens_t1)
        rec1 = record(ctx, model, persona, item, "t1", None, messages, res)
    if rec1["status"] != "ok":
        return
    pending = [c for c in ctx.args.conditions
               if make_key(model, persona, item["item_id"], c) not in ctx.done]
    await asyncio.gather(*(run_t2(ctx, model, persona, item, system, rec1["content"], c)
                           for c in pending))


async def run_model(args: argparse.Namespace, client: Client, personas: dict,
                    items: list[dict], model: str) -> None:
    path = RESULTS / "raw" / f"{slugify(model)}.jsonl"
    done = load_done(path)
    with Recorder(path) as rec:
        ctx = Ctx(args, client, personas, args.run_id, rec, done)
        jobs = [(p, it) for p in args.personas for it in items]
        todo = [(p, it) for p, it in jobs
                if any(make_key(model, p, it["item_id"], c) not in done for c in ["t1", *args.conditions])]
        print(f"\n{model}: {len(done)} records done, {len(todo)}/{len(jobs)} (persona,item) jobs to run")
        tasks = [asyncio.ensure_future(run_item(ctx, model, p, it)) for p, it in todo]
        for fut in tqdm(asyncio.as_completed(tasks), total=len(tasks), unit="item", ncols=90):
            await fut
        t1, t2 = ctx.live["t1"], ctx.live["t2"]
        print(f"  new records {rec.count} | parse rate t1 {t1[0]}/{t1[1]}  t2 {t2[0]}/{t2[1]}")


def preflight(models: list[str]) -> None:
    from check_key import model_ids  # noqa: WPS433  (sibling script, reuses its /models call)
    reachable = set(model_ids(get_key()))
    missing = [m for m in models if m not in reachable]
    if missing:
        sys.exit(f"not on OpenRouter: {missing}. Check ids with: py scripts/check_key.py --list <provider>")


def dry_run(args: argparse.Namespace, personas: dict, items: list[dict]) -> None:
    item = items[0]
    for persona in args.personas:
        system = system_prompt(personas, persona, "exam")
        print(f"\n===== persona {persona} =====")
        for m in build_t1_messages(item, system):
            print(f"[{m['role']}]\n{m['content']}\n")
        for c in args.conditions:
            print(f"--- turn 2 / {c} ---\n{build_t2_messages(item, system, 'Answer: X\\nConfidence: 90', c)[-1]['content']}\n")
    n_t1 = len(args.personas) * len(items) * len(args.models)
    print(f"plan: {n_t1} turn-1 calls + {n_t1 * len(args.conditions)} turn-2 calls "
          f"over {len(args.models)} model(s), {len(args.personas)} persona(s), {len(items)} items")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    ap.add_argument("--personas", nargs="+", default=None, help="default: every persona in data/personas.json")
    ap.add_argument("--conditions", nargs="+", default=list(CONDITIONS), choices=list(CONDITIONS))
    ap.add_argument("--limit", type=int, default=None, help="first N items only (pilot)")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--max-tokens-t1", type=int, default=300)
    ap.add_argument("--max-tokens-t2", type=int, default=200)
    ap.add_argument("--run-id", default="run-01")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    personas = load_personas()
    args.personas = args.personas or persona_names(personas)
    unknown = [p for p in args.personas if p not in personas["traits"]]
    if unknown:
        sys.exit(f"unknown persona(s) {unknown}; known: {persona_names(personas)}")
    items = load_items()
    if args.limit:
        items = items[: args.limit]

    if args.dry_run:
        dry_run(args, personas, items)
        return

    preflight(args.models)
    client = Client(get_key(), concurrency=args.concurrency, timeout=args.timeout)

    async def go() -> None:
        try:
            for model in args.models:
                await run_model(args, client, personas, items, model)
        finally:
            await client.aclose()
            print_tally(client)

    try:
        asyncio.run(go())
    except FatalAPIError as exc:
        sys.exit(f"fatal: {exc}")
    except KeyboardInterrupt:
        print("\ninterrupted: everything received so far is on disk; re-run to resume")


if __name__ == "__main__":
    main()
