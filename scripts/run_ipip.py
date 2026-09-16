"""Manipulation check: administer the IPIP-50 to every persona x model, one item per call.

    py scripts/run_ipip.py --limit 5 --personas none        # smoke test
    py scripts/run_ipip.py                                  # all 50 items x personas x models (resumes)

One item per call at temperature 0 means item order cannot matter. Responses go to
results/ipip/<model_slug>.jsonl, append-only; completed keys are skipped on re-run.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (DATA, RESULTS, Client, FatalAPIError, Recorder, build_ipip_messages,  # noqa: E402
                    get_key, load_done, load_json, load_personas, make_key, now_iso, parse_likert,
                    persona_names, print_tally, run_all, slugify, system_prompt)

DEFAULT_MODELS = ["anthropic/claude-sonnet-5", "openai/gpt-5.2"]
MAX_TOKENS = 200


async def run_one(client: Client, rec: Recorder, done: dict, run_id: str, model: str,
                  persona: str, system: str, item: dict) -> None:
    key = make_key(model, persona, item["id"], "ipip")
    messages = build_ipip_messages(item, system)
    res = await client.chat(model, messages, MAX_TOKENS)
    if res["status"] == "empty":
        res = await client.chat(model, messages, MAX_TOKENS * 2)
    out = {
        "key": key, "run_id": run_id, "ts": now_iso(), "model": model, "persona": persona,
        "item_id": item["id"], "factor": item["factor"], "keyed": item["keyed"], "text": item["text"],
        "messages": messages, **res,
    }
    if out["status"] == "ok":
        out["rating"] = parse_likert(out["content"])
        done[key] = out
    rec.write(out)


async def run_model(args: argparse.Namespace, client: Client, personas: dict, items: list[dict],
                    model: str, position: int) -> None:
    path = RESULTS / "ipip" / f"{slugify(model)}.jsonl"
    done = load_done(path)
    with Recorder(path) as rec:
        todo = [(p, it) for p in args.personas for it in items
                if make_key(model, p, it["id"], "ipip") not in done]
        print(f"{model}: {len(done)} done, {len(todo)} to run")
        tasks = [asyncio.ensure_future(run_one(client, rec, done, args.run_id, model, p,
                                               system_prompt(personas, p, "questionnaire"), it))
                 for p, it in todo]
        await run_all(tasks, desc=slugify(model)[:28], position=position)
        new = [r for r in done.values() if r.get("run_id") == args.run_id]
        parsed = sum(1 for r in new if r.get("rating") is not None)
        print(f"\n{model}: new records {rec.count} | likert parse rate {parsed}/{len(new)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    ap.add_argument("--personas", nargs="+", default=None)
    ap.add_argument("--limit", type=int, default=None, help="first N items only")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--rpm", type=float, default=18.0, help="request starts per minute per model")
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--run-id", default="ipip-01")
    args = ap.parse_args()

    personas = load_personas()
    args.personas = args.personas or persona_names(personas)
    items = load_json(DATA / "ipip50.json")["items"]
    if args.limit:
        items = items[: args.limit]

    client = Client(get_key(), concurrency=args.concurrency, timeout=args.timeout, rpm=args.rpm)

    async def go() -> None:
        try:
            await asyncio.gather(*(run_model(args, client, personas, items, m, i)
                                   for i, m in enumerate(args.models)))
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
