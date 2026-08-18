#!/usr/bin/env bash
# MossVoice secret / artifact scanner.
#   * fails on known credential file names and hardcoded API tokens
#   * fails on user-data artifacts that must never ship (recordings, __MACOSX)
#   * fails on absolute developer paths leaking into the tree
#
# Usage: bash scripts/check_secrets.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

failures=0

check() { # check <desc> <command...>
  local desc="$1"; shift
  if ! "$@" >/dev/null 2>&1; then
    echo "FAIL: $desc"
    failures=$((failures + 1))
  else
    echo "ok  : $desc"
  fi
}

# --- 1. credential file names ------------------------------------------------
if find . -type f \
    \( -name "bot.token" -o -name "*.token" -o -name ".env" \
       -o -name "*.pem" -o -name "id_rsa" -o -name "*.p12" \) \
    -not -path "./.git/*" | grep -q .; then
  echo "FAIL: credential files present"
  find . -type f \( -name "bot.token" -o -name "*.token" -o -name ".env" \
      -o -name "*.pem" -o -name "id_rsa" -o -name "*.p12" \) \
      -not -path "./.git/*"
  failures=$((failures + 1))
else
  echo "ok  : no credential files"
fi

# --- 2. hardcoded tokens in source -------------------------------------------
if grep -rnE "([0-9]{8,10}:[A-Za-z0-9_-]{35}|sk-[A-Za-z0-9]{20,}|[A-Za-z0-9_\-]{24,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{38})" \
    --include="*.py" --include="*.sh" --include="*.yaml" --include="*.yml" \
    --include="*.lua" --include="*.md" --include="*.json" . 2>/dev/null \
    | grep -v "\.git/" | grep -qE .; then
  echo "FAIL: possible hardcoded tokens"
  grep -rnE "([0-9]{8,10}:[A-Za-z0-9_-]{35}|sk-[A-Za-z0-9]{20,}|[A-Za-z0-9_\-]{24,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{38})" \
      --include="*.py" --include="*.sh" --include="*.yaml" --include="*.yml" \
      --include="*.lua" --include="*.md" --include="*.json" . 2>/dev/null \
      | grep -v "\.git/" | head -20
  failures=$((failures + 1))
else
  echo "ok  : no hardcoded tokens"
fi

# --- 3. user-data artifacts ---------------------------------------------------
if [ -d __MACOSX ] || find . -type f \( -name "*.log" -o -name "*.pid" \
    -o -name "user-*.wav" -o -name "reply-*.wav" \) -not -path "./.git/*" | grep -q .; then
  echo "FAIL: user-data / runtime artifacts present (__MACOSX, logs, PIDs, recordings)"
  find . -type f \( -name "*.log" -o -name "*.pid" -o -name "user-*.wav" \
      -o -name "reply-*.wav" \) -not -path "./.git/*" | head
  failures=$((failures + 1))
else
  echo "ok  : no user-data artifacts"
fi

# --- 4. absolute developer paths ---------------------------------------------
grep -rn "/Users/" --include="*.py" --include="*.sh" --include="*.lua" \
    --include="*.md" --include="*.yaml" --include="*.yml" . 2>/dev/null \
    | grep -v "\.git/" | grep -v "scripts/check_secrets.sh" \
    | grep -qE . && {
  echo "FAIL: absolute developer paths leak into the tree"
  grep -rn "/Users/" --include="*.py" --include="*.sh" --include="*.lua" \
      --include="*.md" --include="*.yaml" --include="*.yml" . 2>/dev/null \
      | grep -v "\.git/" | grep -v "scripts/check_secrets.sh" | head
  failures=$((failures + 1))
} || echo "ok  : no absolute developer paths"

# --- 5. model weights not in the tree (pinned download instead) ---------------
if [ -d runtime/models ] && find runtime/models -name "*.onnx" | grep -q .; then
  echo "WARN: runtime/models present locally — excluded from git/ZIP, but "
  echo "     : remove before packing the archive if you want a minimal ZIP."
else
  echo "ok  : no model weights in the tree"
fi

if [ "$failures" -gt 0 ]; then
  echo ""
  echo "SECRET SCAN FAILED: $failures issue(s)"
  exit 1
fi
echo ""
echo "SECRET SCAN OK"