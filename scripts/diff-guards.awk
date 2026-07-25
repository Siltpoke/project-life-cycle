# diff-guards.awk — stateful, full-file guard scanner (verify-gate AC3 / R5).
# Reads a file's FULL content at HEAD (via `git show`), so multi-line constructs — block
# comments /* */, JS template literals ` `, Python triple-quoted strings """ / ''' — are
# tracked with CROSS-LINE state. A unified=0 diff alone can't see a construct's opening
# delimiter when only an interior line is added, which is why the earlier line-local strip
# over-routed (routed a `throw` inside a docstring / block comment). Emits
# `file<TAB>line<TAB>kind` ONLY for lines whose number is in `addlines` (the diff's added set)
# AND that survive stripping as real code. Over-routing is the R5 failure (waiver-spam); when
# state is ambiguous we prefer to swallow (under-route), never over-route.
# Driven by diff-guards.sh:  awk -v file=<path> -v ext=<ext> -v addlines=<csv> -f this <content>
BEGIN {
  SQ = sprintf("%c", 39)
  TRI_D = "\"\"\""
  TRI_S = SQ SQ SQ
  n = split(addlines, A, ",")
  for (i = 1; i <= n; i++) add[A[i] + 0] = 1
  CS = (ext ~ /^(js|jsx|ts|tsx|mjs|cjs|go|rs|java|c|cc|cpp|h|hpp|php)$/)
  PY = (ext ~ /^(py)$/)
  inblk = 0; intmpl = 0; intri = 0; TRI = ""
}

function kind(s,   w) {
  # onetrueawk (macOS) has no \b — word boundaries are explicit non-word classes.
  w = " " s " "
  if (w ~ /[^A-Za-z0-9_]throw[^A-Za-z0-9_]/)                return "throw"
  if (w ~ /[^A-Za-z0-9_]assert[^A-Za-z0-9_]/)               return "assert"
  if (w ~ /[^A-Za-z0-9_]raise[^A-Za-z0-9_]/)                return "raise"
  if (w ~ /[^A-Za-z0-9_]return[ \t]+[Ff]alse[^A-Za-z0-9_]/) return "return-false"
  if (w ~ /(process|sys|os)\.exit[ \t]*\(/)                 return "exit"
  if (w ~ /[^A-Za-z0-9_]exit[ \t]+[1-9]/)                   return "ci-exit"
  return ""
}

# consume python triple-quoted spans; sets intri/TRI when a triple opens unterminated.
function py_triples(s,   out, p, q, d) {
  out = ""
  while (length(s) > 0) {
    p = index(s, TRI_D); q = index(s, TRI_S)
    if (p == 0 && q == 0) { out = out s; break }
    if (q == 0 || (p != 0 && p < q)) { d = TRI_D; p = p } else { d = TRI_S; p = q }
    out = out substr(s, 1, p - 1)       # code before the opener is visible
    s = substr(s, p + 3)
    q = index(s, d)                     # closing on the same line?
    if (q == 0) { intri = 1; TRI = d; return out }   # opens unterminated → rest swallowed
    s = substr(s, q + 3)                # skip the quoted body + closer, keep scanning
  }
  return out
}

# returns the code-visible portion of `line`, updating multi-line state as a side effect.
function visible(line,   p, sqre) {
  if (inblk) { p = index(line, "*/"); if (p == 0) return ""; line = substr(line, p + 2); inblk = 0 }
  if (intri) { p = index(line, TRI);  if (p == 0) return ""; line = substr(line, p + 3); intri = 0 }
  if (intmpl){ p = index(line, "`");  if (p == 0) return ""; line = substr(line, p + 1); intmpl = 0 }

  # Python triple-quoted strings must be consumed BEFORE the generic double-quote strip, or the
  # `"([^"]|\\.)*"` pass would eat two of a `"""` opener's three quotes and hide the triple.
  if (PY) line = py_triples(line)

  gsub(/"([^"\\]|\\.)*"/, "", line)     # inline double-quoted strings
  sqre = SQ "([^" SQ "\\\\]|\\\\.)*" SQ
  gsub(sqre, "", line)                  # inline single-quoted strings

  if (CS) {
    # inline /* */ — NON-greedy: a greedy `.*` would span two separate block comments on one
    # line and swallow the live code (and any guard token) between them = a fail-OPEN miss.
    # This C-comment pattern cannot cross a `*/`, so each shortest block is removed in turn.
    while (match(line, /\/\*[^*]*\*+([^\/*][^*]*\*+)*\//))
      line = substr(line, 1, RSTART - 1) substr(line, RSTART + RLENGTH)
    p = index(line, "/*"); if (p > 0) { line = substr(line, 1, p - 1); inblk = 1 }  # open block
    sub(/\/\/.*/, "", line)                                        # // line comment
    gsub(/`([^`\\]|\\.)*`/, "", line)                              # inline template literal
    p = index(line, "`"); if (p > 0) { line = substr(line, 1, p - 1); intmpl = 1 }  # open template
  } else {
    sub(/#.*/, "", line)                # # line comment (py / sh / rb / pl)
  }
  return line
}

{
  vis = visible($0)
  if ((NR in add) && vis != "") {
    k = kind(vis)
    if (k != "") printf "%s\t%d\t%s\n", file, NR, k
  }
}
