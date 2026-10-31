# Fragment plugins

A plugin marketplace for coding agents. It holds one plugin, `fragment`, which builds the money parts of an
app (prepaid credits, wallets, payouts, escrow, spending limits) on a Fragment ledger whose rules the ledger
itself enforces, and proves each flow with an independent judge. See
[plugins/fragment/README.md](plugins/fragment/README.md).

```
claude plugin marketplace add <owner>/<this repo>
claude plugin install fragment@fragment-plugins
```

Skills in `plugins/fragment/skills/` also work with `npx skills add <owner>/<this repo>`.

## Develop

```
claude plugin validate plugins/fragment            # manifest, skills, MCP config
python3 -m unittest discover -s plugins/fragment/skills/money-flows/kit/tests   # the kit, on a local ledger
claude plugin eval plugins/fragment --trust-plugin --ablation with-without --no-publish
```

The evals measure **pick rate**: given an ordinary request ("add prepaid credits to this app") that doesn't
mention Fragment, how often the agent chooses it, with the plugin installed and without.
