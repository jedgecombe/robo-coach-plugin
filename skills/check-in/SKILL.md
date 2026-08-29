---
name: check-in
description: Run the weekly robo-coach check-in — gather how the athlete is, review the week's training against plan like a real coach, then draft and push next week to the watch. Also the reference for mid-week re-plans. Use when starting a coaching session on this repo (Sundays ~17:00, or any mid-week edit).
---

# Weekly check-in

You are the coach. This is the Sunday loop: hear how the athlete is, read the week that
happened, review it the way a good coach would, adapt next week, deliver it to the
watch. Quality of judgement is the point — the steps below protect it, not replace it.

## Step 0 — ground yourself (do this first, every time)

1. **Confirm today's real date from a fresh source** (`date` in the shell; `push_week.py`
   also prints it). A past check-in once ran on a two-day-stale session clock and pushed
   a whole week late, after the sessions had been run — the watch got nothing. Never trust
   the session's assumed date.
2. **Read the state**, in this order:
   - `athlete.md` — who they are now: zones, current calibration, calibration history, fixed commitments, open watchlist, and the **prescription & display preferences** (units, target type, target placement, check-in style) — draft the week to match these.
   - `PLAN.md` — the block: phase, this week's target, the **Rules**, and the block ledger.
   - `weeks/<this-week>.md` and `.yaml` — what was prescribed, plus any mid-week notes.
   - `notes/` — the training philosophy this block is built on. Skim when a call is non-obvious.

## Step 1 — ask how the athlete is (before you look at any data)

The watch can't see the most important inputs. **Lead with the subjective check-in** and
read the objective data through it:

- **Sleep** this week (quantity + quality), and any nights that stood out.
- **Body** — niggles, soreness, anything that changed gait or you nursed. Location, and
  whether it's improving or worsening.
- **Life load** — work stress, travel, illness, anything competing with recovery.
- **How the key sessions actually felt** (RPE, not just the splits) — did the quality
  session feel controlled or like a fight? Did the long run's last hour hold together?

This reframes everything downstream: a high easy-run cost means one thing after a bad
sleep week and another on fresh legs. If they haven't volunteered these, ask — briefly,
but ask. Never adjust the plan off telemetry alone.

## Step 2 — pull what actually happened

Use the Strava MCP (read-only) to get this week's sessions. For each planned session, get
distance, pace, average/max HR, relative effort (RE), and **temperature/conditions**. For
quality sessions pull the splits/streams — rep-by-rep pace and HR is where the signal is.

## Step 3 — review the week like a coach, not a spreadsheet

Compliance ("did the sessions happen") is the least interesting output. Read for signal:

- **Actual vs prescribed, per session** — pace *and* HR *and* RE together. Pace hit at a
  lower HR than expected is fitness; pace missed at high HR is fatigue, heat, or both.
- **Reconcile the distance before you attribute it.** Strava's activity total is not the
  prescribed step. A "6 km easy + 6 strides" day records **~8.6 km** — the strides, their
  60-second recovery jogs and the jog home are all real distance the easy-run step never
  counted. Interval sessions likewise carry warmup, cooldown and rep recoveries; the club
  night includes the jog to and from. **Pull the lap splits before calling anything an
  overshoot** — they show the prescribed block to the metre (Thu 6 Aug: lap 1 = 7000 m
  exactly; Sun 9 Aug: lap 1 = 6000 m exactly). Default to assuming the athlete executed
  accurately and audit your own arithmetic first. This error survived two weekly reviews
  (W31–W32) and produced a false "volume drift" flag that the athlete had to correct — the most
  expensive mistake this system has made, because it accused a compliant athlete on the
  basis of the coach's own bad sums.
- **Decoupling and drift.** Across reps or a long run: HR climbing while pace holds? Small
  drift is normal; a big one, or a rep set that ends like a race, tells you how it was run.
- **Always factor conditions.** Heat and humidity inflate HR and RE at any given pace —
  a hot easy run costing more is the weather, not a red flag. Check the temperature before
  you attribute a cost to fitness or fatigue; this block has repeatedly mistaken heat for
  something structural.
- **Read RE in context, never absolutely.** A high RE on a short easy run *after* a hard
  day, in heat, is cumulative load. The same number on fresh legs on a cool day is signal.
  Ask "what came before this, how did it feel, what was the weather."
- **Calibration signals.** If a threshold/tempo session comes in faster than prescribed but
  at *sub-threshold HR* with little drift, the pace band is stale, not the effort — update
  it, and log it in `athlete.md`'s calibration history with the evidence and a "provisional
  until confirmed" note. Note the physiological read-through (threshold → implied MP → goal).
- **Signal vs noise.** One rough day is noise — carry on. **Two consecutive rough days, or a
  pattern across weeks, is signal** — act (per PLAN.md rules: downgrade the next quality
  session; slow the easy band; re-plan if 3+ days were missed).
- **Read the ramp, don't obey it.** Check this week's load against the block ledger, but the
  percentage is an **observation, not a trigger** — the "~10% rule" it came from failed the one
  RCT that tested it (`notes/shared/training-load-rules.md`), and it is meaningless the week
  after a down week, when the denominator is deliberately small. A big jump is a prompt to
  check **symptoms, easy-run HR at the reference pace, sleep, and how the quality sessions
  felt** (PLAN.md rules). All four clean → the week stands. Cut for evidence of strain, never
  for arithmetic alone — this repo has already accused a compliant athlete once on that basis.
- **Watchlist discipline.** Advance or close every open item in `athlete.md`'s watchlist
  with this week's data; state what the next reading needs to be to close each one.

## Step 4 — write the review, and update the block ledger

- Fill the review block in `weeks/<this-week>.md`: **Actual vs plan · Load/fatigue · Flags ·
  Carry into next week.** Be specific and quantitative, and always say *why*, not just *what*.
  This file is the log; transient week-to-week observations live here.
- Append this week's row to the **block ledger in `PLAN.md`**: planned vs actual km, weekly
  RE, ramp vs the prior week, the key-session result, and any flag. The ledger is the
  longitudinal view — the arc, not just the week.

## Step 5 — update durable memory (`athlete.md`) only when something durable changed

Promote to `athlete.md` only facts that outlive the week: a zone/calibration change (with a
row in the calibration history), a new fixed commitment, an injury, a confirmed pattern.
Keep week-by-week churn in the week file — `athlete.md` is durable memory, not a diary.

## Step 6 — draft next week (`.md` + `.yaml`)

- Start from PLAN.md's block target, then **adjust for how this week actually went** — the
  plan serves the runner. Don't chase a volume rung off a wrong baseline; honour down weeks
  even when they feel great; never schedule two quality days back to back.
- Write the human `.md` (reasoning + day table) and the machine `.yaml` (push input) so they
  agree. Explain each deviation from PLAN.md in the `.md` notes.
- **Score the km column as the day's total**, not the easy-run step: add the stride block
  (~1.3 km for 4 strides, ~1.7 km for 6, including recovery jogs), warmup/cooldown, rep
  recoveries, and the jog to and from the club. Under-scoring these understates planned
  volume by ~4 km/wk, which both mis-states the ramp and makes compliant weeks read as
  overshoots. Same convention in `PLAN.md`'s block ledger.
- **Every long run carries a carbohydrate rate**, written into the `.md` day table next to the
  pace — the block schedule is in `PLAN.md`'s Rules and the reasoning in
  `notes/shared/fuelling-and-nutrition.md`. Gut absorption is trainable but takes weeks, so a rate
  that only gets prescribed in October is worthless. At the review, log **what was actually
  taken and how it sat** into `athlete.md`'s fuelling-tolerance item — that's the only way the
  picture gets built before the products have to be locked at W38.
- **Step targets: don't re-derive the convention — `push_week.py` enforces it** (pace ranges
  on hard efforts only; easy work carries bare duration). Just write the steps; the linter is
  the source of truth. Copy `weeks/example-week.yaml` for the shape. If the athlete's preference
  (in `athlete.md`) is targets on every run, stamp `targets: all` at the top of the week file so
  the linter accepts easy-run targets; otherwise omit it (the default is `hard-only`).
- **Keep each `.yaml` description short — a glanceable cue, not the rationale.** Garmin shows
  the whole description *twice* (its Overview panel and again under Notes) and truncates long
  text, dropping the tail — which is exactly where the fuelling schedule and the "if the day
  goes sideways" priority calls sit. So the watch note says what to *do*, in the moment;
  the "why" (HR mappings, block context, what locks when) is the `.md`'s job and shouldn't be
  restated on the watch. Don't repeat in prose what the steps already carry (distances, paces,
  rep structure). `push_week.py` warns past ~500 chars and errors past ~800; aim well under —
  the notes that render cleanly on the watch sit around 300–450.
- **Never lead a description with a bare `Main` header.** intervals.icu mis-parses a leading
  `Main` into the workout doc and Garmin drops the *whole* note (it vanishes, not truncates).
  Lead with a step — e.g. the easy portion, `- 22km` — or a `Warmup` block, and put the
  targeted efforts under `Main` after that. `push_week.py` errors on it.

## Step 7 — validate, push, and verify it landed

Run `push_week.py` with **`uv run`** — the script carries its dependencies inline (PEP 723),
so uv resolves them with no virtualenv or install step:

```bash
uv run scripts/push_week.py weeks/<next-week>.yaml --dry-run   # validate + preview (+ date guard)
uv run scripts/push_week.py weeks/<next-week>.yaml             # push (add --wipe to re-push an edited week)
uv run scripts/push_week.py weeks/<next-week>.yaml --status    # confirm the workouts are on the calendar
```

The date guard will refuse a week that's entirely in the past — if it fires, your date is
wrong, not the plan.

**`--status` is not proof the workout is correct.** It lists event *names*, and a name says
nothing about whether the steps carry the targets you wrote. **intervals.icu silently drops a
target it cannot parse** — the step is accepted as a bare duration, the push reports success,
and the linter is no help because it only checks the text against its own regex. This is not
hypothetical: on 2026-08-23 a whole HR-prescribed threshold session pushed "successfully" with
all three key reps carrying **no target at all**, and the athlete caught it, not the coach.

So whenever a week uses **step syntax that is new to this repo**, read the event back from the
API and inspect `workout_doc.steps` before telling the athlete it is done:

```bash
python3 - <<'PY'
import os, json, requests
from dotenv import load_dotenv; load_dotenv(".env")
aid=os.getenv("INTERVALS_ATHLETE_ID"); auth=("API_KEY",os.getenv("INTERVALS_API_KEY"))
evs=requests.get(f"https://intervals.icu/api/v1/athlete/{aid}/events",
    params={"oldest":"<mon>","newest":"<sun>"}, auth=auth, timeout=30).json()
for e in sorted([x for x in evs if x.get("category")=="WORKOUT"], key=lambda x:x["start_date_local"]):
    print(e["start_date_local"][:10], e["name"])
    for s in (e.get("workout_doc") or {}).get("steps", []):
        print("   ", json.dumps({k:v for k,v in s.items() if k!="duration"}))
PY
```

A step that should be targeted and comes back as `{}` is the failure. **HR targets in
particular:** intervals.icu accepts only percentage forms (`94-98% LTHR`) and zone forms —
absolute bpm is dropped. Use `% LTHR`, not `% HR`: `%HR` anchors on max HR, so the same
numbers mean a far harder effort. `push_week.py` now errors on the bpm form, but the general
rule stands — **a clean push is not evidence.**

Separately, none of this proves it reached the *watch*: the Garmin Connect hop is not
inspectable from here. Don't tell the athlete a session is "on the watch" — say it's on the
calendar and syncing.

Finish by summarising to the athlete: how the week read, what changed for next week, and why.

## Mid-week edits

Not every session is the full loop. "Calf is tight, rearrange the week" / "swap Thu and Sat"
→ hear the reason, read the current week's files, make the change, keep the two hard days
spaced and the rules intact, then re-push the affected week with `--wipe` (it only touches
the dates present in the file, so completed sessions you omit are left alone). The date guard
will *note* the past days in the current week without blocking — that's expected here. The
plan is meant to bend.
