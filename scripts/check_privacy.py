#!/usr/bin/env python3
"""Refuse to commit personal data. Run as a pre-commit hook, or by hand to audit.

    python3 scripts/check_privacy.py            # check what's staged (hook mode)
    python3 scripts/check_privacy.py --all      # audit tree content + history (paths AND content)
    python3 scripts/check_privacy.py --history  # scan git-history CONTENT only ("can I publish this?")

This repo's deal is "share the system, not the athlete": `athlete.md`, `PLAN.md`,
`weeks/20*` and `notes/` are gitignored, and the *.example.* files carry the shape.

.gitignore alone is not enough, for two reasons this repo has already met:

1. **It guards paths, not content.** The athlete's name reached GitHub inside
   `CLAUDE.md` and the check-in skill — both legitimately tracked files. Nothing
   was misfiled; the personal data was simply written into a shared file. That is
   the likelier leak, and .gitignore cannot see it.
2. **`git add -f` bypasses it,** as does any tool that stages files for you.

So this script checks both vectors: forbidden *paths*, and forbidden *strings*
anywhere in staged content.

The strings themselves live in `.privacy-markers` (one per line, `#` comments
ignored) which is itself gitignored — putting a list of someone's personal
identifiers into a shared repo would be a strange way to protect their privacy.
No markers file, no content check: the script says so rather than passing silently.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKERS_FILE = ROOT / ".privacy-markers"

# Paths that must never be committed. Keep in step with .gitignore's personal block.
FORBIDDEN_PATHS = [
    re.compile(r"^athlete\.md$"),
    re.compile(r"^PLAN\.md$"),
    re.compile(r"^weeks/20"),
    # notes/ is private except the opt-in shared/ subdirectory. Note that
    # notes/shared/ is NOT exempt from the marker scan below — shared is exactly
    # where a leak would matter most.
    re.compile(r"^notes/(?!shared/)"),
    re.compile(r"^\.env$"),
    re.compile(r"^\.privacy-markers$"),
]


def sh(*args):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True).stdout


def load_markers():
    if not MARKERS_FILE.exists():
        return None
    out = []
    for line in MARKERS_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def staged_files():
    return [f for f in sh("git", "diff", "--cached", "--name-only",
                          "--diff-filter=ACM").splitlines() if f]


def tracked_files():
    return [f for f in sh("git", "ls-files").splitlines() if f]


def content_of(path, staged):
    if staged:
        return sh("git", "show", f":{path}")
    p = ROOT / path
    try:
        return p.read_text(errors="ignore")
    except (OSError, UnicodeDecodeError):
        return ""


def check(files, markers, staged):
    problems = []
    for f in files:
        for pat in FORBIDDEN_PATHS:
            if pat.search(f):
                problems.append(f"  {f}\n      → personal file; it must stay local (see .gitignore)")
                break
        else:
            if not markers:
                continue
            text = content_of(f, staged)
            for m in markers:
                for i, line in enumerate(text.splitlines(), 1):
                    if m.lower() in line.lower():
                        snippet = line.strip()[:70]
                        problems.append(
                            f"  {f}:{i}\n      → contains a private marker "
                            f"({m!r}) in a shared file:\n        {snippet}"
                        )
                        break
    return problems


def history_paths():
    """Forbidden PATHS that ever appeared in history. Gitignoring a file now does
    not remove it from past commits — a clone still has it."""
    ever = sh("git", "log", "--all", "--pretty=format:", "--name-only").splitlines()
    return sorted({f for f in ever if f and any(p.search(f) for p in FORBIDDEN_PATHS)})


def history_content(markers):
    """Scan the CONTENT of every file version in history for markers.

    This is the gap the path checks and the --all tree scan both miss, and it is
    the likeliest leak: a marker written into a legitimately-tracked file (a name
    in CLAUDE.md, say), committed, then scrubbed. The current file is clean and
    the path was never forbidden, so every other check passes — but the name still
    lives in an old commit. `git grep` across every commit finds it. -F matches the
    fixed-string `in` semantics used elsewhere here (an email's dots aren't regex)."""
    if not markers:
        return []
    shas = sh("git", "rev-list", "--all").split()
    if not shas:
        return []
    cmd = ["git", "grep", "-I", "-F", "-i", "-n"]
    for m in markers:
        cmd += ["-e", m]
    out = subprocess.run(cmd + shas, cwd=ROOT, capture_output=True, text=True).stdout
    seen, problems = set(), []
    for line in out.splitlines():
        parts = line.split(":", 3)  # <commit>:<path>:<lineno>:<content>
        if len(parts) < 4:
            continue
        commit, path, _, content = parts
        low = content.lower()
        hit = next((m for m in markers if m.lower() in low), "?")
        if (path, hit) in seen:  # one row per (file, marker) is plenty
            continue
        seen.add((path, hit))
        problems.append(f"  {path} @ {commit[:9]} — private marker ({hit!r}) in git history")
    return problems


def report_history(paths, content):
    """Print history findings; return True if anything was found."""
    if paths:
        print("\nIn git HISTORY — forbidden PATHS (gitignoring them now does NOT remove them):")
        for f in paths:
            print(f"  {f}")
    if content:
        print("\nIn git HISTORY — private CONTENT in past versions of tracked files:")
        print("\n".join(content))
    if paths or content:
        print("  → history needs rewriting (git filter-repo) or a fresh repo; a clone still has it.")
    return bool(paths or content)


def main():
    audit = "--all" in sys.argv
    history_only = "--history" in sys.argv and not audit
    markers = load_markers()

    if markers is None:
        print("check_privacy: no .privacy-markers file — checking paths only.")
        print("  Create one (it's gitignored) with the names, emails and places that")
        print("  must never appear in a shared file, one per line.")

    # --history: scan committed history only — the "can I publish this repo?" check.
    if history_only:
        if report_history(history_paths(), history_content(markers)):
            return 1
        print("check_privacy: OK — git history clean.")
        return 0

    files = tracked_files() if audit else staged_files()
    if not files:
        print("check_privacy: nothing to check.")
        return 0

    problems = check(files, markers, staged=not audit)

    # --all is a full audit: current tree AND history (paths + content).
    history_dirty = report_history(history_paths(), history_content(markers)) if audit else False

    if problems:
        where = "tracked files" if audit else "staged changes"
        print(f"\ncheck_privacy: FAILED — personal data in {where}:\n")
        print("\n".join(problems))
        print("\nUnstage it, or move the content into a gitignored file.")
        return 1

    if history_dirty:
        # The trap that started this: a clean tree is NOT a clean repo.
        print(f"\ncheck_privacy: tree clean ({len(files)} file(s)) — but HISTORY is not (above). "
              f"Do not publish this repo as-is.")
        return 1

    print(f"check_privacy: OK — {len(files)} file(s) clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
