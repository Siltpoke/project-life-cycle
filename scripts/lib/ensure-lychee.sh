#!/usr/bin/env bash
# Resolve, download, VERIFY and cache the pinned lychee binary. Prints its path on stdout.
#
# Exit non-zero on: unknown platform, no pin for this platform, download failure, checksum
# mismatch. NEVER substitute a different version -- that recreates the two-version problem
# this whole file exists to remove, and it would do it silently.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIN_FILE="${LYCHEE_PIN_FILE:-$HERE/lychee-pin.env}"
CACHE_DIR="${LYCHEE_CACHE_DIR:-${TMPDIR:-/tmp}/plc-lychee-cache}"

[ -r "$PIN_FILE" ] || { echo "FATAL: pin file unreadable: $PIN_FILE" >&2; exit 2; }
# shellcheck disable=SC1090
. "$PIN_FILE"

case "$(uname -s)/$(uname -m)" in
  Linux/x86_64)   ASSET="lychee-x86_64-unknown-linux-gnu.tar.gz"; WANT="$LYCHEE_SHA256_x86_64_linux" ;;
  Darwin/arm64)   ASSET="lychee-aarch64-apple-darwin.tar.gz";      WANT="$LYCHEE_SHA256_aarch64_darwin" ;;
  *)
    echo "FATAL: no pinned lychee for $(uname -s)/$(uname -m) at $LYCHEE_VERSION." >&2
    echo "  Add the platform's asset + sha256 to $PIN_FILE. Do NOT fall back to another" >&2
    echo "  version: a local binary at a different version stops testing what CI runs." >&2
    exit 3 ;;
esac

BIN="$CACHE_DIR/$LYCHEE_VERSION/lychee"
if [ -x "$BIN" ]; then printf '%s\n' "$BIN"; exit 0; fi

mkdir -p "$CACHE_DIR/$LYCHEE_VERSION"
TARBALL="$CACHE_DIR/$LYCHEE_VERSION/$ASSET"
URL="https://github.com/lycheeverse/lychee/releases/download/lychee-$LYCHEE_VERSION/$ASSET"

if ! curl -fsSL "$URL" -o "$TARBALL"; then
  rm -f "$TARBALL"
  echo "FATAL: could not download $URL" >&2
  exit 4
fi

GOT="$(shasum -a 256 "$TARBALL" 2>/dev/null | awk '{print $1}')"
[ -n "$GOT" ] || GOT="$(sha256sum "$TARBALL" | awk '{print $1}')"
if [ "$GOT" != "$WANT" ]; then
  rm -f "$TARBALL"
  echo "FATAL: checksum mismatch for $ASSET" >&2
  echo "  expected $WANT" >&2
  echo "  got      $GOT" >&2
  echo "  The download was DELETED. Do not re-run until you know why it differed." >&2
  exit 5
fi

tar -xzf "$TARBALL" -C "$CACHE_DIR/$LYCHEE_VERSION"
# The release tarball extracts into a same-named subdirectory (e.g.
# lychee-aarch64-apple-darwin/lychee), not flat -- verified against both platforms' tarball
# listings. Move the binary up to $BIN so callers get a stable path regardless
# of platform, then discard the rest of the extracted tree (README, docs, shell completions).
EXTRACTED_DIR="$CACHE_DIR/$LYCHEE_VERSION/${ASSET%.tar.gz}"
mv "$EXTRACTED_DIR/lychee" "$BIN"
rm -rf "$EXTRACTED_DIR"
chmod +x "$BIN"
printf '%s\n' "$BIN"
