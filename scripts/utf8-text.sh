#!/usr/bin/env bash
# Sourced helpers: take or drop the first N CHARACTERS of a UTF-8 string, on any machine.
#
#   . "$(dirname "${BASH_SOURCE[0]}")/utf8-text.sh"
#   title="$(plc_utf8_head "$raw" 105)"
#   rest="$(plc_utf8_tail "$raw" 1)"
#
# WHY THIS EXISTS, AND WHY THE FIRST FIX WAS WRONG.
#
# `cut -c1-105` and `cut -c2-` were used to truncate repository text, and that
# text can be CJK. Under a C/POSIX locale `cut -c` counts BYTES, so a generator can slice a row
# title mid-character and rewrite a tracked file as INVALID UTF-8, or mangle a status glyph so
# it renders as a different one. Neither shows up in a UTF-8 shell; both show up on a CI runner.
#
# THE FIRST FIX WAS WRONG. It forced a UTF-8 locale and kept `cut -c`, on the
# assumption that a UTF-8 locale makes `cut -c` count characters. That is true of BSD userland and
# FALSE of GNU coreutils, where `cut -c` is byte-based regardless of locale. The guard measured
# rather than assumed, found no locale on the runner that worked, and refused to run -- correct
# behaviour, and it turned every generator into a hard failure on Linux. The lesson is not
# "pick a better locale": it is that no amount of locale selection makes a byte-based tool
# character-aware, so the truncation must not delegate to one.
#
# HOW THIS WORKS. It walks BYTES under `LC_ALL=C` -- deterministic everywhere -- and counts
# characters using UTF-8's own rule: a byte is the start of a character unless it is a
# continuation byte (0x80-0xBF). No tool is asked to be multibyte-aware, and the answer does not
# depend on the ambient locale. Verified identical under `LC_ALL=C` and `LC_ALL=en_US.UTF-8`.
#
# GOTCHA, recorded because it cost a debugging round: `printf '%d' "'$byte"` returns a SIGNED
# value, so 0xE4 arrives as -28, not 228. The first version compared it directly and classified
# every lead byte as ASCII, producing offsets that were plain wrong in both locales at once. The
# `(v + 256) % 256` normalisation is load-bearing.
#
# Scope, stated so it is not read as wider: these operate on CHARACTERS, which is what the callers
# mean. They are not grapheme-cluster aware -- a combining mark or an emoji ZWJ sequence can still
# be split -- and that is acceptable here because the callers cut prose titles and read one status glyph. Invalid UTF-8
# input is passed through byte-wise rather than rejected; validating input is not this file's job.

# Byte offset just past the first $2 characters of $1. The primitive both helpers below use.
plc__utf8_offset() {
    local s=$1 n=$2 i=0 c=0 v len
    local LC_ALL=C          # bash re-runs setlocale on assignment, so ${#s} and ${s:i:1} are BYTES
    len=${#s}
    while [ "$i" -lt "$len" ]; do
        printf -v v '%d' "'${s:$i:1}"
        v=$(( (v + 256) % 256 ))
        if [ "$v" -lt 128 ] || [ "$v" -ge 192 ]; then   # not a continuation byte => a new character
            [ "$c" -ge "$n" ] && break
            c=$(( c + 1 ))
        fi
        i=$(( i + 1 ))
    done
    printf '%s' "$i"
}

# First $2 characters of $1.
plc_utf8_head() {
    local s=$1 off
    off="$(plc__utf8_offset "$s" "$2")"
    local LC_ALL=C
    printf '%s' "${s:0:$off}"
}

# Everything after the first $2 characters of $1.
plc_utf8_tail() {
    local s=$1 off
    off="$(plc__utf8_offset "$s" "$2")"
    local LC_ALL=C
    printf '%s' "${s:$off}"
}
