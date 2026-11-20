"""GenAI-assisted test design: Claude proposes extra test cases from the
requirements, a rule-based gate checks them, and a human reviews the rest.

Why this design (QA view):
  * The model only *proposes*. Nothing goes into the suite without review
    (human in the loop, like a 4-eyes check).
  * Output is forced into a JSON schema (structured outputs), so it can be
    validated automatically: known REQ id? valid ISTQB technique? duplicate?
  * The prompt contains the existing test names, so the model looks for gaps
    instead of repeating what is there.

Usage:
  python3 ml/genai_testgen.py --dry-run           # print the prompt, no API call
  python3 ml/genai_testgen.py                     # call Claude (needs ANTHROPIC_API_KEY
                                                  #  or `ant auth login`)
  python3 ml/genai_testgen.py --from-file x.json   # only run the review gate
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TECHNIQUES = ["EP", "BVA", "DT", "ST", "UC", "EG", "PAIRWISE"]
MODEL = "claude-opus-5-5"

SCHEMA = {
    "type": "object",
    "properties": {
        "test_cases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "requirement": {"type": "string"},
                    "technique": {"type": "string", "enum": TECHNIQUES},
                    "preconditions": {"type": "string"},
                    "steps": {"type": "array", "items": {"type": "string"}},
                    "expected": {"type": "string"},
                    "risk": {"type": "string", "enum": ["high", "medium", "low"]},
                    "rationale": {"type": "string"},
                },
                "required": ["title", "requirement", "technique", "preconditions",
                             "steps", "expected", "risk", "rationale"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["test_cases"],
    "additionalProperties": False,
}

SYSTEM = (
    "You are a senior test engineer for embedded sanitary products (touchless WC/urinal "
    "controllers). You design black-box test cases following the ISTQB Foundation syllabus. "
    "Use only the DUT commands that exist: PRES 0|1, BATT <mV>, ADV <ms>, TIME <ms>, "
    "CFG <key> <value>, STAT. Prefer cases that find real defects: boundaries, timing "
    "races, state combinations, power loss. Do not repeat the existing tests."
)


def build_prompt(n: int) -> str:
    reqs = (ROOT / "docs/REQUIREMENTS.md").read_text()
    tests = (ROOT / "tests/system/test_flush_system.py").read_text()
    existing = sorted(set(re.findall(r"def (test_\w+)", tests)))
    return (
        f"<requirements>\n{reqs}\n</requirements>\n\n"
        f"<existing_tests>\n" + "\n".join(existing) + "\n</existing_tests>\n\n"
        f"Propose {n} NEW test cases that close gaps in the existing suite. "
        f"Technique must be one of {TECHNIQUES}. Write steps as DUT commands."
    )


def ask_claude(prompt: str) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",                      # re-run on another model if declined
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        sys.exit("model declined the request")
    if response.stop_reason == "max_tokens":
        sys.exit("output truncated (max_tokens) - ask for fewer cases")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def review_gate(data: dict) -> tuple[list[dict], list[tuple[dict, str]]]:
    """Automatic checks before a human looks at the proposals."""
    reqs = set(re.findall(r"\| (REQ-\d\d) \|", (ROOT / "docs/REQUIREMENTS.md").read_text()))
    known_cmds = ("PRES", "BATT", "ADV", "TIME", "CFG", "STAT")
    seen, ok, rejected = set(), [], []
    for tc in data.get("test_cases", []):
        key = re.sub(r"\W+", " ", tc["title"].lower()).strip()
        if tc["requirement"] not in reqs:
            rejected.append((tc, f"unknown requirement {tc['requirement']}"))
        elif tc["technique"] not in TECHNIQUES:
            rejected.append((tc, f"unknown technique {tc['technique']}"))
        elif key in seen:
            rejected.append((tc, "duplicate title"))
        elif not any(s.split()[0] in known_cmds for s in tc["steps"] if s.split()):
            rejected.append((tc, "steps use no DUT command - not executable"))
        else:
            seen.add(key)
            ok.append(tc)
    return ok, rejected


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=8, help="number of test cases to ask for")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--from-file")
    ap.add_argument("--out", default="build/ai_testcases.json")
    a = ap.parse_args()

    if a.dry_run:
        print(build_prompt(a.n))
        return
    data = json.loads(pathlib.Path(a.from_file).read_text()) if a.from_file else ask_claude(build_prompt(a.n))
    ok, rejected = review_gate(data)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"for_human_review": ok, "rejected": [
        {"case": c, "reason": r} for c, r in rejected]}, indent=2, ensure_ascii=False))
    print(f"{len(ok)} proposals passed the gate, {len(rejected)} rejected -> {out}")
    for tc in ok:
        print(f"  [{tc['risk']:<6}] {tc['requirement']} {tc['technique']:<8} {tc['title']}")
    for tc, why in rejected:
        print(f"  REJECTED {tc['title']}: {why}")


if __name__ == "__main__":
    main()
