#!/usr/bin/env bash
# Launch-readiness gate for this Python project: no unfilled double-brace
# blanks and no unconfirmed launch-TODO samples in the requested paths.
#
# Scoped on purpose: does not recurse into .venv, .git, dist, or test trees
# that intentionally contain placeholder fixtures.
#
# Exit 0 = clean, 1 = launch-TODO remains, 2 = missing/unreadable target,
# search error, or double-brace blank.
set -uo pipefail

if [ "$#" -eq 0 ]; then
  echo "usage: $0 PATH [PATH...]" >&2
  echo "example: $0 docs README.md CHANGELOG.md SECURITY.md CONTRIBUTING.md LAUNCH_CHECKLIST.md site" >&2
  exit 2
fi

excludes=(
  --exclude-dir=.git
  --exclude-dir=.venv
  --exclude-dir=dist
  --exclude-dir=node_modules
  --exclude-dir=__pycache__
  --exclude-dir=tests
  --exclude=check-placeholders.sh
  --exclude='*.png'
  --exclude='*.jpg'
  --exclude='*.jpeg'
  --exclude='*.gif'
  --exclude='*.webp'
  --exclude='*.ico'
  --exclude='*.pdf'
  --exclude='*.lock'
  --exclude='*.woff2'
)

blank_re='\{\{[A-Z][A-Z0-9_]*\}\}'
todo_re='TODO\(launch\)'

fail=0
blanks=""
todos=""

scan() {
  local pattern="$1"
  local out rc
  if [ -d "$target" ]; then
    out="$(grep -rInE "${excludes[@]}" -- "$pattern" "$target" 2>&1)"
    rc=$?
  else
    out="$(grep -nE -- "$pattern" "$target" 2>&1)"
    rc=$?
  fi
  if [ "$rc" -ge 2 ]; then
    echo "✗ search error on $target:" >&2
    printf '%s\n' "$out" >&2
    return 2
  fi
  if [ "$rc" -eq 0 ]; then
    printf '%s\n' "$out"
  fi
  return 0
}

for target in "$@"; do
  if [ ! -e "$target" ]; then
    echo "✗ missing target: $target" >&2
    fail=2
    continue
  fi
  if [ ! -r "$target" ]; then
    echo "✗ unreadable target: $target" >&2
    fail=2
    continue
  fi

  found_blanks="$(scan "$blank_re")" || { fail=2; continue; }
  found_todos="$(scan "$todo_re")" || { fail=2; continue; }
  if [ -n "$found_blanks" ]; then
    blanks="${blanks}${found_blanks}"$'\n'
  fi
  if [ -n "$found_todos" ]; then
    todos="${todos}${found_todos}"$'\n'
  fi
done

if [ -n "$blanks" ]; then
  echo "✗ UNFILLED PLACEHOLDERS — fill double-brace blanks before launch:"
  printf '%s' "$blanks" | sed 's/^/    /'
  echo
  fail=2
fi

if [ -n "$todos" ]; then
  echo "⚠ UNCONFIRMED SAMPLES — replace each launch-TODO, or delete that marker line:"
  printf '%s' "$todos" | sed 's/^/    /'
  echo
  [ "$fail" -eq 0 ] && fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "✓ no placeholders or unconfirmed samples in requested paths."
else
  echo "Not launch-ready. Fix the items above and re-run: $0 $*"
fi
exit "$fail"
