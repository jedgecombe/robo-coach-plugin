# robo-coach (Claude Code plugin)

An AI endurance coach for Claude Code. Claude is the coach, **Strava** is the telemetry it
reads, **intervals.icu** is the pipe that delivers workouts to your **Garmin** watch.

```
Garmin watch ──▶ Strava                         (automatic, once connected)
Strava + your files ──▶ Claude check-in         (weekly: review the week, adapt the next)
next week (yaml) ──▶ intervals.icu API ──▶ Garmin Connect ──▶ watch prompts each session
```

The plugin ships the **coaching discipline** — the weekly check-in methodology, the workout
push script with its guardrails, and the privacy tooling. **You** supply the athlete: your
plan, your zones, your week files. Those stay local and gitignored; the plugin never contains
anyone's training data.

## What's in the box

| Component | What it does |
|---|---|
| `check-in` skill | The weekly loop: hear how you are → review the week like a coach → adapt next week → push it to the watch. Also the reference for mid-week re-plans. |
| `/robo-coach:setup` command | Scaffolds a personal training repo from the templates and wires up privacy protection. |
| `scripts/push_week.py` | Validates and pushes a week's workouts to intervals.icu. Enforces the step-target convention and guards against pushing a week that's already in the past. |
| `scripts/check_privacy.py` | Pre-commit hook + auditor: refuses to commit personal data (by path *and* by content). |
| `templates/` | The shape of every file you own — `CLAUDE.md`, `PLAN.example.md`, `athlete.example.md`, example weeks, `.env.example`, `.gitignore`. |

## Install

```bash
/plugin marketplace add jedgecombe/robo-coach-plugin
/plugin install robo-coach@robo-coach
```

(Or point the marketplace at a local clone: `/plugin marketplace add /path/to/robo-coach-plugin`.)

## Quick start

**Requirements:** [uv](https://docs.astral.sh/uv/) (runs `push_week.py` with no venv or install
step — `curl -LsSf https://astral.sh/uv/install.sh | sh`, or `brew install uv`) and `python3`
(for the privacy hook; standard library only). Plus a Garmin watch, intervals.icu, and Strava.

1. Make a new **private** directory for your training block and `cd` into it.
2. Run `/robo-coach:setup` — it copies the templates and scripts, interviews you to fill in your
   gitignored `PLAN.md` / `athlete.md` / `.env`, and installs the privacy hook.
3. Do the one-time intervals.icu setup below.
4. Draft your first week, dry-run it, then push. From then on, run the weekly `check-in`.

After a plugin update, run `/robo-coach:update` to re-sync the vendored scripts and examples
into your repo (it never touches your plan, data, or `.env`).

## Weekly loop

Open a Claude session on your training folder and invoke the **`check-in`** skill (weekly, or
any time you need a mid-week re-plan). It's **interactive by design** — it leads with the
subjective read (sleep, niggles, life load, how the sessions felt) *before* it looks at any
telemetry, because the plan is never adapted off the watch data alone. There's deliberately no
"run it unattended on a schedule" mode: an automated run couldn't have that conversation, which
is the part that matters.

## Reading your week (Strava)

The check-in pulls what you actually ran from **Strava**, read through an MCP connector — so
connect a Strava MCP in Claude (via your connector settings) before your first check-in.
Without it, Claude can't see your activities and can only work from what you tell it. Your
Garmin pushes to Strava automatically once the two are linked, so nothing else is needed here.

## One-time setup (intervals.icu ↔ Garmin, ~10 min)

1. Create a free account at [intervals.icu](https://intervals.icu).
2. intervals.icu **Settings** → connect **Garmin Connect** (enables workout → watch sync).
   Optionally connect Strava too.
3. In Garmin Connect, approve the intervals.icu permission to write workouts/training.
4. intervals.icu **Settings → Developer** → copy the **API key**. Your athlete id is in the
   URL when logged in (`i…`).
5. Paste both into `.env` (created by setup from `.env.example`).
6. Draft `weeks/YYYY-Www.yaml` (copy `weeks/example-week.yaml` for the shape), then:

```bash
uv run scripts/push_week.py weeks/YYYY-Www.yaml --dry-run   # validate + preview
uv run scripts/push_week.py weeks/YYYY-Www.yaml             # push
uv run scripts/push_week.py weeks/YYYY-Www.yaml --status    # confirm it's on the calendar
```

7. Check one workout renders correct steps in the intervals.icu calendar and appears in Garmin
   Connect.

*Garmin's official workout-push API is partner-only, which is why intervals.icu is the bridge —
it's free and officially integrated with Garmin.*

## Privacy model — share the system, never the athlete

The whole design keeps your data on your machine. `athlete.md`, `PLAN.md`, `weeks/20*` and
`notes/` are gitignored; only the generic `*.example.*` shapes are meant to be shared.

But `.gitignore` guards *paths*, and the likelier leak is personal content written into a file
that is legitimately tracked. So `check_privacy.py` scans both — forbidden paths, and forbidden
strings (your name, email, places) anywhere in staged content. Install it as a pre-commit hook
(the setup command does this for you):

```bash
# a robust pre-commit hook (setup does this for you)
printf '#!/bin/sh\nexec python3 "$(git rev-parse --show-toplevel)/scripts/check_privacy.py"\n' \
  > "$(git rev-parse --git-path hooks)/pre-commit"
chmod +x "$(git rev-parse --git-path hooks)/pre-commit"

python3 scripts/check_privacy.py --all       # audit tree content + history
python3 scripts/check_privacy.py --history   # history content only ("can I publish this?")
```

The marker list lives in `.privacy-markers` (itself gitignored). Anything you commit should
**describe the system, never the athlete.**

> **If you publish your own training repo,** remember `.gitignore` and the auditor only see the
> *current* tree. Git *history* can still hold data from before you scrubbed it. Start any repo
> you intend to make public from a clean history, and confirm with a history-content scan, not
> just `check_privacy.py --all`.

## Developing / validating

`./validate.sh` checks the whole plugin builds as expected — manifests, structure, the official
`claude plugin validate` (if the CLI is installed), that the scripts compile, that `push_week.py`
runs self-contained via `uv run`, and a full end-to-end setup simulation (scaffold a throwaway
repo exactly as `/robo-coach:setup` does, then prove the privacy hook blocks a leaking commit).
It exits non-zero on any failure. CI runs it on every push (`.github/workflows/validate.yml`).

```bash
./validate.sh
```

## License

MIT
