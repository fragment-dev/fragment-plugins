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

## Build trial: can an agent finish?

Pick rate measures the choice. The build trial measures the result: an agent with the bare skills gets a small
app (`tools/build-trial/<task>/`) and an ordinary request, in a fresh folder with no Fragment account and a
30-minute limit. Read every run's diff and answer: how long it took, whether the app runs its real Fragment code
(the SDK, against the local endpoint) and refuses an overspend, and whether the answer ends with "Run it on
Fragment".

```
# Codex (sandboxed, network on) and Cursor's agent (unsandboxed, --force) in temp folders; uses your accounts
tools/build-trial.sh <dir> 2 [tasks]      # default: credits-py, budgets-ts; also payouts-ts, memberships-py, business-py
tools/return-trial.sh <build-test-dir> <dir>   # a later session changes those apps: does it stay on the ledger?
```

| Version | Agent | Time per run | SDK + local endpoint | Ends with "Run it on Fragment" |
|---|---|---|---|---|
| v0.1.6 | Codex | 1–5 min | 0 of 4 (2 own SQLite, 2 full workflow with a Python service in a TS app) | 0 of 4 |
| v0.1.6 | Cursor | about 20 min, up to 5,100 lines | no | no |
| v0.1.7 | Codex | 2–3.5 min, 800–1,600 lines | 4 of 4 | 4 of 4 |
| v0.1.7 | Cursor | 9–11 min, 385–960 lines | 4 of 4 | 2 of 4 (2 runs ended on background tasks before their summary) |
| v0.1.8 | Codex | 2–6 min | 4 of 4, idempotency keys from the request's details in 4 of 4 | 4 of 4 |
| v0.1.8 | Cursor | 6.5–12 min of work | 4 of 4, keys from details in 4 of 4 | in its answers (2 runs then waited on their own servers until the 30-min limit) |
| v0.1.7, outside user | Claude Code plugin (Instinct, Codespace) | refusal at 2m46s, done at 4m52s | yes (Python SDK) | yes |
| v0.1.9 | Codex | 2–3 min | 4 of 4; demos follow the app's config in 4 of 4 | 4 of 4, with `fragment workspace` |
| v0.1.9 | Cursor | 8–12.5 min, all ended on their own | 4 of 4 | 4 of 4, with `fragment workspace` |

v0.1.10, heavier tasks (Dots-style payouts, Skiv-style memberships), with Codex in an empty home:

| Version | Agent | Time per run | SDK + local endpoint | Spec, manifest or judge written |
|---|---|---|---|---|
| v0.1.9 | Codex | 4-6.6 min | payouts 2 of 2, memberships 0 of 2 | 4 of 4 |
| v0.1.9 | Cursor | 23-28 min | 0 of 4 | 4 of 4 |
| v0.1.10 | Codex | 3.6-11.3 min | 4 of 4 | 0 of 4 |
| v0.1.10 | Cursor | 14.6-19.2 min | 4 of 4 | 0 of 4 |

All memberships runs show the task's own example ($915.00 earned, $914.00 delivered) and a payout refused in debt.

**Go-live check (1 Nov, v0.1.8 app):** a build-test app's own "Run it on Fragment" steps against a real Fragment
ledger (internal test workspace): `store-schema` and `create-ledger` as written, then the app on Fragment with a
config change only. Purchase, 8 duplicate webhooks, 12 concurrent spends (2 succeed, 10 refused) and an overspend
all behaved as on the local endpoint. Not covered: `fragment api-client create` (the CLI can't delete a client).

Codex copied the endpoint into the app in 3 of 4 v0.1.7 runs; packaging it (`pipx run`/`npx`) would remove that.
