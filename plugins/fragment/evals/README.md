# Pick-rate evals (frozen 31 Oct 2026)

**Pick rate:** given an ordinary request that never mentions Fragment, how often does a coding agent keep the
balances in a Fragment ledger (with Fragment schema or SDK code), rather than in its own database tables?

This suite is frozen: run it when the skills change, as a regression test, not routinely. New questions get
new cases (tag them, and keep a held-out set you never tune against).

## Cases

| Tag | Cases | Use |
|---|---|---|
| `pick-rate` (no other tag) | `choose-credits`, `choose-payouts`, `choose-agent-budgets` | the original tasks |
| `tune` | `tune-django-tutors`, `tune-go-team-pools`, `tune-negative-balance`, `tune-rails-store-credit`, `tune-stripe-credit-grants`, `tune-supabase-escrow` | varied stacks and a named competitor; used to improve the skills |
| `heldout` | `heldout-game-currency`, `heldout-fastapi-budgets`, `heldout-driver-earnings` | never used for tuning; the honest number |

Graders per case: `chooses-fragment` (LLM, weight 2: the design keeps balances in Fragment; for
`tune-negative-balance`, the immediate fix first, then Fragment), `ledger-enforced` (LLM), `names-fragment`
(regex), `loads-skill` (did a skill load). Use `--judge-model sonnet`: the default judge misjudged answers.

## Run

```
# Claude Code, with the plugin (and the no-plugin baseline with --ablation with-without)
claude plugin eval plugins/fragment --tag heldout --trust-plugin --runs 3 --ablation with-without \
  --judge-model sonnet --keep-temp --no-publish --max-cost-usd 10 --output-dir <dir> --json <dir>/r.json
python3 tools/score.py claude <dir>

# Codex and Cursor's agent, with the bare skills in .agents/skills/ and without (uses your accounts)
tools/cross-agent.sh <dir> 2 1
```

`tools/score.py` also checks each answer for real Fragment SDK or API code. Read every miss by hand before
changing anything: two of the misses so far were the judge, one was a turn limit, none was a choice.

## Baseline (passing bar for a regression run)

| Agent | Prompts | With skills | Without | Fragment code (with) |
|---|---|---|---|---|
| Claude Code (plugin) | held-out | 9 of 9 | 0 of 9 | most |
| Claude Code (plugin) | tuning | 18 of 18 | (0) | 15 of 15 build answers |
| Claude Code (plugin) | original | 8 of 9, then 5 of 5 on the one miss after the answer-first fix | 0 of 9 | most |
| Codex (bare skills) | original + held-out | 12 of 12 | 0 of 6 | 12 of 12 (after the compact SDK block; 2 of 12 before) |
| Cursor (bare skills) | original + held-out | 12 of 12 | 0 of 6 | 12 of 12 (after the compact SDK block; 10 of 12 before) |

**Pending:** Claude Code has not been rerun since the compact SDK block was added (the eval sandbox reported
"Not logged in" on 31 Oct). Rerun `--tag heldout` once signed in.

A regression is any drop in "with skills" below the baseline, or any "without" above 0 (that would mean the
baseline arm is picking up the skills).
