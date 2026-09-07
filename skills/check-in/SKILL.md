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
- **Step targets: don't re-derive the convention — `push_week.py` enforces it.** Just write the
  steps; the linter is the source of truth. Copy `weeks/example-week.yaml` for the shape. The
  default is `all`: pace/HR targets are accepted on every step, so a week that wants them
  everywhere needs no stamp. If the athlete's preference (in `athlete.md`) is the stricter
  "targets on hard efforts only" — easy work carrying a bare duration, its pace guidance living
  in the prose — stamp `targets: hard-only` at the top of the week file, or set
  `ROBO_COACH_TARGETS=hard-only` in `.env` to make it the durable per-repo setting.
- **Flag every recovery and rest step with `intensity=`.** Without it, every step outside a
  `Warmup`/`Cooldown` block reaches the watch as a plain work step — the 90-second jog between
  reps shows on the Garmin as "Run", indistinguishable from the rep before it. Append
  `intensity=recovery` to recovery jogs and stride walk-backs, `intensity=rest` to standing
  rests, and `intensity=interval` to the hard efforts. `push_week.py` rejects a value
  intervals.icu doesn't accept — it silently drops unrecognised ones — and warns when a step
  labelled "recovery" carries no flag.
- **Give every workout a `role:`.** It's pushed as a `nocoach:<role>` tag on the calendar
  event and it is the *only* record of what the session was for — the name is free text and
  distance says nothing (one athlete's long run is another's easy run), so nothing reading the
  week back can infer it. An untagged week doesn't read as "unlabelled", it reads as a claim
  about the athlete: the key count comes back unknown, the morning after a threshold can't be
  told from recovered legs, and a race in the window is invisible to the taper and post-race
  rules. The ten, exactly as written (lowercase, and `tune_up` has an underscore): `key`,
  `long`, `easy`, `recovery`, `social`, `race`, `tune_up`, `strength`, `rest`, `other`. Pick
  the one that matches what the session is *for*, not what it looks like — a club night is
  `social` (its stoppage and pace are not read), a parkrun used as a data point is `tune_up`,
  and `other` is the escape hatch so "no role" never has to be. `push_week.py` warns on a
  missing role and pushes that workout untagged rather than defaulting it — an unlabelled
  `key` session defaulted to `other` would make the week's key count a confident wrong
  number, where untagged makes it an honest unknown. A **near-miss** like `Long` or
  `tune-up` is an error, though: it reads downstream as no role at all while leaving you
  believing the week is labelled. The athlete's own `tags:` may sit alongside; never
  hand-write a `nocoach:` one. **The week `.md`'s Role column repeats it**, so the two agree
  and the week is reviewable at a glance — count the `key` rows against the ceiling and check
  none sit back to back before you push.
- **Name every workout factually — the name is the one field other people see.** Garmin's
  "Activity Name" display preference has a *Workout Name (when available)* setting that
  stamps the workout's name onto the **saved activity**, which the athlete's Garmin Connect
  connections see in their feed; the activity page shows it beside the workout's steps
  either way. Whatever you write is published under their account, so write it the way a
  coach writes a training log, not the way a running club names a group chat.
  **Format: session type FIRST, then the structure** — `Easy 7km + strides`,
  `Threshold 4x10min`, `Intervals 6x3min`, `Long run 26km`, `Long 26km + 3x3km MP`,
  `MP 3x5km`, `Recovery 6km`, `Hills 8x60s`, `Progression 16km`, `Strength 45min`,
  `Race 10km`. Plain ASCII, no emoji, no in-jokes, no nicknames, and nothing that
  identifies the athlete or anyone else. The type leads because **the watch shows only the
  first 15 bytes** — FIT stores `wkt_name` in a 16-byte field, so `Threshold 4x10min`
  arrives as `Threshold 4x10` (still informative) while a name that opens with mood or
  week-number arrives as noise. Garmin Connect keeps the full name; the watch does not.
  `push_week.py` enforces the type-first and ASCII rules, caps the name at 42 characters,
  and prints the truncated form so you can see what the watch will say.
- **Use the same name in the `.md` day table's Session column** — verbatim, in backticks.
  The two files are one week seen twice, so the Session column should be the thing you can
  match against the watch, the calendar and the review at a glance; a differently-worded
  label there means cross-referencing by memory. Anything the name leaves out — the gym
  session, whether a run is droppable, the fuelling rate — goes in the **Detail** column
  and the `.yaml` description, which is where that kind of specific already lives. So the
  Session column names the session and the Detail column qualifies it; don't editorialise
  in the Session column.
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
uv run scripts/push_week.py weeks/<next-week>.yaml --status    # confirm they're on the calendar, with roles
```

The date guard will refuse a week that's entirely in the past — if it fires, your date is
wrong, not the plan.

**`--status` is not proof the workout is correct.** It lists event names and the role tag read
back off each one — so it *does* prove the roles landed, and warns when any event carries none —
but a name says nothing about whether the steps carry the targets you wrote. **intervals.icu silently drops a
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
