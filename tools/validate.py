#!/usr/bin/env python3
"""Check the things about this repo that rot silently.

Run it locally with `python3 tools/validate.py`; CI runs the same file. Every
check here exists because the thing it checks was wrong at least once.
"""
import json
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_DIR = os.path.join(ROOT, "skill", "code-design-patterns")
REF_DIR = os.path.join(SKILL_DIR, "references")
BUNDLE = os.path.join(ROOT, "dist", "code-design-patterns.skill")

# https://code.claude.com/docs — skill frontmatter limits
MAX_DESCRIPTION = 1024
MAX_NAME = 64

# Catalogue files and the heading level at which one pattern entry lives.
CATALOGUES = {
    "01-gof-catalog.md": "### ",
    "02-modern-application-patterns.md": "## ",
    "03-concurrency-patterns.md": "## ",
    "04-distributed-resilience-patterns.md": "## ",
    "05-frontend-patterns.md": "## ",
    "10-persistence-patterns.md": "## ",
    "11-api-contract-patterns.md": "## ",
}
# Headings inside a catalogue that introduce or summarise rather than name a pattern.
NOT_ENTRIES = {
    "Contents",
    "Composition",
    "The three questions to answer first",
    "The bugs reviewers look for",
    "Where the invariant lives",
    "The contract is the promise, not the code",
}

failures = []


def fail(check, detail):
    failures.append("%s: %s" % (check, detail))


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def headings(text, level):
    out = []
    for line in text.splitlines():
        if line.startswith(level) and not line[len(level):].startswith("#"):
            out.append(line[len(level):].strip())
    return out


def slug(heading):
    """GitHub's anchor slug: drop punctuation, then one hyphen per remaining space."""
    s = heading.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    return s.replace(" ", "-")


def check_frontmatter():
    text = read(os.path.join(SKILL_DIR, "SKILL.md"))
    if not text.startswith("---\n"):
        return fail("frontmatter", "SKILL.md does not open with a YAML block")
    block = text.split("---", 2)[1]
    fields = dict(re.findall(r"(?m)^([a-z_]+):\s*(.*)$", block))
    name = fields.get("name", "")
    desc = fields.get("description", "")
    if name != os.path.basename(SKILL_DIR):
        fail("frontmatter", "name %r does not match the directory name" % name)
    if len(name) > MAX_NAME:
        fail("frontmatter", "name is %d chars, over the %d cap" % (len(name), MAX_NAME))
    if not desc:
        fail("frontmatter", "description is missing")
    if len(desc) > MAX_DESCRIPTION:
        fail(
            "frontmatter",
            "description is %d chars, over the %d cap — claude.ai rejects the bundle"
            % (len(desc), MAX_DESCRIPTION),
        )


def check_bundle():
    if not os.path.exists(BUNDLE):
        return fail("bundle", "dist/code-design-patterns.skill is missing — run tools/build.py")
    with zipfile.ZipFile(BUNDLE) as z:
        packed = {n for n in z.namelist() if not n.endswith("/")}
        on_disk = set()
        for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, "skill")):
            dirnames.sort()
            for fn in filenames:
                if fn.startswith("."):
                    continue
                p = os.path.join(dirpath, fn)
                on_disk.add(os.path.relpath(p, os.path.join(ROOT, "skill")))
        for missing in sorted(on_disk - packed):
            fail("bundle", "%s is in skill/ but not in the bundle — run tools/build.py" % missing)
        for extra in sorted(packed - on_disk):
            fail("bundle", "%s is in the bundle but not in skill/" % extra)
        for name in sorted(packed & on_disk):
            if z.read(name) != open(os.path.join(ROOT, "skill", name), "rb").read():
                fail("bundle", "%s differs from skill/ — run tools/build.py" % name)


def count_entries():
    total = 0
    for fn, level in CATALOGUES.items():
        path = os.path.join(REF_DIR, fn)
        if not os.path.exists(path):
            fail("counts", "catalogue %s is missing" % fn)
            continue
        total += len([h for h in headings(read(path), level) if h not in NOT_ENTRIES])
    return total


def check_counts():
    readme = read(os.path.join(ROOT, "README.md"))
    m = re.search(
        r"\*\*(\d+) pattern entries · (\d+) anti-patterns · (\d+) canonical LLD problems · "
        r"a (\d+)-dimension design rubric",
        readme,
    )
    if not m:
        return fail("counts", "README headline count line not found or reworded")
    claimed = [int(g) for g in m.groups()]
    actual = [
        count_entries(),
        len(headings(read(os.path.join(REF_DIR, "06-antipatterns-and-smells.md")), "### ")),
        len(headings(read(os.path.join(REF_DIR, "08-lld-question-bank.md")), "### ")),
        len(headings(read(os.path.join(REF_DIR, "07-evaluation-rubric.md")), "### ")),
    ]
    labels = ["pattern entries", "anti-patterns", "LLD problems", "rubric dimensions"]
    for label, said, is_ in zip(labels, claimed, actual):
        if said != is_:
            fail("counts", "README says %d %s; the tree has %d" % (said, label, is_))


def check_headings_unique():
    for fn in sorted(os.listdir(REF_DIR)):
        text = read(os.path.join(REF_DIR, fn))
        for level in ("## ", "### "):
            seen = {}
            for h in headings(text, level):
                key = h.replace("–", "-").replace("—", "-").lower()
                if key in seen:
                    fail("duplicates", "%s has two %r sections at %s" % (fn, h, level.strip()))
                seen[key] = True


def check_references_exist():
    docs = {"README.md": read(os.path.join(ROOT, "README.md")),
            "SKILL.md": read(os.path.join(SKILL_DIR, "SKILL.md"))}
    for fn in sorted(os.listdir(REF_DIR)):
        docs["references/" + fn] = read(os.path.join(REF_DIR, fn))
    known = set(os.listdir(REF_DIR))
    for where, text in docs.items():
        for named in set(re.findall(r"(\d\d-[a-z0-9-]+\.md)", text)):
            if named not in known:
                fail("links", "%s points at references/%s, which does not exist" % (where, named))


def check_anchors():
    for fn in sorted(os.listdir(REF_DIR)):
        text = read(os.path.join(REF_DIR, fn))
        anchors = {slug(h) for level in ("## ", "### ") for h in headings(text, level)}
        contents = text.split("---", 1)[0]
        for target in re.findall(r"\]\(#([a-z0-9-]+)\)", contents):
            if target not in anchors:
                fail("anchors", "%s contents links to #%s, which is not a heading" % (fn, target))
        listed = set(re.findall(r"\]\(#([a-z0-9-]+)\)", contents))
        # Only the "## "-level catalogues list one anchor per entry; 01 lists its three
        # GoF categories instead, and the non-catalogue files have no contents block.
        if listed:
            level = CATALOGUES.get(fn)
            if level == "## ":
                for h in headings(text, level):
                    if h in NOT_ENTRIES:
                        continue
                    if slug(h) not in listed:
                        fail("anchors", "%s: %r is not listed in the contents block" % (fn, h))


def check_evals():
    path = os.path.join(ROOT, "evals", "evals.json")
    try:
        data = json.loads(read(path))
    except ValueError as exc:
        return fail("evals", "evals.json is not valid JSON: %s" % exc)
    cases = data.get("evals", [])
    for i, case in enumerate(cases, start=1):
        for key in ("id", "name", "negative", "prompt", "expected_output", "assertions"):
            if key not in case:
                fail("evals", "case %d is missing %r" % (i, key))
        if case.get("id") != i:
            fail("evals", "case ids are not sequential at position %d" % i)
        if not case.get("assertions"):
            fail("evals", "case %s has no assertions" % case.get("name"))
    flagged = sorted(c["id"] for c in cases if c.get("negative"))
    if not flagged:
        fail("evals", "no case is flagged negative — the restraint tests are the point")
    named = sorted(int(n) for n in re.findall(r"\d+", data.get("notes", "").split("(")[-1]))
    if named != flagged:
        fail("evals", "notes name cases %s; the flagged negative cases are %s" % (named, flagged))


def main():
    check_frontmatter()
    check_bundle()
    check_counts()
    check_headings_unique()
    check_references_exist()
    check_anchors()
    check_evals()
    if failures:
        print("FAIL")
        for f in failures:
            print("  - " + f)
        return 1
    print("OK — frontmatter, bundle, counts, headings, links, anchors and evals all check out")
    return 0


if __name__ == "__main__":
    sys.exit(main())
