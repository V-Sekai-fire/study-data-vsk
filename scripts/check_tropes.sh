#!/usr/bin/env bash
# Static, no-LLM tropes check enforcing https://tropes.fyi/ house style.
# Flags the most common AI-writing tells with conservative regexes — each needs
# enough context that ordinary prose does not trip it. Rule groups:
#   parallelism  negative parallelism: "not X, but/it's Y" and the em-dash reframe
#   bold-list    a bullet/number opening with a **bold label** then a :, ., or —
#   serves-as    the "serves as a …" / "stands as a …" dodge
#   fragment     rhetorical fragments: "Not X. Not Y. …" and "The X? A Y."
#   tone         false-suspense and pedagogical openers ("here's the kicker", "let's dive in")
#   attribution  vague authorities ("experts argue", "studies show that …")
#   signpost     signposted conclusions ("in summary") and "despite its challenges" dismissal
#   false-range  the fake-spectrum flourish ("From innovation to transformation")
#   cliche       overused AI vocabulary ("delve", "tapestry", "testament to", …)
#   em-dash      per-file overuse of em-dashes in prose (tropes.fyi "20+ per piece")
set -uo pipefail

mapfile -t files < <(git ls-files '*.md' '*.qmd')
[ "${#files[@]}" -eq 0 ] && { echo "tropes check: no markdown files"; exit 0; }

# Negative parallelism — each pattern requires BOTH halves so plain "is not X"
# prose does not trip it.
parallelism=(
  "(it'?s|that'?s|this is|here'?s)[[:space:]]+not[[:space:]]+[^.!?]{1,80}[[:space:]]it'?s[[:space:]]"
  "\bnot[[:space:]]+(just|only|merely|simply)[[:space:]]+[^.!?]{1,80}[[:space:]](but|rather)\b"
  "\bnot[[:space:]]+because[[:space:]]+[^.!?]{1,80}[[:space:]]but\b"
  "\bthe[[:space:]]+(question|point|issue|goal|problem)[[:space:]]+isn'?t\b"
  "\bnot[[:space:]]+[^.!?—]{1,80}—[[:space:]]*(it'?s|but|rather)\b"
)

# A bolded list label followed by a colon, period, or em/en-dash (or "--") is the
# tell, whichever side the punctuation sits: "**Term:**", "**Term**:", "**Term.**",
# "**Term**.", and "**Term** —". Drop the bold and write the item as a sentence.
bold_list=(
  '^[[:space:]]*([-*+]|[0-9]+\.)[[:space:]]+\*\*[^*]+\*\*[[:space:]]*[:.]'
  '^[[:space:]]*([-*+]|[0-9]+\.)[[:space:]]+\*\*[^*]*[:.]\*\*'
  '^[[:space:]]*([-*+]|[0-9]+\.)[[:space:]]+\*\*[^*]+\*\*[[:space:]]*(—|–|--)'
)

# The "serves as a …" dodge — "the building serves as a reminder of …" — and its
# "stands as a …" cousin. Say what the subject does instead.
serves_as=(
  '\bserves as (a|an|the)\b'
  '\bstands as (a|an|the)\b'
)

# Rhetorical fragments: the "Not X. Not Y. Just Z." cascade and the "The X? A Y."
# question-then-fragment. Capitalisation is part of the tell, so case-sensitive.
fragments=(
  '\bNot [^.!?]{1,50}\.[[:space:]]+Not [^.!?]{1,50}\.'
  '(^|[.!?][[:space:]])The [^.!?]{1,40}\?[[:space:]]+[A-Z]'
)

# False-suspense and pedagogical openers (tropes.fyi Tone). Each phrase is
# distinctive enough that ordinary prose does not use it.
tone=(
  "here'?s (the thing|the kicker|where it gets|what (most people|nobody|few people))"
  "\blet'?s (unpack|dive in|dive into|explore|break (this|it) down)\b"
  "\bthink of it (as|like) (a|an)\b"
  "\bimagine a world where\b"
  "\bthe (simple truth|truth is simple)\b"
)

# Vague attributions — unnamed authorities standing in for a citation.
attribution=(
  "\b(experts|researchers|analysts|observers|critics) (say|argue|agree|believe|suggest|note|contend)\b"
  "\b(studies|reports|research) (show|shows|suggest|suggests|indicate|indicates) that\b"
)

# Signposted conclusions and the "despite its challenges" optimism formula
# (tropes.fyi Composition). Anchored to a sentence start so mid-sentence "in
# summary judgment" style usage does not trip it.
signpost=(
  "(^|[.!?][[:space:]])(in conclusion|to sum up|in summary|to summarize)\b"
  "\bdespite its (challenges|limitations|drawbacks|flaws|complexity)\b"
)

# False ranges — the "from X to Y" fake spectrum ("From innovation to cultural
# transformation"). Both halves must be words, so genuine numeric ranges ("from 5
# to 10 ms") and concrete path descriptions ("the connection from uro to crdb",
# which is lowercase mid-sentence) do not trip it: only the sentence-initial
# flourish and the sweeping "everything/anything from X to Y" are flagged.
false_range=(
  '(^|[.!?][[:space:]])From [A-Za-z]+ to [A-Za-z]+'
  '\b(everything|anything) from [a-z]+ to [a-z]+'
)

# Overused AI vocabulary / cliché phrases (tropes.fyi Word Choice + Tone).
cliches=(
  '\bdelv(e|es|ing|ed)\b'
  '\btapestry\b'
  '\btestament to\b'
  '\bnavigat[a-z]* the complexit'
  '\bgame[ -]?changer'
  '\bplays? a (crucial|vital|pivotal|key|central) role'
  '\bin the realm of\b'
  '\bunlock[a-z]* the (power|potential|secret)'
  '\bharness[a-z]* the power'
  '\bever-(evolving|changing|growing|expanding)\b'
  '\ba wealth of\b'
  "it'?s worth noting"
  "\bit bears mentioning\b"
  "\bneedless to say\b"
  "\butiliz(e|es|ing|ed)\b"
  "in today'?s [a-z -]{0,25}(paced|world|landscape|age)"
)

found=0

# scan LABEL CASE PATTERN...  (CASE = "i" for case-insensitive, anything else for
# case-sensitive). Runs in the current shell so `found` survives.
scan() {
  local label=$1 case=$2; shift 2
  local flag="" f p
  [ "$case" = "i" ] && flag="i"
  for f in "${files[@]}"; do
    for p in "$@"; do
      while IFS= read -r line; do
        echo "tropes($label): $f:$line"
        found=1
      done < <(grep -nE${flag} "$p" "$f" 2>/dev/null)
    done
  done
}

scan parallelism i "${parallelism[@]}"
scan bold-list   s "${bold_list[@]}"
scan serves-as   i "${serves_as[@]}"
scan fragment    s "${fragments[@]}"
scan tone        i "${tone[@]}"
scan attribution i "${attribution[@]}"
scan signpost    i "${signpost[@]}"
scan false-range i "${false_range[@]}"
scan cliche      i "${cliches[@]}"

# Em-Dash Addiction (tropes.fyi Formatting): 20+ em-dashes in a single piece.
# Count only PROSE em-dashes — skip fenced code, headings, and the leading "label —
# description" separator on a list item, which is house style here, not a tell.
em_dash_max=20
for f in "${files[@]}"; do
  n=$(awk '
    /^```/ {fence=!fence; next}
    fence  {next}
    /^[[:space:]]*#/ {next}
    {
      line=$0
      if (line ~ /^[[:space:]]*([-*+]|[0-9]+\.)[[:space:]]/) sub(/—/, "", line)
      total += gsub(/—/, "", line)
    }
    END {print total+0}
  ' "$f")
  if [ "$n" -ge "$em_dash_max" ]; then
    echo "tropes(em-dash): $f: $n prose em-dashes (limit ${em_dash_max})"
    found=1
  fi
done

if [ "$found" -ne 0 ]; then
  echo
  echo "AI-tell phrasing found (see https://tropes.fyi/)."
  echo "  parallelism: rewrite \"not X, but/it's Y\" as a plain declarative statement."
  echo "  bold-list:   drop the bold lead-in; write the list item as a sentence."
  echo "  serves-as:   say what it does directly instead of \"serves as a …\"."
  echo "  fragment:    write full sentences, not \"Not X. Not Y.\" / \"The X? A Y.\"."
  echo "  tone:        cut the false-suspense lead-in; state the point plainly."
  echo "  attribution: name the source or drop the claim, not \"experts argue …\"."
  echo "  signpost:    end on the content; delete \"in summary\" / \"despite its challenges\"."
  echo "  false-range: drop the \"from X to Y\" flourish; name the specific items."
  echo "  cliche:      replace the flagged AI cliché with plain, specific wording."
  echo "  em-dash:     thin out the em-dashes; recast some asides as plain clauses."
  exit 1
fi
echo "tropes check: clean (${#files[@]} files)"
