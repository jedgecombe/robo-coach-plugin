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
| `scripts/push_week.py` | Validates and pushes a week's workouts to intervals.icu. Enforces the step-target and session-role conventions, and guards against pushing a week that's already in the past. |
| `scripts/check_privacy.py` | Pre-commit hook + auditor: refuses to commit personal data (by path *and* by content). |
| `templates/` | The shape of every file you own — `CLAUDE.md`, `PLAN.example.md`, `athlete.example.md`, example weeks, `.env.example`, `.gitignore`. |

## Install

The only thing you need to *install* it is **Claude Code** (desktop app or CLI) — it fetches and
runs the plugin for you. **You don't need git**, and there's nothing to clone by hand.

**Point-and-click (no terminal):** in the Claude Code desktop app, open the plugin browser with
`/plugin` → **Marketplaces** tab → add `jslug1000/robo-coach-plugin` → **Discover** tab →
select **robo-coach** → **Install**.

**Or by command** (in a terminal `claude` session, or typed into the app):

```bash
/plugin marketplace add jslug1000/robo-coach-plugin
/plugin install robo-coach@robo-coach
```

(Testing a local clone instead: `/plugin marketplace add /path/to/robo-coach-plugin`.)

## Quick start

**What you need:**
- **Claude Code** (desktop app or CLI) — to install and run the plugin. No git required.
- **[uv](https://docs.astral.sh/uv/)** — runs `push_week.py` with no venv or install step
  (`curl -LsSf https://astral.sh/uv/install.sh | sh`, or `brew install uv`). It also brings a
  modern Python along, so you don't have to manage one.
- **python3** — only for the privacy pre-commit hook (standard library; the system one is fine).
- **Accounts / hardware:** a **Garmin** watch, a free **intervals.icu** account, and **Strava** —
  all walked through in "One-time setup" below.

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

**One behaviour worth knowing.** intervals.icu *silently drops* a step target it can't parse —
the step is accepted as a bare duration and the push still reports success, so a session can
land on your watch with no target on it at all. `push_week.py` rejects the forms known to fail
(notably absolute-bpm heart-rate targets, which must be written as a percentage of threshold
HR, e.g. `94-98% LTHR`), and the check-in skill reads the workout back from the API to confirm
the targets survived. The same is true of the `intensity=` attribute that marks a step as a
recovery jog or a standing rest — an unrecognised value is dropped and the step lands on the
watch as a plain "Run" — so the linter checks that too. If you ever push hand-written step syntax, check the calendar entry
rather than trusting the "pushed" message.

**Re-pushing an edited week updates it, rather than replacing it.** Each workout goes up with
a stable `external_id` of its own through intervals.icu's upsert, so a session you edit and
re-push keeps its calendar event id instead of becoming a new row. That matters to anything
reading the calendar back: a reader spots a removed session by re-reading a window of dates and
seeing what doesn't return, a comparison it can't safely make for the newest day in the window —
so a delete-and-recreate on the day you're editing leaves a phantom event in its copy until the
next day. Sessions you drop from a week file are removed after the push, and only ever ones this
script wrote — a hand-made entry on the same day is left alone. `--wipe` widens that clean-up
to entries this script didn't write, on the days the file names; it's for clearing out legacy
events. Every delete now happens *after* the write has landed, so a push that fails leaves the
calendar exactly as it was.

**Every workout also carries a role.** A one-word `role:` in the week file — `key`, `long`,
`easy`, `recovery`, `social`, `race`, `tune_up`, `strength`, `rest` or `other` — is pushed as a
`nocoach:<role>` tag on the calendar event. It's the only thing recording what a session was
*for*, because the workout name is free text and the distance says nothing (one runner's long
run is another's easy run), so nothing reading the week back can infer it. Without it a week
doesn't read as unlabelled, it reads wrong: no key-session count, no way to tell recovered legs
the morning after a hard day, a race just run left undetected, and a mid-week re-plan that
under-counts the quality already done and so permits more of it. `push_week.py` warns when a
workout has none and pushes it untagged — an honest unknown beats the wrong number you'd get
by defaulting it — and rejects near-misses like `Long` or `tune-up`, which would read as no
role while looking labelled. `--status` reads the tags back off the calendar so you can check
they landed.

**And one that's social rather than technical.** The workout *name* is the field other
people end up seeing: Garmin's "Activity Name" display preference can stamp it onto the
saved activity, which your Garmin Connect connections see in their feed. So names here are
factual and standard — session type first, then the structure (`Threshold 4x10min`,
`Easy 7km + strides`, `Long run 26km`) — in plain ASCII, and `push_week.py` enforces that.
Type-first also survives the watch: Garmin Connect keeps the full name, but the FIT
`wkt_name` field is 16 bytes, so the watch itself shows only the first 15 and the linter
prints the truncated form alongside each workout.

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
uv run scripts/push_week.py weeks/YYYY-Www.yaml --status    # confirm it landed, with roles
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
python3 scripts/check_privacy.py --mode      # which mode is active, and why
```

### If your training repo is a private backup instead

Some people would rather keep the athlete data *in* git — a private repo as an off-machine
backup, with the coaching system living here in the plugin. That inverts the rule above, and
running the strict checks against it fails on every single commit. **A hook that always fails
is a hook you learn to bypass**, which is worse than having no hook, so the mode is explicit.
Declare it in `.privacy-mode` at the repo root:

```
private-data
verified-private: https://github.com/you/your-training-repo.git
```

**No `.privacy-mode` file means `shareable`** — the strict mode is the default, so a repo that
hasn't declared itself private is guarded as though it were about to be published. The mode is
never inferred from repo contents; "looks private" is not a security property.

`private-data` turns off the personal-path and marker checks, and turns on the one that matters
once your data is tracked: **every push remote must be pinned as `verified-private`**. The hook
has no network and no credentials, so it can't ask GitHub whether your repo is private — a check
that silently passes when it can't verify is worse than useless. Instead the claim is written
down and pinned to a URL, so adding a remote, changing `origin`, or copying the config into
another repo all break the pin and fail the check. Confirm it in the host's UI before writing
the line.

Secrets are refused in **both** modes. `.env` holds a live intervals.icu API key, and private
today is not private after a fork, a transfer, or an accidental visibility flip — unlike
personal prose, a leaked key is exploitable by a stranger.

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
