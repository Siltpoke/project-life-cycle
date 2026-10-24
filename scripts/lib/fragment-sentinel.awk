# fragment-sentinel.awk -- the declared source of truth for reading the drain's fragment sentinel.
#
# Call it with -v pat="phase-<name>" over one compiled archive file. It prints that phase's slice
# and reports, by exit status, whether a genuine boundary for the phase was found: 0 found, 1 none,
# 2 a sentinel-shaped line naming it was rejected as fenced -- ambiguous, and reported rather than
# resolved.
#
# WHY THIS FILE EXISTS. Two readers need the same answer to "is this line a real fragment
# boundary": the wrap-up gate, which slices one phase's entry out of an archive, and the lifecycle
# ledger, which asks whether a phase's fragment reached a durable file at all. A second reader
# re-deriving these rules is the drift this file exists to stop.
#
# HOW THE ONE-READER RULE IS ENFORCED, AND WHAT IT DOES NOT CLAIM. The ledger reads THIS FILE at
# run time (awk -f). The gate cannot: it is a single drop-in script -- its own harness runs it by
# writing the script text alone into a fixture repository, and the adopter-facing reference ships
# it as one copyable file -- so a sibling file would not travel with it. The gate and that
# reference therefore carry the program BELOW byte-for-byte, and
# scripts/invariants/one-fragment-sentinel-reader.sh holds the source and both embeddings to the
# same bytes and refuses any fourth anchored matcher. So the claim is exactly: ONE source text, two
# pinned embeddings, two direct run-time readers -- not one physical implementation. The second
# direct reader is scripts/invariants/mode-provenance-recorded.sh, which slices a phase's record out
# of the archive after its drain has moved it there; a direct reader holds no copy of the pattern,
# so it is not a fourth matcher and needs no exemption.
#
# THE GRAMMAR IS STATED, NOT GUESSED. Every marker occupies its whole line, and the payload takes one of
# two forms --
# `docs/<dir>/<name>.md`, and a bare basename with no directory and no extension --
# with nothing in any other form. So the payload is a non-empty,
# whitespace-free token and the phase name is read from its basename with a trailing `.md`
# optional: both forms parse. No counts are quoted here,
# because a count in a comment goes stale while the rule it justifies does not.
#
# WHAT THIS PARSER CLAIMS, AND IT IS THE ONLY THING IT CLAIMS: every ambiguity costs a FAIL, never
# a PASS. It is not a markdown parser and does not pretend to be one. Fences are recognised at
# column 1 only, backticks and tildes only; an unterminated fence costs every boundary after it in
# that file, loudly. The three rules, and the error direction each was chosen for, are set out in
# full where the gate calls this program.
#
# TWO CHARACTERS THE PROGRAM BELOW MAY NOT CONTAIN, both learned by breaking something. The two
# embeddings live inside a SINGLE-QUOTED shell string, which itself sits inside a MARKDOWN FENCE,
# so:
#   * no single quote, not even an apostrophe in prose. It closes the shell string and the gate
#     stops parsing. An apostrophe in a comment gives `syntax error near unexpected
#     token` -- and the byte-pinning guard stayed GREEN through it, because identical bytes is not
#     the same claim as valid bytes.
#   * no run of three or more backticks or tildes. It ends the markdown fence early, and the
#     extractor regex is non-greedy, so the adopter-facing gate silently loses everything after
#     it. Measured: nearly all of the gate was lost.
# Both are now refusals in scripts/invariants/one-fragment-sentinel-reader.sh rather than advice.
#
# --- PINNED PROGRAM BELOW: every line after this marker is byte-compared against both embeddings.
    # The length of the delimiter run this line opens with, or 0 if it is not a fence line.
    function frun(s) { if (match(s, /^(`+|~+)/) && RLENGTH >= 3) return RLENGTH; return 0 }
    # A closer for an open <ch>-fence of length <ln>: same character, at least as long, and
    # NOTHING but whitespace after it -- a bare delimiter run closes, and a run carrying a language
    # tag after it is content and an opener, not a closer. (The two forms are not spelled out with
    # literal backtick runs on purpose: the adopter-facing reference embeds this program inside a
    # markdown fence, and a triple run here ends that fence early. Measured: one such line cut the
    # extracted gate from 79,554 bytes to 9,504 -- 88% of it -- with nothing reporting a problem.)
    function fclose(s, ch, ln,   r) {
      r = frun(s)
      if (!r || substr(s, 1, 1) != ch || r < ln) return 0
      return (substr(s, r + 1) ~ /^[[:space:]]*$/)
    }
    # The payload of an ACCEPTED sentinel line: what sits between the opener and the ` -->`
    # terminator. Returns "" for the two shapes the grammar calls malformed -- an empty or
    # all-whitespace payload, and a comment with no terminator on its line -- so one return value
    # means "do not use this", and the caller decides how loudly to say so.
    function fpay(s,   t, i) {
      t = substr(s, length(PFX) + 1)
      i = index(t, " -->")
      if (i == 0) return ""
      t = substr(t, 1, i - 1)
      if (t ~ /^[[:space:]]*$/) return ""
      # WHITESPACE INSIDE THE PAYLOAD IS MALFORMED, which the grammar above has always said and
      # this function did not check. A payload names a PATH; a space in it means the line is not
      # the thing it looks like, and scoring it anyway hands the phase-name test a token nobody
      # wrote. Derived from a census of existing markers, the way the rest of this grammar was:
      # none has whitespace in the payload, so enforcing the stated rule refuses
      # nothing that exists. Returning "" routes it to the same loud failure as an empty payload.
      if (t ~ /[[:space:]]/) return ""
      return t
    }
    BEGIN { PFX = "<!-- fragment: "; fopen = 0; prevblank = 1; inb = 0; found = 0; fenced = 0
            printed = 0; malformed = 0 }
    {
      if (prevblank == 1 && $0 ~ /^<!-- fragment: /) {
        k = index($0, pat)
        after = (k > 0) ? substr($0, k + length(pat), 1) : ""
        nm = (k > 0 && (after == "-" || after == ".")) ? 1 : 0
        if (fopen == 0) {
          # ACCEPTED boundary. It both ends the previous slice and opens this one; the sentinel
          # line itself is never body.
          #
          # PAYLOAD MODE, and it is inert unless asked for: with -v emit=payload the caller gets
          # the markers themselves rather than the slice belonging to one phase.
          #
          # THE REASON IS FAIL-LOUD, not reach. A caller can already ask "is there a boundary for
          # this phase" with the exit status above, and measurement says that answer is right for
          # every marker in this archive today. What it CANNOT do is tell a malformed marker from
          # an absent one: a sentinel line with an empty payload exits 1 up there, which a caller
          # reads as "this file holds nothing for you" -- a fail-OPEN reading of the one shape the
          # grammar wants to fail loudly. Code 3 below is where that distinction lives.
          #
          # It also moves the NAME test to the caller, which already owns one, so a payload ending
          # AT the phase name parses -- the substring rule above needs a following `-` or `.`.
          # Stated rather than implied: that form is not load-bearing today. Such lines in
          # this archive sit directly beneath a full-path marker naming the same fragment, with no
          # blank line above them, so none of them is a boundary and the exit status misses
          # nothing. The grammar accepts the form; no archived evidence depends on it.
          #
          # Malformedness is judged HERE and only for accepted boundaries: a sentinel quoted inside
          # a fence is not a marker, so a malformed quoted example must fail no scan.
          if (emit == "payload") {
            p = fpay($0)
            if (p == "") malformed = 1
            else { print p; printed = 1 }
            prevblank = 0
            next
          }
          inb = nm
          if (nm) found = 1
          prevblank = 0
          next
        }
        # REJECTED — sentinel-shaped, but inside a fence. Rule 2: it still ENDS the open slice,
        # so no slice can ever reach into the next fragment. Rule 3: if it names this phase, say
        # so rather than dropping it silently. The line then falls through as ordinary body.
        if (nm) fenced = 1
        inb = 0
      }
      if (fopen == 0) { r = frun($0); if (r) { fopen = 1; fchar = substr($0, 1, 1); flen = r } }
      else if (fclose($0, fchar, flen)) fopen = 0
      if (inb) print
      prevblank = ($0 ~ /^[[:space:]]*$/) ? 1 : 0
    }
    # Slice mode: 0 a boundary for this phase was found, 1 none was, 2 one naming it was rejected
    # as fenced. Payload mode keeps the same error DIRECTION and adds one code rather than reusing
    # a quieter one: 3 means a malformed marker was seen, and it outranks having printed others,
    # because the whole point of the grammar is that fail-loud stays reachable.
    END { if (emit == "payload") exit(malformed ? 3 : (printed ? 0 : 1))
          exit(found ? 0 : (fenced ? 2 : 1)) }
