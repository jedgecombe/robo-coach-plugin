# Maintaining robo-coach

This repo is the single source of truth for the robo-coach **system** — the
`check-in` skill, the push/lint/privacy scripts, and the training-repo
templates. It is public and holds **no personal training data, ever** (see
[Privacy](#privacy)).

Everyone runs the plugin the same way, the maintainer included: install the
plugin, then keep private training data in a **separate local folder** the
plugin coaches against. That folder is never this repo.

## The two-repo model — why edits happen here, not downstream

- **This repo (public):** the system. Change it here, release it, done.
- **A training folder (private, per athlete):** `PLAN.md`, `athlete.md`,
  `weeks/`, `.env` — plus *vendored copies* of the scripts and templates that
  `/robo-coach:setup` lays down and `/robo-coach:update` refreshes.

The scripts and templates are **vendored** (copied) into the training folder
because the git pre-commit hook and the athlete's own `scripts/…` commands need
real in-repo paths, which a reference into the plugin's install dir can't give
(that path moves on every update). The trade-off is that those copies go stale
until `/robo-coach:update` re-syncs them.

So the rule is: **a system change is made here, released, then pulled downstream
with `/robo-coach:update` — never edited in place in a training folder.** Editing
a vendored copy downstream forks it from source; that drift is exactly what this
model exists to prevent.

## Cutting a release

`validate.sh` gates every release (CI runs it too). To cut one:

1. Make the change. Keep it generic — no athlete, no personal data.
2. Bump `version` in `.claude-plugin/plugin.json` (semver).
3. Add a dated entry at the **top** of `CHANGELOG.md` for the new version.
   `validate.sh` asserts this heading matches `plugin.json`.
4. `./validate.sh` — must print **OK** (manifests, `claude plugin validate
   --strict`, scripts compile, self-contained dry-run, and the end-to-end
   setup + privacy-hook simulation).
5. Commit as `Release x.y.z`, tag `vx.y.z`, and push:
   `git push && git push --tags`.
6. Downstream (your own training folder too): `/robo-coach:update` to pull it.

`/plugin update` tracks this repo's `main`, so a "release" is `main` HEAD plus a
matching tag and CHANGELOG entry — there are no separate release channels. (If
you ever need users to pin an *older* version, that's a bigger change and a
different discussion.)

## Privacy

Personal data must never enter this repo. Every real leak in this project's
history was personal *content* written into a legitimately tracked file, not a
stray path — so the rule for everything here is **describe the system, never the
athlete**: no name, physiology, PBs, or session data in any file. `check_privacy.py`
enforces this downstream, in training folders, against their `.privacy-markers`;
here it is a discipline held while editing.
