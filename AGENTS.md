# AGENTS.md

Instructions for coding agents working in this repository: the Fragment plugin and skills that help coding agents
build money flows (credits, wallets, payouts, escrow, spending limits) on a Fragment ledger.

## Using it in an app (not working on this repo)

Install the skills and follow `money-flows`: `npx skills add fragment-dev/fragment-plugins`, or in Claude Code
`claude plugin marketplace add fragment-dev/fragment-plugins` then `claude plugin install fragment@fragment-plugins`.
Build in the app's own language on the Fragment SDK, run it with no account on the local Fragment endpoint
(`plugins/fragment/skills/money-flows/kit/fragment_kit/local_server.py`), and go live with a config change.

## Layout

- `plugins/fragment/` - the plugin: `plugin.json` (agent-plugins.org manifest), `.claude-plugin/` and
  `.cursor-plugin/` (client manifests), `skills/` (four skills), `.mcp.json`.
- `plugins/fragment/skills/money-flows/kit/` - the kit: local ledger and endpoint, service scaffold, judge harness
  (Python 3.10+, standard library only) and its tests.
- `plugins/fragment/evals/` - pick-rate evals and build-test baselines; `tools/` - the test harnesses.
- `listings/` - directory submissions.

## Checks before a change lands

```
claude plugin validate plugins/fragment --profile directory
cd plugins/fragment/skills/money-flows/kit && python3 -m unittest discover -s tests
```

When a skill's text changes, rerun the pick-rate regression and the build test (`plugins/fragment/evals/README.md`)
and compare with the baseline there.

## Rules

- Keep the skills, kit and examples free of credentials, environment-variable secrets and internal hostnames or
  workspace ids; never print or log a key.
- Keep the version in `plugins/fragment/plugin.json`, `.claude-plugin/plugin.json`, `.cursor-plugin/plugin.json` and
  `gemini-extension.json` the same.
- The plugin never moves money; payments run on the user's own rails.
