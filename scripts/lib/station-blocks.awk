# station-blocks.awk (the station-plan work) — the ONE reader of the station-plan and active blocks in
# docs/ROADMAP.md. Every consumer shells out to this program; nobody re-implements it.
#
# WHY IT IS A FILE AND NOT THREE COPIES. Three scripts need the same records
# (station-id-integrity.sh, closed-step-refs-resolve.sh, station-state-consistency.sh) and
# one grammar with several implementations is the encoder-divergence class this repo has
# already paid for — the p36 design forbids it by name for the closure grammar, and the
# reason does not stop at that file. Extracted verbatim from station-id-integrity.sh, whose
# fixtures and mutants are what prove the extraction changed nothing.
#
# Emits TAB-separated records on stdout:
#     BLOCK<TAB><station-id><TAB><binds-to><TAB><nsteps><TAB><heading-line><TAB><depends-on>
#         depends-on is the RAW declared value, `none` included -- the renderer needs it to
#         say what a station is blocked by, and resolving it is station-deps-acyclic.sh
#         work, not this one.
#     STEP<TAB><station-id><TAB><step-number><TAB><rendered step text incl. `sN ` prefix>
#     ACTIVEBLOCK<TAB><line>          the `## 🚦` heading exists (emitted once, if at all)
#     ACTIVE<TAB><name>               one entry of the active list
#     ERR<TAB><station-id><TAB><line><TAB><message>
#
# ACTIVEBLOCK IS EMITTED SEPARATELY FROM ACTIVE, and that is the point of it: without it an
# absent `## 🚦` section and a present-but-empty one produce the same output — zero ACTIVE
# records — and a reader cannot tell "nobody declared what is in flight" from "somebody
# declared that nothing is". That distinction is the entire subject of this phase.
#
# ERR records are the CLOSED-LINE-SET finding and the two missing-key findings. They are
# reported here because only the parser can see them, but acting on them belongs to
# station-id-integrity.sh; a consumer that only wants BLOCK/STEP must ignore them rather
# than re-report them, or two guards go red for one defect and the second one's scope is
# wider than its name.

function flush(   i) {
  if (id == "") return
  printf "BLOCK\t%s\t%s\t%d\t%d\t%s\n", id, bindsto, nsteps, startline, deps
  for (i = 1; i <= nsteps; i++) printf "STEP\t%s\t%s\t%s\n", id, stepnum[i], steptext[i]
  if (bindsto == "") printf "ERR\t%s\t%d\tmissing binds-to\n", id, startline
  if (!seen_deps) printf "ERR\t%s\t%d\tmissing depends-on\n", id, startline
  id = ""; bindsto = ""; nsteps = 0; seen_deps = 0; insteps = 0; deps = ""
}

# The two section flags are cleared by each other, not merely by the next `## `. The blocks
# happen to appear plan-then-active in this repo today, and a parser that only works in that
# order would read a `- binds-to:` line as an active-list entry the moment somebody swapped
# them -- silently, since both shapes start with `- `.
index($0, "## 🧭") == 1 { flush(); inactive = 0; inplan = 1; next }
inplan && substr($0, 1, 3) == "## " { flush(); inplan = 0 }

index($0, "## 🚦") == 1 { flush(); inplan = 0; inactive = 1; printf "ACTIVEBLOCK\t%d\n", NR; next }
inactive && substr($0, 1, 3) == "## " { inactive = 0 }
inactive && /^- / {
  a = $0; sub(/^- [ \t]*/, "", a); gsub(/[ \t]+$/, "", a)
  printf "ACTIVE\t%s\n", a
  next
}

!inplan { next }
/^### / {
  flush()
  id = $0; sub(/^### [ \t]*/, "", id); gsub(/[ \t]+$/, "", id)
  startline = NR
  next
}
id == "" { next }                              # preamble (marker comment, blanks)
/^[ \t]*$/ { next }
/^- binds-to:[ \t]*/ {
  bindsto = $0; sub(/^- binds-to:[ \t]*/, "", bindsto); gsub(/[ \t]+$/, "", bindsto)
  insteps = 0; next
}
/^- depends-on:[ \t]*/ {
  seen_deps = 1; insteps = 0
  deps = $0; sub(/^- depends-on:[ \t]*/, "", deps); gsub(/[ \t]+$/, "", deps)
  next
}
/^- steps:[ \t]*$/ { insteps = 1; next }
insteps && /^[ \t]+- s[0-9]+ / {
  line = $0; sub(/^[ \t]+- /, "", line)
  num = line; sub(/^s/, "", num); sub(/ .*$/, "", num)
  nsteps++
  stepnum[nsteps] = num
  steptext[nsteps] = line
  next
}
{ printf "ERR\t%s\t%d\tline not in the closed set: %s\n", id, NR, $0 }
END { flush() }
