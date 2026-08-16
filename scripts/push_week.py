#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests>=2.31", "pyyaml>=6.0", "python-dotenv>=1.0"]
# ///
"""Push a week of workouts to intervals.icu (which syncs them to Garmin Connect).

Run it with `uv run scripts/push_week.py …` — the inline metadata above lets uv
resolve the dependencies with no virtualenv or install step. (Plain `python3` also
works if requests/pyyaml/python-dotenv are already on the interpreter — the metadata
is just a comment to Python.)

Usage:
    python scripts/push_week.py weeks/2026-W30.yaml [--dry-run] [--wipe]
    python scripts/push_week.py weeks/2026-W30.yaml --status   # what's on the calendar

--dry-run     validate + print payloads, send nothing (no .env needed)
--wipe        delete existing workouts on the dates this file covers, then re-push
              (makes re-pushing an edited week idempotent). Only touches the dates
              present in the file, so a manual entry on an off day is left alone.
--status      list the workouts currently on the intervals.icu calendar for this
              file's dates, then exit — use it to confirm a push landed.
--allow-past  override the past-week guard (below); for deliberate backfills only.

Every push is validated first (see lint_description): the intervals.icu step
syntax is checked, and by default pace/HR targets are allowed on every step. An
athlete who wants the stricter "targets on hard efforts only" convention (easy
work carries a bare duration, its pace guidance living in the prose) sets it
per-repo with ROBO_COACH_TARGETS=hard-only in .env, or per-week with
`targets: hard-only` at the top of the week file.

Before a real push the script also runs a date guard. It uses THIS machine's
real date (not the caller's, which can be stale) and refuses to push a week whose
every workout is already in the past — the failure mode where a late check-in
delivered a week to the watch after it had been run. --allow-past overrides.

Needs .env in the repo root (not for --dry-run):
    INTERVALS_API_KEY=...      # intervals.icu Settings -> Developer
    INTERVALS_ATHLETE_ID=i...  # from the URL when logged in
"""
import argparse
import os
import re
import sys
from datetime import date
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

BASE = "https://intervals.icu/api/v1"
ROOT = Path(__file__).resolve().parent.parent

# --- workout-syntax validation ------------------------------------------------
# Each step we emit is "- <duration>[ <target>][ label]". By default pace/HR
# targets are allowed on every step. An athlete who wants the stricter convention —
# targets on hard efforts ONLY, with warmup, cooldown, recovery jogs, easy/recovery
# runs and strides carrying a bare duration (pace guidance in the prose) — sets
# ROBO_COACH_TARGETS=hard-only in .env, or `targets: hard-only` in the week file,
# which switches on the easy-step check below (see lint_description's targets_everywhere).
DURATION = re.compile(r"^\d+(\.\d+)?(km|mi|min|m|s|h)$")
PACE_TARGET = re.compile(r"^\d:\d{2}(-\d:\d{2})?/(km|mi) Pace(\s.*)?$")
HR_TARGET = re.compile(r"^\d+(-\d+)? HR(\s.*)?$")
REPEAT_HDR = re.compile(r"^\w[\w /]*\d+x$")
GROUP_HDRS = ("warmup", "cooldown", "main", "strides", "rest")
# Groups whose steps are easy by definition, so they must carry a bare duration.
# `None` = an ungrouped step, i.e. a plain easy/recovery run.
EASY_GROUPS = (None, "warmup", "cooldown", "strides", "rest")
# A step "claims a target" only on a real target token — `\bHR\b` not a bare
# substring, or the pace regex. Matching "HR" anywhere used to hard-fail any
# step labelled THRESHOLD, which contains the letters H-R.
CLAIMS_TARGET = re.compile(r"\bPace\b|\bHR\b|\d:\d{2}\s*(-\s*\d:\d{2})?\s*/(km|mi)")


def lint_description(name, desc, targets_everywhere=False):
    """Return (errors, warnings) for one workout's step text.

    Enforces the convention PLAN.md defers to this script for: explicit
    pace/HR targets belong on hard efforts ONLY. Warmup, cooldown, strides,
    recovery blocks and ungrouped easy runs must carry a bare duration —
    their pace guidance lives in the prose, which is what the watch preference
    asks for. A violation is an ERROR, not a warning: a warning printed during
    a push is a warning nobody reads.

    When the athlete's preference is targets-on-every-run (`targets: all` in the
    week file), pass targets_everywhere=True to allow pace/HR targets on easy
    steps too. Malformed targets are still errors either way.
    """
    errors, warnings = [], []
    group = None
    for raw in desc.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Only a bare header line changes the group. Prose that happens to open
        # with "Rest of the week..." previously reset the group state silently.
        if REPEAT_HDR.match(line) or line.lower().rstrip(":") in GROUP_HDRS:
            group = line.lower().rstrip(":").split()[0]
            continue
        if not line.startswith("- "):
            continue  # prose paragraph
        parts = line[2:].split(None, 1)
        dur = parts[0] if parts else ""
        rest = parts[1].strip() if len(parts) > 1 else ""
        if not DURATION.match(dur):
            errors.append(f"{name}: step '{line}' — bad duration/distance '{dur}'")
            continue
        if not CLAIMS_TARGET.search(rest):
            continue
        if not (PACE_TARGET.match(rest) or HR_TARGET.match(rest)):
            errors.append(f"{name}: step '{line}' — malformed target '{rest}'")
        elif group in EASY_GROUPS and not targets_everywhere:
            where = group or "easy/ungrouped"
            errors.append(
                f"{name}: {where} step '{line}' carries a pace/HR target — "
                f"convention is targets on hard efforts only; easy work takes a "
                f"bare duration and its pace guidance goes in the prose"
            )
    return errors, warnings


def validate(workouts, targets_everywhere=False):
    """Lint every workout; abort on errors, print warnings and continue."""
    errors, warnings = [], []
    for w in workouts:
        e, wn = lint_description(w.get("name", "?"), w.get("description", ""), targets_everywhere)
        errors += e
        warnings += wn
    for wn in warnings:
        print(f"  warning: {wn}")
    if errors:
        sys.exit("Validation failed:\n  " + "\n  ".join(errors))


def check(r):
    """Like raise_for_status(), but shows the API's error message — the useful bit."""
    if not r.ok:
        sys.exit(f"HTTP {r.status_code} {r.request.method} {r.url}\n{r.text[:500]}")


def get_auth():
    load_dotenv(ROOT / ".env")
    key = os.getenv("INTERVALS_API_KEY")
    aid = os.getenv("INTERVALS_ATHLETE_ID")
    if not key or not aid:
        sys.exit("Set INTERVALS_API_KEY and INTERVALS_ATHLETE_ID in .env (see .env.example)")
    return ("API_KEY", key), aid


def date_guard(week_field, dates, allow_past, enforce):
    """Guard against the stale-session-clock failure. The script runs on the real
    machine, so date.today() is the true date even when the caller's clock is
    stale. Refuse a week that is entirely in the past (nothing pushed could reach
    the watch in time), warn on any ISO-week mismatch, and note partly-past weeks
    (normal for a mid-week re-push). --allow-past overrides the refusal."""
    today = date.today()
    print(f"Today (real, this machine): {today.isoformat()}")
    parsed = []
    for x in dates:
        try:
            parsed.append(date.fromisoformat(x))
        except ValueError:
            pass  # placeholder dates (e.g. the example file) — nothing to check
    if not parsed:
        return
    if week_field:
        for x in parsed:
            y, w, _ = x.isocalendar()
            iso = f"{y}-W{w:02d}"
            if iso != str(week_field):
                print(f"  warning: {x.isoformat()} falls in {iso}, not the file's week {week_field}")
    past = [x for x in parsed if x < today]
    if max(parsed) < today:
        msg = (f"the whole week is in the past (latest workout {max(parsed).isoformat()} "
               f"< today {today.isoformat()}); nothing pushed can reach the watch in time "
               f"— the stale-clock failure mode")
        if enforce and not allow_past:
            sys.exit(f"Refusing to push: {msg}.\nTo backfill deliberately, re-run with --allow-past.")
        print(f"  warning: {msg}")
    elif past:
        print(f"  note: {len(past)} workout(s) dated before today "
              f"({', '.join(x.isoformat() for x in past)}) — normal for a mid-week "
              f"re-push; double-check your date if you meant to push a fresh week.")


def wipe(creds, aid, dates):
    """Delete planned workouts on exactly the dates this file covers, so a
    re-push is idempotent without disturbing manual entries on other days."""
    dset = set(dates)
    r = requests.get(
        f"{BASE}/athlete/{aid}/events",
        params={"oldest": min(dates), "newest": max(dates)},
        auth=creds,
        timeout=30,
    )
    check(r)
    for ev in r.json():
        if ev.get("category") == "WORKOUT" and str(ev.get("start_date_local", ""))[:10] in dset:
            d = requests.delete(f"{BASE}/athlete/{aid}/events/{ev['id']}", auth=creds, timeout=30)
            check(d)
            print(f"  wiped {str(ev.get('start_date_local', ''))[:10]}  {ev.get('name')}")


def show_status(creds, aid, dates):
    """List the workouts currently on the intervals.icu calendar for these dates,
    so a push can be verified as landed rather than assumed."""
    dset = set(dates)
    r = requests.get(
        f"{BASE}/athlete/{aid}/events",
        params={"oldest": min(dates), "newest": max(dates)},
        auth=creds,
        timeout=30,
    )
    check(r)
    rows = [
        ev for ev in r.json()
        if ev.get("category") == "WORKOUT" and str(ev.get("start_date_local", ""))[:10] in dset
    ]
    if not rows:
        print("No workouts on the calendar for these dates.")
        return
    print(f"On the intervals.icu calendar ({min(dates)} … {max(dates)}):")
    for ev in sorted(rows, key=lambda e: str(e.get("start_date_local", ""))):
        print(f"  {str(ev.get('start_date_local', ''))[:10]}  {ev.get('name')}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("week_file", help="e.g. weeks/2026-W30.yaml")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--wipe", action="store_true")
    ap.add_argument("--status", action="store_true", help="list calendar workouts for these dates, then exit")
    ap.add_argument("--allow-past", action="store_true", help="override the past-week guard (backfills only)")
    args = ap.parse_args()

    path = Path(args.week_file)
    if not path.exists():
        sys.exit(f"No such week file: {path}")
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        sys.exit(f"{path}: not valid YAML — {exc}")
    workouts = data.get("workouts")
    if not workouts:
        sys.exit(f"{path}: no 'workouts:' list found (copy weeks/example-week.yaml for the shape)")
    missing = [i for i, w in enumerate(workouts, 1) if not w.get("date") or not w.get("name")]
    if missing:
        sys.exit(f"{path}: workout(s) {missing} missing a date or name")
    dates = sorted(str(w["date"]) for w in workouts)

    # --status is read-only; don't let a lint error block simply asking the
    # calendar what's there.
    if args.status:
        creds, aid = get_auth()
        show_status(creds, aid, dates)
        return

    # Target placement, in precedence order: the week file's top-level `targets:`
    # key, else ROBO_COACH_TARGETS in .env (the durable per-athlete setting), else
    # the default `all`. Load .env now so --dry-run resolves it too (it doesn't
    # otherwise touch .env, and load_dotenv is a no-op when the file is absent).
    load_dotenv(ROOT / ".env")
    targets = str(data.get("targets") or os.getenv("ROBO_COACH_TARGETS") or "all").lower()
    if targets not in ("hard-only", "all"):
        sys.exit(f"{path}: unknown target placement '{targets}' — use 'all' (default) or "
                 f"'hard-only'. Set it per-week (top-level `targets:`) or per-repo "
                 f"(ROBO_COACH_TARGETS in .env).")
    validate(workouts, targets_everywhere=(targets == "all"))

    if args.dry_run:
        date_guard(data.get("week"), dates, args.allow_past, enforce=False)
        for w in workouts:
            print(f"[dry-run] {str(w['date'])}  {w['name']}")
            print("  " + w.get("description", "").replace("\n", "\n  ").rstrip())
        return

    creds, aid = get_auth()
    date_guard(data.get("week"), dates, args.allow_past, enforce=True)

    if args.wipe:
        wipe(creds, aid, dates)

    for w in workouts:
        payload = {
            "category": "WORKOUT",
            "type": w.get("type", "Run"),
            "start_date_local": f"{w['date']}T00:00:00",
            "name": w["name"],
            "description": w.get("description", ""),
        }
        r = requests.post(f"{BASE}/athlete/{aid}/events", json=payload, auth=creds, timeout=30)
        check(r)
        print(f"pushed {str(w['date'])}  {w['name']}")

    print(f"\nDone — {len(workouts)} workouts on intervals.icu; Garmin Connect picks them up shortly.")


if __name__ == "__main__":
    main()
