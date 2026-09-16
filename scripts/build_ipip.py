"""Parse the public-domain IPIP Big Five Factor Markers (50-item version) into data/ipip50.json.

    py scripts/build_ipip.py

Source page: https://ipip.ori.org/newBigFive5broadKey.htm . Each factor has a
"10-item scale" block followed by a "20-item scale" block; we keep the 10-item
blocks. Items are keyed "+" or "-" and may wrap over two lines on the page.
"""
import html
import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "ipip50.json"
URL = "https://ipip.ori.org/newBigFive5broadKey.htm"
TIMEOUT_S = 30

# The page labels factors by Roman numeral: I Surgency/Extraversion, II Agreeableness,
# III Conscientiousness, IV Emotional Stability, V Intellect/Imagination.
ROMAN_TO_FACTOR = {"i": "E", "ii": "A", "iii": "C", "iv": "N", "v": "O"}
FACTOR_NAMES = {"E": "Extraversion", "A": "Agreeableness", "C": "Conscientiousness",
                "N": "Emotional Stability", "O": "Intellect/Imagination"}


def page_lines(html_text: str) -> list[str]:
    text = html.unescape(re.sub(r"<[^>]+>", "\n", html_text))
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.splitlines()]
    return [l for l in lines if l]


def parse(lines: list[str]) -> list[dict]:
    """Walk the page: factor header -> first 'scale (Alpha' block = 10-item scale -> +/- keyed items.

    The '10-item' prefix is sometimes split onto its own line, so any 'scale (Alpha'
    line that is not the 20-item one opens the block.
    """
    items: list[dict] = []
    factor = None
    in_block = False
    key = None
    buf = ""
    for line in lines:
        low = line.lower()
        m = re.match(r"^factor\s+(i{1,3}|iv|v)\b", low)
        if m:
            factor, in_block, key, buf = ROMAN_TO_FACTOR[m.group(1)], False, None, ""
            continue
        if "scale (alpha" in low:
            in_block = not low.startswith("20-item")
            key, buf = None, ""
            continue
        if not in_block or factor is None:
            continue
        if re.match(r"^\+\s*keyed", low):
            key, buf = 1, ""
            continue
        if re.match(r"^[–—\-]\s*keyed", low):  # en dash after html.unescape, or plain hyphen
            key, buf = -1, ""
            continue
        if key is None:
            continue
        buf = (buf + " " + line).strip()
        if buf.endswith("."):
            items.append({"factor": factor, "keyed": key, "text": buf})
            buf = ""
    return items


def main() -> None:
    r = requests.get(URL, timeout=TIMEOUT_S)
    r.raise_for_status()
    html_text = r.content.decode(r.encoding or "latin-1", errors="replace")
    items = parse(page_lines(html_text))

    for i, it in enumerate(items, 1):
        it["id"] = f"{it['factor']}{i:02d}"
    counts = {f: sum(1 for it in items if it["factor"] == f) for f in FACTOR_NAMES}
    keyed = {f: (sum(1 for it in items if it["factor"] == f and it["keyed"] == 1),
                 sum(1 for it in items if it["factor"] == f and it["keyed"] == -1)) for f in FACTOR_NAMES}
    print("items per factor:", counts)
    print("(+,-) per factor:", keyed)
    if len(items) != 50 or any(c != 10 for c in counts.values()):
        sys.exit(f"expected 50 items (10 per factor), parsed {len(items)}; page layout may have changed")

    payload = {
        "source": URL,
        "instrument": "IPIP Big Five Factor Markers, 50-item (Goldberg, 1992); public domain",
        "scale": "1 = Very Inaccurate, 2 = Moderately Inaccurate, 3 = Neither, 4 = Moderately Accurate, 5 = Very Accurate",
        "factors": FACTOR_NAMES,
        "items": items,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(items)} items -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
