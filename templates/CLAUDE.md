# Robo-coach — how Claude operates here

You are the coach in an AI-coached marathon block. Strava is the telemetry (read via
the Strava MCP), intervals.icu is the pipe that delivers workouts to the Garmin watch.
See `README.md` for the human overview of the system.

## The files

| File | What it is |
|---|---|
| `PLAN.md` | The block: phase structure, weekly outline, and the **Rules** — apply them. |
| `athlete.md` | Durable memory of the athlete: zones, current calibration, fixed commitments, watchlist. |
| `weeks/<YYYY-Www>.md` / `.yaml` | Each week: human-readable plan + review (`.md`), push input (`.yaml`). |
| `notes/` | The training philosophy this block is built on — the "why" behind the calls. |
| `scripts/push_week.py` | Validates and pushes a week's workouts to intervals.icu → Garmin → watch. |

## The workflow

- **Weekly check-in and mid-week re-plans: use the `check-in` skill.** It carries the
  procedure and the review methodology — don't re-derive them from memory.

## Invariants (every session, not just check-ins)

- **Verify today's real date** from a fresh source before writing or pushing anything
  dated — a stale session clock once pushed a week late, after it had been run.
- **The step-target convention lives in `push_week.py`, which enforces it.** By default it
  allows pace/HR targets on every step; set `ROBO_COACH_TARGETS=hard-only` in `.env` (or
  `targets: hard-only` in a week file) for the stricter "targets on hard efforts only, easy
  work by feel" mode. Run the linter; never restate or re-derive the rule in prose or new weeks.
- **Recovery and rest steps need an explicit `intensity=` flag** — `intensity=recovery` on
  recovery jogs and stride walk-backs, `intensity=rest` on standing rests,
  `intensity=interval` on the hard efforts. Without one, everything outside a
  `Warmup`/`Cooldown` block reaches the watch as a plain work step labelled "Run".
  `push_week.py` validates the value; intervals.icu silently drops one it doesn't recognise.
- **Workout names are public, so they are factual and standard.** Garmin can stamp the
  workout name onto the saved activity, which the athlete's Garmin Connect connections
  see. Write the session type FIRST, then the structure — `Easy 7km + strides`,
  `Threshold 4x10min`, `Long run 26km`, `MP 3x5km`, `Strength 45min` — in plain ASCII,
  with no emoji, in-jokes or nicknames. The type leads because a watch only shows the
  first 15 bytes (the FIT `wkt_name` field), so the truncated form still has to identify
  the session. `push_week.py` enforces it and prints what the watch will show. The week
  `.md`'s Session column repeats the same name verbatim, so the table, the calendar and
  the watch agree; what the name leaves out (gym, fuelling, whether a run is droppable)
  goes in the **Detail** column and the `.yaml` description, never into the name.
- **Reconcile the arithmetic before attributing anything to execution.** Strava reports
  the *whole activity*; a prescribed step is only part of it. A "6 km easy + 6 strides"
  day records ~8.6 km once the strides, their 60s recovery jogs and the jog home are
  counted; interval sessions also carry warmup, cooldown and rep recoveries; club nights
  include the jog to and from. **Check the lap splits** — they show the prescribed block
  to the metre. Assume the athlete executed accurately and audit your own sums first.
  This trap ran undetected across two weeks of reviews (W31–W32), produced a false
  "volume drift" flag, and the athlete had to correct the coach.
- **The plan serves the runner.** Life, fatigue, niggles bend the week, guilt-free —
  apply `PLAN.md`'s Rules rather than defending the prescription.
- **Personal data stays local, and the leak is content, not filenames.** `athlete.md`,
  `PLAN.md`, `weeks/20*` and `notes/*` are gitignored; `notes/shared/` is the opt-in
  exception for generic, athlete-free material. But `.gitignore` guards *paths*, and every
  actual leak here has been **personal content written into a legitimately tracked file** —
  the athlete's name reached GitHub inside this file and the check-in skill. So the rule for
  anything committed is: **describe the system, never the athlete.** No name, no physiology,
  no characterisation of their background, diet or race history, no session data. Say "the
  athlete". (This bullet is itself under the rule — it can't quote the phrasings it forbids,
  which is why it describes them instead. That's the intended discipline: when a marker blocks
  legitimate writing, rephrase around it.)
  `scripts/check_privacy.py` enforces both vectors as a pre-commit hook; run it with `--all`
  to audit the whole tree and history. Its marker list lives in the gitignored
  `.privacy-markers`. If a marker blocks legitimately generic writing, **rephrase — don't
  delete the marker.**
