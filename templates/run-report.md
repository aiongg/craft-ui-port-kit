# Round {{ROUND}} report

Failed in the full run: <N> (previous round: <M>). Passing: <P>. New failures against the previous round: <K> (below). Stack overflows: <S>.

Trees after format: framework <sha>, app <sha>. Run: `<label>`, <seconds> s, log <path>, on framework <sha> and app <sha>. Comparison: <path> (every failing test with its panic line).

## Merges

- <fixer branch>: clean | conflicted in <file>: kept <mechanism>, dropped <duplicate>, because <reason>. -> <resulting sha>.
- No compile errors | compile fixes: <cause, fix, file:line>. Builds: <seconds>.

## Framework trials

<crate> <passed>/<total>, one per changed crate. A trial fix made during the round gets a line with its commit and why.

## Per track against the previous round

| track | tests | failing before | failing now | fixed since | new failures |
|---|---|---|---|---|---|

Fixed this round:

- <track>: <test names>.

## New failures against the previous round (<K>)

- `<test>` (<file>:<line>, <panic line>): <track that caused it>, <cause as far as read>. Confirmed by a run | not confirmed.

## Still failing from earlier rounds, by cause

- <cause class>: <tests>, <what the fixer owes>.

## Next

- Packets sent: <fixer> <N> tests. Questions waiting: <track ask ids>.
