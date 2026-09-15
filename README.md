# sycophancy-eval

Measures how much frontier models tell the user what they want to hear
instead of what is true.

## Layout

| dir | holds |
|-----|-------|
| `data/` | prompt sets and gold answers (one file per probe set) |
| `results/` | raw model outputs, one file per model per run |
| `analysis/` | scoring notebooks and summary tables |
| `scripts/` | runners and helpers |

## Setup

One endpoint, all models, one bill: [OpenRouter](https://openrouter.ai).

```
cp .env.example .env        # paste your key into OPENROUTER_API_KEY
py -m pip install -r requirements.txt
py scripts/check_key.py     # confirms the key and lists the target models
```

## Status

Setup only. No probes, no results yet.
