# Changelog

All notable changes to the robo-coach plugin. This project follows
[semantic versioning](https://semver.org); the version here tracks
`.claude-plugin/plugin.json`. After updating the plugin, run
`/robo-coach:update` in your training repo to re-vendor the scripts and
templates.

## [0.1.5] — 2026-09-07

### Added
- **Privacy modes: `shareable` (default) and `private-data`.** `check_privacy.py` was built
  for one arrangement — a repo holding the coaching *system* with the athlete gitignored —
  but a private repo whose whole purpose is backing the athlete's data up inverts that rule,
  and the strict checks then fail on every single commit. **A hook that always fails is a
  hook you learn to bypass**, so the mode is now declared explicitly in `.privacy-mode` at
  the repo root. **No file means `shareable`**: the strict mode is the default, and the mode
  is never inferred from repo contents. `private-data` turns off the personal-path and
  marker checks and in exchange requires every git remote to be pinned as
  `verified-private: <url>` — a pre-commit hook has no network and no credentials, so it
  cannot ask the host whether a repo is private, and a check that silently passes when it
  cannot verify is worse than useless. Adding a remote, changing `origin`, or copying the
  config into another repo all break the pin. **Secrets are refused in both modes** — `.env`
  holds a live intervals.icu API key, and private today is not private after a fork, a
  transfer, or an accidental visibility flip. New `--mode` flag prints which mode is active
  and why.
- **Workout names are now a checked field, because they are the public one.** Garmin's
  "Activity Name" display preference has a *Workout Name (when available)* setting that
  stamps the workout's name onto the **saved activity** — the one an athlete's Garmin
  Connect connections see in their feed, and the one the activity page shows beside the
  workout's steps either way. Nothing in the plugin had ever said so, so names were
  freeform and a private joke could end up published under the athlete's own account.
  The house convention is now **session type first, then the structure**, in plain
  ASCII: `Easy 7km + strides`, `Threshold 4x10min`, `Long run 26km`, `MP 3x5km`,
  `Strength 45min`. `push_week.py` errors on a name that doesn't open with a known
  session type, on non-ASCII characters (emoji included), and past a 42-character cap.
  The `check-in` skill, the training-repo `CLAUDE.md` and the example week carry the
  convention; the example week's first session is renamed accordingly.
- **The week `.md`'s Session column now repeats the workout name verbatim.** The `.md`
  and the `.yaml` are one week seen twice, so a differently-worded label in the day table
  meant cross-referencing the plan, the calendar and the watch by memory. The Session
  column now names the session and the **Detail** column qualifies it — gym, fuelling
  rate, whether a run is droppable — which is where that specific already lived.
- **The push and dry-run output now show what the *watch* will display.** Garmin Connect
  stores the full name, but FIT allocates `wkt_name` as a 16-byte array
  (`FIT_WORKOUT_MESG_WKT_NAME_COUNT` in garmin/fit-c-sdk), so a device shows only the
  first 15 bytes. Each workout line now prints the truncated form next to the name when
  the two differ — which is the concrete reason the session type has to lead:
  `Threshold 4x10min` arrives as `Threshold 4x10` and still says what the session is.
  (intervals.icu itself imposes no limit — its OpenAPI spec types `name` as a bare
  string — so the constraint is entirely device-side.)

## [0.1.4] — 2026-09-01

### Fixed
- **Recovery steps now reach the watch as recovery.** intervals.icu passes Garmin's step
  intensity through only from an explicit `intensity=<value>` token, and the plugin never
  emitted one — so every step outside a `Warmup`/`Cooldown` block arrived on the watch as a
  plain work step, and the jog between reps was labelled "Run" exactly like the rep before
  it. The example week, the `check-in` skill and the training-repo `CLAUDE.md` now flag
  recovery jogs and stride walk-backs `intensity=recovery`, standing rests
  `intensity=rest`, and hard efforts `intensity=interval`.
- **The `check-in` skill stated the wrong default for step targets.** It told the coach the
  default was `hard-only` and to stamp `targets: all` for targets on every step — the inverse
  of `push_week.py`, which defaults to `all` and takes `hard-only` as the opt-in. A coach
  following the skill would have omitted the only stamp that changes anything, and silently
  got the permissive mode while believing the strict one was in force.

### Added
- **`intensity=` validation in `push_week.py`.** An unrecognised value (`intensity=recover`)
  and a spaced form (`intensity = recovery`) are both silently dropped by intervals.icu —
  the same failure class as absolute-bpm targets — so both are now errors. A step whose
  label reads "recovery"/"rest" but carries no flag raises a warning. Under
  `targets: hard-only`, a step flagged `intensity=recovery`/`rest` is held to the easy-step
  rule wherever it sits, not just inside an easy group. (Verified against the live
  intervals.icu API, 2026-09-01.)

## [0.1.3] — 2026-08-29

### Fixed
- **Reject descriptions that lead with a bare `Main` header.** intervals.icu mis-parses a
  leading `Main` into `workout_doc.description`, and Garmin then drops the *entire* note — it
  vanishes rather than truncating, which disguises it as a length problem. The linter now
  errors and points at the fix: lead with a step or a `Warmup` block, keeping the targeted
  efforts under `Main` after it. (Confirmed end-to-end against a live Garmin, 2026-08-29.)

## [0.1.2] — 2026-08-28

### Added
- **Workout-description length check in `push_week.py`.** Garmin echoes the whole
  description into both its Overview and Notes panels and truncates long text, so
  an over-long note silently loses its tail — where the fuelling schedule and the
  "if the day goes sideways" priority calls sit. The linter now warns past ~500
  characters and errors past ~800; the watch note stays a glanceable cue and the
  reasoning lives in the week's `.md`. The `check-in` skill documents the
  convention.

### Fixed
- **Reject HR targets that intervals.icu silently drops.** An absolute-bpm target
  (`168-175 HR`) parses to a bare duration with no target and reaches the watch
  empty, while the push still reports success. The linter now errors on the bpm
  form and points at the `% LTHR` percentage form intervals.icu actually accepts.

### Changed
- Plugin description refined — coach-style weekly review, corrected sync wording.

## [0.1.1] — 2026-08-16

### Added
- **Mandatory, self-verifying privacy safety net.** `/robo-coach:setup` installs
  the `check_privacy.py` pre-commit hook and proves it blocks a planted leak
  before it reports setup complete — a scaffolded repo that silently protects
  nothing is no longer possible.
- GUI-first install documentation, a prerequisites checklist, and a LICENSE.

## [0.1.0] — 2026-08-16

### Added
- Initial plugin: the `check-in` skill, the `push_week.py` / `check_privacy.py`
  scripts, the `setup` and `update` commands, and the training-repo templates.
