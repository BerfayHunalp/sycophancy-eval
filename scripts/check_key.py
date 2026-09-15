"""Verify the OpenRouter key and show what it can reach.

    py scripts/check_key.py                 key info + model counts per provider
    py scripts/check_key.py --list google   every model id under a provider prefix
    py scripts/check_key.py --ping MODEL    one 5-token completion against MODEL
"""
import argparse
import os
import sys

import requests
from dotenv import load_dotenv

BASE = "https://openrouter.ai/api/v1"
PROVIDERS = ("anthropic", "openai", "google")
TIMEOUT_S = 30


def get_key() -> str:
    load_dotenv()
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        sys.exit("OPENROUTER_API_KEY is empty. Copy .env.example to .env and paste the key.")
    return key


def headers(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


def key_info(key: str) -> None:
    r = requests.get(f"{BASE}/auth/key", headers=headers(key), timeout=TIMEOUT_S)
    if r.status_code != 200:
        sys.exit(f"key check failed: HTTP {r.status_code} {r.text[:200]}")
    d = r.json().get("data", {})
    print(f"key      {d.get('label', '?')}")
    print(f"usage    ${d.get('usage', 0):.4f}")
    print(f"limit    {d.get('limit') if d.get('limit') is not None else 'none'}")


def model_ids(key: str) -> list[str]:
    r = requests.get(f"{BASE}/models", headers=headers(key), timeout=TIMEOUT_S)
    r.raise_for_status()
    return sorted(m["id"] for m in r.json().get("data", []))


def summarise(ids: list[str]) -> None:
    print(f"models   {len(ids)} reachable")
    for p in PROVIDERS:
        n = sum(1 for i in ids if i.startswith(p + "/"))
        print(f"  {p:<10}{n}")


def ping(key: str, model: str) -> None:
    body = {
        "model": model,
        "max_tokens": 5,
        "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
    }
    r = requests.post(f"{BASE}/chat/completions", headers=headers(key), json=body, timeout=TIMEOUT_S)
    if r.status_code != 200:
        sys.exit(f"ping {model} failed: HTTP {r.status_code} {r.text[:300]}")
    text = r.json()["choices"][0]["message"]["content"].strip()
    print(f"ping     {model} -> {text!r}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", metavar="PREFIX", help="print model ids under this provider prefix")
    ap.add_argument("--ping", metavar="MODEL", help="send one tiny completion to MODEL")
    args = ap.parse_args()

    key = get_key()
    key_info(key)
    ids = model_ids(key)
    if args.list:
        for i in ids:
            if i.startswith(args.list.rstrip("/") + "/"):
                print(i)
    else:
        summarise(ids)
    if args.ping:
        ping(key, args.ping)


if __name__ == "__main__":
    main()
