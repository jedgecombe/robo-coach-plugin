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

Steps also take an optional `intensity=<value>` attribute. It is the only way to tell
Garmin that a step is a recovery jog or a standing rest rather than work: without it
every step outside a Warmup/Cooldown block reaches the watch labelled a plain "Run",
so a 90-second recovery jog is indistinguishable from the rep before it. The linter
checks the value against what intervals.icu actually accepts, because an unrecognised
one is silently dropped.

Descriptions are also length-checked. Garmin echoes the whole description into
both its Overview and Notes panels and truncates long text, so a watch note is
kept a short glanceable cue (the reasoning lives in the week's .md): the linter
warns past ~500 characters and errors past ~800.

Names are checked too, and more strictly than they look like they deserve: the
name is the one field that ends up PUBLIC. Garmin stamps it onto the saved
activity, which the athlete's connections see. So a name is factual and standard —
"<session type> <structure>", plain ASCII — and the linter enforces that (see
lint_name). It also prints what a watch will actually show, since the FIT field
truncates at 15 bytes.

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
# HR targets: intervals.icu's parser accepts ONLY percentage and zone forms.
# Absolute bpm is silently DROPPED — "- 10m 168-175 HR" and "- 10m 168-175 bpm"
# both come back from the API as a bare {"duration": 600} with no target, so the
# step reaches the watch with nothing on it. This regex used to accept the bpm
# form, which meant a whole HR-prescribed session linted clean and pushed empty
# (caught 2026-08-23 on W35's 4×10′, by the athlete, after the push). Verified
# against the live API that day: %LTHR and %HR parse, bare bpm does not.
#
# Use %LTHR, not %HR. %LTHR anchors on threshold HR (sport-settings `lthr`);
# %HR anchors on max HR, so the same numbers mean something far harder — 94-98%
# read as %HR scored Z7 in the same probe. `Z4 HR` parses too but is rejected
# below: the house convention is explicit numbers, never zone references.
HR_TARGET = re.compile(r"^\d+(\.\d+)?(-\d+(\.\d+)?)?% ?(LTHR|HR)(\s.*)?$")
HR_ZONE_REF = re.compile(r"^Z\d+ ?(HR|Pace)(\s.*)?$")
HR_BPM = re.compile(r"^\d+(-\d+)? ?(HR|bpm|BPM)(\s.*)?$")
# --- Garmin step intensity ----------------------------------------------------
# intervals.icu carries the FIT `intensity` field through to Garmin, but ONLY from an
# explicit `intensity=<value>` token on the step. There is no auto-detection worth
# relying on: the old automatic rule only marked a step as recovery when it carried a
# target below a zone threshold, so a bare-duration jog could never qualify. A
# `Warmup`/`Cooldown` header still sets its own flag; everything else defaults to a
# plain work step, which the watch shows as "Run".
#
# Verified against the live API 2026-09-01. `- 90s intensity=recovery` parses to
# {"duration": 90, "intensity": "recovery"} with no target present, inside a repeat and
# ungrouped alike. The value is case-insensitive, but an unrecognised one (`recover`)
# and a spaced form (`intensity = recovery`) are both SILENTLY DROPPED — the same
# failure class as absolute bpm targets, so both are errors below.
INTENSITY = re.compile(r"\bintensity=(\S+)", re.I)
INTENSITY_WORD = re.compile(r"\bintensity\b", re.I)
INTENSITIES = ("active", "interval", "recovery", "rest", "warmup", "cooldown", "other")
# A step whose label says "recovery"/"rest" but carries no flag is the trap this catches:
# it reads right in the YAML and still arrives on the watch as work.
RECOVERY_LABEL = re.compile(r"\b(recovery|rest)\b", re.I)

REPEAT_HDR = re.compile(r"^\w[\w /]*\d+x$")
GROUP_HDRS = ("warmup", "cooldown", "main", "strides", "rest")
# Groups whose steps are easy by definition, so they must carry a bare duration.
# `None` = an ungrouped step, i.e. a plain easy/recovery run.
EASY_GROUPS = (None, "warmup", "cooldown", "strides", "rest")
# A step "claims a target" only on a real target token — `\bHR\b` not a bare
# substring, or the pace regex. Matching "HR" anywhere used to hard-fail any
# step labelled THRESHOLD, which contains the letters H-R.
# \bHR\b does not match inside "LTHR" (T and H are both word chars, so there is
# no boundary), so LTHR and bpm are listed explicitly — otherwise a %LTHR target
# on an easy step would slip past the hard-only check unnoticed.
CLAIMS_TARGET = re.compile(
    r"\bPace\b|\bLTHR\b|\bHR\b|\bbpm\b|\bBPM\b|\d:\d{2}\s*(-\s*\d:\d{2})?\s*/(km|mi)"
)

# --- workout name --------------------------------------------------------------
# The name is the most public field in the whole payload. intervals.icu sends it on to
# Garmin Connect as the workout name, and Garmin's "Activity Name" display preference
# has a "Workout Name (when available)" setting that stamps it onto the SAVED ACTIVITY —
# the one the athlete's Garmin Connect connections see in their feed, and the one the
# activity page shows alongside the workout's steps either way. A name written as a
# private joke is therefore published under the athlete's own account, long after the
# joke has stopped being funny. So names here are factual and standard, and this is the
# one piece of house style the linter enforces for taste rather than for correctness.
#
# Length is a device constraint, not a server one. intervals.icu declares no limit (its
# OpenAPI spec types `name` as a bare string) and Garmin Connect stores a long name
# fine — but the FIT workout message allocates `wkt_name` as a 16-byte array
# (garmin/fit-c-sdk, FIT_WORKOUT_MESG_WKT_NAME_COUNT = 16): 15 bytes plus a terminator,
# which is why a long name is cut on the watch itself. The first 15 bytes therefore
# have to carry the meaning, which is exactly what the session-type-first rule buys —
# "Threshold 4x10min" cuts to "Threshold 4x10" and still says what the session is,
# where "Session 4 of the specific block" cuts to nothing useful at all.
NAME_WATCH = 15   # bytes a watch shows before truncating (FIT wkt_name is 16 with its NUL)
NAME_MAX = 42     # convention cap — past this the name is doing the description's job

# A name opens with its session type. That keeps the truncated form identifying, and it
# makes the calendar read as a training log rather than a mood board. The list is
# deliberately broad: it exists to catch a jokey or cryptic name, not to police
# vocabulary — extend it if a legitimate session type is missing.
SESSION_TYPES = (
    # running
    "easy", "recovery", "steady", "long", "progression", "tempo", "threshold",
    "intervals", "reps", "hills", "fartlek", "strides", "shakeout", "run",
    "mp", "marathon", "half", "race", "time", "test", "warmup",
    # everything else a week file legitimately carries
    "bike", "ride", "swim", "row", "walk", "hike", "strength", "gym", "core",
    "mobility", "yoga", "pilates", "cross", "rest", "off",
)
NAME_LEAD = re.compile(r"^[A-Za-z]+")


def watch_name(name):
    """What a Garmin will show for this name, or None when it fits as written.

    The cut is on BYTES, not characters, because FIT stores wkt_name in a fixed-size
    array — which is the other reason to keep a name plain ASCII: a single emoji
    spends four of the fifteen bytes the watch has to work with.
    """
    raw = name.encode("utf-8")
    if len(raw) <= NAME_WATCH:
        return None
    return raw[:NAME_WATCH].decode("utf-8", "ignore")


def name_line(name):
    """The name as it will be pushed, plus what the watch shows when they differ."""
    cut = watch_name(name)
    return name if cut is None else f'{name}   (watch: "{cut}")'


def lint_name(name):
    """Return (errors, warnings) for one workout's name.

    Stricter than it looks like it needs to be, for the reason in the NAME_* block
    above: this field gets published on the athlete's activity feed.
    """
    errors, warnings = [], []
    n = name.strip()
    if not n:
        return ["a workout has a blank name"], warnings
    if n != name:
        warnings.append(f"{n}: name is padded with whitespace — trimmed before sending")
    odd = sorted({c for c in n if not 32 <= ord(c) <= 126})
    if odd:
        errors.append(
            f"{n}: name contains non-ASCII character(s) {', '.join(repr(c) for c in odd)}. "
            f"Garmin publishes this name on the saved activity, watch fonts frequently "
            f"can't render emoji, and each one spends up to four of the {NAME_WATCH} bytes "
            f"the watch has. Keep names plain ASCII."
        )
    raw = len(n.encode("utf-8"))
    if raw > NAME_MAX:
        errors.append(
            f"{n}: name is {raw} chars — over the {NAME_MAX}-char cap. The name says what "
            f"the session IS; the execution cues belong in the description."
        )
    lead = NAME_LEAD.match(n)
    if not lead or lead.group(0).lower() not in SESSION_TYPES:
        errors.append(
            f"{n}: name must open with the session type, so the watch-truncated form still "
            f"identifies the session and the calendar reads as a training log — e.g. "
            f"'Threshold 4x10min', 'Easy 8km + strides', 'Long run 26km', 'Strength 45min'. "
            f"(Full vocabulary: SESSION_TYPES in push_week.py — extend it if a legitimate "
            f"session type is missing.)"
        )
    return errors, warnings


# --- description length --------------------------------------------------------
# Garmin renders the WHOLE description twice — once in its "Overview" panel and
# again under "Notes" — and it truncates the field past roughly a kilobyte,
# dropping the tail. The tail is where the fuelling schedule and the "if the day
# goes sideways" priority calls tend to sit, so an over-long note loses the part
# that matters most. Observed behaviour: a short note (~300 chars) renders in
# full in both panels; a ~1300-char one is cut off mid-note. The steps still
# reach the watch correctly either way — this only bites the prose.
#
# So a watch note is a short, glanceable execution cue: what to DO, in the
# moment, at a glance. The reasoning — HR mappings, block context, what locks
# when — belongs in the week's .md, read at home, not on a wrist mid-run. These
# bounds enforce that; they are a convention limit, deliberately well under
# Garmin's own, not a guess at the exact truncation point.
DESC_WARN = 500   # getting long — trim toward a scannable cue
DESC_MAX = 800    # too long to read mid-run, and at risk of truncation


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

    Also checks each step's optional `intensity=` attribute — the flag that makes a
    recovery jog show up on the watch as recovery rather than as another work step.
    """
    errors, warnings = [], []
    group = None
    # A description that LEADS with a bare "Main" header is silently broken: intervals.icu
    # mis-parses the lone "Main" into workout_doc.description, and Garmin then drops the WHOLE
    # note (confirmed 2026-08-29 — the note vanished entirely rather than truncating, which is
    # what made it look like a length problem). Lead with a step or a "Warmup" block instead;
    # keep the targeted efforts under "Main" after that. A "Warmup"/…/"Main" order parses clean.
    first_line = next((l.strip() for l in desc.splitlines() if l.strip()), "")
    if first_line.lower().rstrip(":") == "main":
        errors.append(
            f"{name}: description leads with a bare 'Main' header — intervals.icu mis-parses it "
            f"and Garmin drops the entire note. Lead with a step (e.g. the easy portion) or a "
            f"'Warmup' block, and keep the targeted efforts under 'Main' after it."
        )
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
        # `intensity=` is a step attribute, not part of the target — check it and strip
        # it before the target regexes below ever see it.
        intensity = None
        found = INTENSITY.search(rest)
        if found:
            intensity = found.group(1).lower()
            if intensity not in INTENSITIES:
                errors.append(
                    f"{name}: step '{line}' — unknown intensity '{found.group(1)}'; "
                    f"intervals.icu SILENTLY DROPS a value it doesn't recognise and the "
                    f"step reaches the watch as a plain work step. Use one of: "
                    f"{', '.join(INTENSITIES)}"
                )
            rest = INTENSITY.sub(" ", rest).strip()
        elif INTENSITY_WORD.search(rest):
            errors.append(
                f"{name}: step '{line}' — malformed intensity attribute; write it as "
                f"'intensity=recovery', with no spaces around the '='. Any other form "
                f"is silently dropped and the step reaches the watch as work."
            )
        elif RECOVERY_LABEL.search(rest):
            warnings.append(
                f"{name}: step '{line}' — the label says recovery/rest but the step "
                f"carries no 'intensity=' attribute, so Garmin shows it as a plain work "
                f"step. Add 'intensity=recovery' (or 'intensity=rest')."
            )
        if not CLAIMS_TARGET.search(rest):
            continue
        if HR_BPM.match(rest):
            errors.append(
                f"{name}: step '{line}' — absolute bpm target '{rest}' is SILENTLY "
                f"DROPPED by intervals.icu; the step would reach the watch with no "
                f"target. Use a percentage of threshold HR instead, e.g. "
                f"'94-98% LTHR' (check sport-settings `lthr` for the bpm it resolves to)"
            )
        elif HR_ZONE_REF.match(rest):
            errors.append(
                f"{name}: step '{line}' — zone reference '{rest}'; convention is "
                f"explicit numbers (a pace range, or a % of LTHR), never zones"
            )
        elif not (PACE_TARGET.match(rest) or HR_TARGET.match(rest)):
            errors.append(f"{name}: step '{line}' — malformed target '{rest}'")
        elif (group in EASY_GROUPS or intensity in ("recovery", "rest")) and not targets_everywhere:
            where = ("recovery" if intensity in ("recovery", "rest")
                     else group or "easy/ungrouped")
            errors.append(
                f"{name}: {where} step '{line}' carries a pace/HR target — "
                f"convention is targets on hard efforts only; easy work takes a "
                f"bare duration and its pace guidance goes in the prose"
            )
        if HR_TARGET.match(rest) and "LTHR" not in rest:
            warnings.append(
                f"{name}: step '{line}' anchors on max HR (%HR) rather than "
                f"threshold (%LTHR) — the same numbers mean a much harder effort"
            )
    n = len(desc)
    if n > DESC_MAX:
        errors.append(
            f"{name}: description is {n} chars — over the {DESC_MAX}-char watch-note "
            f"limit. Garmin shows it twice (Overview + Notes) and truncates the tail, "
            f"where the fuelling and priority calls live. Keep the note a glanceable "
            f"cue and move the reasoning to the week's .md."
        )
    elif n > DESC_WARN:
        warnings.append(
            f"{name}: description is {n} chars — getting long. The watch note should "
            f"be a scannable cue (~400 or under); put the 'why' in the .md."
        )
    return errors, warnings


def validate(workouts, targets_everywhere=False):
    """Lint every workout; abort on errors, print warnings and continue."""
    errors, warnings = [], []
    for w in workouts:
        name = str(w.get("name", "?"))
        for e, wn in (lint_name(name),
                      lint_description(name, w.get("description", ""), targets_everywhere)):
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
    # Normalise names once, here, so the linted string and the pushed string are the
    # same one — a name that lints clean after trimming must not be sent back padded.
    for w in workouts:
        w["name"] = str(w["name"]).strip()
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
            print(f"[dry-run] {str(w['date'])}  {name_line(w['name'])}")
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
        print(f"pushed {str(w['date'])}  {name_line(w['name'])}")

    print(f"\nDone — {len(workouts)} workouts on intervals.icu; Garmin Connect picks them up shortly.")


if __name__ == "__main__":
    main()
