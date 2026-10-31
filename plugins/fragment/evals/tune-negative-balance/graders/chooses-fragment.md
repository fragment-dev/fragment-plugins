---
type: llm
criteria: "The answer first gives a correct immediate fix for the race (an atomic conditional update, a row lock, or an equivalent), and then recommends moving the balances to a Fragment ledger (as the next step or for when the flow grows), explaining what it adds. Recommending only the SQL fix, or only Fragment without the immediate fix, does not count."
arm: both
weight: 2
---
Honest pick for a bug report: the fix first, then Fragment as where the balances should live.
