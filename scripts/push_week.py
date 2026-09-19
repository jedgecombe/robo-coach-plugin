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
--wipe        after a successful push, also delete workouts on these dates that this
              script did not write — legacy or hand-made entries. Rarely needed now
              that a plain re-push updates in place (see below). The deletes happen
              AFTER the write lands, so a failed push leaves the calendar untouched.
--status      list the workouts currently on the intervals.icu calendar for this
              file's dates, with the role tag read back off each one, then exit —
              use it to confirm a push landed and kept its roles.
--allow-past  override the past-week guard (below); for deliberate backfills only.

Every push is validated first (see lint_description): the intervals.icu step
syntax is checked, and by default pace/HR targets are allowed on every step. An
athlete who wants the stricter "targets on hard efforts only" convention (easy
work carries a bare duration, its pace guidance living in the prose) sets it
per-repo with ROBO_COACH_TARGETS=hard-only in .env, or per-week with
`targets: hard-only` at the top of the week file.

A pace range target (`4:05-4:15/km Pace`) must be at least 20 seconds wide. Anything
narrower sits inside a GPS watch's own pace noise, so the reading jitters in and out of
the target zone and the watch beeps almost continuously for the rest of the step — no
coaching benefit, just noise. Widen a too-tight range around the same centre; the linter
errors on anything under 20s.

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

Every workout also carries a `role:` — one of the ten in ROLES — pushed as a
`nocoach:<role>` tag on the calendar event. That tag is the only thing recording what a
session was FOR. Nothing downstream infers it: not from the name, which is free text,
and not from the distance, because one athlete's long run is another's easy run. So an
event pushed without one has no role at all, and a week of them reads as a claim about
the athlete rather than about our labelling — the key count goes unknown, the morning
after a threshold can't be told from recovered legs, a race just run goes undetected by
the rules that read the week behind (the taper is NOT one of them: it fires off the goal
date, not off any tag), and a mid-week re-plan under-counts the quality already run,
which is the one place a missing tag makes a rule more permissive rather than less sure. A workout without one is pushed untagged, with a
warning — the week then reads back as "we don't know" rather than as a wrong number.
A MISSPELT one is an error, because it reads downstream as no role while looking
labelled. Read the tags back off the calendar with --status.

Re-pushing an edited week UPDATES the events already on the calendar rather than
replacing them. Each workout is written with a stable `external_id` of our own —
`robo-coach:<date>:<n>` — through intervals.icu's `events/bulk?upsert=true`, so the
same slot pushed twice lands on the same row and keeps its provider event id. That
matters to anything mirroring the calendar: a reader notices a removed event by asking
for a window of dates and seeing what does not come back, so a delete-and-recreate on
the day of a check-in leaves the dead event in its copy, unlabelled, until the next
day — long enough to make a fully tagged week read as though it holds an untagged
session. Sessions the week file no longer describes are removed afterwards, and only
ever OURS: an event without our `external_id` prefix is left alone, so a hand-made
entry or another system's session on the same calendar survives a push.

Note the two namespaces are different and both matter. The `nocoach:` tag namespace is
the READER's, and we write into it because that is what it reads. The `robo-coach:`
external_id namespace is OURS, and must stay ours — two writers sharing an external_id
prefix would silently overwrite each other's sessions.

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
# A pace range narrower than this is inside a GPS watch's own pace noise: on flat, clean
# GPS the reported pace still jitters by several seconds/km rep to rep, so a band tighter
# than that reads as in-and-out of the target zone constantly and the watch beeps every
# few seconds for the rest of the step. Minimum width, not a suggestion — captures the
# group so the two sides can be compared in seconds; the centre is left wherever it was.
PACE_RANGE_MIN_S = 20
PACE_RANGE = re.compile(r"^(\d):(\d{2})-(\d):(\d{2})/(km|mi) Pace")
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


# --- session role -------------------------------------------------------------
# Each pushed event carries ONE tag naming what the session is for: `nocoach:<role>`.
# The tag is the sole carrier of that fact — see the docstring for why nothing
# downstream can infer it — so an event pushed without one is not "unlabelled" in any
# recoverable way; it simply has no role, and every rule scoped to a role goes quiet.
#
# A missing role is a WARNING, and the workout is then pushed with no `nocoach:` tag at
# all rather than a stand-in. Defaulting it to `other` is the tempting alternative and
# the worse one: `other` is a real role meaning "a run with no role-scoped rule", so a
# session that was meant to be `key` and simply didn't get labelled would go up as a
# deliberate non-key run, and the week's key count would come back a confident wrong
# number. Untagged degrades the other way — nothing downstream has a role to work with,
# so the key count reads as unknown and the legs the morning after read as unverified.
# "We don't know" is the honest failure; a plausible wrong number is not.
#
# A near-miss is still an ERROR, for that same reason rather than in spite of it.
# `Long`, `longrun` and `tune-up` are all read downstream as no role at all, which is
# indistinguishable from never having written one — except that the athlete believes the
# week is labelled and won't see the `?` that would have told them otherwise. Exact
# strings, lowercase; note the underscore in `tune_up`.
#
# What each one turns on downstream:
#   key       the week's quality; counts toward the key ceiling
#   long      the long run; continuity is read across it
#   easy      the reference-band instrument reads here, on recovered legs only
#   recovery  like easy, but the band instrument is suppressed: legs not recovered
#   social    stoppage ignored and pace not read; volume still counts
#   race      the goal race; no compliance verdict; detects a race just run, which is
#             what the post-race week rule reads (the taper needs no tag — goal date)
#   tune_up   a race that is a data point; quality stays three days clear of it
#   strength  non-running; an entry with no session
#   rest      a written rest day, zero steps, so the rest rule is checkable
#   other     a run with no role-scoped rule
# Verified against the live account 2026-09-07: a `tags` array on a single-event POST is
# accepted and persists — the tag shows on the intervals.icu calendar entry, and reaches
# neither the description nor the watch. (The bulk upsert path below is the same field.)
ROLE_TAG = "nocoach:"
ROLES = (
    "key", "long", "easy", "recovery", "social",
    "race", "tune_up", "strength", "rest", "other",
)
# Plausible ways to write a real role that are not the real role. Each is a way to lose
# a week's labelling to a typo, so the error names the one that was meant.
ROLE_NEAR_MISS = {
    "long_run": "long", "longrun": "long", "lr": "long",
    "tuneup": "tune_up", "tune": "tune_up", "parkrun": "tune_up", "time_trial": "tune_up",
    "quality": "key", "session": "key", "workout": "key", "hard": "key",
    "tempo": "key", "threshold": "key", "intervals": "key", "reps": "key", "hills": "key",
    "gym": "strength", "core": "strength", "cross_training": "strength",
    "off": "rest", "day_off": "rest", "none": "other", "null": "other",
    "club": "social", "group": "social", "shakeout": "easy",
}
ROLE_COL = max(len(r) for r in ROLES)   # keeps the printed role column aligned


def role_hint(value):
    """The role a mistyped one was probably meant to be, or None."""
    norm = value.strip().lower().replace("-", "_").replace(" ", "_")
    return norm if norm in ROLES else ROLE_NEAR_MISS.get(norm)


def lint_role(name, w):
    """Return (errors, warnings) for one workout's `role:`.

    A missing role is a warning and the workout goes up untagged (see the ROLES block).
    A malformed one is an error: `Long`, `longrun` and `tune-up` are all read downstream
    as no role at all, which is the failure this mechanism exists to prevent — every long
    run reading as something else, the rules scoped to that role silently never firing,
    and nothing on the athlete's side saying so.
    """
    role = w.get("role")
    if role is None:
        return [], [
            f"{name}: no `role:` — pushing it untagged. Nothing downstream can then tell "
            f"what this session was for (the name is free text; distance says nothing), so "
            f"the week's key count reads as unknown rather than as a number, and the legs "
            f"the morning after read as unverified. Add one of: {', '.join(ROLES)} "
            f"(`other` for a run with no role-scoped rule)."
        ]
    if not isinstance(role, str):
        return [
            f"{name}: `role:` must be a single string, not {type(role).__name__}. Exactly "
            f"one role per workout — an event carrying two is rejected downstream, since "
            f"choosing between them would be a guess."
        ], []
    if role.strip() in ROLES:
        return [], ([f"{name}: `role:` is padded with whitespace — trimmed before sending"]
                    if role.strip() != role else [])
    guess = role_hint(role)
    said = f" Did you mean `{guess}`? " if guess else " "
    return [
        f"{name}: unknown role '{role}'.{said}The value is matched exactly — lowercase, "
        f"and `tune_up` with an underscore. Valid: {', '.join(ROLES)}"
    ], []


def lint_tags(name, w):
    """Return (errors, warnings) for a workout's own optional `tags:`.

    The athlete's own labelling is welcome alongside the role tag and is ignored
    downstream. A hand-written `nocoach:` tag is not: two of them on one event is a
    hard failure there, so it is a hard failure here, where the fix is obvious.
    """
    tags = w.get("tags")
    if tags is None:
        return [], []
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        return [f"{name}: `tags:` must be a list of strings (or absent)"], []
    mine = [t for t in tags if t.strip().lower().startswith(ROLE_TAG)]
    if mine:
        return [
            f"{name}: tag(s) {', '.join(repr(t) for t in mine)} set the session role by "
            f"hand. Use `role:` instead — it is pushed as the {ROLE_TAG}… tag, and an "
            f"event carrying two of those is rejected downstream."
        ], []
    return [], []


NO_ROLE = "—"   # what the role column shows for a workout carrying none


def event_tags(w):
    """The tag list pushed for one workout: its role tag when it has one, then the
    athlete's own. A workout with no role is pushed with no `nocoach:` tag rather than
    a defaulted one — see the ROLES block for why that is the safer way to be wrong."""
    role = w.get("role")
    return ([ROLE_TAG + str(role).strip()] if role else []) + \
           [str(t) for t in (w.get("tags") or [])]


def role_cell(w):
    """One workout's role, padded for the output column."""
    role = w.get("role")
    return f"{str(role).strip() if role else NO_ROLE:<{ROLE_COL}}"


def role_of(ev):
    """The role on a calendar event read back from the API, named the way the check-in
    reads it. Returns the display string, not a role — 'no role' and 'AMBIGUOUS' are
    both states worth seeing in --status output rather than errors to raise on."""
    tags = ev.get("tags")
    if not isinstance(tags, list):
        return NO_ROLE
    found = [t[len(ROLE_TAG):] for t in tags
             if isinstance(t, str) and t.startswith(ROLE_TAG)]
    if not found:
        return NO_ROLE
    if len(found) > 1:
        return "AMBIGUOUS(" + ",".join(found) + ")"
    return found[0]


# --- event identity ------------------------------------------------------------
# Every event we write carries an `external_id` of ours, and we push through
# `events/bulk?upsert=true`, where a repeated external_id UPDATES the event instead of
# adding another. The point is that a session keeps its provider event id across a
# rewrite. A delete-and-recreate mints a new id, and anything mirroring this calendar
# detects a removal by asking for a window of dates and seeing what fails to come back —
# a comparison that cannot safely be made on the newest day of the window, because the
# provider's date bounds are the thing being trusted. So a session replaced TODAY leaves
# its predecessor in the mirror until tomorrow, and check-in day is exactly that day: the
# week then reads as holding an unlabelled session it does not hold, and where a day has
# more than one event the dead one can take over the role of the live one.
#
# The id is `robo-coach:<date>:<n>`, n counting workouts within that date from 1 in file
# order. Stable across an edit to a session's name, steps or role — which is the case that
# matters, since that is what a re-push after a mid-week change actually does. Reordering
# two sessions on the SAME day swaps their ids and so rewrites both; harmless, and rarer
# than the case this buys.
#
# The prefix must stay ours. `nocoach:` is the reader's tag namespace and we write into it
# deliberately; external_id is a different namespace, and two systems sharing a prefix
# there would each silently overwrite the other's sessions.
EXT_PREFIX = "robo-coach:"


def with_external_ids(workouts):
    """A stable external_id per workout, in file order."""
    seen = {}
    ids = []
    for w in workouts:
        day = str(w["date"])
        seen[day] = seen.get(day, 0) + 1
        ids.append(f"{EXT_PREFIX}{day}:{seen[day]}")
    return ids


def is_ours(ev):
    """Whether we wrote this event. Anything else on the calendar is left alone."""
    return str(ev.get("external_id") or "").startswith(EXT_PREFIX)


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
        pace_range = PACE_RANGE.match(rest)
        if pace_range:
            m1, s1, m2, s2, _ = pace_range.groups()
            lo = int(m1) * 60 + int(s1)
            hi = int(m2) * 60 + int(s2)
            width = hi - lo
            if width < PACE_RANGE_MIN_S:
                errors.append(
                    f"{name}: step '{line}' — pace range is {width}s wide, under the "
                    f"{PACE_RANGE_MIN_S}s minimum. A band that tight sits inside a GPS "
                    f"watch's own pace noise, so it reads in and out of the target zone "
                    f"constantly and beeps the whole step. Widen it (keep the same centre) "
                    f"to at least {PACE_RANGE_MIN_S}s."
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
                      lint_role(name, w),
                      lint_tags(name, w),
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


def fetch_workouts(creds, aid, dates, span=False):
    """Planned workouts already on the calendar for this file's dates.

    The API takes a date range, and by default the result is filtered back down to the
    file's own days — so a manual entry on an off day inside the week is invisible here
    and cannot be touched. Pass span=True to keep everything between the first and last
    date instead, which is what finding a dropped session needs: a day removed from the
    week file is no longer one of its dates, so the orphan left on it would otherwise
    never be looked at.
    """
    dset = set(dates)
    first, last = min(dates), max(dates)
    r = requests.get(
        f"{BASE}/athlete/{aid}/events",
        params={"oldest": first, "newest": last},
        auth=creds,
        timeout=30,
    )
    check(r)
    # Filter on the dates we got back rather than trusting the query bounds. Whether the
    # provider treats oldest/newest as inclusive, and whether it selects on local time or
    # UTC, is not something this script has established — and one of the two callers here
    # DELETES what this returns. A day either side is the difference between removing a
    # dropped session and removing last week's.
    def keeps(ev):
        day = str(ev.get("start_date_local", ""))[:10]
        return first <= day <= last if span else day in dset
    return [ev for ev in r.json() if ev.get("category") == "WORKOUT" and keeps(ev)]


def delete_event(creds, aid, ev, verb):
    d = requests.delete(f"{BASE}/athlete/{aid}/events/{ev['id']}", auth=creds, timeout=30)
    check(d)
    print(f"  {verb} {str(ev.get('start_date_local', ''))[:10]}  {ev.get('name')}")


def reconcile(creds, aid, dates, keep, wipe_foreign=False):
    """Remove what the week file no longer describes. Runs AFTER the push has succeeded,
    never before: a delete that happens first is a delete that has already happened when
    the write turns out to fail.

    By default only OUR events are removed — a session dropped from an edited week.
    An event without our external_id prefix is not ours to delete: it is a hand-made
    entry, or another system writing to the same calendar. `wipe_foreign` (--wipe) takes
    those too.

    Two different windows, deliberately. Our own events are reconciled across the whole
    span between the file's first and last date, so a session dropped from a day in the
    middle is caught. Foreign events are only touched on the days the file actually
    names, which preserves --wipe's old promise that a manual entry on an off day is
    left alone. The span still stops at the file's own dates rather than widening to the
    ISO week, because a mid-week re-plan legitimately covers only the days still to
    come and widening it would delete the completed days. The cost is that a session
    dropped from the very START or END of a week falls outside the new span and
    survives; that shows in --status, and leaving an event is the right way to be wrong.
    """
    dset = set(dates)
    for ev in fetch_workouts(creds, aid, dates, span=True):
        if ev.get("external_id") in keep:
            continue
        if is_ours(ev):
            delete_event(creds, aid, ev, "removed (no longer in the week file)")
        elif wipe_foreign and str(ev.get("start_date_local", ""))[:10] in dset:
            delete_event(creds, aid, ev, "wiped (not written by this script)")


def show_status(creds, aid, dates):
    """List the workouts currently on the intervals.icu calendar for these dates, with
    the role tag and provider event id of each, so a push can be verified as landed
    rather than assumed. The id is the check that a re-push UPDATED a session rather
    than replacing it: one session, one id, however many times it is edited.
    A `~` marks an event we did not write, which a push will leave alone. The listing
    covers the whole span between the first and last date, not just the days the file
    names, so a session left behind on a day dropped from the week shows up here."""
    rows = fetch_workouts(creds, aid, dates, span=True)
    if not rows:
        print("No workouts on the calendar for these dates.")
        return
    print(f"On the intervals.icu calendar ({min(dates)} … {max(dates)}):")
    untagged = foreign = 0
    for ev in sorted(rows, key=lambda e: str(e.get("start_date_local", ""))):
        role = role_of(ev)
        untagged += role == NO_ROLE
        mine = is_ours(ev)
        foreign += not mine
        print(f"  {str(ev.get('start_date_local', ''))[:10]} {' ' if mine else '~'} "
              f"{role:<{ROLE_COL}}  id={str(ev.get('id')):<10}  {ev.get('name')}")
    if untagged:
        print(f"\n  warning: {untagged} of these carry no {ROLE_TAG}… role tag, so nothing "
              f"downstream knows what those sessions were for. Re-pushing the week tags "
              f"the ones we wrote; anything marked ~ has to be fixed where it came from.")
    if foreign:
        was = "was" if foreign == 1 else "were"
        print(f"\n  note: {foreign} marked ~ {was} not written by this script (no "
              f"{EXT_PREFIX}… external_id). A push leaves them alone; --wipe deletes them.")


def push(creds, aid, workouts, dates, wipe_foreign=False):
    """Write the week, updating in place. Every event carries our external_id and goes
    through the bulk endpoint with upsert=true, so a session pushed twice lands on the
    same row and keeps its provider event id instead of being replaced by a new one."""
    ext_ids = with_external_ids(workouts)
    payload = [
        {
            "category": "WORKOUT",
            "type": w.get("type", "Run"),
            "start_date_local": f"{w['date']}T00:00:00",
            "name": w["name"],
            "description": w.get("description", ""),
            "tags": event_tags(w),
            "external_id": x,
        }
        for w, x in zip(workouts, ext_ids)
    ]
    # upsert=true is what makes a re-push an update: the provider matches on external_id
    # and rewrites that row instead of adding another, so the event id survives.
    r = requests.post(f"{BASE}/athlete/{aid}/events/bulk", params={"upsert": "true"},
                      json=payload, auth=creds, timeout=60)
    check(r)

    # Report the id the provider came back with, since "one session, one id across a
    # rewrite" is the whole point and is worth being able to see rather than assume.
    try:
        returned = {ev["external_id"]: ev.get("id") for ev in r.json()
                    if isinstance(ev, dict) and ev.get("external_id")}
    except (ValueError, TypeError, AttributeError):
        returned = {}
    for w, x in zip(workouts, ext_ids):
        got = returned.get(x)
        seen = f"   id={got}" if got is not None else ""
        print(f"pushed {str(w['date'])}  {role_cell(w)}  {name_line(w['name'])}{seen}")
    if not returned:
        print("  note: the bulk response carried no event ids to show — check --status.")

    reconcile(creds, aid, dates, set(ext_ids), wipe_foreign)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("week_file", help="e.g. weeks/2026-W30.yaml")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--wipe", action="store_true",
                    help="after the push, also delete workouts on these dates that this "
                         "script did not write (legacy or hand-made entries). A plain "
                         "re-push already updates ours in place, so this is rarely needed")
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
        for w, ext in zip(workouts, with_external_ids(workouts)):
            tags = event_tags(w)
            extra = f"   tags: {', '.join(tags[1:])}" if len(tags) > 1 else ""
            print(f"[dry-run] {str(w['date'])}  {role_cell(w)}  "
                  f"{name_line(w['name'])}{extra}")
            print(f"  external_id: {ext} (a re-push updates this event, keeping its id)")
            print("  " + w.get("description", "").replace("\n", "\n  ").rstrip())
        return

    creds, aid = get_auth()
    date_guard(data.get("week"), dates, args.allow_past, enforce=True)

    push(creds, aid, workouts, dates, wipe_foreign=args.wipe)

    print(f"\nDone — {len(workouts)} workouts on intervals.icu; Garmin Connect picks them up shortly.")


if __name__ == "__main__":
    main()
