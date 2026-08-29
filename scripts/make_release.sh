#!/usr/bin/env bash
# MossVoice — SINGLE official packaging path (read.md rev-3, gate G0).
#
# Why this exists: Finder→Compress or ad-hoc zipping ships user recordings
# (telephony/calls/), secrets (docker/.env), logs and macOS droppings even
# when CI is green — because CI never sees those untracked files. The ONE
# sanctioned way to build a release is from VERSION CONTROL, then scan the
# FINAL artifact. This is the only point where a ZIP may be produced.
#
# Pipeline:
#   git archive HEAD          tracked-source allowlist (gitignore'd junk is
#                             absent by construction: no calls/, .env,
#                             .DS_Store, __pycache__, *.log, runtime/models)
#       -> release/<ver>/
#       -> bash check_secrets.sh  (run INSIDE the packaged tree = scan exactly
#                                  what ships; fails the build on any leak)
#       -> sha256 manifest
#       -> mossvoice-<ver>.zip
#
# Usage: bash scripts/make_release.sh [tag-or-commit]
#   default: git rev-parse --short HEAD
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# read.md rev-4, gate A (release correctness): the release MUST be built from
# a commaited commit, never from "the state of the folder on a laptop".
# `git archive HEAD` only reads the last commit, so a dirty worktree would
# ship the OLD tree (missing this session's fixes, old scanner, old compose
# settings) while cheerfully printing "SECRET SCAN OK" from that old scanner.
# Refuse loudly instead.
if [ -n "$(git status --porcelain)" ]; then
    echo "" >&2
    echo "RELEASE REFUSED: working tree is dirty." >&2
    echo "  Commit (or stash) all changes first, then re-run." >&2
    echo "  The release is built from VERSION CONTROL, not the working copy." >&2
    echo "  Current uncommitted state:" >&2
    git status --short >&2
    exit 2
fi

VERSION="${1:-$(git rev-parse --short HEAD)}"
OUT="${REPO}/release"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "==> git archive HEAD (allowlisted source) ..."
# Dev-tooling dirs that must not ship (dev-only analysis; the secret
# scanner would otherwise flag them). Everything else comes straight from
# version control.
git archive HEAD -- . \
  ':(exclude)voice-lab' \
  ':(exclude)voice-bench' \
  | tar -x -C "$WORK"

ARTIFACT="${OUT}/mossvoice-${VERSION}"
rm -rf "${ARTIFACT}"
mkdir -p "${ARTIFACT}"
cp -R "${WORK}/." "${ARTIFACT}/"

echo "==> scanning the PACKAGED tree (exactly what ships) in ${ARTIFACT} ..."
# check_secrets.sh derives its repo root from its own location, so running it
# by absolute path makes it scan the packaged tree, not the working copy.
bash "${ARTIFACT}/scripts/check_secrets.sh"

echo "==> packaging zip + sha256 ..."
ZIP="${OUT}/mossvoice-${VERSION}.zip"
rm -f "${ZIP}"
(
  cd "${OUT}"
  zip -qr "mossvoice-${VERSION}.zip" "mossvoice-${VERSION}"
)
# manifest inside the artifact too, so recipients can verify
(
  cd "${ARTIFACT}"
  # stable relative listing (no timestamps) for reproducibility
  find . -type f | sort | xargs shasum -a 256 > SHA256SUMS
)
cp "${ARTIFACT}/SHA256SUMS" "${OUT}/mossvoice-${VERSION}.SHA256SUMS"

echo ""
echo "RELEASE OK: ${ZIP}"
echo "  size : $(du -h "${ZIP}" | cut -f1)"
echo "  sha256: $(shasum -a 256 "${ZIP}" | cut -d' ' -f1)"
