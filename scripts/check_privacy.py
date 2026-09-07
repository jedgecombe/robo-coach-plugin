#!/usr/bin/env python3
"""Refuse to commit data that shouldn't be committed. Pre-commit hook, or run by hand.

    python3 scripts/check_privacy.py            # check what's staged (hook mode)
    python3 scripts/check_privacy.py --all      # audit tree content + history
    python3 scripts/check_privacy.py --history  # scan git-history CONTENT only
    python3 scripts/check_privacy.py --mode     # print the active mode and exit

TWO KINDS OF REPO, TWO DIFFERENT JOBS
=====================================

This script started life guarding one arrangement: a repo that holds the coaching
*system* and gitignores the athlete. That is still the common case, but it is not
the only one — a private repo whose whole purpose is backing up the athlete's data
inverts the rule, and running the strict checks against it produces a guard that
fails on every commit. **A hook that always fails is a hook you learn to bypass**,
which is worse than no hook, so the mode is now explicit.

  shareable     The default. "Share the system, never the athlete." Personal paths
                are forbidden, and `.privacy-markers` strings are forbidden anywhere
                in tracked content or history. This is the plugin repo, and any
                training repo that keeps its data gitignored.

  private-data  A private backup. Personal files are SUPPOSED to be tracked, so the
                path and marker checks are off. In exchange the script enforces the
                thing that actually protects the athlete here — that every git
                remote has been explicitly declared private (see below).

Set it in `.privacy-mode` at the repo root. **No file means `shareable`**: the
strict mode is the safe default, so a repo that has not declared itself private
gets guarded as though it were about to be published. Never infer the mode from
repo contents — "looks private" is not a security property.

WHAT `private-data` STILL ENFORCES
==================================

Turning off the personal-data checks does not make the repo unguarded:

  * **Secrets are forbidden in every mode.** `.env` holds an intervals.icu API key.
    A credential in a private repo is still a credential in a repo — private today
    is not private after a fork, a transfer, or an accidental visibility flip, and
    unlike personal prose a leaked key is exploitable by a stranger.

  * **Every remote must be pinned as verified-private.** The script cannot ask
    GitHub whether a repo is private — a pre-commit hook has no network and no
    credentials, and one that silently passes when it cannot check is worse than
    useless. So the claim is made locally and pinned to a URL:

        private-data
        verified-private: https://github.com/you/your-training-repo.git

    Adding a remote, changing `origin`, or copying this config into a different
    repo all break the pin and fail the check. That converts "I think it's private"
    into a statement someone deliberately wrote down and has to re-affirm whenever
    the destination changes. **Verify it in the host's UI before writing the line.**

WHY .gitignore IS NOT ENOUGH (unchanged, and the reason this file exists)
========================================================================

1. **It guards paths, not content.** The athlete's name reached GitHub inside
   `CLAUDE.md` and the check-in skill — both legitimately tracked files. Nothing
   was misfiled; the personal data was written into a shared file. That is the
   likelier leak, and .gitignore cannot see it.
2. **`git add -f` bypasses it,** as does any tool that stages files for you.

The marker strings live in `.privacy-markers` (one per line, `#` comments ignored)
which is itself gitignored — putting a list of someone's personal identifiers into
a shared repo would be a strange way to protect their privacy. No markers file, no
content check: the script says so rather than passing silently.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKERS_FILE = ROOT / ".privacy-markers"
MODE_FILE = ROOT / ".privacy-mode"

MODES = ("shareable", "private-data")

# Personal paths — forbidden in `shareable`, expected in `private-data`.
PERSONAL_PATHS = [
    re.compile(r"^athlete\.md$"),
    re.compile(r"^PLAN\.md$"),
    re.compile(r"^weeks/20"),
    # notes/ is private except the opt-in shared/ subdirectory. notes/shared/ is
    # NOT exempt from the marker scan — shared is where a leak would matter most.
    re.compile(r"^notes/(?!shared/)"),
    re.compile(r"^\.privacy-markers$"),
]

# Secrets — forbidden in EVERY mode. A private repo is not a vault.
SECRET_PATHS = [
    (re.compile(r"^\.env$"), "holds live API credentials"),
    (re.compile(r"^\.env\.(?!example$)"), "an .env variant; only .env.example is shareable"),
    (re.compile(r"(^|/)id_(rsa|ed25519)$"), "a private SSH key"),
    (re.compile(r"\.pem$"), "a private key or certificate"),
]


def sh(*args):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True).stdout


def load_mode():
    """Return (mode, verified_remotes). Absent or unreadable file => shareable."""
    if not MODE_FILE.exists():
        return "shareable", []
    mode, verified = None, []
    for line in MODE_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("verified-private:"):
            verified.append(line.split(":", 1)[1].strip())
        elif mode is None:
            mode = line.lower()
    if mode not in MODES:
        print(f"check_privacy: .privacy-mode says {mode!r}, which is not one of "
              f"{MODES}. Falling back to 'shareable' — the safe default.")
        return "shareable", verified
    return mode, verified


def norm_remote(url):
    """host/owner/repo, so ssh and https forms of the same remote compare equal."""
    u = url.strip().removesuffix(".git")
    u = re.sub(r"^[a-z+]+://", "", u)          # https://, ssh://
    u = re.sub(r"^[^@/]+@", "", u)             # git@
    u = u.replace(":", "/", 1) if "/" not in u.split(":", 1)[0] else u
    return u.strip("/").lower()


def push_remotes():
    """{name: url} for every remote we could actually push to."""
    out = {}
    for line in sh("git", "remote", "-v").splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[2] == "(push)":
            out[parts[0]] = parts[1]
    return out


def check_remote_pins(verified):
    """In private-data mode, every push remote must be declared verified-private."""
    remotes = push_remotes()
    if not remotes:
        return []  # local-only repo: nothing to leak to
    ok = {norm_remote(v) for v in verified}
    problems = []
    for name, url in sorted(remotes.items()):
        if norm_remote(url) not in ok:
            problems.append(
                f"  remote {name!r} -> {url}\n"
                f"      → not declared private. Confirm in the host's UI that this repo\n"
                f"        is private, then add to .privacy-mode:\n"
                f"          verified-private: {url}"
            )
    return problems


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


def check(files, markers, staged, mode):
    problems = []
    for f in files:
        secret = next((why for pat, why in SECRET_PATHS if pat.search(f)), None)
        if secret:
            problems.append(f"  {f}\n      → {secret}; never commit it, in any mode")
            continue
        if mode == "private-data":
            continue  # personal paths and markers are the point of this repo
        if any(pat.search(f) for pat in PERSONAL_PATHS):
            problems.append(f"  {f}\n      → personal file; it must stay local (see .gitignore)")
            continue
        if not markers:
            continue
        text = content_of(f, staged)
        for m in markers:
            for i, line in enumerate(text.splitlines(), 1):
                if m.lower() in line.lower():
                    problems.append(
                        f"  {f}:{i}\n      → contains a private marker "
                        f"({m!r}) in a shared file:\n        {line.strip()[:70]}"
                    )
                    break
    return problems


def history_secrets():
    """Secret PATHS that ever appeared. Deleting them now does not un-leak the key."""
    ever = sh("git", "log", "--all", "--pretty=format:", "--name-only").splitlines()
    return sorted({f for f in ever if f and any(p.search(f) for p, _ in SECRET_PATHS)})


def history_paths():
    ever = sh("git", "log", "--all", "--pretty=format:", "--name-only").splitlines()
    return sorted({f for f in ever if f and any(p.search(f) for p in PERSONAL_PATHS)})


def history_content(markers):
    """Scan the CONTENT of every file version in history for markers.

    The gap both the path checks and the tree scan miss, and the likeliest leak: a
    marker written into a legitimately-tracked file, committed, then scrubbed. The
    current file is clean and the path was never forbidden, so every other check
    passes — but the name still lives in an old commit. -F matches the fixed-string
    `in` semantics used elsewhere here (an email's dots aren't regex)."""
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
        if (path, hit) in seen:
            continue
        seen.add((path, hit))
        problems.append(f"  {path} @ {commit[:9]} — private marker ({hit!r}) in git history")
    return problems


def report_history(paths, content, secrets):
    if secrets:
        print("\nIn git HISTORY — SECRETS (rotate the credential; removal is not enough):")
        for f in secrets:
            print(f"  {f}")
    if paths:
        print("\nIn git HISTORY — forbidden PATHS (gitignoring them now does NOT remove them):")
        for f in paths:
            print(f"  {f}")
    if content:
        print("\nIn git HISTORY — private CONTENT in past versions of tracked files:")
        print("\n".join(content))
    if paths or content:
        print("  → history needs rewriting (git filter-repo) or a fresh repo; a clone still has it.")
    return bool(paths or content or secrets)


def main():
    audit = "--all" in sys.argv
    history_only = "--history" in sys.argv and not audit
    mode, verified = load_mode()

    if "--mode" in sys.argv:
        print(f"mode: {mode}")
        for v in verified:
            print(f"  verified-private: {v}")
        if mode == "shareable" and not MODE_FILE.exists():
            print("  (no .privacy-mode file — defaulting to the strict mode)")
        return 0

    markers = load_markers()
    if markers is None and mode == "shareable":
        print("check_privacy: no .privacy-markers file — checking paths only.")
        print("  Create one (it's gitignored) with the names, emails and places that")
        print("  must never appear in a shared file, one per line.")

    # In private-data mode, personal paths and markers in history are expected —
    # only secrets are reportable there.
    def hist():
        if mode == "private-data":
            return report_history([], [], history_secrets())
        return report_history(history_paths(), history_content(markers), history_secrets())

    if history_only:
        if hist():
            return 1
        print(f"check_privacy: OK — git history clean ({mode}).")
        return 0

    remote_problems = check_remote_pins(verified) if mode == "private-data" else []

    files = tracked_files() if audit else staged_files()
    problems = check(files, markers, staged=not audit, mode=mode) if files else []
    history_dirty = hist() if audit else False

    if remote_problems:
        print(f"\ncheck_privacy: FAILED — this repo is declared 'private-data', but "
              f"{len(remote_problems)} remote(s) are not pinned as private:\n")
        print("\n".join(remote_problems))
        print("\nPersonal data is tracked here deliberately, so an undeclared remote is\n"
              "the one mistake that actually exposes the athlete.")
        return 1

    if problems:
        where = "tracked files" if audit else "staged changes"
        print(f"\ncheck_privacy: FAILED — in {where} ({mode} mode):\n")
        print("\n".join(problems))
        print("\nUnstage it, or move the content into a gitignored file.")
        return 1

    if history_dirty:
        # The trap that started this: a clean tree is NOT a clean repo.
        print(f"\ncheck_privacy: tree clean ({len(files)} file(s)) — but HISTORY is not "
              f"(above). Do not publish this repo as-is.")
        return 1

    if not files:
        print(f"check_privacy: nothing to check ({mode}).")
        return 0
    print(f"check_privacy: OK — {len(files)} file(s) clean ({mode}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
