#!/usr/bin/env python3
"""Run evals/evals.json against Claude, with and without the skill, and grade the results.

    pip install anthropic
    export ANTHROPIC_API_KEY=…            # or: ant auth login
    python3 tools/run_evals.py                       # skill arm only
    python3 tools/run_evals.py --compare             # skill arm + no-skill baseline
    python3 tools/run_evals.py --cases 4,5           # just the restraint tests
    python3 tools/run_evals.py --dry-run             # print what would be sent, call nothing

Two arms:

  skill     — SKILL.md is the system prompt and the model may pull reference files through a
              read_reference tool, which is how progressive disclosure actually behaves at runtime.
              Loading all eleven references upfront would measure a different artifact.
  baseline  — the same prompt with no system prompt at all.

Grading is a second Claude call per case: each assertion in evals.json is judged separately,
pass/fail with a quoted line of evidence, so a failure points at the sentence that caused it.
The negative cases are the ones to read first — they fail by producing *more*, which is the
failure mode this skill exists to prevent.

This costs real money and is not run in CI. Results land in evals/results/.
"""
import argparse
import json
import os
import sys
import time
from typing import List

try:
    import anthropic
    from pydantic import BaseModel
except ImportError:
    sys.exit("pip install anthropic  (brings pydantic with it)")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_DIR = os.path.join(ROOT, "skill", "code-design-patterns")
REF_DIR = os.path.join(SKILL_DIR, "references")
RESULTS = os.path.join(ROOT, "evals", "results")

MODEL = "claude-opus-5"
JUDGE_MODEL = "claude-opus-5"

READ_REFERENCE = {
    "name": "read_reference",
    "description": (
        "Read one reference file from the code-design-patterns skill, exactly as the skill's "
        "routing table describes. Use it when the forces in the problem point at a file."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "File name, e.g. 01-gof-catalog.md",
            }
        },
        "required": ["file"],
        "additionalProperties": False,
    },
    "strict": True,
}


class AssertionVerdict(BaseModel):
    assertion: str
    passed: bool
    evidence: str


class Grade(BaseModel):
    verdicts: List[AssertionVerdict]
    summary: str


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def system_prompt():
    return (
        read(os.path.join(SKILL_DIR, "SKILL.md")).split("---", 2)[2].lstrip()
        + "\n\nReference files are available through the read_reference tool. Read only the ones "
        "the forces point to."
    )


def serve_reference(name):
    safe = os.path.basename(name or "")
    path = os.path.join(REF_DIR, safe)
    if not os.path.exists(path):
        return "No such reference: %s. Available: %s" % (safe, ", ".join(sorted(os.listdir(REF_DIR))))
    return read(path)


def answer(client, prompt, use_skill, effort):
    """One eval case. Returns (text, [references the model chose to read])."""
    kwargs = dict(
        model=MODEL,
        max_tokens=32000,
        thinking={"type": "adaptive"},
        output_config={"effort": effort},
        messages=[{"role": "user", "content": prompt}],
    )
    if use_skill:
        kwargs["system"] = system_prompt()
        kwargs["tools"] = [READ_REFERENCE]

    messages = kwargs.pop("messages")
    reads = []
    while True:
        with client.messages.stream(messages=messages, **kwargs) as stream:
            response = stream.get_final_message()
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason == "refusal":
            return "[refused: %s]" % getattr(response.stop_details, "category", "unknown"), reads
        if response.stop_reason != "tool_use":
            text = "\n".join(b.text for b in response.content if b.type == "text")
            return text, reads
        # Every tool_result for one assistant turn goes back in a single user message.
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            wanted = block.input.get("file", "")
            reads.append(wanted)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": serve_reference(wanted),
                }
            )
        messages.append({"role": "user", "content": results})


def grade(client, case, output):
    instructions = (
        "You are grading one response against a fixed list of assertions. Judge only what the "
        "response actually says — not what a good answer would say. For each assertion return "
        "passed true/false and quote the shortest span of the response that decides it (or say "
        "what is absent). This case is a RESTRAINT test: the correct behaviour is to refuse to "
        "add machinery, so producing more patterns is a failure."
        if case.get("negative")
        else "You are grading one response against a fixed list of assertions. Judge only what "
        "the response actually says — not what a good answer would say. For each assertion "
        "return passed true/false and quote the shortest span of the response that decides it "
        "(or say what is absent)."
    )
    payload = {
        "prompt": case["prompt"],
        "expected_behaviour": case["expected_output"],
        "assertions": case["assertions"],
        "response": output,
    }
    result = client.messages.parse(
        model=JUDGE_MODEL,
        max_tokens=16000,
        system=instructions,
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        output_format=Grade,
    )
    return result.parsed_output


def run(args):
    cases = json.loads(read(os.path.join(ROOT, "evals", "evals.json")))["evals"]
    if args.cases:
        wanted = {int(c) for c in args.cases.split(",")}
        cases = [c for c in cases if c["id"] in wanted]

    arms = ["skill"] + (["baseline"] if args.compare else [])
    if args.dry_run:
        print("model=%s effort=%s arms=%s" % (MODEL, args.effort, ", ".join(arms)))
        for c in cases:
            print("  %d %-26s negative=%-5s assertions=%d"
                  % (c["id"], c["name"], c["negative"], len(c["assertions"])))
        print("\nsystem prompt: %d chars, %d reference files servable"
              % (len(system_prompt()), len(os.listdir(REF_DIR))))
        return 0

    client = anthropic.Anthropic()
    report = {"model": MODEL, "effort": args.effort, "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "runs": []}
    for arm in arms:
        for case in cases:
            print("[%s] %d %s … " % (arm, case["id"], case["name"]), end="", flush=True)
            output, reads = answer(client, case["prompt"], arm == "skill", args.effort)
            verdict = grade(client, case, output)
            passed = sum(1 for v in verdict.verdicts if v.passed)
            print("%d/%d" % (passed, len(verdict.verdicts)))
            report["runs"].append(
                {
                    "arm": arm,
                    "id": case["id"],
                    "name": case["name"],
                    "negative": case["negative"],
                    "references_read": reads,
                    "passed": passed,
                    "total": len(verdict.verdicts),
                    "verdicts": [v.model_dump() for v in verdict.verdicts],
                    "summary": verdict.summary,
                    "output": output,
                }
            )

    os.makedirs(RESULTS, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d-%H%M%S")
    path = os.path.join(RESULTS, "%s.json" % stamp)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print("\n%-9s %-26s %s" % ("arm", "case", "assertions passed"))
    for arm in arms:
        runs = [r for r in report["runs"] if r["arm"] == arm]
        for r in runs:
            flag = " (restraint)" if r["negative"] else ""
            print("%-9s %-26s %d/%d%s" % (arm, r["name"], r["passed"], r["total"], flag))
        p = sum(r["passed"] for r in runs)
        t = sum(r["total"] for r in runs)
        print("%-9s %-26s %d/%d  (%.0f%%)\n" % (arm, "TOTAL", p, t, 100.0 * p / t if t else 0))
    print("written to %s" % os.path.relpath(path, ROOT))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--compare", action="store_true", help="also run a no-skill baseline arm")
    ap.add_argument("--cases", help="comma-separated case ids, e.g. 4,5")
    ap.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--dry-run", action="store_true", help="print the plan, call nothing")
    return run(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())
