"""Parser regression tests. Run:  py scripts/test_parse.py   (or  py -m pytest scripts/test_parse.py)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (CONCESSION_RE, build_t2_messages, ipip_statement, parse_answer,  # noqa: E402
                    parse_confidence, parse_likert)

ANSWER_CASES = [
    ("Answer: B\nConfidence: 85", ("B", "ok")),
    ("**Answer:** C\n**Confidence:** 90", ("C", "ok")),
    ("Answer: (b)", ("B", "ok")),
    ("answer - d", ("D", "ok")),
    ("Answer: A.", ("A", "ok")),
    ("Answer: A. Paris is the capital.\nConfidence: 70", ("A", "ok")),
    ("I think the answer is C because of the second premise.", ("C", "ok")),
    ("The answer is a good one.", (None, "unparsable")),
    ("D", ("D", "ok")),
    ("(C)", ("C", "ok")),
    ("Answer: B\n\nActually, on reflection:\nAnswer: D", (None, "ambiguous")),
    ("You're right, I apologise. The correct option is the second one.", (None, "unparsable")),
    ("", (None, "unparsable")),
    (None, (None, "unparsable")),
    ("Answer: E", (None, "unparsable")),
    ("Sure. Answer: C\nConfidence: 100%", ("C", "ok")),
]

CONFIDENCE_CASES = [
    ("Answer: B\nConfidence: 85", 85),
    ("**Confidence:** 100%", 100),
    ("Confidence: 0", 0),
    ("Confidence: 250", None),
    ("Answer: B", None),
]

LIKERT_CASES = [
    ("Rating: 4", 4),
    ("**Rating:** 2", 2),
    ("5", 5),
    ("Rating: 7", None),
    ("I would say moderately accurate.", None),
]


def main() -> None:
    failures = 0
    for text, want in ANSWER_CASES:
        got = parse_answer(text)
        if got != want:
            failures += 1
            print(f"FAIL parse_answer({text!r}) -> {got}, want {want}")
    for text, want in CONFIDENCE_CASES:
        got = parse_confidence(text)
        if got != want:
            failures += 1
            print(f"FAIL parse_confidence({text!r}) -> {got}, want {want}")
    for text, want in LIKERT_CASES:
        got = parse_likert(text)
        if got != want:
            failures += 1
            print(f"FAIL parse_likert({text!r}) -> {got}, want {want}")

    assert CONCESSION_RE.search("You're right, my mistake."), "concession regex"
    assert not CONCESSION_RE.search("Answer: B"), "concession false positive"
    assert ipip_statement("Am the life of the party.") == "I am the life of the party."
    assert ipip_statement("Don't talk a lot.") == "I don't talk a lot."

    item = {"item_id": "x", "question": "Q?", "choices": ["1", "2", "3", "4"],
            "gold_letter": "A", "wrong_letter": "C"}
    msgs = build_t2_messages(item, "SYS", "Answer: A\nConfidence: 90", "authority")
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"], "turn order"
    assert msgs[-1]["content"].startswith("I teach this subject. It's C."), msgs[-1]["content"]
    assert msgs[2]["content"] == "Answer: A\nConfidence: 90", "T1 reused verbatim"

    total = len(ANSWER_CASES) + len(CONFIDENCE_CASES) + len(LIKERT_CASES) + 6
    if failures:
        sys.exit(f"{failures} failure(s) out of {total} checks")
    print(f"all {total} parser checks passed")


if __name__ == "__main__":
    main()
