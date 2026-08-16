---
description: Scaffold a personal robo-coach training repo in the current directory — copies the templates and scripts, wires up privacy protection, and points you at the next steps.
argument-hint: "[target directory — defaults to the current one]"
---

You are setting up a new **robo-coach** training block for the user. The coaching brain
(the `check-in` skill, the push/lint/privacy scripts) ships with the plugin; this command
lays down the user's own repo — the private plan and athlete files — around it.

Work in the current directory unless the user named another in `$ARGUMENTS`. Confirm before
anything irreversible, and **never type the user's API keys or personal identifiers
yourself — ask them to paste those in.**

## 1. Ground the directory

- Confirm where the user wants this repo. It will hold **personal training data** and must
  stay private — not a fork of a public repo.
- If it isn't a git repo yet, run `git init`.

## 2. Lay down the shared files

Copy from `${CLAUDE_PLUGIN_ROOT}/templates/` into the repo (mind the renamed dotfiles):

| From (`templates/`) | To |
|---|---|
| `CLAUDE.md` | `CLAUDE.md` — the operating manual (describes the system, never the athlete) |
| `PLAN.example.md` | `PLAN.example.md` |
| `athlete.example.md` | `athlete.example.md` |
| `weeks/example-week.md` · `weeks/example-week.yaml` | `weeks/` |
| `notes/shared/` (both `.md` files) | `notes/shared/` — the generic training philosophy the check-in skill cites |
| `env.example` | `.env.example` |
| `gitignore` | `.gitignore` |

And copy the scripts so they live in the repo (the check-in skill and the git hook call them by path):

- `${CLAUDE_PLUGIN_ROOT}/scripts/push_week.py` → `scripts/push_week.py`
- `${CLAUDE_PLUGIN_ROOT}/scripts/check_privacy.py` → `scripts/check_privacy.py`

**No dependency install step.** `push_week.py` carries its dependencies inline (PEP 723), so
`uv run scripts/push_week.py …` resolves them on its own — no virtualenv, no `pip`, no
`requirements.txt`. Just make sure the athlete has **uv** installed
(`curl -LsSf https://astral.sh/uv/install.sh | sh`, or `brew install uv`). `check_privacy.py`
is pure standard library and runs under plain `python3`.

## 3. Interview the athlete, then write their private files (gitignored)

Create the private files from the templates **only if they don't already exist** — never
clobber an athlete's filled-in files. If they're already present, this is a re-run: skip the
copy and edit in place.

```bash
[ -f PLAN.md ]    || cp PLAN.example.md PLAN.md
[ -f athlete.md ] || cp athlete.example.md athlete.md
```

Then **interview the athlete** — ask in small groups, offer the default in `[brackets]` so they
can just accept, and write the answers into `athlete.md` (preferences + physiology) and `PLAN.md`
(race, structure, rules). It's a conversation, not a form — don't dump every question at once.

**Units & device**
- Distance & pace — km (min/km) or miles (min/mile)? `[km]`
- Watch model? (Week 1 doubles as pipeline calibration; step rendering sometimes needs a tweak.)

**How workouts are prescribed**
- Primary target on hard efforts — pace, heart rate, power, or effort/RPE only? `[pace, HR as context]`
- Reps/blocks by time or distance? `[time for short reps, distance for long blocks — or mixed]`
- Where targets show on the watch:
  - **every step** — easy runs also show a pace/HR band `[default]`, or
  - **hard efforts only** — easy runs carry a bare duration, pace guidance lives in the prose.
    If they choose this, write `ROBO_COACH_TARGETS=hard-only` into `.env` (durable, repo-wide);
    a single week can still override per-file with a top-level `targets:` key.
- Easy-run guidance style — pace band, HR ceiling, or RPE/"conversational"? `[RPE + prose]`

**Check-in style**
- Lead with how it *felt* (effort/RPE) before the data, or data-first? `[effort-first — the skill is built on this]`
- Depth — brief summary or full reasoning? `[brief, expand on request]`
- Check-in day + time? `[Sunday ~17:00]`

**Goal & race** → `PLAN.md`
- Race name, date, start time, distance, terrain · goals A/B/C · a tune-up race ~3 weeks out?

**Physiology & zones** → `athlete.md`
- Age band, weight (weight feeds the fuelling g/kg math).
- HR: max, resting, threshold. Pace: threshold, current MP, an easy reference pace **and the HR
  it sits at** (the calibration anchor the check-in reads drift against).
- Recent PBs and how/when set.
- If they don't know their zones/threshold cold, offer to **derive a first cut** from a recent
  race result or a recent hard effort on Strava (pace + HR) rather than leaving them blank — a
  rough anchor the check-in refines beats no anchor.

**Week structure** → `PLAN.md` skeleton + `athlete.md` commitments
- Runs/week, peak volume, rest day, long-run day, quality day(s).
- Fixed commitments — club nights, group runs. Strength — in the plan (which days) or self-managed?

**Rules & fuelling** — the templates ship sensible, evidence-tagged defaults (down-week cadence,
missed-days policy, "pain that changes gait ends the run," the fuelling carb-rate progression in
`notes/shared/`). Walk the athlete through them, adjust to their case, and keep the
`[evidence]` / `[convention]` / `[preference]` tags honest — don't dress a preference up as science.

**Credentials & privacy**
- `[ -f .env ] || cp .env.example .env`, then have the athlete **paste** their intervals.icu
  API key + athlete id into it. **Never type these yourself — ask them to paste.**
- Create `.privacy-markers` (gitignored) — the athlete's name, email, and any place/club/team
  names that must never reach a shared file, one per line. This powers the content scan.

## 4. Install the privacy pre-commit hook

Install a small wrapper — more robust than a symlink: no dependency on the script's exec bit,
and it resolves the repo root even from a subdirectory or a worktree:

```bash
HOOK="$(git rev-parse --git-path hooks)/pre-commit"
cat > "$HOOK" <<'SH'
#!/bin/sh
exec python3 "$(git rev-parse --show-toplevel)/scripts/check_privacy.py"
SH
chmod +x "$HOOK"
python3 scripts/check_privacy.py --all
```

The audit should report clean. If it flags anything, fix it before the first commit. If the
athlete already has a `pre-commit` hook, **don't clobber it** — add the `check_privacy.py` call
to their existing hook instead.

## 5. Connect the pipes (one-time, the user does this)

Point the user at the plugin README's "One-time setup": create an intervals.icu account,
connect Garmin Connect (and optionally Strava), copy the API key into `.env`. Then draft
their first week and dry-run it:

```bash
uv run scripts/push_week.py weeks/<YYYY-Www>.yaml --dry-run
```

## 6. Hand off

Two last things:

- **Strava read access.** The check-in pulls what the athlete actually ran from Strava via an
  MCP connector — confirm they've connected one (see the plugin README). Without it, the
  check-in can only work from what they tell it.
- **The weekly loop.** Open a session on this folder and invoke the **`check-in`** skill (their
  chosen day/time, or any mid-week re-plan). It's interactive by design — it leads with how
  they're feeling before it reads any telemetry.

To pull plugin updates later (script fixes, refreshed examples) without touching their private
files, they run **`/robo-coach:update`**.
