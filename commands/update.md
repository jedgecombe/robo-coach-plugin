---
description: Refresh a robo-coach training repo from the installed plugin — re-vendors the scripts, example templates, and dependency manifests, and reinstalls the privacy hook, without touching any personal data.
---

The setup command **vendors** copies of the scripts and templates into the athlete's repo (the
git pre-commit hook and the athlete's own `python3 scripts/…` commands both need real file paths
in the repo, which a live reference into the plugin's install directory can't give — that path
moves on every plugin update). The trade-off is that those copies don't change when the plugin
updates. This command re-syncs them.

Run it from the athlete's training repo after updating the plugin (`/plugin update robo-coach`).

## Refresh — overwrite these from the plugin

These carry no personal data, so overwriting is safe:

- `${CLAUDE_PLUGIN_ROOT}/scripts/push_week.py` → `scripts/push_week.py`
- `${CLAUDE_PLUGIN_ROOT}/scripts/check_privacy.py` → `scripts/check_privacy.py`
- `${CLAUDE_PLUGIN_ROOT}/templates/PLAN.example.md` → `PLAN.example.md`
- `${CLAUDE_PLUGIN_ROOT}/templates/athlete.example.md` → `athlete.example.md`
- `${CLAUDE_PLUGIN_ROOT}/templates/weeks/example-week.{md,yaml}` → `weeks/`
- `${CLAUDE_PLUGIN_ROOT}/templates/notes/shared/` → `notes/shared/`

`push_week.py` carries its dependencies inline (PEP 723), so refreshing it is all that's needed —
there is no separate dependency manifest to re-install. Then reinstall the pre-commit hook (in
case its mechanism changed) exactly as setup step 4 does.

## Never touch — these are the athlete's

Do **not** overwrite: `PLAN.md`, `athlete.md`, `.env`, `.privacy-markers`, anything under
`weeks/20*`, private `notes/` (outside `shared/`), or their `CLAUDE.md` (they may have edited it).
If the plugin's `templates/CLAUDE.md` has changed meaningfully, **show the athlete the diff** and
let them merge — don't overwrite it for them.

## Verify

Finish with `python3 scripts/check_privacy.py --all` and a `--dry-run` of the current week, and
tell the athlete what changed (e.g. "push_week.py updated; your plan and data untouched").
