#!/usr/bin/env bash
# Validate the robo-coach plugin builds and works as expected.
#
#   ./validate.sh
#
# Runs manifest, structure, compile, self-contained-run, and a full end-to-end
# setup simulation (scaffold a throwaway repo exactly as /robo-coach:setup does,
# then prove the privacy hook blocks a leaking commit). Exits non-zero on any
# failure so it can gate CI. Requires: python3, git, uv. Uses `claude` if present.
set -u
PLUG="$(cd "$(dirname "$0")" && pwd)"
pass=0; fail=0; skip=0
ok(){   printf '  \033[32m✓\033[0m %s\n' "$1"; pass=$((pass+1)); }
no(){   printf '  \033[31m✗\033[0m %s\n' "$1"; fail=$((fail+1)); }
warn(){ printf '  \033[33m–\033[0m %s (skipped)\n' "$1"; skip=$((skip+1)); }
sec(){  printf '\n\033[1m%s\033[0m\n' "$1"; }

sec "Prerequisites"
for tool in python3 git uv; do
  if command -v "$tool" >/dev/null 2>&1; then ok "$tool present"; else no "$tool missing (required)"; fi
done
command -v claude >/dev/null 2>&1 && ok "claude CLI present" || warn "claude CLI (official validator)"

sec "Manifests"
python3 - "$PLUG" <<'PY' && ok "plugin.json + marketplace.json valid" || no "manifest validation failed"
import json, sys, pathlib
root = pathlib.Path(sys.argv[1])
p = json.load(open(root/".claude-plugin/plugin.json"))
assert p.get("name"), "plugin.json missing required 'name'"
m = json.load(open(root/".claude-plugin/marketplace.json"))
assert m.get("name") and m.get("owner") and m.get("plugins"), "marketplace.json missing name/owner/plugins"
for entry in m["plugins"]:
    assert entry.get("name") and entry.get("source"), "a marketplace plugin entry lacks name/source"
PY

sec "Structure (components at root, only plugin.json under .claude-plugin/)"
must=(".claude-plugin/plugin.json" ".claude-plugin/marketplace.json"
      "skills/check-in/SKILL.md" "commands/setup.md" "commands/update.md"
      "scripts/push_week.py" "scripts/check_privacy.py"
      "templates/CLAUDE.md" "templates/PLAN.example.md" "templates/athlete.example.md"
      "templates/env.example" "templates/gitignore"
      "templates/weeks/example-week.yaml" "templates/weeks/example-week.md"
      "templates/notes/shared/training-load-rules.md"
      "templates/notes/shared/fuelling-and-nutrition.md")
for f in "${must[@]}"; do
  [ -f "$PLUG/$f" ] && ok "$f" || no "missing $f"
done
# these must NOT be shipped (redundant now that push_week is PEP 723 self-contained)
for f in templates/requirements.txt templates/pyproject.toml; do
  [ -e "$PLUG/$f" ] && no "$f should not be shipped" || ok "$f absent (correct)"
done

sec "Official validator (claude plugin validate --strict)"
if command -v claude >/dev/null 2>&1; then
  # --strict fails on warnings too (missing metadata, unrecognized fields).
  claude plugin validate --strict "$PLUG" >/tmp/rc-mkt.out 2>&1 \
    && ok "marketplace manifest (strict)" || { no "marketplace manifest (strict)"; sed 's/^/      /' /tmp/rc-mkt.out; }
  # A co-located marketplace.json makes `validate <dir>` check the marketplace, so
  # validate a copy without it to exercise the plugin manifest + component frontmatter.
  tmp="$(mktemp -d)"; cp -R "$PLUG/." "$tmp/"; rm -f "$tmp/.claude-plugin/marketplace.json"; rm -rf "$tmp/.git"
  claude plugin validate --strict "$tmp" >/tmp/rc-plg.out 2>&1 \
    && ok "plugin manifest + frontmatter (strict)" || { no "plugin manifest + frontmatter (strict)"; sed 's/^/      /' /tmp/rc-plg.out; }
  rm -rf "$tmp"
else warn "claude plugin validate (CLI not installed)"; fi

sec "Scripts compile"
python3 -m py_compile "$PLUG/scripts/push_week.py" "$PLUG/scripts/check_privacy.py" \
  && ok "py_compile" || no "py_compile failed"

sec "push_week.py is self-contained (PEP 723 via uv run)"
if command -v uv >/dev/null 2>&1; then
  uv run "$PLUG/scripts/push_week.py" "$PLUG/templates/weeks/example-week.yaml" --dry-run \
    >/dev/null 2>&1 && ok "uv run --dry-run resolves deps + validates" || no "uv run --dry-run failed"
else warn "uv run --dry-run"; fi

sec "End-to-end setup simulation (throwaway repo)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
(
  cd "$T" && git init -q
  cp "$PLUG/templates/CLAUDE.md" CLAUDE.md
  cp "$PLUG/templates/PLAN.example.md" "$PLUG/templates/athlete.example.md" .
  mkdir -p weeks notes/shared scripts
  cp "$PLUG/templates/weeks/"example-week.* weeks/
  cp "$PLUG/templates/notes/shared/"*.md notes/shared/
  cp "$PLUG/templates/env.example" .env.example
  cp "$PLUG/templates/gitignore" .gitignore
  cp "$PLUG/scripts/"*.py scripts/
  [ -f PLAN.md ] || cp PLAN.example.md PLAN.md
  printf 'Jane Testrunner\n' > .privacy-markers
  HOOK="$(git rev-parse --git-path hooks)/pre-commit"
  printf '#!/bin/sh\nexec python3 "$(git rev-parse --show-toplevel)/scripts/check_privacy.py"\n' > "$HOOK"
  chmod +x "$HOOK"
  git add -A
)
# a) shareable set audits clean
( cd "$T" && python3 scripts/check_privacy.py --all >/dev/null 2>&1 ) \
  && ok "scaffolded shareable set audits clean" || no "check_privacy --all flagged the clean set"
# b) dry-run works with zero dependency setup
if command -v uv >/dev/null 2>&1; then
  ( cd "$T" && uv run scripts/push_week.py weeks/example-week.yaml --dry-run >/dev/null 2>&1 ) \
    && ok "uv run dry-run in scaffolded repo" || no "dry-run failed in scaffolded repo"
else warn "uv run dry-run in scaffolded repo"; fi
# c) the pre-commit hook must BLOCK a leaking commit
( cd "$T" && printf 'Coached by Jane Testrunner\n' > leak.md && git add leak.md \
    && ! git -c user.name=t -c user.email=t@t commit -q -m leak >/dev/null 2>&1 ) \
  && ok "pre-commit hook blocks a planted leak" || no "hook did NOT block a leak"

sec "Result"
printf "  %d passed, %d failed, %d skipped\n" "$pass" "$fail" "$skip"
[ "$fail" -eq 0 ] && { printf '  \033[32mOK\033[0m\n'; exit 0; } || { printf '  \033[31mFAILED\033[0m\n'; exit 1; }
