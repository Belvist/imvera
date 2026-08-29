#!/usr/bin/env bash
# MossVoice secret / artifact scanner.
#   * fails on known credential file names and hardcoded API tokens
#   * fails on user-data artifacts that must never ship (recordings, __MACOSX)
#   * fails on absolute developer paths leaking into the tree
#
# SECURITY NOTE (read.md rev-2 #17): we NEVER use `grep -q` inside a
# `set -o pipefail` pipeline — on the first match grep closes the pipe, find
# gets SIGPIPE (exit 141), and the pipeline then looks like "no matches",
# silently hiding build-breaking files. All gates below instead COLLECT the
# findings into a variable and test its length with `[ -n ... ]`.
#
# Usage: bash scripts/check_secrets.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# read.md rev-3 G0: the release bundle is `git archive` of TRACKED files, so
# a gate failure must reflect tracked content. Local ignored/untracked
# artifacts (docker/.env, .trae/, *.wav recordings) never ship, so they are
# WARNed here, not FAILed.
tracked_only() {
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    f="${line%%:*}"
    [ -f "$f" ] || continue
    if git ls-files --error-unmatch -- "$f" >/dev/null 2>&1; then
      printf '%s\n' "$line"
    fi
  done
}
untracked_only() {
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    f="${line%%:*}"
    [ -f "$f" ] || continue
    if ! git ls-files --error-unmatch -- "$f" >/dev/null 2>&1; then
      printf '%s\n' "$line"
    fi
  done
}

failures=0

# --- 1. credential file names -------------------------------------------------
# read.md rev-3: also match .env.* (docker/.env.prod etc.) but ALWAYS allow the
# documented template .env.example (it carries no secrets, only placeholders).
creds="$(find . -type f \
    \( -name "bot.token" -o -name "*.token" -o -name ".env" \
       -o -name ".env.*" -o -name "*.pem" -o -name "id_rsa" \
       -o -name "*.p12" \) \
    ! -name ".env.example" \
    -not -path "./.git/*" -print 2>/dev/null)"
if [ -n "$creds" ]; then
  _creds_tracked="$(printf '%s\n' "$creds" | tracked_only)"
  _creds_untracked="$(printf '%s\n' "$creds" | untracked_only)"
  if [ -n "$_creds_tracked" ]; then
    echo "FAIL: credential files present (tracked)"
    printf '%s\n' "$_creds_tracked"
    failures=$((failures + 1))
  elif [ -n "$_creds_untracked" ]; then
    echo "WARN: credential file names in untracked/ignored files (not shipped)"
    printf '%s\n' "$_creds_untracked"
  fi
else
  echo "ok  : no credential files"
fi

# --- 2. hardcoded tokens in source -------------------------------------------
tok_match="$(grep -rnE "([0-9]{8,10}:[A-Za-z0-9_-]{35}|sk-[A-Za-z0-9]{20,}|[A-Za-z0-9_\-]{24,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{38})" \
    --include="*.py" --include="*.sh" --include="*.yaml" --include="*.yml" \
    --include="*.lua" --include="*.md" --include="*.json" . 2>/dev/null \
    | grep -v "\.git/" || true)"
# read.md rev-3 #17: long hex runs (32+ hex chars) are the shape of the
# FreeSWITCH ESL password that leaked into release archives (2026-08-29);
# API tokens are often hex too. Match a run of EXACTLY 32 hex chars bounded
# by non-hex so git commit SHAs (40 hex) are not flagged. Short fixture
# values and UUIDs (8-4-4-4-12) do not trip the scan either.
hex_match="$(grep -rnE "[^0-9a-fA-F][0-9a-fA-F]{32}[^0-9a-fA-F]" \
    --include="*.py" --include="*.sh" --include="*.lua" \
    --include="*.yaml" --include="*.yml" --include="*.json" . 2>/dev/null \
    | grep -v "\.git/" || true)"
_tok_tracked="$(printf '%s\n%s\n' "$tok_match" "$hex_match" | tracked_only)"
_tok_untracked="$(printf '%s\n%s\n' "$tok_match" "$hex_match" | untracked_only)"
if [ -n "$_tok_tracked" ]; then
  echo "FAIL: possible hardcoded tokens (tracked)"
  (printf '%s\n' "$_tok_tracked" | head -20)
  failures=$((failures + 1))
elif [ -n "$_tok_untracked" ]; then
  echo "WARN: possible tokens in untracked/ignored files (not shipped)"
  (printf '%s\n' "$_tok_untracked" | head -20)
else
  echo "ok  : no hardcoded tokens"
fi

# --- 3. user-data artifacts ---------------------------------------------------
# read.md rev-2 #16: real runtime data lives in telephony/calls/ (call
# recordings, result.json, summary.txt, *.log) and tests can leave _tmp_
# jars; caches and macOS droppings must also never ship. Gates use a plain
# non-empty test, NOT grep -q in a pipefail pipeline.
# read.md rev-3: .DS_Store is a FILE, not a directory — it must live in the
# file-artifacts predicate (a `-type d -name .DS_Store` never matched it).
artifacts="$(find . -type f \
    \( -name "*.log" -o -name "*.pid" -o -name "user-*.wav" \
       -o -name "reply-*.wav" -o -name "result.json" \
       -o -name "summary.txt" -o -name "_tmp_*.wav" \
       -o -name ".DS_Store" \) \
    -not -path "./.git/*" -print 2>/dev/null)"
dirs="$(find . -type d \
    \( -name "__MACOSX" -o -name "__pycache__" -o -name "_tmp_*" \
       -o -name "calls" \) -print 2>/dev/null)"
if [ -e __MACOSX ] || [ -n "$artifacts" ]; then
  _art_tracked="$(printf '%s\n' "$artifacts" | tracked_only)"
  _art_untracked="$(printf '%s\n' "$artifacts" | untracked_only)"
  if [ -n "$_art_tracked" ]; then
    echo "FAIL: user-data / runtime artifacts present (logs, PIDs, recordings, results)"
    (printf '%s\n' "$_art_tracked" | head -20)
    failures=$((failures + 1))
  else
    echo "WARN: runtime artifacts in untracked/ignored files (not shipped)"
    (printf '%s\n' "$_art_untracked" | head -20)
  fi
elif [ -n "$dirs" ]; then
  echo "FAIL: user-data / runtime directories present (calls/, __pycache__, __MACOSX, ...)"
  printf '%s\n' "$dirs"
  failures=$((failures + 1))
else
  echo "ok  : no user-data artifacts"
fi

# --- 4. absolute developer paths ---------------------------------------------
devpath="$(grep -rn "/Users/" --include="*.py" --include="*.sh" --include="*.lua" \
    --include="*.md" --include="*.yaml" --include="*.yml" . 2>/dev/null \
    | grep -v "\.git/" | grep -v "scripts/check_secrets.sh" || true)"
_dev_tracked="$(printf '%s\n' "$devpath" | tracked_only)"
_dev_untracked="$(printf '%s\n' "$devpath" | untracked_only)"
if [ -n "$_dev_tracked" ]; then
  echo "FAIL: absolute developer paths leak into the tree"
  (printf '%s\n' "$_dev_tracked" | head -20)
  failures=$((failures + 1))
elif [ -n "$_dev_untracked" ]; then
  echo "WARN: developer paths in untracked/ignored files (not shipped)"
  (printf '%s\n' "$_dev_untracked" | head -20)
else
  echo "ok  : no absolute developer paths"
fi

# --- 5. model weights not in the tree (pinned download instead) ---------------
onnx="$(find runtime/models -name "*.onnx" -print 2>/dev/null || true)"
if [ -d runtime/models ] && [ -n "$onnx" ]; then
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