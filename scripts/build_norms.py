"""Human norms for the IPIP-50 from the Open Psychometrics IPIP-FFM sample (1,015,342 responses).

    py scripts/build_norms.py            -> data/ipip_norms.json

Needs data/norms/IPIP-FFM-data-8Nov2018.zip, downloaded from
https://openpsychometrics.org/_rawdata/IPIP-FFM-data-8Nov2018.zip (151 MB, gitignored).

Cleaning: one record per IP address (IPC == 1) and no missing item (a 0 response).
Scoring: for each factor, the mean of its 10 items after reversing minus-keyed items
(6 - x), i.e. exactly how the personas' answers are scored in analyze.py.
Caveat recorded in the output: this sample rated items on Disagree(1)..Agree(5)
while the personas rate accuracy (Very Inaccurate..Very Accurate); same 5-point
structure, different anchor wording.
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, ipip_statement, load_json  # noqa: E402

ZIP = DATA / "norms" / "IPIP-FFM-data-8Nov2018.zip"
OUT = DATA / "ipip_norms.json"
CSV_MEMBER = "IPIP-FFM-data-8Nov2018/data-final.csv"
CODEBOOK_MEMBER = "IPIP-FFM-data-8Nov2018/codebook.txt"
CODE_TO_FACTOR = {"EXT": "E", "EST": "N", "AGR": "A", "CSN": "C", "OPN": "O"}
ITEM_RE = re.compile(r"^(EXT|EST|AGR|CSN|OPN)(\d+)\t(.+?)\s*$")


def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("’", "'").strip().lower())


def read_codebook(zf: zipfile.ZipFile) -> dict[str, str]:
    """{'EXT1': 'I am the life of the party.', ...}"""
    text = zf.read(CODEBOOK_MEMBER).decode("utf-8", errors="replace")
    codes = {}
    for line in text.splitlines():
        m = ITEM_RE.match(line)
        if m:
            codes[f"{m.group(1)}{m.group(2)}"] = m.group(3)
    if len(codes) != 50:
        sys.exit(f"codebook parse found {len(codes)} items, expected 50")
    return codes


def keyed_by_code(codes: dict[str, str]) -> dict[str, int]:
    """Match each dataset item to our ipip50.json item by statement text to inherit its +/- key."""
    ours = {norm_text(ipip_statement(it["text"])): it for it in load_json(DATA / "ipip50.json")["items"]}
    keyed: dict[str, int] = {}
    for code, text in codes.items():
        it = ours.get(norm_text(text))
        if it is None:
            sys.exit(f"no IPIP item matches dataset text {text!r} ({code})")
        if CODE_TO_FACTOR[code[:3]] != it["factor"]:
            sys.exit(f"factor mismatch for {code}: dataset {code[:3]} vs ours {it['factor']}")
        keyed[code] = it["keyed"]
    return keyed


def load_clean(zf: zipfile.ZipFile, codes: list[str]) -> pd.DataFrame:
    with zf.open(CSV_MEMBER) as fh:
        df = pd.read_csv(fh, sep="\t", usecols=codes + ["IPC"], dtype="float32", na_values=["NULL"])
    n0 = len(df)
    df = df[df["IPC"] == 1].drop(columns="IPC")
    df = df[(df > 0).all(axis=1)]  # 0 = item not answered
    print(f"rows: {n0} raw -> {len(df)} after IPC==1 and complete responses")
    return df


def main() -> None:
    if not ZIP.exists():
        sys.exit(f"missing {ZIP}; download it from https://openpsychometrics.org/_rawdata/IPIP-FFM-data-8Nov2018.zip")
    with zipfile.ZipFile(ZIP) as zf:
        codes = read_codebook(zf)
        keyed = keyed_by_code(codes)
        df = load_clean(zf, list(codes))

    scored = pd.DataFrame({c: (df[c] if keyed[c] == 1 else 6 - df[c]) for c in codes})
    factors: dict[str, dict] = {}
    for prefix, factor in CODE_TO_FACTOR.items():
        cols = [c for c in codes if c.startswith(prefix)]
        score = scored[cols].mean(axis=1)
        factors[factor] = {"mean": round(float(score.mean()), 4), "sd": round(float(score.std(ddof=1)), 4),
                           "n": int(len(score)), "items": cols}
        print(f"{factor}: mean {factors[factor]['mean']:.3f}  sd {factors[factor]['sd']:.3f}")

    payload = {
        "source": "Open Psychometrics IPIP-FFM data, collected 2016-2018, file IPIP-FFM-data-8Nov2018.zip",
        "cleaning": "IPC == 1 and all 50 items answered (no 0)",
        "scoring": "factor = mean of 10 items on 1-5 after reversing minus-keyed items (6 - x)",
        "anchor_caveat": "sample used Disagree(1)-Neutral(3)-Agree(5); personas use IPIP accuracy anchors",
        "items": {code: {"text": codes[code], "keyed": keyed[code], "factor": CODE_TO_FACTOR[code[:3]],
                         "mean": round(float(df[code].mean()), 4)} for code in codes},
        "factors": factors,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {OUT.relative_to(DATA.parent)}")


if __name__ == "__main__":
    main()
